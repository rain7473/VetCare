$ErrorActionPreference = "Stop"

$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot ".venv\Scripts\python.exe"
$assetsPath = Join-Path $projectRoot "assets"
$iconPath = Join-Path $projectRoot "assets\icons\vetcare.ico"
$versionPath = Join-Path $projectRoot "assets\windows\vetcare_version.txt"

if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw "No se encontró el entorno virtual en $pythonPath"
}
if (-not (Test-Path -LiteralPath $iconPath)) {
    throw "No se encontró el icono en $iconPath"
}

Push-Location $projectRoot
try {
    & $pythonPath -m PyInstaller `
        --noconfirm `
        --clean `
        --onefile `
        --windowed `
        --name VetCare `
        --icon $iconPath `
        --version-file $versionPath `
        --add-data "$assetsPath;assets" `
        --collect-data qtawesome `
        --distpath $projectRoot `
        --workpath "build" `
        --specpath "build" `
        "VetCare.pyw"
    if ($LASTEXITCODE -ne 0) {
        throw "No se pudo generar VetCare.exe (código $LASTEXITCODE)."
    }
}
finally {
    Pop-Location
}
