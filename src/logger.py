"""
logger.py — Persistencia de trades en CSV y configuración de logging
"""

import csv
import logging
import os
import sys

from config import CONFIG
from models import Trade


def setup_logging():
    os.makedirs(os.path.dirname(CONFIG["log_monitor"]), exist_ok=True)
    fmt = "%(asctime)s %(message)s"
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt="%H:%M:%S",
        handlers=[
            logging.FileHandler(CONFIG["log_monitor"], encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )


def save_trade(trade: Trade):
    """Agrega una operación al CSV de paper trades."""
    os.makedirs(os.path.dirname(CONFIG["log_trades"]), exist_ok=True)
    path       = CONFIG["log_trades"]
    file_exists = os.path.exists(path)
    row        = trade.to_dict()

    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=row.keys())
        if not file_exists:
            writer.writeheader()
        writer.writerow(row)


def print_summary(state):
    """Imprime resumen final al detener el bot."""
    print("\n" + "=" * 62)
    print("  RESUMEN FINAL — PAPER TRADING")
    print("=" * 62)
    print(f"  {state.summary()}")
    print(f"  Log trades  : {CONFIG['log_trades']}")
    print(f"  Log monitor : {CONFIG['log_monitor']}")
    print("=" * 62)

    resolved = [t for t in state.trades if t.result != "pending"]
    if resolved:
        print("\n  Últimas operaciones:")
        for t in resolved[-20:]:
            pnl = f"{t.pnl_net:+.2f}" if t.pnl_net else "---"
            print(
                f"    {t.ts} | {t.asset} {t.tf} {t.direction:<4} "
                f"@ {t.odds_entry:.3f} | edge={t.edge_pct:.1f}% | "
                f"{t.result:<4} | PnL={pnl}"
            )
