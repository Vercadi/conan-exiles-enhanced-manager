param(
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$AppRoot = Resolve-Path (Join-Path $RepoRoot "CEMSM")

Set-Location $AppRoot

if (-not $SkipTests) {
    python -m compileall conan_manager -q
    python -m pytest -q
}

python -m PyInstaller conan_exiles_enhanced_manager.spec --noconfirm --clean

$Exe = Join-Path $AppRoot "dist\Conan Exiles Enhanced Manager\Conan Exiles Enhanced Manager.exe"
if (-not (Test-Path $Exe)) {
    throw "Build finished but executable was not found: $Exe"
}

Write-Host "Built portable release:"
Write-Host $Exe
