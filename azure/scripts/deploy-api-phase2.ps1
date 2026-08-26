# ==============================================================================
# deploy-api-phase2.ps1 — Deploy ARIA API to Azure Container Apps
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

$RevSuffix = "p2-" + (Get-Date -Format "HHmmss")

$ApiYaml = @"
type: Microsoft.App/containerApps
name: aria-api
location: eastasia
properties:
  managedEnvironmentId: /subscriptions/3ab8ccbd-89d3-4eba-b8ac-81544e33c4c0/resourceGroups/aria-rg/providers/Microsoft.App/managedEnvironments/aria-env
  configuration:
    activeRevisionsMode: Multiple
    ingress:
      external: true
      targetPort: 8001
      transport: auto
      allowInsecure: false
      traffic:
        - revisionName: aria-api--0000004
          weight: 100
        - revisionName: "aria-api--$RevSuffix"
          label: staging
          weight: 0
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
          - name: APP_ENV
            value: production
          - name: LOG_FORMAT
            value: json
          - name: PORT
            value: "8001"
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
          - name: SQLITE_DB_PATH
            value: /app/data/repo_understanding.db
          - name: ANALYSIS_STORE_PATH
            value: /app/data/analysis_store.json
          - name: JOB_STATE_DIR
            value: /app/data/jobs
          - name: CHROMA_DB_PATH
            value: /tmp/chroma_db
          - name: VECTOR_STORE_BACKEND
            value: qdrant
          - name: ALLOWED_HOSTS
            value: '["aria-api.lemonriver-308dc42a.eastasia.azurecontainerapps.io","*.lemonriver-308dc42a.eastasia.azurecontainerapps.io","aria-orpin-five.vercel.app","localhost","127.0.0.1"]'
        probes:
          - type: Startup
            httpGet:
              path: /health
              port: 8001
            initialDelaySeconds: 30
            periodSeconds: 10
            timeoutSeconds: 5
            failureThreshold: 18
          - type: Liveness
            httpGet:
              path: /health
              port: 8001
            initialDelaySeconds: 15
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 5
          - type: Readiness
            httpGet:
              path: /ready
              port: 8001
            initialDelaySeconds: 15
            periodSeconds: 30
            timeoutSeconds: 5
            failureThreshold: 5
        volumeMounts:
          - volumeName: aria-data-volume
            mountPath: /app/data
    scale:
      minReplicas: 1
      maxReplicas: 1
"@

$ApiTemp = Join-Path $env:TEMP "aria-api-p2.yaml"
$ApiYaml | Set-Content -Path $ApiTemp -Encoding utf8

Write-Host "Applying Container App configuration to aria-api ($RevSuffix)..." -ForegroundColor Cyan
az containerapp update --name aria-api --resource-group $ResourceGroup --yaml $ApiTemp

Remove-Item -Path $ApiTemp -Force -ErrorAction SilentlyContinue
Write-Host "ARIA API Phase 2 deployment applied successfully!" -ForegroundColor Green
