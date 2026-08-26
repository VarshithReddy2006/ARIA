# ==============================================================================
# deploy-api.ps1 — Build and Deploy ARIA API to Azure Container Apps
# ==============================================================================

param(
    [string]$ResourceGroup = "aria-rg",
    [string]$ContainerRegistry = "ariacr3ab8",
    [string]$EnvironmentName = "aria-env",
    [string]$AppName = "aria-api",
    [Parameter(Mandatory = $true)]
    [string]$ImageTag
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================" -ForegroundColor Cyan
Write-Host "Deploying ARIA API Container App ($ImageTag)" -ForegroundColor Cyan
Write-Host "==========================================================" -ForegroundColor Cyan

# 1. Build and Push API Image using Docker (ACR Tasks not supported on Basic registry)
$ImageName = "$ContainerRegistry.azurecr.io/aria-api:$ImageTag"
Write-Host "Building image $ImageName locally via Docker..."
docker build -t $ImageName -f Dockerfile.api .

Write-Host "Authenticating with Azure Container Registry '$ContainerRegistry'..."
az acr login --name $ContainerRegistry

Write-Host "Pushing image $ImageName to ACR..."
docker push $ImageName

# 2. Deploy or Update Container App
Write-Host "Updating Container App '$AppName' with image $ImageName..."
az containerapp update `
    --name $AppName `
    --resource-group $ResourceGroup `
    --image $ImageName

Write-Host "ARIA API deployed successfully!" -ForegroundColor Green
