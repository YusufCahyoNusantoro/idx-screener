# 📈 IDX Screener — Teknikal & Price Action

Screener saham Bursa Efek Indonesia dengan data asli (Yahoo Finance), diperbarui otomatis
setelah **penutupan Sesi 1** dan setelah **closing** setiap hari bursa.

**👉 Lihat hasil terbaru: https://USERNAME.github.io/NAMA-REPO/**
*(ganti USERNAME dan NAMA-REPO dengan milikmu)*

## Isi screener
- Skor gabungan: Trend (MA20/50/200), Breakout 20 hari + volume, Price Action (pola candle), Momentum (RSI)
- Ringkasan teknikal 1H / 2H / 4H / Daily / Mingguan / Bulanan
- Preset: Breakout Momentum, Golden Cross Uptrend, Oversold Reversal, Strong Buy Semua Timeframe, dll.
- Konsistensi masuk Top-10 dalam 10 hari bursa terakhir
- Data mentah juga tersedia: `docs/hasil_screener.csv`

## Jadwal update (WIB)
| Hari | Setelah Sesi 1 | Setelah closing |
|---|---|---|
| Senin–Kamis | ±12:05 | ±16:10 |
| Jumat | ±11:35 | ±16:10 |

Jadwal GitHub Actions bisa telat beberapa menit sampai lebih lama saat server GitHub sibuk.

## Jalankan di komputer sendiri (Windows)
1. Pasang Python dari python.org
2. Klik dua kali `jalankan_screener.bat`

Atau manual: `pip install -r requirements.txt` lalu `python idx_screener.py --buka`

## Catatan
- Harga dari Yahoo Finance biasanya tertunda ±10–15 menit dari bursa.
- ⚠️ **Bukan rekomendasi/nasihat keuangan.** Alat bantu penyaringan teknikal saja —
  lakukan riset dan manajemen risiko sendiri sebelum trading.
