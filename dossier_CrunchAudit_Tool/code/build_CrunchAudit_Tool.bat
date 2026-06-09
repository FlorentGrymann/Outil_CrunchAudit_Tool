@echo off
echo ============================================
echo   Build CrunchAudit_Tool
echo ============================================

:: Verifie que Python est accessible
python --version >nul 2>&1
if errorlevel 1 (
    echo ERREUR : Python introuvable dans le PATH.
    echo Reinstalle Python en cochant "Add Python to PATH".
    pause
    exit /b 1
)

:: Verifie que PyInstaller est installe, sinon l'installe
python -c "import PyInstaller" >nul 2>&1
if errorlevel 1 (
    echo PyInstaller non trouve. Installation en cours...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo ERREUR : impossible d'installer PyInstaller.
        pause
        exit /b 1
    )
)

:: Verifie que main.py est present
if not exist "main.py" (
    echo ERREUR : main.py introuvable.
    echo Lance ce script depuis le dossier contenant main.py et routines_V9.py
    pause
    exit /b 1
)

:: Verifie que routines.py est present
if not exist "routines.py" (
    echo ERREUR : routines.py introuvable.
    echo Lance ce script depuis le dossier contenant main.py et routines_V9.py
    pause
    exit /b 1
)

:: Nettoyage des anciens builds
echo.
echo Nettoyage des anciens builds...
if exist "build"  rmdir /s /q build
if exist "dist"   rmdir /s /q dist
if exist "*.spec" del /q *.spec

:: Compilation
echo.
echo Compilation en cours...
python -m PyInstaller --onefile --windowed --name CrunchAudit_Tool main.py

if errorlevel 1 (
    echo.
    echo ERREUR : la compilation a echoue. Consulte les messages ci-dessus.
    pause
    exit /b 1
)

:: Succes
echo.
echo ============================================
echo   Build termine avec succes !
echo   Executable : dist\CrunchAudit_Tool.exe
echo ============================================
pause
