"""
models.py — Estructuras de datos del bot
"""

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class Window:
    """Representa una ventana Up/Down activa en Polymarket."""
    key:        str
    market_id:  str
    asset:      str
    tf:         str
    question:   str
    ts_start:   int
    ts_end:     int
    odds_up:    float
    odds_down:  float
    token_up:   str
    token_down: str
    price_open: Optional[float] = None


@dataclass
class Trade:
    """Representa una operación simulada (paper trade)."""
    ts:              str
    asset:           str
    tf:              str
    direction:       str
    odds_entry:      float
    edge_pct:        float
    price_spot:      float
    price_open:      float
    partial_ret_pct: float
    secs_to_close:   int
    size_usdc:       float
    result:          str   = "pending"
    pnl_gross:       float = 0.0
    pnl_net:         float = 0.0
    notes:           str   = ""

    def to_dict(self):
        return asdict(self)


class BotState:
    """Estado global del bot — precios, ventanas activas y estadísticas."""

    def __init__(self):
        self.prices:    dict[str, float]  = {}
        self.windows:   dict[str, Window] = {}
        self.trades:    list[Trade]       = []
        self.pending:   dict[str, tuple[Trade, Window]] = {}
        self.done_keys: set[str]          = set()
        self.wins    = 0
        self.losses  = 0
        self.pnl     = 0.0
        self.signals = 0
        self.monitored = 0

    @property
    def win_rate(self) -> float:
        total = self.wins + self.losses
        return self.wins / total if total else 0.0

    @property
    def total_trades(self) -> int:
        return self.wins + self.losses

    def summary(self) -> str:
        return (
            f"Ventanas={self.monitored} | Señales={self.signals} | "
            f"Trades={self.total_trades} | WR={self.win_rate*100:.0f}% "
            f"({self.wins}W/{self.losses}L) | PnL={self.pnl:+.2f} USDC"
        )
