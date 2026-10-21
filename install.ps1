# One-command installer for OfflineScholar on Windows 10/11.
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$InstallDir = if ($env:OS_INSTALL_DIR) { $env:OS_INSTALL_DIR } else { Join-Path $HOME "OfflineScholar" }
$ChatModel = if ($env:OS_CHAT_MODEL) { $env:OS_CHAT_MODEL } else { "gemma3:1b" }
$EmbedModel = if ($env:OS_EMBED_MODEL) { $env:OS_EMBED_MODEL } else { "snowflake-arctic-embed:33m" }
$Port = if ($env:OS_PORT) { $env:OS_PORT } else { "7860" }
$SkipDeps = $env:OS_SKIP_DEPS -eq "1"
$SkipModels = $env:OS_SKIP_MODELS -eq "1"
$NoStart = $env:OS_NO_START -eq "1"
$Url = "http://127.0.0.1:$Port"
$ArchiveUrl = "https://github.com/hafeezmt/OfflineScholar-chat/archive/refs/heads/main.zip"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message"
}

function Stop-Install([string]$Message) {
    Write-Host "Error: $Message" -ForegroundColor Red
    exit 1
}

function Refresh-Path {
    $machine = [Environment]::GetEnvironmentVariable("Path", "Machine")
    $user = [Environment]::GetEnvironmentVariable("Path", "User")
    $env:Path = "$machine;$user"
}

function Install-WingetPackage([string]$Id) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Stop-Install "winget is required. Install App Installer from the Microsoft Store and try again."
    }
    Write-Step "Installing $Id"
    & winget install --id $Id --exact --silent --accept-source-agreements --accept-package-agreements
    Refresh-Path
}

function Test-Url([string]$Address) {
    try {
        Invoke-WebRequest -Uri $Address -UseBasicParsing -TimeoutSec 3 | Out-Null
        return $true
    } catch {
        return $false
    }
}

function Find-Python {
    $py = Get-Command py -ErrorAction SilentlyContinue
    if ($py) {
        return @{ Exe = $py.Source; Args = @("-3") }
    }
    $python = Get-Command python -ErrorAction SilentlyContinue
    if ($python) {
        return @{ Exe = $python.Source; Args = @() }
    }
    $known = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $known) {
        return @{ Exe = $known; Args = @() }
    }
    return $null
}

Write-Step "Installing OfflineScholar in $InstallDir"
New-Item -ItemType Directory -Path $InstallDir -Force | Out-Null

$python = Find-Python
if (-not $python) {
    if ($SkipDeps) {
        Stop-Install "Python 3.10 or newer is required."
    }
    Install-WingetPackage "Python.Python.3.12"
    $python = Find-Python
}
if (-not $python) {
    Stop-Install "Python was installed but is not on PATH. Open a new PowerShell window and try again."
}
$pythonExe = $python.Exe
$pythonArgs = @($python.Args)
& $pythonExe @pythonArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3,10) else 1)"
if ($LASTEXITCODE -ne 0) {
    Stop-Install "Python 3.10 or newer is required."
}

$ollama = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollama) {
    $ollamaExe = $ollama.Source
} else {
    $knownOllama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
    if (Test-Path $knownOllama) {
        $ollamaExe = $knownOllama
    } elseif ($SkipDeps) {
        Stop-Install "Ollama is required. Install it from https://ollama.com/download."
    } else {
        Install-WingetPackage "Ollama.Ollama"
        $ollama = Get-Command ollama -ErrorAction SilentlyContinue
        if ($ollama) {
            $ollamaExe = $ollama.Source
        } elseif (Test-Path $knownOllama) {
            $ollamaExe = $knownOllama
        } else {
            Stop-Install "Ollama was installed but is not on PATH. Open a new PowerShell window and try again."
        }
    }
}

Write-Step "Downloading OfflineScholar"
$temp = Join-Path $env:TEMP ("offlinescholar-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $temp -Force | Out-Null
$zip = Join-Path $temp "source.zip"
try {
    Invoke-WebRequest -Uri $ArchiveUrl -OutFile $zip -UseBasicParsing
    Expand-Archive -Path $zip -DestinationPath $temp -Force
    $source = Get-ChildItem $temp -Directory | Where-Object { $_.Name -like "OfflineScholar-chat-*" } | Select-Object -First 1
    if (-not $source) {
        Stop-Install "The downloaded archive did not contain the app."
    }
    Copy-Item -Path (Join-Path $source.FullName "*") -Destination $InstallDir -Recurse -Force
} finally {
    Remove-Item $temp -Recurse -Force -ErrorAction SilentlyContinue
}

if ($SkipModels) {
    Write-Step "Skipping model downloads because OS_SKIP_MODELS=1"
} else {
    if (-not (Test-Url "http://127.0.0.1:11434/api/tags")) {
        Write-Step "Starting Ollama"
        Start-Process -FilePath $ollamaExe -ArgumentList "serve" -WindowStyle Hidden
        for ($i = 0; $i -lt 30; $i++) {
            Start-Sleep -Seconds 1
            if (Test-Url "http://127.0.0.1:11434/api/tags") {
                break
            }
        }
    }
    if (-not (Test-Url "http://127.0.0.1:11434/api/tags")) {
        Stop-Install "Ollama did not start. Open it from the Start menu and run this installer again."
    }
    Write-Step "Downloading the chat model ($ChatModel)"
    & $ollamaExe pull $ChatModel
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Could not download the chat model."
    }
    Write-Step "Downloading the notes model ($EmbedModel)"
    & $ollamaExe pull $EmbedModel
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Could not download the notes model."
    }
}

Write-Step "Setting up the Python environment"
$venvPython = Join-Path $InstallDir "venv\Scripts\python.exe"
if (-not (Test-Path $venvPython)) {
    & $pythonExe @pythonArgs -m venv (Join-Path $InstallDir "venv")
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Could not create the Python environment."
    }
}
& $venvPython -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) {
    Stop-Install "Could not update pip."
}
& $venvPython -m pip install -r (Join-Path $InstallDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Stop-Install "Could not install the Python packages."
}

$startBat = @'
@echo off
cd /d "%~dp0"
set "OS_LOW_MEMORY=1"
set "OS_MODEL=__MODEL__"
set "OS_PORT=__PORT__"
"%~dp0venv\Scripts\python.exe" "%~dp0app.py"
'@
$startBat = $startBat.Replace("__MODEL__", $ChatModel).Replace("__PORT__", $Port)
Set-Content -Path (Join-Path $InstallDir "start.bat") -Value $startBat -Encoding ASCII

$stopBat = @'
@echo off
for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":__PORT__ " ^| findstr LISTENING') do taskkill /F /PID %%a >nul 2>&1
'@
$stopBat = $stopBat.Replace("__PORT__", $Port)
Set-Content -Path (Join-Path $InstallDir "stop.bat") -Value $stopBat -Encoding ASCII

if ($NoStart) {
    Write-Step "Skipping app startup because OS_NO_START=1"
} else {
    if (Test-Url "$Url/api/status") {
        Write-Step "OfflineScholar is already running"
    } else {
        Write-Step "Starting OfflineScholar"
        $env:OS_LOW_MEMORY = "1"
        $env:OS_MODEL = $ChatModel
        $env:OS_PORT = $Port
        Start-Process -FilePath $venvPython -ArgumentList "app.py" `
            -WorkingDirectory $InstallDir -WindowStyle Hidden `
            -RedirectStandardOutput (Join-Path $InstallDir "server.log") `
            -RedirectStandardError (Join-Path $InstallDir "server.err")
        for ($i = 0; $i -lt 60; $i++) {
            Start-Sleep -Seconds 1
            if (Test-Url "$Url/api/status") {
                break
            }
        }
    }
    if (-not (Test-Url "$Url/api/status")) {
        $errorLog = Join-Path $InstallDir "server.err"
        if (Test-Path $errorLog) {
            Get-Content $errorLog -Tail 20
        }
        Stop-Install "The app did not start. Open start.bat to see the error."
    }
    Start-Process $Url
    Write-Step "OfflineScholar is ready"
    Write-Host "Open: $Url"
}

Write-Host ""
Write-Host "Installed in: $InstallDir"
Write-Host "Start again later: $(Join-Path $InstallDir 'start.bat')"
Write-Host "Stop the app: $(Join-Path $InstallDir 'stop.bat')"
