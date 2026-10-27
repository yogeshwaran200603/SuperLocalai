@echo off
title Superlocal: Windows AI Assistant (by Yogeshwaran)
chcp 65001 >nul
set PYTHONIOENCODING=utf-8
set PYTHONUTF8=1

if exist "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" (
    "C:\Users\Administrator\AppData\Local\Programs\Python\Python312\python.exe" main.py %*
) else (
    python main.py %*
)
