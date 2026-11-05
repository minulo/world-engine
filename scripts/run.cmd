@echo off
rem Install the world engine, build the default world once, and open it in the browser (Windows).
rem Double-click this file, or run it from cmd with the options of run.ps1, for example:
rem     scripts\run.cmd -Port 9000 -NoBrowser
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0run.ps1" %*
set WORLDENGINE_EXIT=%ERRORLEVEL%
rem After a failure, keep the window of a double-click open so that its message can be read (not in CI).
if not "%WORLDENGINE_EXIT%"=="0" if not defined CI pause
exit /b %WORLDENGINE_EXIT%
