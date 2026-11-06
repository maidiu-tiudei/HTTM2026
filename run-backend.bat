@echo off
cd /d "%~dp0"
title TinaMeetNote Backend
py -3.10 -m uvicorn backend.app:app --host 127.0.0.1 --port 8000
pause