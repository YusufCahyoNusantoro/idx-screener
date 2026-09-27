"""
jadwal_screener.py — jalankan idx_screener.py otomatis sesuai jam bursa BEI.

Mode:
  sesi  (default) : jalan 1x setelah penutupan Sesi 1 dan 1x setelah closing harian
  live            : jalan tiap N menit selama jam perdagangan (+ snapshot penutupan)

Contoh:
  python jadwal_screener.py                       # mode sesi
  python jadwal_screener.py --mode live --interval 15
  python jadwal_screener.py --cmd "python idx_screener.py --top 50"
  python jadwal_screener.py --sekarang            # jalankan sekali saat ini juga (tes)

Jam BEI (WIB), Senin–Kamis: Sesi 1 09:00–12:00, Sesi 2 13:30–15:49
                 Jumat      : Sesi 1 09:00–11:30, Sesi 2 14:00–15:49
Pre-closing 15:50–16:00 -> harga penutupan resmi keluar ~16:00.
Cek ulang jadwal di idx.co.id kalau BEI mengubah jam perdagangan.
"""
import argparse
import subprocess
import sys
import time
from datetime import datetime, date, time as dtime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:  # Windows tanpa paket tzdata -> WIB tetap UTC+7 (Indonesia tidak pakai DST)
    from datetime import timezone, timedelta as _td
    WIB = timezone(_td(hours=7), "WIB")

# Isi tanggal libur bursa dari kalender resmi BEI (format YYYY-MM-DD).
LIBUR_BURSA = {
    # "2026-12-25",
    # "2026-12-31",
}

# Jeda setelah sesi tutup supaya data di sumber (mis. Yahoo) sempat ter-update.
JEDA_SESI1 = timedelta(minutes=5)
JEDA_CLOSING = timedelta(minutes=20)   # 15:49 + pre-closing + delay data -> ~16:10–16:20


def jam_sesi(d: date):
    """Kembalikan (buka1, tutup1, buka2, tutup2) untuk tanggal d."""
    if d.weekday() == 4:  # Jumat
        return dtime(9, 0), dtime(11, 30), dtime(14, 0), dtime(15, 50)
    return dtime(9, 0), dtime(12, 0), dtime(13, 30), dtime(15, 50)


def hari_bursa(d: date) -> bool:
    return d.weekday() < 5 and d.isoformat() not in LIBUR_BURSA


def dt(d: date, t: dtime) -> datetime:
    return datetime.combine(d, t, tzinfo=WIB)


def jadwal_hari(d: date, mode: str, interval: int):
    """Daftar (waktu_jalan, label) untuk satu hari bursa."""
    b1, t1, b2, t2 = jam_sesi(d)
    runs = [(dt(d, t1) + JEDA_SESI1, "Penutupan Sesi 1"),
            (dt(d, t2) + JEDA_CLOSING, "Closing harian")]
    if mode == "live":
        step = timedelta(minutes=interval)
        for mulai, akhir, nama in ((dt(d, b1), dt(d, t1), "Sesi 1"),
                                   (dt(d, b2), dt(d, t2), "Sesi 2")):
            t = mulai + step
            while t < akhir:
                runs.append((t, f"Intraday {nama}"))
                t += step
    return sorted(runs)


def jadwal_berikutnya(sekarang: datetime, mode: str, interval: int):
    d = sekarang.date()
    for _ in range(15):
        if hari_bursa(d):
            for waktu, label in jadwal_hari(d, mode, interval):
                if waktu > sekarang:
                    return waktu, label
        d += timedelta(days=1)
    raise RuntimeError("Tidak ada hari bursa dalam 15 hari ke depan — cek LIBUR_BURSA.")


def jalankan(cmd: str, label: str):
    stamp = datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{stamp} WIB] ▶ {label}: {cmd}", flush=True)
    hasil = subprocess.run(cmd, shell=True)
    status = "OK" if hasil.returncode == 0 else f"GAGAL (kode {hasil.returncode})"
    print(f"[{datetime.now(WIB):%H:%M:%S} WIB] ■ {label} selesai: {status}", flush=True)


def main():
    ap = argparse.ArgumentParser(description="Penjadwal screener IDX")
    ap.add_argument("--mode", choices=["sesi", "live"], default="sesi")
    ap.add_argument("--interval", type=int, default=15, help="menit, untuk mode live")
    skrip = Path(__file__).resolve().parent / "idx_screener.py"
    ap.add_argument("--cmd", default=f'"{sys.executable}" "{skrip}"',
                    help="perintah yang dijalankan tiap jadwal")
    ap.add_argument("--sekarang", action="store_true", help="jalankan sekali lalu keluar")
    args = ap.parse_args()

    if args.sekarang:
        jalankan(args.cmd, "Manual")
        return

    print(f"Penjadwal aktif — mode {args.mode}"
          + (f", tiap {args.interval} menit" if args.mode == "live" else "")
          + ". Ctrl+C untuk berhenti.", flush=True)
    while True:
        waktu, label = jadwal_berikutnya(datetime.now(WIB), args.mode, args.interval)
        print(f"Berikutnya: {label} pada {waktu:%a %d %b %H:%M} WIB", flush=True)
        while (sisa := (waktu - datetime.now(WIB)).total_seconds()) > 0:
            time.sleep(min(sisa, 60))
        jalankan(args.cmd, label)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nDihentikan.")
