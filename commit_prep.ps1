# Quality Control Script for exile_ladder_overlay
# This script runs comprehensive code quality checks before committing
$timer = [System.Diagnostics.Stopwatch]::StartNew()
& "$PSScriptRoot\venv\Scripts\Activate.ps1"

Write-Host "================================" -ForegroundColor Cyan
Write-Host "Quality Control Check Started" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host ""

$ErrorCount = 0
$WarningCount = 0

# 1. Code Formatting with Black
Write-Host "[1/5] Running Black (Code Formatter)..." -ForegroundColor Yellow
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
Write-Host "[2/5] Running Flake8 (Linter)..." -ForegroundColor Yellow
try {
    python -m flake8 .\
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

# 3. Blank Line Check
Write-Host "[3/5] Running Blank Line Hater (Style Check)..." -ForegroundColor Yellow
try {
    Push-Location $PSScriptRoot
    $blsOutput = python "$PSScriptRoot\blank_line_hater.py" --fix 2>&1
    $blsExitCode = $LASTEXITCODE
    Pop-Location
    foreach ($line in ($blsOutput -split "`n")) {
        if ($line -match '>>> code "(.+):(\d+)"') {
            $blsFile = $matches[1]
            $blsLine = $matches[2]
            $blsUri = "vscode://file/$blsFile`:$blsLine"
            $esc = [char]27
            Write-Host "    >>> $esc]8;;$blsUri$esc\code $blsFile`:$blsLine$esc]8;;$esc\" -ForegroundColor Cyan
        } else {
            Write-Host $line
        }
    }
    if ($blsExitCode -ne 0) {
        Write-Host "Blank line style issues found" -ForegroundColor Red
        $ErrorCount++
    } else {
        Write-Host "No blank line issues detected" -ForegroundColor Green
    }
} catch {
    Write-Host "Blank line check failed" -ForegroundColor Red
    $ErrorCount++
}
Write-Host ""

# 4. Type Checking with MyPy
Write-Host "[4/5] Running MyPy (Type Checker)..." -ForegroundColor Yellow
try {
    python -m mypy .\
    if ($LASTEXITCODE -ne 0) {
        Write-Host "MyPy found type issues" -ForegroundColor Yellow
        $WarningCount++
    } else {
        Write-Host "Type checking passed" -ForegroundColor Green
    }
} catch {
    Write-Host "MyPy check had an issue (non-critical)" -ForegroundColor Yellow
    $WarningCount++
}
Write-Host ""

# 5. Docstring Consistency Check
Write-Host "[5/5] Running Docstring Checker..." -ForegroundColor Yellow
try {
    $checkerScript = "$PSScriptRoot\check_docstrings.py"
    $checkerPython = "$PSScriptRoot\venv\Scripts\python.exe"

    if ((Test-Path $checkerPython) -and (Test-Path $checkerScript)) {
        [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
        $env:PYTHONIOENCODING = "utf-8"
        $env:FORCE_COLOR = "1"
        $stderrFile = [System.IO.Path]::GetTempFileName()
        Start-Process -FilePath $checkerPython -ArgumentList @("`"$checkerScript`"", "`"$PSScriptRoot`"") -RedirectStandardError $stderrFile -NoNewWindow -Wait
        $env:FORCE_COLOR = $null
        $env:PYTHONIOENCODING = $null
        $stderrContent = Get-Content $stderrFile -Raw -Encoding utf8
        Remove-Item $stderrFile -Force
        if ($stderrContent -match 'DOCCHECK_MISMATCHES:(\d+)') {
            $mismatchCount = [int]$matches[1]
            if ($mismatchCount -gt 0) {
                Write-Host "  $mismatchCount docstring mismatch(es) - review before committing" -ForegroundColor Yellow
                $WarningCount++
            } else {
                Write-Host "  No docstring mismatches found" -ForegroundColor Green
            }
        } else {
            Write-Host "  Docstring check complete (output did not match expected pattern)" -ForegroundColor Yellow
        }
    } else {
        Write-Host "  Docstring checker not found at '$PSScriptRoot' - skipping" -ForegroundColor Yellow
        $WarningCount++
    }
} catch {
    Write-Host "  Docstring check had an issue: $_" -ForegroundColor Yellow
    $WarningCount++
}
Write-Host ""

# Summary
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Quality Control Summary" -ForegroundColor Cyan
Write-Host "================================" -ForegroundColor Cyan
Write-Host "Errors found: $ErrorCount" -ForegroundColor $(if ($ErrorCount -gt 0) { "Red" } else { "Green" })
Write-Host "Warnings found: $WarningCount" -ForegroundColor $(if ($WarningCount -gt 0) { "Yellow" } else { "Green" })
Write-Host ""
$timer.Stop()
Write-Host "Prep completed in $([math]::Round($timer.Elapsed.TotalSeconds, 1)) seconds" -ForegroundColor Cyan
Write-Host ""
$success = $true
if ($ErrorCount -gt 0) {
    Write-Host "FAILED: Fix errors before committing" -ForegroundColor Red
    $success = $false
} elseif ($WarningCount -gt 0) {
    Write-Host "WARNINGS: Review warnings above" -ForegroundColor Yellow
    $success = $false
} else {
    Write-Host "ALL CHECKS PASSED - Ready to commit!" -ForegroundColor Green
}
Write-Host "================================" -ForegroundColor Cyan
if (-not $success) {
    exit 1
}