@echo off
rem ============================================================
rem  War in the North - Widescreen Mod
rem  Author:  Imyala
rem  Version: 1.9
rem  Guide:   https://steamcommunity.com/sharedfiles/filedetails/?id=3786147705
rem  Licensed under MIT. Copyright (c) 2026 Imyala.
rem  Keep this header intact in forks and redistributions.
rem ============================================================
cd /d "%~dp0"
title War in the North - Ultrawide + HUD

if not exist witn.exe goto nogame

set PY=
where py >nul 2>&1 && set PY=py -3
if not defined PY goto trypython
goto havepython
:trypython
where python >nul 2>&1 && set PY=python
if not defined PY goto nopython
:havepython

echo.
echo   Your monitor resolution, for example 3440x1440 or 5120x1440.
echo   One build covers 2560x1080, 3440x1440, 3840x1600 and 5120x1440, so this
echo   only picks which family goes in the primary slot.
set /p RES=  Resolution [3440x1440]: 
if "%RES%"=="" set RES=3440x1440

echo.
echo   Patching witn.exe for %RES% ...
%PY% witn_patch.py --res %RES%
if errorlevel 1 goto failed

echo.
echo   Repositioning the HUD ...
%PY% witn_hud_shift.py --res %RES%
if errorlevel 1 goto failed

echo.
echo   Done.  Fully quit the game before launching it, then pick %RES%
echo   in the video options.  Works on every Steam build so far, including
echo   Patch 2 (3 Nov 2026) - the installer re-finds everything by signature.  F5 quicksaves out in the levels, F6 in the
echo   hub towns (Bree, Rivendell, Nordinbad, Sarn Ford).
echo.
echo   To undo:  witn_patch.py --revert  and  witn_hud_shift.py --revert
echo.
pause
exit /b 0

:nogame
echo.
echo   witn.exe is not in this folder.
echo   Copy every file from this package into your game folder, the one
echo   that contains witn.exe, then run install.bat from there:
echo       ...\steamapps\common\LORWIN
echo.
pause
exit /b 1

:nopython
echo.
echo   Python 3 was not found.
echo   Install it from https://www.python.org/downloads/ and tick
echo   "Add python.exe to PATH" on the first page of the installer,
echo   then run this again.
echo.
pause
exit /b 1

:failed
echo.
echo   Something went wrong - the message above says what.  Nothing was left
echo   half-applied: both scripts always rebuild from their .original backup.
echo   If the game has just updated and it still fails, grab the newest
echo   version of this mod from the guide - a game update can move things.
echo.
pause
exit /b 1
