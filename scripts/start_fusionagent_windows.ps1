param(
    [int]$Port = 8000,
    [string]$LogDir = "logs"
)

$ErrorActionPreference = "Stop"
$RepoRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
$LogPath = Join-Path $RepoRoot $LogDir
New-Item -ItemType Directory -Force -Path $LogPath | Out-Null

& $Python (Join-Path $RepoRoot "scripts\windows_runtime_doctor.py") `
    --output-json (Join-Path $RepoRoot "docs\superpowers\specs\2026-06-10-windows-runtime-doctor.json")

& $Python (Join-Path $RepoRoot "scripts\start_local.py") `
    --port $Port `
    *> (Join-Path $LogPath "fusionagent-local.log")
