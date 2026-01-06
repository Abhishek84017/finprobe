from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np

def to_raw_numbers(d):
    """
    Convert numpy types to native Python numbers only
    """
    raw = {}

    for k, v in d.items():
        if isinstance(v, (np.integer,)):
            raw[k] = int(v)
        elif isinstance(v, (np.floating,)):
            raw[k] = float(v)
        else:
            raw[k] = v

    return raw

def calculate_intraday_indicators(raw_data):
    """
    raw_data: list[dict] or DataFrame
    """

    df = pd.DataFrame(raw_data)

    # ================== BASIC VALIDATION ==================
    if df.empty or len(df) < 10:
        return {
            "error": "Not enough raw data",
            "rows_available": len(df)
        }

    # ================== TIMESTAMP FIX (AUTO-DETECT UNIT) ==================
    ts = pd.to_numeric(df['exchange_timestamp'], errors='coerce').dropna()

    if ts.empty:
        return {"error": "Invalid exchange_timestamp data"}

    max_ts = ts.max()

    if max_ts > 10**18:        # nanoseconds
        df['timestamp'] = pd.to_datetime(df['exchange_timestamp'], unit='ns', errors='coerce')
    elif max_ts > 10**15:      # microseconds
        df['timestamp'] = pd.to_datetime(df['exchange_timestamp'], unit='us', errors='coerce')
    elif max_ts > 10**12:      # milliseconds
        df['timestamp'] = pd.to_datetime(df['exchange_timestamp'], unit='ms', errors='coerce')
    else:                      # seconds
        df['timestamp'] = pd.to_datetime(df['exchange_timestamp'], unit='s', errors='coerce')

    df = df.dropna(subset=['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    if len(df) < 10:
        return {
            "error": "Not enough rows after timestamp normalization",
            "rows_available": len(df)
        }

    # ================== NUMERIC CLEANUP ==================
    num_cols = [
        'ltp', 'last_traded_qty', 'volume',
        'open', 'high', 'low', 'close'
    ]
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors='coerce')
    df = df.dropna(subset=['ltp', 'last_traded_qty', 'volume'])

    if len(df) < 10:
        return {
            "error": "Not enough valid rows after cleanup",
            "rows_available": len(df)
        }

    # ================== FIX CUMULATIVE VOLUME ==================
    df['volume'] = df['volume'].diff().fillna(0).clip(lower=0)

    # ================== VOLUME & VALUE ==================
    df['trade_value'] = df['last_traded_qty'] * df['ltp']

    vol_roll = df['volume'].rolling(20).mean().dropna()
    val_roll = df['trade_value'].rolling(20).mean().dropna()

    avg_volume = vol_roll.iloc[-1] if not vol_roll.empty else df['volume'].mean()
    avg_value = val_roll.iloc[-1] if not val_roll.empty else df['trade_value'].mean()

    latest = df.iloc[-1]
    prev_close = df['close'].iloc[-2] if len(df) > 1 else latest['ltp']

    if latest['volume'] > avg_volume and latest['trade_value'] > avg_value:
        volume_value_signal = "HIGH_VOLUME_HIGH_VALUE"
    elif latest['volume'] > avg_volume and latest['trade_value'] < avg_value:
        volume_value_signal = "HIGH_VOLUME_LOW_VALUE"
    elif latest['ltp'] > prev_close and latest['volume'] < avg_volume:
        volume_value_signal = "PRICE_UP_LOW_VOLUME"
    else:
        volume_value_signal = "NEUTRAL"

    # ================== VWAP ==================
    df['pv'] = df['ltp'] * df['last_traded_qty']
    df['cum_pv'] = df['pv'].cumsum()
    df['cum_qty'] = df['last_traded_qty'].cumsum()

    if df['cum_qty'].iloc[-1] == 0:
        return {"error": "VWAP quantity is zero"}

    df['vwap'] = df['cum_pv'] / df['cum_qty']
    vwap = df['vwap'].iloc[-1]
    vwap_signal = "PRICE_ABOVE_VWAP" if latest['ltp'] > vwap else "PRICE_BELOW_VWAP"

    # ================== 5 MIN CANDLES ==================
    df_5m = df.resample(
        '5T', on='timestamp'
    ).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()

    if len(df_5m) < 15:
        return {
            "error": "Not enough 5m candles",
            "candles_available": len(df_5m)
        }

    prev = df_5m.iloc[-2]
    curr = df_5m.iloc[-1]

    market_structure = (
        "BULLISH_HH_HL"
        if curr['high'] > prev['high'] and curr['low'] > prev['low']
        else "NOT_BULLISH"
    )

    # ================== EMA ==================
    df_5m['ema_20'] = df_5m['close'].ewm(span=20, adjust=False).mean()
    df_5m['ema_50'] = df_5m['close'].ewm(span=50, adjust=False).mean()

    ema_20 = df_5m['ema_20'].iloc[-1]
    ema_50 = df_5m['ema_50'].iloc[-1]
    ema_signal = "EMA20_ABOVE_EMA50" if ema_20 > ema_50 else "EMA20_BELOW_EMA50"

    # ================== RSI ==================
    delta = df_5m['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    avg_gain = gain.rolling(14).mean()
    avg_loss = loss.rolling(14).mean()

    if avg_loss.iloc[-1] == 0:
        rsi = 100.0
    else:
        rs = avg_gain.iloc[-1] / avg_loss.iloc[-1]
        rsi = 100 - (100 / (1 + rs))

    if 55 <= rsi <= 70:
        rsi_signal = "RSI_BULLISH_ZONE"
    elif rsi > 70:
        rsi_signal = "RSI_OVERBOUGHT"
    else:
        rsi_signal = "RSI_WEAK"

    # ================== FINAL OUTPUT ==================
    return to_raw_numbers({
        "timestamp": curr.name.tz_localize("UTC").astimezone(ZoneInfo("Asia/Kolkata")).isoformat(),
        "ltp": round(latest['ltp'], 2),

        "volume": int(latest['volume']),
        "trade_value": round(latest['trade_value'], 2),
        "volume_value_signal": volume_value_signal,

        "vwap": round(vwap, 2),
        "vwap_signal": vwap_signal,

        "market_structure": market_structure,

        "ema_20": round(ema_20, 2),
        "ema_50": round(ema_50, 2),
        "ema_signal": ema_signal,

        "rsi": round(rsi, 2),
        "rsi_signal": rsi_signal,

        "bullish_score": sum([
            volume_value_signal == "HIGH_VOLUME_HIGH_VALUE",
            vwap_signal == "PRICE_ABOVE_VWAP",
            market_structure == "BULLISH_HH_HL",
            ema_20 > ema_50,
            55 <= rsi <= 70
        ])
    })
