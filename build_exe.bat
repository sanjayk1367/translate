@echo off
cd /d %~dp0

echo Installing requirements...
pip install -r requirements.txt

echo Building exe...
pyinstaller --noconfirm --clean --onedir --windowed --name PDFTranslator --add-data "templates;templates" app.py

echo.
echo Build completed.
echo EXE path: dist\PDFTranslator\PDFTranslator.exe
pause