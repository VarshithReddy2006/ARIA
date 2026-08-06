# Developer Guide

This guide describes how to extend the Repo Intelligence Agent by adding new analysis services and wiring them into the build pipeline.

## 1. Adding a New Analysis Service

1. Create a new service under `services/`, e.g., `services/security_scanner_service.py`.
2. Define a class implementing the analysis logic:
   ```python
   class SecurityScannerService:
       def build(self, repo_name: str, repo_path: str = None, files: list = None) -> None:
           # Perform analysis and save results using snapshot_store
           from backend.dependencies import snapshot_store

           snapshot_store.save(repo_name, "security_issues", {"issues": []})
   ```

## 2. Registering the Service in the DAG

Open `backend/dependencies.py` and register your service class on the `analysis_registry` singleton:

```python
# Import your new service class
from services.security_scanner_service import SecurityScannerService

# Register in DAG
analysis_registry.register(
    "Security Scan",
    SecurityScannerService,
    dependencies=["Symbol Index"],  # Run after Symbol Index completes
    outputs=["security_issues"],
)
```
The `ExecutionScheduler` will automatically place your task in the correct execution stage, and the `ParallelExecutionRunner` will schedule it concurrently. No manual threading or stage management is needed!
