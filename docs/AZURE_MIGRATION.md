# ARIA Azure Deployment & Migration Guide

This document outlines the deployment architecture, configuration, testing procedures, and operational guidelines for running ARIA on **Microsoft Azure (Azure Container Apps)** alongside the existing **Modal** and **Local** deployment targets.

## Current Azure Environment

| Resource Component | Provisioned Name / Value | Target Region | Billing Tier / SKU |
| :--- | :--- | :--- | :--- |
| **Subscription** | Azure for Students (`3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0`) | — | Student Credit ($100) |
| **Resource Group** | `aria-rg` | `eastasia` | Standard |
| **Container Apps Environment** | `aria-env` | `eastasia` | Consumption (Serverless, $0 idle) |
| **Container Registry (ACR)** | `ariacr3ab8` | `eastasia` | Basic ($0.167/day) |
| **ACR Login Server** | `ariacr3ab8.azurecr.io` | `eastasia` | — |
| **Storage Account** | `ariastg3ab8` | `eastasia` | Standard_LRS (StorageV2) |
| **Storage Queue** | `aria-analysis-jobs` | `eastasia` | Standard Queue |
| **Azure Files Share** | `aria-data` (5 GB quota) | `eastasia` | Mounted as `ariadata` (`/app/data`) |
| **Log Analytics Workspace** | `workspace-ariargng7x` | `eastasia` | Pay-as-you-go |

---

## 1. Architecture Overview

### Target Azure Topology
```
User Browser
    │
    ▼
Azure Container Apps (FastAPI API + Astro Frontend)
    │
    ├── /health (Liveness) & /ready (Readiness Probes)
    ├── REST API Endpoints (/api/v1/*)
    └── Submit Analysis Job (POST /api/v1/analyze)
    │
    ▼
Azure Storage Queue (`aria-analysis-jobs`)
    │
    ▼
Azure Container Apps Job / Worker (`backend.worker`)
    │
    ├── Dequeues Job Payload
    ├── Executes FROZEN execute_repository_analysis(...)
    ├── Updates JobState Progress
    ├── Embeds code via local BGE model (BAAI/bge-small-en-v1.5)
    └── Indexes Vectors to Qdrant Cloud
    │
    ▼
Persistent Storage (/app/data on Azure Files volume)
    ├── SQLite database (repo_understanding.db with WAL)
    ├── Serialized Store (analysis_store.json)
    └── Snapshot Storage (data/snapshots/)
```

### Core Engine Independence
The core repository intelligence and analysis engine (`execute_repository_analysis` in `backend/routers/repositories.py`) remains **100% frozen and infrastructure-agnostic**. The same analysis logic runs identically whether dispatched via Local threads, Modal functions, or Azure Container App Jobs.

```
                    ARIA CORE ENGINE
                           │
                           ▼
              execute_repository_analysis()
                           │
                           ▼
                      JobExecutor
                    /      │      \
               Local     Modal    Azure
```

---

## 2. Infrastructure Abstraction Layer

The `infrastructure/job_executor.py` module exposes the `JobExecutor` abstraction:

1. **`LocalJobExecutor`**: Dispatches analysis tasks to in-process background threads. Default for development and local testing.
2. **`ModalJobExecutor`**: Dispatches tasks to serverless Modal functions (`modal_app.run_analysis_job.spawn`).
3. **`AzureJobExecutor`**: Enqueues structured JSON payloads to Azure Storage Queue or Azure Service Bus.

### Factory Resolution
The active executor is resolved at runtime via `get_job_executor()`:
- `JOB_EXECUTOR=local` (default)
- `JOB_EXECUTOR=modal`
- `JOB_EXECUTOR=azure`

---

## 3. Storage Design & SQLite Safety on Azure

| Data Category | Purpose | Persistence Nature | Azure Target |
| :--- | :--- | :--- | :--- |
| **Workspace Repositories** | Cloned git repositories | Ephemeral Workspace | Container `/tmp/cloned_repos` |
| **Relational Metadata** | `repo_understanding.db` | Persistent App State | Azure Files `/app/data` (SQLite WAL) |
| **Analysis Store** | `analysis_store.json` | Persistent App State | Azure Files `/app/data` (Atomic JSON) |
| **Analysis Snapshots** | AST, Symbol, Graph snapshots | Persistent App State | Azure Files `/app/data/snapshots` |
| **Vector Embeddings** | Code chunks & dense vectors | Persistent Vector DB | External Qdrant Cloud Cluster |
| **Job Progress & State** | Job lifecycle tracking | Shared State | Memory / Storage Queue / Shared Store |

### SQLite on Azure Files Safety
> [!WARNING]
> SQLite is safe on Azure Files mounted volumes when write operations are serialized through repository-level locking (`repository_lock()`) and WAL mode with atomic file transactions.
>
> To prevent lock contention across multiple worker instances:
> - Container Apps Jobs are configured with single execution parallelism per repository.
> - The in-process `repository_lock` and atomic file write utilities in `core/concurrency.py` prevent partial file corruptions.

---

## 4. Background Worker (`backend.worker`)

The worker process is independently runnable and container-ready:
```bash
# Run continuous polling worker loop
python -m backend.worker

# Run once (processes at most one message, then exits)
python -m backend.worker --run-once

# Run with local in-memory queue (no cloud credentials required)
python -m backend.worker --run-once --memory-queue
```

### Worker Lifecycle:
1. Dequeues message from `aria-analysis-jobs`.
2. Sets job state to `RUNNING` with `started_at` timestamp.
3. Invokes the frozen `execute_repository_analysis(...)` with real-time progress callbacks.
4. On success: marks job `COMPLETED`, records duration, and commits output.
5. On failure: marks job `FAILED`, records sanitized diagnostics via `format_analysis_error(exc)`.

---

## 5. Cost-Control Strategy (Azure Student $100 Credit)

To ensure ARIA operates within a minimal, cost-effective development budget:
- **Zero-Cost Idle API**: `aria-api` is configured with `minReplicas: 0` in Azure Container Apps, scaling down to 0 compute when no HTTP traffic arrives.
- **Event-Driven Compute for Workers**: `aria-worker-job` spins up only when analysis tasks are queued, terminating immediately upon job completion.
- **No Managed Kubernetes / Dedicated VMs**: Uses serverless Container Apps rather than AKS clusters.
- **No GPU Deployment**: Uses CPU-optimized BGE embedding inference locally on the worker.
- **Storage Tiering**: Basic ACR and Standard LRS Storage Account.

---

## 6. How to Switch Environments

### Switch to Local:
```bash
export JOB_EXECUTOR=local
export PUBLIC_API_URL=http://127.0.0.1:8001
uvicorn backend.api:app --host 127.0.0.1 --port 8001
```

### Switch to Modal:
```bash
export JOB_EXECUTOR=modal
modal run modal_app.py
```

### Switch to Azure:
```bash
export JOB_EXECUTOR=azure
export AZURE_STORAGE_CONNECTION_STRING="<connection-string>"
export AZURE_STORAGE_QUEUE_NAME="aria-analysis-jobs"
uvicorn backend.api:app --host 0.0.0.0 --port 8001
```

---

## 7. Rollback Procedure

If an Azure deployment needs to be rolled back to Modal:
1. Re-point frontend DNS or `PUBLIC_API_URL` to the Modal web endpoint (`https://<modal-workspace>--aria-web.modal.run`).
2. Set `JOB_EXECUTOR=modal` in configuration.
3. The identical core engine ensures 100% feature parity and zero schema drift.

---

## 8. Deployment Execution (When Approved)

When ready to perform live deployment to Azure:
1. Authenticate: `az login`
2. Run infrastructure provisioning:
   ```powershell
   .\azure\scripts\create-resources.ps1
   ```
3. Deploy API Container:
   ```powershell
   .\azure\scripts\deploy-api.ps1
   ```
4. Deploy Worker Container App Job:
   ```powershell
   .\azure\scripts\deploy-worker.ps1
   ```
