"""
strategy.py — Motor de decisión: detección de edge y liquidación de trades
"""

import logging
from typing import Optional

from config import CONFIG, p_up_from_return
from models import BotState, Trade, Window

log = logging.getLogger(__name__)


def evaluate_signal(
    window: Window,
    spot: float,
) -> tuple[Optional[str], float, float]:
    # No operar si las odds son extremas: el mercado ya incorporó información
    # que nosotros no tenemos (oracle ya actualizó, o ventana casi resuelta)
    ODDS_MIN = 0.10   # No entrar si odds < 10% (mercado casi seguro de Down)
    ODDS_MAX = 0.90   # No entrar si odds > 90% (mercado casi seguro de Up)
    if window.odds_up < ODDS_MIN or window.odds_up > ODDS_MAX:
        return None, 0.0, 0.5
    """
    Compara la probabilidad empírica de Up contra las odds actuales de Polymarket.

    Retorna (dirección, edge_pct, odds_entrada):
      - dirección  : "Up", "Down", o None si no hay edge suficiente
      - edge_pct   : ventaja estimada en puntos porcentuales
      - odds_entrada: precio de la posición recomendada (0–1)

    Lógica de oracle lag:
      Si el precio spot ya reflejó un movimiento que el oracle de Chainlink
      aún no procesó, las odds de Polymarket pueden estar desactualizadas.
      Comparamos P(Up) empírica (calibrada con backtest) vs odds actuales.
    """
    if window.price_open is None or spot <= 0:
        return None, 0.0, 0.5

    partial_return = (spot - window.price_open) / window.price_open
    p_up_emp       = p_up_from_return(partial_return)

    edge_up   = p_up_emp - window.odds_up
    edge_down = (1 - p_up_emp) - window.odds_down
    min_edge  = CONFIG["min_edge_pct"] / 100

    if edge_up >= edge_down and edge_up >= min_edge:
        return "Up",   round(edge_up * 100, 2),   window.odds_up
    if edge_down > edge_up and edge_down >= min_edge:
        return "Down", round(edge_down * 100, 2), window.odds_down
    return None, 0.0, 0.5


def open_trade(
    state: BotState,
    window: Window,
    spot: float,
    direction: str,
    edge_pct: float,
    odds_entry: float,
    secs_left: float,
    secs_elapsed: float,
) -> Trade:
    """Registra una nueva operación simulada en el estado del bot."""
    from datetime import datetime, timezone

    partial_ret = (spot - window.price_open) / window.price_open * 100

    trade = Trade(
        ts=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        asset=window.asset,
        tf=window.tf,
        direction=direction,
        odds_entry=odds_entry,
        edge_pct=edge_pct,
        price_spot=spot,
        price_open=window.price_open,
        partial_ret_pct=round(partial_ret, 4),
        secs_to_close=int(secs_left),
        size_usdc=CONFIG["simulated_size"],
        notes=f"elapsed={int(secs_elapsed)}s|oracle_lag",
    )

    state.trades.append(trade)
    state.done_keys.add(window.key)
    state.pending[window.key] = (trade, window)
    state.signals += 1

    log.info(
        f"[SEÑAL ★] {window.asset} {window.tf} → {direction.upper()} "
        f"@ {odds_entry:.3f} | Edge={edge_pct:.1f}% | "
        f"Ret={partial_ret:+.3f}% | Faltan {int(secs_left)}s"
    )
    return trade


def settle_trade(
    state: BotState,
    trade: Trade,
    window: Window,
    final_price: float,
):
    """Cierra una operación simulada y registra el resultado."""
    resolution = "Up" if final_price >= window.price_open else "Down"
    win        = trade.direction == resolution

    trade.result    = "Win" if win else "Loss"
    size            = trade.size_usdc
    gross           = size * (1.0 / trade.odds_entry - 1.0) if win else -size
    fee             = size * CONFIG["maker_fee"]
    trade.pnl_gross = round(gross, 4)
    trade.pnl_net   = round(gross - fee, 4)

    if win:
        state.wins += 1
    else:
        state.losses += 1
    state.pnl += trade.pnl_net

    icon = "✓ WIN " if win else "✗ LOSS"
    log.info(
        f"[RESULT] {icon} | {trade.asset} {trade.tf} {trade.direction:<4} "
        f"@ {trade.odds_entry:.3f} | PnL={trade.pnl_net:+.2f} | "
        f"Acum={state.pnl:+.2f} | {state.summary()}"
    )
