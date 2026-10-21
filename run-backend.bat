@echo off
cd /d "%~dp0"
title TinaMeetNote Backend
python -m uvicorn backend.app:app --port 8000
pause