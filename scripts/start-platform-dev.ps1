param(
  [int]$BackendPort = 8000,
  [int]$FrontendPort = 5173,
  [switch]$StartInfra,
  [switch]$StartWorker,
  [switch]$InstallBackendDeps,
  [switch]$InstallFrontendDeps
)

$ErrorActionPreference = "Stop"

function Normalize-ProcessPathEnvironment {
  $pathValue = [Environment]::GetEnvironmentVariable("Path", "Process")
  if ([string]::IsNullOrWhiteSpace($pathValue)) {
    $pathValue = [Environment]::GetEnvironmentVariable("PATH", "Process")
  }

  if (![string]::IsNullOrWhiteSpace($pathValue)) {
    [Environment]::SetEnvironmentVariable("PATH", $null, "Process")
    [Environment]::SetEnvironmentVariable("Path", $null, "Process")
    [Environment]::SetEnvironmentVariable("Path", $pathValue, "Process")
  }
}

Normalize-ProcessPathEnvironment

function Resolve-ProjectRoot {
  $scriptDir = Split-Path -Parent $PSCommandPath
  return Split-Path -Parent $scriptDir
}

function Test-HttpOpen {
  param([string]$Url)

  try {
    $response = Invoke-WebRequest -UseBasicParsing -Uri $Url -TimeoutSec 2
    return $response.StatusCode -ge 200 -and $response.StatusCode -lt 500
  } catch {
    return $false
  }
}

function Resolve-ValidPort {
  param(
    [int]$Port,
    [int]$DefaultPort,
    [string]$Name
  )

  if ($Port -lt 1 -or $Port -gt 65535) {
    Write-Host "[$Name] invalid port $Port; using default port $DefaultPort" -ForegroundColor Yellow
    return $DefaultPort
  }

  return $Port
}

function Test-TcpPortOpen {
  param([int]$Port)

  try {
    $client = New-Object System.Net.Sockets.TcpClient
    $connectTask = $client.ConnectAsync("127.0.0.1", $Port)
    $isReady = $connectTask.Wait(1000)
    $client.Dispose()
    return $isReady
  } catch {
    return $false
  }
}

function Wait-TcpReady {
  param(
    [string]$Name,
    [int]$Port,
    [int]$TimeoutSeconds = 45
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-TcpPortOpen -Port $Port) {
      Write-Host "[$Name] ready on port $Port" -ForegroundColor Green
      return $true
    }
    Start-Sleep -Seconds 1
  }

  Write-Host "[$Name] not ready within ${TimeoutSeconds}s on port $Port" -ForegroundColor Yellow
  return $false
}

function Wait-HttpReady {
  param(
    [string]$Name,
    [string]$Url,
    [int]$TimeoutSeconds = 30
  )

  $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
  while ((Get-Date) -lt $deadline) {
    if (Test-HttpOpen -Url $Url) {
      Write-Host "[$Name] ready: $Url" -ForegroundColor Green
      return $true
    }
    Start-Sleep -Seconds 1
  }

  Write-Host "[$Name] not ready within ${TimeoutSeconds}s: $Url" -ForegroundColor Yellow
  return $false
}

function Get-PythonPath {
  param([string]$Root)

  $candidates = @(
    (Join-Path $Root "venv\Scripts\python.exe"),
    (Join-Path $Root ".venv\Scripts\python.exe"),
    "python"
  )

  foreach ($candidate in $candidates) {
    if ($candidate -eq "python" -or (Test-Path $candidate)) {
      if (Test-PythonRuntime -PythonPath $candidate) {
        return $candidate
      }
      Write-Host "[backend] skipping unusable Python runtime: $candidate" -ForegroundColor Yellow
    }
  }

  throw "No usable Python runtime found. Recreate venv with an accessible Python, then run .\scripts\start-platform-dev.ps1 -InstallBackendDeps"
}

function Test-PythonRuntime {
  param([string]$PythonPath)

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $PythonPath -c "import ctypes, sqlite3" > $null 2> $null
    return $LASTEXITCODE -eq 0
  } catch {
    return $false
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
}

function Show-LogTail {
  param(
    [string]$Name,
    [string]$Path,
    [int]$LineCount = 80
  )

  if (!(Test-Path $Path)) {
    Write-Host "[$Name] log not found: $Path" -ForegroundColor Yellow
    return
  }

  Write-Host ""
  Write-Host "[$Name] last $LineCount log lines: $Path" -ForegroundColor Yellow
  Get-Content -Tail $LineCount $Path
}

function Test-PythonModule {
  param(
    [string]$PythonPath,
    [string]$ModuleName
  )

  $previousErrorActionPreference = $ErrorActionPreference
  $ErrorActionPreference = "Continue"
  try {
    & $PythonPath -c "import $ModuleName" > $null 2> $null
    return $LASTEXITCODE -eq 0
  } catch {
    return $false
  } finally {
    $ErrorActionPreference = $previousErrorActionPreference
  }
}

$Root = Resolve-ProjectRoot
$FrontendRoot = Join-Path $Root "frontend"
$LogRoot = Join-Path $Root ".dev-logs"
$BackendPort = Resolve-ValidPort -Port $BackendPort -DefaultPort 8000 -Name "backend"
$FrontendPort = Resolve-ValidPort -Port $FrontendPort -DefaultPort 5173 -Name "frontend"

if (!(Test-Path $FrontendRoot)) {
  throw "Frontend directory not found: $FrontendRoot"
}

New-Item -ItemType Directory -Force -Path $LogRoot | Out-Null

$BackendOutLog = Join-Path $LogRoot "backend.out.log"
$BackendErrLog = Join-Path $LogRoot "backend.err.log"
$WorkerOutLog = Join-Path $LogRoot "worker.out.log"
$WorkerErrLog = Join-Path $LogRoot "worker.err.log"
$FrontendOutLog = Join-Path $LogRoot "frontend-vite.out.log"
$FrontendErrLog = Join-Path $LogRoot "frontend-vite.err.log"
$PythonPath = Get-PythonPath -Root $Root

Write-Host "Project root: $Root"
Write-Host "Backend: $Root"
Write-Host "Frontend: $FrontendRoot"
Write-Host "Python: $PythonPath"

if ($InstallFrontendDeps -or !(Test-Path (Join-Path $FrontendRoot "node_modules"))) {
  Write-Host "[frontend] installing dependencies..." -ForegroundColor Cyan
  Push-Location $FrontendRoot
  try {
    npm install
  } finally {
    Pop-Location
  }
}

if ($StartInfra) {
  Write-Host "[infra] starting PostgreSQL, Redis and RabbitMQ with Docker Compose..." -ForegroundColor Cyan
  Push-Location $Root
  try {
    docker compose up -d postgres redis rabbitmq
  } finally {
    Pop-Location
  }

  [void](Wait-TcpReady -Name "postgres" -Port 5432 -TimeoutSeconds 45)
  [void](Wait-TcpReady -Name "redis" -Port 6379 -TimeoutSeconds 30)
  [void](Wait-TcpReady -Name "rabbitmq" -Port 5672 -TimeoutSeconds 45)

  $env:DATABASE_URL = "postgresql+psycopg://liangzhi:liangzhi@localhost:5432/liangzhi"
  $env:REDIS_URL = "redis://localhost:6379/0"
  $env:RABBITMQ_URL = "amqp://liangzhi:liangzhi@localhost:5672/"
  $env:WORKFLOW_EXECUTION_MODE = "queued"
}

$BackendRequirements = Join-Path $Root "backend\requirements.txt"
if ($InstallBackendDeps) {
  if (!(Test-Path $BackendRequirements)) {
    throw "Backend requirements not found: $BackendRequirements"
  }

  Write-Host "[backend] installing backend dependencies..." -ForegroundColor Cyan
  & $PythonPath -m pip install -r $BackendRequirements
  if ($LASTEXITCODE -ne 0) {
    throw "Backend dependency installation failed. See pip output above."
  }
}

$requiredModules = @("uvicorn", "pydantic_settings", "pika")
foreach ($moduleName in $requiredModules) {
  if (!(Test-PythonModule -PythonPath $PythonPath -ModuleName $moduleName)) {
    Write-Host "[backend] missing dependency: $moduleName" -ForegroundColor Yellow
    Write-Host "Run this once:" -ForegroundColor Yellow
    Write-Host "  .\scripts\start-platform-dev.ps1 -InstallBackendDeps" -ForegroundColor Yellow
    throw "Backend dependencies are incomplete."
  }
}

$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"

$backendHealthUrl = "http://127.0.0.1:$BackendPort/api/health"
$frontendUrl = "http://127.0.0.1:$FrontendPort"

if (Test-HttpOpen -Url $backendHealthUrl) {
  Write-Host "[backend] already running: $backendHealthUrl" -ForegroundColor Green
} else {
  Write-Host "[backend] starting backend on port $BackendPort..." -ForegroundColor Cyan
  $backendArgs = @("-m", "uvicorn", "backend.main:app", "--host", "127.0.0.1", "--port", "$BackendPort")
  $backendProcess = Start-Process -FilePath $PythonPath -ArgumentList $backendArgs -WorkingDirectory $Root -RedirectStandardOutput $BackendOutLog -RedirectStandardError $BackendErrLog -PassThru -WindowStyle Hidden
  Write-Host "[backend] pid=$($backendProcess.Id)"
}

$shouldStartWorker = $StartWorker -or $StartInfra
if ($shouldStartWorker) {
  Write-Host "[worker] starting queue worker..." -ForegroundColor Cyan
  $workerArgs = @("-m", "backend.workers.run_queue_worker")
  $workerProcess = Start-Process -FilePath $PythonPath -ArgumentList $workerArgs -WorkingDirectory $Root -RedirectStandardOutput $WorkerOutLog -RedirectStandardError $WorkerErrLog -PassThru -WindowStyle Hidden
  Write-Host "[worker] pid=$($workerProcess.Id)"
}

if (Test-HttpOpen -Url $frontendUrl) {
  Write-Host "[frontend] already running: $frontendUrl" -ForegroundColor Green
} else {
  Write-Host "[frontend] starting Vite on port $FrontendPort..." -ForegroundColor Cyan
  $frontendArgs = @("run", "dev", "--", "--host", "127.0.0.1", "--port", "$FrontendPort")
  $frontendProcess = Start-Process -FilePath "npm.cmd" -ArgumentList $frontendArgs -WorkingDirectory $FrontendRoot -RedirectStandardOutput $FrontendOutLog -RedirectStandardError $FrontendErrLog -PassThru -WindowStyle Hidden
  Write-Host "[frontend] pid=$($frontendProcess.Id)"
}

$isBackendReady = Wait-HttpReady -Name "backend" -Url $backendHealthUrl -TimeoutSeconds 30
$isFrontendReady = Wait-HttpReady -Name "frontend" -Url $frontendUrl -TimeoutSeconds 30

if (!$isBackendReady) {
  Show-LogTail -Name "backend stderr" -Path $BackendErrLog
  throw "Backend failed to become ready: $backendHealthUrl"
}

if (!$isFrontendReady) {
  Show-LogTail -Name "frontend stderr" -Path $FrontendErrLog
  throw "Frontend failed to become ready: $frontendUrl"
}

Write-Host ""
Write-Host "Open these URLs:" -ForegroundColor Cyan
Write-Host "  Frontend: $frontendUrl"
Write-Host "  Auth:     $frontendUrl/auth?tab=register"
Write-Host "  Backend:  http://127.0.0.1:$BackendPort/docs"
Write-Host ""
Write-Host "Logs:" -ForegroundColor Cyan
Write-Host "  Backend stdout:  $BackendOutLog"
Write-Host "  Backend stderr:  $BackendErrLog"
Write-Host "  Worker stdout:   $WorkerOutLog"
Write-Host "  Worker stderr:   $WorkerErrLog"
Write-Host "  Frontend stdout: $FrontendOutLog"
Write-Host "  Frontend stderr: $FrontendErrLog"
