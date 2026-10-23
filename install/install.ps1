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

$ModelOptions = @(
    [pscustomobject]@{ Name = "gemma3:1b"; Label = "Gemma 3 1B"; SizeMB = 806; Note = "recommended for 8 GB laptops" },
    [pscustomobject]@{ Name = "qwen2.5:1.5b"; Label = "Qwen 2.5 1.5B"; SizeMB = 986; Note = "better reasoning, still light" },
    [pscustomobject]@{ Name = "gemma4:e2b-it-qat"; Label = "Gemma 4 E2B QAT"; SizeMB = 4403; Note = "best answers, needs more free RAM" }
)
$EmbedSizeMB = 67
$DiskMarginMB = 1024
$ChatModels = @($ChatModel)

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

function Format-SizeMB([double]$MB) {
    if ($MB -ge 1024) {
        return ("{0:N1} GB" -f ($MB / 1024))
    }
    return ("{0} MB" -f [int]$MB)
}

function Get-ModelSizeMB([string]$Name) {
    $option = $ModelOptions | Where-Object { $_.Name -eq $Name } | Select-Object -First 1
    if ($option) {
        return [int]$option.SizeMB
    }
    return 0
}

function Get-FreeDiskMB {
    try {
        $root = [System.IO.Path]::GetPathRoot((Resolve-Path -LiteralPath $InstallDir).Path)
        $drive = New-Object System.IO.DriveInfo($root)
        return [math]::Floor($drive.AvailableFreeSpace / 1MB)
    } catch {
        return 0
    }
}

function Get-RamMB {
    try {
        $computer = Get-CimInstance Win32_ComputerSystem -ErrorAction Stop
        $system = Get-CimInstance Win32_OperatingSystem -ErrorAction Stop
        return @{
            Total = [math]::Round($computer.TotalPhysicalMemory / 1MB)
            Available = [math]::Round(($system.FreePhysicalMemory * 1KB) / 1MB)
        }
    } catch {
        return @{ Total = 0; Available = 0 }
    }
}

function ConvertTo-ModelSelection([string]$Raw) {
    $selection = @()
    $items = @($Raw -split '[,\s]+' | Where-Object { $_ })
    foreach ($item in $items) {
        if ((Get-ModelSizeMB $item) -eq 0) {
            Write-Host "Warning: no download-size estimate for $item; disk check is approximate."
        }
        if ($selection -notcontains $item) {
            $selection += $item
        }
    }
    if ($selection.Count -eq 0) {
        Stop-Install "OS_MODELS or OS_CHAT_MODEL did not contain a model name."
    }
    return $selection
}

function Select-ChatModels {
    if ($env:OS_MODELS) {
        Write-Step "Using the chat model selection from OS_MODELS"
        return @(ConvertTo-ModelSelection $env:OS_MODELS)
    }
    if ($env:OS_CHAT_MODEL) {
        Write-Step "Using the chat model from OS_CHAT_MODEL"
        return @(ConvertTo-ModelSelection $env:OS_CHAT_MODEL)
    }
    if ($SkipModels) {
        return @($ChatModel)
    }
    if (-not [Environment]::UserInteractive) {
        Stop-Install "No interactive terminal is available. Set OS_MODELS=`"gemma3:1b`" (or OS_SKIP_MODELS=1) and run again."
    }

    $free = Get-FreeDiskMB
    $ram = Get-RamMB
    Write-Step "Choose the chat model(s) to download"
    Write-Host ""
    if ($free -gt 0) {
        Write-Host ("Disk: {0} free in {1}" -f (Format-SizeMB $free), $InstallDir)
    } else {
        Write-Host "Disk: could not determine free space in $InstallDir"
    }
    if ($ram.Available -gt 0) {
        Write-Host ("RAM: {0} total, {1} available" -f (Format-SizeMB $ram.Total), (Format-SizeMB $ram.Available))
    } else {
        Write-Host ("RAM: {0} total" -f (Format-SizeMB $ram.Total))
    }
    Write-Host ""
    Write-Host "Available chat models (select one or more):"
    for ($i = 0; $i -lt $ModelOptions.Count; $i++) {
        $option = $ModelOptions[$i]
        Write-Host ("  {0}) {1,-18} {2,8}  {3}" -f ($i + 1), $option.Label,
            (Format-SizeMB $option.SizeMB), $option.Note)
    }
    Write-Host ""
    Write-Host ("The notes search model ({0}) will also be installed." -f (Format-SizeMB $EmbedSizeMB))

    while ($true) {
        $answer = Read-Host "Select model numbers separated by spaces, or q to cancel [1]"
        if ([string]::IsNullOrWhiteSpace($answer)) {
            $answer = "1"
        }
        if ($answer -match '^[qQ]$') {
            Stop-Install "Installation cancelled. No models were downloaded."
        }
        $picked = @()
        $invalid = $false
        $tokens = @($answer -split '[,\s]+' | Where-Object { $_ })
        foreach ($token in $tokens) {
            $number = 0
            if (-not [int]::TryParse($token, [ref]$number) -or
                $number -lt 1 -or $number -gt $ModelOptions.Count) {
                $invalid = $true
                break
            }
            $name = $ModelOptions[$number - 1].Name
            if ($picked -notcontains $name) {
                $picked += $name
            }
        }
        if ((-not $invalid) -and $picked.Count -gt 0) {
            Write-Host ("Selected: {0}" -f ($picked -join ", "))
            return $picked
        }
        Write-Host ("Enter numbers from 1 to {0}." -f $ModelOptions.Count)
    }
}

function Confirm-ModelRequirements([string[]]$Models) {
    $downloadMB = 0
    $gemma4 = $false
    $warned = $false
    foreach ($model in $Models) {
        $size = Get-ModelSizeMB $model
        if ($size -eq 0) {
            Write-Host "Warning: no download-size estimate for $model; disk check is approximate."
        }
        $downloadMB += $size
        if ($model -eq "gemma4:e2b-it-qat") {
            $gemma4 = $true
        }
    }
    $downloadMB += $EmbedSizeMB
    $requiredMB = $downloadMB + $DiskMarginMB
    $freeMB = Get-FreeDiskMB
    $ram = Get-RamMB

    Write-Host ""
    Write-Host ("Download size: {0} for the selected models plus notes search" -f (Format-SizeMB $downloadMB))
    Write-Host ("Disk needed: {0} including a {1} safety margin" -f (Format-SizeMB $requiredMB), (Format-SizeMB $DiskMarginMB))
    if ($freeMB -gt 0) {
        Write-Host ("Disk available: {0}" -f (Format-SizeMB $freeMB))
        if ($freeMB -lt $requiredMB) {
            Write-Host ("Warning: not enough free disk space; you are short by {0}." -f
                (Format-SizeMB ($requiredMB - $freeMB))) -ForegroundColor Yellow
            $warned = $true
        }
    } else {
        Write-Host "Warning: could not determine free disk space; check it manually." -ForegroundColor Yellow
        $warned = $true
    }

    if ($gemma4) {
        if ($ram.Available -gt 0 -and $ram.Available -lt 5120) {
            Write-Host ("Warning: Gemma 4 needs about 5 GB of free RAM; only {0} is available." -f
                (Format-SizeMB $ram.Available)) -ForegroundColor Yellow
            $warned = $true
        }
        if ($ram.Total -gt 0 -and $ram.Total -lt 8192) {
            Write-Host ("Warning: this computer has {0} RAM; Gemma 4 is happiest with 8 GB or more." -f
                (Format-SizeMB $ram.Total)) -ForegroundColor Yellow
            $warned = $true
        }
    }

    if ($warned) {
        if ([Environment]::UserInteractive) {
            $answer = Read-Host "Continue with the download anyway? [y/N]"
            if ($answer -notmatch '^[yY]') {
                Stop-Install "Installation cancelled. No models were downloaded."
            }
        } else {
            Write-Host "Continuing because the model selection was provided non-interactively."
        }
    }
}

function Install-Models([string[]]$Models) {
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
    foreach ($model in $Models) {
        Write-Step "Downloading chat model ($model)"
        & $ollamaExe pull $model
        if ($LASTEXITCODE -ne 0) {
            Stop-Install "Could not download the chat model $model."
        }
    }
    Write-Step "Downloading the notes model ($EmbedModel)"
    & $ollamaExe pull $EmbedModel
    if ($LASTEXITCODE -ne 0) {
        Stop-Install "Could not download the notes model."
    }
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

$ChatModels = @(Select-ChatModels)
$ChatModel = $ChatModels[0]
if ($SkipModels) {
    Write-Step "Skipping model downloads because OS_SKIP_MODELS=1"
} else {
    Confirm-ModelRequirements $ChatModels
    Install-Models $ChatModels
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
    chat_models = @($ChatModels)
    embed_model = $EmbedModel
    port = [int]$Port
} | ConvertTo-Json
Set-Content -Path (Join-Path $InstallDir "settings.json") -Value $settings -Encoding ASCII

$cli = @'
@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -m offlinescholar.manage %*
'@
Set-Content -Path (Join-Path $InstallDir "offlinescholar.cmd") -Value $cli -Encoding ASCII
Set-Content -Path (Join-Path $InstallDir "offlinescolar.cmd") -Value $cli -Encoding ASCII

$startBat = @'
@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -m offlinescholar.manage up
'@
Set-Content -Path (Join-Path $InstallDir "start.bat") -Value $startBat -Encoding ASCII

$stopBat = @'
@echo off
cd /d "%~dp0"
"%~dp0venv\Scripts\python.exe" -m offlinescholar.manage stop
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
            $shortcut.Arguments = '-m offlinescholar.desktop'
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

Push-Location $InstallDir
& $venvPython -m offlinescholar.manage stop | Out-Null
Pop-Location

Write-Host ""
Write-Host "Installed in: $InstallDir"
Write-Host "Chat model(s): $($ChatModels -join ', ')"
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
