@echo off
setlocal enabledelayedexpansion

echo Dazzlelink File Association Setup
echo ================================
echo.

:: Check for administrative rights
net session >nul 2>&1
if %errorLevel% neq 0 (
    echo This script requires administrative privileges.
    echo Please right-click and select "Run as administrator".
    echo.
    pause
    exit /b 1
)

:: Determine Python path
for /f "tokens=*" %%a in ('where python 2^>nul') do (
    set PYTHON_PATH=%%a
    goto :found_python
)

:: Python not found in PATH, try common locations
if exist "%LOCALAPPDATA%\Programs\Python\Python310\python.exe" (
    set PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python310\python.exe
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python39\python.exe" (
    set PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python39\python.exe
    goto :found_python
)

if exist "%LOCALAPPDATA%\Programs\Python\Python38\python.exe" (
    set PYTHON_PATH=%LOCALAPPDATA%\Programs\Python\Python38\python.exe
    goto :found_python
)

echo Python installation not found. Please make sure Python is installed.
echo.
pause
exit /b 1

:found_python
echo Found Python at: %PYTHON_PATH%

:: Determine script location (default to current directory)
set SCRIPT_DIR=%~dp0
set DAZZLELINK_SCRIPT=%SCRIPT_DIR%dazzlelink.py

if not exist "%DAZZLELINK_SCRIPT%" (
    echo.
    echo dazzlelink.py not found in the current directory.
    echo.
    set /p DAZZLELINK_SCRIPT=Please enter the full path to dazzlelink.py: 
    
    if not exist "!DAZZLELINK_SCRIPT!" (
        echo File not found: !DAZZLELINK_SCRIPT!
        pause
        exit /b 1
    )
)

echo.
echo Using dazzlelink script: %DAZZLELINK_SCRIPT%
echo.

:: Create .reg file for file association
set REGFILE=%TEMP%\dazzlelink_association.reg
echo Windows Registry Editor Version 5.00 > "%REGFILE%"
echo. >> "%REGFILE%"

:: Create file type
echo [HKEY_CLASSES_ROOT\.dazzlelink] >> "%REGFILE%"
echo @="DazzlelinkFile" >> "%REGFILE%"
echo. >> "%REGFILE%"

:: Create file type information
echo [HKEY_CLASSES_ROOT\DazzlelinkFile] >> "%REGFILE%"
echo @="Dazzlelink Symbolic Link" >> "%REGFILE%"
echo "FriendlyTypeName"="Dazzlelink Symbolic Link" >> "%REGFILE%"
echo. >> "%REGFILE%"

:: Create icon entry (using Python icon as default)
echo [HKEY_CLASSES_ROOT\DazzlelinkFile\DefaultIcon] >> "%REGFILE%"
echo @="\"%PYTHON_PATH%\",0" >> "%REGFILE%"
echo. >> "%REGFILE%"

:: Create open command
echo [HKEY_CLASSES_ROOT\DazzlelinkFile\shell\open\command] >> "%REGFILE%"
echo @="\"%PYTHON_PATH%\" \"%DAZZLELINK_SCRIPT%\" execute \"%%1\"" >> "%REGFILE%"
echo. >> "%REGFILE%"

:: Create additional context menu commands
echo [HKEY_CLASSES_ROOT\DazzlelinkFile\shell\info] >> "%REGFILE%"
echo @="Show Information" >> "%REGFILE%"
echo. >> "%REGFILE%"

echo [HKEY_CLASSES_ROOT\DazzlelinkFile\shell\info\command] >> "%REGFILE%"
echo @="\"%PYTHON_PATH%\" \"%DAZZLELINK_SCRIPT%\" execute --mode info \"%%1\"" >> "%REGFILE%"
echo. >> "%REGFILE%"

echo [HKEY_CLASSES_ROOT\DazzlelinkFile\shell\recreate] >> "%REGFILE%"
echo @="Recreate Symlink" >> "%REGFILE%"
echo. >> "%REGFILE%"

echo [HKEY_CLASSES_ROOT\DazzlelinkFile\shell\recreate\command] >> "%REGFILE%"
echo @="\"%PYTHON_PATH%\" \"%DAZZLELINK_SCRIPT%\" import \"%%1\"" >> "%REGFILE%"
echo. >> "%REGFILE%"

:: Create a batch file for execute operation
set EXECUTE_BAT=%SCRIPT_DIR%dazzlelink_execute.bat
echo @echo off > "%EXECUTE_BAT%"
echo "%PYTHON_PATH%" "%DAZZLELINK_SCRIPT%" execute %%* >> "%EXECUTE_BAT%"

:: Apply registry settings
echo Applying registry settings...
regedit.exe /s "%REGFILE%"

echo.
if %errorLevel% equ 0 (
    echo File association created successfully!
    echo.
    echo You can now double-click .dazzlelink files to execute them.
    echo Right-click a .dazzlelink file for additional options.
) else (
    echo Failed to create file association.
)

echo.
pause
exit /b