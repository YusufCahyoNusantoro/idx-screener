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
    if sisa:   # coba ulang yang gagal satu per satu (mis. error 'database is locked' dari cache yfinance)
        time.sleep(2)
        for t in sisa:
            out.update(_unduh([t], period, interval, 1, threads=False))
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


def ambil_sektor(tickers):
    cache = {}
    if CACHE_SEKTOR.exists():
        try:
            cache = json.loads(CACHE_SEKTOR.read_text(encoding="utf-8"))
        except Exception:
            cache = {}
    kurang = [t for t in tickers if t not in cache]
    if kurang:
        print(f"  Mengambil sektor untuk {len(kurang)} saham (sekali saja, lalu disimpan)...")
    for t in kurang:
        try:
            info = yf.Ticker(t + ".JK").info or {}
            cache[t] = info.get("sector") or "-"
        except Exception:
            pass   # gagal (mis. rate limit) -> tidak disimpan, dicoba lagi di run berikutnya
    CACHE_SEKTOR.write_text(json.dumps(cache, indent=1), encoding="utf-8")
    return {t: cache.get(t, "-") for t in tickers}


# ─────────────────────────── indikator ───────────────────────────
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
    tp = (h + l + c) / 3
    mad = tp.rolling(20).apply(lambda x: np.mean(np.abs(x - x.mean())), raw=True)
    cci = ((tp - tp.rolling(20).mean()) / (0.015 * mad.replace(0, np.nan))).iloc[-1]
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
    agg = g.groupby(["_d", "_b"], sort=True).agg(
        Open=("Open", "first"), High=("High", "max"), Low=("Low", "min"),
        Close=("Close", "last"), Volume=("Volume", "sum"))
    return agg.reset_index(drop=True)


def pola_candle(df):
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


# ─────────────────────────── analisa per saham ───────────────────────────
def analisa(t, d, jam, ihsg_ret, sektor, frac_hari, hari_ini):
    c, v = d["Close"], d["Volume"]
    if len(d) < 30:
        return None
    last = float(c.iloc[-1])
    prev = float(c.iloc[-2])
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

    pattern = pola_candle(d)
    o, hh, ll = d["Open"].iloc[-1], d["High"].iloc[-1], d["Low"].iloc[-1]
    posisi = (last - ll) / ((hh - ll) or 1e-9)
    if pattern:
        pa = 100
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
    if jam is not None and len(jam) >= 20:
        tf["h1"] = rating(jam)
        tf["h2"] = rating(gabung_jam(jam, 2))
        tf["h4"] = rating(gabung_jam(jam, 4))
    tf = {k: x for k, x in tf.items() if x}

    tail = d.iloc[-30:]
    return {
        "t": t, "p": round(last, 2), "chg": round((last / prev - 1) * 100, 2),
        "val": float(nilai) if fin(nilai) else 0.0,
        "trend": trend, "brk": brk, "pa": pa, "mom": mom,
        "trendOk": trend_ok, "brkOk": brk_ok, "pattern": pattern,
        "rsi": round(r, 1), "vr": round(vr, 2), "tf": tf,
        "c": [round(float(x), 2) for x in tail["Close"]],
        "ohlc": [[round(float(a), 2) for a in row] for row in tail[["Open", "High", "Low", "Close"]].values],
        "sector": sektor.get(t, "-"), "beta": beta,
        "tgl": d.index[-1].strftime("%Y-%m-%d"),
    }


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
    top = sorted(rows, key=skor, reverse=True)[:10]
    riw[tanggal] = [r["t"] for r in top]          # run berulang di hari sama = ditimpa
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


def tulis_html(rows, now, status, n_gagal, pakai_intraday, out_html=OUT_HTML, arsip=True):
    tgl_data = max((r["tgl"] for r in rows), default="-")
    waktu = f"{now.day} {BULAN[now.month - 1]} {now.year}, {now:%H:%M} WIB"
    sub = (f"Data diambil: {waktu} • {status} • {len(rows)} saham"
           + (f" ({n_gagal} gagal diambil)" if n_gagal else "")
           + f" • Candle terakhir: {tgl_data}")
    parsial = "berjalan" in status or "Sesi 1" in status or status == "Pre-closing"
    disc = ("📡 Data asli dari Yahoo Finance — biasanya tertunda ±10–15 menit dari harga bursa."
            + (" Candle hari ini <b>belum final</b> (sesi masih/baru berjalan); rasio volume "
               "diproyeksikan ke satu hari penuh." if parsial else "")
            + ("" if pakai_intraday else " Kolom 1H/2H/4H dimatikan (--no-intraday).")
            + " Halaman ini reload otomatis tiap 5 menit.<br><br>⚠️ Bukan rekomendasi/nasihat keuangan. "
              "Alat bantu penyaringan teknikal saja — tetap lakukan riset &amp; manajemen risiko "
              "sendiri sebelum trading.")
    html = (TEMPLATE
            .replace("__DATA__", json.dumps(bersih(rows), ensure_ascii=False, allow_nan=False))
            .replace("__TITLE__", f"{now:%Y-%m-%d %H:%M}")
            .replace("__REFRESH__", '<meta http-equiv="refresh" content="300">')
            .replace("__BADGE__", f"DATA ASLI • {status.upper()}")
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
    } for r in sorted(rows, key=skor, reverse=True)]
    pd.DataFrame(flat).to_csv(out_html.parent / "hasil_screener.csv", index=False)


def main():
    ap = argparse.ArgumentParser(description="Screener saham IDX (data asli Yahoo Finance)")
    ap.add_argument("--tickers", help="file teks berisi ticker (tanpa .JK), dipisah spasi/baris")
    ap.add_argument("--no-intraday", action="store_true", help="lewati data 1 jam (lebih cepat)")
    ap.add_argument("--no-sektor", action="store_true", help="lewati pengambilan sektor")
    ap.add_argument("--buka", action="store_true", help="buka hasil di browser")
    ap.add_argument("--output", default=str(OUT_HTML), help="lokasi file HTML hasil (default hasil_screener.html)")
    ap.add_argument("--no-arsip", action="store_true", help="jangan simpan salinan ke folder arsip/")
    args = ap.parse_args()

    tickers = DEFAULT_TICKERS
    if args.tickers:
        tickers = Path(args.tickers).read_text(encoding="utf-8").replace(",", " ").split()
    tickers = sorted({t.strip().upper().removesuffix(".JK") for t in tickers if t.strip()})

    now = datetime.now(WIB)
    status, frac = status_pasar(now)
    print(f"[{now:%H:%M} WIB] {status} — screening {len(tickers)} saham...")

    print("  Unduh data harian (5 tahun)...")
    harian = {t: ke_tanggal(df) for t, df in unduh(tickers, "5y", "1d").items()}
    ihsg = unduh(["^JKSE"], "2y", "1d").get("^JKSE")
    ihsg_ret = ke_tanggal(ihsg)["Close"].pct_change() if ihsg is not None else None

    jam = {}
    if not args.no_intraday:
        print("  Unduh data 1 jam (60 hari)...")
        jam = unduh(list(harian), "60d", "60m")

    sektor = {} if args.no_sektor else ambil_sektor(list(harian))

    hari_ini = now.date()
    rows, gagal = [], [t for t in tickers if t not in harian]
    for t, d in harian.items():
        if (pd.Timestamp(hari_ini) - d.index[-1]).days > 10:   # suspend / tidak aktif
            gagal.append(t)
            continue
        try:
            r = analisa(t, d, jam.get(t), ihsg_ret, sektor, frac, hari_ini)
        except Exception as e:
            print(f"  ! {t}: {e}")
            r = None
        if r:
            rows.append(r)
        else:
            gagal.append(t)

    if not rows:
        sys.exit("Tidak ada data yang berhasil diambil. Cek koneksi internet atau coba lagi beberapa menit lagi.")

    update_konsistensi(rows, now.strftime("%Y-%m-%d"))
    out_html = Path(args.output).resolve()
    tulis_html(rows, now, status, len(gagal), not args.no_intraday, out_html, not args.no_arsip)

    top = sorted(rows, key=skor, reverse=True)[:5]
    print(f"  Selesai: {len(rows)} saham, {len(gagal)} gagal" + (f" ({', '.join(sorted(gagal)[:10])}{'...' if len(gagal) > 10 else ''})" if gagal else ""))
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
__REFRESH__
<style>
  :root {
    --bg:#f4f6f9; --panel:#ffffff; --panel2:#f8f9fb; --border:#e3e7ed; --text:#1a2233;
    --muted:#6b7688; --accent:#2563eb; --accent2:#1d4ed8; --green:#16a34a; --green-lt:#22c55e;
    --red:#dc2626; --red-lt:#f87171;
    padding-top: env(safe-area-inset-top, 0px);
    padding-bottom: env(safe-area-inset-bottom, 0px);
  }
  @media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) {
      --bg:#f4f6f9; --panel:#ffffff; --panel2:#f8f9fb; --border:#e3e7ed; --text:#1a2233; --muted:#6b7688;
    }
  }
  * { box-sizing: border-box; }
  html, body { height: 100%; }
  body {
    margin:0; padding: 20px; background: var(--bg); color: var(--text);
    font-family: -apple-system, Segoe UI, Roboto, Helvetica, Arial, sans-serif;
  }
  h1 { font-size: 1.4rem; margin: 0 0 4px; color:#0f172a; }
  .sub { color: var(--muted); font-size: 0.88rem; margin-bottom: 16px; }
  .disclaimer {
    background:#fff7e6; border:1px solid #ffe1a8; color:#92660a;
    padding:10px 14px; border-radius:8px; font-size:0.8rem; margin-bottom:18px;
  }
  .panel {
    background: var(--panel); border:1px solid var(--border); border-radius:12px;
    padding:16px 18px; margin-bottom:16px; box-shadow: 0 1px 3px rgba(16,24,40,0.04);
  }
  .panel h2 { font-size: 0.85rem; margin: 0 0 12px; color: #334155; font-weight:700; text-transform:uppercase; letter-spacing:0.03em; }

  .presets { display:flex; flex-wrap:wrap; gap:8px; margin-bottom:4px; }
  .preset-btn {
    background:#eef2ff; color:#3730a3; border:1px solid #c7d2fe; border-radius:999px;
    padding:7px 14px; font-size:0.82rem; font-weight:600; cursor:pointer; white-space:nowrap;
    transition: background 0.15s;
  }
  .preset-btn:hover { background:#e0e7ff; }
  .preset-btn.active { background:#4338ca; color:#fff; border-color:#4338ca; }
  .preset-btn.reset { background:#f1f5f9; color:#475569; border-color:#e2e8f0; }

  .weights-grid {
    display:grid; grid-template-columns: repeat(auto-fit, minmax(180px,1fr)); gap: 14px 20px;
  }
  .weight-row label { display:flex; justify-content:space-between; font-size:0.82rem; margin-bottom:4px; color:#334155;}
  .weight-row .val { color: var(--accent); font-weight:700; }
  input[type=range] { width:100%; accent-color: var(--accent); }

  .filters-grid {
    display:grid; grid-template-columns: repeat(auto-fit, minmax(200px,1fr)); gap: 14px 22px;
    margin-top: 14px; padding-top:14px; border-top:1px solid var(--border);
  }
  .filter-item label { display:block; font-size:0.78rem; color:#64748b; margin-bottom:5px; font-weight:600; text-transform:uppercase; letter-spacing:0.02em;}
  .range-pair { display:flex; align-items:center; gap:6px; }
  .range-pair input[type=number] {
    width:100%; padding:7px 9px; border:1px solid var(--border); border-radius:7px;
    font-size:0.85rem; background:#fff; color:var(--text);
  }
  .filter-chip { display:flex; align-items:center; gap:6px; font-size:0.85rem; color:#334155; }
  .filter-chip input { accent-color: var(--accent); width:16px; height:16px; }
  .chips-row { display:flex; flex-wrap:wrap; gap:14px 22px; align-items:center; margin-top:14px; padding-top:14px; border-top:1px solid var(--border); }
  .minscore { display:flex; align-items:center; gap:10px; flex:1; min-width:220px; }
  .minscore label { font-size:0.85rem; white-space:nowrap; color:#334155;}
  .minscore .val { color: var(--accent); font-weight:700; min-width:34px; }
  .search-box {
    background:#fff; border:1px solid var(--border); color:var(--text);
    border-radius:8px; padding:8px 12px; font-size:0.85rem; min-width:160px;
  }
  .count-info { color: var(--muted); font-size:0.85rem; margin: 4px 2px 10px; }

  table { width:100%; border-collapse:collapse; background: var(--panel); border-radius:10px; overflow:hidden; }
  thead th {
    background: var(--panel2); color:#475569; text-align:left; padding:10px 12px;
    font-size:0.74rem; text-transform:uppercase; letter-spacing:0.04em; cursor:pointer;
    border-bottom:1px solid var(--border); user-select:none; white-space:nowrap;
  }
  thead th:hover { color: var(--accent); }
  thead th.active::after { content: " BE"; color: var(--accent); }
  tbody td { padding:9px 12px; border-bottom:1px solid var(--border); font-size:0.86rem; vertical-align:middle; }
  tbody tr:hover { background:#f8fafc; }
  .tk { font-weight:700; letter-spacing:0.3px; color:#0f172a; }
  .pos { color: var(--green); font-weight:600; }
  .neg { color: var(--red); font-weight:600; }
  .muted { color: var(--muted); }
  .badge {
    display:inline-block; font-size:0.7rem; padding:2px 8px; border-radius:999px;
    margin:1px 2px; border:1px solid var(--border); white-space:nowrap; font-weight:600;
  }
  .badge.trend { background:#eff6ff; color:#1d4ed8; border-color:#bfdbfe; }
  .badge.breakout { background:#f0fdf4; color:#15803d; border-color:#bbf7d0; }
  .badge.pattern { background:#fffbeb; color:#92400e; border-color:#fde68a; }
  .score-bar { position:relative; width:84px; height:18px; background:#eef1f5; border-radius:6px; overflow:hidden; }
  .score-fill { position:absolute; left:0; top:0; bottom:0; background: linear-gradient(90deg,#2563eb,#38bdf8); }
  .score-bar span {
    position:absolute; inset:0; display:flex; align-items:center; justify-content:center;
    font-size:0.72rem; font-weight:700; color:#fff; text-shadow:0 1px 2px rgba(0,0,0,.35);
  }
  svg.spark { display:block; }
  .verdict { font-weight:700; font-size:0.78rem; white-space:nowrap; cursor:default; }
  .verdict.sb { color:#15803d; }
  .verdict.b { color:#22c55e; font-weight:600; }
  .verdict.n { color:#94a3b8; font-weight:600; }
  .verdict.s { color:#f87171; font-weight:600; }
  .verdict.ss { color:#dc2626; }
  .table-wrap { overflow-x:auto; border-radius:10px; border:1px solid var(--border); }
  .pager { display:flex; gap:8px; justify-content:flex-end; margin-top:12px; }
  .pager button {
    background: var(--panel); color:var(--text); border:1px solid var(--border);
    border-radius:6px; padding:6px 12px; cursor:pointer; font-size:0.82rem;
  }
  .pager button:disabled { opacity:0.4; cursor:default; }
  .pager button:not(:disabled):hover { border-color: var(--accent); }

  .guide-item {
    border:1px solid var(--border); border-radius:10px; margin-bottom:10px; padding:0; overflow:hidden;
  }
  .guide-item summary {
    padding:12px 16px; cursor:pointer; font-weight:700; font-size:0.9rem; color:#1e293b;
    background:var(--panel2); list-style:none; display:flex; align-items:center; gap:8px;
  }
  .guide-item summary::-webkit-details-marker { display:none; }
  .guide-item summary::before { content:"\25B8"; color:var(--accent); font-size:0.75rem; transition:transform 0.15s; }
  .guide-item[open] summary::before { transform:rotate(90deg); }
  .guide-item summary:hover { background:#eef2ff; }
  .guide-body { padding:14px 18px 16px; font-size:0.85rem; line-height:1.6; color:#334155; }
  .guide-body p { margin:0 0 10px; }
  .guide-body p:last-child { margin-bottom:0; }
</style>
</head>
<body>
  <h1>📈 IDX Screener — Teknikal &amp; Price Action <span style="font-size:0.6rem;background:#dcfce7;color:#166534;padding:3px 10px;border-radius:999px;vertical-align:middle;">__BADGE__</span></h1>
  <div class="sub">__SUB__</div>
  <div class="disclaimer">__DISCLAIMER__</div>

  <div class="panel">
    <h2>⚡ Screen Populer</h2>
    <div class="presets" id="presets">
      <button class="preset-btn reset" data-preset="reset" title="Kembalikan semua bobot &amp; filter ke pengaturan awal">↻ Reset</button>
      <button class="preset-btn" data-preset="breakout" title="Harga tembus level tertinggi 20 hari + volume melonjak &#8805;1.5x rata-rata">🚀 Breakout Momentum</button>
      <button class="preset-btn" data-preset="golden" title="Struktur uptrend rapi: MA20 &gt; MA50 &gt; MA200 dan harga di atas MA20">📈 Golden Cross Uptrend</button>
      <button class="preset-btn" data-preset="reversal" title="RSI rendah (oversold) + pola candle bullish reversal muncul">🔄 Oversold Reversal</button>
      <button class="preset-btn" data-preset="allgreen" title="Rating Strong Buy kompak di Daily, Mingguan, DAN Bulanan sekaligus">✅ Strong Buy Semua Timeframe</button>
      <button class="preset-btn" data-preset="pattern" title="Candle terakhir membentuk pola bullish (engulfing/hammer/marubozu)">🕯️ Ada Pola Candle</button>
      <button class="preset-btn" data-preset="quality" title="Nilai transaksi &#8805; Rp 5M/hari DAN konsisten masuk Top-10 skor &#8805;3 dari 10 hari terakhir">🏆 Likuid &amp; Konsisten Top10</button>
    </div>
    <p style="font-size:0.8rem;color:#64748b;margin:10px 2px 0;">Bingung istilahnya? Lihat <a href="#panduan" style="color:#2563eb;font-weight:600;">Panduan Screen &amp; Istilah</a> di bagian bawah halaman ini.</p>
  </div>

  <div class="panel">
    <h2>⚖️ Bobot Skor</h2>
    <div class="weights-grid">
      <div class="weight-row">
        <label>Trend <span class="val" id="w-trend-val">30</span></label>
        <input type="range" id="w-trend" min="0" max="100" value="30">
      </div>
      <div class="weight-row">
        <label>Breakout <span class="val" id="w-brk-val">30</span></label>
        <input type="range" id="w-brk" min="0" max="100" value="30">
      </div>
      <div class="weight-row">
        <label>Price Action <span class="val" id="w-pa-val">25</span></label>
        <input type="range" id="w-pa" min="0" max="100" value="25">
      </div>
      <div class="weight-row">
        <label>Momentum (RSI) <span class="val" id="w-mom-val">15</span></label>
        <input type="range" id="w-mom" min="0" max="100" value="15">
      </div>
    </div>

    <div class="filters-grid">
      <div class="filter-item">
        <label>Rentang Harga (Rp)</label>
        <div class="range-pair">
          <input type="number" id="price-min" placeholder="Min" min="0">
          <span>–</span>
          <input type="number" id="price-max" placeholder="Max" min="0">
        </div>
      </div>
      <div class="filter-item">
        <label>Rentang RSI</label>
        <div class="range-pair">
          <input type="number" id="rsi-min" placeholder="0" min="0" max="100">
          <span>–</span>
          <input type="number" id="rsi-max" placeholder="100" min="0" max="100">
        </div>
      </div>
      <div class="filter-item">
        <label>Min. Nilai Transaksi 20H (Rp Miliar)</label>
        <input type="number" id="val-min" placeholder="mis. 5" min="0" step="0.5" style="width:100%">
      </div>
      <div class="filter-item">
        <label>Min. Konsisten Top10 (hari, dari 10 hari terakhir)</label>
        <input type="number" id="streak-min" placeholder="mis. 3" min="0" style="width:100%">
      </div>
      <div class="filter-item">
        <label>Cari Ticker</label>
        <input type="text" id="search" class="search-box" placeholder="mis. BBCA" style="width:100%">
      </div>
    </div>

    <div class="chips-row">
      <div class="minscore">
        <label>Skor minimum</label>
        <input type="range" id="min-score" min="0" max="100" value="40" style="flex:1">
        <span class="val" id="min-score-val">40</span>
      </div>
      <label class="filter-chip"><input type="checkbox" id="f-trend"> Hanya Uptrend</label>
      <label class="filter-chip"><input type="checkbox" id="f-breakout"> Hanya Breakout</label>
      <label class="filter-chip"><input type="checkbox" id="f-pattern"> Hanya ada Pola Candle</label>
      <label class="filter-chip"><input type="checkbox" id="f-allgreen"> Strong Buy di semua Timeframe</label>
    </div>
  </div>

  <div class="count-info" id="count-info"></div>
  <div class="table-wrap">
    <table id="tbl">
      <thead>
        <tr>
          <th data-key="_chart">Chart</th>
          <th data-key="t">Ticker</th>
          <th data-key="p">Harga</th>
          <th data-key="chg">Chg%</th>
          <th data-key="sector">Sektor</th>
          <th data-key="val">Nilai Transaksi 20H</th>
          <th data-key="score" class="active">Skor</th>
          <th data-key="_sinyal">Sinyal</th>
          <th data-key="rsi">RSI</th>
          <th data-key="beta" title="Beta terhadap IHSG (^JKSE) - volatilitas relatif ke pasar">Beta</th>
          <th data-key="_h1" title="Sinyal intraday 1 Jam (dari candle 1 jam Yahoo, bisa kosong)">1H</th>
          <th data-key="_h2" title="Sinyal intraday 2 Jam (dari candle 1 jam Yahoo, bisa kosong)">2H</th>
          <th data-key="_h4" title="Sinyal intraday 4 Jam (dari candle 1 jam Yahoo, bisa kosong)">4H</th>
          <th data-key="_tfd" title="Ringkasan teknikal Daily (Moving Averages + Indikator)">Daily</th>
          <th data-key="_tfw" title="Ringkasan teknikal Mingguan">Mingguan</th>
          <th data-key="_tfm" title="Ringkasan teknikal Bulanan">Bulanan</th>
          <th data-key="_streak" title="Berapa hari (dari beberapa hari run terakhir) saham ini masuk Top-10 skor">Konsisten Top10</th>
        </tr>
      </thead>
      <tbody id="tbody"></tbody>
    </table>
  </div>
  <div class="pager">
    <button id="prev-page">‹ Prev</button>
    <span id="page-info" style="align-self:center;color:var(--muted);font-size:0.82rem;"></span>
    <button id="next-page">Next ›</button>
  </div>

  <div class="panel" id="panduan" style="margin-top:18px;">
    <h2>📖 Panduan Screen &amp; Istilah</h2>
    <p style="font-size:0.85rem;color:#475569;margin-top:0;">Klik tiap judul untuk buka penjelasannya — apa artinya, kenapa dipakai, dan biasanya muncul di kondisi seperti apa.</p>

    <details class="guide-item">
      <summary>🚀 Breakout Momentum</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Saham yang harganya menembus (breakout) level harga tertinggi dalam 20 hari terakhir, DAN volume hari itu minimal 1.5x lipat rata-rata volume 20 hari.</p>
        <p><b>Kenapa dipakai:</b> Breakout yang disertai volume tinggi biasanya menandakan ada tekanan beli baru yang cukup kuat (bisa dari investor besar, berita, atau sentimen positif) — ini sering jadi awal dari pergerakan harga yang lebih besar.</p>
        <p><b>Kapan biasanya terjadi:</b> Setelah saham bergerak sideways/konsolidasi cukup lama di rentang harga tertentu, lalu tiba-tiba ada katalis yang mendorong harga menembus resistance dengan volume besar.</p>
        <p><b>Risiko:</b> Ada risiko "false breakout" (breakout palsu) — harga sempat tembus tapi turun lagi, terutama kalau volume pendukungnya tidak benar-benar besar atau kondisi market secara umum sedang lemah.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>📈 Golden Cross Uptrend</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Kondisi dimana Moving Average jangka pendek (MA20) berada di atas MA menengah (MA50), yang juga berada di atas MA jangka panjang (MA200) — dan harga saat ini di atas MA20. Susunan MA yang rapi dari pendek ke panjang ini menandakan struktur uptrend yang sehat.</p>
        <p><b>Kenapa dipakai:</b> Ini menyaring saham yang trennya benar-benar naik secara berkelanjutan (bukan cuma lonjakan satu-dua hari). Istilah "Golden Cross" sendiri klasik dipakai saat MA50 memotong ke atas MA200 pertama kali — sering dianggap sinyal bullish jangka menengah-panjang.</p>
        <p><b>Kapan biasanya terjadi:</b> Pada saham yang sudah dalam tren naik cukup lama dan konsisten, biasanya setelah periode akumulasi yang panjang.</p>
        <p><b>Catatan:</b> Sinyal berbasis MA itu sifatnya "lagging" (telat) karena dihitung dari rata-rata historis — jadi kamu kemungkinan besar tidak masuk di harga paling murah, tapi konfirmasi trennya lebih bisa diandalkan.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>🔄 Oversold Reversal</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Kombinasi RSI yang rendah (kondisi oversold/jenuh jual) DENGAN munculnya pola candlestick bullish reversal (Bullish Engulfing, Hammer/Pin Bar, dsb) di candle terakhir.</p>
        <p><b>Kenapa dipakai:</b> RSI rendah menandakan tekanan jual sudah cukup ekstrem, dan pola candle bullish memberi "konfirmasi visual" bahwa pembeli mulai masuk kembali — kombinasi ini sering dipakai untuk menangkap potensi pembalikan arah (rebound).</p>
        <p><b>Kapan biasanya terjadi:</b> Setelah penurunan harga yang cukup tajam atau panjang, ketika muncul tanda-tanda pembeli mulai masuk di harga bawah.</p>
        <p><b>Risiko:</b> Dikenal dengan istilah "menangkap pisau jatuh" (catching a falling knife) — saham oversold bisa saja terus turun lebih dalam kalau tren turunnya masih sangat kuat. Sebaiknya tunggu konfirmasi tambahan sebelum entry.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>✅ Strong Buy Semua Timeframe</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Saham yang mendapat rating "Strong Buy" secara bersamaan di ketiga timeframe: Daily, Mingguan, DAN Bulanan (dihitung dari gabungan sinyal Moving Average + indikator oscillator di tiap timeframe).</p>
        <p><b>Kenapa dipakai:</b> Kalau sinyal bullish-nya kompak di berbagai skala waktu (jangka pendek, menengah, dan panjang), itu menandakan momentum yang jauh lebih solid dibanding cuma bagus di satu timeframe saja.</p>
        <p><b>Kapan biasanya terjadi:</b> Cukup jarang — biasanya cuma saham-saham dengan tren naik yang sangat kuat dan sudah berlangsung lama di segala skala waktu.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>🕯️ Ada Pola Candle</summary>
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
      <summary>🏆 Likuid &amp; Konsisten Top10</summary>
      <div class="guide-body">
        <p><b>Apa itu:</b> Kombinasi dua filter: (1) nilai transaksi rata-rata 20 hari minimal Rp 5 Miliar/hari, dan (2) saham yang konsisten masuk ranking Top-10 skor selama minimal 3 dari 10 hari run terakhir.</p>
        <p><b>Kenapa dipakai:</b> Nilai transaksi tinggi = saham cukup likuid, gampang masuk/keluar posisi tanpa bikin harga bergerak sendiri (slippage kecil). Konsistensi Top-10 menyaring sinyal yang memang bertahan dari waktu ke waktu, bukan cuma breakout sesaat sehari yang belum tentu berlanjut.</p>
        <p><b>Kapan berguna:</b> Baru kelihatan hasilnya setelah kamu menjalankan script ini beberapa hari berturut-turut, karena histori ranking harian perlu terkumpul dulu.</p>
        <p><b>Catatan:</b> Karena butuh "konsisten beberapa hari", saham yang muncul di sini kadang sudah agak telat masuk fase awal pergerakannya — lebih cocok untuk konfirmasi tren yang sedang berjalan, bukan menangkap breakout paling awal.</p>
      </div>
    </details>

    <details class="guide-item">
      <summary>📊 Istilah Indikator (RSI, MACD, Stochastic, dll)</summary>
      <div class="guide-body">
        <p><b>RSI (Relative Strength Index):</b> Mengukur kecepatan & besar perubahan harga, skala 0-100. RSI di bawah 30 biasa dianggap "oversold" (jenuh jual, harga sudah turun banyak), di atas 70 dianggap "overbought" (jenuh beli).</p>
        <p><b>MACD:</b> Membandingkan dua rata-rata bergerak (12 &amp; 26 hari) untuk melihat arah &amp; kekuatan tren. Kalau garis MACD di atas garis sinyalnya, dianggap momentum naik.</p>
        <p><b>Stochastic:</b> Mirip RSI, membandingkan harga penutupan dengan rentang harga tertinggi-terendah dalam periode tertentu untuk mendeteksi jenuh beli/jual.</p>
        <p><b>CCI (Commodity Channel Index) &amp; Williams %R:</b> Indikator oscillator lain yang juga mendeteksi kondisi jenuh beli/jual dengan formula berbeda — dipakai sebagai "suara tambahan" selain RSI/Stochastic supaya sinyalnya lebih meyakinkan kalau beberapa indikator sepakat.</p>
        <p><b>Rating Strong Sell/Sell/Neutral/Buy/Strong Buy:</b> Dihitung dari perbandingan jumlah indikator yang kasih sinyal "beli" vs "jual" — makin banyak yang sepakat searah, makin kuat labelnya (Strong Buy/Strong Sell). Ini pendekatan kami sendiri, bukan rumus resmi dari provider manapun.</p>
        <p><b>Beta:</b> Mengukur seberapa volatil suatu saham dibanding IHSG. Beta &gt; 1 = secara historis bergerak lebih liar dari IHSG (naik/turunnya lebih besar), Beta &lt; 1 = lebih stabil/kalem dibanding IHSG.</p>
      </div>
    </details>
  </div>

<script>
const DATA = __DATA__;
const PAGE_SIZE = 25;
let page = 0;
let sortKey = "score";
let sortDir = -1;

const PRESETS = {
  breakout:  { weights:{trend:20,brk:50,pa:20,mom:10}, minScore:50, filters:{trend:false,breakout:true,pattern:false,allgreen:false} },
  golden:    { weights:{trend:60,brk:10,pa:10,mom:20}, minScore:55, filters:{trend:true,breakout:false,pattern:false,allgreen:false} },
  reversal:  { weights:{trend:10,brk:10,pa:40,mom:40}, minScore:35, filters:{trend:false,breakout:false,pattern:true,allgreen:false}, rsiMax:45 },
  allgreen:  { weights:{trend:25,brk:25,pa:25,mom:25}, minScore:0,  filters:{trend:false,breakout:false,pattern:false,allgreen:true} },
  pattern:   { weights:{trend:15,brk:15,pa:55,mom:15}, minScore:40, filters:{trend:false,breakout:false,pattern:true,allgreen:false} },
  quality:   { weights:{trend:30,brk:30,pa:25,mom:15}, minScore:40, filters:{trend:false,breakout:false,pattern:false,allgreen:false}, valMin:5, streakMin:3 },
  reset:     { weights:{trend:30,brk:30,pa:25,mom:15}, minScore:40, filters:{trend:false,breakout:false,pattern:false,allgreen:false} },
};

function fmtNum(n) { return n.toLocaleString('id-ID', {maximumFractionDigits:0}); }
function fmtValue(v) {
  if (v >= 1e12) return 'Rp ' + (v/1e12).toFixed(2) + ' T';
  if (v >= 1e9) return 'Rp ' + (v/1e9).toFixed(1) + ' M';
  if (v >= 1e6) return 'Rp ' + (v/1e6).toFixed(0) + ' Jt';
  return 'Rp ' + fmtNum(v);
}

function computeScore(row, w) {
  const totalW = w.trend + w.brk + w.pa + w.mom;
  if (totalW <= 0) return 0;
  return (row.trend*w.trend + row.brk*w.brk + row.pa*w.pa + row.mom*w.mom) / totalW;
}

function verdictClass(v) {
  if (v === "Strong Buy") return "sb";
  if (v === "Buy") return "b";
  if (v === "Strong Sell") return "ss";
  if (v === "Sell") return "s";
  return "n";
}

function verdictBadge(tfKey, tfData) {
  if (!tfData || !tfData[tfKey]) return '<span class="verdict n">-</span>';
  const d = tfData[tfKey];
  const cls = verdictClass(d.summary);
  const tip = `MA: ${d.ma} (${d.ma_detail}) | Indikator: ${d.ind} (${d.ind_detail})`;
  return `<span class="verdict ${cls}" title="${tip}">${d.summary}</span>`;
}

function isAllGreen(tfData) {
  if (!tfData || !tfData.daily || !tfData.weekly || !tfData.monthly) return false;
  return tfData.daily.summary === "Strong Buy" && tfData.weekly.summary === "Strong Buy" && tfData.monthly.summary === "Strong Buy";
}

function candleSvg(ohlc) {
  if (!ohlc || ohlc.length < 2) return '';
  const w = 130, h = 46, padX = 2, padY = 3;
  const highs = ohlc.map(c => c[1]), lows = ohlc.map(c => c[2]);
  const max = Math.max(...highs), min = Math.min(...lows);
  const range = (max - min) || 1;
  const n = ohlc.length;
  const slotW = (w - padX*2) / n;
  const bodyW = Math.max(1.2, slotW * 0.6);
  const yFor = v => h - padY - ((v - min) / range) * (h - padY*2);

  const parts = ohlc.map((c, i) => {
    const [o, hi, lo, cl] = c;
    const x = padX + i*slotW + slotW/2;
    const up = cl >= o;
    const color = up ? "#16a34a" : "#dc2626";
    const yHigh = yFor(hi), yLow = yFor(lo);
    const yOpen = yFor(o), yClose = yFor(cl);
    const bodyTop = Math.min(yOpen, yClose);
    const bodyH = Math.max(1, Math.abs(yClose - yOpen));
    return `<line x1="${x.toFixed(1)}" y1="${yHigh.toFixed(1)}" x2="${x.toFixed(1)}" y2="${yLow.toFixed(1)}" stroke="${color}" stroke-width="1"></line>
      <rect x="${(x-bodyW/2).toFixed(1)}" y="${bodyTop.toFixed(1)}" width="${bodyW.toFixed(1)}" height="${bodyH.toFixed(1)}" fill="${color}"></rect>`;
  }).join("");

  return `<svg class="spark" viewBox="0 0 ${w} ${h}" width="130" height="46">${parts}</svg>`;
}

function getWeights() {
  return {
    trend: +document.getElementById('w-trend').value,
    brk: +document.getElementById('w-brk').value,
    pa: +document.getElementById('w-pa').value,
    mom: +document.getElementById('w-mom').value,
  };
}

function applyPreset(name) {
  const p = PRESETS[name];
  if (!p) return;
  document.getElementById('w-trend').value = p.weights.trend;
  document.getElementById('w-brk').value = p.weights.brk;
  document.getElementById('w-pa').value = p.weights.pa;
  document.getElementById('w-mom').value = p.weights.mom;
  document.getElementById('w-trend-val').textContent = p.weights.trend;
  document.getElementById('w-brk-val').textContent = p.weights.brk;
  document.getElementById('w-pa-val').textContent = p.weights.pa;
  document.getElementById('w-mom-val').textContent = p.weights.mom;
  document.getElementById('min-score').value = p.minScore;
  document.getElementById('min-score-val').textContent = p.minScore;
  document.getElementById('f-trend').checked = p.filters.trend;
  document.getElementById('f-breakout').checked = p.filters.breakout;
  document.getElementById('f-pattern').checked = p.filters.pattern;
  document.getElementById('f-allgreen').checked = p.filters.allgreen;
  document.getElementById('rsi-max').value = p.rsiMax !== undefined ? p.rsiMax : '';
  document.getElementById('rsi-min').value = '';
  document.getElementById('price-min').value = '';
  document.getElementById('price-max').value = '';
  document.getElementById('val-min').value = p.valMin !== undefined ? p.valMin : '';
  document.getElementById('streak-min').value = p.streakMin !== undefined ? p.streakMin : '';
  document.getElementById('search').value = '';

  document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
  const btn = document.querySelector(`.preset-btn[data-preset="${name}"]`);
  if (btn && name !== 'reset') btn.classList.add('active');

  page = 0;
  render();
}

function render() {
  const w = getWeights();
  const minScore = +document.getElementById('min-score').value;
  const onlyTrend = document.getElementById('f-trend').checked;
  const onlyBreakout = document.getElementById('f-breakout').checked;
  const onlyPattern = document.getElementById('f-pattern').checked;
  const onlyAllGreen = document.getElementById('f-allgreen').checked;
  const q = document.getElementById('search').value.trim().toUpperCase();
  const priceMin = parseFloat(document.getElementById('price-min').value);
  const priceMax = parseFloat(document.getElementById('price-max').value);
  const rsiMin = parseFloat(document.getElementById('rsi-min').value);
  const rsiMax = parseFloat(document.getElementById('rsi-max').value);
  const valMin = parseFloat(document.getElementById('val-min').value);
  const streakMin = parseFloat(document.getElementById('streak-min').value);

  let rows = DATA.map(r => ({...r, score: computeScore(r, w)}));
  rows = rows.filter(r => r.score >= minScore);
  if (onlyTrend) rows = rows.filter(r => r.trendOk);
  if (onlyBreakout) rows = rows.filter(r => r.brkOk);
  if (onlyPattern) rows = rows.filter(r => r.pattern);
  if (onlyAllGreen) rows = rows.filter(r => isAllGreen(r.tf));
  if (!isNaN(priceMin)) rows = rows.filter(r => r.p >= priceMin);
  if (!isNaN(priceMax)) rows = rows.filter(r => r.p <= priceMax);
  if (!isNaN(rsiMin)) rows = rows.filter(r => r.rsi >= rsiMin);
  if (!isNaN(rsiMax)) rows = rows.filter(r => r.rsi <= rsiMax);
  if (!isNaN(valMin)) rows = rows.filter(r => r.val >= valMin * 1e9);
  if (!isNaN(streakMin)) rows = rows.filter(r => (r.cst && r.cst.streak || 0) >= streakMin);
  if (q) rows = rows.filter(r => r.t.toUpperCase().includes(q));

  rows.sort((a,b) => {
    let av = a[sortKey], bv = b[sortKey];
    if (typeof av === 'string') return sortDir * av.localeCompare(bv);
    return sortDir * ((av||0) - (bv||0));
  });

  document.getElementById('count-info').textContent =
    `${rows.length} saham cocok dengan kriteria saat ini (dari ${DATA.length} total)`;

  const totalPages = Math.max(1, Math.ceil(rows.length / PAGE_SIZE));
  if (page >= totalPages) page = totalPages - 1;
  if (page < 0) page = 0;
  const pageRows = rows.slice(page*PAGE_SIZE, page*PAGE_SIZE + PAGE_SIZE);

  const tbody = document.getElementById('tbody');
  tbody.innerHTML = pageRows.map(r => {
    const chgClass = r.chg >= 0 ? 'pos' : 'neg';
    const badges = [];
    if (r.trendOk) badges.push('<span class="badge trend">Uptrend</span>');
    if (r.brkOk) badges.push('<span class="badge breakout">Breakout</span>');
    if (r.pattern) badges.push(`<span class="badge pattern">${r.pattern}</span>`);
    const badgeHtml = badges.join(' ') || '<span class="muted">-</span>';
    const scoreRounded = r.score.toFixed(1);
    const cst = r.cst || {count:0,total:0,streak:0};
    const streakStrong = cst.streak >= 3;
    const cstHtml = cst.total > 0
      ? `<span style="${streakStrong ? 'color:#15803d;font-weight:700;' : 'color:#475569;'}" title="${cst.count} dari ${cst.total} hari run terakhir masuk Top-10">${cst.count}/${cst.total} hari (streak ${cst.streak})</span>`
      : '<span class="muted">- (run beberapa hari dulu)</span>';
    const betaHtml = (r.beta === null || r.beta === undefined) ? '<span class="muted">-</span>' : r.beta.toFixed(2);
    const sectorHtml = r.sector && r.sector !== '-' ? r.sector : '<span class="muted">-</span>';
    return `<tr>
      <td>${candleSvg(r.ohlc)}</td>
      <td class="tk">${r.t}</td>
      <td>${fmtNum(r.p)}</td>
      <td class="${chgClass}">${r.chg>=0?'+':''}${r.chg.toFixed(2)}%</td>
      <td>${sectorHtml}</td>
      <td>${fmtValue(r.val)}</td>
      <td><div class="score-bar"><div class="score-fill" style="width:${Math.min(100,scoreRounded)}%"></div><span>${scoreRounded}</span></div></td>
      <td>${badgeHtml}</td>
      <td>${r.rsi}</td>
      <td>${betaHtml}</td>
      <td>${verdictBadge('h1', r.tf)}</td>
      <td>${verdictBadge('h2', r.tf)}</td>
      <td>${verdictBadge('h4', r.tf)}</td>
      <td>${verdictBadge('daily', r.tf)}</td>
      <td>${verdictBadge('weekly', r.tf)}</td>
      <td>${verdictBadge('monthly', r.tf)}</td>
      <td>${cstHtml}</td>
    </tr>`;
  }).join('');

  document.getElementById('page-info').textContent = `Hal ${page+1} / ${totalPages}`;
  document.getElementById('prev-page').disabled = page <= 0;
  document.getElementById('next-page').disabled = page >= totalPages - 1;
}

document.querySelectorAll('.preset-btn').forEach(btn => {
  btn.addEventListener('click', () => applyPreset(btn.dataset.preset));
});

[['w-trend','w-trend-val'],['w-brk','w-brk-val'],['w-pa','w-pa-val'],['w-mom','w-mom-val']].forEach(([id,valId]) => {
  const el = document.getElementById(id);
  el.addEventListener('input', () => {
    document.getElementById(valId).textContent = el.value;
    document.querySelectorAll('.preset-btn').forEach(b => b.classList.remove('active'));
    page = 0; render();
  });
});
document.getElementById('min-score').addEventListener('input', function() {
  document.getElementById('min-score-val').textContent = this.value;
  page = 0; render();
});
['f-trend','f-breakout','f-pattern','f-allgreen'].forEach(id => {
  document.getElementById(id).addEventListener('change', () => { page = 0; render(); });
});
['price-min','price-max','rsi-min','rsi-max','val-min','streak-min'].forEach(id => {
  document.getElementById(id).addEventListener('input', () => { page = 0; render(); });
});
document.getElementById('search').addEventListener('input', () => { page = 0; render(); });
document.getElementById('prev-page').addEventListener('click', () => { page--; render(); });
document.getElementById('next-page').addEventListener('click', () => { page++; render(); });
document.querySelectorAll('thead th').forEach(th => {
  th.addEventListener('click', () => {
    const key = th.dataset.key;
    if (key.startsWith('_')) return;
    if (sortKey === key) { sortDir *= -1; } else { sortKey = key; sortDir = -1; }
    document.querySelectorAll('thead th').forEach(x => x.classList.remove('active'));
    th.classList.add('active');
    render();
  });
});

render();
</script>
</body>
</html>'''


if __name__ == "__main__":
    main()
