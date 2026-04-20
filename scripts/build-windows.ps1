# Build the Vortex Wizard Windows bundle.
# Runs on Windows 10+ with Python 3.11+ installed.
#
# Usage (PowerShell, from project root):
#   Set-ExecutionPolicy -Scope Process Bypass
#   .\scripts\build-windows.ps1
#
# Output: dist\vortex-wizard\vortex-wizard.exe
#         + dist\vortex-wizard-windows-YYYYMMDD.zip
#
# Pre-reqs:
#   - Python 3.11+ (winget install Python.Python.3.12)
#   - Rust toolchain (winget install Rustlang.Rustup)
#   - Visual Studio 2022 Build Tools with "Desktop development with C++"
#     (needed for cryptography / maturin compilation)

$ErrorActionPreference = "Stop"

$ProjectRoot = (Get-Item (Join-Path $PSScriptRoot "..")).FullName
Set-Location $ProjectRoot

Write-Host "=== [1/5] Creating venv ===" -ForegroundColor Cyan
if (-not (Test-Path ".venv-win")) {
    py -3 -m venv .venv-win
}
$Venv = Join-Path $ProjectRoot ".venv-win\Scripts"
$env:PATH = "$Venv;$env:PATH"

Write-Host "=== [2/5] Installing deps ===" -ForegroundColor Cyan
& "$Venv\python.exe" -m pip install --upgrade pip
& "$Venv\pip.exe" install pyinstaller maturin
& "$Venv\pip.exe" install -r requirements.txt

Write-Host "=== [3/5] Building vortex_chat (Rust) ===" -ForegroundColor Cyan
if (Test-Path "rust_utils") {
    Push-Location rust_utils
    & "$Venv\maturin.exe" develop --release
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "vortex_chat build failed — continuing with Python fallbacks"
    }
    Pop-Location
}

Write-Host "=== [4/5] PyInstaller bundle ===" -ForegroundColor Cyan
if (Test-Path build)  { Remove-Item -Recurse -Force build }
if (Test-Path dist)   { Remove-Item -Recurse -Force dist }
$env:SOURCE_DATE_EPOCH = "0"
$env:PYTHONHASHSEED    = "0"
& "$Venv\pyinstaller.exe" vortex_wizard\vortex-wizard.spec --clean --noconfirm

$ExePath = "dist\vortex-wizard\vortex-wizard.exe"
if (-not (Test-Path $ExePath)) {
    Write-Error "PyInstaller did not produce $ExePath"
    exit 1
}

Write-Host "=== [5/5] Zipping + SHA256 ===" -ForegroundColor Cyan
$Date    = Get-Date -Format "yyyyMMdd"
$ZipPath = "dist\vortex-wizard-windows-$Date.zip"
Compress-Archive -Path "dist\vortex-wizard\*" -DestinationPath $ZipPath -Force

$Sha = (Get-FileHash $ZipPath -Algorithm SHA256).Hash
"$Sha  $ZipPath" | Out-File -FilePath "dist\SHA256SUMS" -Encoding ascii

Write-Host ""
Write-Host "===== SUCCESS =====" -ForegroundColor Green
Write-Host "Executable:  $ExePath"
Write-Host "Zip:         $ZipPath"
Write-Host "SHA-256:     $Sha"
Write-Host ""
Write-Host "Next (optional): install as Windows service via NSSM:" -ForegroundColor Yellow
Write-Host "  Download NSSM from https://nssm.cc/"
Write-Host "  Fetch the template: curl http://127.0.0.1:9001/api/wiz/admin/super/windows/service.ps1 -o install-svc.ps1"
Write-Host "  .\install-svc.ps1"
