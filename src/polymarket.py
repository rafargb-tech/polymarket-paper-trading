"""
polymarket.py — Cliente de la API de Polymarket (Gamma + CLOB)
"""

import json
import logging
import urllib.request
from datetime import datetime, timezone

from config import CONFIG, ASSET_MAP
from models import Window

log = logging.getLogger(__name__)

GAMMA_URL = "https://gamma-api.polymarket.com/markets?limit=300&order=id&ascending=false"
HEADERS   = {"User-Agent": "Mozilla/5.0"}


def fetch_active_windows() -> dict[str, Window]:
    """
    Consulta Polymarket y devuelve las ventanas Up/Down activas
    o próximas a activarse (próximos 2 minutos).
    """
    try:
        req = urllib.request.Request(GAMMA_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            markets = json.loads(r.read())
    except Exception as e:
        log.warning(f"[API] Error fetching markets: {e}")
        return {}

    now_ts  = datetime.now(timezone.utc).timestamp()
    windows = {}

    for m in markets:
        q = m.get("question", "")
        if "Up or Down" not in q or m.get("closed"):
            continue

        # Identificar asset
        asset = next(
            (a for a, v in ASSET_MAP.items() if v["pm_name"] in q), None
        )
        if asset not in CONFIG["assets"]:
            continue

        # Identificar timeframe
        slug = m.get("slug", "")
        tf   = "15m" if "15m" in slug else "5m"
        if tf not in CONFIG["timeframes"]:
            continue

        # Timestamps desde el slug
        ts_str = slug.split("-")[-1]
        if not ts_str.isdigit():
            continue

        ts_start     = int(ts_str)
        duration     = 900 if tf == "15m" else 300
        ts_end       = ts_start + duration
        secs_left    = ts_end - now_ts
        secs_elapsed = now_ts - ts_start

        # Solo ventanas en curso o que empiezan en los próximos 2 minutos
        if secs_left < 0 or secs_elapsed < -120:
            continue

        # Odds actuales
        try:
            op        = json.loads(m.get("outcomePrices", '["0.5","0.5"]'))
            odds_up   = float(op[0])
            odds_down = float(op[1])
        except:
            odds_up = odds_down = 0.5

        # Token IDs (para ejecución futura en Fase 2)
        try:
            ids       = json.loads(m.get("clobTokenIds", "[]"))
            token_up  = ids[0] if len(ids) > 0 else ""
            token_dn  = ids[1] if len(ids) > 1 else ""
        except:
            token_up = token_dn = ""

        key = f"{asset}_{tf}_{ts_start}"
        windows[key] = Window(
            key=key,
            market_id=str(m.get("id", "")),
            asset=asset,
            tf=tf,
            question=q,
            ts_start=ts_start,
            ts_end=ts_end,
            odds_up=odds_up,
            odds_down=odds_down,
            token_up=token_up,
            token_down=token_dn,
        )

    return windows
