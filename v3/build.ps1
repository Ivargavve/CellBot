# build.ps1
# Clean build för CellBot v3

Write-Host "Clearing old cache files..."
Remove-Item -Recurse -Force build, dist, *.spec -ErrorAction SilentlyContinue

Write-Host "Building new exe..."
python -m PyInstaller --onefile --noconsole cellbotv3.py

Write-Host ""
Write-Host "Finished!" -ForegroundColor Green
