# ==============================================================================
# deploy-worker.ps1 — Build and Deploy ARIA Worker to Azure Container Apps Job
# ==============================================================================

param(
    [string]$ResourceGroup = "aria-rg",
    [string]$ContainerRegistry = "ariacr3ab8",
    [string]$EnvironmentName = "aria-env",
    [string]$JobName = "aria-worker-job",
    [Parameter(Mandatory = $true)]
    [string]$ImageTag
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Deploying ARIA Worker Container App Job ($ImageTag)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Build and Push Worker Image using Docker (ACR Tasks not supported on Basic registry)
$ImageName = "$ContainerRegistry.azurecr.io/aria-worker:$ImageTag"
Write-Host "Building worker image $ImageName locally via Docker..."
docker build -t $ImageName -f Dockerfile.worker .

Write-Host "Authenticating with Azure Container Registry '$ContainerRegistry'..."
az acr login --name $ContainerRegistry

Write-Host "Pushing worker image $ImageName to ACR..."
docker push $ImageName

# 2. Deploy or Update Container App Job
Write-Host "Updating Container App Job '$JobName' with image $ImageName..."
az containerapp job update `
    --name $JobName `
    --resource-group $ResourceGroup `
    --image $ImageName `
    --cpu "2.0" `
    --memory "4.0Gi"

Write-Host "ARIA Worker Job configured successfully!" -ForegroundColor Green
