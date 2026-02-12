
@echo off
cd /d "%~dp0"

echo ==============================
echo  Colour Creations Archive
echo  Starting Server...
echo ==============================

IF NOT EXIST "venv" (
    echo Creating virtual environment...
    python -m venv venv
)

echo Activating virtual environment...
call venv\Scripts\activate.bat

echo Installing required packages...
pip install --upgrade pip
pip install -r requirements.txt

echo.
echo Starting Flask server...
echo.

python app.py

echo.
echo ==============================
echo  SERVER STOPPED
echo ==============================

pause
