# ==============================================================================
# deploy-production-mesh.ps1 — Deploy ARIA API and Worker Job with Shared Azure Files
# Note: Deploys the canonical architecture: Container App (API) + Container Apps Job (Worker).
# ==============================================================================

param(
    [string]$ResourceGroup = "aria-rg",
    [string]$EnvironmentName = "aria-env",
    [string]$RegistryName = "ariacr3ab8",
    [Parameter(Mandatory = $true)]
    [string]$ImageTag,
    [string]$ApiKey = $env:API_KEY
)

$ErrorActionPreference = "Stop"

Write-Host "Fetching Azure connection strings and credentials..." -ForegroundColor Cyan
$StorageConn = az storage account show-connection-string --name ariastg3ab8 --resource-group $ResourceGroup --query "connectionString" -o tsv
$AcrPass = az acr credential show --name $RegistryName --query "passwords[0].value" -o tsv

$hasEnv = Test-Path .env
$GeminiKey = if ($env:GEMINI_API_KEY) { $env:GEMINI_API_KEY } elseif ($hasEnv) { (Get-Content .env | Where-Object { $_ -match "^GEMINI_API_KEY=(.+)$" } | ForEach-Object { $Matches[1] }).Trim() } else { "" }

if (-not $ApiKey -and $hasEnv) {
    $ApiKey = (Get-Content .env | Where-Object { $_ -match "^API_KEY=(.+)$" } | ForEach-Object { $Matches[1] }).Trim()
}
if (-not $ApiKey) {
    throw "ApiKey is required. Pass -ApiKey <key> or set API_KEY environment variable."
}

$RevSuffix = "r" + (Get-Date -Format "HHmmss")

$ApiYaml = @"
type: Microsoft.App/containerApps
name: aria-api
location: eastasia
properties:
  managedEnvironmentId: /subscriptions/3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0/resourceGroups/aria-rg/providers/Microsoft.App/managedEnvironments/aria-env
  configuration:
    activeRevisionsMode: Single
    ingress:
      external: true
      targetPort: 8001
      transport: auto
      allowInsecure: false
      corsPolicy:
        allowedOrigins:
          - "https://aria-orpin-five.vercel.app"
          - "https://aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io"
          - "http://localhost:3000"
          - "http://localhost:4321"
        allowedMethods:
          - "GET"
          - "POST"
          - "OPTIONS"
        allowedHeaders:
          - "*"
    secrets:
      - name: storage-conn
        value: "$StorageConn"
      - name: gemini-key
        value: "$GeminiKey"
      - name: api-key
        value: "$ApiKey"
      - name: acr-pass
        value: "$AcrPass"
    registries:
      - server: ariacr3ab8.azurecr.io
        username: ariacr3ab8
        passwordSecretRef: acr-pass
  template:
    revisionSuffix: "$RevSuffix"
    volumes:
      - name: aria-data-volume
        storageType: AzureFile
        storageName: ariadata
    containers:
      - image: ariacr3ab8.azurecr.io/aria-api:$ImageTag
        name: aria-api
        resources:
          cpu: 1.0
          memory: 2.0Gi
        env:
          - name: JOB_EXECUTOR
            value: azure
          - name: AZURE_STORAGE_QUEUE_NAME
            value: aria-analysis-jobs
          - name: AZURE_STORAGE_CONNECTION_STRING
            secretRef: storage-conn
          - name: GEMINI_API_KEY
            secretRef: gemini-key
          - name: API_KEY
            secretRef: api-key
          - name: ALLOWED_HOSTS
            value: "aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io,lemonriver-308dc42a.eastasia.azurecontainerapps.io,localhost,127.0.0.1"
          - name: SQLITE_DB_PATH
            value: /app/data/repo_understanding.db
          - name: ANALYSIS_STORE_PATH
            value: /app/data/analysis_store.json
          - name: JOB_STATE_DIR
            value: /app/data/jobs
          - name: APP_ENV
            value: production
        volumeMounts:
          - volumeName: aria-data-volume
            mountPath: /app/data
    scale:
      minReplicas: 1
      maxReplicas: 2
"@

$WorkerYaml = @"
type: Microsoft.App/jobs
name: aria-worker-job
location: eastasia
properties:
  environmentId: /subscriptions/3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0/resourceGroups/aria-rg/providers/Microsoft.App/managedEnvironments/aria-env
  configuration:
    triggerType: Event
    replicaTimeout: 3600
    replicaRetryLimit: 3
    eventTriggerConfig:
      scale:
        minExecutions: 0
        maxExecutions: 5
        pollingInterval: 15
        rules:
          - name: queue-rule
            type: azure-queue
            metadata:
              queueName: aria-analysis-jobs
              queueLength: 1
            auth:
              - secretRef: storage-conn
                triggerParameter: connection
    secrets:
      - name: storage-conn
        value: "$StorageConn"
      - name: gemini-key
        value: "$GeminiKey"
      - name: api-key
        value: "$ApiKey"
      - name: acr-pass
        value: "$AcrPass"
    registries:
      - server: ariacr3ab8.azurecr.io
        username: ariacr3ab8
        passwordSecretRef: acr-pass
  template:
    volumes:
      - name: aria-data-volume
        storageType: AzureFile
        storageName: ariadata
    containers:
      - image: ariacr3ab8.azurecr.io/aria-worker:$ImageTag
        name: aria-worker
        resources:
          cpu: 2.0
          memory: 4.0Gi
        env:
          - name: AZURE_STORAGE_QUEUE_NAME
            value: aria-analysis-jobs
          - name: AZURE_STORAGE_CONNECTION_STRING
            secretRef: storage-conn
          - name: GEMINI_API_KEY
            secretRef: gemini-key
          - name: API_KEY
            secretRef: api-key
          - name: ALLOWED_HOSTS
            value: "localhost,127.0.0.1"
          - name: SQLITE_DB_PATH
            value: /app/data/repo_understanding.db
          - name: ANALYSIS_STORE_PATH
            value: /app/data/analysis_store.json
          - name: JOB_STATE_DIR
            value: /app/data/jobs
          - name: APP_ENV
            value: production
        volumeMounts:
          - volumeName: aria-data-volume
            mountPath: /app/data
        command:
          - python
          - -m
          - backend.worker
          - --run-once
"@

$ApiTemp = Join-Path $env:TEMP "aria-api-mesh.yaml"
$WorkerTemp = Join-Path $env:TEMP "aria-worker-mesh.yaml"

$ApiYaml | Set-Content -Path $ApiTemp -Encoding utf8
$WorkerYaml | Set-Content -Path $WorkerTemp -Encoding utf8

Write-Host "Updating aria-api with volume mount and revision $RevSuffix..." -ForegroundColor Cyan
az containerapp update --name aria-api --resource-group $ResourceGroup --yaml $ApiTemp -o json | Out-Null

Write-Host "Updating aria-worker-job with volume mount and image $ImageTag..." -ForegroundColor Cyan
az containerapp job update --name aria-worker-job --resource-group $ResourceGroup --yaml $WorkerTemp -o json | Out-Null

Remove-Item -Path $ApiTemp, $WorkerTemp -Force -ErrorAction SilentlyContinue
Write-Host "Production Mesh deployment ($RevSuffix) complete!" -ForegroundColor Green
