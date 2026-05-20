@echo off
cd /d "%~dp0"

REM Activate Python virtual environment (where streamlit is installed)
call "C:\Claude Projects\venv\Scripts\activate.bat"

REM Kill any process already listening on port 8501
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8501 ^| findstr LISTENING') do (
  taskkill /F /PID %%a >nul 2>&1
)

echo.
echo ============================================
echo  VIP Briefing - Streamlit Server
echo ============================================
echo  Starting... browser will open automatically.
echo  If not, open: http://localhost:8501
echo.
echo  To stop the server: close this window.
echo ============================================
echo.

streamlit run app.py --browser.gatherUsageStats false

pause
