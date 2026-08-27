# ==============================================================================
# deploy-worker-phase2.ps1 — Deploy ARIA Worker to Azure Container Apps Job
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
$DeepSeekKey = if ($env:DEEPSEEK_API_KEY) { $env:DEEPSEEK_API_KEY } elseif ($hasEnv) { (Get-Content .env | Where-Object { $_ -match "^DEEPSEEK_API_KEY=(.+)$" } | ForEach-Object { $Matches[1] }).Trim() } else { "" }
$GitHubToken = if ($env:GITHUB_TOKEN) { $env:GITHUB_TOKEN } elseif ($hasEnv) { (Get-Content .env | Where-Object { $_ -match "^GITHUB_TOKEN=(.+)$" } | ForEach-Object { $Matches[1] }).Trim() } else { "" }
$QdrantUrl = if ($env:QDRANT_URL) { $env:QDRANT_URL } elseif ($hasEnv) { (Get-Content .env | Where-Object { $_ -match "^QDRANT_URL=(.+)$" } | ForEach-Object { $Matches[1] }).Trim() } else { "" }
$QdrantApiKey = if ($env:QDRANT_API_KEY) { $env:QDRANT_API_KEY } elseif ($hasEnv) { (Get-Content .env | Where-Object { $_ -match "^QDRANT_API_KEY=(.+)$" } | ForEach-Object { $Matches[1] }).Trim() } else { "" }

if (-not $ApiKey -and $hasEnv) {
    $ApiKey = (Get-Content .env | Where-Object { $_ -match "^API_KEY=(.+)$" } | ForEach-Object { $Matches[1] }).Trim()
}
if (-not $ApiKey) {
    throw "ApiKey is required. Pass -ApiKey <key> or set API_KEY environment variable."
}

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
      parallelism: 1
      replicaCompletionCount: 1
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
      - name: deepseek-key
        value: "$DeepSeekKey"
      - name: github-token
        value: "$GitHubToken"
      - name: qdrant-key
        value: "$QdrantApiKey"
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
          - name: JOB_EXECUTOR
            value: azure
          - name: AZURE_STORAGE_QUEUE_NAME
            value: aria-analysis-jobs
          - name: AZURE_STORAGE_CONNECTION_STRING
            secretRef: storage-conn
          - name: GEMINI_API_KEY
            secretRef: gemini-key
          - name: DEEPSEEK_API_KEY
            secretRef: deepseek-key
          - name: GITHUB_TOKEN
            secretRef: github-token
          - name: API_KEY
            secretRef: api-key
          - name: QDRANT_URL
            value: "$QdrantUrl"
          - name: QDRANT_API_KEY
            secretRef: qdrant-key
          - name: VECTOR_STORE_BACKEND
            value: qdrant
          - name: ALLOWED_HOSTS
            value: '["localhost","127.0.0.1"]'
          - name: SQLITE_DB_PATH
            value: /app/data/repo_understanding.db
          - name: ANALYSIS_STORE_PATH
            value: /app/data/analysis_store.json
          - name: JOB_STATE_DIR
            value: /app/data/jobs
          - name: CHROMA_DB_PATH
            value: /tmp/chroma_db
          - name: APP_ENV
            value: production
          - name: LOG_FORMAT
            value: json
        volumeMounts:
          - volumeName: aria-data-volume
            mountPath: /app/data
"@

$WorkerTemp = Join-Path $env:TEMP "aria-worker-job-p2.yaml"
$WorkerYaml | Set-Content -Path $WorkerTemp -Encoding utf8

Write-Host "Applying Container App Job configuration to aria-worker-job ($ImageTag)..." -ForegroundColor Cyan
az containerapp job update --name aria-worker-job --resource-group $ResourceGroup --yaml $WorkerTemp

Remove-Item -Path $WorkerTemp -Force -ErrorAction SilentlyContinue
Write-Host "ARIA Worker Job Phase 2 deployment applied successfully!" -ForegroundColor Green
