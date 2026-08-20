"""Hugging Face Spaces Entrypoint for ARIA (AI-Powered Repository Intelligence Agent).

Bridges the existing ARIA FastAPI application with the Hugging Face Gradio runtime.
Exposes:
  - All native FastAPI routes (/api/v1/*, /health, /docs, /openapi.json)
  - Full SSE/streaming analysis pipelines
  - Gradio dashboard UI at /gradio
"""

import os
import sys

# Ensure project root is on sys.path so all local modules (backend, core, services, etc.) resolve cleanly
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from backend.api import app as fastapi_app

try:
    import gradio as gr

    # Create a clean Gradio dashboard interface for Hugging Face Spaces UI
    with gr.Blocks(title="ARIA — Autonomous Repository Intelligence Agent") as demo:
        gr.Markdown("# ⚡ ARIA — Autonomous Repository Intelligence Engine")
        gr.Markdown(
            """
            ### 🟢 Backend is Live on Hugging Face Spaces (16 GB RAM)
            
            - **Interactive OpenAPI Documentation**: [`/docs`](/docs)
            - **System Health Status**: [`/health`](/health)
            - **Metrics**: [`/metrics`](/metrics)
            - **API Canonical Base**: `/api/v1/`
            - **SSE Stream Analysis**: `POST /api/v1/analyze`
            
            *This space provides backend inference, AST parsing, and graph construction for the ARIA web client.*
            """
        )

    # Mount the Gradio demo onto our full FastAPI application under /gradio.
    # This ensures that root API routes (/api/v1/*, /health, /docs) and SSE streams remain top-level and unmodified.
    app = gr.mount_gradio_app(fastapi_app, demo, path="/gradio")
except ImportError:
    # Fallback to pure FastAPI if Gradio is not installed in the local environment
    app = fastapi_app

if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", 7860))
    uvicorn.run(app, host="0.0.0.0", port=port)
