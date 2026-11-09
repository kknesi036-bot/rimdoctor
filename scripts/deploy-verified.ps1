param([Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference = 'Stop'
$root = if ($env:RUNNER_TEMP) { $env:RUNNER_TEMP } else { [IO.Path]::GetTempPath() }
$proof = Join-Path $root ('rimdoctor-proof-' + $Version + '-' + [guid]::NewGuid())
if (Test-Path $proof) { throw "Proof directory already exists: $proof" }
New-Item -ItemType Directory -Path $proof | Out-Null
if ($env:GITHUB_ENV) { "RIMDOCTOR_PROOF=$proof" | Out-File $env:GITHUB_ENV -Encoding utf8 -Append }
$python = Join-Path $env:LOCALAPPDATA 'Programs/Python/Python313/python.exe'
if (-not (Test-Path $python)) { $python = (Get-Command python.exe -ErrorAction Stop).Source }
$arguments = @('"' + "$PSScriptRoot/observe.py" + '"', '--url', 'http://127.0.0.1:8000', '--expected', $Version, '--output', '"' + $proof + '"')
$observer = Start-Process -FilePath $python -ArgumentList ($arguments -join ' ') -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $proof 'observer.log') -RedirectStandardError (Join-Path $proof 'observer-error.log')
$deploymentError = $null
try {
    for ($i=0; $i -lt 30 -and -not (Test-Path (Join-Path $proof 'ready.json')); $i++) { Start-Sleep -Seconds 1 }
    if (-not (Test-Path (Join-Path $proof 'ready.json'))) { throw 'Observer did not become ready' }
    & "$PSScriptRoot/deploy.ps1" -Version $Version
    Start-Sleep -Seconds 5
} catch { $deploymentError = $_ }
finally {
    Set-Content (Join-Path $proof 'stop') 'stop'
    if (-not $observer.WaitForExit(100000)) { $observer.Kill(); throw 'Observer did not finish' }
    Get-Content (Join-Path $proof 'observer.log')
    Get-Content (Join-Path $proof 'observer-error.log')
}
if ($deploymentError) { throw $deploymentError }
$summary = Get-Content (Join-Path $proof 'summary.json') -Raw | ConvertFrom-Json
if (-not $summary.passed) { throw "Availability verification failed: $proof" }
if ($env:GITHUB_STEP_SUMMARY) {
    "Deployment verified: $($summary.requests) requests, $($summary.failures) failures; in-flight POST completed. Evidence: availability-proof artifact." | Out-File $env:GITHUB_STEP_SUMMARY -Encoding utf8 -Append
}
Write-Output "Availability proof: $proof"
