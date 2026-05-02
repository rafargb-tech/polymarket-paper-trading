"""
feed.py — Feed de precios en tiempo real via Bybit WebSocket
"""

import asyncio
import json
import logging
import time
import websockets

from config import ASSET_MAP
from models import BotState

log = logging.getLogger(__name__)


async def price_feed(state: BotState):
    """
    Mantiene conexión al WebSocket de Bybit y actualiza state.prices
    con el último precio de cada asset. Reconecta automáticamente.
    """
    symbols = [ASSET_MAP[a]["bybit"] for a in ASSET_MAP]
    uri     = "wss://stream.bybit.com/v5/public/spot"
    sub_msg = {
        "op":   "subscribe",
        "args": [f"tickers.{s}" for s in symbols],
    }

    while True:
        try:
            log.info(f"[WS] Conectando a Bybit WebSocket... {symbols}")
            async with websockets.connect(uri, ssl=True, ping_interval=20) as ws:
                await ws.send(json.dumps(sub_msg))
                log.info("[WS] ✓ Bybit conectado")

                async for raw in ws:
                    data  = json.loads(raw)
                    topic = data.get("topic", "")

                    if topic.startswith("tickers."):
                        symbol = topic.split(".")[1]
                        price  = float(data["data"].get("lastPrice", 0))
                        asset  = next(
                            (a for a, v in ASSET_MAP.items() if v["bybit"] == symbol),
                            None,
                        )
                        if asset and price > 0:
                            state.prices[asset] = price

        except Exception as e:
            log.warning(f"[WS] Desconectado: {e}. Reintentando en 5s...")
            await asyncio.sleep(5)
