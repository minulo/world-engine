@echo off
rem Open the World Engine control panel (Windows). Double-click this file, or run it from cmd or PowerShell:
rem     scripts\panel.cmd                     open the panel
rem     scripts\panel.cmd -InstallShortcut    put "World Engine" on the Desktop and in the Start menu
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0panel.ps1" %*
set WORLDENGINE_EXIT=%ERRORLEVEL%
rem After a failure, keep the window of a double-click open so that its message can be read (not in CI).
if not "%WORLDENGINE_EXIT%"=="0" if not defined CI pause
exit /b %WORLDENGINE_EXIT%
