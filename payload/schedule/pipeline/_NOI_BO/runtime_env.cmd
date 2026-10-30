@echo off
set "PYTHONHOME=%~dp0runtime\python"
set "PYTHONPATH="
set "PYTHONNOUSERSITE=1"
set "PIPELINE_PYTHON=%~dp0runtime\python\python.exe"
set "PIPELINE_PYTHONW=%~dp0runtime\python\pythonw.exe"
set "PATH=%~dp0runtime\ffmpeg;%~dp0runtime\python;%PATH%"
if not exist "%PIPELINE_PYTHONW%" (
 echo Python runtime is missing. Extract the entire portable package.
 pause
 exit /b 1
)
if not exist "%~dp0runtime\ffmpeg\ffprobe.exe" (
 echo FFprobe is missing. Extract the entire portable package.
 pause
 exit /b 1
)
if not exist "%~dp0runtime\ffmpeg\ffmpeg.exe" (
 echo FFmpeg is missing. Extract the entire portable package.
 pause
 exit /b 1
)
exit /b 0
