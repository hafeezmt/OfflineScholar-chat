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
$SkipDesktop = $env:OS_SKIP_DESKTOP -eq "1"
$ArchiveUrl = "https://github.com/hafeezmt/OfflineScholar-chat/archive/refs/heads/main.zip"

function Write-Step([string]$Message) {
    Write-Host ""
    Write-Host "==> $Message"
}

function Stop-Install([string]$Message) {
    Write-Host "Error: $Message" -ForegroundColor Red
    exit 1
}

if ($Port -notmatch '^\d+$') {
    Stop-Install "OS_PORT must be a number."
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
& $venvPython -m pip install --disable-pip-version-check -r (Join-Path $InstallDir "requirements.txt")
if ($LASTEXITCODE -ne 0) {
    Stop-Install "Could not install the Python packages."
}

$settings = @{
    chat_model = $ChatModel
    embed_model = $EmbedModel
    port = [int]$Port
} | ConvertTo-Json
Set-Content -Path (Join-Path $InstallDir "settings.json") -Value $settings -Encoding ASCII

$cli = @'
@echo off
"%~dp0venv\Scripts\python.exe" "%~dp0manage.py" %*
'@
Set-Content -Path (Join-Path $InstallDir "offlinescholar.cmd") -Value $cli -Encoding ASCII
Set-Content -Path (Join-Path $InstallDir "offlinescolar.cmd") -Value $cli -Encoding ASCII

$startBat = @'
@echo off
"%~dp0venv\Scripts\python.exe" "%~dp0manage.py" up
'@
Set-Content -Path (Join-Path $InstallDir "start.bat") -Value $startBat -Encoding ASCII

$stopBat = @'
@echo off
"%~dp0venv\Scripts\python.exe" "%~dp0manage.py" stop
'@
Set-Content -Path (Join-Path $InstallDir "stop.bat") -Value $stopBat -Encoding ASCII

$userPath = [Environment]::GetEnvironmentVariable("Path", "User")
$pathParts = @($userPath -split ";" | Where-Object { $_ })
if ($pathParts -notcontains $InstallDir) {
    [Environment]::SetEnvironmentVariable("Path", (($pathParts + $InstallDir) -join ";"), "User")
}
if (($env:Path -split ";") -notcontains $InstallDir) {
    $env:Path = "$InstallDir;$env:Path"
}

if (-not $SkipDesktop) {
    $pythonw = Join-Path $InstallDir "venv\Scripts\pythonw.exe"
    if (Test-Path $pythonw) {
        function New-AppShortcut([string]$Path) {
            $shell = New-Object -ComObject WScript.Shell
            $shortcut = $shell.CreateShortcut($Path)
            $shortcut.TargetPath = $pythonw
            $shortcut.Arguments = '"' + (Join-Path $InstallDir "desktop.py") + '"'
            $shortcut.WorkingDirectory = $InstallDir
            $shortcut.Description = "OfflineScholar"
            $shortcut.Save()
        }
        try {
            $programs = [Environment]::GetFolderPath("Programs")
            New-AppShortcut (Join-Path $programs "OfflineScholar.lnk")
            $desktop = [Environment]::GetFolderPath("Desktop")
            if ($desktop) {
                New-AppShortcut (Join-Path $desktop "OfflineScholar.lnk")
            }
        } catch {
            Write-Host "Could not create the app shortcut: $($_.Exception.Message)"
        }
    }
}

& $venvPython (Join-Path $InstallDir "manage.py") stop | Out-Null

Write-Host ""
Write-Host "Installed in: $InstallDir"
Write-Host ""
Write-Host "Start OfflineScholar from any terminal:"
Write-Host "  offlinescholar up"
Write-Host ""
Write-Host "Stop it and release RAM:"
Write-Host "  offlinescholar stop"
if (-not $SkipDesktop) {
    Write-Host ""
    Write-Host "Or open OfflineScholar from the Start Menu or Desktop."
}
