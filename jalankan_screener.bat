@echo off
cd /d "%~dp0"
echo Memasang/cek library (sekali saja agak lama)...
python -m pip install --quiet yfinance pandas numpy tzdata
echo.
echo Menjalankan screener sekarang...
python idx_screener.py --buka
echo.
echo Penjadwal aktif: otomatis jalan setelah Sesi 1 dan setelah closing.
echo Biarkan jendela ini terbuka. Tutup jendela untuk berhenti.
python jadwal_screener.py
pause
