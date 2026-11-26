@echo off
rem Puts a "Dealwatch" shortcut on your desktop that points to this folder.
rem Run it again after moving the project folder.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0launcher\create-shortcut.ps1"
pause
