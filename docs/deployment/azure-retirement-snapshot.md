# Azure Live Deployment Retirement Snapshot
**Date:** 2026-08-31
**Environment:** Azure for Students (Subscription ID: `3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0`)
**Resource Group:** `aria-rg` (Location: `eastasia`)
**Git SHA:** `4c4fdf2a899a947c244d63cec42b5b4ee6896c20`

---

## 1. Resource Inventory & Active Status

| Resource Name | Resource Type | Provisioning / Power State | Public Traffic / Compute Status |
| :--- | :--- | :--- | :--- |
| **`aria-backend`** | `Microsoft.Compute/virtualMachines` | **VM deallocated** | **OFFLINE** (Zero compute billing) |
| **`aria-backend_OsDisk_1_*`** | `Microsoft.Compute/disks` | Succeeded | Attached to deallocated VM |
| **`aria-backend-ip`** | `Microsoft.Network/publicIPAddresses` | Succeeded | Dynamic Public IP (Unused) |
| **`aria-backend-nsg`** | `Microsoft.Network/networkSecurityGroups` | Succeeded | Inactive |
| **`vnet-eastasia-1`** | `Microsoft.Network/virtualNetworks` | Succeeded | Inactive |
| **`aria-env`** | `Microsoft.App/managedEnvironments` | Succeeded | Idle Container App Environment |
| **`aria-api`** | `Microsoft.App/containerApps` | **Provisioning Failed / Dormant** | **OFFLINE** (`ContainerAppNotFoundInCluster`) |
| **`aria-worker`** | `Microsoft.App/containerApps` | **Provisioning Failed / Dormant** | **OFFLINE** (`ContainerAppNotFoundInCluster`) |
| **`aria-worker-job`** | `Microsoft.App/jobs` | **Provisioning Failed / Dormant** | **OFFLINE** (No active executions) |
| **`ariacr3ab8`** | `Microsoft.ContainerRegistry/registries` | Succeeded (SKU: Basic) | Dormant image registry |
| **`ariastg3ab8`** | `Microsoft.Storage/storageAccounts` | Succeeded (StorageV2 Hot) | Dormant storage account |
| **`workspace-ariargng7x`** | `Microsoft.OperationalInsights/workspaces` | Succeeded | Log Analytics Workspace (Idle) |

---

## 2. Configuration & Reference Metadata

### Container Apps Environment
- **Managed Environment ID**: `/subscriptions/3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0/resourceGroups/aria-rg/providers/Microsoft.App/managedEnvironments/aria-env`
- **Workload Profile**: `Consumption`

### Container Apps (`aria-api`, `aria-worker`)
- **Ingress**: `null` (Disabled / Inactive)
- **Active Revisions**: `None`
- **Containers Running**: `0`

### Container App Job (`aria-worker-job`)
- **Trigger Type**: `Schedule` / `Manual`
- **Active Executions**: `0`

---

## 3. Cost & Safety Assessment
- **Compute Cost**: **$0.00 / month** (All compute instances, VMs, and container replicas are deallocated and dormant).
- **Public Ingress**: **Completely Offline** (No public DNS or container ingress is routing traffic).
- **Code & Repository Safety**: **100% Preserved** locally and on GitHub.
