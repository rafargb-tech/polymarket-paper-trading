"""
config.py — Configuración centralizada del bot
Modifica aquí sin tocar el resto del código.
"""

CONFIG = {
    # ── Assets y timeframes ──────────────────────────────────────
    "assets":     ["BTC", "ETH", "SOL"],
    "timeframes": ["5m", "15m"],

    # ── Parámetros de la estrategia ──────────────────────────────
    "min_edge_pct":         3.0,   # Edge mínimo para simular entrada (%)
    "entry_window_start":   90,    # Segundos antes del cierre: inicio de ventana de entrada
    "entry_window_end":     15,    # Segundos antes del cierre: fin de ventana de entrada
    "simulated_size":       10.0,  # USDC simulados por operación

    # ── Fees ─────────────────────────────────────────────────────
    "maker_fee":  0.000,   # Fee como maker (limit order) = 0
    "taker_fee":  0.0156,  # Fee máxima como taker en odds 50/50 (referencia)

    # ── Polling ──────────────────────────────────────────────────
    "polymarket_poll_secs": 20,    # Frecuencia de actualización de odds

    # ── Archivos de salida ───────────────────────────────────────
    "log_trades":  "../logs/paper_trades.csv",
    "log_monitor": "../logs/monitor.log",
}

# Mapeo de assets: nombre interno → nombre en Polymarket y símbolo en Bybit
ASSET_MAP = {
    "BTC": {"pm_name": "Bitcoin",  "bybit": "BTCUSDT"},
    "ETH": {"pm_name": "Ethereum", "bybit": "ETHUSDT"},
    "SOL": {"pm_name": "Solana",   "bybit": "SOLUSDT"},
}

# Calibración empírica: P(Up final) dado retorno parcial observable
# Fuente: backtest 2,689 ventanas × 3 assets, Binance.US 1min, abril 2026
# Formato: (umbral_retorno, P_up_si_retorno_<=_umbral)
CALIBRATION = [
    (-0.003, 0.01),   # retorno < -0.3%  → P(Up) = 1%
    (-0.001, 0.09),   # -0.3% a -0.1%   → P(Up) = 9%
    ( 0.000, 0.29),   # -0.1% a 0%      → P(Up) = 29%
    ( 0.001, 0.76),   # 0% a +0.1%      → P(Up) = 76%
    ( 0.003, 0.95),   # +0.1% a +0.3%   → P(Up) = 95%
    ( 9.999, 0.99),   # > +0.3%         → P(Up) = 99%
]

def p_up_from_return(partial_return: float) -> float:
    """Estima P(Up final) dado el retorno parcial observable en el momento de entrada."""
    for threshold, p in CALIBRATION:
        if partial_return <= threshold:
            return p
    return 0.99
