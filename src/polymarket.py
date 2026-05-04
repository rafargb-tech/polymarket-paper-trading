"""
polymarket.py — Cliente de la API de Polymarket
Detecta ventanas activas con autodescubrimiento de ID y manejo de gaps nocturnos.
"""

import json
import logging
import time
import urllib.request
from datetime import datetime, timezone

from config import CONFIG, ASSET_MAP
from models import Window

log = logging.getLogger(__name__)
HEADERS = {"User-Agent": "Mozilla/5.0"}

# ID base autodescubierto en runtime (se actualiza continuamente)
_state = {"last_known_id": None, "last_discovery": 0.0}

LISTING_URL = (
    "https://gamma-api.polymarket.com/markets"
    "?limit=300&order=id&ascending=false"
)


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


def _discover_base_id() -> int:
    """
    Descubre el ID más alto actual de mercados Up/Down vía el listing general.
    Usa esto como punto de partida para el scan de ventanas activas.
    """
    try:
        req = urllib.request.Request(LISTING_URL, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=8) as r:
            markets = json.loads(r.read())
        updown_ids = [
            int(m.get("id", 0))
            for m in markets
            if "Up or Down" in m.get("question", "")
        ]
        if updown_ids:
            max_id = max(updown_ids)
            log.info(f"[API] ID base descubierto: {max_id}")
            return max_id
    except Exception as e:
        log.warning(f"[API] Error en autodescubrimiento: {e}")
    return 2155000  # fallback conservador


def _parse_window(m: dict, now_ts: float) -> Window | None:
    """Convierte un market dict en Window si está activo o próximo."""
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


def is_market_hours() -> bool:
    """
    Estima si Polymarket tiene ventanas activas ahora.
    Basado en datos empíricos: opera ~9:30 AM – 4:00 PM ET (13:30–20:00 UTC)
    de lunes a viernes. Fuera de ese horario el bot espera sin hacer scans.
    """
    now = datetime.now(timezone.utc)
    # Fin de semana completo: no hay mercado
    if now.weekday() >= 5:
        return False
    # Horario UTC: 13:30 – 20:30 (margen de 30min extra por si acaso)
    now_min = now.hour * 60 + now.minute
    return 13 * 60 + 25 <= now_min <= 20 * 60 + 30


def mins_to_market_open() -> float:
    """Minutos hasta la próxima apertura estimada del mercado."""
    from datetime import timedelta
    now = datetime.now(timezone.utc)
    # Próxima apertura: 13:30 UTC del siguiente día hábil
    candidate = now.replace(hour=13, minute=30, second=0, microsecond=0)
    if candidate <= now:
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return (candidate - now).total_seconds() / 60


def fetch_active_windows() -> dict[str, Window]:
    """
    Detecta ventanas Up/Down activas.
    - Fuera de horario: retorna vacío sin hacer requests innecesarios.
    - En horario: autodescubre el ID base y hace scan en el rango correcto.
    """
    now_ts = datetime.now(timezone.utc).timestamp()

    # Fuera de horario: no gastar requests de API
    if not is_market_hours():
        return {}

    # Autodescubrir ID base cada 10 minutos o al arrancar
    if (
        _state["last_known_id"] is None
        or now_ts - _state["last_discovery"] > 600
    ):
        _state["last_known_id"] = _discover_base_id()
        _state["last_discovery"] = now_ts

    base    = _state["last_known_id"]
    windows = {}

    # ── Scan normal: ±300 IDs desde el último conocido ───────────────
    for id_val in range(max(base - 300, 2080000), base + 100, 3):
        m = _fetch_market(id_val)
        if not m:
            continue
        # Actualizar ID base si encontramos algo más reciente
        if "Up or Down" in m.get("question", ""):
            mid = int(m.get("id", 0))
            if mid > _state["last_known_id"]:
                _state["last_known_id"] = mid
        w = _parse_window(m, now_ts)
        if w:
            windows[w.key] = w
        time.sleep(0.02)

    # ── Si no encontramos nada, scan amplio hacia adelante ───────────
    if not windows:
        log.info("[API] Scan amplio buscando ventanas activas...")
        for id_val in range(base + 100, base + 3000, 5):
            m = _fetch_market(id_val)
            if not m:
                continue
            if "Up or Down" in m.get("question", ""):
                mid = int(m.get("id", 0))
                if mid > _state["last_known_id"]:
                    _state["last_known_id"] = mid
            w = _parse_window(m, now_ts)
            if w:
                windows[w.key] = w
            time.sleep(0.02)
            if len(windows) >= 3:
                break

    if windows:
        log.info(f"[API] {len(windows)} ventana(s) activa(s) detectadas")

    return windows
