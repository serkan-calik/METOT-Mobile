$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
Write-Host "METOT Mobile v11.4.82 - VS Code APK Build"
$bat = Join-Path $PSScriptRoot "BUILD_APK_VSCODE.bat"
& $bat
exit $LASTEXITCODE
