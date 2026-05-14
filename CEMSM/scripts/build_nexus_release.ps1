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

$PortableDir = Join-Path $AppRoot "dist\Conan Exiles Enhanced Manager"
$Exe = Join-Path $PortableDir "Conan Exiles Enhanced Manager.exe"
if (-not (Test-Path $Exe)) {
    throw "Build finished but portable executable was not found: $Exe"
}

$ReleaseDir = New-Item -ItemType Directory -Path (Join-Path $AppRoot "release") -Force
$Version = python -c "from conan_manager import __version__; print(__version__)"
$Zip = Join-Path $ReleaseDir.FullName "ConanExilesEnhancedManager-v$Version-Nexus-Portable.zip"
$Checksum = "$Zip.sha256.txt"

if (Test-Path $Zip) {
    Remove-Item -LiteralPath $Zip -Force
}
if (Test-Path $Checksum) {
    Remove-Item -LiteralPath $Checksum -Force
}

Compress-Archive -LiteralPath $PortableDir -DestinationPath $Zip -CompressionLevel Optimal
$Hash = Get-FileHash -LiteralPath $Zip -Algorithm SHA256
"$($Hash.Hash)  $(Split-Path $Zip -Leaf)" | Set-Content -LiteralPath $Checksum -Encoding ASCII

Write-Host "Built Nexus release:"
Write-Host $Zip
Write-Host $Checksum
