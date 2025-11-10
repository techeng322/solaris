# PowerShell script to set up Python 3.12 virtual environment for Solaris project
# Run this script after installing Python 3.12

Write-Host "=== Solaris Python 3.12 Environment Setup ===" -ForegroundColor Cyan
Write-Host ""

# Check if Python 3.12 is available
Write-Host "Checking for Python 3.12..." -ForegroundColor Yellow
$python312 = $null

# Try different ways to find Python 3.12
$pythonPaths = @(
    "py -3.12",
    "python3.12",
    "C:\Python312\python.exe",
    "C:\Program Files\Python312\python.exe",
    "C:\Users\$env:USERNAME\AppData\Local\Programs\Python\Python312\python.exe"
)

foreach ($path in $pythonPaths) {
    try {
        if ($path -like "py -3.12") {
            $result = & py -3.12 --version 2>&1
        } elseif ($path -like "python3.12") {
            $result = & python3.12 --version 2>&1
        } else {
            if (Test-Path $path) {
                $result = & $path --version 2>&1
            } else {
                continue
            }
        }
        
        if ($result -like "*3.12*") {
            if ($path -like "py -3.12") {
                $python312 = "py -3.12"
            } elseif ($path -like "python3.12") {
                $python312 = "python3.12"
            } else {
                $python312 = $path
            }
            Write-Host "Found Python 3.12: $python312" -ForegroundColor Green
            break
        }
    } catch {
        continue
    }
}

if (-not $python312) {
    Write-Host "ERROR: Python 3.12 not found!" -ForegroundColor Red
    Write-Host ""
    Write-Host "Please install Python 3.12 from:" -ForegroundColor Yellow
    Write-Host "https://www.python.org/downloads/release/python-31211/" -ForegroundColor Cyan
    Write-Host ""
    Write-Host "During installation, make sure to:" -ForegroundColor Yellow
    Write-Host "  1. Check 'Add Python to PATH'" -ForegroundColor White
    Write-Host "  2. Check 'Install for all users' (optional)" -ForegroundColor White
    Write-Host ""
    Write-Host "After installation, run this script again." -ForegroundColor Yellow
    exit 1
}

# Create virtual environment
Write-Host ""
Write-Host "Creating virtual environment 'venv312'..." -ForegroundColor Yellow

if (Test-Path "venv312") {
    Write-Host "Virtual environment 'venv312' already exists." -ForegroundColor Yellow
    $overwrite = Read-Host "Do you want to recreate it? (y/N)"
    if ($overwrite -eq "y" -or $overwrite -eq "Y") {
        Remove-Item -Recurse -Force "venv312"
    } else {
        Write-Host "Using existing virtual environment." -ForegroundColor Green
    }
}

if (-not (Test-Path "venv312")) {
    if ($python312 -like "py -3.12") {
        & py -3.12 -m venv venv312
    } elseif ($python312 -like "python3.12") {
        & python3.12 -m venv venv312
    } else {
        & $python312 -m venv venv312
    }
    
    if ($LASTEXITCODE -ne 0) {
        Write-Host "ERROR: Failed to create virtual environment!" -ForegroundColor Red
        exit 1
    }
    Write-Host "Virtual environment created successfully!" -ForegroundColor Green
}

# Activate virtual environment
Write-Host ""
Write-Host "Activating virtual environment..." -ForegroundColor Yellow
& "venv312\Scripts\Activate.ps1"

if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Could not activate virtual environment automatically." -ForegroundColor Yellow
    Write-Host "Please run manually: .\venv312\Scripts\Activate.ps1" -ForegroundColor Cyan
} else {
    Write-Host "Virtual environment activated!" -ForegroundColor Green
}

# Upgrade pip
Write-Host ""
Write-Host "Upgrading pip..." -ForegroundColor Yellow
python -m pip install --upgrade pip

# Install dependencies
Write-Host ""
Write-Host "Installing project dependencies (this may take a few minutes)..." -ForegroundColor Yellow
Write-Host ""

python -m pip install -r requirements.txt

if ($LASTEXITCODE -eq 0) {
    Write-Host ""
    Write-Host "=== Setup Complete! ===" -ForegroundColor Green
    Write-Host ""
    Write-Host "To use this environment in the future:" -ForegroundColor Cyan
    Write-Host "  1. Activate: .\venv312\Scripts\Activate.ps1" -ForegroundColor White
    Write-Host "  2. Run: python run_gui.py" -ForegroundColor White
    Write-Host ""
    Write-Host "To verify Open3D installation:" -ForegroundColor Cyan
    Write-Host '  python -c "import open3d as o3d; print(''Open3D version:'', o3d.__version__)"' -ForegroundColor White
} else {
    Write-Host ""
    Write-Host "ERROR: Some dependencies failed to install." -ForegroundColor Red
    Write-Host "Please check the error messages above." -ForegroundColor Yellow
    exit 1
}

