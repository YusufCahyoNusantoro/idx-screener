#!/usr/bin/env python3
"""
idx_screener.py — Screener saham IDX dengan DATA ASLI (Yahoo Finance via yfinance).

Pasang dulu (sekali saja):
    pip install yfinance pandas numpy tzdata

Pakai:
    python idx_screener.py                  # screen daftar default -> hasil_screener.html
    python idx_screener.py --buka           # sekalian buka di browser
    python idx_screener.py --tickers daftar.txt   # daftar ticker sendiri (1 ticker per baris)
    python idx_screener.py --no-intraday    # lebih cepat, tanpa kolom 1H/2H/4H
    python idx_screener.py --no-sektor      # lewati ambil sektor (run pertama jadi lebih cepat)

Output (di folder yang sama dengan file ini):
    hasil_screener.html   -> buka di browser; halaman reload otomatis tiap 5 menit
    hasil_screener.csv    -> data mentah hasil screen
    arsip/                -> salinan tiap run (untuk dibandingkan antar sesi)

Catatan data: harga Yahoo untuk saham IDX biasanya tertunda ±10–15 menit.
Bukan rekomendasi/nasihat keuangan.
"""
import argparse
import json
import math
import sys
import time
import webbrowser
from datetime import datetime, time as dtime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd

try:
    import yfinance as yf
except ImportError:
    sys.exit("yfinance belum terpasang. Jalankan dulu:  pip install yfinance pandas numpy")

try:
    WIB = ZoneInfo("Asia/Jakarta")
except Exception:  # Windows tanpa paket tzdata -> WIB tetap UTC+7 (Indonesia tidak pakai DST)
    from datetime import timezone, timedelta as _td
    WIB = timezone(_td(hours=7), "WIB")
BASE = Path(__file__).resolve().parent
OUT_HTML = BASE / "hasil_screener.html"
OUT_CSV = BASE / "hasil_screener.csv"
ARSIP = BASE / "arsip"
CACHE_SEKTOR = BASE / "cache_sektor.json"
RIWAYAT = BASE / "riwayat_top10.json"
DAFTAR = BASE / "daftar_saham.csv"          # semua emiten BEI: kode, nama, sektor
TAMBAHAN = BASE / "tambahan_tickers.txt"    # opsional: IPO baru yang belum ada di daftar
DAFTAR_INFO = BASE / "daftar_saham_info.json"  # kapan daftar terakhir diperbarui dari BEI

# Daftar default: saham-saham likuid IDX. Edit sesukamu, atau pakai --tickers file.txt
DEFAULT_TICKERS = """
BBCA BBRI BMRI BBNI BRIS ARTO BBTN BNGA NISP BDMN BJBR BJTM MEGA PNBN
TLKM ISAT EXCL TOWR MTEL
ASII UNTR AUTO
UNVR ICBP INDF MYOR CPIN JPFA KLBF SIDO MAPI MAPA ACES AMRT ERAA HMSP GGRM
ADRO AADI PTBA ITMG HRUM INDY MEDC PGAS AKRA ELSA ENRG BUMI DEWA PTRO
ANTM INCO MDKA TINS NCKL MBMA AMMN BRMS PSAB ARCI
SMGR INTP
BSDE CTRA PWON SMRA
JSMR
BRPT TPIA ESSA INKP TKIM
GOTO BUKA EMTK SCMA MNCN
PGEO BREN CUAN RAJA
MIKA HEAL SILO
AALI LSIP DSNG TAPG
ADMR SRTG BIRD
""".split()

LOGO_96 = "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"   # logo Dibalik Saham (ikon rakun), PNG base64
LOGO_32 = "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"

W_DEFAULT = {"trend": 25, "brk": 20, "pa": 20, "mom": 10, "st": 25}   # sama dengan bobot awal di HTML

KALENDER = BASE / "kalender.json"   # opsional: agenda tambahanmu sendiri (lihat README / panduan)

# Agenda pasar bawaan (tanggal WIB). Sumber: jadwal resmi MSCI (rilis 12 Agu 2026), FTSE GEIS 2026 (Jul 2026),
# MarketVector MVGDX, dan POJK 14/2022 untuk batas laporan keuangan. Jenis: msci, ftse, gdx, lapkeu.
AGENDA_DEFAULT = [
    ["2026-08-12", "msci", "MSCI: pengumuman review Agustus 2026", "Hasil biasanya terbaca dini hari WIB keesokan harinya.", []],
    ["2026-08-21", "ftse", "FTSE: rilis file indikatif review September 2026", "", []],
    ["2026-08-31", "msci", "MSCI: rebalancing review Agustus (penutupan)", "Efektif 1 September 2026. Volume saham yang masuk/keluar biasanya melonjak di penutupan hari ini.", []],
    ["2026-09-11", "gdx", "GDX/GDXJ: pengumuman review Q3 2026", "MarketVector Global Gold Miners Index.", ["AMMN", "BRMS", "ARCI", "EMAS", "PSAB"]],
    ["2026-09-18", "gdx", "GDX/GDXJ: implementasi review Q3 2026 (penutupan)", "", ["AMMN", "BRMS", "ARCI", "EMAS", "PSAB"]],
    ["2026-09-18", "ftse", "FTSE: rebalancing review September 2026 (penutupan)", "Efektif saat pembukaan Senin 21 September 2026.", []],
    ["2026-10-31", "lapkeu", "Batas laporan keuangan Q3 2026 (tanpa audit)", "Akhir bulan pertama setelah 30 September (POJK 14/2022). Jatuh pada hari Sabtu; banyak emiten merilis di hari kerja terakhir Oktober.", []],
    ["2026-11-11", "msci", "MSCI: pengumuman review November 2026", "Hasil biasanya terbaca dini hari 12 November WIB. Pasar menyorot keputusan MSCI terkait perlakuan saham Indonesia.", []],
    ["2026-11-13", "ftse", "FTSE: rilis file indikatif review Desember 2026", "FTSE menunda penambahan saham Indonesia setidaknya sampai review Desember 2026.", []],
    ["2026-11-30", "msci", "MSCI: rebalancing review November (penutupan)", "Efektif 1 Desember 2026.", []],
    ["2026-11-30", "lapkeu", "Batas laporan keuangan Q3 2026 (direviu akuntan)", "Akhir bulan kedua setelah 30 September.", []],
    ["2026-12-04", "ftse", "FTSE: rilis file final review Desember 2026", "", []],
    ["2026-12-11", "gdx", "GDX: pengumuman review Q4 2026", "", ["AMMN", "BRMS", "ARCI", "EMAS", "PSAB"]],
    ["2026-12-18", "gdx", "GDX: implementasi review Q4 2026 (penutupan)", "", ["AMMN", "BRMS", "ARCI", "EMAS", "PSAB"]],
    ["2026-12-18", "ftse", "FTSE: rebalancing review Desember 2026 (penutupan)", "Efektif saat pembukaan Senin 21 Desember 2026.", []],
    ["2026-12-31", "lapkeu", "Batas laporan keuangan Q3 2026 (diaudit)", "Akhir bulan ketiga setelah 30 September.", []],
    ["2027-02-09", "msci", "MSCI: pengumuman review Februari 2027", "", []],
    ["2027-02-26", "msci", "MSCI: rebalancing review Februari (penutupan)", "Efektif 1 Maret 2027.", []],
    ["2027-03-31", "lapkeu", "Batas laporan keuangan tahunan 2026", "Akhir bulan ketiga setelah 31 Desember (POJK 14/2022).", []],
    ["2027-05-10", "msci", "MSCI: pengumuman review Mei 2027", "", []],
    ["2027-05-27", "msci", "MSCI: rebalancing review Mei (penutupan)", "Efektif 28 Mei 2027.", []],
    ["2027-08-12", "msci", "MSCI: pengumuman review Agustus 2027", "", []],
    ["2027-08-31", "msci", "MSCI: rebalancing review Agustus 2027 (penutupan)", "Efektif 1 September 2027.", []],
    # --- kalender ekonomi (tanggal WIB) ---
    # BI: jadwal RDG 2026 resmi Bank Indonesia; keputusan BI Rate diumumkan di hari ke-2.
    ["2026-09-23", "bi", "BI: pengumuman suku bunga (RDG 22–23 Sep)", "Keputusan BI Rate diumumkan siang hari WIB di hari kedua RDG.", []],
    ["2026-10-21", "bi", "BI: pengumuman suku bunga (RDG 20–21 Okt)", "RDG cakupan triwulanan dan tahunan. Keputusan BI Rate diumumkan siang hari WIB.", []],
    ["2026-11-18", "bi", "BI: pengumuman suku bunga (RDG 17–18 Nov)", "Keputusan BI Rate diumumkan siang hari WIB.", []],
    ["2026-12-16", "bi", "BI: pengumuman suku bunga (RDG 15–16 Des)", "Keputusan BI Rate diumumkan siang hari WIB.", []],
    # FOMC: keputusan 14:00 waktu New York = dini hari WIB keesokan harinya (ditaruh di tanggal WIB).
    ["2026-09-17", "fomc", "The Fed: keputusan suku bunga (FOMC 15–16 Sep)", "Diumumkan sekitar pukul 01.00 WIB; dampaknya terasa di perdagangan BEI hari ini.", []],
    ["2026-10-29", "fomc", "The Fed: keputusan suku bunga (FOMC 27–28 Okt)", "Diumumkan sekitar pukul 01.00 WIB; dampaknya terasa di perdagangan BEI hari ini.", []],
    ["2026-12-10", "fomc", "The Fed: keputusan suku bunga (FOMC 8–9 Des)", "Diumumkan sekitar pukul 02.00 WIB, disertai proyeksi ekonomi (dot plot).", []],
    ["2027-01-28", "fomc", "The Fed: keputusan suku bunga (FOMC 26–27 Jan)", "Diumumkan dini hari WIB. Jadwal 2027 masih tentatif menurut The Fed.", []],
    ["2027-03-18", "fomc", "The Fed: keputusan suku bunga (FOMC 16–17 Mar)", "Diumumkan dini hari WIB, disertai proyeksi ekonomi.", []],
    ["2027-04-29", "fomc", "The Fed: keputusan suku bunga (FOMC 27–28 Apr)", "Diumumkan dini hari WIB.", []],
    ["2027-06-10", "fomc", "The Fed: keputusan suku bunga (FOMC 8–9 Jun)", "Diumumkan dini hari WIB, disertai proyeksi ekonomi.", []],
    ["2027-07-29", "fomc", "The Fed: keputusan suku bunga (FOMC 27–28 Jul)", "Diumumkan dini hari WIB.", []],
    ["2027-09-16", "fomc", "The Fed: keputusan suku bunga (FOMC 14–15 Sep)", "Diumumkan dini hari WIB, disertai proyeksi ekonomi.", []],
    ["2027-10-28", "fomc", "The Fed: keputusan suku bunga (FOMC 26–27 Okt)", "Diumumkan dini hari WIB.", []],
    ["2027-12-09", "fomc", "The Fed: keputusan suku bunga (FOMC 7–8 Des)", "Diumumkan dini hari WIB, disertai proyeksi ekonomi.", []],
    # BLS: CPI dan NFP (Employment Situation) pukul 08:30 waktu New York = 19:30 WIB (20:30 WIB mulai November).
    ["2026-09-04", "nfp", "NFP AS (data lapangan kerja Agustus)", "Dirilis pukul 19.30 WIB; dampaknya di BEI hari bursa berikutnya.", []],
    ["2026-09-11", "cpi", "CPI AS (inflasi Agustus)", "Dirilis pukul 19.30 WIB; dampaknya di BEI hari bursa berikutnya.", []],
    ["2026-10-02", "nfp", "NFP AS (data lapangan kerja September)", "Dirilis pukul 19.30 WIB; dampaknya di BEI hari bursa berikutnya.", []],
    ["2026-10-14", "cpi", "CPI AS (inflasi September)", "Dirilis pukul 19.30 WIB; dampaknya di BEI keesokan harinya.", []],
    ["2026-11-06", "nfp", "NFP AS (data lapangan kerja Oktober)", "Dirilis pukul 20.30 WIB; dampaknya di BEI hari bursa berikutnya.", []],
    ["2026-11-10", "cpi", "CPI AS (inflasi Oktober)", "Dirilis pukul 20.30 WIB; dampaknya di BEI keesokan harinya.", []],
    ["2026-12-04", "nfp", "NFP AS (data lapangan kerja November)", "Dirilis pukul 20.30 WIB; dampaknya di BEI hari bursa berikutnya.", []],
    ["2026-12-10", "cpi", "CPI AS (inflasi November)", "Dirilis pukul 20.30 WIB; dampaknya di BEI keesokan harinya.", []],
    # BPS: inflasi Indonesia biasanya dirilis hari kerja pertama tiap bulan, sekitar pukul 11.00 WIB.
    ["2026-09-01", "inflasi", "Inflasi Indonesia (BPS, data Agustus)", "Dirilis BPS sekitar pukul 11.00 WIB.", []],
    ["2026-10-01", "inflasi", "Inflasi Indonesia (BPS, data September)", "Perkiraan: BPS biasanya merilis di hari kerja pertama bulan, sekitar pukul 11.00 WIB.", []],
    ["2026-11-02", "inflasi", "Inflasi Indonesia (BPS, data Oktober)", "Perkiraan: BPS biasanya merilis di hari kerja pertama bulan, sekitar pukul 11.00 WIB.", []],
    ["2026-12-01", "inflasi", "Inflasi Indonesia (BPS, data November)", "Perkiraan: BPS biasanya merilis di hari kerja pertama bulan, sekitar pukul 11.00 WIB.", []],
]


def muat_agenda():
    """Agenda bawaan + agenda dari kalender.json (kalau ada). Format tiap item kalender.json:
    {"tgl": "2026-11-05", "jenis": "lain", "judul": "...", "ket": "...", "saham": ["BBRI"]}"""
    agenda = [{"tgl": t, "jenis": j, "judul": ju, "ket": k, "saham": sh} for t, j, ju, k, sh in AGENDA_DEFAULT]
    if KALENDER.exists():
        try:
            tambahan = json.loads(KALENDER.read_text(encoding="utf-8"))
            for it in tambahan if isinstance(tambahan, list) else []:
                if isinstance(it, dict) and it.get("tgl") and it.get("judul"):
                    agenda.append({"tgl": str(it["tgl"])[:10], "jenis": str(it.get("jenis", "lain")),
                                   "judul": str(it["judul"]), "ket": str(it.get("ket", "")),
                                   "saham": [str(x).upper() for x in it.get("saham", [])]})
        except Exception as e:
            print(f"  ! kalender.json tidak bisa dibaca: {e}")
    return sorted(agenda, key=lambda a: a["tgl"])


# ─────────────────────────── jam bursa ───────────────────────────
def jam_sesi(d):
    if d.weekday() == 4:  # Jumat
        return dtime(9, 0), dtime(11, 30), dtime(14, 0), dtime(15, 50)
    return dtime(9, 0), dtime(12, 0), dtime(13, 30), dtime(15, 50)


def menit(t):
    return t.hour * 60 + t.minute


def status_pasar(now):
    """(label status, fraksi hari perdagangan yang sudah lewat 0..1)."""
    if now.weekday() >= 5:
        return "Bursa tutup (akhir pekan)", 1.0
    b1, t1, b2, t2 = jam_sesi(now.date())
    m = menit(now.time())
    s1 = menit(t1) - menit(b1)
    s2 = menit(t2) - menit(b2)
    total = s1 + s2
    if m < menit(b1):
        return "Sebelum pembukaan", 1.0
    if m < menit(t1):
        return "Sesi 1 berjalan", max(0.05, (m - menit(b1)) / total)
    if m < menit(b2):
        return "Setelah penutupan Sesi 1", s1 / total
    if m < menit(t2):
        return "Sesi 2 berjalan", (s1 + m - menit(b2)) / total
    if m < 16 * 60:
        return "Pre-closing", 1.0
    return "Setelah closing", 1.0


# ─────────────────────────── ambil data ───────────────────────────
def unduh(tickers, period, interval, chunk=40, mentah=False):
    if mentah:                                   # simbol non-IDX (kurs, komoditas, indeks global) apa adanya
        return _unduh(tickers, period, interval, chunk, threads=True, mentah=True)
    out = _unduh(tickers, period, interval, chunk, threads=True)
    sisa = [t for t in tickers if t not in out]
    if sisa:   # coba ulang yang gagal (mis. 'database is locked' dari cache yfinance atau pembatasan sementara)
        time.sleep(3)
        out.update(_unduh(sisa, period, interval, 20, threads=False))
        sisa = [t for t in tickers if t not in out]
        if 0 < len(sisa) <= 60:            # sisa sedikit: coba satu per satu
            for t in sisa:
                out.update(_unduh([t], period, interval, 1, threads=False))
        elif sisa:
            print(f"  ! {len(sisa)} saham gagal diunduh ({interval}), kemungkinan dibatasi Yahoo. Dicoba lagi di run berikutnya.")
    return out


def _unduh(tickers, period, interval, chunk, threads, mentah=False):
    out = {}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        syms = [t if (mentah or t.startswith("^")) else t + ".JK" for t in part]
        try:
            data = yf.download(syms, period=period, interval=interval, group_by="ticker",
                               auto_adjust=False, threads=threads, progress=False)
        except Exception as e:
            print(f"  ! gagal unduh {interval} batch {i // chunk + 1}: {e}")
            continue
        if data is None or data.empty:
            continue
        for t, sym in zip(part, syms):
            try:
                df = data[sym] if isinstance(data.columns, pd.MultiIndex) else data
                df = df[["Open", "High", "Low", "Close", "Volume"]].dropna(subset=["Close"])
                df = df[df["Close"] > 0]
            except Exception:
                continue
            if len(df):
                out[t] = df.copy()
    return out


def ke_tanggal(df):
    """Index harian -> tanggal polos (tanpa zona waktu) agar bisa disejajarkan."""
    df = df.copy()
    df.index = pd.to_datetime([d.date() for d in df.index])
    return df[~df.index.duplicated(keep="last")]


def muat_daftar():
    """Baca daftar_saham.csv -> ({kode: nama}, {kode: sektor})."""
    nama, sektor = {}, {}
    if DAFTAR.exists():
        df = pd.read_csv(DAFTAR, keep_default_na=False, dtype=str)
        for r in df.itertuples():
            k = r.kode.strip().upper()
            nama[k] = r.nama.strip()
            if r.sektor.strip() and r.sektor.strip() != "-":
                sektor[k] = r.sektor.strip()
    return nama, sektor


SEKTOR_BEI = {
    "barang konsumen primer": "Konsumen Primer", "consumer non-cyclicals": "Konsumen Primer",
    "barang konsumen non-primer": "Konsumen Non-Primer", "consumer cyclicals": "Konsumen Non-Primer",
    "energi": "Energi", "energy": "Energi", "barang baku": "Barang Baku", "basic materials": "Barang Baku",
    "keuangan": "Keuangan", "financials": "Keuangan", "kesehatan": "Kesehatan", "healthcare": "Kesehatan",
    "perindustrian": "Perindustrian", "industrials": "Perindustrian", "infrastruktur": "Infrastruktur",
    "infrastructures": "Infrastruktur", "teknologi": "Teknologi", "technology": "Teknologi",
    "properti & real estat": "Properti & Real Estat", "properties & real estate": "Properti & Real Estat",
    "transportasi & logistik": "Transportasi & Logistik", "transportation & logistic": "Transportasi & Logistik",
}


def _ambil_json(url):
    """GET JSON dari situs BEI. Pakai curl_cffi (ikut terpasang bersama yfinance) agar mirip browser."""
    headers = {"Accept": "application/json, text/plain, */*", "Referer": "https://www.idx.co.id/",
               "Accept-Language": "id-ID,id;q=0.9,en;q=0.8"}
    try:
        from curl_cffi import requests as creq
        r = creq.get(url, headers=headers, impersonate="chrome", timeout=40)
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code}")
        return r.json()
    except ImportError:
        import urllib.request
        req = urllib.request.Request(url, headers={**headers, "User-Agent":
              "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"})
        with urllib.request.urlopen(req, timeout=40) as f:
            return json.loads(f.read().decode("utf-8"))


def _ambil_field(row, *keys):
    low = {str(k).lower(): v for k, v in row.items()}
    for k in keys:
        v = low.get(k.lower())
        if v not in (None, ""):
            return str(v).strip()
    return ""


def perbarui_daftar(paksa=False, hari=7):
    """Perbarui daftar_saham.csv dari situs resmi BEI (maks. sekali per `hari` hari).
    Kalau gagal atau hasilnya janggal, daftar lama tetap dipakai."""
    info = {}
    if DAFTAR_INFO.exists():
        try:
            info = json.loads(DAFTAR_INFO.read_text(encoding="utf-8"))
        except Exception:
            info = {}
    hari_ini = datetime.now(WIB).date()
    terakhir = info.get("dicoba") or info.get("diperbarui")
    if not paksa and terakhir:
        try:
            jeda = hari if info.get("status") == "ok" else 1   # gagal -> coba lagi besok
            if (hari_ini - datetime.strptime(terakhir, "%Y-%m-%d").date()).days < jeda:
                return
        except ValueError:
            pass

    print("  Memeriksa daftar emiten terbaru di situs BEI...")
    lama_nama, lama_sektor = muat_daftar()
    baru, sumber, err = {}, "", ""
    sumber_url = [
        "https://www.idx.co.id/primary/ListedCompany/GetCompanyProfiles?emitenType=s&start=0&length=9999",
        "https://www.idx.co.id/primary/StockData/GetSecuritiesStock?start=0&length=9999&code=&sector=&board=&language=id-id",
    ]
    for url in sumber_url:
        try:
            js = _ambil_json(url)
            rows = (js.get("data") or js.get("Data") or []) if isinstance(js, dict) else js
            for row in rows or []:
                kode = _ambil_field(row, "KodeEmiten", "Kode_Emiten", "Code", "Kode").upper()
                if not kode or not kode.isalnum() or len(kode) > 5:
                    continue
                nama = _ambil_field(row, "NamaEmiten", "Nama_Emiten", "Name", "Nama")
                sek = SEKTOR_BEI.get(_ambil_field(row, "Sektor", "Sector").lower(), "")
                baru[kode] = (nama, sek)
            if len(baru) >= 600:
                sumber = url.split("/primary/")[1].split("?")[0]
                break
            err = f"hanya {len(baru)} emiten"
        except Exception as e:
            err = str(e)[:120]
        baru = {}

    info["dicoba"] = hari_ini.isoformat()
    if not baru:
        print(f"  ! Tidak bisa ambil daftar dari BEI ({err}). Memakai daftar yang ada ({len(lama_nama)} emiten).")
        info["status"] = f"gagal: {err}"
        DAFTAR_INFO.write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
        return

    rows = []
    for kode in sorted(baru):
        nama, sek = baru[kode]
        rows.append({"kode": kode, "nama": nama or lama_nama.get(kode, ""),
                     "sektor": sek or lama_sektor.get(kode, "-") or "-"})
    tambah = sorted(set(baru) - set(lama_nama))
    hilang = sorted(set(lama_nama) - set(baru))
    pd.DataFrame(rows).to_csv(DAFTAR, index=False)
    info.update({"diperbarui": hari_ini.isoformat(), "status": "ok", "sumber": sumber, "jumlah": len(rows),
                 "baru": tambah[:50], "hilang": hilang[:50]})
    DAFTAR_INFO.write_text(json.dumps(info, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"  Daftar emiten diperbarui dari BEI: {len(rows)} emiten"
          + (f", {len(tambah)} baru ({', '.join(tambah[:8])}{'...' if len(tambah) > 8 else ''})" if tambah else "")
          + (f", {len(hilang)} tidak ada lagi" if hilang else "") + ".")


def ambil_sektor(tickers, sektor_daftar, maks_baru=30):
    """Sektor dari daftar resmi; yang belum ada dilengkapi dari Yahoo (maks 30 per run, disimpan)."""
    cache = {}
    if CACHE_SEKTOR.exists():
        try:
            cache = json.loads(CACHE_SEKTOR.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    kurang = [t for t in tickers if t not in sektor_daftar and t not in cache][:maks_baru]
    for t in kurang:
        try:
            info = yf.Ticker(t + ".JK").info or {}
            cache[t] = info.get("sector") or "-"
        except Exception:
            pass   # gagal (mis. rate limit) -> dicoba lagi di run berikutnya
    CACHE_SEKTOR.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    yahoo_ke_bei = {"basic materials": "Barang Baku", "energy": "Energi", "financial services": "Keuangan",
                    "consumer cyclical": "Konsumen Non-Primer", "consumer defensive": "Konsumen Primer",
                    "healthcare": "Kesehatan", "industrials": "Perindustrian", "real estate": "Properti & Real Estat",
                    "technology": "Teknologi", "communication services": "Infrastruktur", "utilities": "Infrastruktur"}
    return {t: sektor_daftar.get(t) or yahoo_ke_bei.get(str(cache.get(t, "-")).lower(), cache.get(t, "-"))
            for t in tickers}


def sma(s, n):
    return s.rolling(n).mean()


def ema(s, n):
    return s.ewm(span=n, adjust=False, min_periods=n).mean()


def rsi(c, n=14):
    d = c.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False, min_periods=n).mean()
    rs = up / dn.replace(0, np.nan)
    out = 100 - 100 / (1 + rs)
    return out.where(dn != 0, 100.0)


def fin(x):
    return x is not None and not (isinstance(x, float) and math.isnan(x)) and np.isfinite(x)


def verdict(x):
    if x > 0.5:
        return "Strong Buy"
    if x > 0.1:
        return "Buy"
    if x < -0.5:
        return "Strong Sell"
    if x < -0.1:
        return "Sell"
    return "Neutral"


def rating(df):
    """Ringkasan teknikal ala 'technical summary': Moving Averages + 6 oscillator."""
    if df is None or len(df) < 20:
        return None
    df = df.iloc[-320:]
    c, h, l = df["Close"], df["High"], df["Low"]
    last = c.iloc[-1]

    mb = ms = mt = 0
    for n in (5, 10, 20, 30, 50, 100, 200):
        if len(c) >= n + 1:
            for v in (sma(c, n).iloc[-1], ema(c, n).iloc[-1]):
                if fin(v):
                    mt += 1
                    mb += last > v
                    ms += last < v

    votes = []
    r = rsi(c).iloc[-1]
    if fin(r):
        votes.append(1 if r < 30 else -1 if r > 70 else 0)
    ll, hh = l.rolling(14).min(), h.rolling(14).max()
    k = (100 * (c - ll) / (hh - ll).replace(0, np.nan)).rolling(3).mean().iloc[-1]
    if fin(k):
        votes.append(1 if k < 20 else -1 if k > 80 else 0)
    macd = ema(c, 12) - ema(c, 26)
    sig = macd.ewm(span=9, adjust=False).mean()
    if fin(macd.iloc[-1]) and fin(sig.iloc[-1]):
        votes.append(1 if macd.iloc[-1] > sig.iloc[-1] else -1)
    tp = ((h + l + c) / 3).iloc[-20:]
    cci = np.nan
    if len(tp) == 20:
        mad = float(np.mean(np.abs(tp - tp.mean())))
        cci = (tp.iloc[-1] - tp.mean()) / (0.015 * mad) if mad > 0 else np.nan
    if fin(cci):
        votes.append(1 if cci < -100 else -1 if cci > 100 else 0)
    wr = (-100 * (hh - c) / (hh - ll).replace(0, np.nan)).iloc[-1]
    if fin(wr):
        votes.append(1 if wr < -80 else -1 if wr > -20 else 0)
    if len(c) > 11:
        mom = c.iloc[-1] - c.iloc[-11]
        votes.append(1 if mom > 0 else -1 if mom < 0 else 0)

    ib, is_, it = votes.count(1), votes.count(-1), len(votes)
    xm = (mb - ms) / mt if mt else 0
    xi = (ib - is_) / it if it else 0
    xs = (xm + xi) / 2 if mt and it else (xm or xi)
    return {
        "ma": verdict(xm), "ind": verdict(xi), "summary": verdict(xs),
        "ma_detail": f"{mb} Buy / {ms} Sell dari {mt} MA",
        "ind_detail": f"{ib} Buy / {is_} Sell dari {it} indikator",
    }


def resample(df, rule):
    agg = {"Open": "first", "High": "max", "Low": "min", "Close": "last", "Volume": "sum"}
    return df.resample(rule).agg(agg).dropna(subset=["Close"])


def bulanan(df):
    try:
        return resample(df, "ME")
    except Exception:
        return resample(df, "M")


def gabung_jam(df, n):
    """Gabungkan candle 1 jam jadi n-jam, dihitung per hari bursa (tidak nyambung antar hari)."""
    if df is None or df.empty or n == 1:
        return df
    g = df.copy()
    tgl = pd.Series([d.date() for d in g.index], index=g.index)
    g["_b"] = g.groupby(tgl.values).cumcount() // n
    g["_d"] = tgl.values
    g["_ts"] = g.index
    agg = g.groupby(["_d", "_b"], sort=True).agg(
        Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
        Close=("Close", "last"), Volume=("Volume", "sum"), _ts=("_ts", "first"))
    return agg.set_index("_ts")


def pola_candle(df):
    """Pola bullish pada candle TERAKHIR df (Bullish Engulfing / Hammer / Bullish Marubozu) atau None."""
    if len(df) < 7:
        return None
    o, h, l, c = (df[k].iloc[-1] for k in ("Open", "High", "Low", "Close"))
    po, pc = df["Open"].iloc[-2], df["Close"].iloc[-2]
    rng = (h - l) or 1e-9
    body = abs(c - o)
    turun_sebelumnya = df["Close"].iloc[-2] < df["Close"].iloc[-7]
    if pc < po and c > o and c >= po and o <= pc and body > abs(pc - po):
        return "Bullish Engulfing"
    lower, upper = min(o, c) - l, h - max(o, c)
    if turun_sebelumnya and body > 0 and lower >= 2 * body and upper <= max(body * 0.6, rng * 0.1):
        return "Hammer"
    if c > o and body >= 0.85 * rng and body / o > 0.02:
        return "Bullish Marubozu"
    return None


def pola_dengan_konfirmasi(d):
    """(nama_pola, status, high_pola). status 'tunggu' = baru muncul hari ini,
    'ok' = muncul kemarin dan hari ini candle hijau tutup di atas high pola."""
    p_now = pola_candle(d)
    if p_now:
        return p_now, "tunggu", float(d["High"].iloc[-1])
    p_prev = pola_candle(d.iloc[:-1])
    if p_prev:
        hi_prev = float(d["High"].iloc[-2])
        o, c = d["Open"].iloc[-1], d["Close"].iloc[-1]
        if c > o and c > hi_prev:
            return p_prev, "ok", hi_prev
    return None, None, None


def atr(d, n=14):
    h, l, c = d["High"], d["Low"], d["Close"]
    tr = pd.concat([h - l, (h - c.shift()).abs(), (l - c.shift()).abs()], axis=1).max(axis=1)
    return float(tr.ewm(alpha=1 / n, adjust=False, min_periods=n).mean().iloc[-1])


def fraksi(harga):
    """Fraksi harga (tick) saham BEI."""
    if harga < 200:
        return 1
    if harga < 500:
        return 2
    if harga < 2000:
        return 5
    if harga < 5000:
        return 10
    return 25


def bulat_bawah(x):
    t = fraksi(x)
    return int(math.floor(x / t) * t)


def bulat_atas(x):
    t = fraksi(x)
    return int(math.ceil(x / t) * t)


def rupiah(x):
    return f"{int(round(x)):,}".replace(",", ".")


def analisa(t, d, ihsg_ret, sektor, nama, frac_hari, hari_ini):
    c, v = d["Close"], d["Volume"]
    if len(d) < 30:
        return None
    last = float(c.iloc[-1])
    prev = float(c.iloc[-2])
    if last <= 0 or prev <= 0:
        return None
    parsial = d.index[-1].date() == hari_ini and frac_hari < 1.0

    ma20, ma50, ma200 = sma(c, 20).iloc[-1], sma(c, 50).iloc[-1], sma(c, 200).iloc[-1]
    conds = [last > ma20, fin(ma50) and ma20 > ma50, fin(ma200) and ma50 > ma200, fin(ma200) and last > ma200]
    trend = 25 * sum(bool(x) for x in conds)
    trend_ok = bool(fin(ma200) and ma20 > ma50 > ma200 and last > ma20)

    hi20 = float(d["High"].iloc[-21:-1].max())
    vavg = float(v.iloc[-21:-1].mean()) or 1.0
    vol_now = float(v.iloc[-1]) / (frac_hari if parsial else 1.0)   # proyeksi volume full-day
    vr = vol_now / vavg
    brk = 0
    if last > hi20:
        brk += 60
    elif last >= hi20 * 0.98:
        brk += 30
    brk += 40 if vr >= 1.5 else 20 if vr >= 1.0 else 0
    brk_ok = bool(last > hi20 and vr >= 1.5)

    pattern, pk, ph = pola_dengan_konfirmasi(d)
    o, hh, ll = d["Open"].iloc[-1], d["High"].iloc[-1], d["Low"].iloc[-1]
    posisi = (last - ll) / ((hh - ll) or 1e-9)
    if pattern and pk == "ok":
        pa = 100
    elif pattern:
        pa = 70          # pola baru muncul, belum terkonfirmasi
    elif last > o and posisi >= 0.7:
        pa = 60
    elif last > o:
        pa = 40
    elif abs(last - o) <= 0.1 * ((hh - ll) or 1e-9):
        pa = 25
    else:
        pa = 10

    r = rsi(c).iloc[-1]
    r = float(r) if fin(r) else 50.0
    if 50 <= r <= 70:
        mom = 100
    elif 70 < r <= 80:
        mom = 60
    elif 40 <= r < 50:
        mom = 50
    elif r > 80:
        mom = 30
    elif r < 30:
        mom = 40
    else:
        mom = 30

    nilai = (d["Close"] * d["Volume"]).iloc[-21:-1].mean()
    # Vol 1D/10D: nilai transaksi hari ini (diproyeksikan saat sesi berjalan) / rata-rata 10 hari sebelumnya
    avg10 = (d["Close"] * d["Volume"]).iloc[-11:-1].mean()
    hari_ini_val = float(d["Close"].iloc[-1] * d["Volume"].iloc[-1]) / (frac_hari if parsial else 1.0)
    v10 = round(hari_ini_val / avg10, 2) if fin(avg10) and avg10 > 0 and fin(hari_ini_val) else None
    try:
        ind = sinyal_harian(d)
    except Exception:
        ind = {}

    beta = None
    if ihsg_ret is not None:
        ret = c.pct_change()
        j = pd.concat([ret, ihsg_ret], axis=1, join="inner").dropna().iloc[-250:]
        if len(j) >= 60 and j.iloc[:, 1].var() > 0:
            beta = round(float(j.iloc[:, 0].cov(j.iloc[:, 1]) / j.iloc[:, 1].var()), 2)

    tf = {"daily": rating(d), "weekly": rating(resample(d, "W-FRI")), "monthly": rating(bulanan(d))}
    tf = {k: x for k, x in tf.items() if x}


    tail = d.iloc[-30:]
    return {
        "t": t, "nm": nama.get(t, ""), "p": round(last, 0 if last >= 50 else 2), "chg": round((last / prev - 1) * 100, 2),
        "val": float(nilai) if fin(nilai) else 0.0,
        "trend": trend, "brk": brk, "pa": pa, "mom": mom,
        "trendOk": trend_ok, "brkOk": brk_ok, "pattern": pattern, "pk": pk,
        "rsi": round(r, 1), "vr": round(vr, 2), "tf": tf,
        "vday": float(d["Close"].iloc[-1] * d["Volume"].iloc[-1]) if fin(d["Close"].iloc[-1] * d["Volume"].iloc[-1]) else 0.0,
        "v10": v10,
        "ind": ind,
        "ohlc": [[round(float(a), 0 if last >= 50 else 2) for a in row] for row in tail[["Open", "High", "Low", "Close"]].values],
        "sector": sektor.get(t, "-"), "beta": beta,
        "tgl": d.index[-1].strftime("%Y-%m-%d"),
        "x": {"m20": [None if not fin(v) else round(float(v), 1) for v in sma(c, 20).iloc[-30:]],
              "m50": [None if not fin(v) else round(float(v), 1) for v in sma(c, 50).iloc[-30:]],
              "ma200": round(float(ma200), 1) if fin(ma200) else None, "hi20": round(hi20, 1),
              "m20l": round(float(ma20), 1) if fin(ma20) else None, "atr": round(atr(d), 2)},
        "_ma20": float(ma20) if fin(ma20) else None, "_atr": atr(d), "_ph": ph, "_d": d,
    }


def musim_ihsg(d):
    """Statistik musiman IHSG dari data harian (idealnya 10 tahun): per hari, posisi awal/akhir bulan, dan per bulan."""
    if d is None or len(d) < 500:
        return None
    c = d["Close"].astype(float)
    ret = c.pct_change().dropna()
    ret = ret[ret.abs() < 0.2]                       # buang data janggal
    st = lambda x: {"n": int(len(x)), "up": int((x > 0).sum()), "avg": round(float(x.mean()) * 100, 3)}
    out = {"dari": ret.index[0].strftime("%Y-%m-%d"), "sampai": ret.index[-1].strftime("%Y-%m-%d"),
           "wd": [st(ret[ret.index.dayofweek == i]) for i in range(5)], "tom": {}}
    per = ret.index.to_period("M")
    pos = pd.Series(range(len(ret)), index=ret.index).groupby(per).cumcount() + 1
    rev = pd.Series(range(len(ret)), index=ret.index)[::-1].groupby(per[::-1]).cumcount()[::-1] + 1
    for k in (1, 2, 3):
        out["tom"][f"f{k}"] = st(ret[pos.values == k])
        out["tom"][f"l{k}"] = st(ret[rev.values == k])
    m = c.resample("ME").last() if hasattr(c, "resample") else c
    mret = m.pct_change().dropna()
    out["mon"] = [st(mret[mret.index.month == i]) for i in range(1, 13)]
    return out


MAKRO_LIST = [
    ("IDR=X", "USD/IDR", "Kurs rupiah. Naik = rupiah melemah, biasanya menekan saham importir dan memicu jual asing."),
    ("DX-Y.NYB", "Indeks Dolar AS (DXY)", "Kekuatan dolar terhadap mata uang utama. Dolar menguat sering berarti tekanan bagi pasar negara berkembang."),
    ("^TNX", "Yield obligasi AS 10 tahun (%)", "Naik = biaya dana global lebih mahal; sering membuat asing keluar dari pasar negara berkembang."),
    ("GC=F", "Emas (USD/oz)", "Harga emas dunia per troy ounce. Aset aman; berpengaruh ke saham emas seperti ANTM, MDKA, BRMS, EMAS."),
    ("CL=F", "Minyak WTI (USD/barel)", "Berpengaruh ke saham energi seperti MEDC, ENRG, AKRA, dan ke inflasi."),
    ("MTF=F", "Batubara Rotterdam (USD/ton)", "Acuan harga batubara Eropa. Pembanding untuk saham batubara seperti PTBA, ITMG, ADRO, AADI."),
    ("HG=F", "Tembaga (USD/lb)", "Indikator permintaan industri global. Berpengaruh ke MDKA, AMMN."),
    ("^GSPC", "S&P 500", "Bursa saham AS, penentu arah sentimen global."),
    ("^HSI", "Hang Seng", "Bursa Hong Kong, cerminan sentimen Asia dan Tiongkok."),
]


def data_makro(ihsg):
    """Harga 1 tahun terakhir indikator pasar global dan makro dari Yahoo, plus korelasi 60 hari dengan IHSG."""
    got = unduh([s for s, _, _ in MAKRO_LIST], "1y", "1d", mentah=True)
    ih = ke_tanggal(ihsg)["Close"].pct_change() if ihsg is not None else None
    daftar = list(MAKRO_LIST)
    # emas dunia dalam rupiah per gram = USD/oz x USD/IDR / 31,1035 (tanggal yang sama)
    if got.get("GC=F") is not None and got.get("IDR=X") is not None:
        g, k = ke_tanggal(got["GC=F"])["Close"], ke_tanggal(got["IDR=X"])["Close"]
        j = pd.concat([g, k], axis=1, join="inner").dropna()
        if len(j) >= 30:
            v = j.iloc[:, 0] * j.iloc[:, 1] / 31.1035
            got["EMAS_IDR"] = pd.DataFrame({"Open": v, "High": v, "Low": v, "Close": v, "Volume": 0.0})
            pos = next(i for i, x in enumerate(daftar) if x[0] == "GC=F") + 1
            daftar.insert(pos, ("EMAS_IDR", "Emas (Rp/gram)",
                                "Harga emas dunia dirupiahkan: USD/oz × kurs USD/IDR ÷ 31,1035. Bukan harga emas batangan Antam/Pegadaian, yang biasanya lebih tinggi karena ongkos cetak, margin, dan pajak. Naik bisa karena emas dunia naik, rupiah melemah, atau keduanya."))
    out = []
    for sym, nama, ket in daftar:
        df = got.get(sym)
        if df is None or len(df) < 30:
            continue
        df = ke_tanggal(df)
        c = df["Close"].astype(float)
        dec = 0 if sym == "EMAS_IDR" else (3 if c.iloc[-1] < 20 else 2)
        korel = None
        if ih is not None:
            j = pd.concat([c.pct_change(), ih], axis=1, join="inner").dropna().iloc[-60:]
            if len(j) >= 30:
                korel = round(float(j.iloc[:, 0].corr(j.iloc[:, 1])), 2)
        d0 = c.index[0]
        out.append({"sym": sym, "nama": nama, "ket": ket, "dec": dec, "d0": d0.strftime("%Y-%m-%d"),
                    "do": [(t - d0).days for t in c.index], "c": [round(float(x), dec) for x in c],
                    "korel": korel})
    return out


def analisa_emas():
    """Emas dunia dalam Rp/gram sebagai 'aset' lengkap: OHLC = emas USD/oz x kurs USD/IDR / 31,1035,
    volume = volume kontrak emas dunia. Dipakai halaman analisa emas (SMC, Fibo, volume profile, rencana)."""
    got = unduh(["GC=F", "IDR=X"], "2y", "1d", mentah=True)
    g, k = got.get("GC=F"), got.get("IDR=X")
    if g is None or k is None:
        return None, None
    g, k = ke_tanggal(g), ke_tanggal(k)
    j = g.join(k[["Close"]].rename(columns={"Close": "K"}), how="inner").dropna(subset=["Close", "K"])
    if len(j) < 150:
        return None, None
    f = j["K"] / 31.1035
    df = pd.DataFrame({c: j[c] * f for c in ("Open", "High", "Low", "Close")})
    df["Volume"] = j["Volume"].fillna(0) * 100          # pak_ohlcv membagi 100, jadi angka tampil = jumlah kontrak
    sm = smc(df)
    if not sm:
        return None, None
    c = df["Close"]
    r = {"t": "XAUIDR", "nm": "Emas dunia (Rp/gram)", "p": round(float(c.iloc[-1])),
         "chg": round(float(c.iloc[-1] / c.iloc[-2] - 1) * 100, 2), "tgl": df.index[-1].strftime("%Y-%m-%d"),
         "smc": sm, "_atr": atr(df), "_ma20": float(c.iloc[-20:].mean()), "vu": "kontrak"}
    e = sm["ev"][-1] if sm["ev"] else None
    r["ms"] = {"d": {"tr": sm["tr"], "ev": [e[3], e[4], e[5]] if e else None}}
    sw = struktur_ringkas(resample(df, "W-FRI"), L=3)
    if sw:
        r["ms"]["w"] = sw
    plans = {"K": rencana_konf(r), "S": rencana_struktur(r, "ok"), "A": rencana(r, "ok")}
    r["plans"] = {kk: v for kk, v in plans.items() if v}
    best = next((kk for kk in ("K", "S", "A") if plans[kk]), None)
    r["plan"] = dict(plans[best], src=best) if best else None
    tfd = {kk: v for kk, v in (("1d", pak_ohlcv(df, 430)), ("1w", pak_ohlcv(resample(df, "W-FRI"), 280))) if v}
    r["tfx"] = sorted(tfd)
    for kk in ("_atr", "_ma20"):
        r.pop(kk, None)
    return r, tfd


def konteks_pasar(ihsg, rows, ihsg_jam=None, ihsg_panjang=None):
    """Ringkasan IHSG + napas pasar (persentase saham likuid di atas MA20)."""
    m = {"ihsg": None, "breadth": None}
    if ihsg is not None and len(ihsg) > 60:
        c = ihsg["Close"]
        rt = rating(ihsg) or {}
        m20, m50, m200 = sma(c, 20).iloc[-1], sma(c, 50).iloc[-1], sma(c, 200).iloc[-1]
        r = rsi(c).iloc[-1]
        m["ihsg"] = {"p": round(float(c.iloc[-1]), 2), "chg": round((c.iloc[-1] / c.iloc[-2] - 1) * 100, 2),
                     "ma20": round(float(m20), 2), "ma50": round(float(m50), 2),
                     "ma200": round(float(m200), 2) if fin(m200) else None,
                     "rsi": round(float(r), 1) if fin(r) else None, "d": rt.get("summary", "Neutral"),
                     "ohlc": [[round(float(a), 2) for a in row] for row in ihsg[["Open", "High", "Low", "Close"]].iloc[-30:].values]}
        tf = {"daily": rt or None, "weekly": rating(resample(ihsg, "W-FRI")), "monthly": rating(bulanan(ihsg))}
        if ihsg_jam is not None and len(ihsg_jam) >= 20:
            tf.update({"h1": rating(ihsg_jam), "h2": rating(gabung_jam(ihsg_jam, 2)), "h4": rating(gabung_jam(ihsg_jam, 4))})
        m["ihsg"]["tf"] = {k: v for k, v in tf.items() if v}
        m["ihsg"]["tgl"] = ihsg.index[-1].strftime("%Y-%m-%d")
        try:
            m["ihsg"]["smc"] = smc(ihsg)
            ms = {}
            if m["ihsg"]["smc"]:
                e = m["ihsg"]["smc"]["ev"][-1] if m["ihsg"]["smc"]["ev"] else None
                ms["d"] = {"tr": m["ihsg"]["smc"]["tr"], "ev": [e[3], e[4], e[5]] if e else None}
            sw = struktur_ringkas(resample(ihsg, "W-FRI"), L=3)
            if sw:
                ms["w"] = sw
            if ihsg_jam is not None and len(ihsg_jam) >= 40:
                s4 = struktur_ringkas(gabung_jam(ihsg_jam, 4), L=3)
                if s4:
                    ms["h4"] = s4
            m["ihsg"]["ms"] = ms
        except Exception as e:
            print(f"  ! smc IHSG: {e}")
    try:
        m["musim"] = musim_ihsg(ihsg_panjang if ihsg_panjang is not None else ihsg)
    except Exception as e:
        print(f"  ! musim IHSG: {e}")
    try:
        print("  Unduh data pasar global & makro...")
        m["makro"] = data_makro(ihsg)
    except Exception as e:
        print(f"  ! makro: {e}")
    likuid = [r for r in rows if r["val"] >= 1e9 and r["x"].get("m20l")]
    if likuid:
        naik = sum(1 for r in likuid if r["p"] > r["x"]["m20l"])
        m["breadth"] = {"pct": round(naik / len(likuid) * 100), "n": len(likuid)}
    return m


def smc(d, L=5, win=220, ctx=420):
    """Smart Money Concepts (versi sederhana) pada candle harian.
    Menghasilkan struktur BOS/CHoCH, order block & FVG yang belum termitigasi,
    equal highs/lows, dan range premium/discount untuk `win` candle terakhir."""
    d = d.iloc[-ctx:]
    n = len(d)
    if n < 60:
        return None
    win = min(win, n)          # saham dengan riwayat pendek (IPO baru): pakai semua candle yang ada
    o, h, l, c = (d[k].to_numpy(float) for k in ("Open", "High", "Low", "Close"))
    tgl = [x.strftime("%Y-%m-%d") for x in d.index]
    a = atr(d) or (np.nanmean(h - l) or 1.0)
    rp = (lambda x: round(float(x))) if c[-1] >= 50 else (lambda x: round(float(x), 2))

    piv_h = [i for i in range(L, n - L) if h[i] >= h[i - L:i + L + 1].max() and h[i] > h[i - L:i].max()]
    piv_l = [i for i in range(L, n - L) if l[i] <= l[i - L:i + L + 1].min() and l[i] < l[i - L:i].min()]
    konf_h = {i + L: i for i in piv_h}
    konf_l = {i + L: i for i in piv_l}

    last_h = last_l = None
    tren, ev, obs = 0, [], []
    for i in range(n):
        if i in konf_h:
            last_h = [konf_h[i], h[konf_h[i]], False]
        if i in konf_l:
            last_l = [konf_l[i], l[konf_l[i]], False]
        if last_h and not last_h[2] and c[i] > last_h[1]:
            ev.append((last_h[0], i, last_h[1], "CHoCH" if tren == -1 else "BOS", 1))
            tren, last_h[2] = 1, True
            seg = range(last_h[0], i)
            k = next((j for j in reversed(seg) if c[j] < o[j]), None)
            if k is None:
                k = min(seg, key=lambda j: l[j])
            obs.append([k, h[k], l[k], 1, False])
        if last_l and not last_l[2] and c[i] < last_l[1]:
            ev.append((last_l[0], i, last_l[1], "CHoCH" if tren == 1 else "BOS", -1))
            tren, last_l[2] = -1, True
            seg = range(last_l[0], i)
            k = next((j for j in reversed(seg) if c[j] > o[j]), None)
            if k is None:
                k = max(seg, key=lambda j: h[j])
            obs.append([k, h[k], l[k], -1, False])
        for ob in obs:
            if not ob[4] and ob[0] < i:
                if (ob[3] == 1 and c[i] < ob[2]) or (ob[3] == -1 and c[i] > ob[1]):
                    ob[4] = True

    fvg = []
    for i in range(2, n):
        if l[i] > h[i - 2] and l[i] - h[i - 2] > 0.15 * a:
            fvg.append([i - 1, l[i], h[i - 2], 1])
        elif h[i] < l[i - 2] and l[i - 2] - h[i] > 0.15 * a:
            fvg.append([i - 1, l[i - 2], h[i], -1])
    fvg = [g for g in fvg if not (
        (g[3] == 1 and g[0] + 2 < n and l[g[0] + 2:].min() <= g[2]) or
        (g[3] == -1 and g[0] + 2 < n and h[g[0] + 2:].max() >= g[1]))]

    eq = []
    for arr, src, nama in ((piv_h, h, "EQH"), (piv_l, l, "EQL")):
        for p1, p2 in zip(arr, arr[1:]):
            if abs(src[p1] - src[p2]) <= 0.1 * a:
                eq.append((p1, p2, (src[p1] + src[p2]) / 2, nama))

    s0 = n - win
    cl = lambda i: max(0, i - s0)

    # volume profile 220 candle terakhir (sama dengan rentang chart): volume tiap candle dibagi rata ke rentang high-low-nya
    vp = None
    if "Volume" in d:
        v = d["Volume"].to_numpy(float)
        vlo, vhi, nb = l[s0:].min(), h[s0:].max(), 24
        if vhi > vlo and np.nansum(v[s0:]) > 0:
            edges = np.linspace(vlo, vhi, nb + 1)
            bins = np.zeros(nb)
            for i in range(s0, n):
                a0 = int(np.clip((l[i] - vlo) / (vhi - vlo) * nb, 0, nb - 1))
                a1 = int(np.clip((h[i] - vlo) / (vhi - vlo) * nb, 0, nb - 1))
                bins[a0:a1 + 1] += (v[i] if np.isfinite(v[i]) else 0) / (a1 - a0 + 1)
            poc = int(bins.argmax())
            lo_i = hi_i = poc
            tot, acc = bins.sum(), bins[poc]
            while acc < 0.7 * tot and (lo_i > 0 or hi_i < nb - 1):
                nxt_lo = bins[lo_i - 1] if lo_i > 0 else -1
                nxt_hi = bins[hi_i + 1] if hi_i < nb - 1 else -1
                if nxt_hi >= nxt_lo:
                    hi_i += 1; acc += bins[hi_i]
                else:
                    lo_i -= 1; acc += bins[lo_i]
            mx = bins.max() or 1
            vp = {"b": [int(round(x / mx * 100)) for x in bins], "lo": rp(vlo), "hi": rp(vhi),
                  "poc": rp((edges[poc] + edges[poc + 1]) / 2), "vah": rp(edges[hi_i + 1]), "val": rp(edges[lo_i])}

    def volume_tinggi(top, bot):
        if not vp:
            return 0
        if bot <= vp["vah"] and top >= vp["val"]:
            return 1
        return 0
    ev_out = [[cl(a1), b1 - s0, rp(pr), t, dr, tgl[b1]] for a1, b1, pr, t, dr in ev if b1 >= s0][-8:]
    ob_aktif = [ob for ob in obs if not ob[4]]
    ob_out = ([[cl(k), rp(t_), rp(b_), dr, volume_tinggi(t_, b_)] for k, t_, b_, dr, _ in ob_aktif if dr == 1][-3:] +
              [[cl(k), rp(t_), rp(b_), dr, volume_tinggi(t_, b_)] for k, t_, b_, dr, _ in ob_aktif if dr == -1][-3:])
    fvg_out = ([[cl(i), rp(t_), rp(b_), dr] for i, t_, b_, dr in fvg if dr == 1][-3:] +
               [[cl(i), rp(t_), rp(b_), dr] for i, t_, b_, dr in fvg if dr == -1][-3:])
    eq_out = [[cl(p1), p2 - s0, rp(pr), nm] for p1, p2, pr, nm in eq if p2 >= s0][-4:]
    try:
        kf = _konfluensi(o, h, l, c, d["Volume"].to_numpy(float) if "Volume" in d else None,
                         piv_l, ev, obs, fvg, eq, a, s0)
    except Exception as e:
        kf = {"lay": False, "alasan": f"Gagal dihitung: {e}"}
    return {
        "kf": kf,
        "b": [[rp(v) for v in row] for row in d[["Open", "High", "Low", "Close"]].iloc[-win:].values],
        "v": ([int(round(x / 100)) if np.isfinite(x) else 0 for x in d["Volume"].iloc[-win:].to_numpy(float)]
              if "Volume" in d else None),        # volume harian dalam lot
        "d0": tgl[s0], "d1": tgl[-1],
        "do": [(x - d.index[s0]).days for x in d.index[s0:]],
        "ev": ev_out, "ob": ob_out, "fvg": fvg_out, "eq": eq_out,
        "pd": [rp(h[s0:].max()), rp(l[s0:].min())], "tr": tren, "vp": vp,
    }


def _konfluensi(o, h, l, c, v, piv_l, ev, obs, fvg, eq, a, s0):
    """Setup pullback berbasis konfluensi: dorongan naik terakhir (dari BOS/CHoCH naik) ditarik Fibonacci,
    lalu dicari harga di zona 0,5–0,786 yang paling banyak ditumpuki faktor lain."""
    n = len(c)
    price = float(c[-1])
    if not ev or ev[-1][4] != 1:
        return {"lay": False, "alasan": "Struktur harian belum bullish (BOS/CHoCH terakhir bukan ke atas)."}
    brk = ev[-1][1]
    pls = [pp for pp in piv_l if pp < brk]
    start = pls[-1] if pls else max(0, brk - 40) + int(np.argmin(l[max(0, brk - 40):brk + 1]))
    hi_idx = brk + int(np.argmax(h[brk:]))
    m_idx = start + int(np.argmin(l[start:hi_idx + 1]))
    if l[m_idx] < l[start]:
        start = m_idx
    lo, hi = float(l[start]), float(h[hi_idx])
    rng = hi - lo
    if rng < 2 * a:
        return {"lay": False, "alasan": "Dorongan naik terakhir terlalu kecil untuk ditarik Fibonacci."}
    if price < lo:
        return {"lay": False, "alasan": "Harga sudah di bawah awal dorongan naik; struktur naiknya rusak."}
    fib = {r: hi - r * rng for r in (0, 0.382, 0.5, 0.618, 0.705, 0.786, 0.886, 1)}
    zlo, zhi = fib[0.786], fib[0.5]
    NB = 24
    edges = np.linspace(lo, hi, NB + 1)
    bins = np.zeros(NB)
    vv = np.nan_to_num(v, nan=0.0) if v is not None else np.zeros(n)
    for i in range(start, hi_idx + 1):
        a0 = int(np.clip((l[i] - lo) / rng * NB, 0, NB - 1))
        a1 = int(np.clip((h[i] - lo) / rng * NB, 0, NB - 1))
        bins[a0:a1 + 1] += vv[i] / (a1 - a0 + 1)
    pi = int(bins.argmax())
    poc = (edges[pi] + edges[pi + 1]) / 2
    bmax = bins.max() or 1
    bin_of = lambda p: int(np.clip((p - lo) / rng * NB, 0, NB - 1))
    ma20 = float(np.mean(c[-20:]))
    ma50 = float(np.mean(c[-50:])) if n >= 50 else None
    tol = 0.25 * a
    ob_b = [ob for ob in obs if not ob[4] and ob[3] == 1]
    fvg_b = [g for g in fvg if g[3] == 1]
    eql = [x for x in eq if x[3] == "EQL"]

    def faktor(pr):
        return {
            "fibo": any(abs(pr - fib[r]) <= tol for r in (0.5, 0.618, 0.705, 0.786)),
            "volume": abs(pr - poc) <= tol or bins[bin_of(pr)] >= 0.7 * bmax,
            "ob": any(ob[2] - tol <= pr <= ob[1] + tol for ob in ob_b),
            "fvg": any(g[2] - tol <= pr <= g[1] + tol for g in fvg_b),
            "ma": any(m is not None and abs(pr - m) <= 1.5 * tol for m in (ma20, ma50)),
            "tren": True,
        }
    grid = np.linspace(zlo, zhi, 41)
    best = max(grid, key=lambda pr: (sum(faktor(pr).values()), pr))
    fk = faktor(best)
    skor = int(sum(fk.values()))
    e1, e2 = best - 0.35 * a, best + 0.35 * a
    if e2 > price:
        e2 = price
    if e1 >= e2:
        e1 = e2 - 0.35 * a
    # SL di bawah penahan terdekat yang masuk akal: dasar OB, Fibo 0,886, atau swing low (dikurangi 0,3 ATR),
    # dipilih yang tertinggi asalkan minimal 0,8 ATR di bawah area entry; lalu digeser ke bawah EQL kalau ada di antaranya.
    ob_hit = [ob for ob in ob_b if ob[2] - tol <= best <= ob[1] + tol]
    cand = [lo - 0.3 * a, fib[0.886] - 0.3 * a] + ([min(ob[2] for ob in ob_hit) - 0.3 * a] if ob_hit else [])
    ok = [x for x in cand if x <= e1 - 0.8 * a]
    sl = max(ok) if ok else min(cand)
    for x in eql:
        if sl < x[2] < e1:
            sl = x[2] - 0.3 * a
    if sl >= e1:
        sl = e1 - a
    tp = [hi, hi + 0.272 * rng, hi + 0.618 * rng]
    e1r, e2r, slr = bulat_bawah(e1), bulat_bawah(e2), bulat_bawah(sl)
    e2r = max(e1r, e2r)
    tpr = [bulat_atas(x) for x in tp]
    mid = (e1r + e2r) / 2
    risk = mid - slr
    rr = (tpr[0] - mid) / risk if risk > 0 else 0
    status = "di_zona" if e1 - 0.1 * a <= price <= e2 + 0.1 * a else ("atas" if price > e2 else "bawah")
    lay = skor >= 3 and rr >= 1.5 and risk > 0 and slr > 0
    alasan = "" if lay else (f"Skor konfluensi baru {skor}/6 (minimal 3)." if skor < 3 else f"Risk:reward ke TP1 hanya 1:{rr:.1f} (minimal 1:1,5).")
    return {
        "lay": lay, "alasan": alasan, "skor": skor, "fk": fk, "status": status,
        "e1": e1r, "e2": e2r, "sl": slr, "tp": tpr, "rr": round(rr, 2), "risk": round(risk / mid * 100, 1) if mid else None,
        "dist": round((price - e2r) / price * 100, 1),
        "leg": [max(0, start - s0), max(0, hi_idx - s0), round(lo, 2), round(hi, 2)],
        "fib": {str(k): round(vv_, 2) for k, vv_ in fib.items()}, "poc": round(float(poc), 2), "lvl": round(float(best), 2),
    }


def pak_ohlcv(df, n=150):
    """Candle terakhir untuk file data per saham: b=[[o,h,l,c]], v=volume (lot), ts=waktu (detik UTC)."""
    if df is None or len(df) == 0:
        return None
    df = df.dropna(subset=["Close"]).iloc[-n:]
    if len(df) < 10:
        return None
    last = float(df["Close"].iloc[-1])
    rp = (lambda x: round(float(x))) if last >= 50 else (lambda x: round(float(x), 2))
    idx = pd.DatetimeIndex(df.index)
    if idx.tz is None:
        idx = idx.tz_localize(WIB)
    return {"b": [[rp(v) for v in row] for row in df[["Open", "High", "Low", "Close"]].values],
            "v": [int(round(x / 100)) if np.isfinite(x) else 0 for x in df["Volume"].to_numpy(float)],
            "ts": [int(t.timestamp()) for t in idx]}


def struktur_ringkas(d, L=3):
    """Arah struktur (1 naik, -1 turun, 0 belum jelas) + kejadian BOS/CHoCH terakhir untuk satu timeframe."""
    if d is None or len(d) < 40:
        return None
    sm = smc(d, L=L, win=min(120, len(d)), ctx=min(260, len(d)))
    if not sm:
        return None
    e = sm["ev"][-1] if sm["ev"] else None
    return {"tr": sm["tr"], "ev": [e[3], e[4], e[5]] if e else None}


def _ema(x, n):
    return x.ewm(span=n, adjust=False).mean()


def _tenkan(d, n=9):
    """Garis Conversion Ichimoku (Tenkan-sen): rata-rata harga tertinggi & terendah 9 candle."""
    return (d["High"].rolling(n).max() + d["Low"].rolling(n).min()) / 2


def _tembus(close, line):
    """+1 = candle terakhir tutup tembus ke atas garis, -1 = tembus ke bawah, 0 = tidak ada."""
    if close is None or line is None or len(close) < 3:
        return 0
    c0, c1, l0, l1 = (float(v) for v in (close.iloc[-2], close.iloc[-1], line.iloc[-2], line.iloc[-1]))
    if not all(np.isfinite([c0, c1, l0, l1])):
        return 0
    return 1 if (c0 <= l0 and c1 > l1) else (-1 if (c0 >= l0 and c1 < l1) else 0)


def _macd_state(close, look=3):
    """(arah, cross): arah +1 bila MACD di atas sinyal; cross +1/-1 bila memotong dalam `look` candle terakhir."""
    if close is None or len(close) < 40:
        return 0, 0
    m = _ema(close, 12) - _ema(close, 26)
    h = (m - _ema(m, 9)).dropna()
    if len(h) < look + 2:
        return 0, 0
    arah = 1 if h.iloc[-1] > 0 else -1
    cross = 0
    for k in range(1, look + 1):
        a, b = h.iloc[-k - 1], h.iloc[-k]
        if a <= 0 < b:
            cross = 1; break
        if a >= 0 > b:
            cross = -1; break
    return arah, cross


def sinyal_harian(d):
    """Sinyal screener indikator di Daily dan Weekly."""
    w = resample(d, "W-FRI")
    return {"cb1d": _tembus(d["Close"], _tenkan(d)), "cb1w": _tembus(w["Close"], _tenkan(w)) if len(w) >= 12 else 0,
            "e21": _tembus(d["Close"], _ema(d["Close"], 21)), "e20w": _tembus(w["Close"], _ema(w["Close"], 20)) if len(w) >= 25 else 0}


def tambah_intraday(r, jam):
    if jam is not None and len(jam) >= 20:
        j4 = gabung_jam(jam, 4)
        try:                                     # sinyal 2 jam: tembus Conversion + MACD
            j2 = gabung_jam(jam, 2)
            arah, cross = _macd_state(j2["Close"])
            r.setdefault("ind", {}).update({"cb2h": _tembus(j2["Close"], _tenkan(j2)), "m2h": arah, "mc2h": cross})
        except Exception as e:
            print(f"  ! sinyal 2H {r['t']}: {e}")
        for k, x in (("h1", rating(jam)), ("h2", rating(gabung_jam(jam, 2))), ("h4", rating(j4))):
            if x:
                r["tf"][k] = x
        try:
            s4 = struktur_ringkas(j4, L=3)
            if s4:
                r.setdefault("ms", {})["h4"] = s4
        except Exception as e:
            print(f"  ! struktur 4H {r['t']}: {e}")


def kondisi(r):
    """Label kondisi + alasan singkat. c: ok / wait / hot / rev / n / bad / notx."""
    if r.get("notx"):
        y, mo, dd = r["notx"].split("-")
        bln = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"][int(mo) - 1]
        return "notx", "Tidak ada transaksi", f"Tidak ada transaksi di hari bursa terakhir; transaksi terakhir {int(dd)} {bln} {y}. Kemungkinan disuspensi BEI, cek pengumuman bursa"
    tf = r["tf"]
    d = tf.get("daily", {}).get("summary", "Neutral")
    w = tf.get("weekly", {}).get("summary", "Neutral")
    h1 = tf.get("h1", {}).get("summary")
    h2 = tf.get("h2", {}).get("summary")
    naik = lambda x: x in ("Buy", "Strong Buy")
    turun = lambda x: x in ("Sell", "Strong Sell")
    rs, pat, pk = r["rsi"], r["pattern"], r["pk"]
    rs_txt = f"{rs:g}".replace(".", ",")
    ma20, a = r["_ma20"], r["_atr"]

    if r["val"] < 5e8:
        return "bad", "Hindari dulu", "Transaksi rata-rata di bawah Rp 500 juta/hari, terlalu sepi"
    if turun(d) and turun(w):
        if pat and pk == "ok":
            return "rev", "Pantau pembalikan", f"Tren masih turun, tapi {pat} sudah terkonfirmasi. Tunggu Daily minimal Neutral"
        if pat:
            return "bad", "Hindari dulu", f"Tren harian dan mingguan turun. {pat} belum terkonfirmasi"
        return "bad", "Hindari dulu", "Tren harian dan mingguan masih turun"
    kf = (r.get("smc") or {}).get("kf") or {}
    if kf.get("lay"):
        sepi = " Transaksi di bawah Rp 5 M/hari, pakai lot kecil." if r["val"] < 5e9 else ""
        z = f"{rupiah(kf['e1'])}–{rupiah(kf['e2'])}"
        if kf["status"] == "di_zona":
            return "zone", "Di zona entry", f"Harga di zona konfluensi {z} (skor {kf['skor']}/6). Tunggu konfirmasi candle hijau atau CHoCH naik di 1H.{sepi}"
        if kf["status"] == "atas":
            return "tz", "Tunggu ke zona", f"Zona konfluensi {z}, {str(kf['dist']).replace('.', ',')}% di bawah harga (skor {kf['skor']}/6).{sepi}"
    if rs > 75:
        return "hot", "Tunggu pullback", f"RSI {rs_txt} sudah panas. Tunggu harga turun ke area entry"
    if ma20 and a and (r["p"] - ma20) > 2.5 * a:
        return "hot", "Tunggu pullback", "Harga sudah jauh di atas MA20. Tunggu turun ke area entry"
    if pat and pk == "tunggu":
        return "wait", "Tunggu konfirmasi", f"{pat} baru muncul. Tunggu candle berikutnya hijau dan tutup di atas {rupiah(bulat_atas(r['_ph']))}"
    if naik(d) and naik(w):
        if h1 and (turun(h1) or turun(h2 or "")):
            return "wait", "Tunggu pantulan", "Tren naik, tapi 1H/2H sedang koreksi. Tunggu berbalik Buy"
        if 45 <= rs <= 70 and r["val"] < 5e9:
            return "n", "Pantau", f"Teknikal bagus, tapi transaksi baru Rp {r['val'] / 1e9:.1f} M/hari (di bawah Rp 5 M). Gunakan lot kecil".replace(".", ",", 1)
        if 45 <= rs <= 70:
            extra = f", {pat} terkonfirmasi" if pat and pk == "ok" else ""
            return "ok", "Kandidat kuat", f"Tren harian dan mingguan naik, RSI {rs_txt} sehat{extra}"
        return "n", "Pantau", f"Tren naik, tapi RSI {rs_txt} belum di zona ideal 45-70"
    if turun(d):
        return "n", "Pantau", "Tren harian melemah, mingguan masih bertahan"
    return "n", "Pantau", "Belum ada arah yang jelas"


def rencana_struktur(r, kd):
    """Entry di order block bullish terdekat, SL sedikit di bawahnya, TP di OB bearish/puncak range (min. 1,5R)."""
    S, a, p = r.get("smc"), r.get("_atr") or 0, r["p"]
    if kd == "bad" or not S or not S.get("ob") or a <= 0:
        return None
    obs_ = sorted([z for z in S["ob"] if z[3] == 1 and z[2] <= p], key=lambda z: -z[1])
    if not obs_:
        return None
    ob = obs_[0]
    e1 = bulat_bawah(ob[2]); e2 = max(e1, bulat_bawah(min(ob[1], p)))
    sl = bulat_bawah(ob[2] - 0.3 * a)
    if sl >= e1:
        sl = e1 - fraksi(e1)
    if sl <= 0:
        return None
    mid = (e1 + e2) / 2; risk = mid - sl
    bear = sorted([z for z in S["ob"] if z[3] == -1 and z[2] > p], key=lambda z: z[2])
    tp = bulat_bawah(bear[0][2]) if bear else (bulat_bawah(S["pd"][0]) if S.get("pd") and S["pd"][0] > p else None)
    if not tp or (tp - mid) / risk < 1.5:
        tp = bulat_atas(mid + 2 * risk)
    return {"e1": e1, "e2": e2, "sl": sl, "tp": tp, "risk": round(risk / mid * 100, 1)}


def rencana_konf(r):
    kf = (r.get("smc") or {}).get("kf")
    if not kf or not kf.get("lay"):
        return None
    return {"e1": kf["e1"], "e2": kf["e2"], "sl": kf["sl"], "tp": kf["tp"][0], "tp2": kf["tp"][1], "tp3": kf["tp"][2],
            "risk": kf["risk"]}


def rencana(r, kd):
    """Contoh rencana berbasis ATR: area entry, stop loss (1 ATR di bawah area), target 2x risiko."""
    p, ma20, a = r["p"], r["_ma20"], r["_atr"]
    if kd == "bad" or not a or not ma20 or a <= 0:
        return None
    if kd == "hot":                      # tunggu pullback: area entry di bawah harga sekarang
        e2 = p - a
        e1 = max(ma20, p - 2 * a) if ma20 < e2 else p - 2 * a
    elif p > ma20:
        e1, e2 = max(ma20, p - a), p
    else:
        e1, e2 = p - 0.5 * a, p
    sl = e1 - a
    if sl <= 0:
        return None
    mid = (e1 + e2) / 2
    tp = mid + 2 * (mid - sl)
    e1r, e2r, slr, tpr = bulat_bawah(e1), bulat_bawah(e2), bulat_bawah(sl), bulat_atas(tp)
    if slr >= e1r or e1r <= 0:
        return None
    risk = (mid - slr) / mid * 100
    return {"e1": e1r, "e2": max(e1r, e2r), "sl": slr, "tp": tpr, "risk": round(risk, 1)}


def skor(r, w=W_DEFAULT):
    tot = sum(w.values())
    return (r["trend"] * w["trend"] + r["brk"] * w["brk"] + r["pa"] * w["pa"] + r["mom"] * w["mom"]
            + r.get("st", 50) * w.get("st", 0)) / tot


def skor_struktur(r):
    """Komponen Struktur SMC 0–100: Mingguan 40, Harian 40, 4 jam 20 (bullish penuh, belum jelas setengah, bearish 0)."""
    ms = r.get("ms") or {}
    def nilai(k, bobot, kosong):
        t = (ms.get(k) or {}).get("tr")
        return kosong if t is None else (bobot if t == 1 else bobot / 2 if t == 0 else 0)
    return round(nilai("w", 40, 20) + nilai("d", 40, 20) + nilai("h4", 20, 10))


def uptrend_penuh(r):
    """Syarat Top 10: badge Uptrend (MA tersusun naik) dan struktur SMC Mingguan & Harian bullish."""
    ms = r.get("ms") or {}
    return bool(r.get("trendOk")) and (ms.get("w") or {}).get("tr") == 1 and (ms.get("d") or {}).get("tr") == 1


def update_konsistensi(rows, tanggal):
    riw = {}
    if RIWAYAT.exists():
        try:
            riw = json.loads(RIWAYAT.read_text(encoding="utf-8"))
        except Exception:
            riw = {}
    top = sorted([r for r in rows if r["val"] >= 5e9 and uptrend_penuh(r) and not r.get("notx")], key=skor, reverse=True)[:10]
    for i, r in enumerate(top, 1):
        r["top"] = i                               # peringkat Top 10 hari ini
    riw[tanggal] = [r["t"] for r in top]          # dicatat per tanggal candle bursa; run berulang = ditimpa
    tgl = sorted(riw)[-10:]
    riw = {k: riw[k] for k in tgl}
    RIWAYAT.write_text(json.dumps(riw, indent=1), encoding="utf-8")
    for r in rows:
        ada = [r["t"] in riw[k] for k in tgl]
        streak = 0
        for x in reversed(ada):
            if not x:
                break
            streak += 1
        r["cst"] = {"count": sum(ada), "total": len(tgl), "streak": streak}


# ─────────────────────────── output ───────────────────────────
def bersih(o):
    if isinstance(o, dict):
        return {k: bersih(v) for k, v in o.items()}
    if isinstance(o, list):
        return [bersih(v) for v in o]
    if isinstance(o, (np.floating, float)):
        return None if not np.isfinite(o) else float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.bool_):
        return bool(o)
    return o


BULAN = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli",
         "Agustus", "September", "Oktober", "November", "Desember"]


def tulis_data_tf(tfdata, folder):
    """Satu file JSON kecil per saham, diambil halaman hanya saat timeframe itu dipilih."""
    folder.mkdir(parents=True, exist_ok=True)
    for f in folder.glob("*.json"):
        f.unlink()
    n = 0
    for t, d in tfdata.items():
        if d:
            (folder / f"{t}.json").write_text(json.dumps(bersih(d), separators=(",", ":")), encoding="utf-8")
            n += 1
    print(f"  Data timeframe tersimpan untuk {n} saham di {folder}")


def tulis_html(rows, now, status, n_gagal, pakai_intraday, out_html=OUT_HTML, arsip=True, pasar=None):
    tgl_data = max((r["tgl"] for r in rows), default="-")
    waktu = f"{now.day} {BULAN[now.month - 1]} {now.year}, {now:%H:%M} WIB"
    sub = (f"Data diambil {waktu}, {len(rows)} saham"
           + (f" ({n_gagal} tidak aktif atau gagal diambil)" if n_gagal else "")
           + f". Candle terakhir {tgl_data}.")
    parsial = "berjalan" in status or "Sesi 1" in status or status == "Pre-closing"
    disc = ("📡 Data asli dari Yahoo Finance — biasanya tertunda ±10–15 menit dari harga bursa."
            + (" Candle hari ini <b>belum final</b> (sesi masih/baru berjalan); rasio volume "
               "diproyeksikan ke satu hari penuh." if parsial else "")
            + (" Kolom 1H/2H/4H dan chart intraday tersedia untuk saham dengan transaksi minimal Rp 1 M/hari dan 200 saham skor tertinggi (yang lain tampil -)." if pakai_intraday
               else " Kolom 1H/2H/4H dimatikan (--no-intraday).")
            + " Halaman akan memberi tahu kalau ada data baru.<br><br>⚠️ Bukan rekomendasi/nasihat keuangan. "
              "Alat bantu penyaringan teknikal saja — tetap lakukan riset &amp; manajemen risiko "
              "sendiri sebelum trading.")
    html = (TEMPLATE
            .replace("__DATA__", json.dumps(bersih(rows), ensure_ascii=False, allow_nan=False))
            .replace("__TITLE__", f"{now:%Y-%m-%d %H:%M}")
            .replace("__LOGO96__", LOGO_96).replace("__LOGO32__", LOGO_32)
            .replace("__MARKET__", json.dumps(bersih(pasar or {}), ensure_ascii=False, allow_nan=False))
            .replace("__GEN__", now.strftime("%Y-%m-%d %H:%M"))
            .replace("__AGENDA__", json.dumps(muat_agenda(), ensure_ascii=False))
            .replace("__BADGE__", status)
            .replace("__SUB__", sub)
            .replace("__DISCLAIMER__", disc))
    out_html.parent.mkdir(parents=True, exist_ok=True)
    out_html.write_text(html, encoding="utf-8")
    if arsip:
        ARSIP.mkdir(exist_ok=True)
        (ARSIP / f"screener_{now:%Y-%m-%d_%H%M}.html").write_text(html, encoding="utf-8")

    flat = [{
        "ticker": r["t"], "harga": r["p"], "chg_pct": r["chg"], "skor": round(skor(r), 1),
        "uptrend": r["trendOk"], "breakout": r["brkOk"], "pola": r["pattern"] or "",
        "rsi": r["rsi"], "vol_ratio": r["vr"], "nilai_20h": round(r["val"]), "beta": r["beta"],
        "sektor": r["sector"], "daily": r["tf"].get("daily", {}).get("summary", ""),
        "weekly": r["tf"].get("weekly", {}).get("summary", ""),
        "h1": r["tf"].get("h1", {}).get("summary", ""), "candle": r["tgl"],
        "kondisi": (r.get("kd") or {}).get("l", ""), "alasan": (r.get("kd") or {}).get("why", ""),
        "entry": f'{r["plan"]["e1"]}-{r["plan"]["e2"]}' if r.get("plan") else "",
        "stop_loss": r["plan"]["sl"] if r.get("plan") else "", "target": r["plan"]["tp"] if r.get("plan") else "",
    } for r in sorted(rows, key=skor, reverse=True)]
    pd.DataFrame(flat).to_csv(out_html.parent / "hasil_screener.csv", index=False)


def main():
    ap = argparse.ArgumentParser(description="Screener saham IDX (data asli Yahoo Finance)")
    ap.add_argument("--tickers", help="file teks berisi ticker (tanpa .JK); default: semua emiten di daftar_saham.csv")
    ap.add_argument("--no-intraday", action="store_true", help="lewati data 1 jam (lebih cepat)")
    ap.add_argument("--intraday-top", type=int, default=200, help="1H/2H/4H dihitung untuk N saham skor tertinggi (default 200)")
    ap.add_argument("--no-sektor", action="store_true", help="jangan lengkapi sektor dari Yahoo")
    ap.add_argument("--buka", action="store_true", help="buka hasil di browser")
    ap.add_argument("--output", default=str(OUT_HTML), help="lokasi file HTML hasil (default hasil_screener.html)")
    ap.add_argument("--no-arsip", action="store_true", help="jangan simpan salinan ke folder arsip/")
    ap.add_argument("--perbarui-daftar", action="store_true", help="paksa ambil daftar emiten terbaru dari BEI sekarang")
    ap.add_argument("--tanpa-cek-bei", action="store_true", help="jangan cek daftar emiten di situs BEI")
    args = ap.parse_args()

    if not args.tickers and not args.tanpa_cek_bei:
        try:
            perbarui_daftar(paksa=args.perbarui_daftar)
        except Exception as e:
            print(f"  ! Cek daftar BEI dilewati: {e}")
    nama, sektor_daftar = muat_daftar()
    if args.tickers:
        tickers = Path(args.tickers).read_text(encoding="utf-8").replace(",", " ").split()
    elif nama:
        tickers = list(nama)
        if TAMBAHAN.exists():
            tickers += TAMBAHAN.read_text(encoding="utf-8").replace(",", " ").split()
    else:
        tickers = DEFAULT_TICKERS
    tickers = sorted({t.strip().upper().removesuffix(".JK") for t in tickers if t.strip()})

    now = datetime.now(WIB)
    status, frac = status_pasar(now)
    print(f"[{now:%H:%M} WIB] {status} - screening {len(tickers)} saham...")

    print("  Unduh data harian (5 tahun)...")
    harian = {t: ke_tanggal(df) for t, df in unduh(tickers, "5y", "1d").items()}
    print("  Unduh data bulanan (riwayat terpanjang) untuk chart M...")
    try:
        bulan_max = unduh(list(harian.keys()), "max", "1mo")
    except Exception as e:
        print(f"  ! data bulanan: {e}")
        bulan_max = {}
    ihsg = unduh(["^JKSE"], "2y", "1d").get("^JKSE")
    ihsg_jam = None if args.no_intraday else unduh(["^JKSE"], "6mo", "60m").get("^JKSE")
    ihsg15 = None if args.no_intraday else unduh(["^JKSE"], "60d", "15m").get("^JKSE")
    ihsg10 = unduh(["^JKSE"], "10y", "1d").get("^JKSE")        # untuk pola musiman
    ihsg_ret = ke_tanggal(ihsg)["Close"].pct_change() if ihsg is not None else None

    sektor = ({t: sektor_daftar.get(t, "-") for t in harian} if args.no_sektor
              else ambil_sektor(list(harian), sektor_daftar))

    hari_ini = now.date()
    tfdata = {}                                   # data timeframe lain per saham -> file data/<KODE>.json
    rows, gagal = [], [t for t in tickers if t not in harian]
    print(f"  Menghitung indikator {len(harian)} saham...")
    for t, d in harian.items():
        if (pd.Timestamp(hari_ini) - d.index[-1]).days > 60:   # tidak diperdagangkan > 60 hari: dianggap tidak aktif
                                                               # (suspensi yang lebih singkat tetap tampil berlabel "Tidak ada transaksi")
            gagal.append(t)
            continue
        try:
            r = analisa(t, d, ihsg_ret, sektor, nama, frac, hari_ini)
        except Exception as e:
            print(f"  ! {t}: {e}")
            r = None
        if r:
            rows.append(r)
        else:
            gagal.append(t)

    if not rows:
        sys.exit("Tidak ada data yang berhasil diambil. Cek koneksi internet atau coba lagi beberapa menit lagi.")

    if not args.no_intraday:
        # semua saham likuid (transaksi >= Rp 1 M/hari) + saham skor tertinggi (transaksi >= Rp 500 juta)
        teratas = [r["t"] for r in sorted(rows, key=skor, reverse=True) if r["val"] >= 5e8][:args.intraday_top]
        likuid = [r["t"] for r in rows if r["val"] >= 1e9]
        calon = list(dict.fromkeys(teratas + likuid))
        print(f"  Unduh data 1 jam (6 bulan) untuk {len(calon)} saham (likuid + skor tertinggi)...")
        jam = unduh(calon, "6mo", "60m")                  # 6 bulan: cukup untuk 220 candle 4 jam
        per_t = {r["t"]: r for r in rows}
        for t, df in jam.items():
            try:
                tambah_intraday(per_t[t], df)
                tfdata.setdefault(t, {})
                for k, fr in (("1h", df), ("4h", gabung_jam(df, 4))):
                    pk = pak_ohlcv(fr, 430)
                    if pk:
                        tfdata[t][k] = pk
            except Exception as e:
                print(f"  ! intraday {t}: {e}")
        print(f"  Unduh data 15 menit (60 hari) untuk {len(calon)} saham...")
        for t, df in unduh(calon, "60d", "15m").items():
            try:
                tfdata.setdefault(t, {})
                for k, fr in (("15m", df), ("45m", gabung_jam(df, 3))):
                    pk = pak_ohlcv(fr, 430)
                    if pk:
                        tfdata[t][k] = pk
            except Exception as e:
                print(f"  ! 15m {t}: {e}")

    # saham tanpa transaksi di hari bursa terakhir (tidak ada candle hari itu atau volumenya 0): kemungkinan disuspensi
    tgl_akhir = max(r["tgl"] for r in rows) if rows else None
    for r in rows:
        if r["tgl"] < tgl_akhir or not r.get("vday"):
            r["notx"] = r["tgl"]
    for r in rows:
        try:                                    # SMC untuk semua saham yang datanya cukup
            sm = smc(r["_d"])
            if sm:
                r["smc"] = sm
                e = sm["ev"][-1] if sm["ev"] else None
                r.setdefault("ms", {})["d"] = {"tr": sm["tr"], "ev": [e[3], e[4], e[5]] if e else None}
                r.pop("ohlc", None)             # 30 candle terakhir diambil dari smc["b"] di browser
                r["x"].pop("m20", None)
                r["x"].pop("m50", None)
            sw = struktur_ringkas(resample(r["_d"], "W-FRI"), L=3)
            if sw:
                r.setdefault("ms", {})["w"] = sw
            tfdata.setdefault(r["t"], {})
            bm = bulan_max.get(r["t"])
            bm = ke_tanggal(bm) if bm is not None and len(bm) > 24 else bulanan(r["_d"])
            for k, fr in (("1d", r["_d"]), ("1w", resample(r["_d"], "W-FRI")), ("1mo", bm)):
                pk = pak_ohlcv(fr, {"1d": 430, "1w": 280, "1mo": 420}[k])
                if pk:
                    tfdata[r["t"]][k] = pk
        except Exception as e:
            print(f"  ! smc {r['t']}: {e}")
        c, l, why = kondisi(r)
        r["kd"] = {"c": c, "l": l, "why": why}
        plans = {"K": None, "S": None, "A": None} if c == "notx" else {"K": rencana_konf(r) if c != "bad" else None, "S": rencana_struktur(r, c), "A": rencana(r, c)}
        r["plans"] = {k: v for k, v in plans.items() if v}
        best = next((k for k in ("K", "S", "A") if plans[k]), None)
        r["plan"] = dict(plans[best], src=best) if best else None
        r["st"] = skor_struktur(r)
        for k in ("_ma20", "_atr", "_ph", "_d"):
            r.pop(k, None)

    tgl_bursa = max(r["tgl"] for r in rows)       # tanggal candle terakhir, bukan tanggal run (akhir pekan tidak dihitung)
    update_konsistensi(rows, tgl_bursa)
    out_html = Path(args.output).resolve()
    for r in rows:
        r["tfx"] = sorted(tfdata.get(r["t"], {}).keys())
    ihsg_tf = {}
    try:                                           # IHSG: semua timeframe, sama seperti saham
        base = ke_tanggal(ihsg10) if ihsg10 is not None else (ke_tanggal(ihsg) if ihsg is not None else None)
        pairs = []
        if base is not None:
            pairs += [("1d", base, 430), ("1w", resample(base, "W-FRI"), 280), ("1mo", bulanan(base), 220)]
        if ihsg_jam is not None:
            pairs += [("1h", ihsg_jam, 430), ("4h", gabung_jam(ihsg_jam, 4), 430)]
        if ihsg15 is not None:
            pairs += [("15m", ihsg15, 430), ("45m", gabung_jam(ihsg15, 3), 430)]
        for k, fr, nn in pairs:
            pk = pak_ohlcv(fr, nn)
            if pk:
                ihsg_tf[k] = pk
        if ihsg_tf:
            tfdata["IHSG"] = ihsg_tf
    except Exception as e:
        print(f"  ! data timeframe IHSG: {e}")
    emas_r = None
    try:
        print("  Analisa emas dalam rupiah...")
        emas_r, emas_tf = analisa_emas()
        if emas_tf:
            tfdata["XAUIDR"] = emas_tf
    except Exception as e:
        print(f"  ! analisa emas: {e}")
    tulis_data_tf(tfdata, Path(args.output).resolve().parent / "data")
    pasar = konteks_pasar(ke_tanggal(ihsg) if ihsg is not None else None, rows, ihsg_jam,
                          ke_tanggal(ihsg10) if ihsg10 is not None else None)
    if emas_r:
        pasar["emas"] = emas_r
    if pasar.get("ihsg") is not None:
        pasar["ihsg"]["tfx"] = sorted(ihsg_tf)
    tulis_html(rows, now, status, len(gagal), not args.no_intraday, out_html, not args.no_arsip, pasar)

    top = sorted(rows, key=skor, reverse=True)[:5]
    print(f"  Selesai: {len(rows)} saham, {len(gagal)} gagal/tidak aktif")
    print("  Top 5 skor: " + ", ".join(f"{r['t']} {skor(r):.0f}" for r in top))
    print(f"  -> {out_html}")
    if args.buka:
        webbrowser.open(out_html.as_uri())


TEMPLATE = r'''<!DOCTYPE html>
<html lang="id">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<title>Dibalik Saham · Screener - __TITLE__</title>
<link rel="icon" type="image/png" href="data:image/png;base64,__LOGO32__">
<link rel="apple-touch-icon" href="data:image/png;base64,__LOGO96__">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#F5F6F3; --panel:#FFFFFF; --panel2:#F0F2F5; --ink:#14213D; --ink2:#34405A; --muted:#667085;
    --line:#E1E4E8; --accent:#2E3A87; --accent-soft:#E8EAF7; --up:#0E9F6E; --up-soft:#E3F6EE;
    --down:#D64545; --down-soft:#FBE9E9; --amber:#9A6212; --amber-soft:#FBF1DE; --orange:#B8430E;
    --orange-soft:#FDEBDD; --blue:#2952C9; --blue-soft:#E4ECFD; --row-hover:#F7F8FB;
    --shadow:0 1px 2px rgba(20,33,61,.06); --moon-dark:#C9CED8; --moon-line:#AEB5C2; --field-bg:#FFFFFF; --field-line:#D3D8E0; --field-ph:#8A93A6; --top-bg:#FFF6DB; --top-hover:#FFEFC2; --top-line:#E2A400; --top-ink:#7A5600;
    box-sizing:border-box;
    padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg:#0F1522; --panel:#161E2E; --panel2:#1C2638; --ink:#E6E9EF; --ink2:#C3C9D6; --muted:#8E98AD;
      --line:#263041; --accent:#9AA8FF; --accent-soft:#232C4D; --up:#34C38F; --up-soft:#15302A;
      --down:#F07171; --down-soft:#3A1E24; --amber:#E7B45A; --amber-soft:#35291A; --orange:#F29A63;
      --orange-soft:#3A2419; --blue:#8AB0FF; --blue-soft:#1C2A48; --row-hover:#1A2335; --shadow:none; --moon-dark:#2E3447; --moon-line:#3E465C; --field-bg:#1E2940; --field-line:#3A4868; --field-ph:#9AA5BC; --top-bg:#2B2614; --top-hover:#352E17; --top-line:#F2C94C; --top-ink:#F2C94C;
    }
  }
  :root[data-theme="dark"] {
    --bg:#0F1522; --panel:#161E2E; --panel2:#1C2638; --ink:#E6E9EF; --ink2:#C3C9D6; --muted:#8E98AD;
    --line:#263041; --accent:#9AA8FF; --accent-soft:#232C4D; --up:#34C38F; --up-soft:#15302A;
    --down:#F07171; --down-soft:#3A1E24; --amber:#E7B45A; --amber-soft:#35291A; --orange:#F29A63;
    --orange-soft:#3A2419; --blue:#8AB0FF; --blue-soft:#1C2A48; --row-hover:#1A2335; --shadow:none; --moon-dark:#2E3447; --moon-line:#3E465C; --field-bg:#1E2940; --field-line:#3A4868; --field-ph:#9AA5BC; --top-bg:#2B2614; --top-hover:#352E17; --top-line:#F2C94C; --top-ink:#F2C94C;
  }
  html { scroll-padding-top:env(safe-area-inset-top,0px); }
  *, *::before, *::after { box-sizing:border-box; }
  body {
    margin:0; background:var(--bg); color:var(--ink);
    font-family:"Plus Jakarta Sans", system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
    font-size:15px; line-height:1.5; font-feature-settings:"tnum" 1, "lnum" 1;
  }
  a { color:var(--accent); }
  button, input, select { font:inherit; color:inherit; }
  :focus-visible { outline:2px solid var(--accent); outline-offset:2px; border-radius:6px; }
  .wrap { max-width:1880px; margin:0 auto; padding:20px clamp(12px,3vw,28px) 48px; }

  /* header */
  .navbar { position:sticky; top:0; z-index:15; border-bottom:1px solid var(--line);
    background:color-mix(in srgb, var(--panel) 90%, transparent); -webkit-backdrop-filter:blur(10px); backdrop-filter:blur(10px); }
  .nav-in { max-width:1880px; margin:0 auto; padding:10px clamp(12px,3vw,28px); display:flex; align-items:center; justify-content:space-between; gap:8px 20px; flex-wrap:wrap; }
  .brand { min-width:0; }
  .brand h1 { font-size:1.25rem; font-weight:800; letter-spacing:-0.02em; margin:0; display:flex; align-items:center; gap:0; flex-wrap:wrap; line-height:1.2; }
  .logo { width:40px; height:40px; margin-right:11px; border-radius:10px; flex:0 0 auto; box-shadow:0 1px 3px rgba(0,0,0,.18); background:#fff; }
  .brand-row { display:flex; align-items:center; min-width:0; }
  .brand-name { display:flex; flex-direction:column; line-height:1.1; }
  .brand-name .nm { font-size:1.2rem; font-weight:800; letter-spacing:-0.01em; color:var(--ink); }
  .brand-name .tg { font-size:0.62rem; font-weight:700; letter-spacing:0.14em; color:var(--accent); text-transform:uppercase; margin-top:2px; }
  .brand .meta { color:var(--muted); font-size:0.76rem; margin-top:3px; }
  .wrap { padding-top:18px !important; }
  html { scroll-padding-top:calc(76px + env(safe-area-inset-top,0px)) !important; }
  @media (max-width:760px) { .navbar { position:static; } .top-actions { width:100%; justify-content:space-between; } .tabs { overflow-x:auto; } }
  .status { display:inline-block; margin-left:8px; vertical-align:4px; font-size:0.72rem; font-weight:700;
    padding:3px 10px; border-radius:999px; background:var(--up-soft); color:var(--up); letter-spacing:0; }
  .top-actions { display:flex; gap:10px; align-items:center; flex-wrap:wrap; }
  .icon-btn { border:1px solid var(--line); background:var(--panel); border-radius:10px; padding:7px 12px;
    cursor:pointer; font-size:0.85rem; font-weight:600; color:var(--ink2); }
  .icon-btn:hover { border-color:var(--accent); color:var(--accent); }
  .tabs { display:inline-flex; background:var(--panel2); border:1px solid var(--line); border-radius:12px; padding:3px; gap:2px; }
  .tab-btn { border:0; background:transparent; color:var(--ink2); font-weight:700; font-size:0.86rem; padding:7px 14px; border-radius:9px; cursor:pointer; }
  .tab-btn:hover { color:var(--accent); }
  .tab-btn.on { background:var(--panel); color:var(--accent); box-shadow:var(--shadow); }
  :root[data-theme="dark"] .tab-btn.on { background:var(--accent-soft); }
  .view[hidden] { display:none !important; }
  .pg-size { margin-left:6px; padding:5px 8px; border:1px solid var(--field-line); border-radius:8px; background:var(--field-bg); color:var(--ink); }
  .update-bar { display:none; align-items:center; justify-content:space-between; gap:12px; background:var(--accent);
    color:#fff; padding:10px 16px; border-radius:12px; margin-bottom:14px; font-weight:600; font-size:0.9rem; }
  .update-bar button { background:#fff; color:#2E3A87; border:0; border-radius:8px; padding:6px 14px; font-weight:700; cursor:pointer; }
  .notice { font-size:0.8rem; color:var(--muted); margin:0 0 16px; }
  .notice summary { cursor:pointer; color:var(--ink2); font-weight:600; }
  .notice div { margin-top:6px; }

  /* market strip: the one bold element */
  .market { display:grid; grid-template-columns:minmax(260px,1.4fr) minmax(220px,1fr) minmax(260px,1.3fr); gap:0;
    background:var(--ink); color:#fff; border-radius:16px; overflow:hidden; margin-bottom:18px; }
  :root[data-theme="dark"] .market { background:#1E2A44; }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .market { background:#1E2A44; } }
  .market > div { padding:16px 20px; border-right:1px solid rgba(255,255,255,.12); min-width:0; }
  .market > div:last-child { border-right:0; }
  .m-label { font-size:0.78rem; color:rgba(255,255,255,.66); font-weight:600; }
  .m-ihsg.clickable { cursor:pointer; transition:background .15s; }
  .m-ihsg.clickable:hover { background:rgba(255,255,255,.06); }
  .m-hint { float:right; font-size:0.72rem; color:rgba(255,255,255,.75); border:1px solid rgba(255,255,255,.3); border-radius:999px; padding:1px 8px; }
  .m-big { font-size:1.7rem; font-weight:800; letter-spacing:-0.02em; line-height:1.15; }
  .m-chg { font-size:0.95rem; font-weight:700; margin-left:6px; }
  .m-chg.up { color:#5EE0AE; } .m-chg.down { color:#FF9A9A; }
  .m-say { font-size:0.9rem; margin-top:6px; color:rgba(255,255,255,.9); }
  .m-row { display:flex; align-items:center; gap:14px; }
  .breadth-bar { height:10px; border-radius:99px; background:rgba(255,255,255,.18); overflow:hidden; margin:10px 0 6px; }
  .breadth-bar i { display:block; height:100%; background:#5EE0AE; border-radius:99px; }
  .kd-counts { display:flex; flex-wrap:wrap; gap:6px; margin-top:8px; }
  .kd-count { border:1px solid rgba(255,255,255,.22); background:transparent; color:#fff; border-radius:999px;
    padding:4px 10px; font-size:0.8rem; font-weight:600; cursor:pointer; }
  .kd-count b { font-weight:800; margin-left:4px; }
  .kd-count:hover, .kd-count.on { background:#fff; color:#14213D; }
  @media (max-width:900px) { .market { grid-template-columns:1fr; } .market > div { border-right:0; border-bottom:1px solid rgba(255,255,255,.12); } }

  /* controls */
  .card { background:var(--panel); border:1px solid var(--line); border-radius:14px; padding:16px 18px; margin-bottom:14px; box-shadow:var(--shadow); }
  .card h2 { font-size:1rem; font-weight:700; margin:0 0 10px; }
  .presets { display:flex; gap:8px; overflow-x:auto; padding-bottom:2px; scrollbar-width:thin; }
  .preset-btn { flex:0 0 auto; background:var(--panel2); color:var(--ink2); border:1px solid var(--line); border-radius:999px;
    padding:8px 14px; font-size:0.86rem; font-weight:600; cursor:pointer; white-space:nowrap; }
  .preset-btn:hover { border-color:var(--accent); color:var(--accent); }
  .preset-btn.active { background:var(--accent); border-color:var(--accent); color:#fff; }
  :root[data-theme="dark"] .preset-btn.active { color:#0F1522; }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .preset-btn.active { color:#0F1522; } }
  .watch-btn { border-color:#E2A400; color:#8A6400; }
  .watch-btn b { margin-left:4px; }
  .watch-btn.on { background:#E2A400; border-color:#E2A400; color:#1F1600; }
  :root[data-theme="dark"] .watch-btn { color:#F2C94C; }
  @media (prefers-color-scheme: dark) { :root:not([data-theme="light"]) .watch-btn { color:#F2C94C; } }
  :root[data-theme="dark"] .watch-btn.on, :root:not([data-theme="light"]) .watch-btn.on { color:#1F1600; }
  #filter-card.dim .filt { opacity:.6; }
  .filter-note { display:none; margin-top:10px; font-size:0.84rem; background:var(--accent-soft); color:var(--ink2); border-radius:9px; padding:8px 12px; }
  .filter-note.show { display:block; }
  .search-f { max-width:420px; }
  .top-filters { display:flex; flex-wrap:wrap; gap:10px 16px; align-items:flex-end; }
  .top-filters .search-f { flex:1 1 260px; }
  .sig-f { flex:1 1 260px; max-width:360px; }
  .pref-row { display:flex; flex-wrap:wrap; gap:6px; }
  .pref-row .seg button { padding:6px 10px; font-size:0.8rem; }
  .pref-row .seg button:disabled { opacity:.4; cursor:default; }
  body[data-pref="h1"] .tfc-h1, body[data-pref="h2"] .tfc-h2, body[data-pref="h4"] .tfc-h4,
  body[data-pref="daily"] .tfc-daily, body[data-pref="weekly"] .tfc-weekly, body[data-pref="monthly"] .tfc-monthly { background:color-mix(in srgb, var(--orange) 14%, transparent) !important; }
  .v10-hi { color:var(--orange); font-weight:800; }
  .cal-today { font-size:0.9rem; background:var(--panel2); border:1px solid var(--line); border-radius:10px; padding:10px 12px; margin:0 0 10px; }
  .cal-today .muted { display:block; font-size:0.8rem; margin-top:3px; }
  .cal-peaks { font-size:0.84rem; margin:-4px 0 10px; font-weight:700; }
  .cal-peaks:empty { display:none; }
  .filt { margin-top:14px; }
  .filt > summary { font-size:0.95rem; font-weight:700; color:var(--ink); }
  .fcount { margin-left:8px; font-size:0.76rem; font-weight:700; padding:2px 9px; border-radius:999px; background:var(--accent); color:#fff; vertical-align:1px; }
  .fcount:empty { display:none; }
  :root[data-theme="dark"] .fcount { color:#0F1522; }
  .preset-desc { font-size:0.84rem; color:var(--muted); margin:10px 2px 0; min-height:1.3em; }
  .filters { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px 18px; }
  .f label { display:block; font-size:0.8rem; color:var(--ink2); font-weight:600; margin-bottom:4px; }
  .f input, .f select { width:100%; padding:8px 10px; border:1px solid var(--field-line); border-radius:9px; background:var(--field-bg); color:var(--ink); font-size:0.88rem; }
  .f input::placeholder, .j-form input::placeholder, .cmp-add::placeholder { color:var(--field-ph); opacity:1; }
  .f input:focus, .f select:focus { border-color:var(--accent); outline:none; box-shadow:0 0 0 3px var(--accent-soft); }
  .pair { display:flex; gap:6px; align-items:center; }
  .chips { display:flex; flex-wrap:wrap; gap:8px 18px; align-items:center; margin-top:14px; padding-top:12px; border-top:1px solid var(--line); }
  .chip { display:flex; align-items:center; gap:6px; font-size:0.86rem; color:var(--ink); cursor:pointer; }
  .chip input { accent-color:var(--accent); width:16px; height:16px; }
  .minscore { display:flex; align-items:center; gap:10px; flex:1 1 260px; }
  .minscore label { font-size:0.86rem; white-space:nowrap; color:var(--ink2); }
  .minscore b { color:var(--accent); min-width:28px; }
  input[type=range] { accent-color:var(--accent); width:100%; }
  .adv { margin-top:12px; padding-top:10px; border-top:1px solid var(--line); }
  .adv summary { cursor:pointer; font-size:0.86rem; font-weight:600; color:var(--ink2); }
  .adv .hint { font-size:0.82rem; color:var(--amber); background:var(--amber-soft); border-radius:9px; padding:8px 12px; margin:10px 0 12px; }
  .weights { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:10px 20px; }
  .weights label { display:flex; justify-content:space-between; font-size:0.84rem; color:var(--ink2); }
  .weights b { color:var(--accent); }

  /* table */
  .count-info { color:var(--muted); font-size:0.86rem; margin:6px 2px 8px; }
  .table-wrap { overflow-x:auto; overflow-y:visible; border:1px solid var(--line); border-radius:14px; background:var(--panel); box-shadow:var(--shadow); }
  table { border-collapse:separate; border-spacing:0; width:100%; }
  thead th { position:sticky; top:0; z-index:3; background:var(--panel2); color:var(--muted); text-align:left;
    padding:10px 12px; font-size:0.78rem; font-weight:700; border-bottom:1px solid var(--line); white-space:nowrap; cursor:pointer; user-select:none; }
  thead th.nosort { cursor:default; }
  thead th:hover:not(.nosort) { color:var(--accent); }
  thead th.active { color:var(--accent); }
  thead th.active::after { content:" \25BE"; }
  thead th.active.asc::after { content:" \25B4"; }
  tbody td { padding:9px 12px; border-bottom:1px solid var(--line); font-size:0.88rem; vertical-align:middle; white-space:nowrap; background:var(--panel); }
  tbody tr { cursor:pointer; }
  tbody tr:hover td { background:var(--row-hover); }
  .sticky1 { position:sticky; left:0; z-index:2; width:38px; min-width:38px; padding-left:10px !important; padding-right:0 !important; }
  .sticky2 { position:sticky; left:38px; z-index:2; box-shadow:1px 0 0 var(--line); }
  thead .sticky1, thead .sticky2 { z-index:4; }
  tbody tr.top10 td { background:var(--top-bg); }
  tbody tr.grp { cursor:default; }
  tbody tr.grp td { background:var(--panel2); padding:7px 12px; font-size:0.8rem; font-weight:800; color:var(--ink2); border-bottom:1px solid var(--line); }
  tbody tr.grp td span { position:sticky; left:12px; }
  tbody tr.grp-top { cursor:pointer; }
  tbody tr.grp-top:hover td { background:var(--accent-soft); }
  .grp-toggle { border:0; background:none; font:inherit; font-weight:800; color:var(--ink); cursor:pointer; padding:0; }
  tbody tr.grp:hover td { background:var(--panel2); }
  .count-row { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin:6px 2px 8px; }
  .count-row .count-info { margin:0; }
  .pin-chip { font-size:0.84rem; }
  tbody tr.top10:hover td { background:var(--top-hover); }
  tbody tr.top10 td.sticky1 { box-shadow:inset 4px 0 0 var(--top-line); }
  .top-badge { display:inline-block; margin-left:6px; font-size:0.68rem; font-weight:800; padding:1px 6px; border-radius:6px;
    background:var(--top-line); color:#1F1600; vertical-align:2px; cursor:help; }
  .star { background:none; border:0; cursor:pointer; font-size:1.05rem; color:var(--line); padding:2px; line-height:1; }
  .star.on { color:#E2A400; }
  .tk { font-weight:800; letter-spacing:0.01em; }
  .tk-name { font-size:0.72rem; color:var(--muted); font-weight:500; max-width:150px; overflow:hidden; text-overflow:ellipsis; }
  .num { text-align:right; }
  .pos { color:var(--up); font-weight:700; } .neg { color:var(--down); font-weight:700; }
  .muted { color:var(--muted); }
  .score { display:inline-flex; align-items:center; gap:8px; }
  .score-bar { width:56px; height:6px; border-radius:9px; background:var(--panel2); overflow:hidden; }
  .score-bar i { display:block; height:100%; background:var(--accent); }
  .score b { min-width:30px; }
  .ck { font-weight:700; font-size:0.84rem; }
  .ck.hi { color:var(--up); } .ck.mid { color:var(--amber); } .ck.lo { color:var(--down); }
  .kd { display:inline-block; font-size:0.76rem; font-weight:700; padding:3px 10px; border-radius:999px; white-space:nowrap; }
  .kd.ok { background:var(--up-soft); color:var(--up); }
  .kd.wait { background:var(--amber-soft); color:var(--amber); }
  .kd.hot { background:var(--orange-soft); color:var(--orange); }
  .kd.bad { background:var(--down-soft); color:var(--down); }
  .kd.rev { background:var(--blue-soft); color:var(--blue); }
  .kd.n { background:var(--panel2); color:var(--muted); }
  .kd.zone { background:var(--up); color:#fff; }
  .kd.notx { background:transparent; color:var(--muted); border:1px dashed var(--muted); }
  :root[data-theme="dark"] .kd.zone { color:#0B1A14; }
  .kd.tz { background:var(--blue-soft); color:var(--blue); }
  .src { display:inline-grid; place-items:center; width:17px; height:17px; border-radius:5px; font-size:0.66rem; font-weight:800; margin-right:6px; vertical-align:1px; cursor:help; }
  .src-K { background:#D4A017; color:#1F1600; } .src-S { background:var(--blue-soft); color:var(--blue); } .src-A { background:var(--panel2); color:var(--muted); }
  .kf-box { border:1px solid var(--line); border-radius:10px; padding:8px 12px; margin:0 0 10px; background:var(--panel2); }
  .kf-head { font-size:0.86rem; margin-bottom:4px; }
  .kf-list { display:flex; flex-wrap:wrap; gap:4px 14px; font-size:0.8rem; }
  .kf-list .y { color:var(--up); font-weight:700; } .kf-list .x { color:var(--muted); }
  .kf-tp { font-size:0.84rem; margin-top:6px; }
  .plan { font-size:0.8rem; line-height:1.45; }
  .plan .sl { color:var(--down); font-weight:600; } .plan .tp { color:var(--up); font-weight:600; }
  .badge { display:inline-block; font-size:0.72rem; padding:2px 8px; border-radius:999px; margin:1px 2px 1px 0; font-weight:600; border:1px solid var(--line); color:var(--ink2); }
  .badge.trend { color:var(--blue); border-color:var(--blue-soft); background:var(--blue-soft); }
  .badge.breakout { color:var(--up); border-color:var(--up-soft); background:var(--up-soft); }
  .badge.pattern { color:var(--amber); border-color:var(--amber-soft); background:var(--amber-soft); }
  .badge.pattern.ok { color:var(--up); border-color:var(--up); background:var(--up-soft); }
  .v { font-weight:700; font-size:0.8rem; }
  .v.sb { color:var(--up); } .v.b { color:var(--up); font-weight:600; opacity:.85; }
  .v.n { color:var(--muted); font-weight:600; } .v.s { color:var(--down); font-weight:600; opacity:.85; } .v.ss { color:var(--down); }
  svg.spark { display:block; }
  .pager { display:flex; gap:8px; justify-content:flex-end; align-items:center; margin-top:10px; }
  .pager button { border:1px solid var(--line); background:var(--panel); border-radius:9px; padding:6px 14px; cursor:pointer; font-weight:600; }
  .pager button:disabled { opacity:.4; cursor:default; }
  .empty { padding:40px 20px; text-align:center; color:var(--muted); }
  .empty button { margin-top:10px; }

  /* drawer */
  .scrim { position:fixed; inset:0; background:rgba(15,21,34,.45); opacity:0; pointer-events:none; transition:opacity .2s; z-index:20; }
  .scrim.open { opacity:1; pointer-events:auto; }
  .drawer { position:fixed; top:0; right:0; bottom:0; width:min(720px,100%); background:var(--panel); z-index:21;
    transform:translateX(100%); visibility:hidden; transition:transform .22s ease, visibility 0s linear .22s; overflow-y:auto; box-shadow:-8px 0 24px rgba(0,0,0,.18);
    padding:calc(18px + env(safe-area-inset-top,0px)) 22px calc(28px + env(safe-area-inset-bottom,0px)); }
  .drawer.open { transform:none; visibility:visible; transition:transform .22s ease; }
  @media (prefers-reduced-motion: reduce) { .drawer, .scrim { transition:none; } }
  .d-head { display:flex; justify-content:space-between; gap:12px; align-items:flex-start; }
  .d-tk { font-size:1.6rem; font-weight:800; letter-spacing:-0.01em; line-height:1.1; }
  .d-name { color:var(--muted); font-size:0.88rem; }
  .d-price { font-size:1.4rem; font-weight:800; margin-top:10px; }
  .d-sec { margin-top:18px; }
  .d-sec h3 { font-size:0.95rem; font-weight:700; margin:0 0 8px; }
  .d-why { font-size:0.9rem; color:var(--ink2); margin-top:6px; }
  .d-chart { width:100%; height:auto; display:block; background:var(--panel2); border-radius:12px; }
  .legend { display:flex; flex-wrap:wrap; gap:12px; font-size:0.76rem; color:var(--muted); margin-top:6px; }
  .legend i { display:inline-block; width:14px; height:3px; border-radius:2px; vertical-align:middle; margin-right:5px; }
  .checklist { list-style:none; padding:0; margin:0; }
  .checklist li { display:flex; gap:10px; padding:7px 0; border-bottom:1px solid var(--line); font-size:0.88rem; }
  .checklist li:last-child { border-bottom:0; }
  .ci { width:20px; flex:0 0 20px; font-weight:800; text-align:center; }
  .ci.y { color:var(--up); } .ci.x { color:var(--down); } .ci.na { color:var(--muted); }
  .bars { display:grid; gap:8px; }
  .bar-row { display:grid; grid-template-columns:110px 1fr 130px; gap:10px; align-items:center; font-size:0.85rem; }
  .bar-row .track { height:8px; background:var(--panel2); border-radius:9px; overflow:hidden; }
  .bar-row .track i { display:block; height:100%; background:var(--accent); }
  .bar-row span:last-child { color:var(--muted); font-size:0.78rem; text-align:right; }
  .tf-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:8px; }
  .tf-cell { background:var(--panel2); border-radius:10px; padding:8px 10px; }
  .tf-cell small { display:block; color:var(--muted); font-size:0.74rem; }
  .plan-box { display:grid; grid-template-columns:repeat(4,1fr); gap:8px; }
  .plan-box div { background:var(--panel2); border-radius:10px; padding:8px 10px; }
  .plan-box small { display:block; color:var(--muted); font-size:0.74rem; }
  .plan-box b { font-size:0.98rem; }
  .calc { display:grid; grid-template-columns:1fr 1fr; gap:10px; margin-top:10px; }
  .calc input { width:100%; padding:8px 10px; border:1px solid var(--line); border-radius:9px; background:var(--panel); }
  .calc-out { margin-top:10px; background:var(--accent-soft); border-radius:10px; padding:10px 12px; font-size:0.9rem; }
  .d-actions { display:flex; gap:8px; margin-top:14px; flex-wrap:wrap; }
  .xh-wrap { position:relative; }
  .draw-ctl { margin:0 0 8px; }
  .dw-row { display:flex; flex-wrap:wrap; align-items:center; gap:8px 10px; }
  .dw-tools { display:inline-flex; border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  .dw-tools button { border:0; border-right:1px solid var(--line); background:var(--panel); color:var(--ink); font-weight:700; font-size:0.8rem; padding:6px 10px; cursor:pointer; }
  .dw-tools button:last-child { border-right:0; }
  .dw-tools button.on { background:var(--accent); color:#fff; }
  :root[data-theme="dark"] .dw-tools button.on { color:#0F1522; }
  .dw-colors { display:inline-flex; align-items:center; gap:5px; }
  .dw-colors .sw { width:20px; height:20px; border-radius:50%; border:2px solid var(--panel); box-shadow:0 0 0 1px var(--line); cursor:pointer; padding:0; }
  .dw-colors .sw.on { box-shadow:0 0 0 2px var(--ink); }
  .dw-colors input[type=color] { width:26px; height:24px; border:1px solid var(--line); border-radius:6px; padding:0; background:none; cursor:pointer; }
  .dw-small { padding:5px 10px; font-size:0.78rem; }
  .dw-small.on { border-color:var(--accent); color:var(--accent); }
  .dw-hint { margin-top:6px; font-size:0.82rem; color:var(--ink2); background:var(--accent-soft); border-radius:8px; padding:6px 10px; display:inline-block; }
  .dw-sel { margin-top:6px; font-size:0.84rem; display:flex; flex-wrap:wrap; align-items:center; gap:6px 10px; }
  .dw-del { color:var(--down); }
  .ew-check { width:100%; margin:4px 0 0; padding-left:18px; font-size:0.8rem; }
  svg.smc-svg.draw-on { cursor:crosshair; }
  .zoom-ctl button.on { color:var(--accent); }
  .zoom-ctl { display:inline-flex; align-items:center; border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  .zoom-ctl button { border:0; border-right:1px solid var(--line); background:var(--panel); color:var(--ink); font-weight:800; font-size:0.95rem; min-width:34px; padding:5px 10px; cursor:pointer; }
  .zoom-ctl button:hover:not(:disabled) { color:var(--accent); }
  .zoom-ctl button:disabled { opacity:.35; cursor:default; }
  .zoom-info { font-size:0.76rem; color:var(--muted); padding:0 10px; }
  body.chart-panning, body.chart-panning svg.smc-svg { cursor:grabbing !important; user-select:none; }
  .frvp-ctl { display:flex; flex-wrap:wrap; align-items:center; gap:8px 10px; margin:0 0 8px; }
  .frvp-ctl .icon-btn { padding:6px 12px; font-size:0.82rem; }
  .frvp-ctl .icon-btn.on { background:var(--accent); color:#fff; border-color:var(--accent); }
  :root[data-theme="dark"] .frvp-ctl .icon-btn.on { color:#0F1522; }
  .frvp-info { font-size:0.82rem; color:var(--ink2); }
  svg.smc-svg.frvp-on { cursor:col-resize; touch-action:none; }
  .chart-head { display:flex; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap; margin-bottom:8px; }
  .chart-head h3 { margin:0; }
  .tf-bar { display:inline-flex; border:1px solid var(--line); border-radius:10px; overflow:hidden; }
  .tf-bar button { border:0; background:var(--panel); padding:6px 12px; font-size:0.82rem; font-weight:700; color:var(--ink2); cursor:pointer; border-right:1px solid var(--line); }
  .tf-bar button:last-child { border-right:0; }
  .tf-bar button.on { background:var(--accent); color:#fff; }
  :root[data-theme="dark"] .tf-bar button.on { color:#0F1522; }
  .tf-bar button:disabled { opacity:.35; cursor:not-allowed; }
  .tf-msg { padding:60px 16px; text-align:center; color:var(--muted); background:var(--panel2); border-radius:12px; font-size:0.9rem; }
  .xh-wrap svg.smc-svg { cursor:crosshair; touch-action:pan-y; }
  .xh-legend { position:absolute; left:10px; top:6px; right:110px; z-index:1; font-size:0.78rem; color:var(--ink2); pointer-events:none;
    display:flex; flex-wrap:wrap; gap:2px 8px; align-items:baseline; background:color-mix(in srgb, var(--panel2) 82%, transparent); padding:3px 8px; border-radius:8px; width:max-content; max-width:calc(100% - 120px); }
  .xh-legend b { color:var(--ink); margin-right:4px; }
  .xl-k { color:var(--muted); font-weight:600; }
  .smc-toggles { margin-top:8px; padding-top:0; border-top:0; gap:6px 14px; }
  .smc-toggles .chip { font-size:0.8rem; }
  .smc-sum { margin:10px 0 0; padding-left:18px; font-size:0.86rem; color:var(--ink2); }
  .smc-sum li { margin:4px 0; }
  .d-foot { font-size:0.78rem; color:var(--muted); margin-top:18px; }

  .ms-row { display:inline-flex; gap:4px; }
  .ms { font-size:0.72rem; font-weight:800; padding:2px 6px; border-radius:6px; background:var(--panel2); color:var(--muted); }
  .ms.up { background:var(--up-soft); color:var(--up); } .ms.dn { background:var(--down-soft); color:var(--down); }
  .warn { background:var(--amber-soft); color:var(--amber); border-radius:10px; padding:8px 12px; font-size:0.84rem; margin:8px 0 0; }
  .seg { display:inline-flex; border:1px solid var(--line); border-radius:10px; overflow:hidden; margin-bottom:8px; flex-wrap:wrap; }
  .seg button { border:0; background:var(--panel); padding:7px 12px; font-size:0.84rem; font-weight:600; cursor:pointer; color:var(--ink2); }
  .seg button.on { background:var(--accent); color:#fff; }
  :root[data-theme="dark"] .seg button.on { color:#0F1522; }
  .seg button:disabled { opacity:.4; cursor:default; }
  .plan-note { font-size:0.84rem; color:var(--ink2); margin:4px 0 10px; }
  .j-form { display:grid; grid-template-columns:repeat(auto-fit,minmax(140px,1fr)); gap:10px; margin-top:10px; background:var(--panel2); border-radius:12px; padding:12px; }
  .jr-add { display:grid; gap:6px; min-width:170px; }
  .jr-add input { width:100%; padding:6px 8px; border:1px solid var(--line); border-radius:8px; background:var(--panel); }
  .jr-row { display:grid; grid-template-columns:1fr 1fr auto; gap:8px; margin-bottom:6px; }
  .j-form input, .j-form select { width:100%; padding:7px 9px; border:1px solid var(--line); border-radius:8px; background:var(--panel); }
  .j-tbl { width:100%; border-collapse:collapse; font-size:0.84rem; }
  .j-tbl th { text-align:center; color:var(--muted); font-size:0.76rem; padding:8px 10px; border-bottom:1px solid var(--line); background:var(--panel2); position:static; }
  .j-tbl td { padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:middle; background:var(--panel); text-align:center; }
  .j-tbl td.num, .j-tbl th.num { text-align:center; }
  .j-tbl td:first-child, .j-tbl th:first-child { text-align:left; }
  .j-tbl .ms-row { justify-content:center; }
  .j-exit { width:90px; padding:5px 7px; border:1px solid var(--line); border-radius:8px; }
  .j-stats { grid-template-columns:repeat(auto-fit,minmax(130px,1fr)); }

  .hist-head { display:flex; flex-wrap:wrap; align-items:center; gap:8px 12px; margin-bottom:8px; }
  .hist-head h3 { margin:0 auto 0 0; }
  .hist-head .seg { margin:0; }
  .hist-wrap { max-height:420px; }
  .hist-tbl th { position:sticky; top:0; z-index:1; }
  .hist-tbl td { white-space:nowrap; }
  .hist-tbl tr.spike td { background:var(--top-bg); }
  .vbar { display:inline-block; width:44px; height:6px; background:var(--panel2); border-radius:9px; margin-right:6px; vertical-align:middle; overflow:hidden; }
  .vbar i { display:block; height:100%; background:var(--accent); opacity:.7; }
  .vx-hi { color:var(--top-ink); font-weight:800; }

  /* makro */
  .makro-grid { display:grid; grid-template-columns:repeat(auto-fill,minmax(230px,1fr)); gap:10px; }
  .mk-card { display:flex; flex-direction:column; gap:3px; text-align:left; border:1px solid var(--line); background:var(--panel); border-radius:12px; padding:10px 12px; cursor:pointer; color:var(--ink); }
  .mk-card:hover { border-color:var(--accent); }
  .mk-card.on { border-color:var(--accent); box-shadow:0 0 0 3px var(--accent-soft); }
  .mk-name { font-size:0.8rem; font-weight:700; color:var(--ink2); }
  .mk-val { font-size:1.25rem; font-weight:800; }
  .mk-chg { font-size:0.76rem; display:flex; gap:8px; flex-wrap:wrap; }
  .mk-spark { width:100%; height:48px; margin:2px 0; }
  .mk-kor { font-size:0.74rem; color:var(--muted); }
  .mk-link { font-size:0.74rem; font-weight:700; color:var(--accent); }
  .mk-an { margin-left:auto; margin-right:12px; }
  .mk-big { margin-top:14px; border-top:1px solid var(--line); padding-top:12px; }
  #makro-card { margin-bottom:14px; }

  /* kalender */
  .cal-head { display:flex; flex-wrap:wrap; align-items:center; gap:10px 18px; margin-bottom:12px; }
  .cal-head h2 { margin:0; }
  .cal-nav { display:flex; align-items:center; gap:8px; }
  .cal-title { font-weight:800; font-size:1.05rem; min-width:150px; text-align:center; }
  .cal-opts { display:flex; gap:14px; margin-left:auto; }
  .cal-grid { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:6px; }
  .cal-dow { font-size:0.78rem; font-weight:700; color:var(--muted); text-align:center; padding:2px 0 4px; }
  .cal-cell { position:relative; min-height:92px; border:1px solid var(--line); border-radius:12px; background:var(--panel); padding:6px 7px; text-align:left;
    display:flex; flex-direction:column; gap:3px; cursor:pointer; overflow:hidden; }
  .cal-cell:hover { border-color:var(--accent); }
  .cal-cell.empty { border:0; background:transparent; cursor:default; }
  .cal-cell.weekend { background:var(--panel2); }
  .cal-cell.today { border:2px solid var(--accent); }
  .cal-cell.sel { box-shadow:0 0 0 3px var(--accent-soft); border-color:var(--accent); }
  .cal-d { font-weight:700; font-size:0.86rem; }
  .cal-moon { font-size:1.15rem; line-height:1.1; }
  .cal-moonic { position:absolute; top:6px; right:7px; line-height:0; }
  .cal-moon-lab { font-size:0.68rem; color:var(--muted); font-weight:700; margin-top:2px; }
  .cl-moon { display:inline-block; vertical-align:-3px; line-height:0; }
  .moon-ic { display:block; }
  .cal-moon small { font-size:0.68rem; color:var(--muted); margin-left:4px; vertical-align:3px; font-weight:600; }
  .cal-ev { display:inline-block; font-size:0.68rem; font-weight:700; padding:1px 7px; border-radius:999px; white-space:nowrap; }
  .ev-msci { background:var(--blue-soft); color:var(--blue); }
  .ev-ftse { background:var(--accent-soft); color:var(--accent); }
  .ev-gdx { background:var(--amber-soft); color:var(--amber); }
  .ev-lapkeu { background:var(--orange-soft); color:var(--orange); }
  .ev-lain { background:var(--panel2); color:var(--ink2); }
  .ev-bi, .ev-fomc, .ev-cpi, .ev-nfp, .ev-inflasi { background:#EDE7FB; color:#5B34C4; }
  :root[data-theme="dark"] .ev-bi, :root[data-theme="dark"] .ev-fomc, :root[data-theme="dark"] .ev-cpi, :root[data-theme="dark"] .ev-nfp, :root[data-theme="dark"] .ev-inflasi { background:#2D2450; color:#B9A5F5; }
  .cal-lean { margin-top:auto; font-size:0.95rem; font-weight:800; line-height:1; }
  .cal-lean.up { color:var(--up); } .cal-lean.dn { color:var(--down); } .cal-lean.n { color:var(--muted); }
  .cal-lean.weak { opacity:.38; }
  .cal-musim-sum { font-size:0.88rem; color:var(--ink2); margin:0 0 10px; }
  .cal-musim-sum:empty { display:none; }
  .cal-legend { display:flex; flex-wrap:wrap; gap:6px 18px; font-size:0.8rem; color:var(--muted); margin-top:10px; align-items:center; }
  .cal-legend .cal-lean { margin:0 3px 0 0; }
  .cal-list { list-style:none; margin:14px 0 0; padding:0; }
  .cal-list li { display:flex; gap:14px; padding:9px 0; border-top:1px solid var(--line); font-size:0.88rem; }
  .cl-date { flex:0 0 104px; font-weight:700; color:var(--ink2); white-space:nowrap; }
  .tk-chip { border:1px solid var(--line); background:var(--panel2); border-radius:999px; padding:2px 9px; margin:5px 5px 0 0; font-size:0.76rem; font-weight:700; cursor:pointer; }
  .tk-chip:hover { border-color:var(--accent); color:var(--accent); }
  @media (max-width:700px) { .cal-cell { min-height:64px; } .cal-moon-lab, .cal-ev { display:none; } .cal-moonic svg { width:16px; height:16px; } }

  /* layar penuh */
  .full { position:fixed; inset:0; z-index:25; background:var(--bg); overflow-y:auto; display:none; }
  .full.open { display:block; }
  body.noscroll { overflow:hidden; }
  .full-head { position:sticky; top:0; z-index:3; background:var(--panel); border-bottom:1px solid var(--line); box-shadow:var(--shadow);
    padding-top:env(safe-area-inset-top,0px); }
  .full-head-in { max-width:1500px; margin:0 auto; padding:12px clamp(12px,3vw,28px); display:flex; align-items:center; gap:10px 16px; flex-wrap:wrap; }
  .fh-id { display:flex; flex-direction:column; line-height:1.2; }
  .fh-tk { font-size:1.45rem; font-weight:800; letter-spacing:-0.01em; }
  .fh-name { font-size:0.82rem; color:var(--muted); }
  .fh-price { font-size:1.25rem; font-weight:800; }
  .fh-right { margin-left:auto; display:flex; align-items:center; gap:10px; }
  .full-grid { max-width:1500px; margin:0 auto; padding:18px clamp(12px,3vw,28px) 48px; display:grid;
    grid-template-columns:minmax(0,1.75fr) minmax(340px,1fr); gap:16px; align-items:start; }
  .full-col { display:flex; flex-direction:column; gap:14px; min-width:0; }
  .full-grid2 { grid-template-columns:minmax(0,1fr) minmax(0,1fr); }
  #full .full-head-in, #full .full-grid { max-width:1880px; }
  .full-span { grid-column:1 / -1; margin:0; min-width:0; }
  .full-span > .d-sec:first-child { margin-top:0; }
  body.has-cmpbar .wrap { padding-bottom:110px; }
  body.has-cmpbar .full-grid { padding-bottom:110px; }
  .full-col .card { margin:0; }
  .full-col .card > .d-sec:first-child { margin-top:0; }
  .full .hist-wrap { max-height:560px; }
  @media (max-width:1000px) { .full-grid, .full-grid2 { grid-template-columns:minmax(0,1fr); } .fh-right { margin-left:0; } }
  @media (max-width:700px) { .full-head { position:static; } }
  .d-head-btns { display:flex; gap:6px; align-items:center; flex-wrap:wrap; justify-content:flex-end; }
  .d-nav { display:inline-flex; align-items:center; gap:6px; }
  .d-nav .icon-btn { padding:6px 11px; }
  .d-nav .icon-btn:disabled { opacity:.35; cursor:default; }
  .d-pos { font-size:0.8rem; min-width:48px; text-align:center; }

  .spark-cell { cursor:zoom-in; }
  .cpop { position:fixed; z-index:45; width:min(560px, calc(100% - 16px)); background:var(--panel); border:1px solid var(--line); border-radius:14px;
    box-shadow:0 14px 36px rgba(0,0,0,.32); padding:12px 14px; }
  .cpop[hidden] { display:none; }
  .cpop-head { display:flex; justify-content:space-between; align-items:flex-start; gap:10px; margin-bottom:6px; }
  .cpop-ctl { display:flex; align-items:center; gap:6px; }
  .cpop-ctl .seg button { padding:4px 9px; font-size:0.76rem; }
  .cpop-svg { width:100%; height:auto; display:block; background:var(--panel2); border-radius:10px; }
  .cpop-foot { display:flex; justify-content:space-between; align-items:center; gap:8px; flex-wrap:wrap; margin-top:6px; font-size:0.8rem; }
  .rf-btn { display:inline-flex; align-items:center; gap:6px; }
  .rf-ic { font-size:1.05rem; line-height:1; display:inline-block; }
  .rf-btn.busy { border-color:var(--accent); color:var(--accent); }
  .rf-btn.busy .rf-ic { animation:rfspin 1.1s linear infinite; }
  @keyframes rfspin { to { transform:rotate(360deg); } }
  @media (prefers-reduced-motion: reduce) { .rf-btn.busy .rf-ic { animation:none; } }
  .rf-pop { position:fixed; top:calc(70px + env(safe-area-inset-top,0px)); right:20px; z-index:40; width:min(420px, calc(100% - 24px));
    background:var(--panel); border:1px solid var(--line); border-radius:14px; box-shadow:0 12px 32px rgba(0,0,0,.28); padding:14px 16px; }
  .rf-pop[hidden] { display:none; }
  .rf-head { display:flex; align-items:center; justify-content:space-between; margin-bottom:6px; }
  .rf-go { display:block; text-align:center; text-decoration:none; background:var(--accent); color:#fff; border:0; border-radius:10px; padding:10px 14px; font-weight:800; cursor:pointer; width:100%; font-size:0.9rem; }
  :root[data-theme="dark"] .rf-go { color:#0F1522; }
  .rf-go:disabled { opacity:.5; cursor:default; }
  .rf-msg { font-size:0.84rem; background:var(--accent-soft); color:var(--ink2); border-radius:8px; padding:8px 10px; margin-bottom:10px; }
  .rf-setup { margin-top:10px; font-size:0.84rem; }
  .rf-setup summary { cursor:pointer; font-weight:700; color:var(--accent); }
  .rf-setup ol { padding-left:18px; margin:8px 0; }
  .rf-row { display:flex; gap:8px; }
  .rf-row input { flex:1; padding:8px 10px; border:1px solid var(--field-line); border-radius:9px; background:var(--field-bg); color:var(--ink); }
  @media (max-width:760px) { .rf-lab { display:none; } }
  .to-top { position:fixed; right:calc(20px + env(safe-area-inset-right,0px)); bottom:calc(20px + env(safe-area-inset-bottom,0px)); z-index:30;
    display:none; align-items:center; gap:6px; border:0; border-radius:999px; padding:11px 16px; font-weight:800; font-size:0.88rem;
    background:var(--accent); color:#fff; box-shadow:0 6px 18px rgba(0,0,0,.25); cursor:pointer; }
  .to-top.show { display:inline-flex; }
  .to-top:hover { filter:brightness(1.08); }
  :root[data-theme="dark"] .to-top { color:#0F1522; }
  body.has-cmpbar .to-top { bottom:calc(84px + env(safe-area-inset-bottom,0px)); }

  #movers-card { margin-bottom:14px; }
  #movers-card .filt { margin-top:0; border-top:0; padding-top:0; }
  .mv-tabs { flex-wrap:wrap; }
  .mv-tbl tbody tr { cursor:pointer; }
  .mv-tbl td:nth-child(2), .mv-tbl th:nth-child(2) { text-align:left; }
  .mv-tbl td:first-child, .mv-tbl th:first-child { width:36px; }
  .mv-tbl td.mv-chart { line-height:0; }
  .mv-tbl tbody tr:hover td { background:var(--row-hover); }
  .mv-bar { display:inline-block; width:60px; height:6px; background:var(--panel2); border-radius:9px; margin-right:8px; vertical-align:middle; overflow:hidden; }
  .mv-bar i { display:block; height:100%; }
  .mv-bar.pos i { background:var(--up); } .mv-bar.neg i { background:var(--down); }
  .est { font-size:0.66rem; font-weight:700; background:var(--orange-soft); color:var(--orange); border-radius:5px; padding:1px 5px; margin-left:4px; }

  /* perbandingan */
  .cmp-bar { position:fixed; left:50%; bottom:calc(16px + env(safe-area-inset-bottom,0px)); transform:translateX(-50%); z-index:19; display:none;
    align-items:center; gap:10px; flex-wrap:wrap; background:var(--ink); color:#fff; padding:10px 14px; border-radius:14px; box-shadow:0 8px 24px rgba(0,0,0,.25); font-size:0.88rem; max-width:calc(100% - 24px); }
  .cmp-bar.show { display:flex; }
  .cmp-bar .icon-btn { background:#fff; color:#14213D; border-color:#fff; }
  .cmp-bar .icon-btn:disabled { opacity:.5; }
  :root[data-theme="dark"] .cmp-bar { background:#2A3552; }
  .cmp-grid { grid-template-columns:minmax(0,1fr); }
  .cmp-grid > * { min-width:0; }
  .cmp-chips { display:flex; flex-wrap:wrap; gap:6px; }
  .cmp-chip { display:inline-flex; align-items:center; gap:6px; border:2px solid; border-radius:999px; padding:3px 6px 3px 10px; font-weight:800; font-size:0.86rem; }
  .cmp-chip i { width:10px; height:10px; border-radius:50%; display:inline-block; }
  .cmp-chip button { border:0; background:none; cursor:pointer; font-size:1rem; color:var(--muted); padding:0 2px; }
  .cmp-add { padding:7px 10px; border:1px solid var(--line); border-radius:9px; background:var(--panel); width:150px; }
  .cmp-tbl td, .cmp-tbl th { min-width:150px; }
  .cmp-tbl td:first-child { min-width:170px; }
  .link-btn { border:0; background:none; padding:0; cursor:pointer; color:var(--accent); font:inherit; text-align:left; }
  .sim-self td { background:var(--accent-soft); }
  .sim-add { padding:4px 10px; font-size:0.78rem; }

  /* guide */
  .guide-item { border:1px solid var(--line); border-radius:10px; margin-bottom:8px; overflow:hidden; background:var(--panel); }
  .guide-item summary { cursor:pointer; padding:11px 14px; font-weight:700; font-size:0.9rem; list-style:none; display:flex; gap:8px; align-items:center; }
  .guide-item summary::-webkit-details-marker { display:none; }
  .guide-item summary::before { content:"\25B8"; color:var(--accent); font-size:0.75rem; transition:transform .15s; }
  .guide-item[open] summary::before { transform:rotate(90deg); }
  .guide-item summary:hover { background:var(--panel2); }
  .guide-body { padding:2px 16px 12px 30px; font-size:0.88rem; color:var(--ink2); line-height:1.6; max-width:80ch; }
  .guide-body p { margin:8px 0; }
</style>
</head>
<body>
<header class="navbar" id="navbar">
  <div class="nav-in">
    <div class="brand">
      <h1 class="brand-row"><img class="logo" src="data:image/png;base64,__LOGO96__" alt="" width="40" height="40">
        <span class="brand-name"><span class="nm">Dibalik Saham</span><span class="tg">Research &amp; Insight</span></span>
        <span class="status" id="status-chip">__BADGE__</span></h1>
      <div class="meta">__SUB__</div>
    </div>
    <div class="top-actions">
      <nav class="tabs" aria-label="Halaman">
        <button class="tab-btn" type="button" data-view="screener">Screener</button>
        <button class="tab-btn" type="button" data-view="kalender">Kalender</button>
        <button class="tab-btn" type="button" data-view="jurnal">Jurnal</button>
        <button class="tab-btn" type="button" data-view="panduan">Panduan</button>
      </nav>
      <button class="icon-btn rf-btn" id="rf-btn" type="button" title="Perbarui data (jalankan screener)" aria-label="Perbarui data"><span class="rf-ic" aria-hidden="true">⟳</span><span class="rf-lab">Perbarui</span></button>
      <button class="icon-btn" id="theme-btn" type="button" aria-label="Ganti tema terang atau gelap">Tema gelap</button>
    </div>
  </div>
</header>
<div class="wrap">

  <div class="update-bar" id="update-bar" role="status">
    <span id="update-text">Data baru sudah tersedia.</span>
    <button type="button" id="update-btn">Muat data baru</button>
  </div>

  <div class="view" id="v-screener">
  <section class="market" id="market" aria-label="Kondisi pasar"></section>
  <section class="card" id="movers-card" aria-label="Daftar teratas hari ini">
    <details class="adv filt" id="movers-d"><summary>Daftar teratas hari ini <span class="muted" style="font-weight:500;font-size:0.82rem">· nilai transaksi, naik/turun</span></summary>
      <div id="movers"></div></details>
  </section>

  <section class="card" aria-label="Preset">
    <h2>Pilih gaya screening</h2>
    <div class="presets" id="presets">
      <button class="preset-btn watch-btn" id="watch-btn" type="button" aria-pressed="false">★ Watchlist saya <b id="watch-count">0</b></button>
      <button class="preset-btn" data-preset="reset">Tampilkan semua</button>
      <button class="preset-btn" data-preset="struct">Struktur searah naik</button>
      <button class="preset-btn" data-preset="golden">Tren naik rapi</button>
      <button class="preset-btn" data-preset="quality">Likuid &amp; konsisten</button>
      <button class="preset-btn" data-preset="breakout">Breakout</button>
      <button class="preset-btn" data-preset="allgreen">Kuat di semua timeframe</button>
      <button class="preset-btn" data-preset="reversal">Pantulan dari bawah</button>
      <button class="preset-btn" data-preset="pattern">Ada pola candle</button>
    </div>
    <p class="preset-desc" id="preset-desc"></p>
  </section>

  <section class="card" aria-label="Filter" id="filter-card">
    <div class="top-filters">
      <div class="f search-f"><label for="search">Cari kode atau nama</label><input type="text" id="search" placeholder="mis. BBCA atau Astra" autocomplete="off"></div>
      <div class="f sig-f"><label for="sig-filter">Screener indikator</label><select id="sig-filter"></select></div>
      <div class="f pref-f"><label>Timeframe utama <span class="muted" style="font-weight:500">(disorot &amp; diurutkan)</span></label>
        <div class="pref-row"><div class="seg" id="pref-tf" role="group" aria-label="Timeframe utama"></div>
        <div class="seg" id="pref-dir" role="group" aria-label="Urutan rating"><button type="button" data-dir="-1">Strong Buy → Sell</button><button type="button" data-dir="1">Sell → Strong Buy</button></div></div></div>
    </div>
    <div class="filter-note" id="filter-note" role="status"></div>
    <details class="adv filt" id="filt">
    <summary>Filter pencarian<span class="fcount" id="fcount"></span></summary>
    <div class="filters" style="margin-top:12px">
      <div class="f"><label for="kd-filter">Kondisi</label>
        <select id="kd-filter">
          <option value="">Semua kondisi</option>
          <option value="nobad">Kecuali Hindari dulu</option>
          <option value="zone">Di zona entry</option>
          <option value="notx">Tidak ada transaksi</option>
          <option value="tz">Tunggu ke zona</option>
          <option value="ok">Kandidat kuat</option>
          <option value="wait">Tunggu konfirmasi atau pantulan</option>
          <option value="hot">Tunggu pullback</option>
          <option value="rev">Pantau pembalikan</option>
          <option value="n">Pantau</option>
          <option value="bad">Hindari dulu</option>
        </select></div>
      <div class="f"><label for="sector-filter">Sektor</label><select id="sector-filter"><option value="">Semua sektor</option></select></div>
      <div class="f"><label>Harga (Rp)</label><div class="pair"><input type="number" id="price-min" placeholder="Min" min="0"><input type="number" id="price-max" placeholder="Maks" min="0"></div></div>
      <div class="f"><label>RSI</label><div class="pair"><input type="number" id="rsi-min" placeholder="0" min="0" max="100"><input type="number" id="rsi-max" placeholder="100" min="0" max="100"></div></div>
      <div class="f"><label for="val-min">Min. nilai transaksi (Rp miliar/hari)</label><input type="number" id="val-min" placeholder="mis. 5" min="0" step="0.5"></div>
      <div class="f"><label for="streak-min">Min. hari di Top 10 (dari 10)</label><input type="number" id="streak-min" placeholder="mis. 3" min="0"></div>
    </div>
    <div class="chips">
      <div class="minscore"><label for="min-score">Skor minimum</label><input type="range" id="min-score" min="0" max="100" value="40"><b id="min-score-val">40</b></div>
      <input type="checkbox" id="f-watch" hidden>
      <label class="chip"><input type="checkbox" id="f-trend"> Hanya uptrend</label>
      <label class="chip"><input type="checkbox" id="f-breakout"> Hanya breakout</label>
      <label class="chip"><input type="checkbox" id="f-pattern"> Ada pola candle</label>
      <label class="chip"><input type="checkbox" id="f-confirmed"> Pola terkonfirmasi</label>
      <label class="chip"><input type="checkbox" id="f-allgreen"> Strong Buy D/W/M</label>
      <label class="chip"><input type="checkbox" id="f-ms"> Struktur searah naik</label>
      <label class="chip"><input type="checkbox" id="f-top"> Hanya Top 10 hari ini</label>
    </div>
    <details class="adv" id="adv">
      <summary>Pengaturan lanjutan: bobot skor manual</summary>
      <div class="hint">Cukup pakai preset di atas. Geser slider hanya kalau kamu sudah paham cara skor dihitung, bukan untuk mencari hasil yang terasa cocok.</div>
      <div class="weights">
        <div><label for="w-trend">Trend <b id="w-trend-val">25</b></label><input type="range" id="w-trend" min="0" max="100" value="25"></div>
        <div><label for="w-brk">Breakout <b id="w-brk-val">20</b></label><input type="range" id="w-brk" min="0" max="100" value="20"></div>
        <div><label for="w-pa">Price action <b id="w-pa-val">20</b></label><input type="range" id="w-pa" min="0" max="100" value="20"></div>
        <div><label for="w-mom">Momentum (RSI) <b id="w-mom-val">10</b></label><input type="range" id="w-mom" min="0" max="100" value="10"></div>
        <div><label for="w-st">Struktur SMC (W/D/4H) <b id="w-st-val">25</b></label><input type="range" id="w-st" min="0" max="100" value="25"></div>
      </div>
    </details>
    </details>
  </section>

  <div class="count-row"><div class="count-info" id="count-info" aria-live="polite"></div>
    <label class="chip pin-chip"><input type="checkbox" id="f-pin"> Sematkan Top 10 di atas</label></div>
  <div class="table-wrap">
    <table id="tbl">
      <thead>
        <tr>
          <th class="sticky1 nosort" aria-label="Watchlist">★</th>
          <th class="sticky2" data-key="t">Saham</th>
          <th class="nosort">Chart 30 hari</th>
          <th class="num" data-key="p">Harga</th>
          <th class="num" data-key="chg">Chg%</th>
          <th data-key="score" class="active">Skor</th>
          <th data-key="ck" title="Berapa syarat checklist yang terpenuhi">Checklist</th>
          <th data-key="kdo" title="Label kondisi; klik baris untuk alasannya">Kondisi</th>
          <th data-key="msk" title="Arah struktur SMC Mingguan (W), Harian (D), dan 4 jam (4H)">Struktur</th>
          <th class="nosort" title="Contoh rencana berbasis ATR, bukan rekomendasi">Rencana (contoh)</th>
          <th class="nosort">Sinyal</th>
          <th class="num" data-key="rsi">RSI</th>
          <th class="num" data-key="val">Transaksi/hari</th>
          <th class="num" data-key="v10" title="Nilai transaksi hari ini dibanding rata-rata 10 hari sebelumnya (1,00 = sama dengan rata-rata). Saat sesi berjalan diproyeksikan ke satu hari penuh.">Vol 1D/10D</th>
          <th data-key="sector">Sektor</th>
          <th class="num" data-key="beta" title="Seberapa liar dibanding IHSG">Beta</th>
          <th class="tfc-h1" data-key="tf_h1">1H</th><th class="tfc-h2" data-key="tf_h2">2H</th><th class="tfc-h4" data-key="tf_h4">4H</th>
          <th class="tfc-daily" data-key="tf_daily">Daily</th><th class="tfc-weekly" data-key="tf_weekly">Mingguan</th><th class="tfc-monthly" data-key="tf_monthly">Bulanan</th>
          <th data-key="streak" title="Hari masuk Top 10 (saham transaksi ≥ Rp 5 M) dari 10 hari terakhir">Top 10</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
  <div class="pager">
    <label class="muted" style="font-size:0.84rem;margin-right:auto">Baris per halaman
      <select id="page-size" class="pg-size"><option>25</option><option>50</option><option>100</option></select></label>
    <span class="muted" id="page-info" style="font-size:0.84rem"></span>
    <button id="prev-page" type="button">Sebelumnya</button>
    <button id="next-page" type="button">Berikutnya</button>
  </div>

  </div>

  <div class="view" id="v-kalender" hidden>
  <section class="card" id="makro-card" aria-label="Pasar global dan makro">
    <div class="cal-head"><h2>Pasar global &amp; makro</h2><span class="muted" style="font-size:0.82rem">1 tahun terakhir · klik kartu untuk grafik besar</span></div>
    <div class="makro-grid" id="makro"></div>
    <div id="makro-big"></div>
    <p class="muted" style="font-size:0.78rem;margin:10px 0 0">Data dari Yahoo Finance dan bisa tertunda. <b>Hubungan dengan IHSG</b> adalah korelasi perubahan harian 60 hari terakhir: mendekati +1 berarti biasanya bergerak searah dengan IHSG, mendekati −1 berlawanan arah, mendekati 0 hampir tidak berhubungan. BI Rate dan inflasi Indonesia tidak tersedia di Yahoo, jadi jadwal rilisnya ada di kalender di bawah.</p>
  </section>
  <section class="card cal-card" id="kalender" aria-label="Kalender">
    <div class="cal-head">
      <h2>Kalender</h2>
      <div class="cal-nav">
        <button class="icon-btn" id="cal-prev" type="button" aria-label="Bulan sebelumnya">‹</button>
        <span id="cal-title" class="cal-title"></span>
        <button class="icon-btn" id="cal-next" type="button" aria-label="Bulan berikutnya">›</button>
        <button class="icon-btn" id="cal-today" type="button">Bulan ini</button>
      </div>
      <div class="cal-opts">
        <label class="chip"><input type="checkbox" id="cal-moon"> Fase bulan</label>
        <label class="chip"><input type="checkbox" id="cal-agenda"> Agenda pasar</label>
        <label class="chip"><input type="checkbox" id="cal-makro"> Kalender ekonomi</label>
        <label class="chip"><input type="checkbox" id="cal-musim"> Pola musiman IHSG</label>
      </div>
    </div>
    <div class="cal-today" id="cal-today"></div>
    <p class="cal-musim-sum" id="cal-musim-sum"></p>
    <p class="cal-peaks" id="cal-peaks"></p>
    <div class="cal-grid" id="cal-grid"></div>
    <div class="cal-legend"><span><b class="cal-lean up">▲</b><b class="cal-lean dn">▼</b> condong naik/turun (signifikan)</span><span><b class="cal-lean up">▲+</b> sangat signifikan</span><span><b class="cal-lean up weak">▲</b><b class="cal-lean dn weak">▼</b> lemah, bisa kebetulan</span><span><b class="cal-lean n">·</b> tidak ada kecenderungan</span>
      <span><span class="cal-ev ev-bi">BI</span> <span class="cal-ev ev-fomc">FOMC</span> <span class="cal-ev ev-cpi">CPI AS</span> <span class="cal-ev ev-nfp">NFP AS</span> <span class="cal-ev ev-inflasi">Inflasi RI</span> data ekonomi</span></div>
    <ul class="cal-list" id="cal-list"></ul>
    <p class="muted" style="font-size:0.78rem;margin:10px 0 0">Waktu fase bulan dalam WIB, dihitung dengan rumus astronomi. Agenda MSCI, FTSE, GDX, batas laporan keuangan, BI, The Fed, CPI, dan NFP diambil dari jadwal resmi; tanggal inflasi BPS adalah perkiraan hari kerja pertama bulan. Tanggal bisa berubah, jadi cek pengumuman terbaru. <b>Pola musiman</b> dihitung dari data IHSG 10 tahun: panah tebal berarti persentase hari naik berbeda signifikan dari 50% secara statistik (tingkat keyakinan 95%; "+" untuk 99%), panah samar berarti kecenderungan lemah yang bisa saja kebetulan. Ikon bulan di setiap tanggal menunjukkan bentuk bulan hari itu. Ini pola masa lalu, bukan prediksi. Klik tanggal untuk melihat angkanya.</p>
  </section>

  </div>

  <div class="view" id="v-jurnal" hidden>
  <section class="card" id="jurnal" aria-label="Jurnal trading">
    <div class="cal-head"><h2>Jurnal trading</h2>
      <div class="cal-opts"><button class="icon-btn" id="j-export" type="button">Unduh CSV</button></div></div>
    <div class="plan-box j-stats" id="j-stats"></div>
    <div id="j-setups" style="margin-top:12px"></div>
    <div id="j-list" style="margin-top:12px"></div>
    <p class="muted" style="font-size:0.78rem;margin:10px 0 0">Jurnal tersimpan di browser ini saja, tidak ikut ke GitHub atau perangkat lain. Unduh CSV secara berkala sebagai cadangan. R = hasil dibagi risiko awal (entry − stop loss): +2R berarti untung 2 kali risiko.</p>
  </section>

  </div>

  <div class="view" id="v-panduan" hidden>
  <details class="notice" style="margin-top:18px">
    <summary>Tentang data dan batasan</summary>
    <div>__DISCLAIMER__</div>
  </details>

  <section class="card" id="panduan" style="margin-top:18px">
    <h2>Panduan</h2>
    <p style="font-size:0.88rem;color:var(--muted);margin-top:0">Klik judul untuk membuka penjelasan.</p>
    <details class="guide-item" open>
      <summary>Cara pakai dalam 1 menit</summary>
      <div class="guide-body">
        <p>1. Lihat strip biru tua di atas. Kalau IHSG sedang turun, kurangi agresivitas atau tunggu dulu.</p>
        <p>2. Pilih satu gaya screening, misalnya "Tren naik rapi".</p>
        <p>3. Klik baris saham untuk membuka detailnya di panel kanan. Tombol ‹ › (atau panah kiri/kanan di keyboard) pindah ke saham berikutnya di hasil filter, dan tombol "⤢ Layar penuh" membuka tampilan dua kolom: chart besar dan riwayat di kiri, struktur, rencana, dan checklist di kanan. Tampilan layar penuh punya link sendiri (misalnya …/idx-screener/#s=PTBA) yang bisa di-bookmark.</p>
        <p>4. Tandai saham incaran dengan bintang ☆, lalu klik tombol "★ Watchlist saya" untuk melihat semuanya sekaligus, apa pun filternya.</p>
        <p>5. Kalender, Jurnal, dan Panduan ada di tab kanan atas. Cocokkan dengan chart di aplikasi trading-mu sebelum entry. Checklist yang banyak terpenuhi menambah keyakinan, tapi tidak menjamin harga naik.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Cara menghitung skor</summary>
      <div class="guide-body">
        <p>Skor 0–100 adalah gabungan 5 komponen harian: <b>Trend</b> (harga &gt; MA20, MA20 &gt; MA50, MA50 &gt; MA200, harga &gt; MA200; 25 poin per syarat), <b>Breakout</b> (tembus harga tertinggi 20 hari dan volume di atas rata-rata), <b>Price action</b> (pola candle terakhir), <b>Momentum</b> (zona RSI; 50–70 bernilai penuh), dan <b>Struktur SMC</b> (Mingguan 40, Harian 40, 4 jam 20: penuh kalau bullish, setengah kalau belum jelas, 0 kalau bearish).</p>
        <p>Bobot standar: Trend 25 · Breakout 20 · Price action 20 · Momentum 10 · Struktur 25. Preset memakai bobotnya sendiri, dan bobot bisa diatur manual di "Pengaturan lanjutan". Top 10 selalu memakai bobot standar. Rincian nilai tiap komponen ada di panel detail, bagian "Rincian skor".</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Checklist syarat</summary>
      <div class="guide-body">
        <p>Setiap saham diperiksa terhadap 10 syarat: tren tersusun naik, harga di atas MA200, Daily dan Mingguan Buy, RSI 45–70, volume di atas rata-rata, transaksi ≥ Rp 5 M/hari, 1H tidak Sell, risiko ke stop loss ≤ 7%, IHSG tidak sedang turun, dan struktur SMC Mingguan serta Harian bullish.</p>
        <p>Angka seperti 8/10 berarti 8 dari 10 syarat terpenuhi. Syarat yang datanya tidak ada (misal 1H untuk saham yang transaksinya di bawah Rp 1 M/hari) tidak dihitung. Hijau = minimal 7, kuning = 5–6, merah = di bawah 5.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Smart Money Concepts (SMC) di chart detail</summary>
      <div class="guide-body">
        <p>Panel detail setiap saham menampilkan chart harian (220 candle; tampilan awal 120 candle terakhir, bisa di-zoom) dengan lapisan SMC (kecuali saham yang riwayat harganya masih terlalu pendek). Setiap lapisan bisa dinyalakan atau dimatikan.</p>
        <p><b>BOS</b> (garis penuh): harga menembus swing high/low searah tren, tanda tren berlanjut. <b>CHoCH</b> (garis putus-putus): tembusan pertama yang berlawanan arah, tanda awal pembalikan.<br>
        <b>Order block (OB)</b>: candle terakhir yang berlawanan arah sebelum dorongan yang memicu BOS/CHoCH. Hijau = area permintaan, merah = area penawaran. Yang ditampilkan hanya yang belum ditembus.<br>
        <b>FVG</b>: celah antara candle 1 dan 3 yang belum terisi; harga sering kembali mengisinya.<br>
        <b>EQH/EQL</b>: dua puncak atau dua lembah yang hampir sama tinggi, tempat banyak stop loss berkumpul.<br>
        <b>Premium/discount</b>: separuh atas range 220 hari (relatif mahal) dan separuh bawah (relatif murah), dengan garis EQ di tengah.</p>
        <p>Ini versi sederhana yang dihitung otomatis dari candle harian (swing 5 candle kiri-kanan), jadi bisa berbeda dari indikator SMC di TradingView atau Stockbit. Gunakan sebagai petunjuk area, lalu pastikan di chart aplikasi trading-mu.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Kalender: fase bulan dan agenda pasar</summary>
      <div class="guide-body">
        <p>Bagian Kalender (tombol "Kalender" di kanan atas) menampilkan fase bulan (🌑 bulan baru, 🌓 kuartal awal, 🌕 purnama, 🌗 kuartal akhir) dalam WIB, serta agenda pasar: review MSCI, FTSE, GDX, dan batas penyampaian laporan keuangan. Klik tanggal untuk melihat detailnya; klik kode saham di agenda untuk membuka panel detailnya.</p>
        <p>Fase bulan juga bisa ditampilkan di chart SMC sebagai lingkaran kecil di bawah candle (kuning = purnama, gelap = bulan baru). Penelitian menemukan return rata-rata pasar global sedikit lebih rendah di sekitar purnama dibanding bulan baru, tapi efeknya kecil dan tidak membuktikan fase bulan bisa menentukan titik pembalikan saham tertentu. Pakai sebagai konteks, bukan sinyal utama.</p>
        <p><b>Kalender ekonomi</b> (label ungu): keputusan suku bunga BI, keputusan The Fed (FOMC, ditaruh di tanggal WIB karena diumumkan dini hari), CPI dan NFP Amerika (dirilis malam WIB, dampaknya di BEI keesokan harinya), serta inflasi Indonesia dari BPS. Di hari-hari ini pasar sering bergejolak, jadi pertimbangkan ukuran posisi yang lebih kecil.</p>
        <p><b>Pola musiman IHSG</b> (▲ ▼ · di pojok bawah tanggal): dihitung dari data IHSG 10 tahun berdasarkan hari dalam seminggu dan posisi hari di awal/akhir bulan. ▲ atau ▼ tebal muncul kalau persentase hari naik berbeda signifikan dari 50% secara statistik (95%); "+" berarti sangat signifikan (99%). Panah samar berarti ada sedikit kecenderungan tapi tidak signifikan, jadi bisa saja kebetulan. Klik tanggal untuk melihat angkanya, dan lihat ringkasan kinerja bulan itu di atas kalender. Ini pola masa lalu, bukan ramalan; selisihnya biasanya kecil.</p>
        <p><b>Menambah agenda sendiri:</b> buat file <code>kalender.json</code> di repo berisi daftar seperti <code>[{"tgl": "2026-11-05", "jenis": "lain", "judul": "RUPS XXXX", "ket": "catatan", "saham": ["XXXX"]}]</code>. Jenis bisa msci, ftse, gdx, lapkeu, atau lain. Agenda muncul setelah run berikutnya.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Alur entry berbasis struktur market</summary>
      <div class="guide-body">
        <p><b>1. Arah besar dulu.</b> Lihat kolom Struktur (W = Mingguan, D = Harian, 4H = 4 jam; ▲ bullish, ▼ bearish) atau preset "Struktur searah naik". Idealnya W dan D sama-sama ▲.</p>
        <p><b>2. Tunggu harga ke area bagus.</b> Di chart SMC panel detail, cari order block bullish atau zona discount di bawah harga. Order block yang berada di area volume tinggi (lapisan Volume profile, dekat POC atau value area) biasanya lebih kuat.</p>
        <p><b>3. Konfirmasi di timeframe kecil.</b> Saat harga masuk area itu, tunggu CHoCH naik di 4 jam atau 1 jam (cek di Stockbit/TradingView). Kalau bisa, cek juga broker summary: apakah broker besar sedang akumulasi.</p>
        <p><b>4. Rencana dan ukuran posisi.</b> Di bagian Rencana, pilih "Berbasis struktur (order block)": entry di order block, stop loss sedikit di bawahnya, target di order block bearish berikutnya atau 2 kali risiko. Kalkulator lot menghitung jumlah lot dari risiko per transaksi.</p>
        <p><b>5. Catat dan evaluasi.</b> Klik "Catat ke jurnal", lalu tutup trade dengan harga keluar. Setelah sekitar 30 trade, bagian Jurnal trading menunjukkan setup mana yang benar-benar menghasilkan untukmu.</p>
        <p>Peringatan kuning muncul untuk saham dengan transaksi di bawah Rp 5 M/hari, karena di saham sepi struktur SMC mudah terbentuk oleh sedikit order besar.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Baris Top 10 dan riwayat harian</summary>
      <div class="guide-body">
        <p><b>Baris berwarna kuning</b> dengan label #1 sampai #10 adalah 10 saham dengan skor tertinggi hari ini (bobot standar), hanya dari saham yang benar-benar uptrend: badge Uptrend (MA20 &gt; MA50 &gt; MA200) dan struktur SMC Mingguan serta Harian bullish (W▲ D▲), dengan transaksi minimal Rp 5 M/hari. Kalau yang lolos kurang dari 10, yang tampil memang lebih sedikit. Centang "Hanya Top 10 hari ini" untuk menampilkan kesepuluhnya saja. Kolom Top 10 menghitung berapa hari bursa (dari 10 terakhir) saham itu masuk daftar ini.</p>
        <p><b>Riwayat harian</b> di panel detail menampilkan harga buka, tertinggi, terendah, tutup, perubahan, volume (lot), perkiraan nilai transaksi, dan perbandingan volume dengan rata-rata 20 hari sebelumnya. Baris kuning menandai hari dengan volume minimal 2 kali rata-rata. Riwayat bisa diunduh sebagai CSV.</p>
        <p>Data broker summary (broker pembeli dan penjual) tidak tersedia gratis untuk diambil otomatis, jadi tombol di bawah riwayat membuka halaman saham itu di Stockbit untuk dicek manual.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Bandingkan saham dan saham mirip</summary>
      <div class="guide-body">
        <p><b>Saham mirip:</b> di panel detail, bagian "Saham mirip" menampilkan 5 saham di sektor yang sama dengan pergerakan harga harian paling mirip dalam 60 hari terakhir (korelasi), lengkap dengan kinerja 20 hari, struktur, dan kondisinya. Kalimat di bawahnya memberi tahu apakah saham ini lebih kuat, sejalan, atau tertinggal dari saham-saham miripnya.</p>
        <p><b>Bandingkan:</b> klik "+ Bandingkan" di panel detail (maksimal 4 saham). Bar di bawah layar menampilkan pilihanmu; klik "Buka perbandingan". Halaman perbandingan berisi chart kinerja dalam % sejak titik awal yang sama (20, 60, 120, atau 220 hari) dengan IHSG sebagai pembanding, serta tabel berdampingan: kondisi, struktur W/D/4H, BOS/CHoCH terakhir, posisi premium/discount, order block terdekat, POC, RSI, checklist, dan lainnya. Link halamannya (…/#bandingkan=PTBA,ITMG) bisa dibagikan.</p>
        <p>Saham yang tertinggal dari saham miripnya bisa jadi kandidat menyusul, tapi bisa juga tertinggal karena alasan khusus (berita, kinerja keuangan). Cek dulu sebelum entry.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>MA200, RSI, MACD, dan pasar global</summary>
      <div class="guide-body">
        <p><b>MA20/50/200</b> (lapisan di chart): rata-rata harga 20, 50, dan 200 candle. Harga di atas MA200 menandakan tren jangka panjang naik. MA200 butuh 200 candle sebelumnya, jadi di versi online dihitung dari data tambahan; di timeframe dengan data pendek (misalnya 4H atau bulanan) MA200 bisa belum tersedia.</p>
        <p><b>Geser &amp; zoom skala harga</b>: klik-tahan lalu geser chart ke atas/bawah untuk melihat harga yang lebih tinggi atau rendah; tarik angka di skala harga (kanan) ke atas/bawah atau putar roda mouse di sana (atau Shift + roda mouse) untuk merenggangkan/merapatkan; atau pakai tombol <b>Harga ▲ ▼ ⇕+ ⇕−</b>. <b>Auto</b> (atau ⟲) mengembalikan skala harga otomatis mengikuti candle.</p>
        <p><b>Area prediksi</b>: di kanan candle terakhir ada ruang kosong (awalnya 8 candle, bisa sampai 60). Klik <b>⇥ Area prediksi</b>, tombol ▶, atau geser chart ke kiri untuk memperluasnya, lalu gambar perkiraan arah harga dengan garis, catatan, atau Elliott Wave. Tanggal di area ini adalah perkiraan (hari kerja berikutnya; intraday mengikuti jam bursa). Gambar ditambatkan ke tanggal dan harga, jadi saat candle baru muncul kamu bisa membandingkan prediksi dengan harga sebenarnya.</p>
        <p><b>Alat gambar</b> (baris kedua di atas chart): <b>Garis</b> (klik 2 titik), <b>Horizontal</b> (1 klik, harganya ditampilkan), <b>Catatan</b> (1 klik), dan <b>Elliott Wave</b> (klik titik sebanyak yang dibutuhkan, mulai dari titik awal; akhiri dengan klik dua kali, Enter, atau tombol Selesai; Backspace membatalkan titik terakhir). Gelombang digambar tanpa label; kalau perlu, label bisa ditambahkan sendiri lewat "✎ Label". Setelah selesai, kamu bisa mengisi catatan. Pilih warna dan ketebalan sebelum menggambar, atau klik gambar yang sudah ada lalu ganti warnanya. <b>Magnet</b> membuat titik menempel ke harga tertinggi/terendah candle. Klik gambar untuk memilihnya: tarik bulatan pegangan untuk menggeser satu titik, tarik garisnya untuk memindahkan seluruh gambar, atau klik dua kali untuk mengubah catatan. Untuk menghapus, pilih gambarnya lalu tekan <b>Hapus</b> atau tombol Delete; Esc membatalkan gambar yang sedang dibuat. Untuk Elliott, aplikasi mengecek 3 aturan dasar impuls pada 5 gelombang pertama, pola A–B–C pada 3 gelombang berikutnya, dan menampilkan rasio setiap gelombang terhadap gelombang sebelumnya di bawah chart. Gambar tersimpan di browser per saham dan per timeframe, ditambatkan ke tanggal dan harga, jadi tetap di tempatnya saat chart di-zoom atau datanya diperbarui.</p>
        <p><b>Zoom &amp; geser chart</b>: putar roda mouse di atas chart untuk zoom in/out (berpusat di posisi kursor), klik-tahan lalu geser untuk melihat candle sebelumnya, atau pakai tombol − + ◀ ▶ ⟲ di atas chart. Di HP, cubit dua jari untuk zoom. Skala harga, volume, RSI, dan MACD menyesuaikan dengan candle yang terlihat. Timeframe selain Daily menyimpan sampai 220 candle, jadi bisa di-zoom out lebih jauh.</p>
        <p><b>Volume profile rentang</b> (tombol di atas chart): klik tombolnya, lalu klik-geser di chart dari candle awal ke candle akhir. Histogram volume khusus rentang itu muncul beserta <b>POC</b> (harga paling ramai), <b>VAH</b> dan <b>VAL</b> (batas atas dan bawah value area, tempat 70% volume terjadi). "Pakai rentang dorongan" langsung memilih dorongan naik terakhir yang dipakai konfluensi. Berfungsi di semua timeframe; di HP cukup sentuh lalu geser.</p>
        <p><b>RSI 14</b> (panel di bawah volume): kekuatan kenaikan 0–100. Di atas 70 = sudah panas, di bawah 30 = jenuh jual. <b>MACD 12,26,9</b>: garis biru (MACD) memotong ke atas garis oranye (sinyal) sering dianggap tanda momentum naik; batang hijau/merah adalah selisih keduanya. Nilai keduanya ikut tampil saat kursor di chart.</p>
        <p><b>Analisa emas dalam rupiah</b>: di tab Kalender, klik kartu "Emas (Rp/gram)" lalu "Analisa lengkap". Isinya sama seperti analisa saham (chart candle Daily/Mingguan, SMC, Fibo &amp; konfluensi, volume profile rentang, MA, RSI, MACD) dengan rencana entry/SL/TP dalam Rp/gram. Isi harga beli emas batangan hari ini dari Antam/Pegadaian untuk menerjemahkan angka-angka itu ke harga batangan. Volume memakai jumlah kontrak emas dunia.</p>
        <p><b>Pasar global &amp; makro</b> (di tab Kalender): kurs USD/IDR, indeks dolar, yield obligasi AS 10 tahun, emas, minyak, batubara, tembaga, S&amp;P 500, dan Hang Seng selama 1 tahun, lengkap dengan perubahan 1 hari (1H), 1 bulan (1B), 1 tahun (1T), dan seberapa erat hubungannya dengan IHSG. Klik kartu untuk grafik besar.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Rencana konfluensi (Fibo + volume + SMC) dan huruf K / S / A</summary>
      <div class="guide-body">
        <p><b>Cara kerjanya:</b> aplikasi mengambil dorongan naik terakhir (dari swing low ke puncak setelah BOS/CHoCH naik di Daily), menarik Fibonacci-nya, lalu mencari harga di zona Fibo 0,5–0,786 yang paling banyak ditumpuki faktor lain. Ada 6 faktor: struktur harian bullish, level Fibonacci, volume dorongan (POC atau area ramai dari fixed range volume profile), order block bullish, FVG bullish, dan MA20/MA50.</p>
        <p><b>Entry</b> = zona dengan skor tertinggi. <b>Stop loss</b> = di bawah penahan terdekat (dasar order block, Fibo 0,886, atau swing low), minimal 0,8 ATR dari zona, dan digeser ke bawah EQL kalau ada. <b>Target</b> bertahap: TP1 puncak dorongan, TP2 Fibo 1,272, TP3 Fibo 1,618. Setup dianggap layak kalau skornya minimal 3/6 dan risk:reward ke TP1 minimal 1:1,5.</p>
        <p><b>Pilihan otomatis:</b> kolom Rencana memakai sumber terbaik yang tersedia, ditandai huruf <b>K</b> (konfluensi), <b>S</b> (order block), atau <b>A</b> (ATR). Di panel detail, keempat tombolnya (Otomatis, Konfluensi, Order block, ATR) bisa dipilih untuk membandingkan.</p>
        <p><b>Label Kondisi baru:</b> <b>Di zona entry</b> berarti setup konfluensi layak dan harga sedang di zonanya; tunggu konfirmasi candle hijau atau CHoCH naik di 1H. <b>Tunggu ke zona</b> berarti setup layak tapi harga masih di atas zona; alasannya menyebut jarak zona dari harga.</p>
        <p>Lapisan chart <b>Fibo &amp; konfluensi</b> (Daily) menampilkan garis Fibonacci, zona 0,5–0,786, zona konfluensi, dan POC dorongan. Nyalakan juga lapisan Entry/SL/TP untuk melihat TP1–TP3 dan SL.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Daftar teratas hari ini</summary>
      <div class="guide-body">
        <p>Panel di bawah kondisi pasar berisi 3 daftar 10 saham teratas (hanya saham dengan transaksi ≥ Rp 1 M/hari): <b>Nilai transaksi</b> hari ini, <b>Naik tertinggi</b>, dan <b>Turun terdalam</b>. Klik baris untuk membuka detail sahamnya. Semua angka berasal dari data harga dan volume, bukan perkiraan. Untuk tahu broker mana yang membeli atau menjual, cek broker summary di Stockbit.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Tombol ⟳ Perbarui</summary>
      <div class="guide-body">
        <p>Tombol <b>⟳ Perbarui</b> di navbar menjalankan screener tanpa perlu membuka GitHub. Tanpa pengaturan, tombol ini membuka halaman <i>Run workflow</i> di GitHub. Kalau kamu menghubungkan GitHub sekali (token khusus dengan izin <b>Actions: Read and write</b> untuk repo ini saja), update langsung jalan dari aplikasi dan statusnya tampil di tombol (Antre… / Berjalan… / selesai). Token hanya disimpan di browser yang kamu pakai, tidak di halaman maupun repo. Setelah update selesai, tunggu pemberitahuan "Data baru tersedia".</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Screener indikator, timeframe utama, dan Vol 1D/10D</summary>
      <div class="guide-body">
        <p><b>Screener indikator</b> (dropdown di samping kotak cari) menampilkan saham yang candle terakhirnya memberi sinyal tertentu: <b>Conversion break</b> = harga tutup menembus ke atas garis Conversion Ichimoku (Tenkan-sen, rata-rata harga tertinggi dan terendah 9 candle) di 2H, 1D, atau 1W; <b>Conversion breakdown</b> = menembus ke bawah; <b>EMA21 break/breakdown 1D</b> dan <b>EMA20 break 1W</b> = menembus EMA tersebut; <b>MACD</b> 2H = MACD di atas garis sinyal (atau baru memotong ke atas); <b>Higher TF</b> = struktur SMC Mingguan dan Harian juga bullish. Angka di dalam kurung adalah jumlah saham yang cocok. Saat screener indikator dipilih, filter lain diabaikan. Sinyal 2H hanya untuk saham dengan data intraday (transaksi ≥ Rp 1 M/hari).</p>
        <p><b>Timeframe utama</b>: pilih 1H/2H/4H/D/W/M untuk menyorot kolom rating itu dan mengurutkan tabel dari Strong Buy ke Sell (atau sebaliknya). Kolom rating timeframe juga bisa diklik langsung untuk mengurutkan.</p>
        <p><b>Vol 1D/10D</b>: nilai transaksi hari ini dibanding rata-rata 10 hari sebelumnya (1,00 = sama dengan rata-rata). Oranye kalau ≥ 1,5; saat sesi berjalan diproyeksikan ke satu hari penuh.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Kalkulator lot</summary>
      <div class="guide-body">
        <p>Di panel detail, isi modal dan risiko per transaksi (umumnya 1–2% modal). Kalkulator menghitung jumlah lot supaya kerugian kalau kena stop loss tidak melebihi batas itu. 1 lot = 100 lembar. Isianmu tersimpan di browser ini.</p>
      </div>
    </details>
<details class="guide-item">
      <summary>Preset: Breakout (Breakout Momentum)</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Saham yang harganya menembus (breakout) level harga tertinggi dalam 20 hari terakhir, DAN volume hari itu minimal 1.5x lipat rata-rata volume 20 hari.</p>
        <p><b>Kenapa dipakai:</b> Breakout yang disertai volume tinggi biasanya menandakan ada tekanan beli baru yang cukup kuat (bisa dari investor besar, berita, atau sentimen positif) — ini sering jadi awal dari pergerakan harga yang lebih besar.</p>
        <p><b>Kapan biasanya terjadi:</b> Setelah saham bergerak sideways/konsolidasi cukup lama di rentang harga tertentu, lalu tiba-tiba ada katalis yang mendorong harga menembus resistance dengan volume besar.</p>
        <p><b>Risiko:</b> Ada risiko "false breakout" (breakout palsu) — harga sempat tembus tapi turun lagi, terutama kalau volume pendukungnya tidak benar-benar besar atau kondisi market secara umum sedang lemah.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>Preset: Tren naik rapi (Golden Cross Uptrend)</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Kondisi dimana Moving Average jangka pendek (MA20) berada di atas MA menengah (MA50), yang juga berada di atas MA jangka panjang (MA200) — dan harga saat ini di atas MA20. Susunan MA yang rapi dari pendek ke panjang ini menandakan struktur uptrend yang sehat.</p>
        <p><b>Kenapa dipakai:</b> Ini menyaring saham yang trennya benar-benar naik secara berkelanjutan (bukan cuma lonjakan satu-dua hari). Istilah "Golden Cross" sendiri klasik dipakai saat MA50 memotong ke atas MA200 pertama kali — sering dianggap sinyal bullish jangka menengah-panjang.</p>
        <p><b>Kapan biasanya terjadi:</b> Pada saham yang sudah dalam tren naik cukup lama dan konsisten, biasanya setelah periode akumulasi yang panjang.</p>
        <p><b>Catatan:</b> Sinyal berbasis MA itu sifatnya "lagging" (telat) karena dihitung dari rata-rata historis — jadi kamu kemungkinan besar tidak masuk di harga paling murah, tapi konfirmasi trennya lebih bisa diandalkan.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>Preset: Pantulan dari bawah (Oversold Reversal)</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Kombinasi RSI yang rendah (kondisi oversold/jenuh jual) DENGAN munculnya pola candlestick bullish reversal (Bullish Engulfing, Hammer/Pin Bar, dsb) di candle terakhir.</p>
        <p><b>Kenapa dipakai:</b> RSI rendah menandakan tekanan jual sudah cukup ekstrem, dan pola candle bullish memberi "konfirmasi visual" bahwa pembeli mulai masuk kembali — kombinasi ini sering dipakai untuk menangkap potensi pembalikan arah (rebound).</p>
        <p><b>Kapan biasanya terjadi:</b> Setelah penurunan harga yang cukup tajam atau panjang, ketika muncul tanda-tanda pembeli mulai masuk di harga bawah.</p>
        <p><b>Risiko:</b> Dikenal dengan istilah "menangkap pisau jatuh" (catching a falling knife) — saham oversold bisa saja terus turun lebih dalam kalau tren turunnya masih sangat kuat. Sebaiknya tunggu konfirmasi tambahan sebelum entry.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>Preset: Kuat di semua timeframe</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Saham yang mendapat rating "Strong Buy" secara bersamaan di ketiga timeframe: Daily, Mingguan, DAN Bulanan (dihitung dari gabungan sinyal Moving Average + indikator oscillator di tiap timeframe).</p>
        <p><b>Kenapa dipakai:</b> Kalau sinyal bullish-nya kompak di berbagai skala waktu (jangka pendek, menengah, dan panjang), itu menandakan momentum yang jauh lebih solid dibanding cuma bagus di satu timeframe saja.</p>
        <p><b>Kapan biasanya terjadi:</b> Cukup jarang — biasanya cuma saham-saham dengan tren naik yang sangat kuat dan sudah berlangsung lama di segala skala waktu.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>Preset: Ada pola candle</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Saham yang candle (batang harga) terakhirnya membentuk salah satu dari 3 pola price action bullish berikut:</p>
        <ul style="margin:4px 0 8px 20px;padding:0;">
          <li><b>Bullish Engulfing:</b> candle hijau (naik) yang badannya "menelan" seluruh badan candle merah sebelumnya — menandakan pembeli mengambil alih kendali secara mendadak.</li>
          <li><b>Hammer / Pin Bar:</b> candle dengan badan kecil di bagian atas dan ekor bawah yang panjang — artinya harga sempat jatuh jauh tapi ditutup naik lagi, tanda penolakan harga rendah.</li>
          <li><b>Bullish Marubozu:</b> candle hijau dengan badan penuh nyaris tanpa ekor atas/bawah — artinya beli mendominasi dari awal sampai akhir sesi, momentum sangat kuat.</li>
        </ul>
        <p><b>Kenapa dipakai:</b> Pola-pola ini secara historis sering diasosiasikan dengan potensi pembalikan arah atau penguatan tren naik, tergantung konteksnya.</p>
        <p><b>Kapan biasanya terjadi:</b> Bullish Engulfing & Hammer sering muncul di titik potensi reversal (setelah downtrend), sedangkan Marubozu sering muncul saat momentum beli sedang sangat kuat (misalnya bertepatan dengan breakout).</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>Preset: Likuid &amp; konsisten (Top 10)</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Kombinasi dua filter: (1) nilai transaksi rata-rata 20 hari minimal Rp 5 Miliar/hari, dan (2) saham yang konsisten masuk ranking Top-10 skor selama minimal 3 dari 10 hari run terakhir.</p>
        <p><b>Kenapa dipakai:</b> Nilai transaksi tinggi = saham cukup likuid, gampang masuk/keluar posisi tanpa bikin harga bergerak sendiri (slippage kecil). Konsistensi Top-10 menyaring sinyal yang memang bertahan dari waktu ke waktu, bukan cuma breakout sesaat sehari yang belum tentu berlanjut.</p>
        <p><b>Kapan berguna:</b> Baru kelihatan hasilnya setelah kamu menjalankan script ini beberapa hari berturut-turut, karena histori ranking harian perlu terkumpul dulu.</p>
        <p><b>Catatan:</b> Karena butuh "konsisten beberapa hari", saham yang muncul di sini kadang sudah agak telat masuk fase awal pergerakannya — lebih cocok untuk konfirmasi tren yang sedang berjalan, bukan menangkap breakout paling awal.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>Istilah indikator (RSI, MACD, Stochastic, dan lainnya)</summary>
      <div class="guide-body">
        <p><b>RSI (Relative Strength Index):</b> Mengukur kecepatan & besar perubahan harga, skala 0-100. RSI di bawah 30 biasa dianggap "oversold" (jenuh jual, harga sudah turun banyak), di atas 70 dianggap "overbought" (jenuh beli).</p>
        <p><b>MACD:</b> Membandingkan dua rata-rata bergerak (12 &amp; 26 hari) untuk melihat arah &amp; kekuatan tren. Kalau garis MACD di atas garis sinyalnya, dianggap momentum naik.</p>
        <p><b>Stochastic:</b> Mirip RSI, membandingkan harga penutupan dengan rentang harga tertinggi-terendah dalam periode tertentu untuk mendeteksi jenuh beli/jual.</p>
        <p><b>CCI (Commodity Channel Index) &amp; Williams %R:</b> Indikator oscillator lain yang juga mendeteksi kondisi jenuh beli/jual dengan formula berbeda — dipakai sebagai "suara tambahan" selain RSI/Stochastic supaya sinyalnya lebih meyakinkan kalau beberapa indikator sepakat.</p>
        <p><b>Rating Strong Sell/Sell/Neutral/Buy/Strong Buy:</b> Dihitung dari perbandingan jumlah indikator yang kasih sinyal "beli" vs "jual" — makin banyak yang sepakat searah, makin kuat labelnya (Strong Buy/Strong Sell). Ini pendekatan kami sendiri, bukan rumus resmi dari provider manapun.</p>
        <p><b>Beta:</b> Mengukur seberapa volatil suatu saham dibanding IHSG. Beta &gt; 1 = secara historis bergerak lebih liar dari IHSG (naik/turunnya lebih besar), Beta &lt; 1 = lebih stabil/kalem dibanding IHSG.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>Kolom Kondisi</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Ringkasan otomatis "sebaiknya diapakan dulu" saham ini, dibaca dari tren harian &amp; mingguan, RSI, jarak harga ke MA20, pola candle, dan timeframe 1H/2H. Alasannya tertulis di bawah label.</p>
        <p><b>Di zona entry</b> (hijau penuh): setup konfluensi layak dan harga sedang di zonanya.<br>
        <b>Tunggu ke zona</b> (biru): setup konfluensi layak, tapi harga masih di atas zona.<br>
        <b>Tidak ada transaksi</b> (abu-abu bergaris putus): tidak ada transaksi di hari bursa terakhir, biasanya karena disuspensi BEI. Saham ini tidak diberi rencana, tidak masuk Top 10, dan tidak masuk daftar teratas.<br>
        <b>Kandidat kuat</b> (hijau): tren harian dan mingguan naik, RSI 45–70, transaksi minimal Rp 5 M/hari, dan jangka pendek tidak sedang koreksi.<br>
        <b>Tunggu konfirmasi</b> (kuning): pola candle baru muncul hari ini; tunggu candle berikutnya hijau dan tutup di atas high pola.<br>
        <b>Tunggu pantulan</b> (kuning): tren naik, tapi 1H/2H sedang Sell; tunggu berbalik Buy.<br>
        <b>Tunggu pullback</b> (oranye): RSI di atas 75 atau harga lebih dari 2,5 ATR di atas MA20; rawan koreksi, tunggu turun ke area entry.<br>
        <b>Pantau pembalikan</b> (biru): tren masih turun, tapi pola pembalikan sudah terkonfirmasi.<br>
        <b>Pantau</b> (abu-abu): belum ada arah yang jelas.<br>
        <b>Hindari dulu</b> (merah): tren harian dan mingguan turun, atau transaksi di bawah Rp 500 juta/hari.</p>
        <p><b>Catatan:</b> Kondisi hanya aturan teknikal sederhana, tidak membaca berita atau laporan keuangan.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>Kolom Rencana (contoh)</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Contoh rencana trading yang dihitung dari ATR (Average True Range = rata-rata jarak gerak harga per hari, 14 hari).</p>
        <p><b>Area entry:</b> dari MA20 (atau harga − 1 ATR, mana yang lebih tinggi) sampai harga sekarang. Untuk kondisi "Tunggu pullback", area entry diletakkan di bawah harga sekarang.<br>
        <b>Stop loss (SL):</b> batas bawah area entry dikurangi 1 ATR.<br>
        <b>Target (TP):</b> 2 kali jarak risiko dari tengah area entry (risk:reward 1:2).<br>
        <b>Risiko %:</b> jarak dari tengah area entry ke SL. Semua harga sudah dibulatkan ke fraksi harga BEI.</p>
        <p><b>Catatan:</b> Ini contoh perhitungan, bukan rekomendasi. Cocokkan dengan support/resistance di chart-mu sebelum dipakai, dan sesuaikan jumlah lot supaya kerugian kalau kena SL tetap kecil dibanding modalmu.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>Pola "tunggu" dan "✓ terkonfirmasi"</summary>
      <div class="guide-body">
        <p><b>· tunggu:</b> pola baru terbentuk di candle terakhir. Pola sendirian sering gagal, jadi skor Price Action-nya 70.</p>
        <p><b>✓ terkonfirmasi:</b> pola muncul kemarin, lalu hari ini candle hijau tutup di atas high pola. Skor Price Action 100. Centang "Hanya pola terkonfirmasi" untuk menyaring yang ini saja.</p>
      </div>
    </details>
  </section>
  </div>
</div>

<div class="full" id="full" role="dialog" aria-modal="true" aria-labelledby="d-title"></div>
<div class="full" id="cmpv" role="dialog" aria-modal="true" aria-label="Bandingkan saham"></div>
<div class="cmp-bar" id="cmp-bar" role="region" aria-label="Saham yang akan dibandingkan"></div>
<button type="button" class="to-top" id="to-top" aria-label="Kembali ke paling atas">↑ Ke atas</button>
<div class="rf-pop" id="rf-pop" role="dialog" aria-label="Perbarui data" hidden></div>
<div class="cpop" id="cpop" role="dialog" aria-label="Chart saham" hidden></div>
<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" role="dialog" aria-modal="true" aria-labelledby="d-title" tabindex="-1"></aside>

<script>
const DATA = __DATA__;
const MARKET = __MARKET__;
const GEN = "__GEN__";
let PAGE_SIZE = 25;
const KD_ORDER = { zone: -1, ok: 0, tz: 0.5, rev: 1, wait: 2, hot: 3, n: 4, bad: 5, notx: 6 };
const KD_NAME = { notx: "Tidak ada transaksi", zone: "Di zona entry", tz: "Tunggu ke zona", ok: "Kandidat kuat", wait: "Tunggu", hot: "Tunggu pullback", rev: "Pantau pembalikan", n: "Pantau", bad: "Hindari dulu" };
const PRESETS = {
  struct:   { weights:{trend:20,brk:15,pa:15,mom:10,st:40}, minScore:0, filters:{ms:true}, valMin:5, kd:"nobad",
              desc:"Struktur SMC Mingguan, Harian, dan 4 jam (kalau ada) sama-sama bullish, transaksi minimal Rp 5 M/hari. Cari entry saat harga kembali ke order block bullish atau zona discount, lalu konfirmasi di 1 jam." },
  golden:   { weights:{trend:45,brk:10,pa:10,mom:15,st:20}, minScore:55, filters:{trend:true}, kd:"nobad",
              desc:"Saham dengan susunan MA20 > MA50 > MA200 dan harga di atas MA20. Cocok untuk ikut tren yang sudah terbentuk." },
  quality:  { weights:{trend:25,brk:20,pa:20,mom:10,st:25}, minScore:40, filters:{}, valMin:5, streakMin:3,
              desc:"Transaksi minimal Rp 5 M/hari dan masuk Top 10 minimal 3 dari 10 hari terakhir. Paling aman untuk pemula." },
  breakout: { weights:{trend:15,brk:45,pa:15,mom:5,st:20}, minScore:50, filters:{breakout:true},
              desc:"Harga menembus harga tertinggi 20 hari dengan volume minimal 1,5 kali rata-rata. Waspada breakout palsu." },
  allgreen: { weights:{trend:20,brk:20,pa:20,mom:20,st:20}, minScore:0, filters:{allgreen:true},
              desc:"Daily, Mingguan, dan Bulanan sama-sama Strong Buy. Sering sudah mahal, perhatikan RSI." },
  reversal: { weights:{trend:10,brk:10,pa:40,mom:40,st:0}, minScore:35, filters:{pattern:true, confirmed:true}, rsiMax:45,
              desc:"RSI rendah dengan pola pembalikan yang sudah terkonfirmasi. Lebih berisiko; penurunan bisa berlanjut." },
  pattern:  { weights:{trend:15,brk:15,pa:50,mom:10,st:10}, minScore:40, filters:{pattern:true},
              desc:"Candle terakhir membentuk pola bullish. Pola berlabel \"tunggu\" belum terkonfirmasi." },
  reset:    { weights:{trend:25,brk:20,pa:20,mom:10,st:25}, minScore:40, filters:{},
              desc:"Semua saham dengan skor minimal 40, tanpa filter tambahan." },
};
const STORE = "idxs:v2", WATCH = "idxs:watch", CALC = "idxs:calc", THEME = "idxs:theme";
const $ = id => document.getElementById(id);
const ls = {
  get(k, d) { try { const v = localStorage.getItem(k); return v === null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch (e) {} },
};

let page = 0, sortKey = "score", sortDir = -1, activePreset = "golden", openT = null;
let watch = new Set(ls.get(WATCH, []));

/* ---------- format ---------- */
function fmtNum(n) { return (n === null || n === undefined) ? "-" : Number(n).toLocaleString("id-ID", { maximumFractionDigits: 0 }); }
function fmtDec(n, d = 1) { return Number(n).toLocaleString("id-ID", { minimumFractionDigits: d, maximumFractionDigits: d }); }
function fmtValue(v) {
  if (v >= 1e12) return "Rp " + fmtDec(v / 1e12, 2) + " T";
  if (v >= 1e9) return "Rp " + fmtDec(v / 1e9, 1) + " M";
  if (v >= 1e6) return "Rp " + fmtNum(v / 1e6) + " jt";
  return "Rp " + fmtNum(v);
}
function esc(s) { return String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c])); }
function vClass(v) { return v === "Strong Buy" ? "sb" : v === "Buy" ? "b" : v === "Strong Sell" ? "ss" : v === "Sell" ? "s" : "n"; }
const isUp = v => v === "Buy" || v === "Strong Buy";
const isDown = v => v === "Sell" || v === "Strong Sell";

/* ---------- checklist ---------- */
function checklist(r) {
  const tf = r.tf || {}, x = r.x || {};
  const ihsgDown = MARKET.ihsg ? isDown(MARKET.ihsg.d) : null;
  const items = [
    ["Tren tersusun naik (MA20 > MA50 > MA200, harga di atas MA20)", !!r.trendOk],
    ["Harga di atas MA200 (tren jangka panjang naik)", x.ma200 ? r.p > x.ma200 : null],
    ["Daily dan Mingguan sama-sama Buy", tf.daily && tf.weekly ? isUp(tf.daily.summary) && isUp(tf.weekly.summary) : null],
    ["RSI di zona sehat 45–70 (RSI " + fmtDec(r.rsi, 1) + ")", r.rsi >= 45 && r.rsi <= 70],
    ["Volume hari ini di atas rata-rata 20 hari (" + fmtDec(r.vr, 2) + "×)", r.vr >= 1],
    ["Likuid: transaksi minimal Rp 5 M/hari (" + fmtValue(r.val) + ")", r.val >= 5e9],
    ["Jangka pendek (1H) tidak sedang Sell", tf.h1 ? !isDown(tf.h1.summary) : null],
    ["Risiko ke stop loss maksimal 7%" + (r.plan ? " (" + fmtDec(r.plan.risk, 1) + "%)" : ""), r.plan ? r.plan.risk <= 7 : null],
    ["IHSG tidak sedang dalam tren turun", ihsgDown === null ? null : !ihsgDown],
    ["Struktur SMC Mingguan dan Harian sama-sama bullish", r.ms && r.ms.w && r.ms.d ? r.ms.w.tr === 1 && r.ms.d.tr === 1 : null],
  ];
  const ev = items.filter(i => i[1] !== null);
  return { items, pass: ev.filter(i => i[1]).length, total: ev.length };
}
DATA.forEach(r => { if (r.smc && !r.ohlc) r.ohlc = r.smc.b.slice(-30); });
DATA.forEach(r => {
  const c = checklist(r);
  r._ck = c; r.ck = c.total ? c.pass / c.total + c.pass / 1000 : 0;
  r.kdo = r.kd ? -KD_ORDER[r.kd.c] : -9;
  r.streak = r.cst ? r.cst.streak : 0;
  const ms = r.ms || {}; r.msk = (ms.w ? ms.w.tr : 0) * 1.01 + (ms.d ? ms.d.tr : 0) + (ms.h4 ? ms.h4.tr : 0) * 0.99;
});

/* ---------- theme ---------- */
function applyTheme(t) {
  if (t) document.documentElement.setAttribute("data-theme", t); else document.documentElement.removeAttribute("data-theme");
  const dark = t ? t === "dark" : (window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches);
  $("theme-btn").textContent = dark ? "Tema terang" : "Tema gelap";
}
applyTheme(ls.get(THEME, null));
$("theme-btn").addEventListener("click", () => {
  const cur = document.documentElement.getAttribute("data-theme") || ((window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light");
  const next = cur === "dark" ? "light" : "dark";
  ls.set(THEME, next); applyTheme(next);
});

/* ---------- market strip ---------- */
function renderMarket() {
  const m = MARKET.ihsg, b = MARKET.breadth;
  let a = `<div class="m-ihsg${m ? " clickable" : ""}" ${m ? 'role="button" tabindex="0" id="ihsg-card" aria-label="Buka detail IHSG"' : ""}><div class="m-label">IHSG${m ? ' <span class="m-hint">Klik untuk detail</span>' : ""}</div>`;
  if (m) {
    const up = m.chg >= 0;
    const trend = m.p > m.ma20 && m.p > m.ma50 ? "di atas MA20 dan MA50" : m.p < m.ma20 && m.p < m.ma50 ? "di bawah MA20 dan MA50" : "di antara MA20 dan MA50";
    const say = isDown(m.d) ? "Pasar sedang lemah. Kurangi ukuran posisi atau tunggu dulu."
      : isUp(m.d) ? "Pasar mendukung. Tetap pasang stop loss." : "Pasar belum punya arah jelas. Pilih saham dengan checklist tinggi saja.";
    a += `<div class="m-row"><span class="m-big">${fmtDec(m.p, 2)}</span><span class="m-chg ${up ? "up" : "down"}">${up ? "+" : ""}${fmtDec(m.chg, 2)}%</span></div>
      <div class="m-say">Harga ${trend}, ringkasan teknikal ${m.d}${m.rsi ? ", RSI " + fmtDec(m.rsi, 1) : ""}. ${say}</div>`;
  } else a += '<div class="m-say">Data IHSG tidak tersedia di run ini.</div>';
  a += "</div>";
  let br = '<div><div class="m-label">Napas pasar</div>';
  if (b) br += `<div class="m-big">${b.pct}%</div><div class="breadth-bar"><i style="width:${b.pct}%"></i></div>
      <div class="m-say">dari ${fmtNum(b.n)} saham likuid berada di atas MA20. ${b.pct >= 60 ? "Mayoritas saham sedang naik." : b.pct <= 40 ? "Mayoritas saham sedang turun." : "Pasar terbelah."}</div>`;
  else br += '<div class="m-say">Belum ada data.</div>';
  br += "</div>";
  const cnt = {}; DATA.forEach(r => { if (r.kd) cnt[r.kd.c] = (cnt[r.kd.c] || 0) + 1; });
  let kc = '<div><div class="m-label">Kondisi semua saham (klik untuk menyaring)</div><div class="kd-counts">';
  ["zone", "tz", "ok", "wait", "hot", "rev", "n", "bad", "notx"].forEach(k => { if (cnt[k]) kc += `<button class="kd-count" data-kd="${k}" type="button">${KD_NAME[k]}<b>${cnt[k]}</b></button>`; });
  kc += "</div></div>";
  $("market").innerHTML = a + br + kc;
  const ic = $("ihsg-card");
  if (ic) { ic.addEventListener("click", openIhsg); ic.addEventListener("keydown", e => { if (e.key === "Enter") openIhsg(); }); }
  document.querySelectorAll(".kd-count").forEach(btn => btn.addEventListener("click", () => {
    const turnOff = $("kd-filter").value === btn.dataset.kd;
    applyPreset("reset", true);
    $("min-score").value = 0; $("min-score-val").textContent = "0";
    $("kd-filter").value = turnOff ? "" : btn.dataset.kd;
    page = 0; save(); render();
  }));
}

/* ---------- small charts ---------- */
function candleSvg(ohlc) {
  if (!ohlc || ohlc.length < 2) return "";
  const w = 120, h = 40, px = 2, py = 3, n = ohlc.length;
  const max = Math.max(...ohlc.map(c => c[1])), min = Math.min(...ohlc.map(c => c[2])), rg = (max - min) || 1;
  const sw = (w - px * 2) / n, bw = Math.max(1.2, sw * 0.6), y = v => h - py - ((v - min) / rg) * (h - py * 2);
  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="${w}" height="${h}" aria-hidden="true">` + ohlc.map((c, i) => {
    const [o, hi, lo, cl] = c, x = px + i * sw + sw / 2, col = cl >= o ? "var(--up)" : "var(--down)";
    const top = Math.min(y(o), y(cl)), bh = Math.max(1, Math.abs(y(cl) - y(o)));
    return `<line x1="${x.toFixed(1)}" y1="${y(hi).toFixed(1)}" x2="${x.toFixed(1)}" y2="${y(lo).toFixed(1)}" stroke="${col}" stroke-width="1"/><rect x="${(x - bw / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" fill="${col}"/>`;
  }).join("") + "</svg>";
}

function bigChart(r) {
  const o = r.ohlc || [], n = o.length; if (n < 2) return "";
  const W = 520, H = 250, L = 8, R = 74, T = 12, B = 14, x = r.x || {}, p = r.plan;
  const vals = o.flatMap(c => [c[1], c[2]]);
  (x.m20 || []).forEach(v => v && vals.push(v)); (x.m50 || []).forEach(v => v && vals.push(v));
  if (p) vals.push(p.sl, p.tp, p.e1, p.e2);
  let max = Math.max(...vals), min = Math.min(...vals); const pad = (max - min) * 0.04 || 1; max += pad; min -= pad;
  const sw = (W - L - R) / n, bw = Math.max(2, sw * 0.62);
  const y = v => T + (max - v) / (max - min) * (H - T - B), cx = i => L + i * sw + sw / 2;
  let s = `<svg class="d-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chart 30 hari ${esc(r.t)}">`;
  if (p) {
    s += `<rect x="${L}" y="${y(p.e2).toFixed(1)}" width="${W - L - R}" height="${Math.max(2, y(p.e1) - y(p.e2)).toFixed(1)}" fill="var(--accent)" opacity="0.12"/>`;
    const line = (v, col, lab) => `<line x1="${L}" x2="${W - R}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${col}" stroke-width="1.4" stroke-dasharray="5 4"/><text x="${W - R + 6}" y="${(y(v) + 4).toFixed(1)}" font-size="11" font-weight="700" fill="${col}">${lab} ${fmtNum(v)}</text>`;
    s += line(p.tp, "var(--up)", "TP") + line(p.sl, "var(--down)", "SL");
    s += `<text x="${W - R + 6}" y="${((y(p.e1) + y(p.e2)) / 2 + 4).toFixed(1)}" font-size="11" font-weight="700" fill="var(--accent)">Entry</text>`;
  }
  o.forEach((c, i) => {
    const [op, hi, lo, cl] = c, col = cl >= op ? "var(--up)" : "var(--down)", top = Math.min(y(op), y(cl));
    s += `<line x1="${cx(i).toFixed(1)}" x2="${cx(i).toFixed(1)}" y1="${y(hi).toFixed(1)}" y2="${y(lo).toFixed(1)}" stroke="${col}"/><rect x="${(cx(i) - bw / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(1, Math.abs(y(cl) - y(op))).toFixed(1)}" fill="${col}"/>`;
  });
  const path = (arr, col) => {
    const pts = (arr || []).map((v, i) => v ? `${cx(i).toFixed(1)},${y(v).toFixed(1)}` : null).filter(Boolean);
    return pts.length > 1 ? `<polyline points="${pts.join(" ")}" fill="none" stroke="${col}" stroke-width="1.8"/>` : "";
  };
  s += path(x.m20, "var(--blue)") + path(x.m50, "var(--orange)");
  const last = o[n - 1][3], taken = p ? [y(p.tp), y(p.sl), (y(p.e1) + y(p.e2)) / 2] : [];
  if (taken.every(v => Math.abs(v - y(last)) > 13)) s += `<text x="${W - R + 6}" y="${(y(last) + 4).toFixed(1)}" font-size="11" fill="var(--ink2)">${fmtNum(last)}</text>`;
  s += "</svg>";
  return s;
}

/* ---------- cells ---------- */
function verdictCell(k, tf) {
  const d = tf && tf[k]; if (!d) return '<span class="muted">-</span>';
  return `<span class="v ${vClass(d.summary)}" title="MA: ${esc(d.ma)} (${esc(d.ma_detail)}) | Indikator: ${esc(d.ind)} (${esc(d.ind_detail)})">${esc(d.summary)}</span>`;
}
function badges(r) {
  const b = [];
  if (r.trendOk) b.push('<span class="badge trend">Uptrend</span>');
  if (r.brkOk) b.push('<span class="badge breakout">Breakout</span>');
  if (r.pattern) b.push(r.pk === "ok" ? `<span class="badge pattern ok" title="Sudah dikonfirmasi candle hijau">${esc(r.pattern)} ✓</span>`
    : `<span class="badge pattern" title="Belum terkonfirmasi">${esc(r.pattern)} · tunggu</span>`);
  return b.join("") || '<span class="muted">-</span>';
}
function ckCell(r) {
  const c = r._ck; if (!c.total) return '<span class="muted">-</span>';
  const cls = c.pass >= 7 ? "hi" : c.pass >= 5 ? "mid" : "lo";
  return `<span class="ck ${cls}">${c.pass}/${c.total}</span>`;
}
function planCell(r) {
  const p = r.plan; if (!p) return '<span class="muted">-</span>';
  const SRC = { K: "Konfluensi (Fibo + volume + SMC)", S: "Order block", A: "ATR" };
  return `<div class="plan">${p.src ? `<span class="src src-${p.src}" title="Sumber rencana: ${SRC[p.src]}">${p.src}</span>` : ""}Entry <b>${fmtNum(p.e1)}–${fmtNum(p.e2)}</b><br><span class="sl">SL ${fmtNum(p.sl)}</span> · <span class="tp">TP ${fmtNum(p.tp)}</span></div>`;
}

/* ---------- state ---------- */
const FIELDS = ["search", "kd-filter", "sector-filter", "price-min", "price-max", "rsi-min", "rsi-max", "val-min", "streak-min"];
const CHECKS = ["f-watch", "f-trend", "f-breakout", "f-pattern", "f-confirmed", "f-allgreen", "f-ms", "f-top"];
const W = ["w-trend", "w-brk", "w-pa", "w-mom", "w-st"];
function save() {
  const s = { preset: activePreset, sortKey, sortDir, page, min: $("min-score").value, f: {}, c: {}, w: {} };
  FIELDS.forEach(id => s.f[id] = $(id).value); CHECKS.forEach(id => s.c[id] = $(id).checked); W.forEach(id => s.w[id] = $(id).value);
  ls.set(STORE, s);
}
function load() {
  const s = ls.get(STORE, null); if (!s) { applyPreset("golden", true); return; }
  activePreset = s.preset; sortKey = s.sortKey || "score"; sortDir = s.sortDir || -1; page = s.page || 0;
  FIELDS.forEach(id => { if (s.f && s.f[id] !== undefined) $(id).value = s.f[id]; });
  CHECKS.forEach(id => { if (id !== "f-watch" && s.c && s.c[id] !== undefined) $(id).checked = s.c[id]; });   // mode watchlist tidak dibawa ke kunjungan berikutnya
  W.forEach(id => { if (s.w && s.w[id] !== undefined) { $(id).value = s.w[id]; $(id + "-val").textContent = s.w[id]; } });
  $("min-score").value = s.min ?? 40; $("min-score-val").textContent = $("min-score").value;
  markPreset();
}
function markPreset() {
  const wOn = $("f-watch").checked;
  document.querySelectorAll(".preset-btn[data-preset]").forEach(b => b.classList.toggle("active", !wOn && b.dataset.preset === activePreset));
  $("preset-desc").textContent = wOn ? "Semua saham yang kamu tandai bintang, tanpa filter apa pun. Tanda bintang tersimpan di browser ini."
    : activePreset && PRESETS[activePreset] ? PRESETS[activePreset].desc : "Pengaturan manual.";
  document.querySelectorAll("thead th").forEach(th => { th.classList.toggle("active", th.dataset.key === sortKey); th.classList.toggle("asc", th.dataset.key === sortKey && sortDir === 1); });
}
function applyPreset(name, silent) {
  const p = PRESETS[name]; if (!p) return;
  activePreset = name;
  $("w-trend").value = p.weights.trend; $("w-brk").value = p.weights.brk; $("w-pa").value = p.weights.pa; $("w-mom").value = p.weights.mom; $("w-st").value = p.weights.st ?? 25;
  W.forEach(id => $(id + "-val").textContent = $(id).value);
  $("min-score").value = p.minScore; $("min-score-val").textContent = p.minScore;
  const f = p.filters || {};
  $("f-trend").checked = !!f.trend; $("f-breakout").checked = !!f.breakout; $("f-pattern").checked = !!f.pattern;
  $("f-confirmed").checked = !!f.confirmed; $("f-allgreen").checked = !!f.allgreen; $("f-ms").checked = !!f.ms; $("f-top").checked = !!f.top;
  $("rsi-max").value = p.rsiMax ?? ""; $("rsi-min").value = ""; $("price-min").value = ""; $("price-max").value = "";
  $("val-min").value = p.valMin ?? ""; $("streak-min").value = p.streakMin ?? ""; $("kd-filter").value = p.kd || "";
  $("search").value = ""; $("f-watch").checked = false; $("sector-filter").value = "";
  sortKey = "score"; sortDir = -1; page = 0;
  markPreset(); if (!silent) { save(); render(); }
}

/* ---------- render table ---------- */
function weights() { return { trend: +$("w-trend").value, brk: +$("w-brk").value, pa: +$("w-pa").value, mom: +$("w-mom").value, st: +$("w-st").value }; }
function score(r, w) { const t = w.trend + w.brk + w.pa + w.mom + w.st; return t ? (r.trend * w.trend + r.brk * w.brk + r.pa * w.pa + r.mom * w.mom + (r.st ?? 50) * w.st) / t : 0; }
function allGreen(tf) { return tf && tf.daily && tf.weekly && tf.monthly && [tf.daily, tf.weekly, tf.monthly].every(d => d.summary === "Strong Buy"); }
function num(id) { return parseFloat($(id).value); }

function filtered() {
  const w = weights(), q = $("search").value.trim().toUpperCase(), kd = $("kd-filter").value;
  const pmin = num("price-min"), pmax = num("price-max"), rmin = num("rsi-min"), rmax = num("rsi-max"), vmin = num("val-min"), smin = num("streak-min");
  const RK = { "Strong Buy": 2, "Buy": 1, "Neutral": 0, "Sell": -1, "Strong Sell": -2 };
  const rk = (r, k) => r.tf && r.tf[k] ? RK[r.tf[k].summary] ?? null : null;
  let rows = DATA.map(r => ({ ...r, score: score(r, w), tf_h1: rk(r, "h1"), tf_h2: rk(r, "h2"), tf_h4: rk(r, "h4"), tf_daily: rk(r, "daily"), tf_weekly: rk(r, "weekly"), tf_monthly: rk(r, "monthly") }));
  const sig = $("sig-filter").value;
  if (q) {   // pencarian selalu menemukan saham yang dicari, filter lain diabaikan
    rows = rows.filter(r => r.t.includes(q) || (r.nm || "").toUpperCase().includes(q));
    rows.sort((a, b) => (b.t === q) - (a.t === q) || (b.t.startsWith(q)) - (a.t.startsWith(q)) || b.score - a.score);
    return rows;
  }
  if ($("f-watch").checked) {   // watchlist: tampilkan semua saham bertanda bintang, filter lain diabaikan
    rows = rows.filter(r => watch.has(r.t));
  } else if ($("f-top").checked) {   // Top 10 hari ini: selalu 10 saham, filter lain diabaikan
    rows = rows.filter(r => r.top);
  } else if (sig) {                   // screener indikator: filter lain diabaikan
    rows = rows.filter(r => SIG_DEF[sig] && SIG_DEF[sig][1](r));
  } else {
  rows = rows.filter(r => r.score >= +$("min-score").value);
  if ($("f-trend").checked) rows = rows.filter(r => r.trendOk);
  if ($("f-breakout").checked) rows = rows.filter(r => r.brkOk);
  if ($("f-pattern").checked) rows = rows.filter(r => r.pattern);
  if ($("f-confirmed").checked) rows = rows.filter(r => r.pk === "ok");
  if ($("f-allgreen").checked) rows = rows.filter(r => allGreen(r.tf));
  if ($("f-ms").checked) rows = rows.filter(msAligned);
  if (!isNaN(pmin)) rows = rows.filter(r => r.p >= pmin);
  if (!isNaN(pmax)) rows = rows.filter(r => r.p <= pmax);
  if (!isNaN(rmin)) rows = rows.filter(r => r.rsi >= rmin);
  if (!isNaN(rmax)) rows = rows.filter(r => r.rsi <= rmax);
  if (!isNaN(vmin)) rows = rows.filter(r => r.val >= vmin * 1e9);
  if (!isNaN(smin)) rows = rows.filter(r => r.streak >= smin);
  if (q) rows = rows.filter(r => r.t.includes(q) || (r.nm || "").toUpperCase().includes(q));
  const sec = $("sector-filter").value;
  if (sec) rows = rows.filter(r => (r.sector || "-") === sec);
  if (kd === "nobad") rows = rows.filter(r => !r.kd || r.kd.c !== "bad");
  else if (kd) rows = rows.filter(r => r.kd && r.kd.c === kd);
  }
  rows.sort((a, b) => {
    const av = a[sortKey], bv = b[sortKey];
    if (typeof av === "string") return sortDir * av.localeCompare(bv);
    return sortDir * ((av ?? -1e18) - (bv ?? -1e18));
  });
  return rows;
}

function rowHtml(r) {
  return `<tr data-t="${r.t}" tabindex="0"${r.top ? ' class="top10"' : ""}>
      <td class="sticky1"><button class="star ${watch.has(r.t) ? "on" : ""}" data-star="${r.t}" type="button" aria-label="Watchlist ${r.t}" aria-pressed="${watch.has(r.t)}">★</button></td>
      <td class="sticky2"><div class="tk">${r.t}${r.top ? `<span class="top-badge" title="Top 10 hari ini: peringkat ${r.top} (skor bobot standar, hanya saham uptrend dengan struktur W▲ D▲ dan transaksi minimal Rp 5 M/hari)">#${r.top}</span>` : ""}</div><div class="tk-name" title="${esc(r.nm)}">${esc(r.nm) || "&nbsp;"}</div></td>
      <td class="spark-cell" data-sp="${r.t}" title="Arahkan kursor untuk chart lebih besar, klik untuk menahannya">${candleSvg(r.ohlc)}</td>
      <td class="num">${fmtNum(r.p)}</td>
      <td class="num ${r.chg >= 0 ? "pos" : "neg"}">${r.chg >= 0 ? "+" : ""}${fmtDec(r.chg, 2)}%</td>
      <td><span class="score"><b>${fmtDec(r.score, 0)}</b><span class="score-bar"><i style="width:${Math.min(100, r.score)}%"></i></span></span></td>
      <td>${ckCell(r)}</td>
      <td>${r.kd ? `<span class="kd ${r.kd.c}" title="${esc(r.kd.why)}">${esc(r.kd.l)}</span>` : "-"}</td>
      <td>${msCell(r)}</td>
      <td>${planCell(r)}</td>
      <td>${badges(r)}</td>
      <td class="num">${fmtDec(r.rsi, 1)}</td>
      <td class="num">${fmtValue(r.val)}</td>
      <td class="num">${r.v10 == null ? '<span class="muted">-</span>' : `<span class="${r.v10 >= 1.5 ? "v10-hi" : r.v10 < 0.7 ? "muted" : ""}">${fmtDec(r.v10, 2)}</span>`}</td>
      <td>${r.sector && r.sector !== "-" ? esc(r.sector) : '<span class="muted">-</span>'}</td>
      <td class="num">${r.beta == null ? '<span class="muted">-</span>' : fmtDec(r.beta, 2)}</td>
      <td class="tfc-h1">${verdictCell("h1", r.tf)}</td><td class="tfc-h2">${verdictCell("h2", r.tf)}</td><td class="tfc-h4">${verdictCell("h4", r.tf)}</td>
      <td class="tfc-daily">${verdictCell("daily", r.tf)}</td><td class="tfc-weekly">${verdictCell("weekly", r.tf)}</td><td class="tfc-monthly">${verdictCell("monthly", r.tf)}</td>
      <td>${r.cst && r.cst.total ? `${r.cst.count}/${r.cst.total}` : '<span class="muted">-</span>'}</td>
    </tr>`;
}
const SIG_DEF = {
  cb2hm:  ["Conversion break 2H + MACD", r => r.ind && r.ind.cb2h === 1 && r.ind.m2h === 1],
  cb2hmh: ["Conversion break 2H + MACD + Higher TF", r => r.ind && r.ind.cb2h === 1 && r.ind.m2h === 1 && r.ms && r.ms.w && r.ms.w.tr === 1 && r.ms.d && r.ms.d.tr === 1],
  mc2h:   ["MACD cross naik 2H", r => r.ind && r.ind.mc2h === 1],
  cb1d:   ["Conversion break 1D", r => r.ind && r.ind.cb1d === 1],
  cb1w:   ["Conversion break 1W", r => r.ind && r.ind.cb1w === 1],
  cbd1d:  ["Conversion breakdown 1D", r => r.ind && r.ind.cb1d === -1],
  e21:    ["EMA21 break 1D", r => r.ind && r.ind.e21 === 1],
  e21d:   ["EMA21 breakdown 1D", r => r.ind && r.ind.e21 === -1],
  e20w:   ["EMA20 break 1W", r => r.ind && r.ind.e20w === 1],
};
const SIG_DESC = {
  cb2hm: "Candle 2 jam terakhir tutup menembus ke atas garis Conversion Ichimoku (Tenkan-sen 9), dan MACD 2 jam sedang di atas garis sinyal. Hanya untuk saham dengan data intraday (transaksi ≥ Rp 1 M/hari).",
  cb2hmh: "Sama seperti Conversion break 2H + MACD, ditambah struktur SMC Mingguan dan Harian sama-sama bullish (timeframe besar searah).",
  mc2h: "Garis MACD memotong ke atas garis sinyal dalam 3 candle 2 jam terakhir.",
  cb1d: "Candle harian terakhir tutup menembus ke atas garis Conversion Ichimoku (Tenkan-sen: rata-rata harga tertinggi dan terendah 9 hari).",
  cb1w: "Candle mingguan terakhir tutup menembus ke atas garis Conversion Ichimoku mingguan.",
  cbd1d: "Candle harian terakhir tutup menembus ke bawah garis Conversion: tanda melemah.",
  e21: "Candle harian terakhir tutup menembus ke atas EMA 21.",
  e21d: "Candle harian terakhir tutup menembus ke bawah EMA 21: tanda melemah.",
  e20w: "Candle mingguan terakhir tutup menembus ke atas EMA 20 mingguan.",
};
const PREF_TF = [["h1", "1H"], ["h2", "2H"], ["h4", "4H"], ["daily", "D"], ["weekly", "W"], ["monthly", "M"]];
let prefTF = ls.get("idxs:preftf", ""), prefDir = ls.get("idxs:prefdir", -1);
function renderPref() {
  $("pref-tf").innerHTML = `<button type="button" data-ptf="" class="${prefTF ? "" : "on"}">Tidak ada</button>` + PREF_TF.map(([k, n]) => `<button type="button" data-ptf="${k}" class="${prefTF === k ? "on" : ""}">${n}</button>`).join("");
  document.querySelectorAll("#pref-dir [data-dir]").forEach(b => { b.classList.toggle("on", +b.dataset.dir === prefDir); b.disabled = !prefTF; });
  document.body.dataset.pref = prefTF || "";
  $("pref-tf").querySelectorAll("[data-ptf]").forEach(b => b.addEventListener("click", () => {
    prefTF = b.dataset.ptf; ls.set("idxs:preftf", prefTF);
    if (prefTF) { sortKey = "tf_" + prefTF; sortDir = prefDir; } else { sortKey = "score"; sortDir = -1; }
    page = 0; renderPref(); save(); markPreset(); render();
  }));
}
document.querySelectorAll("#pref-dir [data-dir]").forEach(b => b.addEventListener("click", () => {
  prefDir = +b.dataset.dir; ls.set("idxs:prefdir", prefDir);
  if (prefTF) { sortKey = "tf_" + prefTF; sortDir = prefDir; page = 0; save(); markPreset(); render(); }
  renderPref();
}));
function renderSigOptions() {
  const cnt = k => DATA.filter(r => !r.notx && SIG_DEF[k][1](r)).length;
  $("sig-filter").innerHTML = `<option value="">Semua (tanpa screener indikator)</option>` + Object.keys(SIG_DEF).map(k => `<option value="${k}">${esc(SIG_DEF[k][0])} (${cnt(k)})</option>`).join("");
}
const PIN_KEY = "idxs:pin";
function pinActive() {
  return $("f-pin").checked && !$("search").value.trim() && !$("f-watch").checked && !$("f-top").checked && !$("sig-filter").value;
}
function displayRows() {
  let rows = filtered(), pinned = [];
  if (pinActive()) {
    const w = weights();
    pinned = DATA.filter(r => r.top).map(r => ({ ...r, score: score(r, w) })).sort((a, b) => a.top - b.top);
    rows = rows.filter(r => !r.top);
  }
  return { pinned, rows };
}
function render() {
  const { pinned, rows } = displayRows();
  const watchOn = $("f-watch").checked && !$("search").value.trim();
  $("watch-btn").classList.toggle("on", watchOn); $("watch-btn").setAttribute("aria-pressed", watchOn);
  $("watch-count").textContent = watch.size;
  const topOn = !watchOn && $("f-top").checked && !$("search").value.trim();
  $("filter-card").classList.toggle("dim", watchOn || topOn || !!$("search").value.trim() || !!$("sig-filter").value);
  const note = $("filter-note");
  const sg = $("sig-filter").value;
  note.textContent = $("search").value.trim() ? "Pencarian aktif: filter pencarian di bawah tidak dipakai sampai kotak cari dikosongkan."
    : sg ? `Screener indikator "${SIG_DEF[sg][0]}": ${SIG_DESC[sg]} Filter lain diabaikan; pilih "Semua" untuk kembali.`
    : watchOn ? "Mode Watchlist aktif: filter pencarian tidak dipakai. Klik preset mana saja untuk kembali."
    : topOn ? "Mode Top 10 aktif: filter pencarian tidak dipakai. Hapus centang Hanya Top 10 untuk kembali." : "";
  note.classList.toggle("show", !!note.textContent);
  const nAct = ["kd-filter", "sector-filter", "price-min", "price-max", "rsi-min", "rsi-max", "val-min", "streak-min"].filter(id => $(id).value !== "").length
    + ["f-trend", "f-breakout", "f-pattern", "f-confirmed", "f-allgreen", "f-ms", "f-top"].filter(id => $(id).checked).length;
  $("fcount").textContent = nAct ? `${nAct} aktif` : "";
  $("count-info").textContent = $("search").value.trim()
    ? `${fmtNum(rows.length)} hasil pencarian. Pencarian mengabaikan filter lain. Hapus isi kotak cari untuk kembali ke filter.`
    : watchOn ? `Watchlist-mu: ${fmtNum(rows.length)} saham. Filter lain diabaikan. Klik preset mana saja untuk kembali.`
    : topOn ? `Top 10 hari ini: ${fmtNum(rows.length)} saham (skor bobot standar, hanya saham uptrend dengan struktur W▲ D▲, transaksi minimal Rp 5 M/hari). Filter lain diabaikan; hapus centang untuk kembali.`
    : `${fmtNum(rows.length + (pinActive() ? DATA.filter(r => r.top).length : 0))} saham ditampilkan dari ${fmtNum(DATA.length)}${pinActive() ? " (Top 10 disematkan di atas)" : ""}. Klik baris untuk melihat detail.`;
  document.querySelectorAll(".kd-count").forEach(b => b.classList.toggle("on", b.dataset.kd === $("kd-filter").value));
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  page = Math.min(Math.max(0, page), pages - 1);
  const slice = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
  if (page > 0) pinned.length = 0;              // blok Top 10 hanya di halaman pertama
  if (!slice.length && !pinned.length) {
    $("tbody").innerHTML = $("search").value.trim()
      ? `<tr><td colspan="23" class="empty">Kode atau nama "${esc($("search").value.trim())}" tidak ada di data run ini. Mungkin saham itu baru IPO, sedang disuspensi, atau datanya gagal diambil dari Yahoo.</td></tr>`
      : watchOn ? `<tr><td colspan="23" class="empty">Watchlist masih kosong. Klik bintang ☆ di samping kode saham untuk menambahkannya.</td></tr>`
      : `<tr><td colspan="23" class="empty">Tidak ada saham yang cocok dengan filter ini.<br><button class="icon-btn" type="button" id="empty-reset">Tampilkan semua saham</button></td></tr>`;
    const er = $("empty-reset"); if (er) er.addEventListener("click", e => { e.stopPropagation(); applyPreset("reset"); });
  } else {
    const grp = (txt, cls = "") => `<tr class="grp ${cls}"><td colspan="23"><span>${txt}</span></td></tr>`;
    const topOpen = ls.get("idxs:topopen", true);
    $("tbody").innerHTML = (pinned.length ? grp(`<button type="button" class="grp-toggle" aria-expanded="${topOpen}">${topOpen ? "▾" : "▸"} Top 10 hari ini${pinned.length < 10 ? ` (${pinned.length} saham lolos syarat uptrend)` : ""}</button> <span class="muted">· ${topOpen ? "disematkan di atas, urut peringkat. Klik untuk menutup" : `${pinned.length} saham disembunyikan. Klik untuk membuka`}</span>`, "grp-top") + (topOpen ? pinned.map(rowHtml).join("") : "")
      + grp(`Hasil filter <span class="muted">· ${fmtNum(rows.length)} saham lain</span>`) : "") + slice.map(rowHtml).join("");
  }
  $("page-info").textContent = `Halaman ${page + 1} dari ${pages}`;
  $("prev-page").disabled = page <= 0; $("next-page").disabled = page >= pages - 1;
}

/* ---------- fase bulan (Meeus, Astronomical Algorithms bab 49) ---------- */
function moonPhaseUTC(k) {
  const rad = Math.PI / 180, T = k / 1236.85, T2 = T * T, T3 = T2 * T, T4 = T3 * T;
  let jde = 2451550.09766 + 29.530588861 * k + 0.00015437 * T2 - 0.00000015 * T3 + 0.00000000073 * T4;
  const E = 1 - 0.002516 * T - 0.0000074 * T2;
  const M = (2.5534 + 29.1053567 * k - 0.0000014 * T2 - 0.00000011 * T3) * rad;
  const Mp = (201.5643 + 385.81693528 * k + 0.0107582 * T2 + 0.00001238 * T3 - 0.000000058 * T4) * rad;
  const F = (160.7108 + 390.67050284 * k - 0.0016118 * T2 - 0.00000227 * T3 + 0.000000011 * T4) * rad;
  const Om = (124.7746 - 1.56375588 * k + 0.0020672 * T2 + 0.00000215 * T3) * rad;
  const s = Math.sin, c = Math.cos, f = Math.round((k - Math.floor(k)) * 4) % 4;
  let d;
  if (f === 0 || f === 2) {
    const n = f === 0;
    d = (n ? -0.4072 : -0.40614) * s(Mp) + (n ? 0.17241 : 0.17302) * E * s(M) + (n ? 0.01608 : 0.01614) * s(2 * Mp)
      + (n ? 0.01039 : 0.01043) * s(2 * F) + (n ? 0.00739 : 0.00734) * E * s(Mp - M) - (n ? 0.00514 : 0.00515) * E * s(Mp + M)
      + (n ? 0.00208 : 0.00209) * E * E * s(2 * M) - 0.00111 * s(Mp - 2 * F) - 0.00057 * s(Mp + 2 * F) + 0.00056 * E * s(2 * Mp + M)
      - 0.00042 * s(3 * Mp) + 0.00042 * E * s(M + 2 * F) + 0.00038 * E * s(M - 2 * F) - 0.00024 * E * s(2 * Mp - M) - 0.00017 * s(Om)
      - 0.00007 * s(Mp + 2 * M) + 0.00004 * s(2 * Mp - 2 * F) + 0.00004 * s(3 * M) + 0.00003 * s(Mp + M - 2 * F) + 0.00003 * s(2 * Mp + 2 * F)
      - 0.00003 * s(Mp + M + 2 * F) + 0.00003 * s(Mp - M + 2 * F) - 0.00002 * s(Mp - M - 2 * F) - 0.00002 * s(3 * Mp + M) + 0.00002 * s(4 * Mp);
  } else {
    d = -0.62801 * s(Mp) + 0.17172 * E * s(M) - 0.01183 * E * s(Mp + M) + 0.00862 * s(2 * Mp) + 0.00804 * s(2 * F)
      + 0.00454 * E * s(Mp - M) + 0.00204 * E * E * s(2 * M) - 0.0018 * s(Mp - 2 * F) - 0.0007 * s(Mp + 2 * F) - 0.0004 * s(3 * Mp)
      - 0.00034 * E * s(2 * Mp - M) + 0.00032 * E * s(M + 2 * F) + 0.00032 * E * s(M - 2 * F) - 0.00028 * E * E * s(Mp + 2 * M)
      + 0.00027 * E * s(2 * Mp + M) - 0.00017 * s(Om) - 0.00005 * s(Mp - M - 2 * F) + 0.00004 * s(2 * Mp + 2 * F)
      - 0.00004 * s(Mp + M + 2 * F) + 0.00004 * s(Mp - 2 * M) + 0.00003 * s(Mp + M - 2 * F) + 0.00003 * s(3 * M)
      + 0.00002 * s(2 * Mp - 2 * F) + 0.00002 * s(Mp - M + 2 * F) - 0.00002 * s(3 * Mp + M);
    const W = 0.00306 - 0.00038 * E * c(M) + 0.00026 * c(Mp) - 0.00002 * c(Mp - M) + 0.00002 * c(Mp + M) + 0.00002 * c(2 * F);
    d += f === 1 ? W : -W;
  }
  const A = [[299.77, 0.107408, 0.000325], [251.88, 0.016321, 0.000165], [251.83, 26.651886, 0.000164], [349.42, 36.412478, 0.000126],
    [84.66, 18.206239, 0.00011], [141.74, 53.303771, 0.000062], [207.14, 2.453732, 0.00006], [154.84, 7.30686, 0.000056],
    [34.52, 27.261239, 0.000047], [207.19, 0.121824, 0.000042], [291.34, 1.844379, 0.00004], [161.72, 24.198154, 0.000037],
    [239.56, 25.513099, 0.000035], [331.55, 3.592518, 0.000023]];
  let add = 0; A.forEach(([a, b, amp], i) => add += amp * s((a + b * k - (i === 0 ? 0.009173 * T2 : 0)) * rad));
  jde += d + add - 69 / 86400;                        // TT -> UT (ΔT ≈ 69 detik)
  return new Date((jde - 2440587.5) * 86400000);
}
/* daftar fase (0=bulan baru, 1=kuartal awal, 2=purnama, 3=kuartal akhir) antara dua tanggal */
function moonPhases(from, to) {
  const out = [], y = from.getUTCFullYear() + from.getUTCMonth() / 12;
  let k = Math.floor((y - 2000) * 12.3685) - 1;
  for (; ; k++) {
    for (let q = 0; q < 4; q++) {
      const t = moonPhaseUTC(k + q / 4);
      if (t > to) return out;
      if (t >= from) out.push({ t, q });
    }
  }
}

/* ---------- kalender (fase bulan + agenda pasar) ---------- */
const AGENDA = __AGENDA__;
const MOON_NAME = ["Bulan baru", "Kuartal awal", "Purnama", "Kuartal akhir"];
const MOON_ICON = ["🌑", "🌓", "🌕", "🌗"];
const JENIS = { msci: "MSCI", ftse: "FTSE", gdx: "GDX", lapkeu: "Lapkeu", lain: "Agenda", bi: "BI", fomc: "FOMC", cpi: "CPI AS", nfp: "NFP AS", inflasi: "Inflasi RI" };
const MAKRO = new Set(["bi", "fomc", "cpi", "nfp", "inflasi"]);
const HARI_PANJANG = ["Minggu", "Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu"];
/* pola musiman IHSG: panah hanya muncul kalau berbeda signifikan dari 50% (uji binomial, |z| ≥ 1,96) */
function musimHari(key) {
  const M = MARKET.musim; if (!M) return null;
  const [yy, mm, dd] = key.split("-").map(Number), dt = new Date(Date.UTC(yy, mm - 1, dd)), wd = dt.getUTCDay();
  if (wd === 0 || wd === 6) return null;
  const hk = []; const last = new Date(Date.UTC(yy, mm, 0)).getUTCDate();
  for (let d = 1; d <= last; d++) { const w = new Date(Date.UTC(yy, mm - 1, d)).getUTCDay(); if (w !== 0 && w !== 6) hk.push(d); }
  const pF = hk.indexOf(dd) + 1, pL = hk.length - hk.indexOf(dd);
  const cands = [[`Hari ${HARI_PANJANG[wd]}`, M.wd[wd - 1]]];
  if (pF <= 3) cands.push([`Hari bursa ke-${pF} di awal bulan`, M.tom["f" + pF]]);
  if (pL <= 3) cands.push([pL === 1 ? "Hari bursa terakhir bulan" : `Hari bursa ke-${pL} dari akhir bulan`, M.tom["l" + pL]]);
  const ev = cands.filter(c => c[1] && c[1].n >= 30).map(([lab, st]) => { const pr = st.up / st.n; return { lab, st, pr, z: (pr - 0.5) / Math.sqrt(0.25 / st.n) }; });
  if (!ev.length) return null;
  const best = ev.slice().sort((a, b) => Math.abs(b.z) - Math.abs(a.z))[0];
  const az = Math.abs(best.z), dir = best.z > 0 ? 1 : -1;
  const lean = az >= 1.96 ? dir : 0, kuat = az >= 2.58, lemah = az < 1.96 && az >= 0.6 ? dir : 0;
  return { lean, kuat, lemah, best, all: ev };
}
function musimTeks(st) { return `naik ${fmtDec(st.up / st.n * 100, 0)}% dari ${fmtNum(st.n)} kali, rata-rata ${st.avg >= 0 ? "+" : ""}${fmtDec(st.avg, 2)}%`; }
const BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
const CAL_KEY = "idxs:cal";
const WIB_MS = 7 * 3600000;
const ymd = d => new Date(d.getTime() + WIB_MS).toISOString().slice(0, 10);          // tanggal WIB dari waktu UTC
const hm = d => new Date(d.getTime() + WIB_MS).toISOString().slice(11, 16);
let cal = Object.assign({ moon: true, agenda: true, makro: true, musim: true }, ls.get(CAL_KEY, {}));
let calMonth = (() => { const t = new Date(Date.now() + WIB_MS); return [t.getUTCFullYear(), t.getUTCMonth()]; })();
let calSel = null;

const SYNODIC = 29.530588853;
function moonSvg(age, size = 22) {          // age: umur bulan dalam hari sejak bulan baru
  const p = ((age % SYNODIC) + SYNODIC) % SYNODIC / SYNODIC, r = size / 2 - 1, c = size / 2;
  const illum = (1 - Math.cos(2 * Math.PI * p)) / 2, rx = r * Math.abs(Math.cos(2 * Math.PI * p));
  const lit = "#EFE7CF", dark = "var(--moon-dark)";
  let path = "";
  if (illum > 0.02 && illum < 0.98) {
    const wax = p < 0.5, cres = p < 0.25 || p > 0.75;
    path = wax
      ? `M${c},${c - r} A${r},${r} 0 0 1 ${c},${c + r} A${rx},${r} 0 0 ${cres ? 0 : 1} ${c},${c - r} Z`
      : `M${c},${c - r} A${r},${r} 0 0 0 ${c},${c + r} A${rx},${r} 0 0 ${cres ? 1 : 0} ${c},${c - r} Z`;
  }
  return `<svg class="moon-ic" width="${size}" height="${size}" viewBox="0 0 ${size} ${size}" aria-hidden="true">
    <circle cx="${c}" cy="${c}" r="${r}" fill="${illum >= 0.98 ? lit : dark}" stroke="var(--moon-line)" stroke-width="0.8"/>
    ${path ? `<path d="${path}" fill="${lit}"/>` : ""}</svg>`;
}
function moonAgeAt(t, newMoons) { let last = null; for (const nm of newMoons) { if (nm <= t) last = nm; else break; } return last ? (t - last) / 86400000 : null; }
function calData(y, m) {
  const from = new Date(Date.UTC(y, m, 1) - WIB_MS - 86400000), to = new Date(Date.UTC(y, m + 1, 1) - WIB_MS + 86400000);
  const moons = {}; moonPhases(from, to).forEach(p => { (moons[ymd(p.t)] = moons[ymd(p.t)] || []).push(p); });
  const nms = moonPhases(new Date(from.getTime() - 32 * 86400000), to).filter(p => p.q === 0).map(p => p.t.getTime());
  const ev = {}; AGENDA.forEach(a => { (ev[a.tgl] = ev[a.tgl] || []).push(a); });
  return { moons, ev, nms };
}

function renderCal() {
  const [y, m] = calMonth, { moons, ev, nms } = calData(y, m);
  const today = ymd(new Date()), first = new Date(Date.UTC(y, m, 1)), days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  const lead = (first.getUTCDay() + 6) % 7;             // Senin = kolom pertama
  $("cal-title").textContent = `${BULAN_ID[m]} ${y}`;
  $("cal-moon").checked = cal.moon; $("cal-agenda").checked = cal.agenda; $("cal-makro").checked = cal.makro; $("cal-musim").checked = cal.musim;
  const MS = MARKET.musim;
  // B1: kartu hari ini
  (() => {
    const box = $("cal-today"); if (!box) return;
    const tglTxt = k => { const d = new Date(k + "T00:00:00Z"); return `${d.getUTCDate()} ${BULAN_ID[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
    const now = new Date(Date.now() + WIB_MS), key = now.toISOString().slice(0, 10), wd = now.getUTCDay();
    const evs = (AGENDA || []).filter(a => a.tgl === key);
    const evTxt = evs.length ? ` · Agenda: ${evs.map(a => esc(a.judul)).join("; ")}` : "";
    if (wd === 0 || wd === 6) { box.innerHTML = `<b>Hari ini (${HARI_PANJANG[wd]}, ${tglTxt(key)}):</b> bursa tutup.${evTxt}`; return; }
    const ms = cal.musim ? musimHari(key) : null;
    if (!ms) { box.innerHTML = `<b>Hari ini (${tglTxt(key)}).</b>${evTxt}`; return; }
    const d = ms.lean || ms.lemah, arah = d > 0 ? "naik" : d < 0 ? "turun" : "", cls = d > 0 ? "pos" : d < 0 ? "neg" : "";
    const kuat = ms.lean ? (ms.kuat ? "sangat signifikan" : "signifikan") : ms.lemah ? "lemah, bisa kebetulan" : "";
    box.innerHTML = `<b>Hari ini (${HARI_PANJANG[wd]}, ${tglTxt(key)}):</b> ${d ? `IHSG secara historis condong <b class="${cls}">${arah}</b> (${kuat})` : "tidak ada kecenderungan musiman"}.
      <span class="muted">${ms.all.map(x => `${esc(x.lab)}: ${esc(musimTeks(x.st))}`).join(" · ")}</span>${evTxt}`;
  })();
  // B3: tanggal condong naik/turun terkuat di bulan yang dibuka
  (() => {
    const box = $("cal-peaks"); if (!box) return;
    if (!cal.musim || !MARKET.musim) { box.innerHTML = ""; return; }
    const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate(), arr = [];
    for (let dd = 1; dd <= last; dd++) { const k = `${y}-${String(m + 1).padStart(2, "0")}-${String(dd).padStart(2, "0")}`, ms = musimHari(k); if (ms) arr.push({ dd, z: ms.best.z, sig: !!ms.lean }); }
    const pick = (sgn) => arr.filter(a => sgn * a.z >= 0.6).sort((a, b) => sgn * (b.z - a.z)).slice(0, 4).sort((a, b) => a.dd - b.dd);
    const fmt = l => l.map(a => `${a.dd}${a.sig ? "" : "*"}`).join(", ");
    const up = pick(1), dn = pick(-1);
    box.innerHTML = up.length || dn.length ? `${up.length ? `<span class="pos">▲ Condong naik terkuat: ${fmt(up)}</span>` : ""}${up.length && dn.length ? " &nbsp;·&nbsp; " : ""}${dn.length ? `<span class="neg">▼ Condong turun terkuat: ${fmt(dn)}</span>` : ""}${[...up, ...dn].some(a => !a.sig) ? ' <span class="muted">(* = lemah, bisa kebetulan)</span>' : ""}` : "";
  })();
  $("cal-musim-sum").innerHTML = cal.musim && MS && MS.mon[m] && MS.mon[m].n ? (() => { const st = MS.mon[m];
    return `<b>${BULAN_ID[m]} secara historis</b> (${esc(MS.dari.slice(0, 4))}–${esc(MS.sampai.slice(0, 4))}): IHSG naik di ${st.up} dari ${st.n} tahun, rata-rata ${st.avg >= 0 ? "+" : ""}${fmtDec(st.avg, 2)}% sebulan.`; })() : "";
  let h = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"].map(d => `<div class="cal-dow">${d}</div>`).join("");
  for (let i = 0; i < lead; i++) h += '<div class="cal-cell empty"></div>';
  for (let d = 1; d <= days; d++) {
    const key = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`, wd = (lead + d - 1) % 7;
    const mo = cal.moon ? (moons[key] || []) : [], es = (ev[key] || []).filter(a => MAKRO.has(a.jenis) ? cal.makro : cal.agenda);
    const ms = cal.musim ? musimHari(key) : null;
    h += `<button type="button" class="cal-cell${wd >= 5 ? " weekend" : ""}${key === today ? " today" : ""}${key === calSel ? " sel" : ""}" data-day="${key}">
      <span class="cal-d">${d}</span>
      ${cal.moon ? (() => { const age = moonAgeAt(Date.UTC(y, m, d, 5), nms); if (age == null) return "";
        const il = Math.round((1 - Math.cos(2 * Math.PI * (age / SYNODIC))) / 2 * 100);
        return `<span class="cal-moonic" title="Umur bulan ${fmtDec(age, 1)} hari, bagian bulan yang terang ${il}%${mo.length ? `. ${mo.map(p => MOON_NAME[p.q] + " " + hm(p.t) + " WIB").join(", ")}` : ""}">${moonSvg(age)}</span>`; })() : ""}
      ${mo.filter(p => p.q === 0 || p.q === 2).map(p => `<span class="cal-moon-lab">${MOON_NAME[p.q]} ${hm(p.t)}</span>`).join("")}
      ${es.map(a => `<span class="cal-ev ev-${esc(a.jenis)}" title="${esc(a.judul)}">${esc(JENIS[a.jenis] || JENIS.lain)}</span>`).join("")}
      ${ms ? (() => { const d = ms.lean || ms.lemah, cls = d > 0 ? "up" : d < 0 ? "dn" : "n";
        return `<span class="cal-lean ${cls}${!ms.lean && ms.lemah ? " weak" : ""}" title="${esc(ms.best.lab)}: ${esc(musimTeks(ms.best.st))}${!ms.lean && ms.lemah ? " (lemah, bisa kebetulan)" : ""}">${d > 0 ? "▲" : d < 0 ? "▼" : "·"}${ms.kuat ? "+" : ""}</span>`; })() : ""}
    </button>`;
  }
  $("cal-grid").innerHTML = h;
  $("cal-grid").querySelectorAll("[data-day]").forEach(b => b.addEventListener("click", () => { calSel = calSel === b.dataset.day ? null : b.dataset.day; renderCal(); }));
  // daftar di bawah grid
  const prefix = `${y}-${String(m + 1).padStart(2, "0")}`;
  const items = [];
  if (cal.moon) Object.entries(moons).forEach(([k, arr]) => { if (k.startsWith(prefix)) arr.forEach(p => items.push({ tgl: k, moon: p })); });
  AGENDA.forEach(a => { if (a.tgl.startsWith(prefix) && (MAKRO.has(a.jenis) ? cal.makro : cal.agenda)) items.push({ tgl: a.tgl, ev: a }); });
  if (calSel && cal.musim) { const ms = musimHari(calSel); if (ms) items.push({ tgl: calSel, musim: ms }); }
  const list = items.filter(i => !calSel || i.tgl === calSel).sort((a, b) => a.tgl.localeCompare(b.tgl) || (a.moon ? -1 : 1));
  const tglTxt = k => { const [yy, mm, dd] = k.split("-").map(Number); const w = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"][new Date(Date.UTC(yy, mm - 1, dd)).getUTCDay()]; return `${w}, ${dd} ${BULAN_ID[mm - 1].slice(0, 3)}`; };
  $("cal-list").innerHTML = list.length ? list.map(i => i.musim
    ? `<li><span class="cl-date">${tglTxt(i.tgl)}</span><span class="cl-body"><b>Pola musiman IHSG:</b> ${i.musim.lean ? `condong <b class="${i.musim.lean > 0 ? "pos" : "neg"}">${i.musim.lean > 0 ? "naik" : "turun"}</b>${i.musim.kuat ? " (kuat)" : " (signifikan)"}` : i.musim.lemah ? `sedikit condong ${i.musim.lemah > 0 ? "naik" : "turun"}, tapi <b>lemah</b> (tidak signifikan, bisa kebetulan)` : "tidak ada kecenderungan"}.<br>${i.musim.all.map(x => `<span class="muted">${esc(x.lab)}: ${esc(musimTeks(x.st))}.</span>`).join("<br>")}</span></li>`
    : i.moon
    ? `<li><span class="cl-date">${tglTxt(i.tgl)}</span><span class="cl-body"><b><span class="cl-moon">${moonSvg([0, 7.38, 14.77, 22.15][i.moon.q], 16)}</span> ${MOON_NAME[i.moon.q]}</b> <span class="muted">${hm(i.moon.t)} WIB</span></span></li>`
    : `<li><span class="cl-date">${tglTxt(i.tgl)}</span><span class="cl-body"><span class="cal-ev ev-${esc(i.ev.jenis)}">${esc(JENIS[i.ev.jenis] || JENIS.lain)}</span> <b>${esc(i.ev.judul)}</b>${i.ev.ket ? `<br><span class="muted">${esc(i.ev.ket)}</span>` : ""}${(i.ev.saham || []).length ? `<br>${i.ev.saham.map(t => `<button type="button" class="tk-chip" data-open="${esc(t)}">${esc(t)}</button>`).join("")}` : ""}</span></li>`).join("")
    : `<li class="muted">${calSel ? "Tidak ada fase bulan atau agenda di tanggal ini." : "Tidak ada agenda bulan ini."}</li>`;
  $("cal-list").querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () => {
    if (DATA.some(r => r.t === b.dataset.open)) openDrawer(b.dataset.open);
  }));
}
$("cal-prev").addEventListener("click", () => { calMonth = calMonth[1] === 0 ? [calMonth[0] - 1, 11] : [calMonth[0], calMonth[1] - 1]; calSel = null; renderCal(); });
$("cal-next").addEventListener("click", () => { calMonth = calMonth[1] === 11 ? [calMonth[0] + 1, 0] : [calMonth[0], calMonth[1] + 1]; calSel = null; renderCal(); });
$("cal-today").addEventListener("click", () => { const t = new Date(Date.now() + WIB_MS); calMonth = [t.getUTCFullYear(), t.getUTCMonth()]; calSel = null; renderCal(); });
["cal-moon", "cal-agenda", "cal-makro", "cal-musim"].forEach(id => $(id).addEventListener("change", () => { cal.moon = $("cal-moon").checked; cal.agenda = $("cal-agenda").checked; cal.makro = $("cal-makro").checked; cal.musim = $("cal-musim").checked; ls.set(CAL_KEY, cal); renderCal(); }));

/* ---------- SMC di browser (untuk timeframe selain Daily; algoritma sama dengan versi Python) ---------- */
function smcJS(b, v, L = 5, win = 120) {
  const n = b.length; if (n < 30) return null;
  const o = b.map(x => x[0]), h = b.map(x => x[1]), l = b.map(x => x[2]), c = b.map(x => x[3]);
  const tr = c.map((_, i) => i ? Math.max(h[i] - l[i], Math.abs(h[i] - c[i - 1]), Math.abs(l[i] - c[i - 1])) : h[i] - l[i]);
  let a = tr.slice(0, 14).reduce((s, x) => s + x, 0) / Math.min(14, n); for (let i = 14; i < n; i++) a = a + (tr[i] - a) / 14;
  a = a || 1;
  const mx = (arr, i0, i1) => Math.max(...arr.slice(i0, i1)), mn = (arr, i0, i1) => Math.min(...arr.slice(i0, i1));
  const pH = [], pL = [];
  for (let i = L; i < n - L; i++) {
    if (h[i] >= mx(h, i - L, i + L + 1) && h[i] > mx(h, i - L, i)) pH.push(i);
    if (l[i] <= mn(l, i - L, i + L + 1) && l[i] < mn(l, i - L, i)) pL.push(i);
  }
  const kH = new Map(pH.map(i => [i + L, i])), kL = new Map(pL.map(i => [i + L, i]));
  let lastH = null, lastL = null, tren = 0; const ev = [], obs = [];
  for (let i = 0; i < n; i++) {
    if (kH.has(i)) lastH = [kH.get(i), h[kH.get(i)], false];
    if (kL.has(i)) lastL = [kL.get(i), l[kL.get(i)], false];
    if (lastH && !lastH[2] && c[i] > lastH[1]) {
      ev.push([lastH[0], i, lastH[1], tren === -1 ? "CHoCH" : "BOS", 1]); tren = 1; lastH[2] = true;
      let k = null; for (let j = i - 1; j >= lastH[0]; j--) if (c[j] < o[j]) { k = j; break; }
      if (k === null) { k = lastH[0]; for (let j = lastH[0]; j < i; j++) if (l[j] < l[k]) k = j; }
      obs.push([k, h[k], l[k], 1, false]);
    }
    if (lastL && !lastL[2] && c[i] < lastL[1]) {
      ev.push([lastL[0], i, lastL[1], tren === 1 ? "CHoCH" : "BOS", -1]); tren = -1; lastL[2] = true;
      let k = null; for (let j = i - 1; j >= lastL[0]; j--) if (c[j] > o[j]) { k = j; break; }
      if (k === null) { k = lastL[0]; for (let j = lastL[0]; j < i; j++) if (h[j] > h[k]) k = j; }
      obs.push([k, h[k], l[k], -1, false]);
    }
    obs.forEach(ob => { if (!ob[4] && ob[0] < i && ((ob[3] === 1 && c[i] < ob[2]) || (ob[3] === -1 && c[i] > ob[1]))) ob[4] = true; });
  }
  let fvg = [];
  for (let i = 2; i < n; i++) {
    if (l[i] > h[i - 2] && l[i] - h[i - 2] > 0.15 * a) fvg.push([i - 1, l[i], h[i - 2], 1]);
    else if (h[i] < l[i - 2] && l[i - 2] - h[i] > 0.15 * a) fvg.push([i - 1, l[i - 2], h[i], -1]);
  }
  fvg = fvg.filter(g => !(g[0] + 2 < n && (g[3] === 1 ? mn(l, g[0] + 2, n) <= g[2] : mx(h, g[0] + 2, n) >= g[1])));
  const eq = [];
  [[pH, h, "EQH"], [pL, l, "EQL"]].forEach(([arr, src, nm]) => { for (let q = 1; q < arr.length; q++) if (Math.abs(src[arr[q - 1]] - src[arr[q]]) <= 0.1 * a) eq.push([arr[q - 1], arr[q], (src[arr[q - 1]] + src[arr[q]]) / 2, nm]); });
  win = Math.min(win, n); const s0 = n - win, cl = i => Math.max(0, i - s0);
  let vp = null;
  if (v && v.some(x => x > 0)) {
    const vlo = mn(l, s0, n), vhi = mx(h, s0, n), NB = 24;
    if (vhi > vlo) {
      const bins = new Array(NB).fill(0);
      for (let i = s0; i < n; i++) { const a0 = Math.max(0, Math.min(NB - 1, Math.floor((l[i] - vlo) / (vhi - vlo) * NB))), a1 = Math.max(0, Math.min(NB - 1, Math.floor((h[i] - vlo) / (vhi - vlo) * NB))); for (let k = a0; k <= a1; k++) bins[k] += (v[i] || 0) / (a1 - a0 + 1); }
      let poc = bins.indexOf(Math.max(...bins)), lo = poc, hi = poc, acc = bins[poc]; const tot = bins.reduce((s, x) => s + x, 0);
      while (acc < 0.7 * tot && (lo > 0 || hi < NB - 1)) { const nl = lo > 0 ? bins[lo - 1] : -1, nh = hi < NB - 1 ? bins[hi + 1] : -1; if (nh >= nl) acc += bins[++hi]; else acc += bins[--lo]; }
      const step = (vhi - vlo) / NB, m = Math.max(...bins) || 1;
      vp = { b: bins.map(x => Math.round(x / m * 100)), lo: vlo, hi: vhi, poc: vlo + (poc + 0.5) * step, vah: vlo + (hi + 1) * step, val: vlo + lo * step };
    }
  }
  const vh = t => !vp ? 0 : (t[2] <= vp.vah && t[1] >= vp.val ? 1 : 0);
  const act = obs.filter(x => !x[4]);
  return {
    b: b.slice(s0), v: v ? v.slice(s0) : null,
    ev: ev.filter(e => e[1] >= s0).slice(-8).map(e => [cl(e[0]), e[1] - s0, e[2], e[3], e[4], e[1]]),
    ob: act.filter(x => x[3] === 1).slice(-3).concat(act.filter(x => x[3] === -1).slice(-3)).map(x => [cl(x[0]), x[1], x[2], x[3], vh(x)]),
    fvg: fvg.filter(g => g[3] === 1).slice(-3).concat(fvg.filter(g => g[3] === -1).slice(-3)).map(g => [cl(g[0]), g[1], g[2], g[3]]),
    eq: eq.filter(e => e[1] >= s0).slice(-4).map(e => [cl(e[0]), e[1] - s0, e[2], e[3]]),
    pd: [mx(h, s0, n), mn(l, s0, n)], tr: tren, vp, s0,
  };
}

/* ---------- pilihan timeframe chart ---------- */
const TF_LIST = [["15m", "15m"], ["45m", "45m"], ["1h", "1H"], ["4h", "4H"], ["1d", "D"], ["1w", "W"], ["1mo", "M"]];
const TF_NAME = { "15m": "15 menit", "45m": "45 menit", "1h": "1 jam", "4h": "4 jam", "1d": "harian", "1w": "mingguan", "1mo": "bulanan" };
const TF_KEY = "idxs:tf", tfCache = new Map();
let curTF = ls.get(TF_KEY, "1d");
const fmtWaktu = (ms, tf) => { const d = new Date(ms + WIB_MS); const t = `${HARI3[d.getUTCDay()]}, ${d.getUTCDate()} ${BLN3[d.getUTCMonth()]} ${d.getUTCFullYear()}`; return /m$|h$/.test(tf) && tf !== "1mo" ? `${t} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}` : t; };
function loadTF(t) {
  if (tfCache.has(t)) return tfCache.get(t);
  const pr = location.protocol === "file:" || typeof fetch !== "function" ? Promise.reject(new Error("file"))
    : fetch(`data/${encodeURIComponent(t)}.json?v=${encodeURIComponent(GEN)}`).then(x => { if (!x.ok) throw new Error("HTTP " + x.status); return x.json(); });
  tfCache.set(t, pr); pr.catch(() => tfCache.delete(t)); return pr;
}
function buildTF(raw, tf) {                       // data mentah timeframe -> objek S yang dipakai smcChart
  const S = smcJS(raw.b, raw.v, tf === "1w" || tf === "1mo" ? 3 : 5, 220); if (!S) return null;
  const ts = raw.ts.slice(S.s0).map(x => x * 1000);
  S.ts = ts; S.tf = tf; S.d0 = fmtWaktu(ts[0], tf); S.d1 = fmtWaktu(ts[ts.length - 1], tf);
  S.ev = S.ev.map(e => [e[0], e[1], e[2], e[3], e[4], fmtWaktu(raw.ts[e[5]] * 1000, tf)]);
  return S;
}
function tfBar(r) {
  const av = new Set(["1d", ...(r.tfx || [])]);
  return `<div class="tf-bar" role="group" aria-label="Timeframe chart">${TF_LIST.map(([k, lab]) => `<button type="button" data-tf="${k}" class="${curTF === k ? "on" : ""}" ${av.has(k) ? "" : `disabled title="${k === "1w" || k === "1mo" ? "Belum tersedia untuk saham ini" : "Timeframe intraday hanya untuk saham dengan transaksi minimal Rp 1 M/hari dan 200 saham skor tertinggi"}"`}>${lab}</button>`).join("")}</div>`;
}

/* ---------- indikator: MA, RSI, MACD (dihitung dari seluruh data lalu dipotong ke candle yang terlihat) ---------- */
function indSMA(c, n) { const o = new Array(c.length).fill(null); let s = 0; for (let i = 0; i < c.length; i++) { s += c[i]; if (i >= n) s -= c[i - n]; if (i >= n - 1) o[i] = s / n; } return o; }
function indEMA(c, n) { const o = new Array(c.length).fill(null), k = 2 / (n + 1); let e = null; for (let i = 0; i < c.length; i++) { if (c[i] == null) continue; e = e == null ? c[i] : c[i] * k + e * (1 - k); if (i >= n - 1) o[i] = e; } return o; }
function indRSI(c, n = 14) {
  const o = new Array(c.length).fill(null); let g = 0, l = 0;
  for (let i = 1; i < c.length; i++) { const d = c[i] - c[i - 1], up = Math.max(d, 0), dn = Math.max(-d, 0);
    if (i <= n) { g += up / n; l += dn / n; if (i === n) o[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l); }
    else { g = (g * (n - 1) + up) / n; l = (l * (n - 1) + dn) / n; o[i] = l === 0 ? 100 : 100 - 100 / (1 + g / l); } }
  return o;
}
function indicators(closes, nb) {
  const e12 = indEMA(closes, 12), e26 = indEMA(closes, 26);
  const macd = closes.map((_, i) => e12[i] != null && e26[i] != null ? e12[i] - e26[i] : null);
  const firstM = macd.findIndex(v => v != null), sig = new Array(closes.length).fill(null);
  if (firstM >= 0) { const e = indEMA(macd.slice(firstM), 9); e.forEach((v, i) => sig[firstM + i] = v); }
  const cut = a => a.slice(-nb);
  return { ma20: cut(indSMA(closes, 20)), ma50: cut(indSMA(closes, 50)), ma200: cut(indSMA(closes, 200)), rsi: cut(indRSI(closes)),
    macd: cut(macd), sig: cut(sig), hist: cut(macd.map((v, i) => v != null && sig[i] != null ? v - sig[i] : null)) };
}

/* ---------- pasar global & makro ---------- */
let makroSel = null;
function makroSeries(m) { const base = Date.parse(m.d0 + "T00:00:00Z"); return m.c.map((v, i) => ({ t: base + m.do[i] * 86400000, v })); }
const fmtM = (v, dec) => Number(v).toLocaleString("id-ID", { minimumFractionDigits: dec, maximumFractionDigits: dec });
function chgOf(c, k) { const n = c.length; if (n <= k) return null; return (c[n - 1] / c[n - 1 - k] - 1) * 100; }
function korelTxt(k) {
  if (k == null) return "-";
  const a = Math.abs(k), kuat = a >= 0.5 ? "kuat" : a >= 0.2 ? "sedang" : "lemah";
  return `${k >= 0 ? "+" : ""}${fmtDec(k, 2)} (${a < 0.2 ? "hampir tidak berhubungan" : `${kuat}, ${k > 0 ? "searah" : "berlawanan"}`})`;
}
function sparkSvg(c, w = 220, h = 54) {
  const mn = Math.min(...c), mx = Math.max(...c), rg = (mx - mn) || 1, up = c[c.length - 1] >= c[0];
  const pts = c.map((v, i) => `${(i / (c.length - 1) * w).toFixed(1)},${(h - 3 - (v - mn) / rg * (h - 6)).toFixed(1)}`).join(" ");
  return `<svg viewBox="0 0 ${w} ${h}" preserveAspectRatio="none" class="mk-spark" aria-hidden="true"><polyline points="${pts}" fill="none" stroke="${up ? "var(--up)" : "var(--down)"}" stroke-width="1.6"/></svg>`;
}
function renderMakro() {
  const box = $("makro"); if (!box) return;
  const M = MARKET.makro || [];
  if (!M.length) { box.innerHTML = '<p class="muted" style="margin:0">Data pasar global belum tersedia di run ini.</p>'; $("makro-big").innerHTML = ""; return; }
  box.innerHTML = M.map(m => {
    const c = m.c, last = c[c.length - 1], d1 = chgOf(c, 1), d20 = chgOf(c, 21), dy = (last / c[0] - 1) * 100;
    const chip = (v, lab) => v == null ? "" : `<span class="${v >= 0 ? "pos" : "neg"}">${lab} ${v >= 0 ? "+" : ""}${fmtDec(v, 2)}%</span>`;
    return `<button type="button" class="mk-card${makroSel === m.sym ? " on" : ""}" data-mk="${esc(m.sym)}">
      <span class="mk-name">${esc(m.nama)}</span>
      <span class="mk-val">${fmtM(last, m.dec)}</span>
      <span class="mk-chg">${chip(d1, "1H")} ${chip(d20, "1B")} ${chip(dy, "1T")}</span>
      ${sparkSvg(c)}
      <span class="mk-kor">Hubungan dengan IHSG: <b>${esc(korelTxt(m.korel))}</b></span>
      ${m.sym === "EMAS_IDR" && MARKET.emas ? '<span class="mk-link">Klik untuk grafik, lalu "Analisa lengkap" →</span>' : ""}
    </button>`;
  }).join("");
  box.querySelectorAll("[data-mk]").forEach(b => b.addEventListener("click", () => { makroSel = makroSel === b.dataset.mk ? null : b.dataset.mk; renderMakro(); }));
  const m = M.find(x => x.sym === makroSel), big = $("makro-big");
  if (!m) { big.innerHTML = ""; return; }
  const ser = makroSeries(m), c = m.c, W = 1400, H = 300, L = 8, R = 90, T = 12, B = 24, iw = W - L - R, ih = H - T - B;
  let mn = Math.min(...c), mx = Math.max(...c); const pad = (mx - mn) * 0.06 || 1; mn -= pad; mx += pad;
  const x = i => L + i / (c.length - 1) * iw, y = v => T + (mx - v) / (mx - mn) * ih;
  const raw = (mx - mn) / 6, mag = Math.pow(10, Math.floor(Math.log10(raw || 1))), st = [1, 2, 2.5, 5, 10].map(k => k * mag).find(k => k >= raw) || mag * 10;
  let g = ""; for (let v = Math.ceil(mn / st) * st; v <= mx; v += st) g += `<line x1="${L}" x2="${L + iw}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--line)"/><text x="${L + iw + 8}" y="${(y(v) + 4).toFixed(1)}" font-size="11" fill="var(--muted)">${fmtM(v, m.dec > 2 ? 2 : 0)}</text>`;
  const up = c[c.length - 1] >= c[0], col = up ? "var(--up)" : "var(--down)";
  const pts = c.map((v, i) => `${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(" ");
  const fd = t => { const d = new Date(t); return `${d.getUTCDate()} ${BLN3[d.getUTCMonth()]} ${d.getUTCFullYear()}`; };
  big.innerHTML = `<div class="mk-big"><div class="hist-head"><h3>${esc(m.nama)}</h3>${m.sym === "EMAS_IDR" && MARKET.emas ? '<button type="button" class="icon-btn mk-an" id="mk-emas">Analisa lengkap: SMC, Fibo, volume profile, rencana →</button>' : ""}<span class="muted" id="mk-leg">${fd(ser[ser.length - 1].t)}: <b>${fmtM(c[c.length - 1], m.dec)}</b></span></div>
    <p class="d-why" style="margin:0 0 8px">${esc(m.ket)}</p>
    <svg class="d-chart" id="mk-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Grafik ${esc(m.nama)} 1 tahun">
      ${g}<polygon points="${L},${T + ih} ${pts} ${L + iw},${T + ih}" fill="${col}" opacity="0.08"/><polyline points="${pts}" fill="none" stroke="${col}" stroke-width="2"/>
      <rect x="${L + iw + 3}" y="${(y(c[c.length - 1]) - 9).toFixed(1)}" width="${R - 6}" height="18" rx="3" fill="${col}"/><text x="${L + iw + 9}" y="${(y(c[c.length - 1]) + 4).toFixed(1)}" font-size="11" font-weight="800" fill="#fff">${fmtM(c[c.length - 1], m.dec)}</text>
      <line id="mk-v" y1="${T}" y2="${T + ih}" stroke="var(--ink2)" stroke-dasharray="4 3" style="display:none"/><circle id="mk-dot" r="4" fill="${col}" style="display:none"/>
      <text x="${L}" y="${H - 6}" font-size="11" fill="var(--muted)">${fd(ser[0].t)}</text><text x="${L + iw}" y="${H - 6}" font-size="11" text-anchor="end" fill="var(--muted)">${fd(ser[ser.length - 1].t)}</text>
    </svg></div>`;
  const eb = $("mk-emas"); if (eb) eb.addEventListener("click", openEmas);
  const svg = $("mk-svg"), vl = $("mk-v"), dot = $("mk-dot"), leg = $("mk-leg");
  svg.addEventListener("mousemove", e => { const rc = svg.getBoundingClientRect(), sx = (e.clientX - rc.left) * W / rc.width;
    const i = Math.max(0, Math.min(c.length - 1, Math.round((sx - L) / iw * (c.length - 1))));
    vl.setAttribute("x1", x(i)); vl.setAttribute("x2", x(i)); vl.style.display = ""; dot.setAttribute("cx", x(i)); dot.setAttribute("cy", y(c[i])); dot.style.display = "";
    leg.innerHTML = `${fd(ser[i].t)}: <b>${fmtM(c[i], m.dec)}</b> <span class="${c[i] >= c[0] ? "pos" : "neg"}">(${c[i] >= c[0] ? "+" : ""}${fmtDec((c[i] / c[0] - 1) * 100, 1)}% sejak awal)</span>`; });
  svg.addEventListener("mouseleave", () => { vl.style.display = "none"; dot.style.display = "none"; leg.innerHTML = `${fd(ser[ser.length - 1].t)}: <b>${fmtM(c[c.length - 1], m.dec)}</b>`; });
}

/* ---------- alat gambar: garis, horizontal, catatan, Elliott Wave ---------- */
const DRAW_KEY = "idxs:draw", DRAW_COLORS = ["#F59E0B", "#3B82F6", "#10B981", "#EF4444", "#A855F7", "#EC4899", "#14B8A6", "#E5E7EB"];
const TOOL_PTS = { line: 2, hline: 1, text: 1, ew: Infinity };
const TOOL_NAME = { line: "Garis tren", hline: "Garis horizontal", text: "Catatan", ew: "Elliott Wave", ew5: "Elliott 1–5", ew3: "Elliott A–B–C" };
const EW_SEQ = ["1", "2", "3", "4", "5", "A", "B", "C"];
function ewLabels(d) {             // label tiap titik; titik pertama (awal) tanpa label
  if (d.type === "ew5") return ["", "1", "2", "3", "4", "5"];
  if (d.type === "ew3") return ["", "A", "B", "C"];
  return d.pts.map((_, i) => i === 0 ? "" : (d.labels && d.labels[i - 1]) || "");      // tanpa label, kecuali diisi sendiri
}
const EW_STEP = { ew5: ["titik awal", "ujung gelombang 1", "ujung gelombang 2", "ujung gelombang 3", "ujung gelombang 4", "ujung gelombang 5"], ew3: ["titik awal", "ujung gelombang A", "ujung gelombang B", "ujung gelombang C"],
  line: ["titik pertama", "titik kedua"], hline: ["level harga"], text: ["posisi catatan"] };
function ewStep(n) { return n === 0 ? "titik awal" : `titik ke-${n + 1}`; }
let drawTool = null, drawPending = [], drawSel = null, curChartR = null, dwDrag = null, dwRaf = null, dwLastClick = null;
function editNote(r, id) { const list = drawList(r), d = list.find(x => x.id === id); if (!d) return;
  const v = prompt("Catatan:", d.note || ""); if (v === null) return; drawSave(r, list.map(x => x.id === id ? { ...x, note: v.trim() } : x)); drawSel = id; drawSmc(r); }
function dwDragMove(cx, cy) {
  const D = dwDrag; if (!D) return;
  const pt = D.pointAt(cx, cy, D.mode === "pt" && drawStyle.magnet), S = D.r.smc, n = S.b.length;
  if (!D.moved && Math.hypot(cx - D.x0, cy - D.y0) < 3) return;
  D.moved = true;
  const list = drawList(D.r).map(d => {
    if (d.id !== D.id) return d;
    if (D.mode === "pt") { const pts = d.pts.slice(); pts[D.k] = d.type === "hline" ? { t: pts[D.k].t, p: pt.p } : { t: pt.t, p: pt.p }; return { ...d, pts }; }
    const di = pt.i - D.start.i, dp = pt.p - D.start.p;
    return { ...d, pts: D.orig.map(q => ({ t: d.type === "hline" ? q.t : timeOf(S, Math.max(0, Math.min(n - 1 + FUT, idxOfTime(S, q.t) + di))), p: q.p + dp })) };
  });
  drawSave(D.r, list);
  if (!dwRaf) dwRaf = requestAnimationFrame(() => { dwRaf = null; if (dwDrag) drawSmc(dwDrag.r); });
}
function dwDragEnd() {
  if (!dwDrag) return; const r = dwDrag.r, moved = dwDrag.moved; dwDrag = null; document.body.classList.remove("chart-panning");
  if (moved) { dwLastClick = null; drawSmc(r); }      // tanpa geser: jangan gambar ulang supaya klik (dan klik dua kali) tetap terbaca
}
window.addEventListener("mousemove", e => { if (dwDrag) dwDragMove(e.clientX, e.clientY); });
window.addEventListener("mouseup", dwDragEnd);
window.addEventListener("touchmove", e => { if (dwDrag && e.touches.length === 1) { dwDragMove(e.touches[0].clientX, e.touches[0].clientY); e.preventDefault(); } }, { passive: false });
window.addEventListener("touchend", dwDragEnd);
let drawStyle = Object.assign({ color: "#F59E0B", w: 2, magnet: true }, ls.get("idxs:drawstyle", {}));
const saveStyle = () => ls.set("idxs:drawstyle", drawStyle);
const drawAll = () => ls.get(DRAW_KEY, {}) || {};
function drawKey(r) { return r.t + "|" + ((r.smc && r.smc.tf) || "1d"); }
function drawList(r) { return drawAll()[drawKey(r)] || []; }
function drawSave(r, list) { const a = drawAll(); if (list.length) a[drawKey(r)] = list; else delete a[drawKey(r)]; ls.set(DRAW_KEY, a); }
/* waktu tiap indeks candle; indeks di kanan candle terakhir (area masa depan) diperkirakan:
   chart harian/intraday harian = lompat hari bursa (Sabtu-Minggu dilewati), lainnya = jarak rata-rata antar candle */
function tfStep(S) {
  if (S._step) return S._step;
  const n = S.b.length, a = [];
  for (let i = Math.max(1, n - 30); i < n; i++) a.push(timeOf0(S, i) - timeOf0(S, i - 1));
  a.sort((x, y) => x - y); S._step = a.length ? a[Math.floor(a.length / 2)] : 86400000; return S._step;
}
function timeOf0(S, i) { return S.ts ? S.ts[i] : Date.parse(S.d0 + "T00:00:00Z") + S.do[i] * 86400000; }
function isDailyLike(S) { return !S.ts || S.tf === "1d"; }
function addBizDays(t, k) { let d = new Date(t); while (k > 0) { d = new Date(d.getTime() + 86400000); const w = d.getUTCDay(); if (w !== 0 && w !== 6) k--; } return d.getTime(); }
function intraPattern(S) {          // jam-jam candle dalam satu hari bursa (WIB), dari hari terlengkap 10 hari terakhir
  if (S._pat) return S._pat;
  const byDay = new Map();
  for (let i = Math.max(0, S.ts.length - 120); i < S.ts.length; i++) {
    const w = S.ts[i] + WIB_MS, day = Math.floor(w / 86400000); (byDay.get(day) || byDay.set(day, []).get(day)).push(w - day * 86400000);
  }
  let best = []; byDay.forEach(v => { if (v.length > best.length) best = v; });
  S._pat = best.length ? best.sort((a, b) => a - b) : [9 * 3600000]; return S._pat;
}
function timeOf(S, i) {
  const n = S.b.length; if (i < n) return timeOf0(S, i);
  const last = timeOf0(S, n - 1), k = i - (n - 1);
  if (isDailyLike(S)) return addBizDays(last + (S.ts ? WIB_MS : 0), k) - (S.ts ? WIB_MS : 0);
  if (S.ts && /m$|h$/.test(S.tf || "")) {          // intraday: ulangi pola jam bursa, hari kerja saja
    const pat = intraPattern(S), P = pat.length, w = last + WIB_MS, day0 = Math.floor(w / 86400000) * 86400000, tod = w - day0;
    let p0 = pat.findIndex(x => x >= tod - 60000); if (p0 < 0) p0 = P - 1;
    const tot = p0 + k, dAdd = Math.floor(tot / P), slot = tot % P;
    return addBizDays(day0, dAdd) + pat[slot] - WIB_MS;
  }
  return last + k * tfStep(S);
}
function idxOfTime(S, t) {
  const n = S.b.length; if (t <= timeOf(S, 0)) return 0;
  if (t > timeOf0(S, n - 1)) {                                 // titik di area masa depan
    if (!isDailyLike(S) && !(S.ts && /m$|h$/.test(S.tf || ""))) return n - 1 + Math.max(1, Math.round((t - timeOf0(S, n - 1)) / tfStep(S)));
    const tol = isDailyLike(S) ? 43200000 : tfStep(S) / 2;
    let k = 0; while (k < 2000 && timeOf(S, n - 1 + k) < t - tol) k++; return n - 1 + k;
  }
  if (t >= timeOf(S, n - 1)) return n - 1;
  let lo = 0, hi = n - 1; while (hi - lo > 1) { const m = (lo + hi) >> 1; if (timeOf(S, m) <= t) lo = m; else hi = m; }
  return t - timeOf(S, lo) <= timeOf(S, hi) - t ? lo : hi;
}
function ewCheck(d) {
  if (d.type === "ew") {
    const P = d.pts.map(q => q.p), L = ewLabels(d), out = [];
    if (P.length >= 6) { out.push("Kalau 5 gelombang pertama dihitung sebagai impuls 1–5:"); out.push(...ewCheck({ type: "ew5", pts: d.pts.slice(0, 6) })); }
    if (P.length >= 9) out.push(...ewCheck({ type: "ew3", pts: d.pts.slice(5, 9) }).map(t => "Koreksi setelah gelombang 5: " + t));
    const nm = i => L[i] || `gel. ${i}`;
    const rel = []; for (let i = 2; i < P.length; i++) { const a = P[i - 1] - P[i - 2], b = P[i] - P[i - 1]; if (a) rel.push(`${nm(i)} = ${fmtDec(Math.abs(b / a) * 100, 1)}% dari ${nm(i - 1)}`); }
    if (rel.length) out.push("Rasio tiap gelombang terhadap gelombang sebelumnya: " + rel.join(" · ") + ".");
    if (P.length < 6) out.push("Dengan minimal 6 titik (titik awal + 5 gelombang), aturan impuls Elliott bisa dicek otomatis.");
    return out;
  }
  const P = d.pts.map(q => q.p), pct = v => fmtDec(v * 100, 1) + "%";
  if (d.type === "ew3") {
    const a = P[1] - P[0]; if (!a) return [];
    const bR = (P[1] - P[2]) / a, cA = (P[3] - P[2]) / a;      // A dan C searah, B berlawanan
    return [`Gelombang B memantul ${pct(bR)} dari A (umumnya 50–78,6%).`, `Gelombang C = ${pct(cA)} dari A (umumnya 100% atau 161,8%).`,
      bR <= 0 || bR >= 1 ? "✗ B melewati awal A: ini mungkin bukan koreksi A–B–C biasa." : "✓ B tidak melewati awal A."];
  }
  const sg = P[1] > P[0] ? 1 : -1, w = i => (P[i] - P[i - 1]) * sg;
  const w1 = w(1), w2 = -w(2), w3 = w(3), w4 = -w(4), w5 = w(5);
  if (!(w1 > 0 && w2 > 0 && w3 > 0 && w4 > 0 && w5 > 0)) return ["✗ Arah gelombang tidak berselang-seling (naik-turun-naik-turun-naik). Cek lagi urutan titiknya."];
  return [
    (P[2] - P[0]) * sg > 0 ? "✓ Aturan 1: gelombang 2 tidak melewati titik awal gelombang 1." : "✗ Aturan 1 dilanggar: gelombang 2 melewati titik awal gelombang 1.",
    !(w3 < w1 && w3 < w5) ? "✓ Aturan 2: gelombang 3 bukan yang terpendek." : "✗ Aturan 2 dilanggar: gelombang 3 yang terpendek.",
    (P[4] - P[1]) * sg > 0 ? "✓ Aturan 3: gelombang 4 tidak masuk wilayah gelombang 1." : "✗ Aturan 3 dilanggar: gelombang 4 masuk wilayah gelombang 1.",
    `Gelombang 2 = ${pct(w2 / w1)} dari gelombang 1 (umumnya 50–61,8%). Gelombang 3 = ${pct(w3 / w1)} dari gelombang 1 (sering 161,8%).`,
    `Gelombang 4 = ${pct(w4 / w3)} dari gelombang 3 (umumnya 38,2%). Gelombang 5 = ${pct(w5 / w1)} dari gelombang 1.`,
  ];
}
function drawLayer(r, S, x, y, L, iw, fp) {
  const list = drawList(r); let s = "";
  const lab = (tx, ty, text, col, anchor = "start") => `<text x="${tx.toFixed(1)}" y="${ty.toFixed(1)}" font-size="11" font-weight="800" fill="${col}" text-anchor="${anchor}" stroke="var(--panel)" stroke-width="3" paint-order="stroke" pointer-events="none">${esc(text)}</text>`;
  list.forEach(d => {
    const col = d.color || "#F59E0B", sw = d.w || 2, sel = d.id === drawSel, pts = d.pts.map(q => [x(idxOfTime(S, q.t)), y(q.p), q.p]);
    const hit = path => `<path d="${path}" fill="none" stroke="transparent" stroke-width="14" pointer-events="stroke" data-dw="${d.id}" style="cursor:${sel ? "move" : "pointer"}"/>`;
    const dash = sel ? ` stroke-dasharray="7 4"` : "";
    if (d.type === "hline") {
      const yy = pts[0][1];
      s += `<line x1="${L}" x2="${L + iw}" y1="${yy.toFixed(1)}" y2="${yy.toFixed(1)}" stroke="${col}" stroke-width="${sw}"${dash}/>` + hit(`M${L},${yy} L${L + iw},${yy}`);
      s += lab(L + 8, yy - 5, `${fp(pts[0][2])}${d.note ? " · " + d.note : ""}`, col);
    } else if (d.type === "line") {
      const [a, b] = pts, path = `M${a[0]},${a[1]} L${b[0]},${b[1]}`;
      s += `<path d="${path}" stroke="${col}" stroke-width="${sw}" fill="none"${dash}/>` + hit(path);
      if (d.note) s += lab(b[0] + 6, b[1] - 6, d.note, col);
    } else if (d.type === "text") {
      const [a] = pts;
      s += `<circle cx="${a[0].toFixed(1)}" cy="${a[1].toFixed(1)}" r="3.5" fill="${col}"/>` + hit(`M${a[0] - 4},${a[1]} L${a[0] + 60},${a[1]}`);
      s += lab(a[0] + 7, a[1] + 4, d.note || "(catatan)", col);
    } else {
      const path = "M" + pts.map(q => `${q[0].toFixed(1)},${q[1].toFixed(1)}`).join(" L");
      s += `<path d="${path}" stroke="${col}" stroke-width="${sw}" fill="none" stroke-linejoin="round"${dash}/>` + hit(path);
      const names = ewLabels(d);
      pts.forEach((q, i) => {
        s += `<circle cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="3" fill="${col}"/>`;
        if (!names[i]) return;
        const upPt = q[2] >= pts[i - 1][2];
        s += lab(q[0], upPt ? q[1] - 9 : q[1] + 17, `(${names[i]})`, col, "middle");
      });
      if (d.note) s += lab(pts[pts.length - 1][0] + 8, pts[pts.length - 1][1] + 4, d.note, col);
    }
    if (sel) pts.forEach((q, k) => s += `<circle cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="6.5" fill="var(--panel)" stroke="${col}" stroke-width="2" data-dwh="${d.id}:${k}" pointer-events="all" style="cursor:grab"/>`);
  });
  if (drawTool && drawPending.length) {
    const pp = drawPending.map(q => [x(idxOfTime(S, q.t)), y(q.p), q.p]);
    if (drawTool === "ew" && pp.length > 1) s += `<path d="M${pp.map(q => q[0].toFixed(1) + "," + q[1].toFixed(1)).join(" L")}" stroke="${drawStyle.color}" stroke-width="${drawStyle.w}" fill="none" stroke-linejoin="round"/>`;
    pp.forEach((q, i) => { s += `<circle cx="${q[0].toFixed(1)}" cy="${q[1].toFixed(1)}" r="4" fill="${drawStyle.color}"/>`;
    });
  }
  s += `<polyline class="dw-prev" fill="none" stroke="${drawStyle.color}" stroke-width="1.5" stroke-dasharray="4 3" pointer-events="none"/>`;
  return s;
}
function finishDrawing(r) {
  const type = drawTool, pts = drawPending.slice();
  if (type === "ew" && pts.length < 2) { drawSmc(r); return; }
  drawPending = []; drawTool = null;
  let note = "";
  if (type === "text") { note = (prompt("Tulis catatan:", "") || "").trim(); if (!note) { drawSmc(r); return; } }
  else note = (prompt(`Catatan untuk ${TOOL_NAME[type]} (boleh dikosongkan):`, "") || "").trim();
  const d = { id: Date.now().toString(36) + Math.random().toString(36).slice(2, 5), type, pts, color: drawStyle.color, w: drawStyle.w, note };
  drawSave(r, drawList(r).concat([d])); drawSel = d.id; drawSmc(r);
}
function deleteDrawing(r, id) { drawSave(r, drawList(r).filter(d => d.id !== id)); if (drawSel === id) drawSel = null; drawSmc(r); }
function drawControls(r) {
  const box = $("draw-ctl"); if (!box) return;
  const list = drawList(r), sel = list.find(d => d.id === drawSel);
  const need = drawTool ? TOOL_PTS[drawTool] : 0, step = drawTool === "ew" ? ewStep(drawPending.length) : drawTool ? EW_STEP[drawTool][drawPending.length] : "";
  box.innerHTML = `<div class="dw-row">
      <span class="dw-tools" role="group" aria-label="Alat gambar">${Object.keys(TOOL_PTS).map(k => `<button type="button" data-tool="${k}" class="${drawTool === k ? "on" : ""}">${{ line: "╱ Garis", hline: "― Horizontal", text: "T Catatan", ew: "〰 Elliott Wave" }[k]}</button>`).join("")}</span>
      <span class="dw-colors">${DRAW_COLORS.map(c => `<button type="button" class="sw${(sel ? sel.color : drawStyle.color) === c ? " on" : ""}" data-col="${c}" style="background:${c}" aria-label="Warna ${c}"></button>`).join("")}<input type="color" id="dw-color" value="${sel ? sel.color : drawStyle.color}" title="Warna lain"></span>
      <button type="button" class="icon-btn dw-small" id="dw-w" title="Ketebalan garis">${(sel ? sel.w : drawStyle.w) >= 3 ? "Tebal" : "Tipis"}</button>
      <button type="button" class="icon-btn dw-small${drawStyle.magnet ? " on" : ""}" id="dw-mag" title="Titik menempel ke harga tertinggi/terendah candle">Magnet ${drawStyle.magnet ? "ON" : "OFF"}</button>
      ${list.length ? `<button type="button" class="icon-btn dw-small" id="dw-clear">Hapus semua (${list.length})</button>` : ""}
    </div>
    ${drawTool === "ew" ? `<div class="dw-hint">Klik di chart: <b>${esc(step)}</b> (sudah ${drawPending.length} titik). Klik dua kali, tekan Enter, atau
        <button type="button" class="icon-btn dw-small" id="dw-done" ${drawPending.length < 2 ? "disabled" : ""}>Selesai</button> untuk mengakhiri. Backspace membatalkan titik terakhir, Esc membatalkan semuanya.</div>`
      : drawTool ? `<div class="dw-hint">Klik di chart: <b>${esc(step)}</b> (titik ${drawPending.length + 1} dari ${need}). Tekan Esc untuk batal.</div>` : ""}
    <!--SEL-->${sel ? `<div class="dw-sel"><b style="color:${sel.color}">${TOOL_NAME[sel.type]}</b>${sel.note ? ` · ${esc(sel.note)}` : ""}
        <span class="muted" style="font-size:0.76rem">Tarik bulatan untuk menggeser titik, tarik garisnya untuk memindahkan semuanya, klik dua kali untuk ubah catatan.</span>
        <button type="button" class="icon-btn dw-small" id="dw-note">✎ Catatan</button>${sel.type === "ew" ? '<button type="button" class="icon-btn dw-small" id="dw-lab">✎ Label</button>' : ""}<button type="button" class="icon-btn dw-small dw-del" id="dw-del">Hapus</button>
        ${sel.type === "ew" || sel.type === "ew5" || sel.type === "ew3" ? `<ul class="ew-check">${ewCheck(sel).map(t => `<li class="${t.startsWith("✗") ? "neg" : t.startsWith("✓") ? "pos" : ""}">${esc(t)}</li>`).join("")}</ul>` : ""}</div>` : ""}`;
  const selBox = $("draw-sel");
  if (selBox) { const i = box.innerHTML.indexOf("<!--SEL-->"); selBox.innerHTML = box.innerHTML.slice(i); box.innerHTML = box.innerHTML.slice(0, i); }
  box.querySelectorAll("[data-tool]").forEach(b => b.addEventListener("click", () => { const k = b.dataset.tool; drawTool = drawTool === k ? null : k; drawPending = []; drawSel = null; frvpMode = false; drawSmc(r); }));
  const applyStyle = (patch) => { if (sel) { drawSave(r, list.map(d => d.id === sel.id ? { ...d, ...patch } : d)); } Object.assign(drawStyle, patch); saveStyle(); drawSmc(r); };
  box.querySelectorAll("[data-col]").forEach(b => b.addEventListener("click", () => applyStyle({ color: b.dataset.col })));
  $("dw-color").addEventListener("change", e => applyStyle({ color: e.target.value }));
  $("dw-w").addEventListener("click", () => applyStyle({ w: (sel ? sel.w : drawStyle.w) >= 3 ? 2 : 3 }));
  $("dw-mag").addEventListener("click", () => { drawStyle.magnet = !drawStyle.magnet; saveStyle(); drawSmc(r); });
  const cl = $("dw-clear"); if (cl) cl.addEventListener("click", () => { if (confirm(`Hapus semua ${list.length} gambar di chart ${r.t} (${TF_NAME[(r.smc && r.smc.tf) || "1d"]})?`)) { drawSave(r, []); drawSel = null; drawSmc(r); } });
  const dn = $("dw-note"); if (dn) dn.addEventListener("click", () => { const v = prompt("Catatan:", sel.note || ""); if (v === null) return; drawSave(r, list.map(d => d.id === sel.id ? { ...d, note: v.trim() } : d)); drawSmc(r); });
  const dd = $("dw-del"); if (dd) dd.addEventListener("click", () => deleteDrawing(r, sel.id));
  const dl = $("dw-lab"); if (dl) dl.addEventListener("click", () => {
    const cur = ewLabels(sel).slice(1).join(", ");
    const v = prompt(`Label gelombang (opsional), dipisah koma untuk ${sel.pts.length - 1} titik setelah titik awal. Contoh: 1, 2, 3, 4, 5, A, B, C atau (i), (ii), (iii). Kosongkan untuk tanpa label.`, cur); if (v === null) return;
    const labels = v.split(",").map(t => t.trim()).slice(0, sel.pts.length - 1);
    drawSave(r, list.map(d => d.id === sel.id ? { ...d, labels } : d)); drawSmc(r);
  });
  const ddn = $("dw-done"); if (ddn) ddn.addEventListener("click", () => finishDrawing(r));
}

/* ---------- zoom & geser chart ---------- */
const chartView = new Map();
const priceView = new Map();      // kunci chart -> {off, scale}: geser & zoom skala harga (kosong = otomatis)
let yPanState = null;
function pvOf(r) { return priceView.get(frvpKey(r)) || null; }
function pvSet(r, off, scale) { priceView.set(frvpKey(r), { off, scale: Math.max(0.15, Math.min(12, scale)) }); }
function pvShift(r, f) { const v = pvOf(r) || { off: 0, scale: 1 }; pvSet(r, v.off + f * v.scale, v.scale); redrawSoon(r); }
function pvZoom(r, f) { const v = pvOf(r) || { off: 0, scale: 1 }; pvSet(r, v.off, v.scale * f); redrawSoon(r); }      // kunci "KODE|tf" -> {v0, v1} (rentang candle yang terlihat)
let panState = null, pinchState = null, rafRedraw = null;
const FUT = 60, FUT_DEF = 8;          // ruang kosong di kanan (area prediksi): maksimal 60 candle, tampilan awal 8
function viewOf(r, nb) {
  const V = chartView.get(frvpKey(r)), def = Math.min(nb, 120);      // tampilan awal 120 candle terakhir + sedikit ruang kosong
  let v0 = V ? V.v0 : nb - def, v1 = V ? V.v1 : nb - 1 + FUT_DEF;
  v1 = Math.min(nb - 1 + FUT, Math.max(v1, 0)); v0 = Math.max(0, Math.min(v0, v1 - 4, nb - 10));
  return { v0, v1, n: v1 - v0 + 1 };
}
function setView(r, nb, v0, n) {
  n = Math.max(15, Math.min(nb + FUT, Math.round(n))); v0 = Math.round(v0);
  v0 = Math.max(0, Math.min(v0, nb - 1 + FUT - n + 1, nb - 10));     // minimal 10 candle sungguhan tetap terlihat
  chartView.set(frvpKey(r), { v0, v1: v0 + n - 1 });
}
function redrawSoon(r) { if (rafRedraw) return; rafRedraw = requestAnimationFrame(() => { rafRedraw = null; drawSmc(r); }); }
function zoomBy(r, f, ic) {
  const nb = r.smc.b.length, V = viewOf(r, nb), n2 = Math.max(15, Math.min(nb + FUT, Math.round(V.n * f)));
  if (ic == null) ic = V.v0 + V.n / 2;
  setView(r, nb, ic - (ic - V.v0) * n2 / V.n, n2); redrawSoon(r);
}
function panBy(r, d) { const nb = r.smc.b.length, V = viewOf(r, nb); setView(r, nb, V.v0 + d, V.n); redrawSoon(r); }
window.addEventListener("mousemove", e => {
  if (!panState) return;
  const d = Math.round((panState.x - e.clientX) / panState.pxPerBar);
  const nb = panState.r.smc.b.length; setView(panState.r, nb, panState.v0 + d, panState.n); redrawSoon(panState.r);
});
window.addEventListener("mouseup", () => { if (panState || yPanState) { panState = null; yPanState = null; document.body.classList.remove("chart-panning"); } });
window.addEventListener("mousemove", e => {
  const Y = yPanState; if (!Y) return;
  const dy = e.clientY - Y.y;
  if (Y.mode === "scale") { pvSet(Y.r, Y.off, Y.scale * Math.exp(dy / 220)); redrawSoon(Y.r); return; }
  if (!Y.started && Math.abs(dy) < 10) return;          // geser horizontal biasa tidak ikut menggeser harga
  Y.started = true; pvSet(Y.r, Y.off + dy / Y.ihPx * Y.scale, Y.scale); redrawSoon(Y.r);
});
window.addEventListener("touchmove", e => {
  if (!pinchState || e.touches.length !== 2) return;
  const dd = Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY) || 1;
  const P = pinchState, nb = P.r.smc.b.length, n2 = Math.max(15, Math.min(nb + FUT, Math.round(P.n * P.d / dd)));
  setView(P.r, nb, P.ic - (P.ic - P.v0) * n2 / P.n, n2); redrawSoon(P.r); e.preventDefault();
}, { passive: false });
window.addEventListener("touchend", e => { if (pinchState && e.touches.length < 2) pinchState = null; });
function tglIdx(S, i) {
  if (i >= S.b.length) { const t = timeOf(S, i); return S.ts ? fmtWaktu(t, S.tf) : new Date(t).toISOString().slice(0, 10); }
  if (S.ts) return fmtWaktu(S.ts[i], S.tf);
  if (S.do && S.d0) return new Date(Date.parse(S.d0 + "T00:00:00Z") + S.do[i] * 86400000).toISOString().slice(0, 10);
  return "";
}

/* ---------- volume profile rentang tetap (fixed range) ---------- */
const frvpSel = new Map();        // kunci "KODE|tf" -> {i0, i1} (indeks candle yang terlihat)
let frvpMode = false;
function frvpKey(r) { return r.t + "|" + ((r.smc && r.smc.tf) || "1d") + "|" + (r.smc && r.smc.b ? r.smc.b.length : 0); }
function frvpCalc(S, i0, i1, NB = 30) {
  const b = S.b, v = S.v; if (!v) return null;
  i0 = Math.max(0, Math.min(i0, i1)); i1 = Math.min(b.length - 1, Math.max(i0, i1));
  let lo = Infinity, hi = -Infinity; for (let i = i0; i <= i1; i++) { lo = Math.min(lo, b[i][2]); hi = Math.max(hi, b[i][1]); }
  if (!(hi > lo)) return null;
  const bins = new Array(NB).fill(0), step = (hi - lo) / NB;
  for (let i = i0; i <= i1; i++) { const a0 = Math.max(0, Math.min(NB - 1, Math.floor((b[i][2] - lo) / step))), a1 = Math.max(0, Math.min(NB - 1, Math.floor((b[i][1] - lo) / step)));
    for (let k = a0; k <= a1; k++) bins[k] += (v[i] || 0) / (a1 - a0 + 1); }
  const tot = bins.reduce((s, x) => s + x, 0); if (!tot) return null;
  let poc = bins.indexOf(Math.max(...bins)), lo_i = poc, hi_i = poc, acc = bins[poc];
  while (acc < 0.7 * tot && (lo_i > 0 || hi_i < NB - 1)) { const nl = lo_i > 0 ? bins[lo_i - 1] : -1, nh = hi_i < NB - 1 ? bins[hi_i + 1] : -1; if (nh >= nl) acc += bins[++hi_i]; else acc += bins[--lo_i]; }
  return { i0, i1, lo, hi, step, bins, poc: lo + (poc + 0.5) * step, val: lo + lo_i * step, vah: lo + (hi_i + 1) * step, vaLo: lo_i, vaHi: hi_i, tot };
}

/* ---------- SMC chart ---------- */
const SMC_KEY = "idxs:smc";
const SMC_LAYERS = [["fibo", "Fibo & konfluensi"], ["vp", "Volume profile"], ["pd", "Premium/discount"], ["st", "Struktur BOS/CHoCH"], ["ob", "Order block"], ["fvg", "FVG"], ["eq", "Likuiditas EQH/EQL"], ["moon", "Fase bulan"], ["ma", "MA20/50/200"], ["rsi", "RSI"], ["macd", "MACD"], ["plan", "Entry/SL/TP"]];
function smcLayers() { return Object.assign({ fibo: true, vp: true, pd: true, st: true, ob: true, fvg: true, eq: true, moon: true, ma: false, rsi: true, macd: true, plan: false }, ls.get(SMC_KEY, {})); }

function smcChart(r, lay) {
  const S = r.smc, bars = S.b, nb = bars.length, p = r.plan;
  const full = viewMode === "full";
  const W = full ? 1440 : 720, L = 8, R = full ? 104 : 92, T = 10, B = 22, iw = W - L - R;
  const ind = S.ind || (S.ind = indicators(bars.map(b => b[3]), nb));
  const ih = full ? 500 : 290, GAP = 8, VH = S.v ? (full ? 80 : 54) : 0, PH = full ? 86 : 58, volTop = T + ih + GAP;
  const panes = [];
  if (VH) panes.push({ k: "vol", y0: volTop, h: VH });
  let yCur = volTop + VH;
  if (lay.rsi) { panes.push({ k: "rsi", y0: yCur + GAP, h: PH }); yCur += GAP + PH; }
  if (lay.macd) { panes.push({ k: "macd", y0: yCur + GAP, h: PH }); yCur += GAP + PH; }
  const bottomY = yCur, H = bottomY + B;
  const VW = viewOf(r, nb), v0 = VW.v0, v1 = VW.v1, nbv = VW.n, vis = bars.slice(v0, Math.min(v1, nb - 1) + 1);
  let max = Math.max(...vis.map(b => b[1])), min = Math.min(...vis.map(b => b[2]));
  if (lay.plan && p) { max = Math.max(max, p.tp3 || p.tp2 || p.tp); min = Math.min(min, p.sl); }
  const pad = (max - min) * 0.05 || 1; max += pad; min -= pad;
  const PV = pvOf(r);
  if (PV) { const rg0 = max - min, c = (max + min) / 2 + PV.off * rg0, rg = rg0 * PV.scale; max = c + rg / 2; min = c - rg / 2; }
  const sw = iw / nbv, bw = Math.max(1.4, sw * 0.62);
  const y = v => T + (max - v) / (max - min) * ih, x = i => L + (i - v0) * sw + sw / 2, xl = i => L + (i - v0) * sw;
  const clampY = v => Math.min(T + ih, Math.max(T, y(v)));
  const up = "var(--up)", dn = "var(--down)";
  let s = `<svg class="d-chart smc-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chart ${esc(TF_NAME[S.tf || "1d"])} dengan Smart Money Concepts ${esc(r.t)}" data-g="${[L, T, iw, ih, nb, min, max, W, H, R, GAP, VH, bottomY, v0, nbv].join(",")}" data-panes='${JSON.stringify(panes)}'>`;
  s += `<defs><clipPath id="cp"><rect x="${L}" y="${T}" width="${iw}" height="${ih}"/></clipPath><clipPath id="cpx"><rect x="${L}" y="0" width="${iw}" height="${H}"/></clipPath></defs>`;
  // skala harga: kelipatan "rapi" (mis. 25, 50, 100) sekitar 6-8 garis
  const raw = (max - min) / (full ? 11 : 8), mag = Math.pow(10, Math.floor(Math.log10(raw || 1)));
  const stepP = [1, 2, 2.5, 5, 10].map(k => k * mag).find(k => k >= raw) || mag * 10;
  const ticks = []; for (let v = Math.ceil(min / stepP) * stepP; v <= max; v += stepP) ticks.push(v);
  ticks.forEach(v => s += `<line x1="${L}" x2="${L + iw}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--line)" stroke-width="1" opacity="0.7"/>`);
  s += `<line x1="${L + iw}" x2="${L + iw}" y1="${T}" y2="${T + ih}" stroke="var(--line)"/>`;
  s += `<g clip-path="url(#cp)">`;
  if (v1 > nb - 1) {          // area masa depan: diarsir tipis
    const xf = L + (nb - v0) * sw;
    s += `<rect x="${xf.toFixed(1)}" y="${T}" width="${(L + iw - xf).toFixed(1)}" height="${ih}" fill="var(--accent)" opacity="0.035"/>`;
    s += `<line x1="${xf.toFixed(1)}" x2="${xf.toFixed(1)}" y1="${T}" y2="${T + ih}" stroke="var(--muted)" stroke-dasharray="2 4" opacity="0.5"/>`;
  }
  if (lay.pd && S.pd) {
    const [hi, lo] = S.pd, mid = (hi + lo) / 2;
    s += `<rect x="${L}" y="${clampY(hi)}" width="${iw}" height="${Math.max(0, clampY(mid) - clampY(hi))}" fill="${dn}" opacity="0.06"/>`;
    s += `<rect x="${L}" y="${clampY(mid)}" width="${iw}" height="${Math.max(0, clampY(lo) - clampY(mid))}" fill="${up}" opacity="0.06"/>`;
    s += `<line x1="${L}" x2="${L + iw}" y1="${y(mid)}" y2="${y(mid)}" stroke="var(--muted)" stroke-dasharray="2 4" opacity="0.7"/>`;
  }
  if (lay.vp && S.vp) {
    const V = S.vp, nb = V.b.length, step = (V.hi - V.lo) / nb, maxW = iw * 0.2;
    V.b.forEach((b, i) => {
      const bot = V.lo + i * step, top = bot + step; if (bot > max || top < min) return;
      const y1 = clampY(top), y2 = clampY(bot), w = b / 100 * maxW, inVA = bot >= V.val - 1e-9 && top <= V.vah + 1e-9;
      s += `<rect x="${(L + iw - w).toFixed(1)}" y="${y1.toFixed(1)}" width="${w.toFixed(1)}" height="${Math.max(1, y2 - y1 - 1).toFixed(1)}" fill="var(--accent)" opacity="${inVA ? 0.3 : 0.13}"/>`;
    });
    if (V.poc <= max && V.poc >= min) s += `<line x1="${L}" x2="${L + iw}" y1="${y(V.poc).toFixed(1)}" y2="${y(V.poc).toFixed(1)}" stroke="var(--orange)" stroke-width="1.2" opacity="0.8"/>`;
  }
  const KF = S.kf;
  if (lay.fibo && KF && KF.leg && (!S.tf || S.tf === "1d")) {
    const [i0, i1, flo, fhi] = KF.leg, xs = xl(Math.max(0, Math.min(nb - 1, i0))), xe = L + iw;
    const labX = Math.max(L + 70, xs - 6), fibUsed = [];   // label di kiri awal garis, supaya tidak menumpuk label SMC
    [["0", 0], ["0.5", 0.5], ["0.618", 0.618], ["0.705", 0.705], ["0.786", 0.786], ["1", 1]].forEach(([k, r]) => {
      const v = KF.fib[k]; if (v == null || v > max || v < min) return;
      const gold = r >= 0.618 && r <= 0.786, yy = y(v);
      s += `<line x1="${xs.toFixed(1)}" x2="${xe}" y1="${yy.toFixed(1)}" y2="${yy.toFixed(1)}" stroke="#D4A017" stroke-width="${gold ? 1.3 : 0.9}" stroke-dasharray="${r === 0 || r === 1 ? "" : "4 3"}" opacity="${gold ? 0.95 : 0.6}"/>`;
      if (fibUsed.some(u => Math.abs(u - yy) < 11)) return; fibUsed.push(yy);
      s += `<text x="${labX.toFixed(1)}" y="${(yy + 3.5).toFixed(1)}" font-size="9.5" font-weight="700" text-anchor="end" fill="#D4A017">Fibo ${k} · ${fmtNum(v)}</text>`;
    });
    if (KF.fib["0.5"] != null && KF.fib["0.786"] != null) s += `<rect x="${xs.toFixed(1)}" y="${y(KF.fib["0.5"]).toFixed(1)}" width="${(xe - xs).toFixed(1)}" height="${Math.max(1, y(KF.fib["0.786"]) - y(KF.fib["0.5"])).toFixed(1)}" fill="#D4A017" opacity="0.06"/>`;
    if (KF.lay && KF.e2 <= max && KF.e1 >= min) s += `<rect x="${xs.toFixed(1)}" y="${y(KF.e2).toFixed(1)}" width="${(xe - xs).toFixed(1)}" height="${Math.max(3, y(KF.e1) - y(KF.e2)).toFixed(1)}" fill="var(--up)" opacity="0.22" stroke="var(--up)" stroke-width="1"/><text x="${labX.toFixed(1)}" y="${((y(KF.e1) + y(KF.e2)) / 2 + 16).toFixed(1)}" font-size="10" font-weight="800" text-anchor="end" fill="var(--up)">▶ Zona konfluensi ${KF.skor}/6</text>`;
    if (KF.poc != null && KF.poc <= max && KF.poc >= min) s += `<line x1="${xs.toFixed(1)}" x2="${xe}" y1="${y(KF.poc).toFixed(1)}" y2="${y(KF.poc).toFixed(1)}" stroke="#D4A017" stroke-width="1.2" stroke-dasharray="1 3"/>${fibUsed.some(u => Math.abs(u - y(KF.poc)) < 11) ? "" : `<text x="${labX.toFixed(1)}" y="${(y(KF.poc) + 3.5).toFixed(1)}" font-size="9.5" text-anchor="end" fill="#D4A017">POC dorongan · ${fmtNum(KF.poc)}</text>`}`;
  }
  const zone = (z, cls) => {
    const [i, top, bot, dr] = z, col = dr === 1 ? up : dn;
    if (bot > max || top < min) return "";
    const y1 = clampY(top), y2 = clampY(bot), h = Math.max(2, y2 - y1);
    return `<rect x="${xl(i).toFixed(1)}" y="${y1.toFixed(1)}" width="${(L + iw - xl(i)).toFixed(1)}" height="${h.toFixed(1)}" fill="${col}" opacity="${cls === "ob" ? 0.2 : 0.1}" ${cls === "fvg" ? `stroke="${col}" stroke-dasharray="3 3" stroke-opacity="0.6"` : ""}/>` +
      `<text x="${(xl(i) + 3).toFixed(1)}" y="${(y1 + Math.min(h, 12) - 2).toFixed(1)}" font-size="9" font-weight="700" fill="${col}">${cls === "ob" ? "OB" : "FVG"}</text>`;
  };
  if (lay.fvg) (S.fvg || []).forEach(z => s += zone(z, "fvg"));
  if (lay.ob) (S.ob || []).forEach(z => s += zone(z, "ob"));
  if (lay.eq) (S.eq || []).forEach(([i1, i2, pr, nm]) => {
    if (pr > max || pr < min) return;
    const col = nm === "EQH" ? dn : up;
    s += `<line x1="${x(i1).toFixed(1)}" x2="${x(i2).toFixed(1)}" y1="${y(pr).toFixed(1)}" y2="${y(pr).toFixed(1)}" stroke="${col}" stroke-width="1.2" stroke-dasharray="1 3"/>`;
    s += `<text x="${((x(i1) + x(i2)) / 2).toFixed(1)}" y="${(y(pr) + (nm === "EQH" ? -4 : 11)).toFixed(1)}" font-size="9" text-anchor="middle" fill="${col}">${nm}</text>`;
  });
  if (lay.st) (S.ev || []).forEach(([i1, i2, pr, t, dr]) => {
    const col = dr === 1 ? up : dn;
    s += `<line x1="${x(i1).toFixed(1)}" x2="${x(i2).toFixed(1)}" y1="${y(pr).toFixed(1)}" y2="${y(pr).toFixed(1)}" stroke="${col}" stroke-width="1.3" ${t === "CHoCH" ? 'stroke-dasharray="5 3"' : ""}/>`;
    s += `<text x="${((x(i1) + x(i2)) / 2).toFixed(1)}" y="${(y(pr) + (dr === 1 ? -4 : 11)).toFixed(1)}" font-size="9.5" font-weight="700" text-anchor="middle" fill="${col}">${t}</text>`;
  });
  const path = (arr, col) => { const pts = (arr || []).map((v, i) => v ? `${x(i).toFixed(1)},${y(v).toFixed(1)}` : null).filter(Boolean); return pts.length > 1 ? `<polyline points="${pts.join(" ")}" fill="none" stroke="${col}" stroke-width="1.5" opacity="0.9"/>` : ""; };
  const smaArr = n => bars.map((b, i) => i < n - 1 ? null : bars.slice(i - n + 1, i + 1).reduce((t, v) => t + v[3], 0) / n);
  if (lay.ma) {
    s += path(ind.ma20 || smaArr(20), "var(--blue)") + path(ind.ma50 || smaArr(50), "var(--orange)") + (ind.ma200 ? path(ind.ma200, "#A855F7") : "");
    s += `<text x="${L + iw - 6}" y="${T + 14}" font-size="10" font-weight="700" text-anchor="end"><tspan fill="var(--blue)">MA20</tspan> <tspan fill="var(--orange)">MA50</tspan>${ind.ma200 && ind.ma200.some(v => v != null) ? ' <tspan fill="#A855F7">MA200</tspan>' : ' <tspan fill="var(--muted)">MA200 butuh data lebih panjang</tspan>'}</text>`;
  }
  bars.forEach((b, i) => {
    const [op, hi, lo, cl] = b, col = cl >= op ? up : dn, top = Math.min(y(op), y(cl));
    s += `<line x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${y(hi).toFixed(1)}" y2="${y(lo).toFixed(1)}" stroke="${col}" stroke-width="0.9"/><rect x="${(x(i) - bw / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0.8, Math.abs(y(cl) - y(op))).toFixed(1)}" fill="${col}"/>`;
  });
  if (lay.plan && p) {
    s += `<rect x="${L}" y="${y(p.e2).toFixed(1)}" width="${iw}" height="${Math.max(2, y(p.e1) - y(p.e2)).toFixed(1)}" fill="var(--accent)" opacity="0.12"/>`;
    [[p.tp, up], [p.sl, dn], [p.tp2, up], [p.tp3, up]].forEach(([v, col]) => { if (v != null && v <= max && v >= min) s += `<line x1="${L}" x2="${L + iw}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${col}" stroke-width="1.3" stroke-dasharray="6 4"/>`; });
  }
  const moonDates = S.do && S.d0 ? (() => { const base = Date.parse(S.d0 + "T00:00:00Z"); return S.do.map(o => new Date(base + o * 86400000).toISOString().slice(0, 10)); })()
    : S.ts && S.tf === "1d" ? S.ts.map(t => new Date(t + WIB_MS).toISOString().slice(0, 10)) : null;
  if (lay.moon && moonDates) {
    const dates = moonDates, from = new Date(Date.parse(dates[0] + "T00:00:00Z") - WIB_MS), to = new Date(Date.parse(dates[dates.length - 1] + "T00:00:00Z") + 86400000 - WIB_MS);
    moonPhases(from, to).filter(p => p.q === 0 || p.q === 2).forEach(p => {
      const day = ymd(p.t), i = dates.findIndex(dd => dd >= day); if (i < 0) return;
      const cx = x(i), full = p.q === 2;
      s += `<line x1="${cx.toFixed(1)}" x2="${cx.toFixed(1)}" y1="${T}" y2="${T + ih - 12}" stroke="var(--muted)" stroke-dasharray="2 4" opacity="0.45"/>`;
      s += `<circle cx="${cx.toFixed(1)}" cy="${T + ih - 6}" r="4.5" fill="${full ? "#F2C94C" : "var(--ink)"}" stroke="${full ? "#B8860B" : "var(--muted)"}" stroke-width="1"><title>${MOON_NAME[p.q]} ${day} ${hm(p.t)} WIB</title></circle>`;
    });
  }
  s += drawLayer(r, S, x, y, L, iw, v => r.t === "IHSG" ? fmtDec(v, 2) : fmtNum(v));
  s += "</g>";
  // skala harga di kanan (gaya TradingView/Stockbit): angka bertingkat + kotak label untuk level penting
  const last = bars[nb - 1][3], prevC = nb > 1 ? bars[nb - 2][3] : bars[nb - 1][0], lastCol = last >= prevC ? up : dn;
  s += `<line x1="${L}" x2="${L + iw}" y1="${y(last).toFixed(1)}" y2="${y(last).toFixed(1)}" stroke="${lastCol}" stroke-width="1" stroke-dasharray="2 3" opacity="0.9"/>`;
  const tags = [[last, fmtNum(last), lastCol, true]];
  if (lay.plan && p) { tags.push([p.tp, (p.tp2 ? "TP1 " : "TP ") + fmtNum(p.tp), up]); tags.push([p.sl, "SL " + fmtNum(p.sl), dn]); if (p.tp2) tags.push([p.tp2, "TP2 " + fmtNum(p.tp2), up]); if (p.tp3) tags.push([p.tp3, "TP3 " + fmtNum(p.tp3), up]); }
  if (lay.vp && S.vp) tags.push([S.vp.poc, "POC " + fmtNum(S.vp.poc), "var(--orange)"]);
  if (lay.pd && S.pd) tags.push([(S.pd[0] + S.pd[1]) / 2, "EQ " + fmtNum((S.pd[0] + S.pd[1]) / 2), "var(--muted)"]);
  const placed = [];
  tags.forEach(([v, t, col, main]) => {
    if (v > max || v < min) return;
    let yy = y(v); while (placed.some(u => Math.abs(u - yy) < 15)) yy += 15; placed.push(yy);
    const wTag = R - 6, x0 = L + iw + 3;
    s += main
      ? `<rect x="${x0}" y="${(yy - 8).toFixed(1)}" width="${wTag}" height="16" rx="3" fill="${col}"/><text x="${x0 + 6}" y="${(yy + 4).toFixed(1)}" font-size="11" font-weight="800" fill="#fff">${t}</text>`
      : `<rect x="${x0}" y="${(yy - 8).toFixed(1)}" width="${wTag}" height="16" rx="3" fill="var(--panel)" stroke="${col}"/><text x="${x0 + 6}" y="${(yy + 4).toFixed(1)}" font-size="10.5" font-weight="700" fill="${col}">${t}</text>`;
  });
  const pdMarks = lay.pd && S.pd ? [y(S.pd[0]) + 8, y(S.pd[1]) - 8] : [];
  ticks.forEach(v => { const yy = y(v); if (placed.some(u => Math.abs(u - yy) < 12) || pdMarks.some(u => Math.abs(u - yy) < 11)) return;
    s += `<text x="${L + iw + 8}" y="${(yy + 4).toFixed(1)}" font-size="10.5" fill="var(--muted)">${fmtNum(v)}</text>`; });
  if (lay.pd && S.pd) {   // penanda zona di skala kanan, atas dan bawah
    const yP = y(S.pd[0]) + 12, yD = y(S.pd[1]) - 4;
    if (!placed.some(u => Math.abs(u - yP) < 13)) s += `<text x="${L + iw + 8}" y="${Math.max(T + 10, yP).toFixed(1)}" font-size="9.5" font-weight="700" fill="${dn}">▲ Premium</text>`;
    if (!placed.some(u => Math.abs(u - yD) < 13)) s += `<text x="${L + iw + 8}" y="${Math.min(T + ih, yD).toFixed(1)}" font-size="9.5" font-weight="700" fill="${up}">▼ Discount</text>`;
  }
  s += `<text x="${L}" y="${H - 6}" font-size="10" fill="var(--muted)">${esc(tglIdx(S, v0))}</text><text x="${L + iw}" y="${H - 6}" font-size="10" text-anchor="end" fill="var(--muted)">${esc(tglIdx(S, v1))}</text>`;
  s += `<g clip-path="url(#cpx)">`;
  if (VH && S.v) {
    const vmax = Math.max(...S.v.slice(v0, v1 + 1), 1);
    s += `<line x1="${L}" x2="${L + iw}" y1="${volTop - GAP / 2}" y2="${volTop - GAP / 2}" stroke="var(--line)"/>`;
    S.v.forEach((vv, i) => { const hh = (vv || 0) / vmax * (VH - 4), b = bars[i], col = b && b[3] >= b[0] ? up : dn;
      if (hh > 0.3) s += `<rect x="${(x(i) - bw / 2).toFixed(1)}" y="${(volTop + VH - hh).toFixed(1)}" width="${bw.toFixed(1)}" height="${hh.toFixed(1)}" fill="${col}" opacity="0.55"/>`; });
    s += `<text x="${L + 6}" y="${volTop + 11}" font-size="10" font-weight="700" fill="var(--muted)">Volume (${r.vu || "lot"})</text>`;
    s += `<text x="${L + iw + 8}" y="${volTop + 10}" font-size="10" fill="var(--muted)">${fmtNum(vmax)}</text>`;
  }
  const lineIn = (arr, y0, h, lo, hi, col, w = 1.4) => { const pts = arr.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${(y0 + (hi - v) / (hi - lo) * h).toFixed(1)}`).filter(Boolean); return pts.length > 1 ? `<polyline points="${pts.join(" ")}" fill="none" stroke="${col}" stroke-width="${w}"/>` : ""; };
  panes.forEach(pn => {
    if (pn.k === "rsi") {
      const yy = v => pn.y0 + (100 - v) / 100 * pn.h;
      s += `<rect x="${L}" y="${pn.y0}" width="${iw}" height="${pn.h}" fill="var(--panel2)" opacity="0.35"/>`;
      s += `<rect x="${L}" y="${yy(70)}" width="${iw}" height="${yy(30) - yy(70)}" fill="#A855F7" opacity="0.07"/>`;
      [70, 30].forEach(v => s += `<line x1="${L}" x2="${L + iw}" y1="${yy(v)}" y2="${yy(v)}" stroke="var(--muted)" stroke-dasharray="3 3" opacity="0.7"/><text x="${L + iw + 8}" y="${yy(v) + 4}" font-size="10" fill="var(--muted)">${v}</text>`);
      s += lineIn(ind.rsi, pn.y0, pn.h, 0, 100, "#A855F7", 1.6);
      const lv = ind.rsi[ind.rsi.length - 1];
      s += `<text x="${L + 6}" y="${pn.y0 + 12}" font-size="10" font-weight="700" fill="var(--muted)">RSI 14${lv != null ? ` <tspan fill="#A855F7">${fmtDec(lv, 1)}</tspan>` : ""}</text>`;
    }
    if (pn.k === "macd") {
      const sl = a => a.slice(v0, v1 + 1), vals = [...sl(ind.macd), ...sl(ind.sig), ...sl(ind.hist)].filter(v => v != null); if (!vals.length) return;
      const hi = Math.max(...vals.map(Math.abs)) * 1.1 || 1, lo = -hi, yy = v => pn.y0 + (hi - v) / (hi - lo) * pn.h;
      s += `<rect x="${L}" y="${pn.y0}" width="${iw}" height="${pn.h}" fill="var(--panel2)" opacity="0.35"/>`;
      s += `<line x1="${L}" x2="${L + iw}" y1="${yy(0)}" y2="${yy(0)}" stroke="var(--muted)" opacity="0.6"/>`;
      ind.hist.forEach((v, i) => { if (v == null) return; const y1 = yy(Math.max(0, v)), y2 = yy(Math.min(0, v));
        s += `<rect x="${(x(i) - bw / 2).toFixed(1)}" y="${y1.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0.6, y2 - y1).toFixed(1)}" fill="${v >= 0 ? up : dn}" opacity="0.5"/>`; });
      s += lineIn(ind.macd, pn.y0, pn.h, lo, hi, "var(--blue)", 1.5) + lineIn(ind.sig, pn.y0, pn.h, lo, hi, "var(--orange)", 1.3);
      const lm = ind.macd[ind.macd.length - 1], lsg = ind.sig[ind.sig.length - 1];
      s += `<text x="${L + 6}" y="${pn.y0 + 12}" font-size="10" font-weight="700" fill="var(--muted)">MACD 12,26,9${lm != null ? ` <tspan fill="var(--blue)">${fmtDec(lm, 2)}</tspan> <tspan fill="var(--orange)">${lsg != null ? fmtDec(lsg, 2) : ""}</tspan>` : ""}</text>`;
      s += `<text x="${L + iw + 8}" y="${yy(0) + 4}" font-size="10" fill="var(--muted)">0</text>`;
    }
  });
  s += "</g>";
  const FR = frvpSel.get(frvpKey(r)), FV = FR ? frvpCalc(S, FR.i0, FR.i1) : null;
  s += `<g clip-path="url(#cp)" pointer-events="none">`;
  if (FV) {
    const xa = xl(FV.i0), xb = xl(FV.i1) + sw, wmax = Math.max(40, (xb - xa) * 0.75), bmax = Math.max(...FV.bins) || 1;
    s += `<rect x="${xa.toFixed(1)}" y="${T}" width="${(xb - xa).toFixed(1)}" height="${ih}" fill="var(--accent)" opacity="0.05"/>`;
    s += `<line x1="${xa.toFixed(1)}" x2="${xa.toFixed(1)}" y1="${T}" y2="${T + ih}" stroke="var(--accent)" stroke-dasharray="3 3" opacity="0.7"/><line x1="${xb.toFixed(1)}" x2="${xb.toFixed(1)}" y1="${T}" y2="${T + ih}" stroke="var(--accent)" stroke-dasharray="3 3" opacity="0.7"/>`;
    FV.bins.forEach((bv, k) => { const y1 = y(FV.lo + (k + 1) * FV.step), y2 = y(FV.lo + k * FV.step), inVA = k >= FV.vaLo && k <= FV.vaHi;
      s += `<rect x="${xa.toFixed(1)}" y="${(y1 + 0.5).toFixed(1)}" width="${(bv / bmax * wmax).toFixed(1)}" height="${Math.max(0.8, y2 - y1 - 1).toFixed(1)}" fill="var(--accent)" opacity="${inVA ? 0.42 : 0.18}"/>`; });
    s += `<line x1="${xa.toFixed(1)}" x2="${xb.toFixed(1)}" y1="${y(FV.poc).toFixed(1)}" y2="${y(FV.poc).toFixed(1)}" stroke="#F97316" stroke-width="1.6"/>`;
    [[FV.vah, "VAH"], [FV.val, "VAL"]].forEach(([v, n]) => s += `<line x1="${xa.toFixed(1)}" x2="${xb.toFixed(1)}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--accent)" stroke-dasharray="5 3" opacity="0.8"/><text x="${(xb - 4).toFixed(1)}" y="${(y(v) - 3).toFixed(1)}" font-size="9.5" font-weight="700" text-anchor="end" fill="var(--accent)">${n} ${fmtNum(v)}</text>`);
    s += `<text x="${(xb - 4).toFixed(1)}" y="${(y(FV.poc) - 3).toFixed(1)}" font-size="10" font-weight="800" text-anchor="end" fill="#F97316">POC rentang ${fmtNum(FV.poc)}</text>`;
  }
  s += "</g>";
  s += `<rect class="frvp-drag" y="${T}" height="${ih}" fill="var(--accent)" opacity="0.15" style="display:none"/>`;
  s += `<g class="xh" pointer-events="none" style="display:none">
    <rect class="xh-band" y="${T}" height="${bottomY - T}" fill="var(--ink)" opacity="0.06"/>
    <line class="xh-v" y1="${T}" y2="${bottomY}" stroke="var(--ink2)" stroke-width="1" stroke-dasharray="4 3" opacity="0.8"/>
    <line class="xh-h" x1="${L}" x2="${L + iw}" stroke="var(--ink2)" stroke-width="1" stroke-dasharray="4 3" opacity="0.8"/>
    <rect class="xh-pbox" x="${L + iw + 3}" width="${R - 6}" height="18" rx="3" fill="var(--ink)"/>
    <text class="xh-ptxt" x="${L + iw + 9}" font-size="11" font-weight="800" fill="var(--panel)"></text>
    <rect class="xh-dbox" y="${H - 20}" width="96" height="18" rx="3" fill="var(--ink)"/>
    <text class="xh-dtxt" y="${H - 7}" font-size="10.5" font-weight="700" fill="var(--panel)" text-anchor="middle"></text>
  </g>`;
  return s + "</svg>";
}

function smcSummary(r) {
  const S = r.smc, pr = r.p, out = [], rng = (a, b) => `${fmtNum(Math.min(a, b))}–${fmtNum(Math.max(a, b))}`;
  const e = (S.ev || [])[S.ev.length - 1];
  if (e) {
    const [, , lvl, t, dr, dt] = e;
    const arti = t === "BOS" ? (dr === 1 ? "BOS naik: tren naik berlanjut" : "BOS turun: tren turun berlanjut")
      : (dr === 1 ? "CHoCH naik: tanda awal pembalikan ke atas" : "CHoCH turun: tanda awal pembalikan ke bawah");
    out.push(`Struktur terakhir ${arti} (tembus ${fmtNum(lvl)} pada ${dt}).`);
  } else out.push(`Belum ada perubahan struktur (BOS/CHoCH) dalam ${S.b.length} candle terakhir.`);
  const inside = (S.ob || []).find(z => pr <= z[1] && pr >= z[2]);
  if (inside) out.push(`Harga sedang berada di dalam order block ${inside[3] === 1 ? "bullish (area permintaan)" : "bearish (area penawaran)"} ${rng(inside[1], inside[2])}.`);
  const obBelow = (S.ob || []).filter(z => z[3] === 1 && z[1] < pr).sort((a, b) => b[1] - a[1])[0];
  const obAbove = (S.ob || []).filter(z => z[3] === -1 && z[2] > pr).sort((a, b) => a[2] - b[2])[0];
  if (obBelow) out.push(`Order block bullish terdekat di bawah harga: ${rng(obBelow[1], obBelow[2])} (${fmtDec((pr - obBelow[1]) / pr * 100, 1)}% di bawah)${S.vp ? (obBelow[4] === 1 ? ", berada di area volume tinggi (value area), jadi lebih kuat" : ", berada di area volume rendah, jadi konfirmasinya lebih lemah") : ""}. Sering dipakai sebagai acuan area beli atau penempatan stop loss di bawahnya.`);
  if (obAbove) out.push(`Order block bearish terdekat di atas harga: ${rng(obAbove[1], obAbove[2])} (${fmtDec((obAbove[2] - pr) / pr * 100, 1)}% di atas). Area yang berpotensi menahan kenaikan.`);
  const gaps = (S.fvg || []).map(z => ({ z, d: z[3] === 1 ? pr - z[1] : z[2] - pr })).filter(o => o.d >= 0).sort((a, b) => a.d - b.d);
  if (gaps[0]) out.push(`FVG ${gaps[0].z[3] === 1 ? "bullish" : "bearish"} terdekat yang belum terisi: ${rng(gaps[0].z[1], gaps[0].z[2])}. Harga sering kembali mengisi celah seperti ini.`);
  if (S.vp) out.push(`POC (harga dengan volume terbanyak dalam ${S.b.length} candle) di ${fmtNum(S.vp.poc)}; value area ${fmtNum(S.vp.val)}–${fmtNum(S.vp.vah)}. Harga sekarang ${pr > S.vp.vah ? "di atas value area" : pr < S.vp.val ? "di bawah value area" : "di dalam value area"}.`);
  if (S.pd) {
    const pct = Math.round((pr - S.pd[1]) / ((S.pd[0] - S.pd[1]) || 1) * 100);
    out.push(`Posisi dalam range ${S.b.length} candle: ${pct}%. ${pct >= 55 ? "Zona premium (relatif mahal)." : pct <= 45 ? "Zona discount (relatif murah)." : "Sekitar equilibrium."}`);
  }
  return out;
}

const HARI3 = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"], BLN3 = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
function attachCrosshair(r, box) {
  const S = r.smc, svg = box.querySelector("svg.smc-svg"), leg = box.querySelector(".xh-legend"); if (!svg || !S) return;
  const [L, T, iw, ih, nb, min, max, W, H, , GAP, VH, bottomY, v0, nbv] = svg.dataset.g.split(",").map(Number);
  const panes = JSON.parse(svg.dataset.panes || "[]"), ind = S.ind || {};
  const base = S.ts ? 0 : Date.parse(S.d0 + "T00:00:00Z"), sw = iw / nbv;
  const g = svg.querySelector(".xh"), vL = g.querySelector(".xh-v"), hL = g.querySelector(".xh-h"), band = g.querySelector(".xh-band");
  const pBox = g.querySelector(".xh-pbox"), pTxt = g.querySelector(".xh-ptxt"), dBox = g.querySelector(".xh-dbox"), dTxt = g.querySelector(".xh-dtxt");
  const idx = r.t === "IHSG";
  const fp = v => idx ? fmtDec(v, 2) : fmtNum(v);
  const tglOf = i => i >= S.b.length ? new Date(timeOf(S, i) + (S.ts ? WIB_MS : 0)) : S.ts ? new Date(S.ts[i] + WIB_MS) : new Date(base + (S.do ? S.do[i] : i) * 86400000);
  const intra = S.ts && /m$|h$/.test(S.tf || "");
  const legend = i => {
    if (i >= S.b.length) { const d = tglOf(i); leg.innerHTML = `<b>${HARI3[d.getUTCDay()]}, ${d.getUTCDate()} ${BLN3[d.getUTCMonth()]} ${d.getUTCFullYear()}${intra ? " " + String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0") : ""}</b> <span class="muted">area prediksi (belum ada candle)</span>`; return; }
    const b = S.b[i], prev = i > 0 ? S.b[i - 1][3] : null, chg = prev ? (b[3] / prev - 1) * 100 : null, d = tglOf(i), c = b[3] >= b[0] ? "pos" : "neg";
    const vol = !idx && S.v && S.v[i] != null ? ` <span class="xl-k">Vol</span> ${fmtNum(S.v[i])} ${r.vu || "lot"}` : "";
    leg.innerHTML = `<b>${HARI3[d.getUTCDay()]}, ${d.getUTCDate()} ${BLN3[d.getUTCMonth()]} ${d.getUTCFullYear()}${intra ? " " + String(d.getUTCHours()).padStart(2, "0") + ":" + String(d.getUTCMinutes()).padStart(2, "0") : ""}</b>
      <span class="xl-k">O</span> <span class="${c}">${fp(b[0])}</span> <span class="xl-k">H</span> <span class="${c}">${fp(b[1])}</span>
      <span class="xl-k">L</span> <span class="${c}">${fp(b[2])}</span> <span class="xl-k">C</span> <span class="${c}">${fp(b[3])}</span>
      ${chg == null ? "" : `<span class="${chg >= 0 ? "pos" : "neg"}">${chg >= 0 ? "+" : ""}${fmtDec(chg, 2)}%</span>`}${vol}
      ${ind.rsi && ind.rsi[i] != null ? ` <span class="xl-k">RSI</span> <span style="color:#A855F7">${fmtDec(ind.rsi[i], 1)}</span>` : ""}
      ${ind.macd && ind.macd[i] != null ? ` <span class="xl-k">MACD</span> <span style="color:var(--blue)">${fmtDec(ind.macd[i], 2)}</span>` : ""}
      ${ind.ma200 && ind.ma200[i] != null ? ` <span class="xl-k">MA200</span> <span style="color:#A855F7">${fp(ind.ma200[i])}</span>` : ""}`;
  };
  legend(Math.min(v0 + nbv - 1, S.b.length - 1));
  const toSvg = e => { const rc = svg.getBoundingClientRect(); const pt = e.touches ? e.touches[0] : e; return [(pt.clientX - rc.left) * W / rc.width, (pt.clientY - rc.top) * H / rc.height]; };
  const move = e => {
    const [sx, sy] = toSvg(e);
    if (sx < L || sx > L + iw || sy < T || sy > bottomY) { hide(); return; }
    const i = Math.max(v0, Math.min(v0 + nbv - 1, v0 + Math.floor((sx - L) / sw))), cx = L + (i - v0) * sw + sw / 2;
    g.style.display = "";
    vL.setAttribute("x1", cx); vL.setAttribute("x2", cx);
    band.setAttribute("x", L + (i - v0) * sw); band.setAttribute("width", Math.max(1, sw));
    hL.setAttribute("y1", sy); hL.setAttribute("y2", sy);
    pBox.setAttribute("y", sy - 9); pTxt.setAttribute("y", sy + 4);
    const pn = panes.find(q => sy >= q.y0 - GAP && sy <= q.y0 + q.h);
    pTxt.textContent = sy <= T + ih ? fp(max - (sy - T) / ih * (max - min))
      : !pn || i >= S.b.length ? "" : pn.k === "vol" ? (S.v && S.v[i] != null ? fmtNum(S.v[i]) : "")
      : pn.k === "rsi" ? (ind.rsi && ind.rsi[i] != null ? "RSI " + fmtDec(ind.rsi[i], 1) : "")
      : (ind.macd && ind.macd[i] != null ? fmtDec(ind.macd[i], 2) : "");
    const d = tglOf(i), dx = Math.max(L + 48, Math.min(L + iw - 48, cx));
    dBox.setAttribute("x", dx - 48); dTxt.setAttribute("x", dx);
    dTxt.textContent = intra ? `${d.getUTCDate()} ${BLN3[d.getUTCMonth()]} ${String(d.getUTCHours()).padStart(2, "0")}:${String(d.getUTCMinutes()).padStart(2, "0")}` : `${d.getUTCDate()} ${BLN3[d.getUTCMonth()]} ${String(d.getUTCFullYear()).slice(2)}`;
    legend(i);
    const pv = svg.querySelector(".dw-prev");
    if (pv) pv.setAttribute("points", drawTool && drawPending.length && sy <= T + ih
      ? drawPending.map(q => `${(L + (idxOfTime(S, q.t) - v0) * sw + sw / 2).toFixed(1)},${(T + (max - q.p) / (max - min) * ih).toFixed(1)}`).concat([`${cx.toFixed(1)},${sy.toFixed(1)}`]).join(" ") : "");
    if (e.cancelable && e.touches) e.preventDefault();
  };
  const hide = () => { g.style.display = "none"; legend(Math.min(v0 + nbv - 1, S.b.length - 1)); };
  // volume profile rentang: klik-geser (atau sentuh-geser) saat mode aktif
  const drag = svg.querySelector(".frvp-drag"); let d0 = null;
  const idxAt = e => { const [sx] = toSvg(e); return Math.max(v0, Math.min(v0 + nbv - 1, v0 + Math.floor((sx - L) / sw))); };
  const dShow = (a, b2) => { const i0 = Math.min(a, b2), i1 = Math.max(a, b2); drag.setAttribute("x", L + (i0 - v0) * sw); drag.setAttribute("width", Math.max(sw, (i1 - i0 + 1) * sw)); drag.style.display = ""; };
  const dStart = e => { if (!frvpMode) return; d0 = idxAt(e); dShow(d0, d0); if (e.cancelable) e.preventDefault(); };
  const dMove = e => { if (!frvpMode || d0 == null) return; dShow(d0, idxAt(e)); if (e.cancelable) e.preventDefault(); };
  const dEnd = e => { if (!frvpMode || d0 == null) return; const pt = e.changedTouches ? e.changedTouches[0] : e; const i1 = idxAt(pt); const a = d0; d0 = null;
    if (Math.abs(i1 - a) >= 2) { frvpSel.set(frvpKey(r), { i0: Math.min(a, i1), i1: Math.max(a, i1) }); frvpMode = false; drawSmc(r); } else drag.style.display = "none"; };
  svg.addEventListener("mousedown", dStart); svg.addEventListener("mousemove", dMove); svg.addEventListener("mouseup", dEnd);
  svg.addEventListener("mouseleave", () => { if (d0 != null) { d0 = null; drag.style.display = "none"; } });
  svg.addEventListener("touchstart", dStart, { passive: false }); svg.addEventListener("touchmove", dMove, { passive: false }); svg.addEventListener("touchend", dEnd);
  svg.classList.toggle("frvp-on", frvpMode);
  svg.classList.toggle("draw-on", !!drawTool);
  let downAt = null;
  const pointAtFor = rc => (cx, cy, snap) => {
    const sx = (cx - rc.left) * W / rc.width, sy = (cy - rc.top) * H / rc.height;
    const i = Math.max(v0, Math.min(v0 + nbv - 1, v0 + Math.floor((sx - L) / sw)));
    let p = max - (sy - T) / ih * (max - min);
    if (snap && i < S.b.length) { const bb = S.b[i], yy = v => T + (max - v) / (max - min) * ih; if (Math.abs(sy - yy(bb[1])) < 14) p = bb[1]; else if (Math.abs(sy - yy(bb[2])) < 14) p = bb[2]; }
    return { i, t: timeOf(S, i), p };
  };
  const startDwDrag = (e, cx, cy) => {
    if (drawTool || frvpMode) return false;
    const h = e.target.closest && e.target.closest("[data-dwh]"), body = e.target.closest && e.target.closest("[data-dw]");
    const pa = pointAtFor(svg.getBoundingClientRect());
    if (h) { const [id, k] = h.dataset.dwh.split(":"); dwDrag = { mode: "pt", id, k: +k, r, pointAt: pa, x0: cx, y0: cy }; }
    else if (body && body.dataset.dw === drawSel) { const d = drawList(r).find(x => x.id === drawSel); if (!d) return false;
      dwDrag = { mode: "all", id: d.id, start: pa(cx, cy, false), orig: d.pts.map(q => ({ ...q })), r, pointAt: pa, x0: cx, y0: cy }; }
    else return false;
    document.body.classList.add("chart-panning"); return true;
  };
  svg.addEventListener("mousedown", e => { downAt = [e.clientX, e.clientY]; if (e.button === 0 && startDwDrag(e, e.clientX, e.clientY)) e.preventDefault(); });
  svg.addEventListener("touchstart", e => { if (e.touches.length === 1 && startDwDrag(e, e.touches[0].clientX, e.touches[0].clientY)) e.preventDefault(); }, { passive: false });
  svg.addEventListener("click", e => {
    const moved = downAt && Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]) > 5; downAt = null;
    if (!drawTool) {
      if (moved) return;
      const hit = e.target.closest && (e.target.closest("[data-dw]") || e.target.closest("[data-dwh]"));
      if (hit) {
        const id = hit.dataset.dw || hit.dataset.dwh.split(":")[0], now = Date.now();
        if (dwLastClick && dwLastClick.id === id && now - dwLastClick.t < 450) { dwLastClick = null; editNote(r, id); return; }   // klik dua kali
        dwLastClick = { id, t: now };
        if (drawSel !== id) { drawSel = id; drawSmc(r); }
      } else if (drawSel) { drawSel = null; drawSmc(r); }
      return;
    }
    const [sx, sy] = toSvg(e); if (sx < L || sx > L + iw || sy < T || sy > T + ih) return;
    const i = Math.max(v0, Math.min(v0 + nbv - 1, v0 + Math.floor((sx - L) / sw)));
    let pr = max - (sy - T) / ih * (max - min);
    if (drawStyle.magnet && i < S.b.length) { const bb = S.b[i], yy = v => T + (max - v) / (max - min) * ih;
      if (Math.abs(sy - yy(bb[1])) < 14) pr = bb[1]; else if (Math.abs(sy - yy(bb[2])) < 14) pr = bb[2]; }
    const tt = timeOf(S, i), last = drawPending[drawPending.length - 1];
    if (drawTool === "ew" && last && last.t === tt) return;          // klik kedua dari klik-dua-kali
    drawPending.push({ t: tt, p: pr });
    if (drawPending.length >= TOOL_PTS[drawTool]) finishDrawing(r); else drawSmc(r);
  });
  svg.addEventListener("dblclick", e => {
    if (drawTool === "ew" && drawPending.length >= 2) { e.preventDefault(); finishDrawing(r); return; }
    // klik dua kali pada gambar ditangani di handler klik (lebih andal karena chart digambar ulang saat memilih)
  });
  // zoom (roda mouse / cubit dua jari) dan geser (klik-tahan lalu geser)
  svg.addEventListener("wheel", e => {
    const [sx, sy] = toSvg(e);
    if ((e.shiftKey && sx >= L && sx <= L + iw) || (sx > L + iw && sy <= T + ih)) { e.preventDefault(); pvZoom(r, e.deltaY > 0 ? 1.12 : 1 / 1.12); return; }
    if (sx < L || sx > L + iw) return;
    e.preventDefault(); zoomBy(r, e.deltaY > 0 ? 1.15 : 1 / 1.15, v0 + (sx - L) / sw);
  }, { passive: false });
  svg.addEventListener("mousedown", e => {
    if (frvpMode || drawTool || e.button !== 0 || (e.target.closest && e.target.closest("[data-dw], [data-dwh]"))) return;
    const rc = svg.getBoundingClientRect();
    const [sx, sy] = toSvg(e), pv = pvOf(r) || { off: 0, scale: 1 }, ihPx = ih * rc.height / H;
    if (sx > L + iw && sy <= T + ih) { yPanState = { r, y: e.clientY, scale: pv.scale, off: pv.off, mode: "scale" }; document.body.classList.add("chart-panning"); e.preventDefault(); return; }
    if (sy > T + ih) { panState = { r, x: e.clientX, v0, n: nbv, pxPerBar: sw * rc.width / W }; document.body.classList.add("chart-panning"); e.preventDefault(); return; }
    panState = { r, x: e.clientX, v0, n: nbv, pxPerBar: sw * rc.width / W };
    yPanState = { r, y: e.clientY, off: pv.off, scale: pv.scale, ihPx, mode: "pan", started: !!pvOf(r) };
    document.body.classList.add("chart-panning"); e.preventDefault();
  });
  svg.addEventListener("touchstart", e => {
    if (e.touches.length !== 2) return;
    const [sx] = toSvg({ clientX: (e.touches[0].clientX + e.touches[1].clientX) / 2, clientY: e.touches[0].clientY });
    pinchState = { r, d: Math.hypot(e.touches[0].clientX - e.touches[1].clientX, e.touches[0].clientY - e.touches[1].clientY) || 1, v0, n: nbv, ic: v0 + (sx - L) / sw };
    e.preventDefault();
  }, { passive: false });
  svg.addEventListener("mousemove", move); svg.addEventListener("mouseleave", hide);
  svg.addEventListener("touchstart", move, { passive: false }); svg.addEventListener("touchmove", move, { passive: false }); svg.addEventListener("touchend", hide);
}
function frvpControls(r) {
  const box = $("frvp-ctl"); if (!box) return;
  const S = r.smc, has = frvpSel.has(frvpKey(r)), kf = S && S.kf, FR = frvpSel.get(frvpKey(r)), FV = FR ? frvpCalc(S, FR.i0, FR.i1) : null;
  const tgl = i => S.ts ? fmtWaktu(S.ts[i], S.tf) : (S.do ? new Date(Date.parse(S.d0 + "T00:00:00Z") + S.do[i] * 86400000).toISOString().slice(0, 10) : "");
  const nbAll = S.b.length, VV = viewOf(r, nbAll);
  box.innerHTML = `<span class="zoom-ctl" role="group" aria-label="Zoom chart">
      <button type="button" data-z="out" title="Perkecil (lebih banyak candle)" ${VV.n >= nbAll + FUT ? "disabled" : ""}>−</button>
      <button type="button" data-z="in" title="Perbesar (lebih sedikit candle)" ${VV.n <= 15 ? "disabled" : ""}>+</button>
      <button type="button" data-z="left" title="Geser ke kiri (candle lebih lama)" ${VV.v0 <= 0 ? "disabled" : ""}>◀</button>
      <button type="button" data-z="right" title="Geser ke kanan (candle terbaru, lalu area prediksi)" ${VV.v1 >= nbAll - 1 + FUT ? "disabled" : ""}>▶</button>
      <button type="button" data-z="reset" title="Kembalikan tampilan awal">⟲</button>
      <button type="button" data-z="fut" title="Sisakan area kosong di kanan untuk menggambar prediksi">⇥ Area prediksi</button>
      <span class="zoom-info">${Math.min(VV.v1, nbAll - 1) - VV.v0 + 1} dari ${nbAll} candle${VV.v1 > nbAll - 1 ? ` + ${VV.v1 - (nbAll - 1)} ruang prediksi` : ""}</span></span>
    <span class="zoom-ctl" role="group" aria-label="Skala harga"><span class="zoom-info" style="padding-left:10px">Harga</span>
      <button type="button" data-y="up" title="Geser skala harga ke atas (lihat harga lebih tinggi)">▲</button>
      <button type="button" data-y="down" title="Geser skala harga ke bawah (lihat harga lebih rendah)">▼</button>
      <button type="button" data-y="in" title="Renggangkan skala harga">⇕+</button>
      <button type="button" data-y="out" title="Rapatkan skala harga">⇕−</button>
      <button type="button" data-y="auto" class="${pvOf(r) ? "" : "on"}" title="Skala harga otomatis mengikuti candle">Auto</button></span>
    <button type="button" class="icon-btn${frvpMode ? " on" : ""}" id="frvp-btn" ${S && S.v ? "" : "disabled"}>${frvpMode ? "Klik-geser di chart…" : "Volume profile rentang"}</button>
    ${kf && kf.leg && (!S.tf || S.tf === "1d") ? `<button type="button" class="icon-btn" id="frvp-leg">Pakai rentang dorongan</button>` : ""}
    ${has ? `<button type="button" class="icon-btn" id="frvp-clear">Hapus rentang</button>` : ""}
    <span class="frvp-info">${frvpMode ? "Tarik dari candle awal ke candle akhir rentang yang ingin dihitung." : FV ? `<b>Rentang</b> ${esc(tgl(FV.i0))} – ${esc(tgl(FV.i1))} (${FV.i1 - FV.i0 + 1} candle): <b style="color:#F97316">POC ${fmtNum(FV.poc)}</b> · value area ${fmtNum(FV.val)}–${fmtNum(FV.vah)} · harga sekarang ${r.p > FV.vah ? "di atas" : r.p < FV.val ? "di bawah" : "di dalam"} value area.` : ""}</span>`;
  box.querySelectorAll("[data-y]").forEach(b => b.addEventListener("click", () => {
    const k = b.dataset.y;
    if (k === "up") pvShift(r, 0.2); else if (k === "down") pvShift(r, -0.2);
    else if (k === "in") pvZoom(r, 1 / 1.25); else if (k === "out") pvZoom(r, 1.25);
    else { priceView.delete(frvpKey(r)); drawSmc(r); }
  }));
  box.querySelectorAll("[data-z]").forEach(b => b.addEventListener("click", () => {
    const z = b.dataset.z, V = viewOf(r, nbAll);
    if (z === "in") zoomBy(r, 1 / 1.4); else if (z === "out") zoomBy(r, 1.4);
    else if (z === "fut") { const fut = Math.min(FUT, Math.round(V.n * 0.4)); setView(r, nbAll, nbAll - 1 + fut - V.n + 1, V.n); redrawSoon(r); }
    else if (z === "left") panBy(r, -Math.max(1, Math.round(V.n * 0.3))); else if (z === "right") panBy(r, Math.max(1, Math.round(V.n * 0.3)));
    else { chartView.delete(frvpKey(r)); priceView.delete(frvpKey(r)); drawSmc(r); }
  }));
  const bt = $("frvp-btn"); if (bt) bt.addEventListener("click", () => { frvpMode = !frvpMode; drawSmc(r); });
  const lg = $("frvp-leg"); if (lg) lg.addEventListener("click", () => { frvpSel.set(frvpKey(r), { i0: kf.leg[0], i1: kf.leg[1] }); frvpMode = false; drawSmc(r); });
  const cl = $("frvp-clear"); if (cl) cl.addEventListener("click", () => { frvpSel.delete(frvpKey(r)); frvpMode = false; drawSmc(r); });
}
function drawSmc(r) {
  const lay = smcLayers();
  $("smc-box").innerHTML = `<div class="xh-wrap"><div class="xh-legend" aria-live="off"></div>${smcChart(r, lay)}</div>`;
  attachCrosshair(r, $("smc-box"));
  curChartR = r;
  frvpControls(r);
  drawControls(r);
  const sum = $("smc-sum"); if (sum) sum.innerHTML = smcSummary(r).map(t => `<li>${esc(t)}</li>`).join("");
  const tt = $("smc-title"); if (tt) tt.textContent = `Chart ${TF_NAME[(r.smc && r.smc.tf) || "1d"]} dengan Smart Money Concepts`;
}
function renderSmc(r) {
  frvpMode = false; drawTool = null; drawPending = []; drawSel = null;
  const tb = $("tf-bar");
  if (tb) {
    tb.innerHTML = tfBar(r);
    tb.querySelectorAll("[data-tf]").forEach(bt => bt.addEventListener("click", () => { curTF = bt.dataset.tf; ls.set(TF_KEY, curTF); renderSmc(r); }));
  }
  const tf = curTF !== "1d" && !(r.tfx || []).includes(curTF) ? "1d" : curTF;
  if (tb) tb.querySelectorAll("[data-tf]").forEach(bt => bt.classList.toggle("on", bt.dataset.tf === tf));
  if (tf === "1d") {
    drawSmc(r);
    if ((r.tfx || []).includes("1d")) loadTF(r.t).then(raw => {
      if (curTF !== "1d" && (r.tfx || []).includes(curTF)) return;
      const d = raw && raw["1d"]; if (!d || !r.smc) return;
      // Daily memakai hasil SMC dari server (220 candle, sama dengan yang dipakai Kondisi & Rencana);
      // data yang lebih panjang hanya dipakai supaya MA200, RSI, dan MACD terhitung penuh
      drawSmc({ ...r, smc: { ...r.smc, ind: indicators(d.b.map(b => b[3]), r.smc.b.length) } });
    }).catch(() => {});
  }
  else {
    $("smc-box").innerHTML = '<div class="tf-msg">Memuat data ' + esc(TF_NAME[tf]) + "…</div>";
    loadTF(r.t).then(raw => {
      if (curTF !== tf) return;
      const S = raw && raw[tf] ? buildTF(raw[tf], tf) : null;
      if (S) S.ind = indicators(raw[tf].b.map(b => b[3]), S.b.length);
      if (!S) { $("smc-box").innerHTML = '<div class="tf-msg">Data ' + esc(TF_NAME[tf]) + " belum cukup untuk saham ini.</div>"; return; }
      drawSmc({ ...r, smc: S, plan: tf === "1d" ? r.plan : r.plan });
    }).catch(() => {
      $("smc-box").innerHTML = `<div class="tf-msg">${location.protocol === "file:" ? "Timeframe selain Daily hanya bisa dibuka di versi online (github.io), karena browser tidak mengizinkan halaman lokal membaca file data." : "Data timeframe ini gagal dimuat. Coba lagi beberapa saat, atau pilih D."}</div>`;
    });
  }
  if (!$("smc-toggles")) return;
  const lay = smcLayers();
  $("smc-toggles").innerHTML = `<button type="button" class="icon-btn dw-small" id="lay-all">✓ Pilih semua</button><button type="button" class="icon-btn dw-small" id="lay-none">✕ Kosongkan</button>` + SMC_LAYERS.map(([k, n]) => `<label class="chip"><input type="checkbox" data-layer="${k}" ${lay[k] ? "checked" : ""}> ${n}</label>`).join("");
  $("smc-toggles").querySelectorAll("input").forEach(cb => cb.addEventListener("change", () => {
    const cur = smcLayers(); cur[cb.dataset.layer] = cb.checked; ls.set(SMC_KEY, cur); renderSmc(r);
  }));
  const setAll = v => { const cur = {}; SMC_LAYERS.forEach(([k]) => cur[k] = v); ls.set(SMC_KEY, cur); renderSmc(r); };
  $("lay-all").addEventListener("click", () => setAll(true));
  $("lay-none").addEventListener("click", () => setAll(false));
}

/* ---------- struktur multi-timeframe ---------- */
function msAligned(r) { const ms = r.ms || {}; return !!(ms.w && ms.d && ms.w.tr === 1 && ms.d.tr === 1 && (!ms.h4 || ms.h4.tr === 1)); }
function msCell(r) {
  const ms = r.ms || {}, lab = { w: "W", d: "D", h4: "4H" }, nama = { w: "Mingguan", d: "Harian", h4: "4 jam" };
  return `<span class="ms-row">${["w", "d", "h4"].map(k => {
    const v = ms[k]; if (!v) return `<span class="ms na" title="${nama[k]}: data tidak tersedia">${lab[k]}</span>`;
    const cls = v.tr === 1 ? "up" : v.tr === -1 ? "dn" : "na", ar = v.tr === 1 ? "▲" : v.tr === -1 ? "▼" : "•";
    const t = v.ev ? `${v.ev[0]} ${v.ev[1] === 1 ? "naik" : "turun"} ${v.ev[2]}` : "belum ada BOS/CHoCH";
    return `<span class="ms ${cls}" title="${nama[k]}: ${t}">${lab[k]}${ar}</span>`;
  }).join("")}</span>`;
}
function msBlock(r) {
  const ms = r.ms || {};
  const cells = [["w", "Mingguan"], ["d", "Harian"], ["h4", "4 jam"]].map(([k, n]) => {
    const v = ms[k];
    if (!v) return `<div class="tf-cell"><small>${n}</small><span class="muted">-</span><small>${k === "h4" ? "hanya saham transaksi ≥ Rp 1 M/hari" : "data tidak tersedia"}</small></div>`;
    const lab = v.tr === 1 ? "Bullish" : v.tr === -1 ? "Bearish" : "Belum jelas", cls = v.tr === 1 ? "sb" : v.tr === -1 ? "ss" : "n";
    return `<div class="tf-cell"><small>${n}</small><span class="v ${cls}">${lab}</span><small>${v.ev ? `${v.ev[0]} ${v.ev[1] === 1 ? "naik" : "turun"}, ${esc(v.ev[2])}` : "belum ada BOS/CHoCH"}</small></div>`;
  }).join("");
  const t = [ms.w, ms.d, ms.h4].filter(Boolean).map(v => v.tr);
  let say;
  if (t.length >= 2 && t.every(x => x === 1)) say = "Semua timeframe searah naik. Ini kondisi paling ideal: cari entry buy saat harga kembali ke order block bullish atau zona discount.";
  else if (ms.w && ms.d && ms.w.tr === 1 && ms.d.tr === 1 && ms.h4 && ms.h4.tr === -1) say = "Arah besar naik, tapi 4 jam sedang koreksi. Tunggu CHoCH naik di 4 jam atau 1 jam sebagai tanda koreksi selesai.";
  else if (ms.w && ms.d && ms.w.tr === 1 && ms.d.tr !== 1) say = "Mingguan naik, tapi Harian belum. Ini koreksi di dalam tren besar; lebih aman tunggu Harian kembali bullish (CHoCH naik).";
  else if (ms.w && ms.w.tr === -1) say = "Struktur Mingguan masih turun. Entry buy berarti melawan arus besar; kalau tetap entry, pakai lot kecil dan stop loss ketat.";
  else say = "Struktur belum searah. Tunggu konfirmasi dari timeframe yang lebih besar.";
  const warn = r.val !== undefined && r.val < 5e9 ? `<p class="warn">Transaksi ${fmtValue(r.val)}/hari, di bawah Rp 5 M. Di saham sepi, BOS/CHoCH dan order block mudah terbentuk oleh sedikit order besar, jadi struktur SMC kurang bisa dipercaya.</p>` : "";
  return `<div class="d-sec"><h3>Struktur market (dari timeframe besar ke kecil)</h3><div class="tf-grid">${cells}</div><p class="d-why">${say}</p>${warn}</div>`;
}

/* ---------- rencana berbasis struktur ---------- */
const PLAN_KEY = "idxs:planmode";
const tickJS = v => v < 200 ? 1 : v < 500 ? 2 : v < 2000 ? 5 : v < 5000 ? 10 : 25;
const floorT = v => Math.floor(v / tickJS(v)) * tickJS(v), ceilT = v => Math.ceil(v / tickJS(v)) * tickJS(v);
function structPlan(r) {
  const S = r.smc; if (!S || !S.ob) return null;
  const p = r.p, atr = (r.x && r.x.atr) || 0;
  const ob = S.ob.filter(z => z[3] === 1 && z[2] <= p).sort((a, b) => b[1] - a[1])[0]; if (!ob) return null;
  const e1 = floorT(ob[2]), e2 = Math.max(e1, floorT(Math.min(ob[1], p)));
  let sl = floorT(ob[2] - 0.3 * atr); if (!(sl < e1)) sl = e1 - tickJS(e1); if (sl <= 0) return null;
  const mid = (e1 + e2) / 2, risk = mid - sl; if (risk <= 0) return null;
  const bear = S.ob.filter(z => z[3] === -1 && z[2] > p).sort((a, b) => a[2] - b[2])[0];
  let tp = bear ? floorT(bear[2]) : (S.pd && S.pd[0] > p ? floorT(S.pd[0]) : null);
  let src = bear ? "batas bawah order block bearish terdekat di atas harga" : "puncak range chart";
  if (!tp || (tp - mid) / risk < 1.5) { tp = ceilT(mid + 2 * risk); src = "2 kali risiko, karena target struktur terlalu dekat atau tidak ada"; }
  return { e1, e2, sl, tp, risk: Math.round(risk / mid * 1000) / 10, src, hv: ob[4] === 1, dist: Math.round((p - ob[1]) / p * 1000) / 10 };
}
function renderPlan(r0, r) {
  const box = $("plan-sec"); if (!box) return;
  const P = r0.plans || {}, kf = r0.smc && r0.smc.kf;
  const noPlan = r0.kd && (r0.kd.c === "bad" || r0.kd.c === "notx");
  const sp = noPlan ? null : (P.S ? { ...P.S, ...(structPlan(r0) || {}) } : structPlan(r0));
  const avail = { konf: P.K || null, smc: sp, atr: P.A || null };
  const auto = avail.konf ? "konf" : avail.smc ? "smc" : "atr";
  let mode = ls.get(PLAN_KEY, "auto"); if (mode !== "auto" && !avail[mode]) mode = "auto";
  const eff = mode === "auto" ? auto : mode, use = avail[eff];
  r.plan = use; if (r.smc) renderSmc(r);
  if (!use) { box.innerHTML = `<h3>Rencana</h3><p class="muted" style="margin:0">${r0.kd && r0.kd.c === "notx" ? "Tidak ada rencana karena saham ini tidak ada transaksi di hari bursa terakhir (kemungkinan disuspensi). Tunggu sampai diperdagangkan kembali." : "Tidak ada rencana untuk saham ini (berlabel Hindari dulu, atau datanya kurang)."}</p>`; return; }
  const calc = ls.get(CALC, { modal: 10000000, risk: 1 }), mid = (use.e1 + use.e2) / 2, rr = (use.tp - mid) / (mid - use.sl);
  const why = mode !== "auto" ? "" : eff === "konf" ? "Dipilih otomatis: setup konfluensi layak." :
    eff === "smc" ? `Dipilih otomatis: ${kf && !kf.lay ? "konfluensi belum layak (" + (kf.alasan || "") + ") " : ""}memakai order block.` :
    `Dipilih otomatis: ${kf && !kf.lay ? "konfluensi belum layak, " : ""}tidak ada order block bullish aktif di bawah harga, memakai ATR.`;
  const FK = [["tren", "Struktur harian bullish"], ["fibo", "Fibonacci 0,5–0,786"], ["volume", "Volume dorongan (POC/area ramai)"], ["ob", "Order block bullish"], ["fvg", "FVG bullish"], ["ma", "MA20/MA50"]];
  const note = eff === "konf"
    ? `Zona konfluensi di sekitar ${fmtNum(kf.lvl)} dari dorongan naik ${fmtNum(kf.leg[2])} → ${fmtNum(kf.leg[3])}. Stop loss di bawah penahan terdekat (order block, Fibo 0,886, atau swing low). Target bertahap: TP1 puncak dorongan, TP2 Fibo 1,272, TP3 Fibo 1,618.${kf.status === "atas" ? ` Harga sekarang ${fmtDec(kf.dist, 1)}% di atas zona, jadi tunggu harga turun ke zona.` : kf.status === "di_zona" ? " Harga sedang di zona: tunggu konfirmasi candle hijau atau CHoCH naik di 1H." : ""}`
    : eff === "smc"
    ? `Entry di order block bullish ${fmtNum(use.e1)}–${fmtNum(use.e2)}${use.hv ? ", yang berada di area volume tinggi (konfirmasi lebih kuat)" : use.hv === false ? ", yang berada di area volume rendah (konfirmasi lebih lemah)" : ""}. Stop loss sedikit di bawah order block.${use.src ? " Target: " + use.src + "." : ""}${use.dist > 1 ? ` Harga sekarang ${fmtDec(use.dist, 1)}% di atas area entry, jadi rencana ini menunggu pullback.` : ""}`
    : `Area entry dari MA20 (atau harga − 1 ATR) sampai harga sekarang, stop loss 1 ATR di bawah area entry, target 2 kali risiko.`;
  const kfBox = eff === "konf" ? `<div class="kf-box"><div class="kf-head">Skor konfluensi <b>${kf.skor}/6</b></div>
      <div class="kf-list">${FK.map(([k, n]) => `<span class="${kf.fk[k] ? "y" : "x"}">${kf.fk[k] ? "✓" : "✗"} ${n}</span>`).join("")}</div>
      <div class="kf-tp">TP1 <b class="pos">${fmtNum(kf.tp[0])}</b> · TP2 <b class="pos">${fmtNum(kf.tp[1])}</b> · TP3 <b class="pos">${fmtNum(kf.tp[2])}</b></div></div>`
    : (kf && !kf.lay ? `<p class="muted" style="font-size:0.8rem;margin:0 0 8px">Konfluensi: ${esc(kf.alasan || "belum layak")}</p>` : "");
  box.innerHTML = `<h3>Rencana (contoh, bukan rekomendasi)</h3>
    <div class="seg" role="group" aria-label="Jenis rencana">
      <button type="button" data-mode="auto" class="${mode === "auto" ? "on" : ""}">Otomatis (terbaik)</button>
      <button type="button" data-mode="konf" class="${mode === "konf" ? "on" : ""}" ${avail.konf ? "" : 'disabled title="Setup konfluensi belum layak"'}>Konfluensi</button>
      <button type="button" data-mode="smc" class="${mode === "smc" ? "on" : ""}" ${avail.smc ? "" : "disabled"}>Order block</button>
      <button type="button" data-mode="atr" class="${mode === "atr" ? "on" : ""}" ${avail.atr ? "" : "disabled"}>ATR</button>
    </div>
    ${why ? `<p class="muted" style="font-size:0.8rem;margin:0 0 4px">${esc(why)}</p>` : ""}
    <p class="plan-note">${esc(note)}</p>${kfBox}
    <div class="plan-box"><div><small>Area entry</small><b>${fmtNum(use.e1)}–${fmtNum(use.e2)}</b></div><div><small>Stop loss</small><b class="neg">${fmtNum(use.sl)}</b></div><div><small>Target</small><b class="pos">${fmtNum(use.tp)}</b></div><div><small>Risiko / R:R</small><b>${fmtDec(use.risk, 1)}% · 1:${fmtDec(rr, 1)}</b></div></div>
    <div class="calc">
      <div class="f"><label for="c-modal">Modal (Rp)</label><input type="number" id="c-modal" min="0" step="100000" value="${calc.modal}"></div>
      <div class="f"><label for="c-risk" title="Berapa persen modal yang siap kamu relakan hilang kalau harga menyentuh stop loss. Umumnya 1–2%.">Maks. rugi kalau kena stop loss (% modal)</label><input type="number" id="c-risk" min="0.1" max="100" step="0.1" value="${calc.risk}"></div>
    </div>
    <div class="calc-out" id="c-out"></div>
    <div class="d-actions"><button class="icon-btn" id="j-add" type="button">Catat ke jurnal</button></div>
    <div id="j-form"></div>`;
  box.querySelectorAll("[data-mode]").forEach(b => b.addEventListener("click", () => { ls.set(PLAN_KEY, b.dataset.mode); renderPlan(r0, r); }));
  let lot = 0;
  const upd = () => {
    const modal = parseFloat($("c-modal").value) || 0, risk = parseFloat($("c-risk").value) || 0;
    ls.set(CALC, { modal, risk });
    const perLotRisk = (mid - use.sl) * 100;
    const byRisk = perLotRisk > 0 ? Math.floor(modal * risk / 100 / perLotRisk) : 0, byCash = Math.floor(modal / (mid * 100));
    lot = Math.max(0, Math.min(byRisk, byCash));
    const budget = modal * risk / 100;
    const warn = risk > 5 ? `<div class="warn" style="margin-top:8px">Risiko ${fmtDec(risk, 1)}% per transaksi sangat agresif: 3 kali kena stop loss berturut-turut bisa menghabiskan ${fmtDec(Math.min(100, risk * 3), 0)}% modal. Umumnya trader memakai 1–2%.</div>` : "";
    $("c-out").innerHTML = (lot > 0
      ? `Kamu siap rugi maksimal <b>Rp ${fmtNum(budget)}</b> (${fmtDec(risk, 1)}% dari modal) kalau harga menyentuh stop loss.<br>Jadi beli maksimal <b>${fmtNum(lot)} lot</b> (sekitar Rp ${fmtNum(lot * mid * 100)}). Kalau kena stop loss, ruginya sekitar <b>Rp ${fmtNum(lot * perLotRisk)}</b> atau ${fmtDec(lot * perLotRisk / modal * 100, 2)}% modal.${byCash < byRisk ? `<br><b>Dibatasi oleh jumlah modal:</b> uangmu hanya cukup untuk ${fmtNum(byCash)} lot, jadi menaikkan persentase risiko tidak menambah jumlah lot.` : ""}`
      : "Modal atau risiko terlalu kecil untuk membeli 1 lot dengan stop loss ini.") + warn;
  };
  $("c-modal").addEventListener("input", upd); $("c-risk").addEventListener("input", upd); upd();
  $("j-add").addEventListener("click", () => journalForm(r0, use, lot, eff === "konf" ? "smc" : eff));
}

/* ---------- jurnal trading (tersimpan di browser ini) ---------- */
const JR = "idxs:jurnal";
const SETUPS = ["BOS + order block", "CHoCH + order block", "Pantulan dari FVG", "Pullback ke zona discount", "Breakout", "Pullback ke MA20", "Lainnya"];
const jrLoad = () => ls.get(JR, []), jrSave = a => ls.set(JR, a);
/* Saran SL & target dari rata-rata entry (average up/down). Menjaga rugi maksimal sesuai % modal di kalkulator. */
function exitSuggest(avg, lot, p, r, modal, riskPct) {
  const atr = (r.x && r.x.atr) || 0, budget = modal * riskPct / 100, notes = [];
  let slS = p.sl < avg ? p.sl : null;
  if (slS === null) {
    slS = floorT(atr > 0 ? avg - atr : avg * 0.93); if (!(slS > 0)) slS = floorT(avg * 0.93);
    notes.push("SL rencana (" + fmtNum(p.sl) + ") sudah di atas rata-rata entry, jadi SL dihitung ulang 1 ATR di bawah rata-rata entry.");
  }
  const slR = budget > 0 && lot > 0 ? ceilT(avg - budget / (lot * 100)) : null;
  let sl = slS;
  if (slR !== null && slR < avg && slR > slS) {
    sl = slR;
    const maxLot = Math.floor(budget / ((avg - slS) * 100));
    notes.push("Dengan " + fmtNum(lot) + " lot, SL di " + fmtNum(slS) + " bikin rugi Rp " + fmtNum(lot * 100 * (avg - slS)) + ", lebih dari batas Rp " + fmtNum(budget) + ". SL diketatkan ke " + fmtNum(sl) + " supaya rugi tetap sesuai batas. Alternatifnya: total lot maksimal " + fmtNum(maxLot) + " kalau mau tetap pakai SL " + fmtNum(slS) + ".");
  } else if (slR !== null && slR >= avg) {
    notes.push("Total lot terlalu besar untuk batas rugi " + fmtDec(riskPct, 1) + "% modal: jarak SL yang muat kurang dari 1 tick. Kurangi lot.");
  }
  const risk = avg - sl;
  let tp, tpSrc;
  if (p.tp > avg && (p.tp - avg) / risk >= 1.5) { tp = p.tp; tpSrc = "target rencana"; }
  else { tp = ceilT(avg + 2 * risk); tpSrc = "R:R 1:2 dari rata-rata entry"; }
  const loss = lot * 100 * risk;
  return { sl, tp, tpSrc, tp3: ceilT(avg + 3 * risk), riskPct: risk / avg * 100, rr: (tp - avg) / risk, loss, lossPct: modal > 0 ? loss / modal * 100 : 0, notes };
}
function journalForm(r, p, lot, mode) {
  const today = ymd(new Date()), mid = floorT((p.e1 + p.e2) / 2);
  const rows = [{ h: mid, l: lot || 1 }];
  let dirtySL = false, dirtyTP = false, sug = null, avg = 0, totLot = 0;
  $("j-form").innerHTML = `<div class="j-form">
    <div class="f"><label>Tanggal</label><input type="date" id="jf-tgl" value="${today}"></div>
    <div class="f"><label>Setup</label><select id="jf-setup">${SETUPS.map(s => `<option ${mode === "smc" && s === "BOS + order block" ? "selected" : ""}>${s}</option>`).join("")}</select></div>
    <div class="f"><label>Timeframe entry</label><select id="jf-tf"><option>1 jam</option><option>4 jam</option><option selected>Harian</option></select></div>
    <div class="f" style="grid-column:1/-1"><label>Pembelian (tambah baris kalau average up/down)</label><div id="jf-rows"></div>
      <button class="icon-btn" id="jf-addrow" type="button">+ Tambah pembelian</button></div>
    <div class="calc-out" id="jf-sum" style="grid-column:1/-1;margin-top:0"></div>
    <div class="f"><label>Stop loss</label><input type="number" id="jf-sl"></div>
    <div class="f"><label>Target</label><input type="number" id="jf-tp"></div>
    <div class="f" style="grid-column:1/-1"><label>Catatan</label><input type="text" id="jf-note" placeholder="mis. CHoCH 1 jam di OB harian, broker akumulasi"></div>
    <div style="grid-column:1/-1;display:flex;gap:8px"><button class="icon-btn" id="jf-save" type="button">Simpan trade</button><button class="icon-btn" id="jf-cancel" type="button">Batal</button></div>
  </div>`;
  const drawRows = () => {
    $("jf-rows").innerHTML = rows.map((x, i) => `<div class="jr-row"><input type="number" data-i="${i}" data-k="h" value="${x.h}" min="0" placeholder="Harga beli ${i + 1}" aria-label="Harga beli ${i + 1}"><input type="number" data-i="${i}" data-k="l" value="${x.l}" min="1" placeholder="Lot" aria-label="Lot pembelian ${i + 1}">${rows.length > 1 ? `<button class="icon-btn" type="button" data-rm="${i}" aria-label="Hapus pembelian ${i + 1}">✕</button>` : "<span></span>"}</div>`).join("");
    $("jf-rows").querySelectorAll("input").forEach(inp => inp.addEventListener("input", () => { rows[+inp.dataset.i][inp.dataset.k] = +inp.value; recalc(); }));
    $("jf-rows").querySelectorAll("[data-rm]").forEach(bt => bt.addEventListener("click", () => { rows.splice(+bt.dataset.rm, 1); drawRows(); recalc(); }));
  };
  const apply = () => { if (!sug) return; $("jf-sl").value = sug.sl; $("jf-tp").value = sug.tp; dirtySL = dirtyTP = false; };
  const recalc = () => {
    const ok = rows.filter(x => x.h > 0 && x.l > 0);
    totLot = ok.reduce((s, x) => s + x.l, 0);
    if (!totLot) { sug = null; $("jf-sum").innerHTML = "Isi harga beli dan lot dulu."; return; }
    avg = ok.reduce((s, x) => s + x.h * x.l, 0) / totLot;
    const c = ls.get(CALC, { modal: 10000000, risk: 1 }), cost = avg * totLot * 100;
    sug = exitSuggest(avg, totLot, p, r, c.modal, c.risk);
    if (!dirtySL) $("jf-sl").value = sug.sl;
    if (!dirtyTP) $("jf-tp").value = sug.tp;
    const chg = r.p ? (r.p - avg) / avg * 100 : null;
    $("jf-sum").innerHTML = `Rata-rata entry <b>${fmtDec(avg, Number.isInteger(avg) ? 0 : 1)}</b> · total <b>${fmtNum(totLot)} lot</b> (Rp ${fmtNum(cost)}${c.modal > 0 ? `, ${fmtDec(cost / c.modal * 100, 0)}% modal` : ""})${chg !== null ? `<br>Harga sekarang ${fmtNum(r.p)}: <b class="${chg >= 0 ? "pos" : "neg"}">${chg >= 0 ? "+" : ""}${fmtDec(chg, 1)}%</b> dari rata-rata entry.` : ""}
      <br>Saran: stop loss <b class="neg">${fmtNum(sug.sl)}</b> (−${fmtDec(sug.riskPct, 1)}%), target <b class="pos">${fmtNum(sug.tp)}</b> (${esc(sug.tpSrc)}, R:R 1:${fmtDec(sug.rr, 1)})${sug.tp3 > sug.tp ? `, atau target 1:3 di ${fmtNum(sug.tp3)}` : ""}. Kalau kena SL, rugi sekitar Rp ${fmtNum(sug.loss)} (${fmtDec(sug.lossPct, 2)}% modal).
      ${sug.notes.map(n => `<br><span class="muted">${esc(n)}</span>`).join("")}${c.modal > 0 && cost > c.modal ? `<br><b class="neg">Total pembelian melebihi modal di kalkulator.</b>` : ""}
      <br><button class="icon-btn" id="jf-apply" type="button" style="margin-top:6px">Terapkan saran SL &amp; target</button>`;
    $("jf-apply").addEventListener("click", apply);
  };
  $("jf-sl").addEventListener("input", () => dirtySL = true);
  $("jf-tp").addEventListener("input", () => dirtyTP = true);
  $("jf-addrow").addEventListener("click", () => { rows.push({ h: Math.round(r.p || mid), l: 1 }); drawRows(); recalc(); });
  drawRows(); recalc();
  $("jf-cancel").addEventListener("click", () => $("j-form").innerHTML = "");
  $("jf-save").addEventListener("click", () => {
    const ok = rows.filter(x => x.h > 0 && x.l > 0), sl = +$("jf-sl").value;
    if (!ok.length) { alert("Isi harga beli dan lot."); return; }
    const e = Math.round(avg * 100) / 100;
    if (!(sl > 0) || sl >= e) { alert("Stop loss harus di bawah harga entry (rata-rata)."); return; }
    const a = jrLoad();
    a.push({ id: Date.now(), t: r.t, tgl: $("jf-tgl").value, entry: e, sl, tp: +$("jf-tp").value || null, lot: totLot,
      tr: ok.length > 1 ? ok.map(x => ({ h: x.h, l: x.l })) : undefined,
      setup: $("jf-setup").value, tf: $("jf-tf").value, note: $("jf-note").value.trim(), exit: null, tglExit: null });
    jrSave(a); renderJournal();
    $("j-form").innerHTML = `<p class="calc-out">Tersimpan di jurnal. Buka tab Jurnal di kanan atas untuk melihatnya.</p>`;
  });
}
const rOf = (j, px) => (px - j.entry) / (j.entry - j.sl);
function renderJournal() {
  const a = jrLoad(), closed = a.filter(j => j.exit != null), open = a.filter(j => j.exit == null);
  const wins = closed.filter(j => j.exit > j.entry).length, tot = closed.reduce((s, j) => s + rOf(j, j.exit), 0);
  const bySetup = {}; closed.forEach(j => { const b = bySetup[j.setup] = bySetup[j.setup] || { n: 0, w: 0, r: 0 }; b.n++; b.r += rOf(j, j.exit); if (j.exit > j.entry) b.w++; });
  const stat = (lab, val) => `<div><small>${lab}</small><b>${val}</b></div>`;
  $("j-stats").innerHTML = closed.length
    ? stat("Trade selesai", closed.length) + stat("Win rate", fmtDec(wins / closed.length * 100, 0) + "%") + stat("Rata-rata R", fmtDec(tot / closed.length, 2) + "R") + stat("Total R", fmtDec(tot, 2) + "R")
    : stat("Trade selesai", 0) + stat("Masih terbuka", open.length);
  $("j-setups").innerHTML = Object.keys(bySetup).length ? `<table class="j-tbl"><thead><tr><th>Setup</th><th class="num">Trade</th><th class="num">Win rate</th><th class="num">Rata-rata R</th></tr></thead><tbody>${Object.entries(bySetup).sort((x, y) => y[1].r / y[1].n - x[1].r / x[1].n).map(([k, b]) => `<tr><td>${esc(k)}</td><td class="num">${b.n}</td><td class="num">${fmtDec(b.w / b.n * 100, 0)}%</td><td class="num ${b.r >= 0 ? "pos" : "neg"}">${fmtDec(b.r / b.n, 2)}R</td></tr>`).join("")}</tbody></table>${closed.length < 30 ? '<p class="muted" style="font-size:0.8rem">Kesimpulan per setup baru bisa dipercaya setelah sekitar 30 trade selesai.</p>' : ""}` : "";
  const rows = a.slice().sort((x, y) => ((x.exit != null) - (y.exit != null)) || y.tgl.localeCompare(x.tgl));
  $("j-list").innerHTML = rows.length ? `<div class="table-wrap" style="max-height:none"><table class="j-tbl"><thead><tr><th>Tanggal</th><th>Saham</th><th>Setup</th><th class="num">Entry</th><th class="num">SL</th><th class="num">Target</th><th class="num">Lot</th><th class="num">Harga kini / keluar</th><th class="num">R</th><th>Aksi</th></tr></thead><tbody>${rows.map(j => {
    const cur = DATA.find(d => d.t === j.t), px = j.exit != null ? j.exit : cur ? cur.p : null, r = px != null ? rOf(j, px) : null;
    return `<tr><td>${esc(j.tgl)}</td><td><b>${esc(j.t)}</b><div class="muted" style="font-size:0.72rem">${esc(j.tf)}${j.note ? " · " + esc(j.note) : ""}</div></td><td>${esc(j.setup)}</td><td class="num">${Number.isInteger(j.entry) ? fmtNum(j.entry) : fmtDec(j.entry, 1)}${j.tr ? `<div class="muted" style="font-size:0.72rem" title="${esc(j.tr.map(x => x.h + " x " + x.l + " lot").join("; "))}">rata-rata ${j.tr.length} pembelian</div>` : ""}</td><td class="num">${fmtNum(j.sl)}</td><td class="num">${j.tp ? fmtNum(j.tp) : "-"}</td><td class="num">${fmtNum(j.lot)}</td>
      <td class="num">${px != null ? fmtNum(px) : "-"}${j.exit == null ? '<div class="muted" style="font-size:0.72rem">masih terbuka</div>' : ""}${j.exit == null && cur && cur.p <= j.sl ? '<div class="neg" style="font-size:0.72rem">sudah di bawah SL</div>' : ""}${j.exit == null && cur && j.tp && cur.p >= j.tp ? '<div class="pos" style="font-size:0.72rem">sudah capai target</div>' : ""}</td>
      <td class="num ${r == null ? "" : r >= 0 ? "pos" : "neg"}">${r == null ? "-" : fmtDec(r, 2) + "R"}</td>
      <td class="j-act" data-id="${j.id}">${j.exit == null ? `<button class="icon-btn" data-add="${j.id}" type="button" title="Average up/down: tambah pembelian di trade ini">+ Beli</button> <button class="icon-btn" data-close="${j.id}" type="button">Tutup</button>` : ""} <button class="icon-btn" data-del="${j.id}" type="button">Hapus</button></td></tr>`;
  }).join("")}</tbody></table></div>` : '<p class="muted">Belum ada trade. Buka panel detail saham, lalu klik "Catat ke jurnal" di bagian Rencana.</p>';
  $("j-list").querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", () => { if (confirm("Hapus trade ini dari jurnal?")) { jrSave(jrLoad().filter(j => j.id !== +b.dataset.del)); renderJournal(); } }));
  $("j-list").querySelectorAll("[data-add]").forEach(b => b.addEventListener("click", () => {
    const td = b.closest("td"), j0 = jrLoad().find(x => x.id === +b.dataset.add), cur = DATA.find(d => d.t === j0.t);
    const base = j0.tr || [{ h: j0.entry, l: j0.lot }];
    td.innerHTML = `<div class="jr-add">
      <input type="number" data-k="h" value="${cur ? Math.round(cur.p) : j0.entry}" aria-label="Harga beli tambahan" placeholder="Harga beli">
      <input type="number" data-k="l" value="1" min="1" aria-label="Lot tambahan" placeholder="Lot">
      <div class="muted jr-out" style="font-size:0.72rem"></div>
      <label class="muted" style="font-size:0.72rem">SL <input type="number" data-k="sl" value="${j0.sl}"></label>
      <label class="muted" style="font-size:0.72rem">Target <input type="number" data-k="tp" value="${j0.tp || ""}"></label>
      <div><button class="icon-btn" data-k="ok" type="button">Simpan</button> <button class="icon-btn" data-k="no" type="button">Batal</button></div></div>`;
    const g = k => td.querySelector('[data-k="' + k + '"]'), out = td.querySelector(".jr-out");
    let dSL = false, dTP = false, nAvg = 0, nLot = 0;
    const calc = () => {
      const h = +g("h").value, l = +g("l").value;
      if (!(h > 0 && l > 0)) { out.textContent = "Isi harga beli dan lot."; nLot = 0; return; }
      const c = ls.get(CALC, { modal: 10000000, risk: 1 });
      nLot = j0.lot + l; nAvg = (j0.entry * j0.lot + h * l) / nLot;
      const sg = exitSuggest(nAvg, nLot, { sl: j0.sl, tp: j0.tp || 0 }, cur || {}, c.modal, c.risk);
      if (!dSL) g("sl").value = sg.sl;
      if (!dTP) g("tp").value = sg.tp;
      out.innerHTML = `Rata-rata baru <b>${fmtDec(nAvg, Number.isInteger(nAvg) ? 0 : 1)}</b> · ${fmtNum(nLot)} lot<br>Saran SL ${fmtNum(sg.sl)}, target ${fmtNum(sg.tp)}. Rugi di SL ±Rp ${fmtNum(sg.loss)} (${fmtDec(sg.lossPct, 2)}% modal).${sg.notes.map(n => "<br>" + esc(n)).join("")}`;
    };
    g("h").addEventListener("input", calc); g("l").addEventListener("input", calc);
    g("sl").addEventListener("input", () => dSL = true); g("tp").addEventListener("input", () => dTP = true);
    g("no").addEventListener("click", () => renderJournal());
    g("ok").addEventListener("click", () => {
      const h = +g("h").value, l = +g("l").value, sl = +g("sl").value, e = Math.round(nAvg * 100) / 100;
      if (!(h > 0 && l > 0 && nLot > 0)) { alert("Isi harga beli dan lot."); return; }
      if (!(sl > 0) || sl >= e) { alert("Stop loss harus di bawah rata-rata entry baru (" + e + ")."); return; }
      const arr = jrLoad(), it = arr.find(x => x.id === j0.id);
      it.tr = base.concat([{ h, l, d: ymd(new Date()) }]); it.entry = e; it.lot = nLot; it.sl = sl; it.tp = +g("tp").value || null;
      jrSave(arr); renderJournal();
    });
    calc();
  }));
  $("j-list").querySelectorAll("[data-close]").forEach(b => b.addEventListener("click", () => {
    const td = b.closest("td"), j = jrLoad().find(x => x.id === +b.dataset.close), cur = DATA.find(d => d.t === j.t);
    td.innerHTML = `<input type="number" class="j-exit" value="${cur ? cur.p : j.entry}" aria-label="Harga keluar"> <button class="icon-btn" type="button">OK</button>`;
    td.querySelector("button").addEventListener("click", () => {
      const v = +td.querySelector("input").value; if (!(v > 0)) return;
      const arr = jrLoad(); const it = arr.find(x => x.id === j.id); it.exit = v; it.tglExit = ymd(new Date()); jrSave(arr); renderJournal();
    });
  }));
}
$("j-export").addEventListener("click", () => {
  const a = jrLoad(), head = ["tanggal", "saham", "setup", "timeframe", "entry", "stop_loss", "target", "lot", "harga_keluar", "tanggal_keluar", "R", "catatan", "rincian_pembelian"];
  const lines = [head.join(",")].concat(a.map(j => [j.tgl, j.t, j.setup, j.tf, j.entry, j.sl, j.tp ?? "", j.lot, j.exit ?? "", j.tglExit ?? "", j.exit != null ? rOf(j, j.exit).toFixed(2) : "", `"${(j.note || "").replace(/"/g, '""')}"`, `"${(j.tr || []).map(x => x.h + " x " + x.l).join("; ")}"`].join(",")));
  const blob = new Blob([lines.join("\n")], { type: "text/csv" }), url = URL.createObjectURL(blob), el = document.createElement("a");
  el.href = url; el.download = `jurnal_trading_${ymd(new Date())}.csv`; document.body.appendChild(el); el.click(); el.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
});

/* ---------- riwayat harian ---------- */
const HIST_KEY = "idxs:histn";
function histRows(r) {
  const S = r.smc; if (!S || !S.b || !S.do) return [];
  const base = Date.parse(S.d0 + "T00:00:00Z");
  return S.b.map((b, i) => {
    const vol = S.v ? S.v[i] : null, prev = i > 0 ? S.b[i - 1][3] : null;
    const win = S.v ? S.v.slice(Math.max(0, i - 20), i) : [], avg = win.length ? win.reduce((a, x) => a + x, 0) / win.length : null;
    return { tgl: new Date(base + S.do[i] * 86400000).toISOString().slice(0, 10), o: b[0], h: b[1], l: b[2], c: b[3],
      chg: prev ? (b[3] / prev - 1) * 100 : null, vol, val: vol != null ? vol * 100 * b[3] : null, vx: avg ? vol / avg : null };
  }).reverse();
}
function renderHist(r) {
  const box = $("hist-sec"); if (!box) return;
  const rows = histRows(r);
  if (!rows.length) { box.innerHTML = '<h3>Riwayat harian</h3><p class="muted" style="margin:0">Riwayat belum tersedia untuk saham ini.</p>'; return; }
  const n = ls.get(HIST_KEY, 20), shown = rows.slice(0, n), maxV = Math.max(...shown.map(x => x.vol || 0)) || 1;
  const hari = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"];
  box.innerHTML = `<div class="hist-head"><h3>Riwayat harian</h3>
      <div class="seg" role="group" aria-label="Jumlah hari">${[20, 60, rows.length].map(k => `<button type="button" data-n="${k}" class="${n === k || (k === rows.length && n > rows.length) ? "on" : ""}">${k === rows.length ? "Semua (" + k + ")" : k + " hari"}</button>`).join("")}</div>
      <button class="icon-btn" id="hist-csv" type="button">Unduh CSV</button></div>
    <div class="table-wrap hist-wrap"><table class="j-tbl hist-tbl"><thead><tr><th>Tanggal</th><th class="num">Buka</th><th class="num">Tertinggi</th><th class="num">Terendah</th><th class="num">Tutup</th><th class="num">Chg%</th><th class="num">Volume (lot)</th><th class="num">Nilai (perkiraan)</th><th class="num" title="Volume dibanding rata-rata 20 hari sebelumnya">× rata-rata</th></tr></thead>
    <tbody>${shown.map(x => {
      const d = new Date(x.tgl + "T00:00:00Z"), spike = x.vx != null && x.vx >= 2;
      return `<tr${spike ? ' class="spike"' : ""}><td>${hari[d.getUTCDay()]}, ${esc(x.tgl)}</td><td class="num">${fmtNum(x.o)}</td><td class="num">${fmtNum(x.h)}</td><td class="num">${fmtNum(x.l)}</td><td class="num"><b>${fmtNum(x.c)}</b></td>
        <td class="num ${x.chg == null ? "" : x.chg >= 0 ? "pos" : "neg"}">${x.chg == null ? "-" : (x.chg >= 0 ? "+" : "") + fmtDec(x.chg, 2) + "%"}</td>
        <td class="num"><span class="vbar"><i style="width:${Math.round((x.vol || 0) / maxV * 100)}%"></i></span>${x.vol == null ? "-" : fmtNum(x.vol)}</td>
        <td class="num">${x.val == null ? "-" : fmtValue(x.val)}</td>
        <td class="num">${x.vx == null ? "-" : `<span class="${spike ? "vx-hi" : ""}">${fmtDec(x.vx, 1)}×</span>`}</td></tr>`;
    }).join("")}</tbody></table></div>
    <p class="muted" style="font-size:0.78rem;margin:6px 0 0">Baris kuning = volume minimal 2 kali rata-rata 20 hari sebelumnya (hari dengan transaksi tidak biasa). Nilai transaksi dihitung dari volume × harga tutup, jadi hanya perkiraan. Data frekuensi dan broker tidak tersedia dari Yahoo.</p>
    <div class="d-actions"><a class="icon-btn" href="https://stockbit.com/symbol/${encodeURIComponent(r.t)}" target="_blank" rel="noopener" style="text-decoration:none">Lihat broker summary di Stockbit ↗</a></div>`;
  box.querySelectorAll("[data-n]").forEach(b => b.addEventListener("click", () => { ls.set(HIST_KEY, +b.dataset.n); renderHist(r); }));
  $("hist-csv").addEventListener("click", () => {
    const head = "tanggal,buka,tertinggi,terendah,tutup,chg_persen,volume_lot,nilai_perkiraan,x_rata2";
    const lines = [head].concat(rows.slice().reverse().map(x => [x.tgl, x.o, x.h, x.l, x.c, x.chg == null ? "" : x.chg.toFixed(2), x.vol ?? "", x.val == null ? "" : Math.round(x.val), x.vx == null ? "" : x.vx.toFixed(2)].join(",")));
    const blob = new Blob([lines.join("\n")], { type: "text/csv" }), url = URL.createObjectURL(blob), el = document.createElement("a");
    el.href = url; el.download = `riwayat_${r.t}_${ymd(new Date())}.csv`; document.body.appendChild(el); el.click(); el.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  });
}

/* ---------- drawer ---------- */
/* ---------- perbandingan saham & saham mirip ---------- */
const CMP_KEY = "idxs:cmp", CMP_MAX = 4, CMP_COLORS = ["#3B82F6", "#F59E0B", "#10B981", "#A855F7"];
let cmp = (ls.get(CMP_KEY, []) || []).filter(t => DATA.some(r => r.t === t)).slice(0, CMP_MAX);
let cmpPeriod = ls.get("idxs:cmpn", 60); if (cmpPeriod === 119) cmpPeriod = 120;
const saveCmp = () => { ls.set(CMP_KEY, cmp); renderCmpBar(); };
function seriesOf(o) {                       // {tgl: [...], c: [...]} dari data SMC (220 hari)
  const S = o && o.smc; if (!S || !S.b || !S.do) return null;
  const base = Date.parse(S.d0 + "T00:00:00Z");
  return { tgl: S.do.map(x => new Date(base + x * 86400000).toISOString().slice(0, 10)), c: S.b.map(b => b[3]) };
}
function perf(r, n) { const s = seriesOf(r); if (!s || s.c.length < 2) return null; const k = Math.max(0, s.c.length - 1 - n); return (s.c[s.c.length - 1] / s.c[k] - 1) * 100; }
function toggleCmp(t) {
  if (cmp.includes(t)) cmp = cmp.filter(x => x !== t);
  else { if (cmp.length >= CMP_MAX) { alert(`Maksimal ${CMP_MAX} saham dalam perbandingan. Hapus salah satu dulu.`); return false; } cmp.push(t); }
  saveCmp(); return true;
}
function renderCmpBar() {
  const bar = $("cmp-bar"); if (!bar) return;
  document.body.classList.toggle("has-cmpbar", cmp.length > 0);
  if (!cmp.length) { bar.classList.remove("show"); return; }
  bar.innerHTML = `<span><b>Bandingkan (${cmp.length}/${CMP_MAX}):</b> ${cmp.map(esc).join(", ")}</span>
    <button class="icon-btn" id="cmp-open" type="button" ${cmp.length < 2 ? "disabled title=\"Pilih minimal 2 saham\"" : ""}>Buka perbandingan</button>
    <button class="icon-btn" id="cmp-clear" type="button">Kosongkan</button>`;
  bar.classList.add("show");
  $("cmp-open").addEventListener("click", () => openCompare());
  $("cmp-clear").addEventListener("click", () => { cmp = []; saveCmp(); if (openT && openT !== "IHSG") openDetail(openT, viewMode, { keepNav: true, fromPop: true, keepFocus: true }); });
}

/* B. saham mirip: korelasi return harian 60 hari, di sektor yang sama */
function similarTo(t, n = 5) {
  const r0 = DATA.find(r => r.t === t), s0 = seriesOf(r0); if (!s0 || s0.c.length < 41) return [];
  const rets = s => { const m = new Map(); for (let i = Math.max(1, s.c.length - 60); i < s.c.length; i++) m.set(s.tgl[i], s.c[i] / s.c[i - 1] - 1); return m; };
  const a = rets(s0), sec = r0.sector && r0.sector !== "-" ? r0.sector : null;
  const out = [];
  DATA.forEach(r => {
    if (r.t === t || (sec && r.sector !== sec) || r.val < 1e9) return;
    const s = seriesOf(r); if (!s || s.c.length < 41) return;
    const b = rets(s), xs = [], ys = [];
    a.forEach((v, k) => { if (b.has(k)) { xs.push(v); ys.push(b.get(k)); } });
    if (xs.length < 30) return;
    const mx = xs.reduce((p, v) => p + v, 0) / xs.length, my = ys.reduce((p, v) => p + v, 0) / ys.length;
    let sxy = 0, sxx = 0, syy = 0; xs.forEach((x, i) => { sxy += (x - mx) * (ys[i] - my); sxx += (x - mx) ** 2; syy += (ys[i] - my) ** 2; });
    if (!sxx || !syy) return;
    out.push({ r, corr: sxy / Math.sqrt(sxx * syy) });
  });
  return out.sort((x, y) => y.corr - x.corr).slice(0, n);
}
function renderSimilar(r0) {
  const box = $("sim-sec"); if (!box) return;
  const sim = similarTo(r0.t);
  if (!sim.length) { box.innerHTML = `<h3>Saham mirip</h3><p class="muted" style="margin:0">Belum ada saham pembanding yang cukup datanya di sektor ini.</p>`; return; }
  const p20 = perf(r0, 20), avg = sim.reduce((s, x) => s + (perf(x.r, 20) || 0), 0) / sim.length;
  const say = p20 == null ? "" : p20 > avg + 3 ? `${r0.t} bergerak lebih kuat dari saham-saham miripnya dalam 20 hari terakhir.`
    : p20 < avg - 3 ? `${r0.t} tertinggal dari saham-saham miripnya dalam 20 hari terakhir. Bisa jadi kandidat menyusul, tapi cek dulu apakah ada alasan khusus ia tertinggal.`
    : `${r0.t} bergerak sejalan dengan saham-saham miripnya.`;
  box.innerHTML = `<h3>Saham mirip${r0.sector && r0.sector !== "-" ? ` di sektor ${esc(r0.sector)}` : ""}</h3>
    <p class="muted" style="font-size:0.82rem;margin:0 0 8px">Diurutkan dari pergerakan harga harian yang paling mirip dalam 60 hari terakhir (korelasi). Hanya saham dengan transaksi minimal Rp 1 M/hari.</p>
    <div class="table-wrap" style="max-height:none"><table class="j-tbl"><thead><tr><th>Saham</th><th class="num">Kemiripan</th><th class="num">20 hari</th><th>Struktur</th><th>Kondisi</th><th></th></tr></thead><tbody>
      <tr class="sim-self"><td><b>${esc(r0.t)}</b> <span class="muted">(ini)</span></td><td class="num">-</td><td class="num ${p20 >= 0 ? "pos" : "neg"}">${p20 == null ? "-" : (p20 >= 0 ? "+" : "") + fmtDec(p20, 1) + "%"}</td><td>${msCell(r0)}</td><td>${r0.kd ? `<span class="kd ${r0.kd.c}">${esc(r0.kd.l)}</span>` : "-"}</td><td></td></tr>
      ${sim.map(({ r, corr }) => { const pp = perf(r, 20); return `<tr><td><button class="link-btn" data-go="${r.t}" type="button"><b>${r.t}</b></button><div class="muted" style="font-size:0.72rem">${esc(r.nm)}</div></td>
        <td class="num">${fmtDec(corr * 100, 0)}%</td><td class="num ${pp >= 0 ? "pos" : "neg"}">${pp == null ? "-" : (pp >= 0 ? "+" : "") + fmtDec(pp, 1) + "%"}</td>
        <td>${msCell(r)}</td><td>${r.kd ? `<span class="kd ${r.kd.c}">${esc(r.kd.l)}</span>` : "-"}</td>
        <td><button class="icon-btn sim-add" data-add="${r.t}" type="button">${cmp.includes(r.t) ? "✓" : "+ Bandingkan"}</button></td></tr>`; }).join("")}
    </tbody></table></div>
    ${say ? `<p class="d-why">${esc(say)}</p>` : ""}
    <div class="d-actions"><button class="icon-btn" id="sim-cmp" type="button">Bandingkan ${esc(r0.t)} dengan 3 teratas</button></div>`;
  box.querySelectorAll("[data-go]").forEach(b => b.addEventListener("click", () => openDetail(b.dataset.go, viewMode, { keepFocus: true })));
  box.querySelectorAll("[data-add]").forEach(b => b.addEventListener("click", () => { toggleCmp(b.dataset.add); b.textContent = cmp.includes(b.dataset.add) ? "✓" : "+ Bandingkan"; }));
  $("sim-cmp").addEventListener("click", () => { cmp = [r0.t, ...sim.slice(0, 3).map(x => x.r.t)]; saveCmp(); openCompare(); });
}

/* A. halaman bandingkan */
function openCompare(fromPop) {
  if (cmp.length < 2) { alert("Pilih minimal 2 saham untuk dibandingkan."); return; }
  $("drawer").classList.remove("open"); $("scrim").classList.remove("open"); hideFull(true); openT = null;
  $("cmpv").classList.add("open"); document.body.classList.add("noscroll");
  const h = "#bandingkan=" + cmp.join(",");
  if (!fromPop) { if (location.hash.startsWith("#bandingkan=") || location.hash.startsWith("#s=")) history.replaceState({ cmp: 1 }, "", h); else history.pushState({ cmp: 1 }, "", h); }
  else history.replaceState(history.state, "", h);
  renderCompare();
}
function closeCompare() {
  if (history.state && history.state.cmp) { history.back(); return; }
  hideCompare();
}
function hideCompare() {
  if (!$("cmpv").classList.contains("open")) return;
  $("cmpv").classList.remove("open"); $("cmpv").innerHTML = ""; document.body.classList.remove("noscroll");
  if (location.hash.startsWith("#bandingkan=")) history.replaceState(null, "", location.pathname + location.search);
}
function cmpChart(rows, n) {
  const ih = MARKET.ihsg ? seriesOf(MARKET.ihsg) : null;
  const master = ih ? ih.tgl : seriesOf(rows[0]).tgl;
  const dates = master.slice(-(n + 1));
  const lines = rows.map((r, i) => ({ t: r.t, col: CMP_COLORS[i], s: seriesOf(r), dash: "" }));
  if (ih) lines.push({ t: "IHSG", col: "var(--muted)", s: ih, dash: "5 4" });
  lines.forEach(L => {
    const m = new Map(L.s.tgl.map((d, i) => [d, L.s.c[i]])); let last = null, base = null;
    L.v = dates.map(d => { if (m.has(d)) last = m.get(d); if (last != null && base == null) base = last; return last == null ? null : (last / base - 1) * 100; });
  });
  const all = lines.flatMap(L => L.v.filter(v => v != null));
  let max = Math.max(0, ...all), min = Math.min(0, ...all); const pad = (max - min) * 0.08 || 1; max += pad; min -= pad;
  const W = 1100, H = 380, Lp = 48, R = 110, T = 12, B = 26, iw = W - Lp - R, ihh = H - T - B;
  const x = i => Lp + i / Math.max(1, dates.length - 1) * iw, y = v => T + (max - v) / (max - min) * ihh;
  let s = `<svg class="d-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Perbandingan kinerja">`;
  const step = Math.pow(10, Math.floor(Math.log10((max - min) / 4 || 1))), tick = [1, 2, 5, 10].map(k => k * step).find(k => (max - min) / k <= 6) || step * 10;
  for (let v = Math.ceil(min / tick) * tick; v <= max; v += tick) s += `<line x1="${Lp}" x2="${Lp + iw}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--line)" ${Math.abs(v) < 1e-9 ? 'stroke-width="1.6" stroke="var(--muted)"' : ""}/><text x="${Lp - 6}" y="${(y(v) + 4).toFixed(1)}" font-size="11" text-anchor="end" fill="var(--muted)">${v > 0 ? "+" : ""}${fmtDec(v, Math.abs(tick) < 1 ? 1 : 0)}%</text>`;
  const used = [];
  lines.forEach(L => {
    const pts = L.v.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean);
    s += `<polyline points="${pts.join(" ")}" fill="none" stroke="${L.col}" stroke-width="${L.t === "IHSG" ? 1.6 : 2.4}" ${L.dash ? `stroke-dasharray="${L.dash}"` : ""}/>`;
    const lv = L.v[L.v.length - 1]; if (lv == null) return; let yy = y(lv) + 4; while (used.some(u => Math.abs(u - yy) < 13)) yy += 13; used.push(yy);
    s += `<text x="${Lp + iw + 8}" y="${yy.toFixed(1)}" font-size="12" font-weight="800" fill="${L.col}">${esc(L.t)} ${lv >= 0 ? "+" : ""}${fmtDec(lv, 1)}%</text>`;
  });
  s += `<text x="${Lp}" y="${H - 6}" font-size="11" fill="var(--muted)">${esc(dates[0])}</text><text x="${Lp + iw}" y="${H - 6}" font-size="11" text-anchor="end" fill="var(--muted)">${esc(dates[dates.length - 1])}</text></svg>`;
  return s;
}
function renderCompare() {
  const rows = cmp.map(t => DATA.find(r => r.t === t)).filter(Boolean), w = weights();
  const pdPos = r => { const S = r.smc; if (!S || !S.pd) return null; return Math.round((r.p - S.pd[1]) / ((S.pd[0] - S.pd[1]) || 1) * 100); };
  const lastEv = r => { const e = r.smc && r.smc.ev && r.smc.ev[r.smc.ev.length - 1]; return e ? `${e[3]} ${e[4] === 1 ? "naik" : "turun"}, ${e[5]}` : "-"; };
  const obNear = r => { const S = r.smc; if (!S || !S.ob) return "-"; const z = S.ob.filter(o => o[3] === 1 && o[2] <= r.p).sort((a, b) => b[1] - a[1])[0]; return z ? `${fmtNum(z[2])}–${fmtNum(z[1])} (${fmtDec((r.p - z[1]) / r.p * 100, 1)}% di bawah)${z[4] ? ", volume tinggi" : ""}` : "tidak ada"; };
  const pocTxt = r => { const V = r.smc && r.smc.vp; if (!V) return "-"; return `${fmtNum(V.poc)} (harga ${r.p > V.vah ? "di atas" : r.p < V.val ? "di bawah" : "di dalam"} value area)`; };
  const metr = [
    ["Harga", r => `<b>${fmtNum(r.p)}</b> <span class="${r.chg >= 0 ? "pos" : "neg"}">${r.chg >= 0 ? "+" : ""}${fmtDec(r.chg, 2)}%</span>`],
    [`Kinerja ${cmpPeriod} hari`, r => { const v = perf(r, cmpPeriod); return v == null ? "-" : `<b class="${v >= 0 ? "pos" : "neg"}">${v >= 0 ? "+" : ""}${fmtDec(v, 1)}%</b>`; }],
    ["Sektor", r => esc(r.sector || "-")],
    ["Kondisi", r => r.kd ? `<span class="kd ${r.kd.c}" title="${esc(r.kd.why)}">${esc(r.kd.l)}</span>` : "-"],
    ["Struktur W / D / 4H", r => msCell(r)],
    ["BOS/CHoCH terakhir (harian)", r => esc(lastEv(r))],
    ["Posisi range 220 hari", r => { const v = pdPos(r); return v == null ? "-" : `${v}% · ${v >= 55 ? "premium" : v <= 45 ? "discount" : "equilibrium"}`; }],
    ["OB bullish terdekat", r => esc(obNear(r))],
    ["POC volume", r => esc(pocTxt(r))],
    ["RSI", r => fmtDec(r.rsi, 1)],
    ["Checklist", r => ckCell(r)],
    ["Skor", r => fmtDec(score(r, w), 0)],
    ["Transaksi/hari", r => fmtValue(r.val)],
    ["Top 10", r => r.top ? `<span class="top-badge">#${r.top}</span>` : (r.cst && r.cst.total ? `${r.cst.count}/${r.cst.total} hari` : "-")],
  ];
  const best = rows.slice().sort((a, b) => (perf(b, cmpPeriod) ?? -1e9) - (perf(a, cmpPeriod) ?? -1e9))[0];
  const aligned = rows.filter(msAligned).map(r => r.t);
  $("cmpv").innerHTML = `
    <div class="full-head"><div class="full-head-in">
      <button class="icon-btn" id="cmp-close" type="button">← Kembali ke daftar</button>
      <div class="fh-id"><span class="fh-tk">Bandingkan saham</span><span class="fh-name">${rows.length} saham · dibanding IHSG</span></div>
      <span class="fh-right">
        <span class="cmp-chips">${rows.map((r, i) => `<span class="cmp-chip" style="border-color:${CMP_COLORS[i]}"><i style="background:${CMP_COLORS[i]}"></i>${r.t}<button type="button" data-rm="${r.t}" aria-label="Hapus ${r.t}">×</button></span>`).join("")}</span>
        ${rows.length < CMP_MAX ? `<input list="cmp-list" id="cmp-add" class="cmp-add" placeholder="+ Tambah kode"><datalist id="cmp-list">${DATA.map(r => `<option value="${r.t}">${esc(r.nm)}</option>`).join("")}</datalist>` : ""}
      </span>
    </div></div>
    <div class="full-grid cmp-grid">
      <section class="card">
        <div class="hist-head"><h3>Kinerja sejak titik awal yang sama</h3>
          <div class="seg" role="group" aria-label="Periode">${[20, 60, 120, 219].map(k => `<button type="button" data-p="${k}" class="${cmpPeriod === k ? "on" : ""}">${k === 219 ? "220 hari" : k + " hari"}</button>`).join("")}</div></div>
        ${cmpChart(rows, cmpPeriod)}
        <p class="d-why">${best ? `Paling kuat dalam ${cmpPeriod} hari terakhir: <b>${esc(best.t)}</b>.` : ""} ${aligned.length ? `Struktur searah naik (W dan D bullish): <b>${aligned.map(esc).join(", ")}</b>.` : "Belum ada yang strukturnya searah naik di Mingguan dan Harian."}</p>
        <p class="muted" style="font-size:0.78rem;margin:4px 0 0">Setiap garis menunjukkan perubahan harga dalam % sejak hari pertama periode, jadi saham dengan harga berbeda bisa dibandingkan langsung. Garis putus-putus abu-abu = IHSG.</p>
      </section>
      <section class="card">
        <div class="table-wrap" style="max-height:none"><table class="j-tbl cmp-tbl"><thead><tr><th></th>${rows.map((r, i) => `<th style="border-bottom:3px solid ${CMP_COLORS[i]}"><button class="link-btn" data-open="${r.t}" type="button"><b>${r.t}</b></button><div class="muted" style="font-size:0.72rem;font-weight:500">${esc(r.nm)}</div></th>`).join("")}</tr></thead>
          <tbody>${metr.map(([lab, f]) => `<tr><td class="muted">${lab}</td>${rows.map(r => `<td>${f(r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>
        <p class="muted" style="font-size:0.78rem;margin:8px 0 0">Klik kode saham di judul kolom untuk membuka detailnya. Pilihan perbandingan tersimpan di browser ini.</p>
      </section>
    </div>`;
  $("cmp-close").addEventListener("click", closeCompare);
  $("cmpv").querySelectorAll("[data-p]").forEach(b => b.addEventListener("click", () => { cmpPeriod = +b.dataset.p; ls.set("idxs:cmpn", cmpPeriod); renderCompare(); }));
  $("cmpv").querySelectorAll("[data-rm]").forEach(b => b.addEventListener("click", () => { toggleCmp(b.dataset.rm); if (cmp.length < 2) closeCompare(); else openCompare(true); }));
  $("cmpv").querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () => { const t = b.dataset.open; hideCompare(); openDetail(t, "full"); }));
  const add = $("cmp-add");
  if (add) add.addEventListener("change", () => { const t = add.value.trim().toUpperCase(); if (DATA.some(r => r.t === t) && !cmp.includes(t)) { toggleCmp(t); openCompare(true); } else add.value = ""; });
}

/* ---------- analisa emas dalam rupiah (layar penuh) ---------- */
const ANTAM_KEY = "idxs:antam";
function openEmas() {
  const r0 = MARKET.emas; if (!r0) return;
  const r = { ...r0 };
  hideCompare(); $("drawer").classList.remove("open"); $("scrim").classList.remove("open"); $("drawer").innerHTML = "";
  viewMode = "full"; openT = r.t; navList = [];
  $("full").innerHTML = `
    <div class="full-head"><div class="full-head-in">
      <button class="icon-btn" id="d-close" type="button">← Kembali</button>
      <div class="fh-id"><span class="fh-tk" id="d-title">Emas (Rp/gram)</span><span class="fh-name">Emas dunia dirupiahkan · data ${esc(r.tgl)}</span></div>
      <span class="fh-price">Rp ${fmtNum(r.p)} <span class="${r.chg >= 0 ? "pos" : "neg"}" style="font-size:1rem">${r.chg >= 0 ? "+" : ""}${fmtDec(r.chg, 2)}%</span></span>
      <span class="fh-right">${msBlock(r) ? "" : ""}</span>
    </div></div>
    <div class="full-grid full-grid2">
      <section class="card full-span"><div class="d-sec"><div class="chart-head"><h3 id="smc-title">Chart harian dengan Smart Money Concepts</h3><div id="tf-bar"></div></div>
        <div class="frvp-ctl" id="frvp-ctl"></div><div class="draw-ctl" id="draw-ctl"></div><div id="smc-box"></div><div class="draw-sel" id="draw-sel"></div>
        <div class="chips smc-toggles" id="smc-toggles"></div><ul class="smc-sum" id="smc-sum"></ul>
        <p class="muted" style="font-size:0.78rem;margin:6px 0 0">Harga = emas dunia (USD/oz) × kurs USD/IDR ÷ 31,1035. Volume = jumlah kontrak emas dunia, karena harga emas dalam rupiah tidak punya data volume sendiri.</p></div></section>
      <div class="full-col"><section class="card">${msBlock(r)}</section></div>
      <div class="full-col"><section class="card" id="emas-plan"></section></div>
    </div>`;
  $("full").classList.add("open"); document.body.classList.add("noscroll"); $("full").scrollTop = 0;
  $("d-close").addEventListener("click", closeFull); $("d-close").focus();
  renderEmasPlan(r);
}
function renderEmasPlan(r) {
  const box = $("emas-plan"); if (!box) return;
  const P = r.plans || {}, kf = r.smc && r.smc.kf, NAMA = { K: "Konfluensi", S: "Order block", A: "ATR" };
  let pick = r._pick || (r.plan && r.plan.src) || Object.keys(P)[0];
  const use = P[pick];
  r.plan = use ? { ...use, src: pick } : null; renderSmc(r);
  if (!use) { box.innerHTML = "<h3>Rencana</h3><p class='muted'>Belum ada rencana yang bisa dihitung.</p>"; return; }
  const mid = (use.e1 + use.e2) / 2, rr = (use.tp - mid) / (mid - use.sl);
  const antam = +ls.get(ANTAM_KEY, 0) || 0, prem = antam > 0 ? antam / r.p - 1 : null, cv = v => Math.round(v * (1 + prem) / 1000) * 1000;
  const FK = [["tren", "Struktur bullish"], ["fibo", "Fibo 0,5–0,786"], ["volume", "Volume dorongan"], ["ob", "Order block"], ["fvg", "FVG"], ["ma", "MA20/50"]];
  box.innerHTML = `<h3>Rencana dalam Rp/gram (contoh, bukan rekomendasi)</h3>
    <div class="seg" role="group" aria-label="Jenis rencana">${["K", "S", "A"].map(k => `<button type="button" data-ep="${k}" class="${pick === k ? "on" : ""}" ${P[k] ? "" : "disabled"}>${NAMA[k]}</button>`).join("")}</div>
    ${pick === "K" && kf ? `<div class="kf-box"><div class="kf-head">Skor konfluensi <b>${kf.skor}/6</b></div><div class="kf-list">${FK.map(([k, n]) => `<span class="${kf.fk[k] ? "y" : "x"}">${kf.fk[k] ? "✓" : "✗"} ${n}</span>`).join("")}</div></div>` : kf && !kf.lay ? `<p class="muted" style="font-size:0.8rem">Konfluensi: ${esc(kf.alasan || "belum layak")}</p>` : ""}
    <div class="plan-box"><div><small>Area entry</small><b>${fmtNum(use.e1)}–${fmtNum(use.e2)}</b></div><div><small>Stop loss</small><b class="neg">${fmtNum(use.sl)}</b></div>
      <div><small>Target${use.tp2 ? " 1 / 2 / 3" : ""}</small><b class="pos">${fmtNum(use.tp)}${use.tp2 ? ` / ${fmtNum(use.tp2)} / ${fmtNum(use.tp3)}` : ""}</b></div><div><small>Risiko / R:R</small><b>${fmtDec(use.risk, 1)}% · 1:${fmtDec(rr, 1)}</b></div></div>
    <h3 style="margin-top:14px">Terjemahkan ke harga Antam / Pegadaian</h3>
    <div class="calc"><div class="f"><label for="antam-in">Harga beli emas batangan hari ini (Rp/gram)</label><input type="number" id="antam-in" min="0" step="1000" placeholder="mis. 2150000" value="${antam || ""}"></div>
      <div class="f"><label>Selisih dengan emas dunia (premium)</label><input type="text" readonly value="${prem == null ? "-" : (prem >= 0 ? "+" : "") + fmtDec(prem * 100, 1) + "%"}"></div></div>
    ${prem == null ? `<p class="muted" style="font-size:0.82rem;margin:4px 0 0">Isi harga beli dari situs Antam/Pegadaian/aplikasi emasmu. Selisihnya dipakai untuk menerjemahkan area entry, SL, dan TP di atas ke harga batangan.</p>`
      : `<div class="plan-box" style="margin-top:8px"><div><small>Entry (harga batangan)</small><b>${fmtNum(cv(use.e1))}–${fmtNum(cv(use.e2))}</b></div><div><small>Stop loss</small><b class="neg">${fmtNum(cv(use.sl))}</b></div><div><small>Target</small><b class="pos">${fmtNum(cv(use.tp))}</b></div><div><small>Harga batangan sekarang</small><b>${fmtNum(antam)}</b></div></div>
         <p class="muted" style="font-size:0.78rem;margin:6px 0 0">Asumsi: selisih harga batangan terhadap emas dunia tetap sama. Kenyataannya selisih ini bisa berubah, dan harga jual kembali (buyback) biasanya lebih rendah dari harga beli, jadi hitung juga selisih beli-jual sebelum memasang target.</p>`}`;
  box.querySelectorAll("[data-ep]").forEach(b => b.addEventListener("click", () => { r._pick = b.dataset.ep; renderEmasPlan(r); }));
  const inp = $("antam-in"); inp.addEventListener("change", () => { ls.set(ANTAM_KEY, +inp.value || 0); renderEmasPlan(r); });
}

/* ---------- detail saham: panel kanan & layar penuh ---------- */
let viewMode = "panel", navList = [];
function currentNav(t) { const { pinned, rows } = displayRows(); const l = pinned.map(r => r.t).concat(rows.map(r => r.t)); return l.includes(t) ? l : [t]; }
function detailParts(r, r0, w) {
  const up = r.chg >= 0, c = r._ck, p = r.plan, tf = r.tf || {};
  const comp = [["Trend", r.trend, w.trend], ["Breakout", r.brk, w.brk], ["Price action", r.pa, w.pa], ["Momentum", r.mom, w.mom], ["Struktur SMC", r.st ?? 50, w.st]];
  const tfNames = [["h1", "1 jam"], ["h2", "2 jam"], ["h4", "4 jam"], ["daily", "Harian"], ["weekly", "Mingguan"], ["monthly", "Bulanan"]];
  const sub = `${esc(r.nm)}${r.sector && r.sector !== "-" ? `${r.nm ? " · " : ""}${esc(r.sector)}` : ""}`;
  return {
    sub, up,
    price: `${fmtNum(r.p)} <span class="${up ? "pos" : "neg"}" style="font-size:1rem">${up ? "+" : ""}${fmtDec(r.chg, 2)}%</span>`,
    meta: `Candle terakhir ${esc(r.tgl)}. Skor ${fmtDec(r.score, 0)} dengan bobot saat ini.${r.top ? ` <span class="top-badge">Top 10 #${r.top}</span>` : ""}`,
    kond: `<div class="d-sec">${r.kd ? `<span class="kd ${r.kd.c}">${esc(r.kd.l)}</span><div class="d-why">${esc(r.kd.why)}.</div>` : ""}<div style="margin-top:6px">${badges(r)}</div></div>`,
    struktur: msBlock(r),
    chart: r.smc ? `<div class="d-sec"><div class="chart-head"><h3 id="smc-title">Chart harian dengan Smart Money Concepts</h3><div id="tf-bar"></div></div>
      <div class="frvp-ctl" id="frvp-ctl"></div>
      <div class="draw-ctl" id="draw-ctl"></div>
      <div id="smc-box"></div>
      <div class="draw-sel" id="draw-sel"></div>
      <div class="chips smc-toggles" id="smc-toggles"></div>
      <ul class="smc-sum" id="smc-sum"></ul>
      <p class="muted" style="font-size:0.78rem;margin:6px 0 0">SMC di sini versi sederhana yang dihitung otomatis, jadi bisa berbeda dari indikator SMC di TradingView atau Stockbit. Garis putus-putus = CHoCH, garis penuh = BOS. Lingkaran kuning di bawah = purnama, lingkaran gelap = bulan baru (ditaruh di hari bursa terdekat).</p>
    </div>` : `<div class="d-sec"><h3>Chart 30 hari</h3>${bigChart(r)}
      <div class="legend"><span><i style="background:var(--blue)"></i>MA20</span><span><i style="background:var(--orange)"></i>MA50</span>${p ? '<span><i style="background:var(--accent);opacity:.35;height:8px"></i>Area entry</span><span><i style="background:var(--down)"></i>Stop loss</span><span><i style="background:var(--up)"></i>Target</span>' : ""}</div>
      <p class="muted" style="font-size:0.78rem;margin:6px 0 0">Chart SMC belum tersedia karena riwayat harga saham ini masih terlalu pendek.</p>
    </div>`,
    checklist: `<div class="d-sec"><h3>Checklist: ${c.pass} dari ${c.total} syarat terpenuhi</h3>
      <ul class="checklist">${c.items.map(([label, ok]) => `<li><span class="ci ${ok === null ? "na" : ok ? "y" : "x"}">${ok === null ? "–" : ok ? "✓" : "✗"}</span><span>${esc(label)}${ok === null ? ' <span class="muted">(data tidak tersedia)</span>' : ""}</span></li>`).join("")}</ul></div>`,
    plan: '<div class="d-sec" id="plan-sec"></div>',
    hist: '<div class="d-sec" id="hist-sec"></div>',
    skor: `<div class="d-sec"><h3>Rincian skor</h3><div class="bars">${comp.map(([n, v, wt]) => `<div class="bar-row"><span>${n}</span><span class="track"><i style="width:${v}%"></i></span><span>${v}/100, bobot ${wt}</span></div>`).join("")}</div></div>`,
    tf: `<div class="d-sec"><h3>Ringkasan per timeframe</h3><div class="tf-grid">${tfNames.map(([k, n]) => `<div class="tf-cell"><small>${n}</small>${tf[k] ? `<span class="v ${vClass(tf[k].summary)}">${esc(tf[k].summary)}</span><small>${esc(tf[k].ma_detail)}</small>` : '<span class="muted">-</span>'}</div>`).join("")}</div></div>`,
    lain: `<div class="d-sec"><h3>Data lain</h3><div class="muted" style="font-size:0.86rem">RSI ${fmtDec(r.rsi, 1)}. Volume ${fmtDec(r.vr, 2)}× rata-rata. Transaksi ${fmtValue(r.val)}/hari. Beta ${r.beta == null ? "-" : fmtDec(r.beta, 2)}. ${r.cst && r.cst.total ? `Masuk Top 10 ${r.cst.count} dari ${r.cst.total} hari terakhir.` : ""}</div></div>`,
    star: `<button class="icon-btn" id="d-star" type="button">${watch.has(r.t) ? "★ Hapus dari watchlist" : "☆ Tambah ke watchlist"}</button>`,
    cmpb: `<button class="icon-btn" id="d-cmp" type="button">${cmp.includes(r.t) ? "✓ Di perbandingan" : "+ Bandingkan"}</button>${cmp.includes(r.t) && cmp.length >= 2 ? `<button class="icon-btn" id="d-cmp-open" type="button">Buka perbandingan (${cmp.length})</button>` : ""}`,
    sim: '<div class="d-sec" id="sim-sec"></div>',
    foot: '<p class="d-foot">Semua angka dihitung otomatis dari data Yahoo Finance dan bisa tertunda. Cocokkan dengan chart di aplikasi trading-mu sebelum mengambil keputusan.</p>',
  };
}
function navHtml(t) {
  const i = navList.indexOf(t), n = navList.length;
  if (n <= 1) return "";
  return `<span class="d-nav"><button class="icon-btn" id="d-prev" type="button" ${i <= 0 ? "disabled" : ""} aria-label="Saham sebelumnya">‹</button><span class="muted d-pos">${i + 1} / ${n}</span><button class="icon-btn" id="d-next" type="button" ${i >= n - 1 ? "disabled" : ""} aria-label="Saham berikutnya">›</button></span>`;
}
function openDrawer(t) { openDetail(t, "panel"); }
function openDetail(t, mode, opt = {}) {
  const r0 = DATA.find(x => x.t === t); if (!r0) return;
  const w = weights(), r = { ...r0, score: score(r0, w) };
  if (!opt.keepNav) navList = currentNav(t);
  viewMode = mode; openT = t;
  const P = detailParts(r, r0, w);
  if (mode === "full") {
    $("drawer").classList.remove("open"); $("scrim").classList.remove("open"); $("drawer").innerHTML = "";
    $("full").innerHTML = `
      <div class="full-head"><div class="full-head-in">
        <button class="icon-btn" id="d-close" type="button">← Kembali ke daftar</button>
        <div class="fh-id"><span class="fh-tk" id="d-title">${r.t}</span><span class="fh-name">${P.sub}</span></div>
        <span class="fh-price">${P.price}</span>
        ${r.kd ? `<span class="kd ${r.kd.c}" title="${esc(r.kd.why)}">${esc(r.kd.l)}</span>` : ""}
        ${r.top ? `<span class="top-badge">Top 10 #${r.top}</span>` : ""}
        <span class="fh-right">${P.star}${P.cmpb}${navHtml(t)}</span>
      </div></div>
      <div class="full-grid full-grid2">
        <section class="card full-span">${P.chart}</section>
        <div class="full-col">
          <section class="card"><div class="muted" style="font-size:0.82rem">Candle terakhir ${esc(r.tgl)}. Skor ${fmtDec(r.score, 0)} dengan bobot saat ini.</div>${P.kond}${P.struktur}</section>
          <section class="card">${P.checklist}</section>
        </div>
        <div class="full-col">
          <section class="card">${P.plan}</section>
          <section class="card">${P.skor}${P.tf}${P.lain}${P.foot}</section>
        </div>
        <section class="card full-span">${P.sim}</section>
        <section class="card full-span">${P.hist}</section>
      </div>`;
    $("full").classList.add("open"); document.body.classList.add("noscroll");
    if (!opt.fromPop) {
      const h = "#s=" + t;
      if (location.hash.startsWith("#s=")) history.replaceState({ s: t }, "", h); else history.pushState({ s: t }, "", h);
    }
    $("full").scrollTop = 0; $("d-close").focus();
  } else {
    hideFull(true);
    $("drawer").innerHTML = `
      <div class="d-head">
        <div><div class="d-tk" id="d-title">${r.t}</div><div class="d-name">${P.sub}</div></div>
        <div class="d-head-btns">${navHtml(t)}<button class="icon-btn" id="d-full" type="button" title="Buka layar penuh">⤢ Layar penuh</button><button class="icon-btn" id="d-close" type="button">Tutup</button></div>
      </div>
      <div class="d-price">${P.price}</div>
      <div class="muted" style="font-size:0.8rem">${P.meta}</div>
      ${P.kond}${P.struktur}${P.chart}${P.plan}${P.checklist}${P.sim}${P.hist}${P.skor}${P.tf}${P.lain}
      <div class="d-actions">${P.star}${P.cmpb}</div>${P.foot}`;
    $("drawer").classList.add("open"); $("scrim").classList.add("open");
    if (!opt.keepFocus) $("drawer").focus();
    $("d-full").addEventListener("click", () => openDetail(t, "full", { keepNav: true }));
  }
  $("d-close").addEventListener("click", mode === "full" ? closeFull : closeDrawer);
  $("d-star").addEventListener("click", () => { toggleWatch(t); openDetail(t, mode, { keepNav: true, fromPop: true, keepFocus: true }); });
  $("d-cmp").addEventListener("click", () => { if (toggleCmp(t) !== false) openDetail(t, mode, { keepNav: true, fromPop: true, keepFocus: true }); });
  const co = $("d-cmp-open"); if (co) co.addEventListener("click", () => openCompare());
  const pv = $("d-prev"), nx = $("d-next");
  if (pv) pv.addEventListener("click", () => stepDetail(-1));
  if (nx) nx.addEventListener("click", () => stepDetail(1));
  renderPlan(r0, r);
  renderHist(r0);
  renderSimilar(r0);
}
function stepDetail(d) {
  const i = navList.indexOf(openT), j = i + d;
  if (i < 0 || j < 0 || j >= navList.length) return;
  openDetail(navList[j], viewMode, { keepNav: true, keepFocus: true });
}
function hideFull(silent) {
  if (!$("full").classList.contains("open")) return;
  $("full").classList.remove("open"); $("full").innerHTML = ""; document.body.classList.remove("noscroll");
  if (!silent && location.hash.startsWith("#s=")) history.replaceState(null, "", location.pathname + location.search);
}
function closeFull() {
  const t = openT;
  if (history.state && history.state.s) { history.back(); return; }   // popstate akan menutup tampilan
  hideFull(); openT = null;
  const tr = document.querySelector(`tr[data-t="${t}"]`); if (tr) tr.focus();
}
window.addEventListener("popstate", () => {
  const mc = location.hash.match(/^#bandingkan=([A-Z0-9,]+)$/);
  if (mc) { cmp = mc[1].split(",").filter(t => DATA.some(r => r.t === t)).slice(0, CMP_MAX); saveCmp(); if (cmp.length >= 2) { openCompare(true); return; } }
  if ($("cmpv").classList.contains("open")) hideCompare();
  const m = location.hash.match(/^#s=([A-Z0-9]+)$/);
  if (m && DATA.some(r => r.t === m[1])) openDetail(m[1], "full", { keepNav: navList.includes(m[1]), fromPop: true });
  else if ($("full").classList.contains("open")) {
    const t = openT; hideFull(true); openT = null;
    const tr = document.querySelector(`tr[data-t="${t}"]`); if (tr) tr.focus();
  }
});

function openIhsg() {
  const m = MARKET.ihsg; if (!m) return;
  hideCompare(); $("drawer").classList.remove("open"); $("scrim").classList.remove("open"); $("drawer").innerHTML = "";
  viewMode = "full"; navList = []; openT = "IHSG";
  const up = m.chg >= 0, tf = m.tf || {}, b = MARKET.breadth;
  const r = { t: "IHSG", nm: "Indeks Harga Saham Gabungan", p: m.p, chg: m.chg, smc: m.smc, plan: null, tfx: m.tfx || [], ms: m.ms };
  const pos = (v, n) => v ? `<li><span class="ci ${m.p > v ? "y" : "x"}">${m.p > v ? "✓" : "✗"}</span><span>${m.p > v ? "Di atas" : "Di bawah"} ${n} (${fmtDec(v, 2)})</span></li>` : "";
  const tfNames = [["h1", "1 jam"], ["h2", "2 jam"], ["h4", "4 jam"], ["daily", "Harian"], ["weekly", "Mingguan"], ["monthly", "Bulanan"]];
  $("full").innerHTML = `
    <div class="full-head"><div class="full-head-in">
      <button class="icon-btn" id="d-close" type="button">← Kembali</button>
      <div class="fh-id"><span class="fh-tk" id="d-title">IHSG</span><span class="fh-name">Indeks Harga Saham Gabungan · candle terakhir ${esc(m.tgl || "")}</span></div>
      <span class="fh-price">${fmtDec(m.p, 2)} <span class="${up ? "pos" : "neg"}" style="font-size:1rem">${up ? "+" : ""}${fmtDec(m.chg, 2)}%</span></span>
    </div></div>
    <div class="full-grid full-grid2">
      ${m.smc ? `<section class="card full-span"><div class="d-sec"><div class="chart-head"><h3 id="smc-title">Chart harian dengan Smart Money Concepts</h3><div id="tf-bar"></div></div>
        <div class="frvp-ctl" id="frvp-ctl"></div><div class="draw-ctl" id="draw-ctl"></div><div id="smc-box"></div><div class="draw-sel" id="draw-sel"></div>
        <div class="chips smc-toggles" id="smc-toggles"></div><ul class="smc-sum" id="smc-sum"></ul></div></section>` : ""}
      <div class="full-col">
        <section class="card"><div class="muted" style="font-size:0.82rem">Ringkasan teknikal harian: ${esc(m.d || "-")}${m.rsi ? `, RSI ${fmtDec(m.rsi, 1)}` : ""}.</div>${msBlock({ ms: m.ms })}</section>
        <section class="card"><div class="d-sec"><h3>Posisi terhadap moving average</h3><ul class="checklist">${pos(m.ma20, "MA20")}${pos(m.ma50, "MA50")}${pos(m.ma200, "MA200")}</ul></div></section>
      </div>
      <div class="full-col">
        <section class="card"><div class="d-sec"><h3>Ringkasan per timeframe</h3><div class="tf-grid">${tfNames.map(([k, n]) => `<div class="tf-cell"><small>${n}</small>${tf[k] ? `<span class="v ${vClass(tf[k].summary)}">${esc(tf[k].summary)}</span><small>${esc(tf[k].ma_detail)}</small>` : '<span class="muted">-</span>'}</div>`).join("")}</div></div></section>
        ${b ? `<section class="card"><div class="d-sec"><h3>Napas pasar</h3><div class="muted" style="font-size:0.88rem">${b.pct}% dari ${fmtNum(b.n)} saham likuid (transaksi ≥ Rp 1 M/hari) berada di atas MA20.</div></div></section>` : ""}
      </div>
    </div>
    <p class="d-foot" style="max-width:1880px;margin:0 auto;padding:0 28px 40px">Data IHSG dari Yahoo Finance (^JKSE), bisa tertunda. Kondisi IHSG dipakai sebagai salah satu syarat di checklist setiap saham.</p>`;
  $("full").classList.add("open"); document.body.classList.add("noscroll"); $("full").scrollTop = 0;
  $("d-close").addEventListener("click", closeFull); $("d-close").focus();
  if (m.smc) renderSmc(r);
}

function closeDrawer() { $("drawer").classList.remove("open"); $("scrim").classList.remove("open"); const tr = openT === "IHSG" ? $("ihsg-card") : document.querySelector(`tr[data-t="${openT}"]`); openT = null; if (tr) tr.focus(); }
function toggleWatch(t) { watch.has(t) ? watch.delete(t) : watch.add(t); ls.set(WATCH, [...watch]); render(); }

/* ---------- events ---------- */
document.querySelectorAll(".preset-btn[data-preset]").forEach(b => b.addEventListener("click", () => applyPreset(b.dataset.preset)));
$("watch-btn").addEventListener("click", () => {
  $("f-watch").checked = !$("f-watch").checked; $("search").value = "";
  page = 0; markPreset(); save(); render();
});
W.forEach(id => $(id).addEventListener("input", () => { $(id + "-val").textContent = $(id).value; activePreset = null; markPreset(); page = 0; save(); render(); }));
$("min-score").addEventListener("input", function () { $("min-score-val").textContent = this.value; page = 0; save(); render(); });
CHECKS.forEach(id => $(id).addEventListener("change", () => { page = 0; save(); render(); }));
FIELDS.forEach(id => $(id).addEventListener(id === "kd-filter" || id === "sector-filter" ? "change" : "input", () => { page = 0; save(); render(); }));
$("prev-page").addEventListener("click", () => { page--; save(); render(); });
$("next-page").addEventListener("click", () => { page++; save(); render(); });
document.querySelectorAll("thead th[data-key]").forEach(th => th.addEventListener("click", () => {
  const k = th.dataset.key; if (sortKey === k) sortDir *= -1; else { sortKey = k; sortDir = k === "t" || k === "sector" ? 1 : -1; }
  markPreset(); save(); render();
}));
$("tbody").addEventListener("click", e => {
  if (e.target.closest("tr.grp-top")) { ls.set("idxs:topopen", !ls.get("idxs:topopen", true)); render(); return; }
  const st = e.target.closest("[data-star]"); if (st) { e.stopPropagation(); toggleWatch(st.dataset.star); return; }
  if (e.target.closest(".spark-cell")) return;                       // klik chart mini = popup chart, bukan panel detail
  const tr = e.target.closest("tr[data-t]"); if (tr) openDrawer(tr.dataset.t);
});
$("tbody").addEventListener("keydown", e => { if (e.key === "Enter" && e.target.matches("tr[data-t]")) openDrawer(e.target.dataset.t); });
$("scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", e => {
  const inField = e.target && e.target.closest && e.target.closest("input, textarea, select");
  if (e.key === "Escape" && !$("rf-pop").hidden) { $("rf-pop").hidden = true; return; }
  if (e.key === "Escape" && !$("cpop").hidden) { cpopHide(); return; }
  if (e.key === "Escape" && $("cmpv").classList.contains("open")) { closeCompare(); return; }
  if (drawTool === "ew" && curChartR && !inField) {
    if (e.key === "Enter" && drawPending.length >= 2) { e.preventDefault(); finishDrawing(curChartR); return; }
    if (e.key === "Backspace" && drawPending.length) { e.preventDefault(); drawPending.pop(); drawSmc(curChartR); return; }
  }
  if (e.key === "Escape" && (drawTool || drawPending.length) && curChartR) { drawTool = null; drawPending = []; drawSmc(curChartR); return; }
  if ((e.key === "Delete" || e.key === "Backspace") && drawSel && curChartR && !inField) { e.preventDefault(); deleteDrawing(curChartR, drawSel); return; }
  if (!openT) return;
  if (e.key === "Escape") { if ($("full").classList.contains("open")) closeFull(); else closeDrawer(); return; }
  if ((e.key === "ArrowLeft" || e.key === "ArrowRight") && openT !== "IHSG" && !(e.target && e.target.closest && e.target.closest("input, select, textarea"))) {
    e.preventDefault(); stepDetail(e.key === "ArrowLeft" ? -1 : 1);
  }
});

/* ---------- popup chart dari chart mini di tabel ---------- */
let cpopT = null, cpopPinned = false, cpopTimer = null, cpopN = ls.get("idxs:cpopn", 60);
function cpopSvg(r, n) {
  const S = r.smc; if (!S || !S.b) return '<p class="muted">Data chart belum tersedia.</p>';
  const all = S.b, b = all.slice(-n), off = all.length - b.length, W = 520, H = 250, L = 6, R = 62, T = 8, B = 20, iw = W - L - R, ih = H - T - B;
  const ma = all.map((_, i) => i >= 19 ? all.slice(i - 19, i + 1).reduce((s, x) => s + x[3], 0) / 20 : null).slice(off);
  let max = Math.max(...b.map(x => x[1])), min = Math.min(...b.map(x => x[2])); const pad = (max - min) * 0.05 || 1; max += pad; min -= pad;
  const sw = iw / b.length, bw = Math.max(1.5, sw * 0.62), x = i => L + i * sw + sw / 2, y = v => T + (max - v) / (max - min) * ih;
  const raw = (max - min) / 5, mag = Math.pow(10, Math.floor(Math.log10(raw || 1))), st = [1, 2, 2.5, 5, 10].map(k => k * mag).find(k => k >= raw) || mag * 10;
  let s = `<svg class="cpop-svg" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chart ${esc(r.t)} ${n} hari">`;
  for (let v = Math.ceil(min / st) * st; v <= max; v += st) s += `<line x1="${L}" x2="${L + iw}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="var(--line)"/><text x="${L + iw + 6}" y="${(y(v) + 4).toFixed(1)}" font-size="10.5" fill="var(--muted)">${fmtNum(v)}</text>`;
  b.forEach((c, i) => { const [o, hi, lo, cl] = c, col = cl >= o ? "var(--up)" : "var(--down)", top = Math.min(y(o), y(cl)), bh = Math.max(1, Math.abs(y(cl) - y(o)));
    s += `<line x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${y(hi).toFixed(1)}" y2="${y(lo).toFixed(1)}" stroke="${col}"/><rect x="${(x(i) - bw / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${bh.toFixed(1)}" fill="${col}"/>`; });
  const pts = ma.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean);
  if (pts.length > 1) s += `<polyline points="${pts.join(" ")}" fill="none" stroke="var(--blue)" stroke-width="1.4" opacity="0.9"/>`;
  const last = b[b.length - 1][3], col = last >= b[b.length - 1][0] ? "var(--up)" : "var(--down)";
  s += `<line x1="${L}" x2="${L + iw}" y1="${y(last).toFixed(1)}" y2="${y(last).toFixed(1)}" stroke="${col}" stroke-dasharray="2 3"/>`;
  s += `<rect x="${L + iw + 2}" y="${(y(last) - 8).toFixed(1)}" width="${R - 4}" height="16" rx="3" fill="${col}"/><text x="${L + iw + 6}" y="${(y(last) + 4).toFixed(1)}" font-size="10.5" font-weight="800" fill="#fff">${fmtNum(last)}</text>`;
  s += `<text x="${L}" y="${H - 5}" font-size="10" fill="var(--muted)">${esc(tglIdx(S, off))}</text><text x="${L + iw}" y="${H - 5}" font-size="10" text-anchor="end" fill="var(--muted)">${esc(tglIdx(S, all.length - 1))}</text></svg>`;
  return s;
}
function cpopRender() {
  const r = DATA.find(x => x.t === cpopT), box = $("cpop"); if (!r) return;
  const S = r.smc, n = Math.min(cpopN, S && S.b ? S.b.length : 30), b = S && S.b ? S.b.slice(-n) : [];
  const chgN = b.length ? (b[b.length - 1][3] / b[0][0] - 1) * 100 : null, hi = b.length ? Math.max(...b.map(x => x[1])) : null, lo = b.length ? Math.min(...b.map(x => x[2])) : null;
  box.innerHTML = `<div class="cpop-head"><div><b>${esc(r.t)}</b> <span class="muted">${esc(r.nm)}</span><div style="font-size:0.84rem">${fmtNum(r.p)} <span class="${r.chg >= 0 ? "pos" : "neg"}">${r.chg >= 0 ? "+" : ""}${fmtDec(r.chg, 2)}%</span>${r.kd ? ` <span class="kd ${r.kd.c}">${esc(r.kd.l)}</span>` : ""}</div></div>
      <div class="cpop-ctl"><div class="seg">${[30, 60, 120].map(k => `<button type="button" data-cn="${k}" class="${cpopN === k ? "on" : ""}">${k} hari</button>`).join("")}</div>${cpopPinned ? '<button type="button" class="icon-btn dw-small" id="cpop-x" aria-label="Tutup">✕</button>' : ""}</div></div>
    ${cpopSvg(r, n)}
    <div class="cpop-foot"><span class="muted">${n} hari: <b class="${chgN >= 0 ? "pos" : "neg"}">${chgN == null ? "-" : (chgN >= 0 ? "+" : "") + fmtDec(chgN, 1) + "%"}</b> · tertinggi ${fmtNum(hi)} · terendah ${fmtNum(lo)} · <span style="color:var(--blue)">━</span> MA20</span>
      <button type="button" class="icon-btn dw-small" id="cpop-open">Buka detail →</button></div>`;
  box.querySelectorAll("[data-cn]").forEach(bt => bt.addEventListener("click", () => { cpopN = +bt.dataset.cn; ls.set("idxs:cpopn", cpopN); cpopPinned = true; cpopRender(); }));
  const x = $("cpop-x"); if (x) x.addEventListener("click", cpopHide);
  $("cpop-open").addEventListener("click", () => { const t = cpopT; cpopHide(); openDrawer(t); });
}
function cpopPlace(cell) {
  const box = $("cpop"), rc = cell.getBoundingClientRect(), w = box.offsetWidth || 540, h = box.offsetHeight || 340;
  let left = rc.right + 12, top = rc.top + rc.height / 2 - h / 2;
  if (left + w > innerWidth - 8) left = Math.max(8, rc.left - w - 12);
  if (left < 8) left = 8;
  top = Math.max(8, Math.min(top, innerHeight - h - 8));
  box.style.left = left + "px"; box.style.top = top + "px";
}
function cpopShow(cell, pin) {
  clearTimeout(cpopTimer);
  const t = cell.dataset.sp; if (!t) return;
  if (cpopT !== t || $("cpop").hidden) { cpopT = t; cpopPinned = !!pin; cpopRender(); $("cpop").hidden = false; }
  else if (pin) { cpopPinned = true; cpopRender(); }
  cpopPlace(cell);
}
function cpopHide() { clearTimeout(cpopTimer); $("cpop").hidden = true; cpopT = null; cpopPinned = false; }
const canHover = window.matchMedia && matchMedia("(hover: hover)").matches;
document.addEventListener("mouseover", e => {
  if (!canHover) return;
  const c = e.target.closest && e.target.closest(".spark-cell");
  if (c) { if (!cpopPinned || cpopT !== c.dataset.sp) { cpopPinned = false; cpopShow(c, false); } return; }
  if (!cpopPinned && !$("cpop").hidden && !(e.target.closest && e.target.closest("#cpop"))) { clearTimeout(cpopTimer); cpopTimer = setTimeout(cpopHide, 180); }
});
document.addEventListener("click", e => {
  const c = e.target.closest && e.target.closest(".spark-cell");
  if (c) { e.preventDefault(); cpopShow(c, true); return; }
  const inPop = (e.composedPath ? e.composedPath() : []).includes($("cpop")) || (e.target.closest && e.target.closest("#cpop"));
  if (!$("cpop").hidden && !inPop) cpopHide();          // composedPath: tetap benar walau isi popup baru digambar ulang
});
window.addEventListener("scroll", () => { if (!$("cpop").hidden && !cpopPinned) cpopHide(); }, { passive: true });

/* ---------- tombol perbarui data: jalankan workflow GitHub dari aplikasi ---------- */
const GH_KEY = "idxs:ghtok";
const GH = (() => { const h = location.hostname.match(/^([^.]+)\.github\.io$/i), seg = location.pathname.split("/").filter(Boolean)[0];
  return h && seg ? { owner: h[1], repo: seg } : { owner: "YusufCahyoNusantoro", repo: "idx-screener" }; })();
const GH_ACTIONS = `https://github.com/${GH.owner}/${GH.repo}/actions/workflows/screener.yml`;
let rfPoll = null, rfStart = null;
function ghApi(path, opt = {}) {
  const tok = ls.get(GH_KEY, "");
  return fetch(`https://api.github.com/repos/${GH.owner}/${GH.repo}${path}`, { ...opt,
    headers: { "Accept": "application/vnd.github+json", "Authorization": "Bearer " + tok, "X-GitHub-Api-Version": "2022-11-28", ...(opt.headers || {}) } });
}
function rfRender(msg) {
  const box = $("rf-pop"), tok = ls.get(GH_KEY, "");
  box.innerHTML = `<div class="rf-head"><b>Perbarui data</b><button type="button" class="icon-btn dw-small" id="rf-x" aria-label="Tutup">✕</button></div>
    <p class="muted" style="margin:0 0 10px;font-size:0.84rem">Data saat ini: <b>${esc(GEN)} WIB</b>. Update butuh sekitar 5–8 menit, lalu halaman akan memberi tahu kalau data baru sudah tersedia.</p>
    ${msg ? `<div class="rf-msg">${msg}</div>` : ""}
    ${tok ? `<button type="button" class="rf-go" id="rf-run" ${rfPoll ? "disabled" : ""}>⟳ Jalankan update sekarang</button>
        <p class="muted" style="font-size:0.76rem;margin:8px 0 0">Terhubung ke GitHub (${esc(GH.owner)}/${esc(GH.repo)}). <button type="button" class="link-btn" id="rf-forget">Lupakan token</button></p>`
      : `<a class="rf-go" href="${GH_ACTIONS}" target="_blank" rel="noopener">Buka GitHub → klik "Run workflow"</a>
        <details class="rf-setup"><summary>Atau hubungkan sekali supaya update jalan langsung dari sini</summary>
          <ol>
            <li>Di GitHub: foto profil → <b>Settings</b> → <b>Developer settings</b> → <b>Personal access tokens</b> → <b>Fine-grained tokens</b> → <b>Generate new token</b>.</li>
            <li>Isi nama (misal <i>tombol perbarui</i>), pilih masa berlaku. <b>Repository access</b>: <i>Only select repositories</i> → <b>${esc(GH.repo)}</b>.</li>
            <li><b>Permissions → Repository permissions → Actions</b>: <b>Read and write</b>. Yang lain biarkan.</li>
            <li>Klik <b>Generate token</b>, salin, lalu tempel di bawah ini.</li>
          </ol>
          <div class="rf-row"><input type="password" id="rf-tok" placeholder="github_pat_..." autocomplete="off"><button type="button" class="icon-btn" id="rf-save">Simpan</button></div>
          <p class="muted" style="font-size:0.74rem;margin:6px 0 0">Token hanya disimpan di browser ini (tidak dikirim ke mana pun selain GitHub). Izinnya hanya untuk menjalankan workflow di repo ${esc(GH.repo)}. Jangan bagikan token ke siapa pun.</p>
        </details>`}`;
  $("rf-x").addEventListener("click", () => { $("rf-pop").hidden = true; });
  const run = $("rf-run"); if (run) run.addEventListener("click", rfRun);
  const fg = $("rf-forget"); if (fg) fg.addEventListener("click", () => { ls.set(GH_KEY, ""); rfRender(); });
  const sv = $("rf-save"); if (sv) sv.addEventListener("click", () => {
    const v = $("rf-tok").value.trim(); if (!v) return;
    ls.set(GH_KEY, v); rfRender("Mengecek token…");
    ghApi("/actions/workflows/screener.yml").then(r => rfRender(r.ok ? "✓ Terhubung. Sekarang klik <b>Jalankan update sekarang</b>." : `✗ Token ditolak GitHub (kode ${r.status}). Cek lagi izin <b>Actions: Read and write</b> dan repo yang dipilih.`))
      .catch(() => rfRender("✗ Tidak bisa menghubungi GitHub. Cek koneksi internet."));
  });
}
function rfStatus(text, busy) { const b = $("rf-btn"); b.classList.toggle("busy", !!busy); b.title = text; const l = b.querySelector(".rf-lab"); if (l) l.textContent = busy ? text : "Perbarui"; }
function rfRun() {
  rfRender("Mengirim perintah ke GitHub…");
  ghApi("/actions/workflows/screener.yml/dispatches", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ ref: "main" }) })
    .then(r => {
      if (r.status !== 204) { rfRender(`✗ GitHub menolak (kode ${r.status}). ${r.status === 401 || r.status === 403 || r.status === 404 ? "Token mungkin kedaluwarsa atau izinnya kurang. Klik \"Lupakan token\" lalu hubungkan lagi." : "Coba lagi beberapa saat."}`); return; }
      rfStart = Date.now(); rfRender("✓ Update dimulai. Status tampil di tombol <b>⟳</b> di atas; kamu boleh menutup kotak ini.");
      rfStatus("Antre…", true);
      clearInterval(rfPoll); rfPoll = setInterval(rfCheck, 15000); setTimeout(rfCheck, 4000);
    }).catch(() => rfRender("✗ Tidak bisa menghubungi GitHub. Cek koneksi internet."));
}
function rfCheck() {
  ghApi("/actions/runs?per_page=5&event=workflow_dispatch").then(r => r.ok ? r.json() : null).then(j => {
    const run = j && (j.workflow_runs || []).find(x => Date.parse(x.created_at) >= rfStart - 60000);
    const mm = Math.floor((Date.now() - rfStart) / 60000), ss = String(Math.floor((Date.now() - rfStart) / 1000) % 60).padStart(2, "0");
    if (!run) { rfStatus(`Antre… ${mm}:${ss}`, true); return; }
    if (run.status !== "completed") { rfStatus(`${run.status === "queued" ? "Antre" : "Berjalan"}… ${mm}:${ss}`, true); return; }
    clearInterval(rfPoll); rfPoll = null; rfStatus("Perbarui", false);
    if (run.conclusion === "success") { rfRender("✓ Update selesai. Halaman baru biasanya tayang dalam 1–2 menit; tunggu pemberitahuan <b>Data baru tersedia</b>."); setTimeout(checkUpdate, 30000); setTimeout(checkUpdate, 90000); }
    else rfRender(`✗ Update gagal (${esc(run.conclusion || "")}). <a href="${run.html_url}" target="_blank" rel="noopener">Lihat detail di GitHub</a>.`);
    if ($("rf-pop").hidden) $("rf-pop").hidden = false;
  }).catch(() => {});
}
$("rf-btn").addEventListener("click", () => { const p = $("rf-pop"); if (p.hidden) { rfRender(); p.hidden = false; } else p.hidden = true; });
if (location.protocol === "file:") $("rf-btn").hidden = true;

/* ---------- new data check (no auto reload) ---------- */
function checkUpdate() {
  if (location.protocol === "file:") return;
  fetch(location.pathname + "?t=" + Date.now(), { cache: "no-store" }).then(r => r.ok ? r.text() : "").then(txt => {
    const m = txt.match(/const GEN = "([^"]+)"/);
    if (m && m[1] !== GEN && !m[1].startsWith("__")) { $("update-text").textContent = `Data baru (${m[1]} WIB) sudah tersedia. Filter dan watchlist-mu tetap tersimpan.`; $("update-bar").style.display = "flex"; }
  }).catch(() => {});
}
$("update-btn").addEventListener("click", () => location.reload());
if (location.protocol === "file:") {
  let last = Date.now(); ["click", "keydown", "scroll", "input"].forEach(ev => window.addEventListener(ev, () => last = Date.now(), { passive: true }));
  setInterval(() => { if (!openT && Date.now() - last > 120000) location.reload(); }, 300000);
} else setInterval(checkUpdate, 300000);

(() => {
  const cnt = {}; DATA.forEach(r => { const k = r.sector && r.sector !== "-" ? r.sector : "-"; cnt[k] = (cnt[k] || 0) + 1; });
  $("sector-filter").innerHTML = '<option value="">Semua sektor</option>' + Object.keys(cnt).filter(k => k !== "-").sort()
    .map(k => `<option value="${esc(k)}">${esc(k)} (${cnt[k]})</option>`).join("") + (cnt["-"] ? `<option value="-">Tanpa sektor (${cnt["-"]})</option>` : "");
})();
/* ---------- daftar teratas: tekanan beli/jual (money flow), akumulasi, nilai, naik/turun ---------- */
const MV = [
  ["nilai", "Nilai transaksi", r => r.vday || null, v => fmtValue(v)],
  ["naik", "Naik tertinggi", r => r.chg > 0 ? r.chg : null, v => `+${fmtDec(v, 2)}%`],
  ["turun", "Turun terdalam", r => r.chg < 0 ? -r.chg : null, v => `−${fmtDec(v, 2)}%`],
];
let mvTab = ls.get("idxs:mv", "nilai");
function renderMovers() {
  const box = $("movers"); if (!box) return;
  const cfg = MV.find(x => x[0] === mvTab) || MV[0], [key, name, get, fmt] = cfg;
  const rows = DATA.filter(r => r.val >= 1e9 && !r.notx).map(r => ({ r, v: get(r) })).filter(x => x.v != null).sort((a, b) => b.v - a.v).slice(0, 10);
  const vmax = rows.length ? rows[0].v : 1;
  const NOTE = {
    nilai: "Nilai transaksi hari ini (volume × harga tutup). Saat sesi berjalan, angkanya masih bertambah.",
    naik: "Kenaikan harga terbesar hari ini.", turun: "Penurunan harga terbesar hari ini.",
  };

  box.innerHTML = `<div class="seg mv-tabs" role="tablist">${MV.map(([k, n]) => `<button type="button" data-mv="${k}" class="${k === key ? "on" : ""}">${n}</button>`).join("")}</div>
    <div class="table-wrap" style="max-height:none;margin-top:8px"><table class="j-tbl mv-tbl"><thead><tr><th>#</th><th>Saham</th><th>Chart 30 hari</th><th class="num">Harga</th><th class="num">Chg%</th><th class="num">${esc(name)}</th><th>Kondisi</th></tr></thead>
    <tbody>${rows.length ? rows.map((x, i) => `<tr data-go="${x.r.t}" tabindex="0"><td class="muted">${i + 1}</td><td><b>${x.r.t}</b>${x.r.top ? ` <span class="top-badge">#${x.r.top}</span>` : ""}<div class="muted" style="font-size:0.72rem">${esc(x.r.nm)}</div></td>
      <td class="mv-chart spark-cell" data-sp="${x.r.t}">${candleSvg(x.r.ohlc || (x.r.smc ? x.r.smc.b.slice(-30) : []))}</td>
      <td class="num">${fmtNum(x.r.p)}</td><td class="num ${x.r.chg >= 0 ? "pos" : "neg"}">${x.r.chg >= 0 ? "+" : ""}${fmtDec(x.r.chg, 2)}%</td>
      <td class="num"><span class="mv-bar ${key === "turun" ? "neg" : "pos"}"><i style="width:${Math.max(4, Math.round(x.v / vmax * 100))}%"></i></span>${fmt(x.v, x.r)}</td>
      <td>${x.r.kd ? `<span class="kd ${x.r.kd.c}">${esc(x.r.kd.l)}</span>` : "-"}</td></tr>`).join("") : `<tr><td colspan="7" class="muted">Tidak ada data.</td></tr>`}</tbody></table></div>
    <p class="muted" style="font-size:0.78rem;margin:6px 0 0">${esc(NOTE[key])} Hanya saham dengan transaksi ≥ Rp 1 M/hari. Semua angka dari data harga dan volume Yahoo Finance.</p>`;
  box.querySelectorAll("[data-mv]").forEach(b => b.addEventListener("click", () => { mvTab = b.dataset.mv; ls.set("idxs:mv", mvTab); renderMovers(); }));
  box.querySelectorAll("tr[data-go]").forEach(tr => { const go = e => { if (e && e.target && e.target.closest && e.target.closest(".spark-cell")) return; openDrawer(tr.dataset.go); }; tr.addEventListener("click", go); tr.addEventListener("keydown", e => { if (e.key === "Enter") go(); }); });
}

/* ---------- halaman (tab): screener, kalender, jurnal, panduan ---------- */
const VIEWS = ["screener", "kalender", "jurnal", "panduan"];
function viewFromHash() { const h = location.hash.replace("#", ""); return VIEWS.includes(h) ? h : "screener"; }
function showView(v) {
  VIEWS.forEach(k => { $("v-" + k).hidden = k !== v; });
  document.querySelectorAll(".tab-btn").forEach(b => { b.classList.toggle("on", b.dataset.view === v); b.setAttribute("aria-current", b.dataset.view === v ? "page" : "false"); });
  $("cmp-bar").style.visibility = v === "screener" ? "" : "hidden";
}
document.querySelectorAll(".tab-btn").forEach(b => b.addEventListener("click", () => {
  const v = b.dataset.view, h = v === "screener" ? location.pathname + location.search : "#" + v;
  if (viewFromHash() !== v || location.hash.startsWith("#s=") || location.hash.startsWith("#bandingkan=")) history.pushState({ v }, "", h);
  showView(v); window.scrollTo(0, 0);
}));
window.addEventListener("popstate", () => { if (!location.hash.startsWith("#s=") && !location.hash.startsWith("#bandingkan=")) showView(viewFromHash()); });
showView(viewFromHash());
PAGE_SIZE = +ls.get("idxs:pgsize", 25) || 25; $("page-size").value = String(PAGE_SIZE);
$("page-size").addEventListener("change", () => { PAGE_SIZE = +$("page-size").value; ls.set("idxs:pgsize", PAGE_SIZE); page = 0; save(); render(); });
/* ---------- tombol kembali ke atas ---------- */
(() => {
  const btn = $("to-top"), cur = () => $("cmpv").classList.contains("open") ? $("cmpv") : $("full").classList.contains("open") ? $("full") : null;
  const pos = () => { const c = cur(); return c ? c.scrollTop : (window.scrollY || document.documentElement.scrollTop); };
  const upd = () => btn.classList.toggle("show", pos() > 700);
  window.addEventListener("scroll", upd, { passive: true }); $("full").addEventListener("scroll", upd, { passive: true }); $("cmpv").addEventListener("scroll", upd, { passive: true });
  new MutationObserver(upd).observe($("full"), { attributes: true, attributeFilter: ["class"] });
  new MutationObserver(upd).observe($("cmpv"), { attributes: true, attributeFilter: ["class"] });
  btn.addEventListener("click", () => { const c = cur(); const opt = { top: 0, behavior: window.matchMedia && matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" };
    if (c) c.scrollTo ? c.scrollTo(opt) : (c.scrollTop = 0); else window.scrollTo ? window.scrollTo(opt) : (document.documentElement.scrollTop = 0); });
})();
$("f-pin").checked = ls.get(PIN_KEY, true);
renderSigOptions(); $("sig-filter").value = ls.get("idxs:sig", "");
$("sig-filter").addEventListener("change", () => { ls.set("idxs:sig", $("sig-filter").value); page = 0; render(); });
renderPref();
$("f-pin").addEventListener("change", () => { ls.set(PIN_KEY, $("f-pin").checked); page = 0; render(); });
renderMarket(); load(); render(); renderCal(); renderJournal(); renderMakro(); renderMovers();
(() => { const d = $("movers-d"); d.open = ls.get("idxs:mvopen", true); d.addEventListener("toggle", () => ls.set("idxs:mvopen", d.open)); })();
renderCmpBar();
(() => { const f = $("filt"); f.open = !!ls.get("idxs:filt", false); f.addEventListener("toggle", () => ls.set("idxs:filt", f.open)); })();
(() => {
  const mc = location.hash.match(/^#bandingkan=([A-Z0-9,]+)$/);
  if (mc) { const l = mc[1].split(",").filter(t => DATA.some(r => r.t === t)).slice(0, CMP_MAX); if (l.length >= 2) { cmp = l; saveCmp(); openCompare(true); return; } }
  const m = location.hash.match(/^#s=([A-Z0-9]+)$/); if (m && DATA.some(r => r.t === m[1])) openDetail(m[1], "full", { fromPop: true });
})();
</script>
</body>
</html>
'''


if __name__ == "__main__":
    main()
