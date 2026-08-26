# ==============================================================================
# test-staging-e2e.ps1 — End-to-End Staging Analysis Verification Harness
# ==============================================================================

param(
    [Parameter(Mandatory = $true)]
    [string]$StagingFqdn,
    [string]$ApiKey = $env:API_KEY,
    [string]$RepoUrl = "https://github.com/octocat/Hello-World",
    [string]$Branch = "master",
    [int]$TimeoutSeconds = 180,
    [int]$PollIntervalSeconds = 3
)

$ErrorActionPreference = "Stop"

if (-not $ApiKey -and (Test-Path .env)) {
    $ApiKey = (Get-Content .env | Where-Object { $_ -match "^API_KEY=(.+)$" } | ForEach-Object { $Matches[1] }).Trim()
}
if (-not $ApiKey) {
    throw "ApiKey is required. Pass -ApiKey <key> or set API_KEY environment variable."
}

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "ARIA Staging End-to-End Analysis Verification" -ForegroundColor Cyan
Write-Host "Target FQDN: https://$StagingFqdn" -ForegroundColor Cyan
Write-Host "Repo URL:    $RepoUrl ($Branch)" -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Health Probe Verification
Write-Host "`n[Step 1/5] Checking /health probe..." -ForegroundColor Yellow
$healthUrl = "https://$StagingFqdn/health"
$healthRes = Invoke-WebRequest -Uri $healthUrl -Method Get -UseBasicParsing
if ($healthRes.StatusCode -ne 200) {
    throw "GET /health failed with status code $($healthRes.StatusCode)"
}
Write-Host "Health check passed (HTTP 200)" -ForegroundColor Green

# 2. Readiness Probe Verification
Write-Host "`n[Step 2/5] Checking /ready probe..." -ForegroundColor Yellow
$readyUrl = "https://$StagingFqdn/ready"
$readyRes = Invoke-WebRequest -Uri $readyUrl -Method Get -UseBasicParsing
if ($readyRes.StatusCode -ne 200) {
    throw "GET /ready failed with status code $($readyRes.StatusCode)"
}
Write-Host "Readiness check passed (HTTP 200)" -ForegroundColor Green

# 3. Trigger Async Analysis Job
Write-Host "`n[Step 3/5] Triggering POST /api/v1/analyze..." -ForegroundColor Yellow
$analyzeUrl = "https://$StagingFqdn/api/v1/analyze"
$headers = @{
    "X-API-Key" = $ApiKey
    "Content-Type" = "application/json"
}
$bodyObj = @{
    url = $RepoUrl
    branch = $Branch
    force_rebuild = $true
}
$bodyJson = $bodyObj | ConvertTo-Json

$analyzeRes = Invoke-RestMethod -Uri $analyzeUrl -Method Post -Headers $headers -Body $bodyJson
Write-Host "Dispatch response (HTTP 202):" -ForegroundColor Green
$analyzeRes | ConvertTo-Json -Depth 5 | Write-Host

$jobId = $analyzeRes.job_id
if (-not $jobId) {
    throw "No job_id returned in analyze response!"
}
Write-Host "Captured Job ID: $jobId" -ForegroundColor Cyan

# 4. Poll Job State Lifecycle (queued -> running -> completed)
Write-Host "`n[Step 4/5] Polling job state at /api/v1/analyze/$jobId..." -ForegroundColor Yellow
$statusUrl = "https://$StagingFqdn/api/v1/analyze/$jobId"
$startTime = Get-Date
$seenRunning = $false
$finalState = $null

while (((Get-Date) - $startTime).TotalSeconds -lt $TimeoutSeconds) {
    $pollRes = Invoke-RestMethod -Uri $statusUrl -Method Get -Headers $headers
    $currentStatus = [string]$pollRes.status
    $currentProgress = [string]$pollRes.progress
    $currentStep = [string]$pollRes.step_id
    $currentMessage = [string]$pollRes.message
    $elapsed = [int]((Get-Date) - $startTime).TotalSeconds

    $logLine = "  [" + $elapsed + "s] Status: " + $currentStatus + " | Step: " + $currentStep + " | Progress: " + $currentProgress + "% | " + $currentMessage
    Write-Host $logLine

    if ($currentStatus -eq "running") {
        $seenRunning = $true
    }

    if ($currentStatus -eq "completed") {
        $finalState = $pollRes
        break
    }

    if ($currentStatus -eq "failed") {
        Write-Host "`nJob failed with error details:" -ForegroundColor Red
        $pollRes | ConvertTo-Json -Depth 5 | Write-Host
        throw "Job $jobId transitioned to failed state"
    }

    Start-Sleep -Seconds $PollIntervalSeconds
}

if (-not $finalState) {
    throw "Timed out waiting for job $jobId to complete within $TimeoutSeconds seconds."
}

# 5. Final Report & Verification
Write-Host "`n[Step 5/5] Analysis Successfully Completed!" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "Job ID:          $($finalState.job_id)" -ForegroundColor Green
Write-Host "Status:          $($finalState.status)" -ForegroundColor Green
Write-Host "Elapsed Seconds: $($finalState.elapsed_seconds)s" -ForegroundColor Green
Write-Host "Seen Running:    $seenRunning" -ForegroundColor Green
Write-Host "Result Summary:  $($finalState.result.summary)" -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green
