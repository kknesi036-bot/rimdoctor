param([Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^[0-9a-f]{40}$') { throw 'Expected a commit SHA' }
$image = "qwer09872234/rimdoctor:$Version"
$name = 'rimdoctor'
$backup = 'rimdoctor-previous'
function Docker {
    & docker.exe @args
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $($args[0])" }
}
function Wait-Ready {
    for ($i=0; $i -lt 30; $i++) {
        try {
            $health = Invoke-RestMethod 'http://127.0.0.1:8000/health' -TimeoutSec 2
            if ($health.status -eq 'ok' -and $health.version -eq $Version) { return }
        } catch {}
        Start-Sleep -Seconds 2
    }
    throw 'New service did not become ready'
}
Docker pull $image
$existing = @(Docker ps -a --format '{{.Names}}')
if ($existing -contains $backup) { throw 'Previous rollback container exists; inspect it before deploying' }
$hadOld = $existing -contains $name
if ($hadOld) {
    Docker stop $name
    Docker rename $name $backup
}
try {
    Docker run -d --name $name --restart unless-stopped -p 127.0.0.1:8000:8000 $image
    Wait-Ready
    $web = New-Object System.Net.WebClient
    try { $sample = [Text.Encoding]::UTF8.GetString($web.DownloadData('http://127.0.0.1:8000/static/sample.log')) } finally { $web.Dispose() }
    $result = Invoke-RestMethod 'http://127.0.0.1:8000/api/analyze' -Method Post -ContentType 'text/plain; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($sample))
    if ($result.summary.error_count -ne 5 -or $result.summary.group_count -ne 4) { throw 'Sample analysis failed' }
    if ((Invoke-WebRequest 'http://127.0.0.1:8000/' -UseBasicParsing).StatusCode -ne 200) { throw 'Home page failed' }
} catch {
    & docker.exe logs $name
    & docker.exe rm -f $name
    if ($hadOld) { Docker rename $backup $name; Docker start $name }
    throw
}
if ($hadOld) { Docker rm $backup }
Write-Output "Deployment verified: $image at http://127.0.0.1:8000"

