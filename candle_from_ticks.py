import sqlite3
from datetime import timedelta
from zoneinfo import ZoneInfo

import mplfinance as mpf
import pandas as pd

# CONFIG
DB_PATH = "market_data.db"
TOKEN = "17939"
TIMEFRAME_MINUTES = 1  # 1, 2, 5, 15, etc.
NUM_CANDLES = 40  # Number of latest candles to show

IST = ZoneInfo("Asia/Kolkata")


# Connect to DB
conn = sqlite3.connect(DB_PATH)

# Get last tick timestamp
last_ts = conn.execute(
    "SELECT MAX(exchange_timestamp) FROM market_ticks WHERE token = ?", (TOKEN,)
).fetchone()[0]

if last_ts is None:
    raise ValueError(f"No tick data found for token {TOKEN}")

# Detect if timestamps are in milliseconds
use_millis = last_ts > 1e12
last_ts_seconds = last_ts // 1000 if use_millis else last_ts

# Calculate start and end times
end_time = pd.to_datetime(last_ts_seconds, unit="s").tz_localize("UTC").tz_convert(IST)
start_time = end_time - timedelta(minutes=TIMEFRAME_MINUTES * NUM_CANDLES)

start_ts = (
    int(start_time.timestamp() * 1000) if use_millis else int(start_time.timestamp())
)
end_ts_db = (
    int(end_time.timestamp() * 1000) if use_millis else int(end_time.timestamp())
)

# Fetch tick data
query = """
SELECT exchange_timestamp, ltp, volume
FROM market_ticks
WHERE token = ?
  AND exchange_timestamp BETWEEN ? AND ?
ORDER BY exchange_timestamp
"""
df = pd.read_sql(query, conn, params=(TOKEN, start_ts, end_ts_db))
conn.close()

if df.empty:
    raise ValueError("No ticks found in the requested time range.")

# Convert timestamp to datetime in IST
if use_millis:
    df["exchange_timestamp"] = df["exchange_timestamp"] // 1000
df["datetime"] = (
    pd.to_datetime(df["exchange_timestamp"], unit="s")
    .dt.tz_localize("UTC")
    .dt.tz_convert(IST)
)
df.set_index("datetime", inplace=True)

# Ensure chronological order
df.sort_index(inplace=True)

# Resample ticks → candles
timeframe_str = f"{TIMEFRAME_MINUTES}min"
candles = df.resample(timeframe_str).agg(
    {"ltp": ["first", "max", "min", "last"], "volume": "sum"}
)
candles.columns = ["Open", "High", "Low", "Close", "Volume"]
candles.dropna(inplace=True)

# Keep only the latest NUM_CANDLES
candles = candles.tail(NUM_CANDLES)
mc = mpf.make_marketcolors(
    up="#26a69a",  # nice teal/green for bullish
    down="#ef5350",  # soft red for bearish
    edge="inherit",  # edge same as body
    wick="black",  # black wicks for clarity
    volume="inherit",  # volume bar same color as candle
)

s = mpf.make_mpf_style(
    marketcolors=mc,
    gridstyle="--",  # dashed grid for subtlety
    gridcolor="lightgray",
    y_on_right=False,
    facecolor="white",
    figcolor="white",  # background of figure
)

# Plot improved candlestick chart
mpf.plot(
    candles,
    type="candle",
    volume=True,
    style=s,
    title=f"\n{TOKEN} - Latest {NUM_CANDLES} {TIMEFRAME_MINUTES}min Candles (IST)",
    ylabel="Price (INR)",
    ylabel_lower="Volume",
    datetime_format="%H:%M",
    tight_layout=True,
    figsize=(12, 6),
    show_nontrading=False,
)
