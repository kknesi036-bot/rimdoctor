param([Parameter(Mandatory=$true)][string]$Version)
$ErrorActionPreference = 'Stop'
if ($Version -notmatch '^[0-9a-f]{40}$') { throw 'Expected a commit SHA' }
$image = "qwer09872234/rimdoctor:$Version"
$proxy = 'rimdoctor-proxy'
$network = 'rimdoctor-net'
$nginx = 'nginx@sha256:583b7f2fce1cdb8da5ad5c39ebd3c33b98b87d493190e548bdee1fa8c619c311'
function Docker {
    & docker.exe @args
    if ($LASTEXITCODE -ne 0) { throw "Docker command failed: $($args[0])" }
}
function Wait-Ready {
    for ($i=0; $i -lt 30; $i++) {
        try {
            $response = Invoke-WebRequest 'http://127.0.0.1:8000/health' -UseBasicParsing -TimeoutSec 2
            $health = $response.Content | ConvertFrom-Json
            if ($health.status -eq 'ok' -and $health.version -eq $Version -and $response.Headers['X-RimDoctor-Backend'] -eq $target) { return }
        } catch {}
        Start-Sleep -Seconds 1
    }
    throw 'Public endpoint did not reach requested version'
}
function Wait-Drain {
    for ($i=0; $i -lt 90; $i++) {
        $processes = Docker top $proxy -eo 'pid,args'
        if (-not ($processes -match 'worker process is shutting down')) { return }
        Start-Sleep -Seconds 1
    }
    throw 'Old requests still active: retain both backends and retry later'
}
function Check-Public {
    Docker run --rm --network $network --mount "type=bind,source=$PSScriptRoot/smoke.py,target=/smoke.py,readonly" $image python /smoke.py --url "http://${proxy}" --version $Version
}
Docker pull $image
if (-not (@(Docker network ls --format '{{.Name}}') -contains $network)) { Docker network create $network }
$existing = @(Docker ps -a --format '{{.Names}}')
$bootstrap = -not ($existing -contains $proxy)
$old = $null
if (-not $bootstrap) {
    Wait-Drain
    $config = (Docker exec $proxy cat /etc/rimdoctor/nginx.conf) -join "`n"
    if ($config -notmatch 'server (rimdoctor-(blue|green)):8000;') { throw 'Cannot identify active backend' }
    $old = $Matches[1]
    $target = if ($old -eq 'rimdoctor-blue') { 'rimdoctor-green' } else { 'rimdoctor-blue' }
} else { $target = 'rimdoctor-blue' }
if ($existing -contains $target) { Docker rm -f $target }
Docker run -d --name $target --label rimdoctor.managed=true --network $network --restart unless-stopped $image
try {
    Docker run --rm --network $network --mount "type=bind,source=$PSScriptRoot/smoke.py,target=/smoke.py,readonly" $image python /smoke.py --url "http://${target}:8000" --version $Version
} catch {
    & docker.exe logs $target
    & docker.exe rm -f $target
    throw
}
$configuration = @"
worker_processes 2;
error_log /dev/stderr notice;
pid /var/run/nginx.pid;
events { worker_connections 1024; }
http {
    access_log off;
    client_max_body_size 10m;
    client_body_timeout 120s;
    upstream rimdoctor_backend { server ${target}:8000; }
    server {
        listen 80;
        add_header X-RimDoctor-Backend $target always;
        location / {
            proxy_pass http://rimdoctor_backend;
            proxy_http_version 1.1;
            proxy_set_header Connection "";
            proxy_set_header Host `$host;
            proxy_read_timeout 120s;
            proxy_send_timeout 120s;
        }
    }
}
"@
$temp = Join-Path ([IO.Path]::GetTempPath()) ("rimdoctor-" + [guid]::NewGuid() + '.conf')
[IO.File]::WriteAllText($temp, $configuration, (New-Object Text.UTF8Encoding($false)))
try {
    if ($bootstrap) {
        Docker pull $nginx
        Docker volume create rimdoctor-proxy-config
        Docker create --name $proxy --label rimdoctor.managed=true --network $network --restart unless-stopped -p 127.0.0.1:8000:80 --mount "type=volume,source=rimdoctor-proxy-config,target=/etc/rimdoctor" --entrypoint nginx $nginx -c /etc/rimdoctor/nginx.conf -g 'daemon off;'
        Docker cp $temp "${proxy}:/etc/rimdoctor/nginx.conf"
        $legacy = $existing -contains 'rimdoctor'
        if ($legacy) { Docker stop rimdoctor }
        try { Docker start $proxy; Wait-Ready; Check-Public }
        catch {
            & docker.exe rm -f $proxy
            if ($legacy) { Docker start rimdoctor }
            throw
        }
        Write-Output 'INITIAL PROXY INSTALLATION: not a zero-downtime deployment measurement.'
    } else {
        Docker cp $temp "${proxy}:/etc/rimdoctor/candidate.conf"
        Docker exec $proxy nginx -t -c /etc/rimdoctor/candidate.conf
        Docker exec $proxy cp /etc/rimdoctor/nginx.conf /etc/rimdoctor/previous.conf
        Docker exec $proxy mv /etc/rimdoctor/candidate.conf /etc/rimdoctor/nginx.conf
        try {
            Docker exec $proxy nginx -s reload -c /etc/rimdoctor/nginx.conf
            Wait-Ready
            Check-Public
        } catch {
            Docker exec $proxy cp /etc/rimdoctor/previous.conf /etc/rimdoctor/nginx.conf
            Docker exec $proxy nginx -s reload -c /etc/rimdoctor/nginx.conf
            throw
        }
        Start-Sleep -Seconds 2
        Wait-Drain
        Docker stop --timeout 30 $old
        Docker rm $old
    }
    Write-Output "Verified deployment: $Version via $target at http://127.0.0.1:8000"
} finally { Remove-Item -LiteralPath $temp -ErrorAction SilentlyContinue }



