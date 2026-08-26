# ARIA — Azure Infrastructure Provisioning & Deployment Checkpoint

**Date**: 2026-08-22
**Target Environment**: Microsoft Azure Container Apps (Serverless / Consumption)
**Subscription**: Azure for Students (`3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0`)
**Status**: **INFRASTRUCTURE_READY**

---

## 1. Preflight Verification Summary

| Preflight Check | Target | Status | Notes |
| :--- | :--- | :---: | :--- |
| **Azure CLI** | Version 2.89.1 | **PASSED** | Installed and operational on 64-bit host. |
| **Authentication** | MSAL / Azure CLI Session | **PASSED** | Authenticated as student account (`24B81A05NL@cvr.ac.in`). |
| **Active Subscription** | Azure for Students | **PASSED** | ID: `3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0` (Enabled). |
| **Tenant** | CVR College of Engineering | **PASSED** | Tenant ID: `5c90ddac-41c6-456f-8ac6-8bc0facfe185`. |
| **Target Region** | Single Consistent Region | **PASSED** | `eastasia` selected consistently across all resources. |
| **Resource Providers** | `Microsoft.App`, `Microsoft.ContainerRegistry`, `Microsoft.Storage`, `Microsoft.OperationalInsights` | **PASSED** | All providers registered and active. |

---

## 2. Provisioned Azure Infrastructure Summary

All resources are consolidated in the dedicated `aria-rg` resource group within the `eastasia` region under the student budget ($100 credit).

| Component | Provisioned Name | Type | Billing Tier / SKU | Configuration & Purpose |
| :--- | :--- | :--- | :--- | :--- |
| **Resource Group** | `aria-rg` | `Microsoft.Resources/resourceGroups` | Standard | Regional boundary for all ARIA cloud assets. |
| **Container Registry** | `ariacr3ab8` | `Microsoft.ContainerRegistry/registries` | **Basic** ($0.167/day) | Stores `aria-api` and `aria-worker` images (`ariacr3ab8.azurecr.io`). |
| **Storage Account** | `ariastg3ab8` | `Microsoft.Storage/storageAccounts` | **Standard_LRS** (StorageV2) | Low-cost standard storage account with no public blob access. |
| **Storage Queue** | `aria-analysis-jobs` | `Microsoft.Storage/storageAccounts/queueServices/queues` | Standard | High-throughput asynchronous analysis job queue. |
| **Azure File Share** | `aria-data` | `Microsoft.Storage/storageAccounts/fileServices/shares` | Standard (5 GB quota) | Mounted as `ariadata` (`/app/data`) for SQLite WAL & store. |
| **Container Apps Environment** | `aria-env` | `Microsoft.App/managedEnvironments` | **Consumption** ($0 idle) | Serverless execution environment with scale-to-zero support. |
| **Log Analytics** | `workspace-ariargng7x` | `Microsoft.OperationalInsights/workspaces` | Pay-as-you-go | Container log aggregation and telemetry diagnostics. |

---

## 3. Resource IDs

```text
Resource Group:
/subscriptions/3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0/resourceGroups/aria-rg

Container Apps Environment:
/subscriptions/3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0/resourceGroups/aria-rg/providers/Microsoft.App/managedEnvironments/aria-env

Azure Container Registry:
/subscriptions/3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0/resourceGroups/aria-rg/providers/Microsoft.ContainerRegistry/registries/ariacr3ab8

Storage Account:
/subscriptions/3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0/resourceGroups/aria-rg/providers/Microsoft.Storage/storageAccounts/ariastg3ab8

Container Apps Storage Mount:
/subscriptions/3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0/resourceGroups/aria-rg/providers/Microsoft.App/managedEnvironments/aria-env/storages/ariadata
```

*(Note: Sensitive keys, tokens, and storage connection strings are never printed or stored in repository documentation).*

---

## 4. Cost-Safety & Topology Audit

Before advancing to container deployment, the environment was audited for strict budget compliance under the $100 student credit:
- **No Dedicated VMs**: No virtual machines are deployed or required for the ARIA pipeline.
- **No Managed Kubernetes / AKS**: Compute is hosted on serverless Azure Container Apps.
- **No GPU Clusters**: CPU inference is used for embeddings.
- **No Premium Tier Storage**: Storage account is `Standard_LRS`, file share is capped at 5 GB quota.
- **Scale-to-Zero Ingress**: API scales to 0 instances when idle (`minReplicas: 0`).
- **Scale-to-Zero Workers**: Worker runs as an on-demand Container Apps Job triggered only when queue depth > 0.
- **No Managed SQL DB**: SQLite runs on the mounted persistent volume.
- **No Application Gateways / Public IPs**: Traffic uses standard Azure Container Apps managed ingress.

---

## 5. Next Steps

Infrastructure provisioning is complete. The next phase will:
1. Build `Dockerfile.api` and `Dockerfile.worker` via Docker (`docker build` / `docker push`).
2. Deploy the `aria-api` Container App referencing `ariacr3ab8.azurecr.io/aria-api:latest`.
3. Deploy the `aria-worker-job` Container Apps Job referencing `ariacr3ab8.azurecr.io/aria-worker:latest`.
4. Validate live health probes (`/health`, `/ready`) on the deployed endpoint.

---

## 6. Checkpoint Decision

```
==============================================================================
                            PROVISIONING STATUS
==============================================================================
                            INFRASTRUCTURE_READY
==============================================================================
The minimal serverless Azure infrastructure has been provisioned and validated.
No application containers were deployed during this phase.
==============================================================================
```
