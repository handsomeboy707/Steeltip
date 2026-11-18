@echo off
cd /d "%~dp0"
python configure.py
docker compose up --build -d
echo Open http://127.0.0.1:8000 after the app starts.
pause
