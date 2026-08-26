# ARIA Azure Deployment Assets

This directory contains configuration templates, manifests, and deployment automation scripts for deploying ARIA to **Azure Container Apps (ACA)** and **Azure Container Apps Jobs**.

---

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

## Target Azure Architecture

```
User Browser
    │
    ▼
Azure Container Apps (FastAPI API + Astro Frontend)
    │
    ├── Health & Readiness Probes (/health, /ready)
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
    ├── Embeds code via local BGE model
    └── Indexes Vectors to Qdrant Cloud
    │
    ▼
Persistent Storage (/app/data on Azure Files volume)
    ├── SQLite database (repo_understanding.db with WAL)
    ├── Serialized Store (analysis_store.json)
    └── Snapshot Storage (data/snapshots/)
```

---

## Directory Contents

| Path | Purpose |
| :--- | :--- |
| `scripts/create-resources.ps1` | Creates Resource Group, Azure Container Registry, Storage Account, Queue, and Container Apps Environment. |
| `scripts/deploy-api.ps1` | Builds `Dockerfile.api`, pushes image to ACR, and deploys/updates the API Container App. |
| `scripts/deploy-worker.ps1` | Builds `Dockerfile.worker`, pushes image to ACR, and deploys/updates the Worker Container App Job. |
| `container-apps-api.yaml` | Declarative ACA template for API with HTTP ingress, scale-to-zero, and health probes. |
| `container-apps-job.yaml` | Declarative ACA Job template for Queue-triggered background analysis execution. |

---

## Cost-Control & Scale-to-Zero

To maximize budget efficiency under the Azure Student credit ($100):
1. **API Scale-to-Zero**: The API Container App is configured with `minReplicas: 0`, meaning it scales down to 0 vCPUs when idle.
2. **Worker Event-Driven Execution**: The worker runs as a Container Apps Job triggered by queue depth (or ephemeral manual trigger), consuming compute only while analysis is actively executing.
3. **External Vector Database**: Uses the existing Qdrant Cloud tier instead of deploying an expensive managed vector cluster.
4. **No Managed Kubernetes / GPU clusters**: Minimal standard CPU allocation (1.0 vCPU for API, 2.0 vCPU for Worker).

---

## Switching Between Environments

### To run Locally:
```bash
export JOB_EXECUTOR=local
export PUBLIC_API_URL=http://127.0.0.1:8001
uvicorn backend.api:app --host 127.0.0.1 --port 8001
```

### To run on Modal:
```bash
export JOB_EXECUTOR=modal
modal run modal_app.py
```

### To deploy to Azure (When ready):
1. Authenticate with Azure CLI: `az login`
2. Run provisioning: `.\azure\scripts\create-resources.ps1`
3. Deploy API: `.\azure\scripts\deploy-api.ps1`
4. Deploy Worker: `.\azure\scripts\deploy-worker.ps1`
