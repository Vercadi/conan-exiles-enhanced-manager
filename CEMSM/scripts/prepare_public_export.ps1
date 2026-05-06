param(
    [string]$Destination = ""
)

$ErrorActionPreference = "Stop"

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..\..")
if (-not $Destination) {
    $Destination = Join-Path $RepoRoot ("tmp\public_export_" + (Get-Date -Format "yyyyMMdd_HHmmss"))
}

$DestinationPath = New-Item -ItemType Directory -Path $Destination -Force

$RootFiles = @(".gitignore", "README.md", "CHANGELOG.md", "LICENSE", "PRIVACY_POLICY.md")
foreach ($File in $RootFiles) {
    Copy-Item -LiteralPath (Join-Path $RepoRoot $File) -Destination $DestinationPath.FullName -Force
}

$AppDestination = New-Item -ItemType Directory -Path (Join-Path $DestinationPath.FullName "CEMSM") -Force
$ExcludedNames = @("data", "backups", "logs", "steamcmd", "tmp", "build", "dist", ".pytest_cache", "__pycache__")

Get-ChildItem -LiteralPath (Join-Path $RepoRoot "CEMSM") -Force | Where-Object {
    $ExcludedNames -notcontains $_.Name
} | ForEach-Object {
    Copy-Item -LiteralPath $_.FullName -Destination $AppDestination.FullName -Recurse -Force
}

Get-ChildItem -LiteralPath $DestinationPath.FullName -Recurse -Force -Directory | Where-Object {
    $ExcludedNames -contains $_.Name
} | Remove-Item -Recurse -Force

Get-ChildItem -LiteralPath $DestinationPath.FullName -Recurse -Force -File | Where-Object {
    $_.Extension -in @(".pyc", ".pyo")
} | Remove-Item -Force

Write-Host "Prepared public export:"
Write-Host $DestinationPath.FullName
Write-Host "Implementation docs under docs/ are intentionally excluded."
