[CmdletBinding()]
param(
    [int]$BackendPort = 8000,
    [int]$FrontendPort = 8501,
    [int]$WaitForBackendSeconds = 30,
    [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSCommandPath
$VendorPath = Join-Path $RepoRoot ".vendor"
$BackendUrl = "http://127.0.0.1:$BackendPort"
$FrontendUrl = "http://127.0.0.1:$FrontendPort"
$HealthUrl = "$BackendUrl/health"
$PowerShellExe = (Get-Command powershell -ErrorAction Stop).Source

function Quote-Single {
    param([Parameter(Mandatory = $true)][string]$Value)

    return "'" + $Value.Replace("'", "''") + "'"
}

function Test-PythonCandidate {
    param([Parameter(Mandatory = $true)][string]$PythonPath)

    try {
        & $PythonPath -c "import uvicorn, streamlit, requests, chromadb" *> $null
        return $LASTEXITCODE -eq 0
    } catch {
        return $false
    }
}

function Resolve-Python {
    $candidates = New-Object System.Collections.Generic.List[string]
    $venvPython = Join-Path $RepoRoot ".venv\Scripts\python.exe"

    if (Test-Path $venvPython) {
        [void]$candidates.Add($venvPython)
    }

    foreach ($commandName in @("python", "py")) {
        $command = Get-Command $commandName -ErrorAction SilentlyContinue
        if ($command -and -not $candidates.Contains($command.Source)) {
            [void]$candidates.Add($command.Source)
        }
    }

    foreach ($candidate in $candidates) {
        if (Test-PythonCandidate -PythonPath $candidate) {
            return $candidate
        }
    }

    $tried = if ($candidates.Count -gt 0) {
        $candidates -join ", "
    } else {
        "none"
    }

    throw "No usable Python interpreter found. Tried: $tried. Required modules: uvicorn, streamlit, requests, chromadb."
}

function Build-WindowCommand {
    param(
        [Parameter(Mandatory = $true)][string]$PythonPath,
        [Parameter(Mandatory = $true)][string]$ModuleName,
        [Parameter(Mandatory = $true)][string[]]$Arguments,
        [hashtable]$ExtraEnv = @{}
    )

    $lines = @(
        '$ErrorActionPreference = ''Stop'''
        "Set-Location $(Quote-Single $RepoRoot)"
    )

    if (Test-Path $VendorPath) {
        $vendorLiteral = Quote-Single $VendorPath
        $lines += "if ([string]::IsNullOrWhiteSpace(`$env:PYTHONPATH)) { `$env:PYTHONPATH = $vendorLiteral } else { `$env:PYTHONPATH = ${vendorLiteral} + ';' + `$env:PYTHONPATH }"
    }

    foreach ($entry in $ExtraEnv.GetEnumerator() | Sort-Object Key) {
        $lines += "`$env:$($entry.Key) = $(Quote-Single ([string]$entry.Value))"
    }

    $commandParts = @(
        "& $(Quote-Single $PythonPath)"
        "-m"
        (Quote-Single $ModuleName)
    )
    $commandParts += $Arguments | ForEach-Object { Quote-Single $_ }
    $lines += $commandParts -join " "

    return $lines -join "; "
}

function Wait-ForBackend {
    param(
        [Parameter(Mandatory = $true)][string]$Url,
        [Parameter(Mandatory = $true)][int]$TimeoutSeconds
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $response = Invoke-WebRequest -UseBasicParsing $Url -TimeoutSec 3
            if ($response.StatusCode -eq 200) {
                return $true
            }
        } catch {
        }

        Start-Sleep -Milliseconds 500
    } while ((Get-Date) -lt $deadline)

    return $false
}

$PythonPath = Resolve-Python

$backendCommand = Build-WindowCommand `
    -PythonPath $PythonPath `
    -ModuleName "uvicorn" `
    -Arguments @(
        "backend.app.main:app",
        "--host",
        "127.0.0.1",
        "--port",
        "$BackendPort"
    )

$frontendCommand = Build-WindowCommand `
    -PythonPath $PythonPath `
    -ModuleName "streamlit" `
    -Arguments @(
        "run",
        "frontend/app.py",
        "--server.port",
        "$FrontendPort",
        "--browser.gatherUsageStats",
        "false"
    ) `
    -ExtraEnv @{
        "FRONTEND_API_BASE" = $BackendUrl
    }

if ($DryRun) {
    Write-Host "Python: $PythonPath"
    Write-Host "Backend: $BackendUrl"
    Write-Host "Frontend: $FrontendUrl"
    Write-Host ""
    Write-Host "[backend window]"
    Write-Host $backendCommand
    Write-Host ""
    Write-Host "[frontend window]"
    Write-Host $frontendCommand
    exit 0
}

Write-Host "Using Python: $PythonPath"
Write-Host "Starting backend on $BackendUrl ..."

$backendProcess = Start-Process `
    -FilePath $PowerShellExe `
    -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $backendCommand) `
    -WorkingDirectory $RepoRoot `
    -PassThru

$backendHealthy = Wait-ForBackend -Url $HealthUrl -TimeoutSeconds $WaitForBackendSeconds
if ($backendHealthy) {
    Write-Host "Backend is healthy."
} else {
    Write-Warning "Backend did not pass health check within $WaitForBackendSeconds seconds. Frontend will still be started."
}

Write-Host "Starting frontend on $FrontendUrl ..."

$frontendProcess = Start-Process `
    -FilePath $PowerShellExe `
    -ArgumentList @("-NoExit", "-ExecutionPolicy", "Bypass", "-Command", $frontendCommand) `
    -WorkingDirectory $RepoRoot `
    -PassThru

Write-Host ""
Write-Host "Backend PID : $($backendProcess.Id)"
Write-Host "Frontend PID: $($frontendProcess.Id)"
Write-Host "Backend URL : $BackendUrl"
Write-Host "Frontend URL: $FrontendUrl"
