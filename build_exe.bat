@echo off
cd /d "%~dp0"
python -m pip install pyinstaller
pyinstaller --noconsole --onefile --name ArabicScreenTranslator app.py
pause
