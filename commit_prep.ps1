& "$PSScriptRoot\venv\Scripts\Activate.ps1"

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Quality Control Check Started" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

$ErrorCount = 0
$WarningCount = 0

# 1. Code Formatting with Black
Write-Host "[1/3] Running Black (Code Formatter)..." -ForegroundColor Yellow
try {
    black . --check --quiet
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Black formatting issues found. Running formatter..." -ForegroundColor Yellow
        black .
        $WarningCount++
    } else {
        Write-Host "Code formatting is correct" -ForegroundColor Green
    }
} catch {
    Write-Host "Black check failed" -ForegroundColor Red
    $ErrorCount++
}
Write-Host ""

# 2. Linting with Flake8
Write-Host "[2/3] Running Flake8 (Linter)..." -ForegroundColor Yellow
try {
    python -m flake8 .
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Flake8 found issues" -ForegroundColor Red
        $ErrorCount++
    } else {
        Write-Host "No linting issues detected" -ForegroundColor Green
    }
} catch {
    Write-Host "Flake8 check failed" -ForegroundColor Red
    $ErrorCount++
}
Write-Host ""