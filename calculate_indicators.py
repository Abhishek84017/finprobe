import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

DB_FILE = "market_data.db"


class TechnicalIndicators:
    """
    Calculate technical indicators from real-time market data stored in SQLite DB
    """

    def __init__(self, db_file=DB_FILE):
        self.db_file = db_file

    def get_data(self, token, start_time=None, end_time=None, lookback_minutes=200, interval='1min'):
        """
        Fetch tick data from DB and resample into OHLCV candles

        Args:
            token: Stock token identifier
            start_time: Start datetime (datetime object or string 'YYYY-MM-DD HH:MM:SS')
            end_time: End datetime (datetime object or string 'YYYY-MM-DD HH:MM:SS')
            lookback_minutes: How many minutes of historical data to fetch (if start_time not provided)
            interval: Candle interval ('1min', '5min', '15min', etc.)

        Returns:
            DataFrame with OHLCV data
        """
        conn = sqlite3.connect(self.db_file)

        # Handle start_time and end_time
        if start_time:
            if isinstance(start_time, str):
                start_time = datetime.strptime(start_time, '%Y-%m-%d %H:%M:%S')
            cutoff_time = int(start_time.timestamp() * 1000)
        else:
            # Calculate cutoff timestamp using lookback_minutes
            cutoff_time = int(
                (datetime.now() - timedelta(minutes=lookback_minutes)).timestamp() * 1000)

        if end_time:
            if isinstance(end_time, str):
                end_time = datetime.strptime(end_time, '%Y-%m-%d %H:%M:%S')
            end_timestamp = int(end_time.timestamp() * 1000)
        else:
            end_timestamp = int(datetime.now().timestamp() * 1000)

        query = """
            SELECT 
                exchange_timestamp,
                ltp,
                volume,
                last_traded_qty,
                avg_traded_price,
                high,
                low,
                open,
                close
            FROM market_ticks
            WHERE token = ? AND exchange_timestamp >= ? AND exchange_timestamp <= ?
            ORDER BY exchange_timestamp ASC
        """

        df = pd.read_sql_query(query, conn, params=(
            token, cutoff_time, end_timestamp))
        conn.close()

        if df.empty:
            return pd.DataFrame()

        # Convert timestamp to datetime
        df['datetime'] = pd.to_datetime(df['exchange_timestamp'], unit='ms')
        df.set_index('datetime', inplace=True)

        # Resample to desired interval
        ohlc_dict = {
            'ltp': 'last',
            'high': 'max',
            'low': 'min',
            'open': 'first',
            'close': 'last',
            'volume': 'last',  # Volume is cumulative, take last
            'avg_traded_price': 'mean',
            'last_traded_qty': 'sum'
        }

        # Resample based on interval
        df_resampled = df.resample(interval).agg(ohlc_dict)
        df_resampled = df_resampled.dropna(subset=['ltp'])

        # Use ltp as close if close is not available
        df_resampled['close'] = df_resampled['close'].fillna(
            df_resampled['ltp'])
        df_resampled['open'] = df_resampled['open'].fillna(df_resampled['ltp'])
        df_resampled['high'] = df_resampled['high'].fillna(df_resampled['ltp'])
        df_resampled['low'] = df_resampled['low'].fillna(df_resampled['ltp'])

        return df_resampled

    def calculate_volume_value_insights(self, df):
        """
        Calculate Volume and Value with trading insights

        Returns:
            dict with volume, value, and insights
        """
        if df.empty or len(df) < 2:
            return None

        latest = df.iloc[-1]

        # Calculate value = volume * average traded price
        value = latest['volume'] * latest['avg_traded_price']
        volume = latest['volume']

        # Calculate volume change from previous candle
        if len(df) >= 2:
            prev_volume = df.iloc[-2]['volume']
            volume_change_pct = ((volume - prev_volume) /
                                 prev_volume * 100) if prev_volume > 0 else 0
        else:
            volume_change_pct = 0

        # Calculate average volume for comparison
        avg_volume = df['volume'].tail(20).mean()

        # Trading insights
        high_volume = volume > avg_volume * 1.5
        high_value = value > (
            df['volume'] * df['avg_traded_price']).tail(20).mean() * 1.5
        low_value = value < (
            df['volume'] * df['avg_traded_price']).tail(20).mean() * 0.5

        # Price movement
        price_up = latest['close'] > df.iloc[-2]['close'] if len(
            df) >= 2 else False
        low_volume = volume < avg_volume * 0.7

        insights = []
        if high_volume and high_value:
            insights.append(
                "🔵 Strong institutional participation (High Volume + High Value)")
        elif high_volume and low_value:
            insights.append(
                "⚠️ Low-priced stock activity (High Volume + Low Value)")

        if price_up and low_volume:
            insights.append(
                "⚠️ Price up but volume low - move may not sustain")

        return {
            'volume': volume,
            'value': value,
            'volume_change_pct': round(volume_change_pct, 2),
            'avg_volume': round(avg_volume, 2),
            'is_high_volume': high_volume,
            'insights': insights
        }

    def calculate_vwap(self, df):
        """
        Calculate VWAP (Volume Weighted Average Price)

        VWAP = Cumulative(Price * Volume) / Cumulative(Volume)
        """
        if df.empty:
            return None

        # Calculate typical price (H+L+C)/3
        df['typical_price'] = (df['high'] + df['low'] + df['close']) / 3

        # Calculate volume difference (since volume is cumulative)
        df['volume_diff'] = df['volume'].diff().fillna(df['volume'])

        # Calculate cumulative typical price * volume
        df['tp_volume'] = df['typical_price'] * df['volume_diff']

        # Calculate VWAP for each candle (reset daily)
        # For intraday, reset at start of day
        df['date'] = df.index.date
        df['cumulative_tp_volume'] = df.groupby('date')['tp_volume'].cumsum()
        df['cumulative_volume'] = df.groupby('date')['volume_diff'].cumsum()

        df['vwap'] = df['cumulative_tp_volume'] / df['cumulative_volume']

        latest = df.iloc[-1]
        current_price = latest['close']
        vwap_value = latest['vwap']

        # Signal
        if current_price > vwap_value:
            signal = "BULLISH - Buyers are strong (Price > VWAP)"
        elif current_price < vwap_value:
            signal = "BEARISH - Sellers are strong (Price < VWAP)"
        else:
            signal = "NEUTRAL - Price at VWAP"

        return {
            'vwap': round(vwap_value, 2),
            'current_price': round(current_price, 2),
            'difference': round(current_price - vwap_value, 2),
            'difference_pct': round((current_price - vwap_value) / vwap_value * 100, 2),
            'signal': signal
        }

    def calculate_market_structure(self, df, timeframe='5min'):
        """
        Calculate Market Structure (Higher High + Higher Low)

        Identifies if price is making higher highs and higher lows (bullish structure)
        """
        if df.empty or len(df) < 3:
            return None

        # Get last 3 swing points
        highs = df['high'].tail(10)
        lows = df['low'].tail(10)

        # Find local peaks and troughs
        peaks = []
        troughs = []

        for i in range(1, len(highs) - 1):
            if highs.iloc[i] > highs.iloc[i-1] and highs.iloc[i] > highs.iloc[i+1]:
                peaks.append(highs.iloc[i])
            if lows.iloc[i] < lows.iloc[i-1] and lows.iloc[i] < lows.iloc[i+1]:
                troughs.append(lows.iloc[i])

        # Check for higher highs and higher lows
        higher_high = False
        higher_low = False

        if len(peaks) >= 2:
            higher_high = peaks[-1] > peaks[-2]

        if len(troughs) >= 2:
            higher_low = troughs[-1] > troughs[-2]
            no_breakdown = df['low'].tail(
                5).min() > troughs[-2] if len(troughs) >= 2 else True
        else:
            no_breakdown = True

        # Bullish condition: Higher high + Higher low + No breakdown
        is_bullish = higher_high and higher_low and no_breakdown

        structure = "BULLISH" if is_bullish else "BEARISH/CONSOLIDATING"

        return {
            'structure': structure,
            'higher_high': higher_high,
            'higher_low': higher_low,
            'no_breakdown': no_breakdown,
            'is_bullish': is_bullish,
            'latest_high': round(df['high'].tail(10).max(), 2),
            'latest_low': round(df['low'].tail(10).min(), 2)
        }

    def calculate_ema(self, df, period):
        """
        Calculate Exponential Moving Average
        """
        if df.empty:
            return None

        return df['close'].ewm(span=period, adjust=False).mean()

    def calculate_ema_crossover(self, df):
        """
        Calculate EMA 20 and EMA 50 with crossover signals
        """
        if df.empty or len(df) < 50:
            return None

        df['ema_20'] = self.calculate_ema(df, 20)
        df['ema_50'] = self.calculate_ema(df, 50)

        latest = df.iloc[-1]
        ema_20 = latest['ema_20']
        ema_50 = latest['ema_50']

        # Check crossover
        is_bullish = ema_20 > ema_50

        signal = "BULLISH ✓ (EMA 20 > EMA 50)" if is_bullish else "BEARISH (EMA 20 < EMA 50)"

        return {
            'ema_20': round(ema_20, 2),
            'ema_50': round(ema_50, 2),
            'is_bullish': is_bullish,
            'signal': signal,
            'difference': round(ema_20 - ema_50, 2),
            'current_price': round(latest['close'], 2)
        }

    def calculate_rsi(self, df, period=14):
        """
        Calculate Relative Strength Index (RSI)

        RSI = 100 - (100 / (1 + RS))
        where RS = Average Gain / Average Loss
        """
        if df.empty or len(df) < period + 1:
            return None

        # Calculate price changes
        delta = df['close'].diff()

        # Separate gains and losses
        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        # Calculate average gain and loss
        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        # Calculate RS and RSI
        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        df['rsi'] = rsi

        latest_rsi = df['rsi'].iloc[-1]

        # Signal interpretation
        if 55 <= latest_rsi <= 70:
            signal = "GOOD ✓ (RSI in optimal range 55-70)"
            condition = "BULLISH"
        elif latest_rsi > 70:
            signal = "OVERBOUGHT (RSI > 70) - potential reversal"
            condition = "OVERBOUGHT"
        elif latest_rsi < 30:
            signal = "OVERSOLD (RSI < 30) - potential bounce"
            condition = "OVERSOLD"
        elif 50 <= latest_rsi < 55:
            signal = "NEUTRAL (RSI 50-55) - slight bullish"
            condition = "NEUTRAL"
        else:
            signal = "BEARISH (RSI < 50)"
            condition = "BEARISH"

        return {
            'rsi': round(latest_rsi, 2),
            'signal': signal,
            'condition': condition,
            'is_good': 55 <= latest_rsi <= 70
        }

    def analyze_stock(self, token, interval='5min', start_time=None, end_time=None, lookback_minutes=200):
        """
        Complete analysis of a stock with all indicators

        Args:
            token: Stock token identifier
            interval: Candle interval ('1min', '5min', '15min')
            start_time: Start datetime (datetime object or string 'YYYY-MM-DD HH:MM:SS')
            end_time: End datetime (datetime object or string 'YYYY-MM-DD HH:MM:SS')
            lookback_minutes: Historical data to fetch (if start_time not provided)

        Returns:
            dict with all calculated indicators
        """
        print(f"\n{'='*60}")
        print(f"📊 Technical Analysis for Token: {token}")
        print(f"{'='*60}")

        # Fetch data
        df = self.get_data(token, start_time, end_time,
                           lookback_minutes, interval)

        if df.empty:
            print("❌ No data available for this token")
            return None

        print(f"✓ Fetched {len(df)} candles ({interval} interval)")
        print(f"✓ Time range: {df.index[0]} to {df.index[-1]}")
        print(f"✓ Current Price: ₹{df['close'].iloc[-1]:.2f}")

        # Calculate all indicators
        results = {
            'token': token,
            'timestamp': datetime.now().isoformat(),
            'current_price': round(df['close'].iloc[-1], 2),
            'interval': interval
        }

        # 1. Volume and Value
        print(f"\n{'─'*60}")
        print("1️⃣  VOLUME & VALUE ANALYSIS")
        print(f"{'─'*60}")
        volume_data = self.calculate_volume_value_insights(df)
        if volume_data:
            results['volume_analysis'] = volume_data
            print(f"  📊 Volume: {volume_data['volume']:,.0f}")
            print(f"  💰 Value: ₹{volume_data['value']:,.2f}")
            print(
                f"  📈 Volume Change: {volume_data['volume_change_pct']:+.2f}%")
            print(f"  📊 Avg Volume (20): {volume_data['avg_volume']:,.0f}")
            if volume_data['insights']:
                for insight in volume_data['insights']:
                    print(f"  {insight}")

        # 2. VWAP
        print(f"\n{'─'*60}")
        print("2️⃣  VWAP (Volume Weighted Average Price)")
        print(f"{'─'*60}")
        vwap_data = self.calculate_vwap(df.copy())
        if vwap_data:
            results['vwap'] = vwap_data
            print(f"  📍 VWAP: ₹{vwap_data['vwap']:.2f}")
            print(f"  💹 Current Price: ₹{vwap_data['current_price']:.2f}")
            print(
                f"  📊 Difference: ₹{vwap_data['difference']:+.2f} ({vwap_data['difference_pct']:+.2f}%)")
            print(f"  🎯 {vwap_data['signal']}")

        # 3. Market Structure
        print(f"\n{'─'*60}")
        print("3️⃣  MARKET STRUCTURE (Higher High + Higher Low)")
        print(f"{'─'*60}")
        structure_data = self.calculate_market_structure(df, interval)
        if structure_data:
            results['market_structure'] = structure_data
            print(f"  📈 Structure: {structure_data['structure']}")
            print(
                f"  ✓ Higher High: {'YES' if structure_data['higher_high'] else 'NO'}")
            print(
                f"  ✓ Higher Low: {'YES' if structure_data['higher_low'] else 'NO'}")
            print(
                f"  ✓ No Breakdown: {'YES' if structure_data['no_breakdown'] else 'NO'}")
            print(
                f"  🎯 Is Bullish: {'YES ✓' if structure_data['is_bullish'] else 'NO'}")

        # 4. EMA 20 & 50
        print(f"\n{'─'*60}")
        print("4️⃣  EMA 20 & EMA 50")
        print(f"{'─'*60}")
        ema_data = self.calculate_ema_crossover(df.copy())
        if ema_data:
            results['ema'] = ema_data
            print(f"  📊 EMA 20: ₹{ema_data['ema_20']:.2f}")
            print(f"  📊 EMA 50: ₹{ema_data['ema_50']:.2f}")
            print(f"  📊 Difference: ₹{ema_data['difference']:+.2f}")
            print(f"  🎯 {ema_data['signal']}")

        # 5. RSI
        print(f"\n{'─'*60}")
        print("5️⃣  RSI (Relative Strength Index)")
        print(f"{'─'*60}")
        rsi_data = self.calculate_rsi(df.copy(), period=14)
        if rsi_data:
            results['rsi'] = rsi_data
            print(f"  📊 RSI (14): {rsi_data['rsi']:.2f}")
            print(f"  📊 Condition: {rsi_data['condition']}")
            print(f"  🎯 {rsi_data['signal']}")

        # Overall Summary
        print(f"\n{'='*60}")
        print("📋 OVERALL SUMMARY")
        print(f"{'='*60}")

        bullish_count = 0
        total_checks = 0

        if vwap_data:
            total_checks += 1
            if vwap_data['difference'] > 0:
                bullish_count += 1
                print("✓ VWAP: BULLISH")
            else:
                print("✗ VWAP: BEARISH")

        if structure_data:
            total_checks += 1
            if structure_data['is_bullish']:
                bullish_count += 1
                print("✓ Market Structure: BULLISH")
            else:
                print("✗ Market Structure: BEARISH/CONSOLIDATING")

        if ema_data:
            total_checks += 1
            if ema_data['is_bullish']:
                bullish_count += 1
                print("✓ EMA: BULLISH")
            else:
                print("✗ EMA: BEARISH")

        if rsi_data:
            total_checks += 1
            if rsi_data['is_good']:
                bullish_count += 1
                print("✓ RSI: GOOD (55-70)")
            else:
                print(f"✗ RSI: {rsi_data['condition']}")

        print(f"\n📊 Bullish Signals: {bullish_count}/{total_checks}")

        if bullish_count >= 3:
            overall = "🟢 STRONG BULLISH - Good trading opportunity"
        elif bullish_count >= 2:
            overall = "🟡 MODERATE BULLISH - Cautious optimism"
        else:
            overall = "🔴 BEARISH/WEAK - Avoid or wait for better setup"

        print(f"🎯 Overall Signal: {overall}")
        results['overall_signal'] = overall
        results['bullish_score'] = f"{bullish_count}/{total_checks}"

        print(f"{'='*60}\n")

        return results


# =====================================================
# EXAMPLE USAGE
# =====================================================
if __name__ == "__main__":
    # Initialize calculator
    calc = TechnicalIndicators()

    print("\n" + "="*60)
    print("📈 STOCK TECHNICAL ANALYSIS TOOL")
    print("="*60)

    # Get token from user
    token = input(
        "\n🔍 Enter stock token (default: 17939): ").strip() or "17939"

    # Ask for time period preference
    print("\n⏰ Time Period Options:")
    print("  1. Last N minutes (e.g., last 200 minutes)")
    print("  2. Specific date/time range")
    choice = input("\nSelect option (1 or 2, default: 1): ").strip() or "1"

    start_time = "2026-01-05 09:15:00"
    end_time = "2026-01-05 15:30:00"
    lookback_minutes = 200

    if choice == "2":
        print("\n📅 Enter date/time range (Format: YYYY-MM-DD HH:MM:SS)")
        print("   Example: 2026-01-06 09:15:00")

        start_input = input("\n  Start date/time: ").strip()
        end_input = input(
            "  End date/time (press Enter for current time): ").strip()

        if start_input:
            try:
                start_time = start_input
                end_time = end_input if end_input else None
                print(
                    f"\n✓ Analysis period: {start_input} to {end_input or 'Now'}")
            except Exception as e:
                print(f"\n⚠️ Invalid date format, using default (last 200 minutes)")
                start_time = None
                end_time = None
    else:
        lookback_input = input(
            "\n⏱️  Enter lookback minutes (default: 200): ").strip()
        if lookback_input.isdigit():
            lookback_minutes = int(lookback_input)
        print(f"\n✓ Analyzing last {lookback_minutes} minutes of data")

    # Get interval
    print("\n📊 Candle Interval Options: 1min, 5min, 15min, 30min, 1H")
    interval = input("  Select interval (default: 5min): ").strip() or "5min"

    # Analyze with user inputs
    results = calc.analyze_stock(
        token=token,
        interval=interval,
        start_time=start_time,
        end_time=end_time,
        lookback_minutes=lookback_minutes
    )

    # Example 2: Analyze multiple stocks
    """
    tokens = ["TOKEN1", "TOKEN2", "TOKEN3"]
    
    for token in tokens:
        results = calc.analyze_stock(token, interval='5min', lookback_minutes=200)
        # Store or process results as needed
    """

    # Example 3: Real-time monitoring
    """
    import time
    
    while True:
        results = calc.analyze_stock(token, interval='1min', lookback_minutes=100)
        time.sleep(60)  # Check every minute
    """
