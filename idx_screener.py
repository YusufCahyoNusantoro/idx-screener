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

W_DEFAULT = {"trend": 30, "brk": 30, "pa": 25, "mom": 15}   # sama dengan bobot awal di HTML

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
def unduh(tickers, period, interval, chunk=40):
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


def _unduh(tickers, period, interval, chunk, threads):
    out = {}
    for i in range(0, len(tickers), chunk):
        part = tickers[i:i + chunk]
        syms = [t if t.startswith("^") else t + ".JK" for t in part]
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
        "ohlc": [[round(float(a), 0 if last >= 50 else 2) for a in row] for row in tail[["Open", "High", "Low", "Close"]].values],
        "sector": sektor.get(t, "-"), "beta": beta,
        "tgl": d.index[-1].strftime("%Y-%m-%d"),
        "x": {"m20": [None if not fin(v) else round(float(v), 1) for v in sma(c, 20).iloc[-30:]],
              "m50": [None if not fin(v) else round(float(v), 1) for v in sma(c, 50).iloc[-30:]],
              "ma200": round(float(ma200), 1) if fin(ma200) else None, "hi20": round(hi20, 1),
              "m20l": round(float(ma20), 1) if fin(ma20) else None, "atr": round(atr(d), 2)},
        "_ma20": float(ma20) if fin(ma20) else None, "_atr": atr(d), "_ph": ph, "_d": d,
    }


def konteks_pasar(ihsg, rows, ihsg_jam=None):
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
    likuid = [r for r in rows if r["val"] >= 1e9 and r["x"].get("m20l")]
    if likuid:
        naik = sum(1 for r in likuid if r["p"] > r["x"]["m20l"])
        m["breadth"] = {"pct": round(naik / len(likuid) * 100), "n": len(likuid)}
    return m


def smc(d, L=5, win=120, ctx=260):
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

    # volume profile 120 candle terakhir: volume tiap candle dibagi rata ke rentang high-low-nya
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
    return {
        "b": [[rp(v) for v in row] for row in d[["Open", "High", "Low", "Close"]].iloc[-win:].values],
        "v": ([int(round(x / 100)) if np.isfinite(x) else 0 for x in d["Volume"].iloc[-win:].to_numpy(float)]
              if "Volume" in d else None),        # volume harian dalam lot
        "d0": tgl[s0], "d1": tgl[-1],
        "do": [(x - d.index[s0]).days for x in d.index[s0:]],
        "ev": ev_out, "ob": ob_out, "fvg": fvg_out, "eq": eq_out,
        "pd": [rp(h[s0:].max()), rp(l[s0:].min())], "tr": tren, "vp": vp,
    }


def struktur_ringkas(d, L=3):
    """Arah struktur (1 naik, -1 turun, 0 belum jelas) + kejadian BOS/CHoCH terakhir untuk satu timeframe."""
    if d is None or len(d) < 40:
        return None
    sm = smc(d, L=L, win=min(120, len(d)), ctx=min(260, len(d)))
    if not sm:
        return None
    e = sm["ev"][-1] if sm["ev"] else None
    return {"tr": sm["tr"], "ev": [e[3], e[4], e[5]] if e else None}


def tambah_intraday(r, jam):
    if jam is not None and len(jam) >= 20:
        j4 = gabung_jam(jam, 4)
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
    """Label kondisi + alasan singkat. c: ok / wait / hot / rev / n / bad."""
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
    return (r["trend"] * w["trend"] + r["brk"] * w["brk"] + r["pa"] * w["pa"] + r["mom"] * w["mom"]) / tot


def update_konsistensi(rows, tanggal):
    riw = {}
    if RIWAYAT.exists():
        try:
            riw = json.loads(RIWAYAT.read_text(encoding="utf-8"))
        except Exception:
            riw = {}
    top = sorted([r for r in rows if r["val"] >= 5e9], key=skor, reverse=True)[:10]
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
            + (" Kolom 1H/2H/4H dihitung untuk 200 saham skor tertinggi (yang lain tampil -)." if pakai_intraday
               else " Kolom 1H/2H/4H dimatikan (--no-intraday).")
            + " Halaman akan memberi tahu kalau ada data baru.<br><br>⚠️ Bukan rekomendasi/nasihat keuangan. "
              "Alat bantu penyaringan teknikal saja — tetap lakukan riset &amp; manajemen risiko "
              "sendiri sebelum trading.")
    html = (TEMPLATE
            .replace("__DATA__", json.dumps(bersih(rows), ensure_ascii=False, allow_nan=False))
            .replace("__TITLE__", f"{now:%Y-%m-%d %H:%M}")
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
    ihsg = unduh(["^JKSE"], "2y", "1d").get("^JKSE")
    ihsg_jam = None if args.no_intraday else unduh(["^JKSE"], "60d", "60m").get("^JKSE")
    ihsg_ret = ke_tanggal(ihsg)["Close"].pct_change() if ihsg is not None else None

    sektor = ({t: sektor_daftar.get(t, "-") for t in harian} if args.no_sektor
              else ambil_sektor(list(harian), sektor_daftar))

    hari_ini = now.date()
    rows, gagal = [], [t for t in tickers if t not in harian]
    print(f"  Menghitung indikator {len(harian)} saham...")
    for t, d in harian.items():
        if (pd.Timestamp(hari_ini) - d.index[-1]).days > 10:   # suspend / tidak aktif
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
        calon = [r["t"] for r in sorted(rows, key=skor, reverse=True) if r["val"] >= 5e8][:args.intraday_top]
        print(f"  Unduh data 1 jam (60 hari) untuk {len(calon)} saham skor tertinggi...")
        jam = unduh(calon, "60d", "60m")
        per_t = {r["t"]: r for r in rows}
        for t, df in jam.items():
            try:
                tambah_intraday(per_t[t], df)
            except Exception as e:
                print(f"  ! intraday {t}: {e}")

    for r in rows:
        c, l, why = kondisi(r)
        r["kd"] = {"c": c, "l": l, "why": why}
        r["plan"] = rencana(r, c)
        if True:                                # SMC untuk semua saham yang datanya cukup
            try:
                sm = smc(r["_d"])
                if sm:
                    r["smc"] = sm
                    e = sm["ev"][-1] if sm["ev"] else None
                    r.setdefault("ms", {})["d"] = {"tr": sm["tr"], "ev": [e[3], e[4], e[5]] if e else None}
                sw = struktur_ringkas(resample(r["_d"], "W-FRI"), L=3)
                if sw:
                    r.setdefault("ms", {})["w"] = sw
                    r.pop("ohlc", None)            # 30 candle terakhir diambil dari smc["b"] di browser
                    r["x"].pop("m20", None)
                    r["x"].pop("m50", None)
            except Exception as e:
                print(f"  ! smc {r['t']}: {e}")
        for k in ("_ma20", "_atr", "_ph", "_d"):
            r.pop(k, None)

    tgl_bursa = max(r["tgl"] for r in rows)       # tanggal candle terakhir, bukan tanggal run (akhir pekan tidak dihitung)
    update_konsistensi(rows, tgl_bursa)
    out_html = Path(args.output).resolve()
    pasar = konteks_pasar(ke_tanggal(ihsg) if ihsg is not None else None, rows, ihsg_jam)
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
<title>IDX Screener - __TITLE__</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>
  :root {
    --bg:#F5F6F3; --panel:#FFFFFF; --panel2:#F0F2F5; --ink:#14213D; --ink2:#34405A; --muted:#667085;
    --line:#E1E4E8; --accent:#2E3A87; --accent-soft:#E8EAF7; --up:#0E9F6E; --up-soft:#E3F6EE;
    --down:#D64545; --down-soft:#FBE9E9; --amber:#9A6212; --amber-soft:#FBF1DE; --orange:#B8430E;
    --orange-soft:#FDEBDD; --blue:#2952C9; --blue-soft:#E4ECFD; --row-hover:#F7F8FB;
    --shadow:0 1px 2px rgba(20,33,61,.06); --top-bg:#FFF6DB; --top-hover:#FFEFC2; --top-line:#E2A400; --top-ink:#7A5600;
    box-sizing:border-box;
    padding-top:env(safe-area-inset-top,0px); padding-bottom:env(safe-area-inset-bottom,0px);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg:#0F1522; --panel:#161E2E; --panel2:#1C2638; --ink:#E6E9EF; --ink2:#C3C9D6; --muted:#8E98AD;
      --line:#263041; --accent:#9AA8FF; --accent-soft:#232C4D; --up:#34C38F; --up-soft:#15302A;
      --down:#F07171; --down-soft:#3A1E24; --amber:#E7B45A; --amber-soft:#35291A; --orange:#F29A63;
      --orange-soft:#3A2419; --blue:#8AB0FF; --blue-soft:#1C2A48; --row-hover:#1A2335; --shadow:none; --top-bg:#2B2614; --top-hover:#352E17; --top-line:#F2C94C; --top-ink:#F2C94C;
    }
  }
  :root[data-theme="dark"] {
    --bg:#0F1522; --panel:#161E2E; --panel2:#1C2638; --ink:#E6E9EF; --ink2:#C3C9D6; --muted:#8E98AD;
    --line:#263041; --accent:#9AA8FF; --accent-soft:#232C4D; --up:#34C38F; --up-soft:#15302A;
    --down:#F07171; --down-soft:#3A1E24; --amber:#E7B45A; --amber-soft:#35291A; --orange:#F29A63;
    --orange-soft:#3A2419; --blue:#8AB0FF; --blue-soft:#1C2A48; --row-hover:#1A2335; --shadow:none; --top-bg:#2B2614; --top-hover:#352E17; --top-line:#F2C94C; --top-ink:#F2C94C;
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
  .wrap { max-width:1500px; margin:0 auto; padding:20px clamp(12px,3vw,28px) 48px; }

  /* header */
  .top { display:flex; align-items:flex-start; justify-content:space-between; gap:16px; flex-wrap:wrap; margin-bottom:14px; }
  .brand h1 { font-size:1.55rem; font-weight:800; letter-spacing:-0.02em; margin:0; }
  .brand .meta { color:var(--muted); font-size:0.86rem; margin-top:2px; }
  .status { display:inline-block; margin-left:8px; vertical-align:4px; font-size:0.72rem; font-weight:700;
    padding:3px 10px; border-radius:999px; background:var(--up-soft); color:var(--up); letter-spacing:0; }
  .top-actions { display:flex; gap:8px; align-items:center; }
  .icon-btn { border:1px solid var(--line); background:var(--panel); border-radius:10px; padding:7px 12px;
    cursor:pointer; font-size:0.85rem; font-weight:600; color:var(--ink2); }
  .icon-btn:hover { border-color:var(--accent); color:var(--accent); }
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
  #filter-card.dim { opacity:.45; }
  .preset-desc { font-size:0.84rem; color:var(--muted); margin:10px 2px 0; min-height:1.3em; }
  .filters { display:grid; grid-template-columns:repeat(auto-fit,minmax(180px,1fr)); gap:12px 18px; }
  .f label { display:block; font-size:0.8rem; color:var(--muted); font-weight:600; margin-bottom:4px; }
  .f input, .f select { width:100%; padding:8px 10px; border:1px solid var(--line); border-radius:9px; background:var(--panel); font-size:0.88rem; }
  .pair { display:flex; gap:6px; align-items:center; }
  .chips { display:flex; flex-wrap:wrap; gap:8px 18px; align-items:center; margin-top:14px; padding-top:12px; border-top:1px solid var(--line); }
  .chip { display:flex; align-items:center; gap:6px; font-size:0.86rem; color:var(--ink2); cursor:pointer; }
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
  .table-wrap { overflow:auto; max-height:78vh; border:1px solid var(--line); border-radius:14px; background:var(--panel); box-shadow:var(--shadow); }
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
  .j-form input, .j-form select { width:100%; padding:7px 9px; border:1px solid var(--line); border-radius:8px; background:var(--panel); }
  .j-tbl { width:100%; border-collapse:collapse; font-size:0.84rem; }
  .j-tbl th { text-align:left; color:var(--muted); font-size:0.76rem; padding:8px 10px; border-bottom:1px solid var(--line); background:var(--panel2); position:static; }
  .j-tbl td { padding:8px 10px; border-bottom:1px solid var(--line); vertical-align:top; background:var(--panel); }
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

  /* kalender */
  .cal-head { display:flex; flex-wrap:wrap; align-items:center; gap:10px 18px; margin-bottom:12px; }
  .cal-head h2 { margin:0; }
  .cal-nav { display:flex; align-items:center; gap:8px; }
  .cal-title { font-weight:800; font-size:1.05rem; min-width:150px; text-align:center; }
  .cal-opts { display:flex; gap:14px; margin-left:auto; }
  .cal-grid { display:grid; grid-template-columns:repeat(7,minmax(0,1fr)); gap:6px; }
  .cal-dow { font-size:0.78rem; font-weight:700; color:var(--muted); text-align:center; padding:2px 0 4px; }
  .cal-cell { min-height:92px; border:1px solid var(--line); border-radius:12px; background:var(--panel); padding:6px 7px; text-align:left;
    display:flex; flex-direction:column; gap:3px; cursor:pointer; overflow:hidden; }
  .cal-cell:hover { border-color:var(--accent); }
  .cal-cell.empty { border:0; background:transparent; cursor:default; }
  .cal-cell.weekend { background:var(--panel2); }
  .cal-cell.today { border:2px solid var(--accent); }
  .cal-cell.sel { box-shadow:0 0 0 3px var(--accent-soft); border-color:var(--accent); }
  .cal-d { font-weight:700; font-size:0.86rem; }
  .cal-moon { font-size:1.15rem; line-height:1.1; }
  .cal-moon small { font-size:0.68rem; color:var(--muted); margin-left:4px; vertical-align:3px; font-weight:600; }
  .cal-ev { display:inline-block; font-size:0.68rem; font-weight:700; padding:1px 7px; border-radius:999px; white-space:nowrap; }
  .ev-msci { background:var(--blue-soft); color:var(--blue); }
  .ev-ftse { background:var(--accent-soft); color:var(--accent); }
  .ev-gdx { background:var(--amber-soft); color:var(--amber); }
  .ev-lapkeu { background:var(--orange-soft); color:var(--orange); }
  .ev-lain { background:var(--panel2); color:var(--ink2); }
  .cal-list { list-style:none; margin:14px 0 0; padding:0; }
  .cal-list li { display:flex; gap:14px; padding:9px 0; border-top:1px solid var(--line); font-size:0.88rem; }
  .cl-date { flex:0 0 104px; font-weight:700; color:var(--ink2); white-space:nowrap; }
  .tk-chip { border:1px solid var(--line); background:var(--panel2); border-radius:999px; padding:2px 9px; margin:5px 5px 0 0; font-size:0.76rem; font-weight:700; cursor:pointer; }
  .tk-chip:hover { border-color:var(--accent); color:var(--accent); }
  @media (max-width:700px) { .cal-cell { min-height:64px; } .cal-moon small, .cal-ev { display:none; } .cal-ev + .cal-ev { display:none; } }

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
<div class="wrap">
  <header class="top">
    <div class="brand">
      <h1>IDX Screener <span class="status" id="status-chip">__BADGE__</span></h1>
      <div class="meta">__SUB__</div>
    </div>
    <div class="top-actions">
      <button class="icon-btn" id="theme-btn" type="button" aria-label="Ganti tema terang atau gelap">Tema gelap</button>
      <a class="icon-btn" href="#kalender" style="text-decoration:none">Kalender</a>
      <a class="icon-btn" href="#jurnal" style="text-decoration:none">Jurnal</a>
      <a class="icon-btn" href="#panduan" style="text-decoration:none">Panduan</a>
    </div>
  </header>

  <div class="update-bar" id="update-bar" role="status">
    <span id="update-text">Data baru sudah tersedia.</span>
    <button type="button" id="update-btn">Muat data baru</button>
  </div>

  <section class="market" id="market" aria-label="Kondisi pasar"></section>

  <section class="card" aria-label="Preset">
    <h2>Pilih gaya screening</h2>
    <div class="presets" id="presets">
      <button class="preset-btn watch-btn" id="watch-btn" type="button" aria-pressed="false">★ Watchlist saya <b id="watch-count">0</b></button>
      <button class="preset-btn" data-preset="struct">Struktur searah naik</button>
      <button class="preset-btn" data-preset="golden">Tren naik rapi</button>
      <button class="preset-btn" data-preset="quality">Likuid &amp; konsisten</button>
      <button class="preset-btn" data-preset="breakout">Breakout</button>
      <button class="preset-btn" data-preset="allgreen">Kuat di semua timeframe</button>
      <button class="preset-btn" data-preset="reversal">Pantulan dari bawah</button>
      <button class="preset-btn" data-preset="pattern">Ada pola candle</button>
      <button class="preset-btn" data-preset="reset">Tampilkan semua</button>
    </div>
    <p class="preset-desc" id="preset-desc"></p>
  </section>

  <section class="card" aria-label="Filter" id="filter-card">
    <div class="filters">
      <div class="f"><label for="search">Cari kode atau nama</label><input type="text" id="search" placeholder="mis. BBCA atau Astra"></div>
      <div class="f"><label for="kd-filter">Kondisi</label>
        <select id="kd-filter">
          <option value="">Semua kondisi</option>
          <option value="nobad">Kecuali Hindari dulu</option>
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
        <div><label for="w-trend">Trend <b id="w-trend-val">30</b></label><input type="range" id="w-trend" min="0" max="100" value="30"></div>
        <div><label for="w-brk">Breakout <b id="w-brk-val">30</b></label><input type="range" id="w-brk" min="0" max="100" value="30"></div>
        <div><label for="w-pa">Price action <b id="w-pa-val">25</b></label><input type="range" id="w-pa" min="0" max="100" value="25"></div>
        <div><label for="w-mom">Momentum (RSI) <b id="w-mom-val">15</b></label><input type="range" id="w-mom" min="0" max="100" value="15"></div>
      </div>
    </details>
  </section>

  <div class="count-info" id="count-info" aria-live="polite"></div>
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
          <th data-key="sector">Sektor</th>
          <th class="num" data-key="beta" title="Seberapa liar dibanding IHSG">Beta</th>
          <th class="nosort">1H</th><th class="nosort">2H</th><th class="nosort">4H</th>
          <th class="nosort">Daily</th><th class="nosort">Mingguan</th><th class="nosort">Bulanan</th>
          <th data-key="streak" title="Hari masuk Top 10 (saham transaksi ≥ Rp 5 M) dari 10 hari terakhir">Top 10</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
  <div class="pager">
    <span class="muted" id="page-info" style="font-size:0.84rem"></span>
    <button id="prev-page" type="button">Sebelumnya</button>
    <button id="next-page" type="button">Berikutnya</button>
  </div>

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
      </div>
    </div>
    <div class="cal-grid" id="cal-grid"></div>
    <ul class="cal-list" id="cal-list"></ul>
    <p class="muted" style="font-size:0.78rem;margin:10px 0 0">Waktu fase bulan dalam WIB, dihitung dengan rumus astronomi. Agenda MSCI, FTSE, GDX, dan batas laporan keuangan diambil dari jadwal resmi; tanggal bisa berubah, jadi cek pengumuman terbaru. Klik tanggal untuk melihat detailnya.</p>
  </section>

  <section class="card" id="jurnal" aria-label="Jurnal trading">
    <div class="cal-head"><h2>Jurnal trading</h2>
      <div class="cal-opts"><button class="icon-btn" id="j-export" type="button">Unduh CSV</button></div></div>
    <div class="plan-box j-stats" id="j-stats"></div>
    <div id="j-setups" style="margin-top:12px"></div>
    <div id="j-list" style="margin-top:12px"></div>
    <p class="muted" style="font-size:0.78rem;margin:10px 0 0">Jurnal tersimpan di browser ini saja, tidak ikut ke GitHub atau perangkat lain. Unduh CSV secara berkala sebagai cadangan. R = hasil dibagi risiko awal (entry − stop loss): +2R berarti untung 2 kali risiko.</p>
  </section>

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
        <p>3. Klik baris saham untuk membuka detailnya: chart dengan garis entry, stop loss, dan target, checklist syarat, serta kalkulator lot.</p>
        <p>4. Tandai saham incaran dengan bintang ☆, lalu klik tombol "★ Watchlist saya" untuk melihat semuanya sekaligus, apa pun filternya.</p>
        <p>5. Cocokkan dengan chart di aplikasi trading-mu sebelum entry. Checklist yang banyak terpenuhi menambah keyakinan, tapi tidak menjamin harga naik.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Checklist syarat</summary>
      <div class="guide-body">
        <p>Setiap saham diperiksa terhadap 10 syarat: tren tersusun naik, harga di atas MA200, Daily dan Mingguan Buy, RSI 45–70, volume di atas rata-rata, transaksi ≥ Rp 5 M/hari, 1H tidak Sell, risiko ke stop loss ≤ 7%, IHSG tidak sedang turun, dan struktur SMC Mingguan serta Harian bullish.</p>
        <p>Angka seperti 8/10 berarti 8 dari 10 syarat terpenuhi. Syarat yang datanya tidak ada (misal 1H di luar 200 saham teratas) tidak dihitung. Hijau = minimal 7, kuning = 5–6, merah = di bawah 5.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Smart Money Concepts (SMC) di chart detail</summary>
      <div class="guide-body">
        <p>Panel detail setiap saham menampilkan chart 120 hari dengan lapisan SMC (kecuali saham yang riwayat harganya masih terlalu pendek). Setiap lapisan bisa dinyalakan atau dimatikan.</p>
        <p><b>BOS</b> (garis penuh): harga menembus swing high/low searah tren, tanda tren berlanjut. <b>CHoCH</b> (garis putus-putus): tembusan pertama yang berlawanan arah, tanda awal pembalikan.<br>
        <b>Order block (OB)</b>: candle terakhir yang berlawanan arah sebelum dorongan yang memicu BOS/CHoCH. Hijau = area permintaan, merah = area penawaran. Yang ditampilkan hanya yang belum ditembus.<br>
        <b>FVG</b>: celah antara candle 1 dan 3 yang belum terisi; harga sering kembali mengisinya.<br>
        <b>EQH/EQL</b>: dua puncak atau dua lembah yang hampir sama tinggi, tempat banyak stop loss berkumpul.<br>
        <b>Premium/discount</b>: separuh atas range 120 hari (relatif mahal) dan separuh bawah (relatif murah), dengan garis EQ di tengah.</p>
        <p>Ini versi sederhana yang dihitung otomatis dari candle harian (swing 5 candle kiri-kanan), jadi bisa berbeda dari indikator SMC di TradingView atau Stockbit. Gunakan sebagai petunjuk area, lalu pastikan di chart aplikasi trading-mu.</p>
      </div>
    </details>
    <details class="guide-item">
      <summary>Kalender: fase bulan dan agenda pasar</summary>
      <div class="guide-body">
        <p>Bagian Kalender (tombol "Kalender" di kanan atas) menampilkan fase bulan (🌑 bulan baru, 🌓 kuartal awal, 🌕 purnama, 🌗 kuartal akhir) dalam WIB, serta agenda pasar: review MSCI, FTSE, GDX, dan batas penyampaian laporan keuangan. Klik tanggal untuk melihat detailnya; klik kode saham di agenda untuk membuka panel detailnya.</p>
        <p>Fase bulan juga bisa ditampilkan di chart SMC sebagai lingkaran kecil di bawah candle (kuning = purnama, gelap = bulan baru). Penelitian menemukan return rata-rata pasar global sedikit lebih rendah di sekitar purnama dibanding bulan baru, tapi efeknya kecil dan tidak membuktikan fase bulan bisa menentukan titik pembalikan saham tertentu. Pakai sebagai konteks, bukan sinyal utama.</p>
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
        <p><b>Baris berwarna kuning</b> dengan label #1 sampai #10 adalah 10 saham dengan skor tertinggi hari ini (bobot standar 30/30/25/15, hanya saham dengan transaksi minimal Rp 5 M/hari). Centang "Hanya Top 10 hari ini" untuk menampilkan kesepuluhnya saja. Kolom Top 10 menghitung berapa hari bursa (dari 10 terakhir) saham itu masuk daftar ini.</p>
        <p><b>Riwayat harian</b> di panel detail menampilkan harga buka, tertinggi, terendah, tutup, perubahan, volume (lot), perkiraan nilai transaksi, dan perbandingan volume dengan rata-rata 20 hari sebelumnya. Baris kuning menandai hari dengan volume minimal 2 kali rata-rata. Riwayat bisa diunduh sebagai CSV.</p>
        <p>Data broker summary (broker pembeli dan penjual) tidak tersedia gratis untuk diambil otomatis, jadi tombol di bawah riwayat membuka halaman saham itu di Stockbit untuk dicek manual.</p>
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
        <p><b>Kandidat kuat</b> (hijau): tren harian dan mingguan naik, RSI 45–70, transaksi minimal Rp 5 M/hari, dan jangka pendek tidak sedang koreksi.<br>
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

<div class="scrim" id="scrim"></div>
<aside class="drawer" id="drawer" role="dialog" aria-modal="true" aria-labelledby="d-title" tabindex="-1"></aside>

<script>
const DATA = __DATA__;
const MARKET = __MARKET__;
const GEN = "__GEN__";
const PAGE_SIZE = 25;
const KD_ORDER = { ok: 0, rev: 1, wait: 2, hot: 3, n: 4, bad: 5 };
const KD_NAME = { ok: "Kandidat kuat", wait: "Tunggu", hot: "Tunggu pullback", rev: "Pantau pembalikan", n: "Pantau", bad: "Hindari dulu" };
const PRESETS = {
  struct:   { weights:{trend:30,brk:30,pa:25,mom:15}, minScore:0, filters:{ms:true}, valMin:5, kd:"nobad",
              desc:"Struktur SMC Mingguan, Harian, dan 4 jam (kalau ada) sama-sama bullish, transaksi minimal Rp 5 M/hari. Cari entry saat harga kembali ke order block bullish atau zona discount, lalu konfirmasi di 1 jam." },
  golden:   { weights:{trend:60,brk:10,pa:10,mom:20}, minScore:55, filters:{trend:true}, kd:"nobad",
              desc:"Saham dengan susunan MA20 > MA50 > MA200 dan harga di atas MA20. Cocok untuk ikut tren yang sudah terbentuk." },
  quality:  { weights:{trend:30,brk:30,pa:25,mom:15}, minScore:40, filters:{}, valMin:5, streakMin:3,
              desc:"Transaksi minimal Rp 5 M/hari dan masuk Top 10 minimal 3 dari 10 hari terakhir. Paling aman untuk pemula." },
  breakout: { weights:{trend:20,brk:50,pa:20,mom:10}, minScore:50, filters:{breakout:true},
              desc:"Harga menembus harga tertinggi 20 hari dengan volume minimal 1,5 kali rata-rata. Waspada breakout palsu." },
  allgreen: { weights:{trend:25,brk:25,pa:25,mom:25}, minScore:0, filters:{allgreen:true},
              desc:"Daily, Mingguan, dan Bulanan sama-sama Strong Buy. Sering sudah mahal, perhatikan RSI." },
  reversal: { weights:{trend:10,brk:10,pa:40,mom:40}, minScore:35, filters:{pattern:true, confirmed:true}, rsiMax:45,
              desc:"RSI rendah dengan pola pembalikan yang sudah terkonfirmasi. Lebih berisiko; penurunan bisa berlanjut." },
  pattern:  { weights:{trend:15,brk:15,pa:55,mom:15}, minScore:40, filters:{pattern:true},
              desc:"Candle terakhir membentuk pola bullish. Pola berlabel \"tunggu\" belum terkonfirmasi." },
  reset:    { weights:{trend:30,brk:30,pa:25,mom:15}, minScore:40, filters:{},
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
  ["ok", "wait", "hot", "rev", "n", "bad"].forEach(k => { if (cnt[k]) kc += `<button class="kd-count" data-kd="${k}" type="button">${KD_NAME[k]}<b>${cnt[k]}</b></button>`; });
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
  return `<div class="plan">Entry <b>${fmtNum(p.e1)}–${fmtNum(p.e2)}</b><br><span class="sl">SL ${fmtNum(p.sl)}</span> · <span class="tp">TP ${fmtNum(p.tp)}</span></div>`;
}

/* ---------- state ---------- */
const FIELDS = ["search", "kd-filter", "sector-filter", "price-min", "price-max", "rsi-min", "rsi-max", "val-min", "streak-min"];
const CHECKS = ["f-watch", "f-trend", "f-breakout", "f-pattern", "f-confirmed", "f-allgreen", "f-ms", "f-top"];
const W = ["w-trend", "w-brk", "w-pa", "w-mom"];
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
  $("w-trend").value = p.weights.trend; $("w-brk").value = p.weights.brk; $("w-pa").value = p.weights.pa; $("w-mom").value = p.weights.mom;
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
function weights() { return { trend: +$("w-trend").value, brk: +$("w-brk").value, pa: +$("w-pa").value, mom: +$("w-mom").value }; }
function score(r, w) { const t = w.trend + w.brk + w.pa + w.mom; return t ? (r.trend * w.trend + r.brk * w.brk + r.pa * w.pa + r.mom * w.mom) / t : 0; }
function allGreen(tf) { return tf && tf.daily && tf.weekly && tf.monthly && [tf.daily, tf.weekly, tf.monthly].every(d => d.summary === "Strong Buy"); }
function num(id) { return parseFloat($(id).value); }

function filtered() {
  const w = weights(), q = $("search").value.trim().toUpperCase(), kd = $("kd-filter").value;
  const pmin = num("price-min"), pmax = num("price-max"), rmin = num("rsi-min"), rmax = num("rsi-max"), vmin = num("val-min"), smin = num("streak-min");
  let rows = DATA.map(r => ({ ...r, score: score(r, w) }));
  if (q) {   // pencarian selalu menemukan saham yang dicari, filter lain diabaikan
    rows = rows.filter(r => r.t.includes(q) || (r.nm || "").toUpperCase().includes(q));
    rows.sort((a, b) => (b.t === q) - (a.t === q) || (b.t.startsWith(q)) - (a.t.startsWith(q)) || b.score - a.score);
    return rows;
  }
  if ($("f-watch").checked) {   // watchlist: tampilkan semua saham bertanda bintang, filter lain diabaikan
    rows = rows.filter(r => watch.has(r.t));
  } else if ($("f-top").checked) {   // Top 10 hari ini: selalu 10 saham, filter lain diabaikan
    rows = rows.filter(r => r.top);
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

function render() {
  const rows = filtered();
  const watchOn = $("f-watch").checked && !$("search").value.trim();
  $("watch-btn").classList.toggle("on", watchOn); $("watch-btn").setAttribute("aria-pressed", watchOn);
  $("watch-count").textContent = watch.size;
  const topOn = !watchOn && $("f-top").checked && !$("search").value.trim();
  $("filter-card").classList.toggle("dim", watchOn || topOn);
  $("count-info").textContent = $("search").value.trim()
    ? `${fmtNum(rows.length)} hasil pencarian. Pencarian mengabaikan filter lain. Hapus isi kotak cari untuk kembali ke filter.`
    : watchOn ? `Watchlist-mu: ${fmtNum(rows.length)} saham. Filter lain diabaikan. Klik preset mana saja untuk kembali.`
    : topOn ? `Top 10 hari ini: ${fmtNum(rows.length)} saham (skor bobot standar, transaksi minimal Rp 5 M/hari). Filter lain diabaikan; hapus centang untuk kembali.`
    : `${fmtNum(rows.length)} saham cocok dari ${fmtNum(DATA.length)}. Klik baris untuk melihat detail.`;
  document.querySelectorAll(".kd-count").forEach(b => b.classList.toggle("on", b.dataset.kd === $("kd-filter").value));
  const pages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  page = Math.min(Math.max(0, page), pages - 1);
  const slice = rows.slice(page * PAGE_SIZE, page * PAGE_SIZE + PAGE_SIZE);
  if (!slice.length) {
    $("tbody").innerHTML = $("search").value.trim()
      ? `<tr><td colspan="22" class="empty">Kode atau nama "${esc($("search").value.trim())}" tidak ada di data run ini. Mungkin saham itu baru IPO, sedang disuspensi, atau datanya gagal diambil dari Yahoo.</td></tr>`
      : watchOn ? `<tr><td colspan="22" class="empty">Watchlist masih kosong. Klik bintang ☆ di samping kode saham untuk menambahkannya.</td></tr>`
      : `<tr><td colspan="22" class="empty">Tidak ada saham yang cocok dengan filter ini.<br><button class="icon-btn" type="button" id="empty-reset">Tampilkan semua saham</button></td></tr>`;
    const er = $("empty-reset"); if (er) er.addEventListener("click", e => { e.stopPropagation(); applyPreset("reset"); });
  } else {
    $("tbody").innerHTML = slice.map(r => `<tr data-t="${r.t}" tabindex="0"${r.top ? ' class="top10"' : ""}>
      <td class="sticky1"><button class="star ${watch.has(r.t) ? "on" : ""}" data-star="${r.t}" type="button" aria-label="Watchlist ${r.t}" aria-pressed="${watch.has(r.t)}">★</button></td>
      <td class="sticky2"><div class="tk">${r.t}${r.top ? `<span class="top-badge" title="Top 10 hari ini: peringkat ${r.top} (skor bobot standar, transaksi minimal Rp 5 M/hari)">#${r.top}</span>` : ""}</div><div class="tk-name" title="${esc(r.nm)}">${esc(r.nm) || "&nbsp;"}</div></td>
      <td>${candleSvg(r.ohlc)}</td>
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
      <td>${r.sector && r.sector !== "-" ? esc(r.sector) : '<span class="muted">-</span>'}</td>
      <td class="num">${r.beta == null ? '<span class="muted">-</span>' : fmtDec(r.beta, 2)}</td>
      <td>${verdictCell("h1", r.tf)}</td><td>${verdictCell("h2", r.tf)}</td><td>${verdictCell("h4", r.tf)}</td>
      <td>${verdictCell("daily", r.tf)}</td><td>${verdictCell("weekly", r.tf)}</td><td>${verdictCell("monthly", r.tf)}</td>
      <td>${r.cst && r.cst.total ? `${r.cst.count}/${r.cst.total}` : '<span class="muted">-</span>'}</td>
    </tr>`).join("");
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
const JENIS = { msci: "MSCI", ftse: "FTSE", gdx: "GDX", lapkeu: "Lapkeu", lain: "Agenda" };
const BULAN_ID = ["Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember"];
const CAL_KEY = "idxs:cal";
const WIB_MS = 7 * 3600000;
const ymd = d => new Date(d.getTime() + WIB_MS).toISOString().slice(0, 10);          // tanggal WIB dari waktu UTC
const hm = d => new Date(d.getTime() + WIB_MS).toISOString().slice(11, 16);
let cal = Object.assign({ moon: true, agenda: true }, ls.get(CAL_KEY, {}));
let calMonth = (() => { const t = new Date(Date.now() + WIB_MS); return [t.getUTCFullYear(), t.getUTCMonth()]; })();
let calSel = null;

function calData(y, m) {
  const from = new Date(Date.UTC(y, m, 1) - WIB_MS - 86400000), to = new Date(Date.UTC(y, m + 1, 1) - WIB_MS + 86400000);
  const moons = {}; moonPhases(from, to).forEach(p => { (moons[ymd(p.t)] = moons[ymd(p.t)] || []).push(p); });
  const ev = {}; AGENDA.forEach(a => { (ev[a.tgl] = ev[a.tgl] || []).push(a); });
  return { moons, ev };
}

function renderCal() {
  const [y, m] = calMonth, { moons, ev } = calData(y, m);
  const today = ymd(new Date()), first = new Date(Date.UTC(y, m, 1)), days = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  const lead = (first.getUTCDay() + 6) % 7;             // Senin = kolom pertama
  $("cal-title").textContent = `${BULAN_ID[m]} ${y}`;
  $("cal-moon").checked = cal.moon; $("cal-agenda").checked = cal.agenda;
  let h = ["Sen", "Sel", "Rab", "Kam", "Jum", "Sab", "Min"].map(d => `<div class="cal-dow">${d}</div>`).join("");
  for (let i = 0; i < lead; i++) h += '<div class="cal-cell empty"></div>';
  for (let d = 1; d <= days; d++) {
    const key = `${y}-${String(m + 1).padStart(2, "0")}-${String(d).padStart(2, "0")}`, wd = (lead + d - 1) % 7;
    const mo = cal.moon ? (moons[key] || []) : [], es = cal.agenda ? (ev[key] || []) : [];
    h += `<button type="button" class="cal-cell${wd >= 5 ? " weekend" : ""}${key === today ? " today" : ""}${key === calSel ? " sel" : ""}" data-day="${key}">
      <span class="cal-d">${d}</span>
      ${mo.map(p => `<span class="cal-moon" title="${MOON_NAME[p.q]} ${hm(p.t)} WIB">${MOON_ICON[p.q]}<small>${p.q === 0 || p.q === 2 ? MOON_NAME[p.q] : ""}</small></span>`).join("")}
      ${es.map(a => `<span class="cal-ev ev-${esc(a.jenis)}" title="${esc(a.judul)}">${esc(JENIS[a.jenis] || JENIS.lain)}</span>`).join("")}
    </button>`;
  }
  $("cal-grid").innerHTML = h;
  $("cal-grid").querySelectorAll("[data-day]").forEach(b => b.addEventListener("click", () => { calSel = calSel === b.dataset.day ? null : b.dataset.day; renderCal(); }));
  // daftar di bawah grid
  const prefix = `${y}-${String(m + 1).padStart(2, "0")}`;
  const items = [];
  if (cal.moon) Object.entries(moons).forEach(([k, arr]) => { if (k.startsWith(prefix)) arr.forEach(p => items.push({ tgl: k, moon: p })); });
  if (cal.agenda) AGENDA.forEach(a => { if (a.tgl.startsWith(prefix)) items.push({ tgl: a.tgl, ev: a }); });
  const list = items.filter(i => !calSel || i.tgl === calSel).sort((a, b) => a.tgl.localeCompare(b.tgl) || (a.moon ? -1 : 1));
  const tglTxt = k => { const [yy, mm, dd] = k.split("-").map(Number); const w = ["Min", "Sen", "Sel", "Rab", "Kam", "Jum", "Sab"][new Date(Date.UTC(yy, mm - 1, dd)).getUTCDay()]; return `${w}, ${dd} ${BULAN_ID[mm - 1].slice(0, 3)}`; };
  $("cal-list").innerHTML = list.length ? list.map(i => i.moon
    ? `<li><span class="cl-date">${tglTxt(i.tgl)}</span><span class="cl-body"><b>${MOON_ICON[i.moon.q]} ${MOON_NAME[i.moon.q]}</b> <span class="muted">${hm(i.moon.t)} WIB</span></span></li>`
    : `<li><span class="cl-date">${tglTxt(i.tgl)}</span><span class="cl-body"><span class="cal-ev ev-${esc(i.ev.jenis)}">${esc(JENIS[i.ev.jenis] || JENIS.lain)}</span> <b>${esc(i.ev.judul)}</b>${i.ev.ket ? `<br><span class="muted">${esc(i.ev.ket)}</span>` : ""}${(i.ev.saham || []).length ? `<br>${i.ev.saham.map(t => `<button type="button" class="tk-chip" data-open="${esc(t)}">${esc(t)}</button>`).join("")}` : ""}</span></li>`).join("")
    : `<li class="muted">${calSel ? "Tidak ada fase bulan atau agenda di tanggal ini." : "Tidak ada agenda bulan ini."}</li>`;
  $("cal-list").querySelectorAll("[data-open]").forEach(b => b.addEventListener("click", () => {
    if (DATA.some(r => r.t === b.dataset.open)) openDrawer(b.dataset.open);
  }));
}
$("cal-prev").addEventListener("click", () => { calMonth = calMonth[1] === 0 ? [calMonth[0] - 1, 11] : [calMonth[0], calMonth[1] - 1]; calSel = null; renderCal(); });
$("cal-next").addEventListener("click", () => { calMonth = calMonth[1] === 11 ? [calMonth[0] + 1, 0] : [calMonth[0], calMonth[1] + 1]; calSel = null; renderCal(); });
$("cal-today").addEventListener("click", () => { const t = new Date(Date.now() + WIB_MS); calMonth = [t.getUTCFullYear(), t.getUTCMonth()]; calSel = null; renderCal(); });
["cal-moon", "cal-agenda"].forEach(id => $(id).addEventListener("change", () => { cal.moon = $("cal-moon").checked; cal.agenda = $("cal-agenda").checked; ls.set(CAL_KEY, cal); renderCal(); }));

/* ---------- SMC chart ---------- */
const SMC_KEY = "idxs:smc";
const SMC_LAYERS = [["vp", "Volume profile"], ["pd", "Premium/discount"], ["st", "Struktur BOS/CHoCH"], ["ob", "Order block"], ["fvg", "FVG"], ["eq", "Likuiditas EQH/EQL"], ["moon", "Fase bulan"], ["ma", "MA20/MA50"], ["plan", "Entry/SL/TP"]];
function smcLayers() { return Object.assign({ vp: true, pd: true, st: true, ob: true, fvg: true, eq: true, moon: true, ma: false, plan: false }, ls.get(SMC_KEY, {})); }

function smcChart(r, lay) {
  const S = r.smc, bars = S.b, nb = bars.length, p = r.plan;
  const W = 720, H = 330, L = 8, R = 88, T = 10, B = 22, iw = W - L - R, ih = H - T - B;
  let max = Math.max(...bars.map(b => b[1])), min = Math.min(...bars.map(b => b[2]));
  if (lay.plan && p) { max = Math.max(max, p.tp); min = Math.min(min, p.sl); }
  const pad = (max - min) * 0.05 || 1; max += pad; min -= pad;
  const sw = iw / nb, bw = Math.max(1.4, sw * 0.62);
  const y = v => T + (max - v) / (max - min) * ih, x = i => L + i * sw + sw / 2, xl = i => L + i * sw;
  const clampY = v => Math.min(T + ih, Math.max(T, y(v)));
  const up = "var(--up)", dn = "var(--down)";
  let s = `<svg class="d-chart" viewBox="0 0 ${W} ${H}" role="img" aria-label="Chart 120 hari dengan Smart Money Concepts ${esc(r.t)}">`;
  s += `<defs><clipPath id="cp"><rect x="${L}" y="${T}" width="${iw}" height="${ih}"/></clipPath></defs><g clip-path="url(#cp)">`;
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
  if (lay.ma) s += path(smaArr(20), "var(--blue)") + path(smaArr(50), "var(--orange)");
  bars.forEach((b, i) => {
    const [op, hi, lo, cl] = b, col = cl >= op ? up : dn, top = Math.min(y(op), y(cl));
    s += `<line x1="${x(i).toFixed(1)}" x2="${x(i).toFixed(1)}" y1="${y(hi).toFixed(1)}" y2="${y(lo).toFixed(1)}" stroke="${col}" stroke-width="0.9"/><rect x="${(x(i) - bw / 2).toFixed(1)}" y="${top.toFixed(1)}" width="${bw.toFixed(1)}" height="${Math.max(0.8, Math.abs(y(cl) - y(op))).toFixed(1)}" fill="${col}"/>`;
  });
  if (lay.plan && p) {
    s += `<rect x="${L}" y="${y(p.e2).toFixed(1)}" width="${iw}" height="${Math.max(2, y(p.e1) - y(p.e2)).toFixed(1)}" fill="var(--accent)" opacity="0.12"/>`;
    [[p.tp, up], [p.sl, dn]].forEach(([v, col]) => s += `<line x1="${L}" x2="${L + iw}" y1="${y(v).toFixed(1)}" y2="${y(v).toFixed(1)}" stroke="${col}" stroke-width="1.3" stroke-dasharray="6 4"/>`);
  }
  if (lay.moon && S.do && S.d0) {
    const base = Date.parse(S.d0 + "T00:00:00Z"), dates = S.do.map(o => new Date(base + o * 86400000).toISOString().slice(0, 10));
    const from = new Date(base - WIB_MS), to = new Date(Date.parse(S.d1 + "T00:00:00Z") + 86400000 - WIB_MS);
    moonPhases(from, to).filter(p => p.q === 0 || p.q === 2).forEach(p => {
      const day = ymd(p.t), i = dates.findIndex(dd => dd >= day); if (i < 0) return;
      const cx = x(i), full = p.q === 2;
      s += `<line x1="${cx.toFixed(1)}" x2="${cx.toFixed(1)}" y1="${T}" y2="${T + ih - 12}" stroke="var(--muted)" stroke-dasharray="2 4" opacity="0.45"/>`;
      s += `<circle cx="${cx.toFixed(1)}" cy="${T + ih - 6}" r="4.5" fill="${full ? "#F2C94C" : "var(--ink)"}" stroke="${full ? "#B8860B" : "var(--muted)"}" stroke-width="1"><title>${MOON_NAME[p.q]} ${day} ${hm(p.t)} WIB</title></circle>`;
    });
  }
  s += "</g>";
  // right-side labels
  const labs = [];
  const last = bars[nb - 1][3]; labs.push([last, fmtNum(last), "var(--ink)"]);
  if (lay.plan && p) { labs.push([p.tp, "TP " + fmtNum(p.tp), up]); labs.push([p.sl, "SL " + fmtNum(p.sl), dn]); }
  if (lay.vp && S.vp) labs.push([S.vp.poc, "POC " + fmtNum(S.vp.poc), "var(--orange)"]);
  if (lay.pd && S.pd) { labs.push([S.pd[0], "Premium", dn]); labs.push([(S.pd[0] + S.pd[1]) / 2, "EQ " + fmtNum((S.pd[0] + S.pd[1]) / 2), "var(--muted)"]); labs.push([S.pd[1], "Discount", up]); }
  const used = [];
  labs.forEach(([v, t, col]) => {
    if (v > max || v < min) return; let yy = y(v) + 4;
    if (used.some(u => Math.abs(u - yy) < 12)) return; used.push(yy);
    s += `<text x="${W - R + 6}" y="${yy.toFixed(1)}" font-size="10.5" font-weight="700" fill="${col}">${t}</text>`;
  });
  s += `<text x="${L}" y="${H - 6}" font-size="10" fill="var(--muted)">${esc(S.d0)}</text><text x="${L + iw}" y="${H - 6}" font-size="10" text-anchor="end" fill="var(--muted)">${esc(S.d1)}</text>`;
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
  } else out.push("Belum ada perubahan struktur (BOS/CHoCH) dalam 120 hari terakhir.");
  const inside = (S.ob || []).find(z => pr <= z[1] && pr >= z[2]);
  if (inside) out.push(`Harga sedang berada di dalam order block ${inside[3] === 1 ? "bullish (area permintaan)" : "bearish (area penawaran)"} ${rng(inside[1], inside[2])}.`);
  const obBelow = (S.ob || []).filter(z => z[3] === 1 && z[1] < pr).sort((a, b) => b[1] - a[1])[0];
  const obAbove = (S.ob || []).filter(z => z[3] === -1 && z[2] > pr).sort((a, b) => a[2] - b[2])[0];
  if (obBelow) out.push(`Order block bullish terdekat di bawah harga: ${rng(obBelow[1], obBelow[2])} (${fmtDec((pr - obBelow[1]) / pr * 100, 1)}% di bawah)${S.vp ? (obBelow[4] === 1 ? ", berada di area volume tinggi (value area), jadi lebih kuat" : ", berada di area volume rendah, jadi konfirmasinya lebih lemah") : ""}. Sering dipakai sebagai acuan area beli atau penempatan stop loss di bawahnya.`);
  if (obAbove) out.push(`Order block bearish terdekat di atas harga: ${rng(obAbove[1], obAbove[2])} (${fmtDec((obAbove[2] - pr) / pr * 100, 1)}% di atas). Area yang berpotensi menahan kenaikan.`);
  const gaps = (S.fvg || []).map(z => ({ z, d: z[3] === 1 ? pr - z[1] : z[2] - pr })).filter(o => o.d >= 0).sort((a, b) => a.d - b.d);
  if (gaps[0]) out.push(`FVG ${gaps[0].z[3] === 1 ? "bullish" : "bearish"} terdekat yang belum terisi: ${rng(gaps[0].z[1], gaps[0].z[2])}. Harga sering kembali mengisi celah seperti ini.`);
  if (S.vp) out.push(`POC (harga dengan volume terbanyak dalam 120 hari) di ${fmtNum(S.vp.poc)}; value area ${fmtNum(S.vp.val)}–${fmtNum(S.vp.vah)}. Harga sekarang ${pr > S.vp.vah ? "di atas value area" : pr < S.vp.val ? "di bawah value area" : "di dalam value area"}.`);
  if (S.pd) {
    const pct = Math.round((pr - S.pd[1]) / ((S.pd[0] - S.pd[1]) || 1) * 100);
    out.push(`Posisi dalam range 120 hari: ${pct}%. ${pct >= 55 ? "Zona premium (relatif mahal)." : pct <= 45 ? "Zona discount (relatif murah)." : "Sekitar equilibrium."}`);
  }
  return out;
}

function renderSmc(r) {
  const lay = smcLayers();
  $("smc-box").innerHTML = smcChart(r, lay);
  $("smc-toggles").innerHTML = SMC_LAYERS.map(([k, n]) => `<label class="chip"><input type="checkbox" data-layer="${k}" ${lay[k] ? "checked" : ""}> ${n}</label>`).join("");
  $("smc-toggles").querySelectorAll("input").forEach(cb => cb.addEventListener("change", () => {
    const cur = smcLayers(); cur[cb.dataset.layer] = cb.checked; ls.set(SMC_KEY, cur); renderSmc(r);
  }));
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
    if (!v) return `<div class="tf-cell"><small>${n}</small><span class="muted">-</span><small>${k === "h4" ? "hanya 200 saham skor tertinggi" : "data tidak tersedia"}</small></div>`;
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
  let src = bear ? "batas bawah order block bearish terdekat di atas harga" : "puncak range 120 hari";
  if (!tp || (tp - mid) / risk < 1.5) { tp = ceilT(mid + 2 * risk); src = "2 kali risiko, karena target struktur terlalu dekat atau tidak ada"; }
  return { e1, e2, sl, tp, risk: Math.round(risk / mid * 1000) / 10, src, hv: ob[4] === 1, dist: Math.round((p - ob[1]) / p * 1000) / 10 };
}
function renderPlan(r0, r) {
  const box = $("plan-sec"); if (!box) return;
  const sp = r0.kd && r0.kd.c === "bad" ? null : structPlan(r0), ap = r0.plan;
  let mode = ls.get(PLAN_KEY, "atr"); if (mode === "smc" && !sp) mode = "atr"; if (mode === "atr" && !ap && sp) mode = "smc";
  const use = mode === "smc" ? sp : ap;
  r.plan = use; if (r.smc) renderSmc(r);
  if (!use) { box.innerHTML = `<h3>Rencana</h3><p class="muted" style="margin:0">Tidak ada rencana untuk saham ini (berlabel Hindari dulu, atau tidak ada order block bullish aktif di bawah harga).</p>`; return; }
  const calc = ls.get(CALC, { modal: 10000000, risk: 1 }), mid = (use.e1 + use.e2) / 2, rr = (use.tp - mid) / (mid - use.sl);
  const note = mode === "smc"
    ? `Entry di order block bullish ${fmtNum(use.e1)}–${fmtNum(use.e2)}${use.hv ? ", yang berada di area volume tinggi (konfirmasi lebih kuat)" : ", yang berada di area volume rendah (konfirmasi lebih lemah)"}. Stop loss sedikit di bawah order block. Target: ${use.src}.${use.dist > 1 ? ` Harga sekarang ${fmtDec(use.dist, 1)}% di atas area entry, jadi rencana ini menunggu pullback.` : ""}`
    : `Area entry dari MA20 (atau harga − 1 ATR) sampai harga sekarang, stop loss 1 ATR di bawah area entry, target 2 kali risiko.${sp ? "" : " Rencana berbasis struktur tidak tersedia karena tidak ada order block bullish aktif di bawah harga."}`;
  box.innerHTML = `<h3>Rencana (contoh, bukan rekomendasi)</h3>
    <div class="seg" role="group" aria-label="Jenis rencana">
      <button type="button" data-mode="atr" class="${mode === "atr" ? "on" : ""}" ${ap ? "" : "disabled"}>Berbasis ATR</button>
      <button type="button" data-mode="smc" class="${mode === "smc" ? "on" : ""}" ${sp ? "" : "disabled"}>Berbasis struktur (order block)</button>
    </div>
    <p class="plan-note">${esc(note)}</p>
    <div class="plan-box"><div><small>Area entry</small><b>${fmtNum(use.e1)}–${fmtNum(use.e2)}</b></div><div><small>Stop loss</small><b class="neg">${fmtNum(use.sl)}</b></div><div><small>Target</small><b class="pos">${fmtNum(use.tp)}</b></div><div><small>Risiko / R:R</small><b>${fmtDec(use.risk, 1)}% · 1:${fmtDec(rr, 1)}</b></div></div>
    <div class="calc">
      <div class="f"><label for="c-modal">Modal (Rp)</label><input type="number" id="c-modal" min="0" step="100000" value="${calc.modal}"></div>
      <div class="f"><label for="c-risk">Risiko per transaksi (% modal)</label><input type="number" id="c-risk" min="0.1" max="10" step="0.1" value="${calc.risk}"></div>
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
    $("c-out").innerHTML = lot > 0
      ? `Maksimal <b>${fmtNum(lot)} lot</b> (sekitar Rp ${fmtNum(lot * mid * 100)}). Kalau kena stop loss, rugi sekitar <b>Rp ${fmtNum(lot * perLotRisk)}</b> atau ${fmtDec(lot * perLotRisk / modal * 100, 2)}% modal.${byCash < byRisk ? " Dibatasi oleh jumlah modal." : ""}`
      : "Modal atau risiko terlalu kecil untuk membeli 1 lot dengan stop loss ini.";
  };
  $("c-modal").addEventListener("input", upd); $("c-risk").addEventListener("input", upd); upd();
  $("j-add").addEventListener("click", () => journalForm(r0, use, lot, mode));
}

/* ---------- jurnal trading (tersimpan di browser ini) ---------- */
const JR = "idxs:jurnal";
const SETUPS = ["BOS + order block", "CHoCH + order block", "Pantulan dari FVG", "Pullback ke zona discount", "Breakout", "Pullback ke MA20", "Lainnya"];
const jrLoad = () => ls.get(JR, []), jrSave = a => ls.set(JR, a);
function journalForm(r, p, lot, mode) {
  const today = ymd(new Date()), mid = floorT((p.e1 + p.e2) / 2);
  $("j-form").innerHTML = `<div class="j-form">
    <div class="f"><label>Tanggal</label><input type="date" id="jf-tgl" value="${today}"></div>
    <div class="f"><label>Harga entry</label><input type="number" id="jf-entry" value="${mid}"></div>
    <div class="f"><label>Stop loss</label><input type="number" id="jf-sl" value="${p.sl}"></div>
    <div class="f"><label>Target</label><input type="number" id="jf-tp" value="${p.tp}"></div>
    <div class="f"><label>Lot</label><input type="number" id="jf-lot" value="${lot || 1}" min="1"></div>
    <div class="f"><label>Setup</label><select id="jf-setup">${SETUPS.map(s => `<option ${mode === "smc" && s === "BOS + order block" ? "selected" : ""}>${s}</option>`).join("")}</select></div>
    <div class="f"><label>Timeframe entry</label><select id="jf-tf"><option>1 jam</option><option>4 jam</option><option selected>Harian</option></select></div>
    <div class="f" style="grid-column:1/-1"><label>Catatan</label><input type="text" id="jf-note" placeholder="mis. CHoCH 1 jam di OB harian, broker akumulasi"></div>
    <div style="grid-column:1/-1;display:flex;gap:8px"><button class="icon-btn" id="jf-save" type="button">Simpan trade</button><button class="icon-btn" id="jf-cancel" type="button">Batal</button></div>
  </div>`;
  $("jf-cancel").addEventListener("click", () => $("j-form").innerHTML = "");
  $("jf-save").addEventListener("click", () => {
    const e = +$("jf-entry").value, sl = +$("jf-sl").value;
    if (!(e > 0) || !(sl > 0) || sl >= e) { alert("Stop loss harus di bawah harga entry."); return; }
    const a = jrLoad();
    a.push({ id: Date.now(), t: r.t, tgl: $("jf-tgl").value, entry: e, sl, tp: +$("jf-tp").value || null, lot: +$("jf-lot").value || 1,
      setup: $("jf-setup").value, tf: $("jf-tf").value, note: $("jf-note").value.trim(), exit: null, tglExit: null });
    jrSave(a); renderJournal();
    $("j-form").innerHTML = `<p class="calc-out">Tersimpan di jurnal. Lihat bagian Jurnal trading di halaman utama.</p>`;
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
    return `<tr><td>${esc(j.tgl)}</td><td><b>${esc(j.t)}</b><div class="muted" style="font-size:0.72rem">${esc(j.tf)}${j.note ? " · " + esc(j.note) : ""}</div></td><td>${esc(j.setup)}</td><td class="num">${fmtNum(j.entry)}</td><td class="num">${fmtNum(j.sl)}</td><td class="num">${j.tp ? fmtNum(j.tp) : "-"}</td><td class="num">${fmtNum(j.lot)}</td>
      <td class="num">${px != null ? fmtNum(px) : "-"}${j.exit == null ? '<div class="muted" style="font-size:0.72rem">masih terbuka</div>' : ""}${j.exit == null && cur && cur.p <= j.sl ? '<div class="neg" style="font-size:0.72rem">sudah di bawah SL</div>' : ""}${j.exit == null && cur && j.tp && cur.p >= j.tp ? '<div class="pos" style="font-size:0.72rem">sudah capai target</div>' : ""}</td>
      <td class="num ${r == null ? "" : r >= 0 ? "pos" : "neg"}">${r == null ? "-" : fmtDec(r, 2) + "R"}</td>
      <td class="j-act" data-id="${j.id}">${j.exit == null ? `<button class="icon-btn" data-close="${j.id}" type="button">Tutup</button>` : ""} <button class="icon-btn" data-del="${j.id}" type="button">Hapus</button></td></tr>`;
  }).join("")}</tbody></table></div>` : '<p class="muted">Belum ada trade. Buka panel detail saham, lalu klik "Catat ke jurnal" di bagian Rencana.</p>';
  $("j-list").querySelectorAll("[data-del]").forEach(b => b.addEventListener("click", () => { if (confirm("Hapus trade ini dari jurnal?")) { jrSave(jrLoad().filter(j => j.id !== +b.dataset.del)); renderJournal(); } }));
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
  const a = jrLoad(), head = ["tanggal", "saham", "setup", "timeframe", "entry", "stop_loss", "target", "lot", "harga_keluar", "tanggal_keluar", "R", "catatan"];
  const lines = [head.join(",")].concat(a.map(j => [j.tgl, j.t, j.setup, j.tf, j.entry, j.sl, j.tp ?? "", j.lot, j.exit ?? "", j.tglExit ?? "", j.exit != null ? rOf(j, j.exit).toFixed(2) : "", `"${(j.note || "").replace(/"/g, '""')}"`].join(",")));
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
function openDrawer(t) {
  const r0 = DATA.find(x => x.t === t); if (!r0) return;
  const w = weights(), r = { ...r0, score: score(r0, w) }; openT = t;
  const up = r.chg >= 0, c = r._ck, p = r.plan, tf = r.tf || {};
  const calc = ls.get(CALC, { modal: 10000000, risk: 1 });
  const comp = [["Trend", r.trend, w.trend], ["Breakout", r.brk, w.brk], ["Price action", r.pa, w.pa], ["Momentum", r.mom, w.mom]];
  const tfNames = [["h1", "1 jam"], ["h2", "2 jam"], ["h4", "4 jam"], ["daily", "Harian"], ["weekly", "Mingguan"], ["monthly", "Bulanan"]];
  $("drawer").innerHTML = `
    <div class="d-head">
      <div><div class="d-tk" id="d-title">${r.t}</div><div class="d-name">${esc(r.nm)}${r.sector && r.sector !== "-" ? ". " + esc(r.sector) : ""}</div></div>
      <button class="icon-btn" id="d-close" type="button">Tutup</button>
    </div>
    <div class="d-price">${fmtNum(r.p)} <span class="${up ? "pos" : "neg"}" style="font-size:1rem">${up ? "+" : ""}${fmtDec(r.chg, 2)}%</span></div>
    <div class="muted" style="font-size:0.8rem">Candle terakhir ${esc(r.tgl)}. Skor ${fmtDec(r.score, 0)} dengan bobot saat ini.${r.top ? ` <span class="top-badge">Top 10 #${r.top}</span>` : ""}</div>
    <div class="d-sec">
      ${r.kd ? `<span class="kd ${r.kd.c}">${esc(r.kd.l)}</span><div class="d-why">${esc(r.kd.why)}.</div>` : ""}
      <div style="margin-top:6px">${badges(r)}</div>
    </div>
    ${msBlock(r)}
    ${r.smc ? `<div class="d-sec"><h3>Chart 120 hari dengan Smart Money Concepts</h3>
      <div id="smc-box"></div>
      <div class="chips smc-toggles" id="smc-toggles"></div>
      <ul class="smc-sum">${smcSummary(r).map(t => `<li>${esc(t)}</li>`).join("")}</ul>
      <p class="muted" style="font-size:0.78rem;margin:6px 0 0">SMC di sini versi sederhana yang dihitung otomatis, jadi bisa berbeda dari indikator SMC di TradingView atau Stockbit. Garis putus-putus = CHoCH, garis penuh = BOS. Lingkaran kuning di bawah = purnama, lingkaran gelap = bulan baru (ditaruh di hari bursa terdekat).</p>
    </div>` : `<div class="d-sec"><h3>Chart 30 hari</h3>${bigChart(r)}
      <div class="legend"><span><i style="background:var(--blue)"></i>MA20</span><span><i style="background:var(--orange)"></i>MA50</span>${p ? '<span><i style="background:var(--accent);opacity:.35;height:8px"></i>Area entry</span><span><i style="background:var(--down)"></i>Stop loss</span><span><i style="background:var(--up)"></i>Target</span>' : ""}</div>
      <p class="muted" style="font-size:0.78rem;margin:6px 0 0">Chart SMC 120 hari belum tersedia karena riwayat harga saham ini masih terlalu pendek.</p>
    </div>`}
    <div class="d-sec"><h3>Checklist: ${c.pass} dari ${c.total} syarat terpenuhi</h3>
      <ul class="checklist">${c.items.map(([label, ok]) => `<li><span class="ci ${ok === null ? "na" : ok ? "y" : "x"}">${ok === null ? "–" : ok ? "✓" : "✗"}</span><span>${esc(label)}${ok === null ? ' <span class="muted">(data tidak tersedia)</span>' : ""}</span></li>`).join("")}</ul>
    </div>
    <div class="d-sec" id="plan-sec"></div>
    <div class="d-sec" id="hist-sec"></div>
    <div class="d-sec"><h3>Rincian skor</h3><div class="bars">${comp.map(([n, v, wt]) => `<div class="bar-row"><span>${n}</span><span class="track"><i style="width:${v}%"></i></span><span>${v}/100, bobot ${wt}</span></div>`).join("")}</div></div>
    <div class="d-sec"><h3>Ringkasan per timeframe</h3><div class="tf-grid">${tfNames.map(([k, n]) => `<div class="tf-cell"><small>${n}</small>${tf[k] ? `<span class="v ${vClass(tf[k].summary)}">${esc(tf[k].summary)}</span><small>${esc(tf[k].ma_detail)}</small>` : '<span class="muted">-</span>'}</div>`).join("")}</div></div>
    <div class="d-sec"><h3>Data lain</h3><div class="muted" style="font-size:0.86rem">RSI ${fmtDec(r.rsi, 1)}. Volume ${fmtDec(r.vr, 2)}× rata-rata. Transaksi ${fmtValue(r.val)}/hari. Beta ${r.beta == null ? "-" : fmtDec(r.beta, 2)}. ${r.cst && r.cst.total ? `Masuk Top 10 ${r.cst.count} dari ${r.cst.total} hari terakhir.` : ""}</div></div>
    <div class="d-actions"><button class="icon-btn" id="d-star" type="button">${watch.has(r.t) ? "★ Hapus dari watchlist" : "☆ Tambah ke watchlist"}</button></div>
    <p class="d-foot">Semua angka dihitung otomatis dari data Yahoo Finance dan bisa tertunda. Cocokkan dengan chart di aplikasi trading-mu sebelum mengambil keputusan.</p>`;
  $("drawer").classList.add("open"); $("scrim").classList.add("open"); $("drawer").focus();
  $("d-close").addEventListener("click", closeDrawer);
  $("d-star").addEventListener("click", () => { toggleWatch(r.t); openDrawer(r.t); });
  renderPlan(r0, r);
  renderHist(r0);
}
function openIhsg() {
  const m = MARKET.ihsg; if (!m) return;
  openT = "IHSG";
  const up = m.chg >= 0, tf = m.tf || {}, b = MARKET.breadth;
  const r = { t: "IHSG", p: m.p, smc: m.smc, plan: null };
  const pos = (v, n) => v ? `<li><span class="ci ${m.p > v ? "y" : "x"}">${m.p > v ? "✓" : "✗"}</span><span>${m.p > v ? "Di atas" : "Di bawah"} ${n} (${fmtDec(v, 2)})</span></li>` : "";
  const tfNames = [["h1", "1 jam"], ["h2", "2 jam"], ["h4", "4 jam"], ["daily", "Harian"], ["weekly", "Mingguan"], ["monthly", "Bulanan"]];
  $("drawer").innerHTML = `
    <div class="d-head">
      <div><div class="d-tk" id="d-title">IHSG</div><div class="d-name">Indeks Harga Saham Gabungan</div></div>
      <button class="icon-btn" id="d-close" type="button">Tutup</button>
    </div>
    <div class="d-price">${fmtDec(m.p, 2)} <span class="${up ? "pos" : "neg"}" style="font-size:1rem">${up ? "+" : ""}${fmtDec(m.chg, 2)}%</span></div>
    <div class="muted" style="font-size:0.8rem">Candle terakhir ${esc(m.tgl || "")}. Ringkasan teknikal harian: ${esc(m.d)}${m.rsi ? `, RSI ${fmtDec(m.rsi, 1)}` : ""}.</div>
    ${msBlock({ ms: m.ms })}
    ${m.smc ? `<div class="d-sec"><h3>Chart 120 hari dengan Smart Money Concepts</h3>
      <div id="smc-box"></div><div class="chips smc-toggles" id="smc-toggles"></div>
      <ul class="smc-sum">${smcSummary(r).map(t => `<li>${esc(t)}</li>`).join("")}</ul></div>` : ""}
    <div class="d-sec"><h3>Posisi terhadap moving average</h3><ul class="checklist">${pos(m.ma20, "MA20")}${pos(m.ma50, "MA50")}${pos(m.ma200, "MA200")}</ul></div>
    <div class="d-sec"><h3>Ringkasan per timeframe</h3><div class="tf-grid">${tfNames.map(([k, n]) => `<div class="tf-cell"><small>${n}</small>${tf[k] ? `<span class="v ${vClass(tf[k].summary)}">${esc(tf[k].summary)}</span><small>${esc(tf[k].ma_detail)}</small>` : '<span class="muted">-</span>'}</div>`).join("")}</div></div>
    ${b ? `<div class="d-sec"><h3>Napas pasar</h3><div class="muted" style="font-size:0.88rem">${b.pct}% dari ${fmtNum(b.n)} saham likuid (transaksi ≥ Rp 1 M/hari) berada di atas MA20. Kalau IHSG naik tapi napas pasar di bawah 50%, kenaikannya hanya ditopang sedikit saham besar.</div></div>` : ""}
    <p class="d-foot">Data IHSG dari Yahoo Finance (^JKSE), bisa tertunda. Kondisi IHSG dipakai sebagai salah satu syarat di checklist setiap saham.</p>`;
  $("drawer").classList.add("open"); $("scrim").classList.add("open"); $("drawer").focus();
  $("d-close").addEventListener("click", closeDrawer);
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
  const st = e.target.closest("[data-star]"); if (st) { e.stopPropagation(); toggleWatch(st.dataset.star); return; }
  const tr = e.target.closest("tr[data-t]"); if (tr) openDrawer(tr.dataset.t);
});
$("tbody").addEventListener("keydown", e => { if (e.key === "Enter" && e.target.matches("tr[data-t]")) openDrawer(e.target.dataset.t); });
$("scrim").addEventListener("click", closeDrawer);
document.addEventListener("keydown", e => { if (e.key === "Escape" && openT) closeDrawer(); });

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
renderMarket(); load(); render(); renderCal(); renderJournal();
</script>
</body>
</html>
'''


if __name__ == "__main__":
    main()
