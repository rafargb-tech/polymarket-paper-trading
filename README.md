# Polymarket Paper Trading Bot

Bot de **paper trading** (simulación sin capital real) para mercados Up/Down de Polymarket en BTC, ETH y SOL.

**Fase 1 — Validación estadística**: el bot monitorea, detecta señales y loguea resultados simulados. El objetivo es acumular datos suficientes para decidir si hay edge real antes de arriesgar capital.

---

## Estrategia: Oracle Lag Detection

Polymarket resuelve cada ventana usando el oracle de **Chainlink**, que actualiza el precio con un lag de 10–30 segundos. Si el precio spot en Bybit ya se movió significativamente pero las odds de Polymarket aún no lo reflejan, puede existir una ventaja temporal.

**Lógica del bot:**
1. Monitorea precio spot en tiempo real (Bybit WebSocket, latencia ~50ms)
2. Cada 20s consulta odds actuales de ventanas Up/Down en Polymarket
3. Calcula el retorno parcial observable desde el inicio de la ventana
4. Estima P(Up final) usando calibración empírica de 2,689 ventanas históricas
5. Si `P(Up empírica) - odds_polymarket > 3%` → simula entrada como **maker** (fee = 0)
6. Registra resultado al cierre de la ventana

---

## Estructura del proyecto

```
polymarket_bot/
├── src/
│   ├── bot.py          # Loop principal
│   ├── config.py       # Configuración y calibración
│   ├── feed.py         # Feed de precios Bybit WebSocket
│   ├── models.py       # Estructuras de datos
│   ├── polymarket.py   # Cliente API Polymarket
│   ├── strategy.py     # Motor de decisión y liquidación
│   └── logger.py       # Logging y persistencia CSV
├── logs/               # Generado automáticamente
│   ├── paper_trades.csv
│   └── monitor.log
├── .github/
│   └── workflows/
│       └── bot.yml     # GitHub Actions (corre en la nube)
├── requirements.txt
└── README.md
```

---

## Opción A: Correr en GitHub Actions (sin máquina local)

El bot corre automáticamente en la nube cada vez que haces push o de forma programada.

### Setup (una sola vez)

1. **Fork o sube este repositorio a GitHub**

2. **Activar GitHub Actions**: ve a tu repo → pestaña `Actions` → habilitar workflows

3. **Listo.** El workflow se activa automáticamente:
   - En cada `git push` a `main`
   - Cada día a las 13:25 UTC (9:25 AM ET)
   - Manualmente desde `Actions → Run workflow`

### Ver resultados

- Ve a `Actions` → selecciona el run más reciente
- Al final del job verás los logs en tiempo real
- Descarga el artifact `paper-trades-XXXX` para obtener el CSV

### Límite de GitHub Actions

GitHub Actions tiene un límite de **6 horas por job** en cuentas gratuitas. El workflow está configurado para reiniciarse automáticamente cada día y acumular el historial en artifacts.

---

## Opción B: Correr en tu máquina local

### Requisitos

- Python 3.10 o superior
- Conexión a internet

### Instalación

```bash
# Clonar el repositorio
git clone https://github.com/tu-usuario/polymarket-bot.git
cd polymarket-bot

# Instalar dependencias
pip install -r requirements.txt
```

### Ejecución

```bash
cd src
python3 bot.py
```

Para correrlo en segundo plano (Mac/Linux):
```bash
nohup python3 src/bot.py > logs/nohup.log 2>&1 &
```

Para detenerlo:
```bash
# Ctrl+C si está en primer plano
# O buscar el proceso:
pkill -f bot.py
```

---

## Archivos generados

| Archivo | Contenido |
|---------|-----------|
| `logs/paper_trades.csv` | Cada operación simulada: asset, dirección, odds, edge, resultado, PnL |
| `logs/monitor.log` | Log completo de todo lo que ve el bot |

### Columnas del CSV

| Columna | Descripción |
|---------|-------------|
| `ts` | Timestamp de la entrada |
| `asset` | BTC / ETH / SOL |
| `tf` | Timeframe: 5m o 15m |
| `direction` | Up o Down |
| `odds_entry` | Precio de la posición en el momento de entrada (0–1) |
| `edge_pct` | Ventaja estimada en % |
| `price_spot` | Precio spot al entrar |
| `price_open` | Precio al inicio de la ventana |
| `partial_ret_pct` | Retorno parcial observable (%) |
| `secs_to_close` | Segundos restantes al cierre cuando se entró |
| `size_usdc` | USDC simulados |
| `result` | Win / Loss / pending |
| `pnl_net` | PnL neto en USDC (después de fees) |

---

## Parámetros configurables

Edita `src/config.py`:

```python
CONFIG = {
    "assets":               ["BTC", "ETH", "SOL"],
    "timeframes":           ["5m", "15m"],
    "min_edge_pct":         3.0,    # Edge mínimo para entrar (%)
    "entry_window_start":   90,     # Entrar en los últimos 90s
    "entry_window_end":     15,     # Pero no en los últimos 15s
    "simulated_size":       10.0,   # USDC simulados por operación
}
```

---

## Criterio de evaluación (2 semanas de datos)

| Win rate | Interpretación | Acción |
|----------|---------------|--------|
| > 55% con N > 30 trades | Señal real | Pasar a Fase 2 con $50 reales |
| 50–55% | Señal marginal | Esperar más datos |
| < 50% | Sin edge | No escalar |

---

## Contexto metodológico

Este bot es **Fase 1** de un proceso de validación rigurosa:

- **Fase 1** (actual): paper trading 2 semanas → validar win rate
- **Fase 2**: capital mínimo ($50–100) → validar que el edge sobrevive en producción
- **Fase 3**: escalar solo si Fase 2 confirma resultados

La calibración empírica en `config.py` está basada en un backtest real sobre 120,960 velas de 1 minuto de BTC/ETH/SOL (Binance.US, abril 2026). **No es garantía de resultados futuros.**
