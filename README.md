# Dibalik Saham — Screener Saham IDX (Research & Insight)

Screener semua saham Bursa Efek Indonesia (±950 emiten) dengan data asli dari Yahoo Finance,
diperbarui otomatis setelah **penutupan Sesi 1** dan setelah **closing** setiap hari bursa.

**Lihat aplikasinya: https://yusufcahyonusantoro.github.io/idx-screener/**

## Isi aplikasi
- **Kondisi pasar:** IHSG (bisa diklik untuk detail lengkap), napas pasar, dan jumlah saham per kondisi.
- **Tabel screener:** skor, checklist 10 syarat, label Kondisi, struktur SMC Mingguan/Harian/4 jam, rencana contoh, sinyal, RSI, nilai transaksi, sektor, beta, ringkasan teknikal 1 jam sampai bulanan, dan konsistensi Top 10.
- **Preset:** Struktur searah naik, Tren naik rapi, Likuid & konsisten, Breakout, Kuat di semua timeframe, Pantulan dari bawah, Ada pola candle, dan Watchlist.
- **Filter:** kode/nama, kondisi, sektor, harga, RSI, nilai transaksi, konsistensi Top 10, dan skor minimum.
- **Panel detail per saham:** chart 120 hari dengan Smart Money Concepts (BOS/CHoCH, order block, FVG, EQH/EQL, premium/discount, volume profile, fase bulan), checklist, rencana berbasis ATR atau struktur, kalkulator lot, dan tombol catat ke jurnal.
- **Kalender:** fase bulan (WIB) dan agenda pasar (MSCI, FTSE, GDX, batas laporan keuangan).
- **Jurnal trading:** catat trade, tutup dengan harga keluar, lihat win rate dan rata-rata R per setup, unduh CSV.

## File di repo
| File | Fungsi |
|---|---|
| `idx_screener.py` | Program utama: ambil data, hitung indikator, buat halaman |
| `daftar_saham.csv` | Daftar emiten (kode, nama, sektor); dicoba diperbarui dari situs BEI tiap minggu |
| `tambahan_tickers.txt` | Opsional: kode IPO baru yang belum ada di daftar, satu per baris |
| `kalender.json` | Opsional: agenda tambahanmu sendiri |
| `.github/workflows/screener.yml` | Jadwal otomatis di GitHub Actions |
| `docs/index.html` | Halaman aplikasi (dibuat otomatis) |
| `docs/hasil_screener.csv` | Data mentah hasil screen (dibuat otomatis) |

## Jadwal update (WIB)
| Hari | Setelah Sesi 1 | Setelah closing |
|---|---|---|
| Senin–Kamis | ±12:05 | ±16:10 |
| Jumat | ±11:35 | ±16:10 |

Jadwal GitHub Actions bisa telat beberapa menit. Untuk update segera: tab **Actions → Update Screener → Run workflow**.

## Jalankan di komputer sendiri (Windows)
1. Pasang Python dari python.org.
2. Taruh `idx_screener.py`, `daftar_saham.csv`, `jadwal_screener.py`, dan `jalankan_screener.bat` di satu folder.
3. Klik dua kali `jalankan_screener.bat`.

## Catatan
- Harga dari Yahoo Finance biasanya tertunda ±10–15 menit dan bisa sedikit berbeda dari data bursa.
- SMC di aplikasi adalah versi sederhana yang dihitung otomatis; hasilnya bisa berbeda dari indikator SMC di TradingView atau Stockbit.
- Watchlist, pengaturan, dan jurnal tersimpan di browser masing-masing, tidak ikut ke repo.
- **Bukan rekomendasi atau nasihat keuangan.** Alat bantu penyaringan teknikal saja; lakukan riset dan manajemen risiko sendiri.
