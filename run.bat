@echo off
title Market Overview Dashboard (Streamlit)
cd /d "%~dp0"
echo ===================================================
echo   Market Overview Dashboard (Streamlit)
echo ===================================================
echo Launching application in your default browser...
python -m streamlit run app.py
pause
