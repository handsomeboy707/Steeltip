@echo off
setlocal
cd /d "%~dp0"
echo SteelTip - Windows MariaDB and MongoDB mode
echo Keep both database servers running. Stop the offline demo first.
echo.
if exist ".venv\Scripts\python.exe" goto check_dependencies
python -m venv .venv
if errorlevel 1 goto failed
:check_dependencies
".venv\Scripts\python.exe" -c "import fastapi,uvicorn,pymysql,pymongo" >nul 2>&1
if not errorlevel 1 goto launch
echo Installing the required Python packages. Internet is needed for this step.
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 goto failed
:launch
".venv\Scripts\python.exe" -m app.native_setup
if errorlevel 1 goto failed
goto end
:failed
echo.
echo SteelTip did not start. Read the error above before closing this window.
:end
pause
