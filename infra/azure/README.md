# Azure Container Apps Deployment Guide ($100 Student Credit Budget)

This directory contains the deployment templates and specifications for deploying ARIA to Microsoft Azure Container Apps without altering the core repository analysis engine.

## 1. Directory Structure

- `container-app.yaml`: Web API & Astro static frontend service (Scale: 0 to 3).
- `job.yaml`: Ephemeral background repository analysis worker (Runs only during active analysis ~4 min).
- `parameters.example.json`: Configuration template with environment variables.
- `storage-architecture.md`: Storage access patterns (Azure Files vs Blob Storage vs Local ephemeral).
- `cost-model.md`: Mathematical cost analysis across 10, 50, 100, and 500 analyses/month.

## 2. Quickstart Deployment via Azure CLI

```bash
# 1. Login to Azure
az login

# 2. Set Resource Group and Location
RESOURCE_GROUP="aria-rg"
LOCATION="eastus"
az group create --name $RESOURCE_GROUP --location $LOCATION

# 3. Create Azure Container Apps Environment
az containerapp env create \
  --name aria-env \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION

# 4. Create Standard Storage Account and File Share for /app/data
az storage account create \
  --name ariastorage$RANDOM \
  --resource-group $RESOURCE_GROUP \
  --location $LOCATION \
  --sku Standard_LRS

az storage share create \
  --name ariadata \
  --account-name <storage-account-name>

# 5. Link Storage to ACA Environment
az containerapp env storage set \
  --name aria-env \
  --resource-group $RESOURCE_GROUP \
  --storage-name ariadata \
  --azure-file-account-name <storage-account-name> \
  --azure-file-account-key <storage-account-key> \
  --azure-file-share-name ariadata \
  --access-mode ReadWrite

# 6. Deploy Web Container App
az containerapp create \
  --name aria-web \
  --resource-group $RESOURCE_GROUP \
  --environment aria-env \
  --image repo-intelligence-agent:latest \
  --target-port 8001 \
  --ingress external \
  --min-replicas 0 \
  --max-replicas 3 \
  --cpu 0.5 \
  --memory 1.0Gi
```
