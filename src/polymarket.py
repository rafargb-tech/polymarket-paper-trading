"""
polymarket.py — Cliente Polymarket con búsqueda directa por timestamp.

Lógica: los slugs tienen la forma asset-updown-5m-TIMESTAMP donde
TIMESTAMP es el Unix del inicio de la ventana (múltiplo de 300 o 900).
Calculamos los timestamps de las ventanas actuales y buscamos directamente
esos slugs — sin depender del listing general que solo tiene futuros.
"""

import json
import logging
import time
import urllib.request
from datetime import datetime, timezone, timedelta

from config import CONFIG, ASSET_MAP
from models import Window

log = logging.getLogger(__name__)
HEADERS     = {"User-Agent": "Mozilla/5.0"}
GAMMA_URL   = "https://gamma-api.polymarket.com/markets"

SLUG_PREFIX = {
    "BTC": "btc",
    "ETH": "eth",
    "SOL": "sol",
}


def _fetch_by_slug(slug: str) -> dict | None:
    try:
        url = f"{GAMMA_URL}?slug={slug}"
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=4) as r:
            data = json.loads(r.read())
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict) and data:
            return data
    except:
        pass
    return None


def _parse_window(m: dict, now_ts: float) -> Window | None:
    if not m or m.get("closed"):
        return None

    q     = m.get("question", "")
    slug  = m.get("slug", "")
    asset = next(
        (a for a, v in ASSET_MAP.items() if v["pm_name"] in q), None
    )
    if asset not in CONFIG["assets"]:
        return None

    tf = "15m" if "15m" in slug else "5m"
    if tf not in CONFIG["timeframes"]:
        return None

    ts_str = slug.split("-")[-1]
    if not ts_str.isdigit():
        return None

    ts_start     = int(ts_str)
    duration     = 900 if tf == "15m" else 300
    ts_end       = ts_start + duration
    secs_left    = ts_end - now_ts
    secs_elapsed = now_ts - ts_start

    if secs_left < 0 or secs_elapsed < -120:
        return None

    try:
        op        = json.loads(m.get("outcomePrices", '["0.5","0.5"]'))
        odds_up   = float(op[0])
        odds_down = float(op[1])
    except:
        odds_up = odds_down = 0.5

    try:
        ids      = json.loads(m.get("clobTokenIds", "[]"))
        token_up = ids[0] if len(ids) > 0 else ""
        token_dn = ids[1] if len(ids) > 1 else ""
    except:
        token_up = token_dn = ""

    key = f"{asset}_{tf}_{ts_start}"
    return Window(
        key=key,
        market_id=str(m.get("id", "")),
        asset=asset, tf=tf, question=q,
        ts_start=ts_start, ts_end=ts_end,
        odds_up=odds_up, odds_down=odds_down,
        token_up=token_up, token_down=token_dn,
    )


def _current_window_timestamps(now_ts: float) -> list[tuple[str, int]]:
    """
    Genera los slugs de las ventanas que DEBERÍAN estar activas ahora,
    calculando directamente desde el timestamp actual.
    Retorna lista de (asset, tf, ts_start).
    """
    candidates = []

    for asset, prefix in SLUG_PREFIX.items():
        for tf, duration in [("5m", 300), ("15m", 900)]:
            # Ventana actual: múltiplo de duration que cubre now_ts
            ts_start_now = int(now_ts // duration) * duration
            # También la ventana anterior (puede estar a punto de cerrar)
            ts_start_prev = ts_start_now - duration
            # Y la siguiente (puede estar a punto de abrir)
            ts_start_next = ts_start_now + duration

            for ts in [ts_start_prev, ts_start_now, ts_start_next]:
                slug = f"{prefix}-updown-{tf}-{ts}"
                candidates.append((slug, asset, tf, ts))

    return candidates


def fetch_active_windows() -> dict[str, Window]:
    """
    Busca ventanas activas construyendo slugs desde el timestamp actual.
    No depende del listing general — busca directamente por slug.
    """
    now_ts  = datetime.now(timezone.utc).timestamp()
    windows = {}

    candidates = _current_window_timestamps(now_ts)

    for slug, asset, tf, ts_start in candidates:
        m = _fetch_by_slug(slug)
        if not m:
            continue
        w = _parse_window(m, now_ts)
        if w:
            windows[w.key] = w
        time.sleep(0.05)

    if windows:
        log.info(f"[API] {len(windows)} ventana(s) activa(s) detectadas")

    return windows
