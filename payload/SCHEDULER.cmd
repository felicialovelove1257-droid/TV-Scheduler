@echo off
setlocal
cd /d "%~dp0schedule\pipeline\_NOI_BO"
call runtime_env.cmd
if errorlevel 1 exit /b 1
start "" "%PIPELINE_PYTHONW%" "%CD%\english_ui.py"
