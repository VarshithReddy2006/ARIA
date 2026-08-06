"""Unit and Architectural Regression Tests for Observability Core (R-019)."""

import json
import logging
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from backend.exception_handlers import register_exception_handlers
from backend.logging_config import HumanFormatter, JsonFormatter, configure_logging
from backend.logging_middleware import RequestIdMiddleware
from backend.metrics_middleware import MetricsMiddleware
from backend.routers.health import router as health_router
from core.observability import (
    MetricsCollector,
    RedactionFilter,
    RequestContext,
    get_current_request_id,
    metrics_collector,
    request_id_var,
    sanitize_sensitive_data,
    time_operation,
)
from ria.interfaces.rest.exceptions import RESTAPIException


# ---------------------------------------------------------------------------
# 1. Sensitive Data Redaction Tests
# ---------------------------------------------------------------------------

def test_sensitive_data_redaction():
    text = (
        "Connecting with gemini_key AIzaSyABC12345678901234567890123456789 "
        "and openai sk-123456789012345678901234 and github ghp_123456789012345678901234567890123456 "
        "and Bearer eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.signature"
    )
    cleaned = sanitize_sensitive_data(text)

    assert "AIzaSy" not in cleaned or "AIzaSy***REDACTED***" in cleaned
    assert "sk-123456789012345678901234" not in cleaned
    assert "ghp_123456789012345678901234567890123456" not in cleaned
    assert "signature" not in cleaned or "eyJ***REDACTED***" in cleaned


def test_redaction_dict_sanitization():
    payload = {
        "api_key": "secret_key_12345",
        "user": "admin",
        "password": "super_secret_password",
        "nested": {"token": "bearer_abc"},
    }
    cleaned = sanitize_sensitive_data(payload)

    assert cleaned["api_key"] == "***REDACTED***"
    assert cleaned["password"] == "***REDACTED***"
    assert cleaned["user"] == "admin"
    assert cleaned["nested"]["token"] == "***REDACTED***"


def test_json_and_human_formatters_redact():
    record = logging.LogRecord(
        name="test_logger",
        level=logging.INFO,
        pathname="test.py",
        lineno=1,
        msg="Logging key GOOGLE_API_KEY_PLACEHOLDER",
        args=(),
        exc_info=None,
    )

    token = request_id_var.set("test-req-123")
    try:
        json_fmt = JsonFormatter()
        json_out = json_fmt.format(record)
        assert "AIzaSy***REDACTED***" in json_out
        assert "test-req-123" in json_out

        human_fmt = HumanFormatter()
        human_out = human_fmt.format(record)
        assert "AIzaSy***REDACTED***" in human_out
        assert "test-req-123" in human_out
    finally:
        request_id_var.reset(token)


# ---------------------------------------------------------------------------
# 2. Request ID Ownership Tests
# ---------------------------------------------------------------------------

def test_request_id_middleware_preserves_or_generates():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)

    @app.get("/test-id")
    def sample_endpoint(request: Request):
        return {"req_id": request.state.request_id, "ctx_id": get_current_request_id()}

    client = TestClient(app)

    # 1. Custom client header provided
    res1 = client.get("/test-id", headers={"X-Request-ID": "custom-uuid-999"})
    assert res1.status_code == 200
    assert res1.headers["X-Request-ID"] == "custom-uuid-999"
    assert res1.json()["req_id"] == "custom-uuid-999"
    assert res1.json()["ctx_id"] == "custom-uuid-999"

    # 2. Generated UUID when omitted
    res2 = client.get("/test-id")
    assert res2.status_code == 200
    assert "X-Request-ID" in res2.headers
    assert len(res2.headers["X-Request-ID"]) > 10
    assert res2.json()["req_id"] == res2.headers["X-Request-ID"]


# ---------------------------------------------------------------------------
# 3. Standardized Error Response Envelope Tests
# ---------------------------------------------------------------------------

def test_error_response_envelope_standardization():
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware)
    register_exception_handlers(app)

    @app.get("/http-error")
    def trigger_http_error():
        raise HTTPException(status_code=404, detail="Item not found")

    @app.get("/custom-error")
    def trigger_custom_error():
        raise RESTAPIException("Invalid resource requested", status_code=400)

    @app.get("/500-error")
    def trigger_500():
        raise RuntimeError("Internal crash with secret password=mysecret123")

    client = TestClient(app, raise_server_exceptions=False)

    # 1. HTTPException 404
    res1 = client.get("/http-error", headers={"X-Request-ID": "req-404"})
    assert res1.status_code == 404
    body1 = res1.json()
    assert body1["request_id"] == "req-404"
    assert body1["status"] == "error"
    assert body1["code"] == 404
    assert body1["message"] == "Item not found"
    assert body1["details"] is None

    # 2. Custom RESTAPIException 400
    res2 = client.get("/custom-error", headers={"X-Request-ID": "req-400"})
    assert res2.status_code == 400
    body2 = res2.json()
    assert body2["request_id"] == "req-400"
    assert body2["code"] == 400
    assert body2["message"] == "Invalid resource requested"

    # 3. Catch-all 500
    res3 = client.get("/500-error", headers={"X-Request-ID": "req-500"})
    assert res3.status_code == 500
    body3 = res3.json()
    assert body3["request_id"] == "req-500"
    assert body3["code"] == 500
    assert body3["message"] == "An internal server error occurred."
    assert "mysecret123" not in res3.text
    assert "Traceback" not in res3.text


# ---------------------------------------------------------------------------
# 4. Liveness vs Readiness Probes Tests
# ---------------------------------------------------------------------------

def test_liveness_and_readiness_endpoints():
    app = FastAPI()
    app.include_router(health_router)
    client = TestClient(app)

    # 1. GET /health (Liveness)
    res_liveness = client.get("/health")
    assert res_liveness.status_code == 200
    assert res_liveness.json()["status"] == "healthy"
    assert res_liveness.json()["backend"] == "online"

    # 2. GET /ready (Readiness)
    res_readiness = client.get("/ready")
    assert res_readiness.status_code == 200
    body_ready = res_readiness.json()
    assert body_ready["status"] == "ready"
    assert "storage" in body_ready["checks"]
    assert "parser" in body_ready["checks"]


# ---------------------------------------------------------------------------
# 5. Metrics Abstraction Tests
# ---------------------------------------------------------------------------

def test_metrics_collector_exporter_decoupling():
    collector = MetricsCollector()
    collector.increment_request("GET", "/api/v1/test", 200)
    collector.record_request_duration("GET", "/api/v1/test", 200, 0.05)
    collector.record_cache_access(hit=True, cache_key="call_graph")

    prom_output = collector.generate_prometheus_metrics()
    assert 'http_requests_total{method="GET",path="/api/v1/test",status="200"} 1.0' in prom_output
    assert 'cache_hits_total{cache_key="call_graph"} 1.0' in prom_output


# ---------------------------------------------------------------------------
# 6. Reusability Outside FastAPI Tests
# ---------------------------------------------------------------------------

def test_observability_core_outside_fastapi():
    # Verify RequestContext context manager works in standalone Python scripts / MCP tools
    with RequestContext(request_id="mcp-task-001", repository="my-repo") as ctx:
        assert get_current_request_id() == "mcp-task-001"
        assert request_id_var.get() == "mcp-task-001"

        # Verify time_operation works without HTTP request
        with time_operation("symbol_indexing", repository="my-repo"):
            pass

    assert get_current_request_id() == ""
