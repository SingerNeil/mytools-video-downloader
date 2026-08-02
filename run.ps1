$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location -LiteralPath $ProjectDir

function Test-PythonCommand {
    param(
        [Parameter(Mandatory = $true)][string]$Executable,
        [string[]]$PrefixArgs = @()
    )

    try {
        & $Executable @PrefixArgs -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 10) else 1)" *> $null
        return $LASTEXITCODE -eq 0
    }
    catch {
        return $false
    }
}

$VenvPython = Join-Path $ProjectDir ".venv\Scripts\python.exe"
$PythonExecutable = $null
$PythonPrefixArgs = @()

if (-not $env:PYTHON_BIN -and (Test-Path -LiteralPath $VenvPython) -and (Test-PythonCommand -Executable $VenvPython)) {
    $PythonExecutable = $VenvPython
}

if ($env:PYTHON_BIN) {
    if (Test-PythonCommand -Executable $env:PYTHON_BIN) {
        $PythonExecutable = $env:PYTHON_BIN
    }
    else {
        throw "PYTHON_BIN is unavailable or older than Python 3.10: $env:PYTHON_BIN"
    }
}

if (-not $PythonExecutable) {
    $PyLauncher = Get-Command py -ErrorAction SilentlyContinue
    if ($PyLauncher) {
        foreach ($Selector in @("-3.12", "-3")) {
            if (Test-PythonCommand -Executable $PyLauncher.Source -PrefixArgs @($Selector)) {
                $PythonExecutable = $PyLauncher.Source
                $PythonPrefixArgs = @($Selector)
                break
            }
        }
    }
}

if (-not $PythonExecutable) {
    foreach ($Name in @("python3.12", "python3", "python")) {
        $Command = Get-Command $Name -ErrorAction SilentlyContinue
        if ($Command -and (Test-PythonCommand -Executable $Command.Source)) {
            $PythonExecutable = $Command.Source
            break
        }
    }
}

if (-not $PythonExecutable) {
    throw "Python 3.10 or newer was not found. Install it with: winget install --id Python.Python.3.12 --exact"
}

if (-not (Test-Path -LiteralPath $VenvPython)) {
    if (Test-Path -LiteralPath (Join-Path $ProjectDir ".venv")) {
        throw "The existing .venv is not a valid Windows virtual environment. Remove it, then run run.bat again."
    }
    Write-Host "Creating the Python virtual environment..."
    & $PythonExecutable @PythonPrefixArgs -m venv (Join-Path $ProjectDir ".venv")
}

Write-Host "Installing/updating Python dependencies..."
& $VenvPython -m pip install --disable-pip-version-check -r (Join-Path $ProjectDir "requirements.txt")

if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue) -or -not (Get-Command ffprobe -ErrorAction SilentlyContinue)) {
    Write-Warning "ffmpeg/ffprobe were not found. Install them with: winget install --id Gyan.FFmpeg --exact"
}
if (-not (Get-Command node -ErrorAction SilentlyContinue)) {
    Write-Warning "Node.js was not found. YouTube downloads recommend Node.js 22+: winget install --id OpenJS.NodeJS.LTS --exact"
}

Write-Host "Starting MyTools Video Downloader at http://127.0.0.1:8765"
Write-Host "Press Ctrl+C to stop the server."
& $VenvPython -m uvicorn app.main:app --host 127.0.0.1 --port 8765
