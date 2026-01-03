import pandas as pd
from collections import deque
from datetime import datetime, timezone, timedelta

# =====================================================
# CONFIG
# =====================================================
EMA_FAST = 12
EMA_SLOW = 26
EMA_SIGNAL = 9
RSI_PERIOD = 14
ATR_PERIOD = 14
VOL_AVG_PERIOD = 20
CANDLE_INTERVAL = 60  # seconds

IST = timezone(timedelta(hours=5, minutes=30))


# =====================================================
# UTILITIES
# =====================================================
def ts_to_ist(ts_ms):
    return datetime.fromtimestamp(ts_ms / 1000, tz=IST)


def ema(prev_ema, price, period):
    alpha = 2 / (period + 1)
    return price * alpha + prev_ema * (1 - alpha)


# =====================================================
# CANDLE BUILDER (Tick → 1m candle)
# =====================================================
class CandleBuilder:
    def __init__(self):
        self.current = None
        self.prev_volume = None

    def update(self, tick):
        ts = tick["timestamp"] // 1000
        price = tick["ltp"]
        vol = tick["volume"]

        bucket = ts - (ts % CANDLE_INTERVAL)

        if self.current is None or bucket != self.current["timestamp"]:
            finished = self.current

            self.current = {
                "timestamp": bucket,
                "open": price,
                "high": price,
                "low": price,
                "close": price,
                "volume": 0
            }
            self.prev_volume = vol
            return finished

        self.current["high"] = max(self.current["high"], price)
        self.current["low"] = min(self.current["low"], price)
        self.current["close"] = price

        if self.prev_volume is not None:
            self.current["volume"] += max(0, vol - self.prev_volume)

        self.prev_volume = vol
        return None


# =====================================================
# INDICATOR STATE (BOOTSTRAPPED FROM DB)
# =====================================================
class IndicatorState:
    def __init__(self, df: pd.DataFrame):
        # EMA
        self.ema_fast = df["close"].ewm(span=EMA_FAST, adjust=False).iloc[-1]
        self.ema_slow = df["close"].ewm(span=EMA_SLOW, adjust=False).iloc[-1]
        self.signal = 0.0

        # RSI
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        self.avg_gain = gain.ewm(alpha=1/RSI_PERIOD, adjust=False).iloc[-1]
        self.avg_loss = loss.ewm(alpha=1/RSI_PERIOD, adjust=False).iloc[-1]

        # ATR
        tr = pd.concat([
            df["high"] - df["low"],
            (df["high"] - df["close"].shift()).abs(),
            (df["low"] - df["close"].shift()).abs()
        ], axis=1).max(axis=1)

        self.atr = tr.ewm(alpha=1/ATR_PERIOD, adjust=False).iloc[-1]

        # VWAP
        self.vwap_pv = (df["close"] * df["volume"]).sum()
        self.vwap_vol = df["volume"].sum()

        # Volume spike
        self.vol_window = deque(df["volume"].tail(VOL_AVG_PERIOD), maxlen=VOL_AVG_PERIOD)

        self.prev_close = df["close"].iloc[-1]


# =====================================================
# INDICATOR ENGINE (LIVE)
# =====================================================
class IndicatorEngine:
    def __init__(self, df):
        self.state = IndicatorState(df)

    def update(self, candle):
        close = candle["close"]
        high = candle["high"]
        low = candle["low"]
        vol = candle["volume"]

        # EMA
        self.state.ema_fast = ema(self.state.ema_fast, close, EMA_FAST)
        self.state.ema_slow = ema(self.state.ema_slow, close, EMA_SLOW)
        macd = self.state.ema_fast - self.state.ema_slow
        self.state.signal = ema(self.state.signal, macd, EMA_SIGNAL)

        # RSI
        change = close - self.state.prev_close
        gain = max(change, 0)
        loss = max(-change, 0)

        self.state.avg_gain = (self.state.avg_gain * (RSI_PERIOD - 1) + gain) / RSI_PERIOD
        self.state.avg_loss = (self.state.avg_loss * (RSI_PERIOD - 1) + loss) / RSI_PERIOD

        rs = self.state.avg_gain / self.state.avg_loss if self.state.avg_loss else 0
        rsi = 100 - (100 / (1 + rs))

        # ATR
        tr = max(
            high - low,
            abs(high - self.state.prev_close),
            abs(low - self.state.prev_close)
        )
        self.state.atr = (self.state.atr * (ATR_PERIOD - 1) + tr) / ATR_PERIOD

        # VWAP
        self.state.vwap_pv += close * vol
        self.state.vwap_vol += vol
        vwap = self.state.vwap_pv / self.state.vwap_vol

        # Volume Spike
        self.state.vol_window.append(vol)
        avg_vol = sum(self.state.vol_window) / len(self.state.vol_window)
        vol_spike = vol > (1.5 * avg_vol)

        # Lagged return
        lag_return = (close - self.state.prev_close) / self.state.prev_close

        self.state.prev_close = close

        return {
            "close": close,
            "ema_fast": self.state.ema_fast,
            "ema_slow": self.state.ema_slow,
            "macd": macd,
            "signal": self.state.signal,
            "rsi": rsi,
            "atr": self.state.atr,
            "vwap": vwap,
            "volume_spike": vol_spike,
            "lagged_return": lag_return
        }


# =====================================================
# DEMO (SIMULATED DB + LIVE TICKS)
# =====================================================
if __name__ == "__main__":
    # ---- Simulated historical DB (100 candles) ----
    data = {
        "timestamp": range(100),
        "open": [520 + i * 0.1 for i in range(100)],
        "high": [521 + i * 0.1 for i in range(100)],
        "low": [519 + i * 0.1 for i in range(100)],
        "close": [520 + i * 0.1 for i in range(100)],
        "volume": [1000 + i * 10 for i in range(100)],
    }
    hist_df = pd.DataFrame(data)

    engine = IndicatorEngine(hist_df)
    builder = CandleBuilder()

    # ---- Simulated live ticks ----
    live_ticks = [
        {"timestamp": 1767162470000, "ltp": 520.65, "volume": 52961315},
        {"timestamp": 1767162475000, "ltp": 521.20, "volume": 52961380},
        {"timestamp": 1767162480000, "ltp": 522.10, "volume": 52961450},
    ]

    for tick in live_ticks:
        candle = builder.update(tick)
        if candle:
            indicators = engine.update(candle)
            print(ts_to_ist(tick["timestamp"]), indicators)
