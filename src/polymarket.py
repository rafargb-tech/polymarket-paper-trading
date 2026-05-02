"""
polymarket.py — Cliente de la API de Polymarket
Detecta ventanas activas buscando por ID en el rango correcto.
"""

import json
import logging
import urllib.request
from datetime import datetime, timezone

from config import CONFIG, ASSET_MAP
from models import Window

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0"}

# Estado interno: último ID conocido con actividad
_last_known_id = {"val": 2134000}


def _fetch_market(id_val: int) -> dict | None:
    try:
        req = urllib.request.Request(
            f"https://gamma-api.polymarket.com/markets/{id_val}",
            headers=HEADERS,
        )
        with urllib.request.urlopen(req, timeout=3) as r:
            return json.loads(r.read())
    except:
        return None


def _parse_window(m: dict, now_ts: float) -> Window | None:
    """Convierte un market dict en Window si es válido y está activo/próximo."""
    q = m.get("question", "")
    if "Up or Down" not in q or m.get("closed"):
        return None

    asset = next(
        (a for a, v in ASSET_MAP.items() if v["pm_name"] in q), None
    )
    if asset not in CONFIG["assets"]:
        return None

    slug = m.get("slug", "")
    tf = "15m" if "15m" in slug else "5m"
    if tf not in CONFIG["timeframes"]:
        return None

    ts_str = slug.split("-")[-1]
    if not ts_str.isdigit():
        return None

    ts_start  = int(ts_str)
    duration  = 900 if tf == "15m" else 300
    ts_end    = ts_start + duration
    secs_left = ts_end - now_ts
    secs_elapsed = now_ts - ts_start

    # Solo ventanas en curso o que empiezan en los próximos 2 minutos
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


def fetch_active_windows() -> dict[str, Window]:
    """
    Detecta ventanas Up/Down activas en Polymarket.

    Estrategia: busca por ID en el rango donde están los mercados de hoy.
    El endpoint de listing general (/markets?limit=300) solo devuelve
    mercados futuros precargados, no los activos del momento.
    """
    now_ts  = datetime.now(timezone.utc).timestamp()
    windows = {}

    # ── Paso 1: scan rápido hacia adelante desde último ID conocido ──
    # Los mercados se crean ~1min antes de cada ventana, por lo que
    # los IDs activos están siempre cerca del último conocido
    base = _last_known_id["val"]
    scan_range = range(max(base - 200, 2080000), base + 500, 3)

    for id_val in scan_range:
        m = _fetch_market(id_val)
        if not m:
            continue
        w = _parse_window(m, now_ts)
        if w:
            windows[w.key] = w
            # Actualizar el último ID conocido con actividad
            if id_val > _last_known_id["val"]:
                _last_known_id["val"] = id_val

    # ── Paso 2: si no encontramos nada, hacer scan más amplio ────────
    if not windows:
        log.info("[API] Scan amplio buscando ventanas activas...")
        for id_val in range(base + 500, base + 2000, 5):
            m = _fetch_market(id_val)
            if not m:
                continue
            q = m.get("question", "")
            if "Up or Down" in q:
                if id_val > _last_known_id["val"]:
                    _last_known_id["val"] = id_val
            w = _parse_window(m, now_ts)
            if w:
                windows[w.key] = w

    if windows:
        log.info(f"[API] {len(windows)} ventana(s) activa(s) detectadas")
    
    return windows
