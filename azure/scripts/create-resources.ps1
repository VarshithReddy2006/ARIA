# ==============================================================================
# create-resources.ps1 — Provision Base Azure Infrastructure for ARIA
#
# NOTE: DO NOT run this script until ready for live cloud deployment.
# All operations create billable resources against your Azure subscription.
# ==============================================================================

param(
    [string]$ResourceGroup = "rg-aria-dev",
    [string]$Location = "eastus",
    [string]$ContainerRegistry = "acrarialocal",
    [string]$StorageAccount = "starialocaldata",
    [string]$EnvironmentName = "cae-aria-dev",
    [string]$QueueName = "aria-analysis-jobs",
    [string]$FileShareName = "aria-data"
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "ARIA Azure Infrastructure Provisioning" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Resource Group     : $ResourceGroup"
Write-Host "Location           : $Location"
Write-Host "Container Registry : $ContainerRegistry"
Write-Host "Storage Account    : $StorageAccount"
Write-Host "Container Apps Env : $EnvironmentName"
Write-Host "Queue Name         : $QueueName"
Write-Host "File Share         : $FileShareName"
Write-Host "----------------------------------------------------------"

# 1. Create Resource Group
Write-Host "Creating Resource Group '$ResourceGroup'..."
az group create --name $ResourceGroup --location $Location

# 2. Create Azure Container Registry (Basic SKU for cost efficiency)
Write-Host "Creating Azure Container Registry '$ContainerRegistry' (Basic SKU)..."
az acr create --resource-group $ResourceGroup --name $ContainerRegistry --sku Basic --admin-enabled true

# 3. Create Storage Account (Standard LRS for low cost)
Write-Host "Creating Storage Account '$StorageAccount' (Standard_LRS)..."
az storage account create `
    --name $StorageAccount `
    --resource-group $ResourceGroup `
    --location $Location `
    --sku Standard_LRS `
    --kind StorageV2

# Get Storage Account Connection String
$ConnStr = az storage account show-connection-string `
    --resource-group $ResourceGroup `
    --name $StorageAccount `
    --query connectionString `
    --output tsv

# 4. Create Queue for Job Dispatch
Write-Host "Creating Storage Queue '$QueueName'..."
az storage queue create `
    --name $QueueName `
    --connection-string $ConnStr

# 5. Create File Share for Persistent Application State
Write-Host "Creating File Share '$FileShareName'..."
az storage share create `
    --name $FileShareName `
    --connection-string $ConnStr

# 6. Create Azure Container Apps Environment
Write-Host "Creating Container Apps Environment '$EnvironmentName'..."
az containerapp env create `
    --name $EnvironmentName `
    --resource-group $ResourceGroup `
    --location $Location

# 7. Mount File Share to Container Apps Environment
$StorageKey = az storage account keys list `
    --resource-group $ResourceGroup `
    --account-name $StorageAccount `
    --query "[0].value" `
    --output tsv

Write-Host "Mounting File Share '$FileShareName' to Container Apps Environment..."
az containerapp env storage set `
    --name $EnvironmentName `
    --resource-group $ResourceGroup `
    --storage-name "ariadata" `
    --azure-file-account-name $StorageAccount `
    --azure-file-account-key $StorageKey `
    --azure-file-share-name $FileShareName `
    --access-mode ReadWrite

Write-Host "Base infrastructure created successfully!" -ForegroundColor Green
Write-Host "Queue connection string and credentials configured securely." -ForegroundColor Green
Write-Host "==========================================================" -ForegroundColor Green
