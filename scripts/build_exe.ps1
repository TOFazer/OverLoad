# Build OverLoad.exe sur Windows (PowerShell)
# Nécessite Python 3.12 + Inno Setup 6 pour l'installateur.

$ErrorActionPreference = "Stop"

Write-Host "== OverLoad : build de l'exe ==" -ForegroundColor Cyan

python -m pip install -e ".[build]"

Write-Host "`n-> PyInstaller..." -ForegroundColor Yellow
pyinstaller overload.spec --noconfirm --clean

if (Test-Path "dist/OverLoad.exe") {
    Write-Host "`nOK : dist/OverLoad.exe généré" -ForegroundColor Green
    $size = (Get-Item "dist/OverLoad.exe").Length / 1MB
    Write-Host ("Taille : {0:N1} Mo" -f $size)
} else {
    Write-Host "Échec : OverLoad.exe introuvable dans dist/" -ForegroundColor Red
    exit 1
}

# Optionnel : INNO Setup si disponible
if (Get-Command iscc -ErrorAction SilentlyContinue) {
    Write-Host "`n-> Inno Setup (OverLoad-Setup.exe)..." -ForegroundColor Yellow
    iscc installer/OverLoad.iss
    if (Test-Path "dist/OverLoad-Setup.exe") {
        Write-Host "OK : dist/OverLoad-Setup.exe généré" -ForegroundColor Green
    }
} else {
    Write-Host "Inno Setup non trouvé (iscc) — installateur non généré (optionnel)." -ForegroundColor DarkYellow
}
