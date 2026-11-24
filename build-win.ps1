$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$Version = "6.26.0"
$FileName = "xmrig-$Version-windows-x64.zip"
$Release = "https://github.com/xmrig/xmrig/releases/download/v$Version"

New-Item -ItemType Directory -Force -Path engine | Out-Null
New-Item -ItemType Directory -Force -Path licenses | Out-Null

# Download official XMRig and official release hashes.
Write-Host "Downloading official XMRig $Version..."
Invoke-WebRequest `
  -Uri "$Release/$FileName" `
  -OutFile "xmrig-download.zip"

Invoke-WebRequest `
  -Uri "$Release/SHA256SUMS" `
  -OutFile "SHA256SUMS"

$Line = Get-Content SHA256SUMS |
    Where-Object { $_ -match [regex]::Escape($FileName) + '$' } |
    Select-Object -First 1

if (-not $Line) {
    throw "Official checksum for $FileName not found"
}

$Expected = ($Line.Trim() -split '\s+')[0].ToLowerInvariant()
$Actual = (Get-FileHash "xmrig-download.zip" -Algorithm SHA256).Hash.ToLowerInvariant()

if ($Expected -ne $Actual) {
    throw "XMRig SHA256 verification FAILED"
}

Write-Host "XMRig SHA256 verified."

New-Item -ItemType Directory -Force -Path xmrig-extracted | Out-Null
Expand-Archive "xmrig-download.zip" "xmrig-extracted" -Force

$Miner = Get-ChildItem "xmrig-extracted" -Recurse -File -Filter "xmrig.exe" |
    Select-Object -First 1

if (-not $Miner) {
    throw "XMRig executable not found in official archive"
}

# Include all supporting files from the release folder.
Copy-Item `
  -Path (Join-Path $Miner.DirectoryName '*') `
  -Destination engine -Recurse -Force

if (!(Test-Path "engine/xmrig.exe")) {
    throw "Missing packaged mining engine"
}

# Include XMRig's GPL license.
Invoke-WebRequest `
  -Uri "https://raw.githubusercontent.com/xmrig/xmrig/v$Version/LICENSE" `
  -OutFile "licenses/xmrig-LICENSE.txt"

Write-Host "Installing Python build dependencies..."


# Create a fresh isolated Windows Python environment
python -m venv .buildvenv

$Python = ".\.buildvenv\Scripts\python.exe"

& $Python -m pip install --upgrade pip
& $Python -m pip install -r requirements.txt

if ($LASTEXITCODE -ne 0) {
    throw "Dependency installation failed"
}

# Verify the version used by this build
& $Python -c @'
import PySide6
from PySide6.QtCore import QCoreApplication
from PySide6.QtWidgets import QApplication
assert PySide6.__version__ == "6.9.3"
print("PySide6:", PySide6.__version__)
print("QtCore OK")
print("QtWidgets OK")
'@

if ($LASTEXITCODE -ne 0) {
    throw "Qt verification failed"
}

& $Python verify_qt.py

if ($LASTEXITCODE -ne 0) {
    throw "Qt verification failed"
}

Write-Host "Compiling Python dashboard..."
& $Python -m py_compile darkminer.py
if ($LASTEXITCODE -ne 0) { throw "Syntax check failed" }

Write-Host "Building self-contained Windows application..."


# Public customer API URL, configured in GitHub Actions.
$LicenseURL = $env:DARKMINER_LICENSE_URL

if (!$LicenseURL -or
    !$LicenseURL.StartsWith("https://")) {
    throw "Set DARKMINER_LICENSE_URL to a public HTTPS URL"
}

$Config = @{
    api_url = $LicenseURL.TrimEnd('/')
} | ConvertTo-Json

Set-Content -Path "license_config.json" `
    -Value $Config -Encoding utf8

$PyInstallerArgs = @(
    "--noconfirm"
    "--clean"
    "--onedir"
    "--windowed"
    "--name=DarkMiner"
    "--add-data=engine;engine"
    "--add-data=license_config.json;."
    "darkminer.py"
)

& $Python -m PyInstaller @PyInstallerArgs

if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller build failed"
}

if (!(Test-Path "dist/DarkMiner/DarkMiner.exe")) {
    throw "Application executable missing"
}

$QtCore = "dist/DarkMiner/_internal/PySide6/Qt6Core.dll"

if (!(Test-Path $QtCore)) {
    throw "Qt6Core.dll missing from package"
}

Write-Host "PyInstaller packaging completed."

Write-Host "Creating Windows installer..."

$Compiler = "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe"
if (!(Test-Path $Compiler)) {
    throw "Inno Setup missing from build machine"
}

& $Compiler "installer.iss"
if ($LASTEXITCODE -ne 0) {
    throw "Inno Setup failed"
}

Write-Host "SUCCESS: output/DarkMiner-Setup-0.3.exe"
