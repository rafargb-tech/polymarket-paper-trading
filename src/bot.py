"""
bot.py — Loop principal del monitor
"""

import asyncio
import logging
import sys
import os

# Permite importar desde src/ tanto local como desde raíz
sys.path.insert(0, os.path.dirname(__file__))

from config import CONFIG
from models import BotState
from feed import price_feed
from polymarket import fetch_active_windows
from strategy import evaluate_signal, open_trade, settle_trade
from logger import setup_logging, save_trade, print_summary

log = logging.getLogger(__name__)


async def monitor_loop(state: BotState):
    last_poll      = 0.0
    last_status_ts = 0.0

    log.info("=" * 62)
    log.info("  POLYMARKET PAPER TRADING BOT — FASE 1 (simulación)")
    log.info(f"  Assets   : {CONFIG['assets']}")
    log.info(f"  TF       : {CONFIG['timeframes']}")
    log.info(f"  Edge mín : {CONFIG['min_edge_pct']}%")
    log.info(f"  Tamaño   : ${CONFIG['simulated_size']} USDC simulados")
    log.info("=" * 62)

    await asyncio.sleep(2)  # Esperar primer tick del WebSocket

    while True:
        import time
        from datetime import datetime, timezone

        now_ts = time.time()

        # ── Actualizar ventanas de Polymarket ────────────────────
        if now_ts - last_poll > CONFIG["polymarket_poll_secs"]:
            new_windows = fetch_active_windows()

            for key, w in new_windows.items():
                if key not in state.windows:
                    spot = state.prices.get(w.asset)
                    if spot:
                        w.price_open = spot
                        from datetime import datetime, timezone
                        end_str = datetime.fromtimestamp(
                            w.ts_end, tz=timezone.utc
                        ).strftime("%H:%M")
                        log.info(
                            f"[VENTANA] {w.asset} {w.tf} → cierra {end_str} UTC | "
                            f"Open=${spot:,.2f} | OddsUp={w.odds_up:.3f}"
                        )
                        state.monitored += 1

            state.windows = new_windows
            last_poll = now_ts

        # ── Evaluar cada ventana ─────────────────────────────────
        for key, w in list(state.windows.items()):
            secs_left    = w.ts_end - now_ts
            secs_elapsed = now_ts - w.ts_start
            spot         = state.prices.get(w.asset)

            # Ventana vencida: liquidar si hay trade pendiente
            if secs_left < -10:
                if key in state.pending:
                    trade, pw = state.pending.pop(key)
                    if spot and pw.price_open:
                        settle_trade(state, trade, pw, spot)
                        save_trade(trade)
                del state.windows[key]
                continue

            if not spot or w.price_open is None:
                continue

            partial_ret = (spot - w.price_open) / w.price_open * 100
            direction, edge_pct, odds_entry = evaluate_signal(w, spot)

            in_entry = (
                CONFIG["entry_window_end"]
                < secs_left
                < CONFIG["entry_window_start"]
            )

            # ── Entrada ──────────────────────────────────────────
            if direction and in_entry and key not in state.done_keys:
                open_trade(
                    state, w, spot, direction,
                    edge_pct, odds_entry, secs_left, secs_elapsed,
                )

            # ── Log de estado de ventana en curso ─────────────────
            elif direction and not in_entry and secs_left > 10:
                if int(secs_elapsed) % 30 < 5:
                    log.info(
                        f"  [{w.asset} {w.tf}] ${spot:,.2f} | "
                        f"ret={partial_ret:+.3f}% | OddsUp={w.odds_up:.3f} | "
                        f"→{direction} edge={edge_pct:.1f}% | {int(secs_left)}s"
                    )
            elif not direction and int(secs_elapsed) % 60 < 5 and secs_left > 30:
                log.info(
                    f"  [{w.asset} {w.tf}] ${spot:,.2f} | "
                    f"ret={partial_ret:+.3f}% | OddsUp={w.odds_up:.3f} | "
                    f"sin señal | {int(secs_left)}s"
                )

        # ── Status cada minuto ───────────────────────────────────
        if now_ts - last_status_ts > 60:
            px = " | ".join(
                f"{a}=${state.prices[a]:,.2f}"
                for a in CONFIG["assets"]
                if a in state.prices
            )
            log.info(f"[STATUS] {px} | {state.summary()}")
            last_status_ts = now_ts

        await asyncio.sleep(5)


async def main():
    setup_logging()
    state = BotState()
    try:
        await asyncio.gather(
            price_feed(state),
            monitor_loop(state),
        )
    except KeyboardInterrupt:
        log.info("Bot detenido (Ctrl+C)")
        print_summary(state)


if __name__ == "__main__":
    asyncio.run(main())
