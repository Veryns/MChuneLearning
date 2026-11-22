@echo off
rem Klik dua kali untuk menjalankan Pokedex AI versi web. Browser terbuka otomatis.
rem Tutup jendela hitam ini untuk menghentikan aplikasi.
cd /d "%~dp0"
if not exist venv\Scripts\python.exe (
    echo venv belum dibuat. Jalankan dulu: py -3.12 -m venv venv ^& venv\Scripts\activate ^& pip install -r requirements.txt
    pause
    exit /b 1
)
venv\Scripts\python.exe server.py
pause
