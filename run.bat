@echo off
cd /d "%~dp0"
python sprite_animator.py %*
if errorlevel 1 (
    echo.
    echo Error running sprite_animator.py
    echo Install dependencies: pip install -r requirements.txt
    pause
)
