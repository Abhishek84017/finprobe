#!/usr/bin/env python3
"""
═══════════════════════════════════════════════════════════════════════
         LIVE INTRADAY STOCK TREND ANALYZER
═══════════════════════════════════════════════════════════════════════

Analyzes real-time market trends during trading hours (09:15 - 15:30)
Run this anytime to get current trend analysis with BUY/AVOID signals

USAGE:
    python3 live_trend_analyzer.py           # Interactive mode
    python3 live_trend_analyzer.py all       # Scan all tokens
    python3 live_trend_analyzer.py 17939     # Analyze specific token

═══════════════════════════════════════════════════════════════════════
"""

import sqlite3
from datetime import datetime, time as datetime_time
from zoneinfo import ZoneInfo
import pandas as pd
import numpy as np


# ═══════════════════════════════════════════════════════════════════════
#                     HELPER FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════

def to_raw_numbers(d):
    """Convert numpy types to native Python numbers"""
    raw = {}
    for k, v in d.items():
        if isinstance(v, (np.integer,)):
            raw[k] = int(v)
        elif isinstance(v, (np.floating,)):
            raw[k] = float(v)
        else:
            raw[k] = v
    return raw


def is_market_hours():
    """Check if current time is within market hours (09:15 - 15:30)"""
    now = datetime.now()
    current_time = now.time()
    market_open = datetime_time(9, 15)
    market_close = datetime_time(15, 30)
    return market_open <= current_time <= market_close


def get_today_session_start():
    """Get today's market session start timestamp (09:15 AM) in milliseconds"""
    today = datetime.now().replace(hour=9, minute=15, second=0, microsecond=0)
    return int(today.timestamp() * 1000)


def get_current_timestamp():
    """Get current timestamp in milliseconds"""
    return int(datetime.now().timestamp() * 1000)


# ═══════════════════════════════════════════════════════════════════════
#                  TECHNICAL INDICATORS CALCULATION
# ═══════════════════════════════════════════════════════════════════════

def calculate_intraday_indicators(raw_data):
    """
    Calculate technical indicators for intraday trading
    
    Indicators (calculates what's possible with available data):
    1. Volume & Value Analysis (always)
    2. VWAP (always)
    3. Market Structure (needs 15+ 5m candles)
    4. EMA 20 & 50 (needs 50+ 5m candles)
    5. RSI (needs 15+ 5m candles)
    
    Returns: Dictionary with available indicators and bullish score
    """
    df = pd.DataFrame(raw_data)

    # ================== VALIDATION ==================
    if df.empty or len(df) < 10:
        return {
            "error": "Not enough raw data",
            "rows_available": len(df)
        }

    # ================== TIMESTAMP NORMALIZATION ==================
    ts = pd.to_numeric(df['exchange_timestamp'], errors='coerce').dropna()
    if ts.empty:
        return {"error": "Invalid exchange_timestamp data"}

    max_ts = ts.max()
    if max_ts > 10**18:
        df['timestamp'] = pd.to_datetime(df['exchange_timestamp'], unit='ns', errors='coerce')
    elif max_ts > 10**15:
        df['timestamp'] = pd.to_datetime(df['exchange_timestamp'], unit='us', errors='coerce')
    elif max_ts > 10**12:
        df['timestamp'] = pd.to_datetime(df['exchange_timestamp'], unit='ms', errors='coerce')
    else:
        df['timestamp'] = pd.to_datetime(df['exchange_timestamp'], unit='s', errors='coerce')

    df = df.dropna(subset=['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)

    if len(df) < 10:
        return {"error": "Not enough rows after timestamp normalization"}

    # ================== NUMERIC CLEANUP ==================
    num_cols = ['ltp', 'last_traded_qty', 'volume', 'open', 'high', 'low', 'close']
    df[num_cols] = df[num_cols].apply(pd.to_numeric, errors='coerce')
    df = df.dropna(subset=['ltp', 'last_traded_qty', 'volume'])

    if len(df) < 10:
        return {"error": "Not enough valid rows after cleanup"}

    # Fix cumulative volume
    df['volume'] = df['volume'].diff().fillna(0).clip(lower=0)

    # Track which indicators are available
    available_indicators = []
    skipped_indicators = []

    # ================== 1. VOLUME & VALUE ANALYSIS (ALWAYS) ==================
    df['trade_value'] = df['last_traded_qty'] * df['ltp']
    
    # Get latest row AFTER creating all needed columns
    latest = df.iloc[-1]
    prev_close = df['close'].iloc[-2] if len(df) > 1 else latest['ltp']
    vol_roll = df['volume'].rolling(20).mean().dropna()
    val_roll = df['trade_value'].rolling(20).mean().dropna()

    avg_volume = vol_roll.iloc[-1] if not vol_roll.empty else df['volume'].mean()
    avg_value = val_roll.iloc[-1] if not val_roll.empty else df['trade_value'].mean()

    if latest['volume'] > avg_volume and latest['trade_value'] > avg_value:
        volume_value_signal = "HIGH_VOLUME_HIGH_VALUE"
    elif latest['volume'] > avg_volume and latest['trade_value'] < avg_value:
        volume_value_signal = "HIGH_VOLUME_LOW_VALUE"
    elif latest['ltp'] > prev_close and latest['volume'] < avg_volume:
        volume_value_signal = "PRICE_UP_LOW_VOLUME"
    else:
        volume_value_signal = "NEUTRAL"
    
    available_indicators.append("Volume & Value")

    # ================== 2. VWAP (ALWAYS) ==================
    df['pv'] = df['ltp'] * df['last_traded_qty']
    df['cum_pv'] = df['pv'].cumsum()
    df['cum_qty'] = df['last_traded_qty'].cumsum()

    if df['cum_qty'].iloc[-1] == 0:
        return {"error": "VWAP quantity is zero"}

    df['vwap'] = df['cum_pv'] / df['cum_qty']
    vwap = df['vwap'].iloc[-1]
    vwap_signal = "PRICE_ABOVE_VWAP" if latest['ltp'] > vwap else "PRICE_BELOW_VWAP"
    
    available_indicators.append("VWAP")

    # ================== 5-MIN CANDLES ==================
    df_5m = df.resample(
        '5min', on='timestamp'
    ).agg({
        'open': 'first',
        'high': 'max',
        'low': 'min',
        'close': 'last',
        'volume': 'sum'
    }).dropna()

    # Initialize optional indicators as None
    market_structure = None
    prev_high = prev_low = curr_high = curr_low = None
    ema_20 = ema_50 = None
    ema_signal = None
    rsi = None
    rsi_signal = None

    # ================== 3. MARKET STRUCTURE (needs 2+ candles) ==================
    if len(df_5m) >= 2:
        prev = df_5m.iloc[-2]
        curr = df_5m.iloc[-1]
        
        market_structure = (
            "BULLISH_HH_HL"
            if curr['high'] > prev['high'] and curr['low'] > prev['low']
            else "NOT_BULLISH"
        )
        prev_high = round(prev['high'], 2)
        prev_low = round(prev['low'], 2)
        curr_high = round(curr['high'], 2)
        curr_low = round(curr['low'], 2)
        
        available_indicators.append("Market Structure")
    else:
        skipped_indicators.append("Market Structure (need 10+ min)")

    # ================== 4. EMA CROSSOVER (needs 50+ candles = 250 min) ==================
    if len(df_5m) >= 50:
        df_5m['ema_20'] = df_5m['close'].ewm(span=20, adjust=False).mean()
        df_5m['ema_50'] = df_5m['close'].ewm(span=50, adjust=False).mean()

        ema_20 = round(df_5m['ema_20'].iloc[-1], 2)
        ema_50 = round(df_5m['ema_50'].iloc[-1], 2)
        ema_signal = "EMA20_ABOVE_EMA50" if ema_20 > ema_50 else "EMA20_BELOW_EMA50"
        
        available_indicators.append("EMA Crossover")
    else:
        ema_20 = ema_50 = 0.0
        ema_signal = "INSUFFICIENT_DATA"
        skipped_indicators.append(f"EMA (need 250+ min, have {len(df_5m)*5} min)")

    # ================== 5. RSI (needs 15+ candles = 75 min) ==================
    if len(df_5m) >= 15:
        delta = df_5m['close'].diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)

        avg_gain = gain.rolling(14).mean()
        avg_loss = loss.rolling(14).mean()

        # Check if we have valid RSI data
        if not avg_gain.empty and not avg_loss.empty and not pd.isna(avg_gain.iloc[-1]):
            if avg_loss.iloc[-1] == 0 or pd.isna(avg_loss.iloc[-1]):
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
            
            rsi = round(rsi, 2)
            available_indicators.append("RSI")
        else:
            rsi = None
            rsi_signal = "INSUFFICIENT_DATA"
            skipped_indicators.append("RSI (calculation failed)")
    else:
        rsi = None
        rsi_signal = "INSUFFICIENT_DATA"
        skipped_indicators.append(f"RSI (need 75+ min, have {len(df_5m)*5} min)")

    # ================== BULLISH SCORE (based on available indicators) ==================
    bullish_checks = []
    max_possible_score = 0
    
    # Volume & Value (always available)
    bullish_checks.append(volume_value_signal == "HIGH_VOLUME_HIGH_VALUE")
    max_possible_score += 1
    
    # VWAP (always available)
    bullish_checks.append(vwap_signal == "PRICE_ABOVE_VWAP")
    max_possible_score += 1
    
    # Market Structure (if available)
    if market_structure:
        bullish_checks.append(market_structure == "BULLISH_HH_HL")
        max_possible_score += 1
    
    # EMA (if available)
    if ema_20 and ema_50 and ema_signal != "INSUFFICIENT_DATA":
        bullish_checks.append(ema_20 > ema_50)
        max_possible_score += 1
    
    # RSI (if available)
    if rsi is not None and rsi_signal != "INSUFFICIENT_DATA":
        bullish_checks.append(55 <= rsi <= 70)
        max_possible_score += 1
    
    bullish_score = sum(bullish_checks)
    
    # Determine overall signal (adjusted for available indicators)
    if max_possible_score == 0:
        overall_signal = "INSUFFICIENT_DATA"
        recommendation = "WAIT - Not enough data yet"
    else:
        percentage = (bullish_score / max_possible_score) * 100
        
        if percentage >= 80:  # 4/5 or 2/2
            overall_signal = "STRONG_BULLISH"
            recommendation = f"BUY - Strong signal ({bullish_score}/{max_possible_score} indicators bullish)"
        elif percentage >= 60:  # 3/5
            overall_signal = "BULLISH"
            recommendation = f"BUY - Moderate signal ({bullish_score}/{max_possible_score} indicators bullish)"
        elif percentage >= 40:  # 2/5
            overall_signal = "NEUTRAL"
            recommendation = f"WAIT - Mixed signals ({bullish_score}/{max_possible_score} indicators bullish)"
        else:
            overall_signal = "BEARISH"
            recommendation = f"AVOID - Weak signals ({bullish_score}/{max_possible_score} indicators bullish)"
    
    # Get timestamp
    if len(df_5m) > 0:
        timestamp = df_5m.index[-1].tz_localize("UTC").astimezone(ZoneInfo("Asia/Kolkata")).isoformat()
    else:
        timestamp = latest['timestamp'].tz_localize("UTC").astimezone(ZoneInfo("Asia/Kolkata")).isoformat()
    
    # ================== RETURN RESULTS ==================
    return to_raw_numbers({
        "timestamp": timestamp,
        "ltp": round(latest['ltp'], 2),
        
        # Volume & Value
        "volume": int(latest['volume']),
        "avg_volume": round(avg_volume, 2),
        "trade_value": round(latest['trade_value'], 2),
        "avg_trade_value": round(avg_value, 2),
        "volume_value_signal": volume_value_signal,
        
        # VWAP
        "vwap": round(vwap, 2),
        "vwap_signal": vwap_signal,
        "ltp_vs_vwap": round(((latest['ltp'] - vwap) / vwap) * 100, 2),
        
        # Market Structure (optional)
        "market_structure": market_structure if market_structure else "N/A",
        "prev_high": prev_high if prev_high else 0.0,
        "curr_high": curr_high if curr_high else round(latest['high'], 2),
        "prev_low": prev_low if prev_low else 0.0,
        "curr_low": curr_low if curr_low else round(latest['low'], 2),
        
        # EMA (optional)
        "ema_20": ema_20 if ema_20 else 0.0,
        "ema_50": ema_50 if ema_50 else 0.0,
        "ema_signal": ema_signal if ema_signal else "N/A",
        
        # RSI (optional)
        "rsi": rsi if rsi else 0.0,
        "rsi_signal": rsi_signal if rsi_signal else "N/A",
        
        # Overall
        "bullish_score": bullish_score,
        "max_score": max_possible_score,
        "overall_signal": overall_signal,
        "recommendation": recommendation,
        
        # Info
        "data_rows": len(df),
        "candles_5m": len(df_5m),
        "available_indicators": available_indicators,
        "skipped_indicators": skipped_indicators,
    })


# ═══════════════════════════════════════════════════════════════════════
#                    DATABASE & DATA FETCHING
# ═══════════════════════════════════════════════════════════════════════

def fetch_today_live_data(token, db_path="market_data.db"):
    """Fetch all data from today's market session (09:15 AM till now)"""
    conn = sqlite3.connect(db_path)
    
    session_start_ms = get_today_session_start()
    current_ms = get_current_timestamp()
    
    query = """
        SELECT 
            token, exchange_type, subscription_mode,
            sequence_number, exchange_timestamp, exchange_timestamp_human,
            ltp, last_traded_qty, avg_traded_price, volume,
            total_buy_qty, total_sell_qty,
            open, high, low, close,
            last_traded_time, open_interest, oi_change_percent,
            upper_circuit, lower_circuit, week_52_high, week_52_low,
            received_at
        FROM market_ticks
        WHERE token = ? 
        AND received_at >= ?
        AND received_at <= ?
        ORDER BY received_at ASC
    """
    
    df = pd.read_sql_query(query, conn, params=(token, session_start_ms, current_ms))
    conn.close()
    
    return df


# ═══════════════════════════════════════════════════════════════════════
#                       LIVE TREND ANALYSIS
# ═══════════════════════════════════════════════════════════════════════

def analyze_live_trend(token, db_path="market_data.db"):
    """
    Analyze current live market trend for a token
    Shows all 5 indicators and gives BUY/AVOID decision
    """
    now = datetime.now()
    current_time_str = now.strftime('%H:%M:%S')
    
    print(f"\n{'='*70}")
    print(f"📊 LIVE MARKET TREND ANALYSIS")
    print(f"{'='*70}")
    print(f"🕐 Current Time: {current_time_str}")
    print(f"📈 Token: {token}")
    
    # Market status
    if is_market_hours():
        print(f"🟢 Market Status: OPEN (Trading Hours)")
    else:
        current_time = now.time()
        if current_time < datetime_time(9, 15):
            print(f"🟡 Market Status: PRE-MARKET (Opens at 09:15)")
        else:
            print(f"🔴 Market Status: CLOSED (Closed at 15:30)")
    
    print(f"{'='*70}\n")
    
    # Fetch today's data
    print("📡 Fetching today's market data...")
    raw_data = fetch_today_live_data(token, db_path)
    
    if raw_data.empty:
        print(f"\n❌ No data available for token {token} in today's session!")
        print(f"   • Make sure ws_client.py is running")
        print(f"   • Check if market has opened (09:15 AM)")
        print(f"   • Verify token number is correct\n")
        return None
    
    # Data info
    data_start = datetime.fromtimestamp(raw_data['received_at'].iloc[0] / 1000)
    data_end = datetime.fromtimestamp(raw_data['received_at'].iloc[-1] / 1000)
    duration_minutes = (data_end - data_start).total_seconds() / 60
    
    print(f"✓ Found {len(raw_data)} data points")
    print(f"✓ Session started: {data_start.strftime('%H:%M:%S')}")
    print(f"✓ Latest data: {data_end.strftime('%H:%M:%S')}")
    print(f"✓ Duration: {duration_minutes:.0f} minutes\n")
    
    # Calculate indicators
    print("🔄 Calculating technical indicators...\n")
    result = calculate_intraday_indicators(raw_data.to_dict('records'))
    
    if "error" in result:
        print(f"❌ Analysis Error: {result['error']}")
        print(f"   Current session: {duration_minutes:.0f} minutes\n")
        return None
    
    # Show which indicators are available/skipped
    if result.get('skipped_indicators'):
        print("⚠️  EARLY SESSION - Some indicators skipped:")
        for skip in result['skipped_indicators']:
            print(f"   ⏭️  {skip}")
        print(f"\n✅ Available indicators ({len(result['available_indicators'])}):")
        for avail in result['available_indicators']:
            print(f"   ✓ {avail}")
        print()
    
    # Display snapshot
    print("="*70)
    print("📸 CURRENT MARKET SNAPSHOT")
    print("="*70)
    print(f"💰 Current Price (LTP): ₹{result['ltp']}")
    print(f"📊 VWAP: ₹{result['vwap']} ({result['ltp_vs_vwap']:+.2f}%)")
    print(f"📈 Today's Range: ₹{result['curr_low']} - ₹{result['curr_high']}")
    print(f"🔄 Volume: {result['volume']:,}")
    
    # Show indicators
    print(f"\n{'='*70}")
    print("🎯 LIVE TECHNICAL INDICATORS")
    print("="*70)
    
    # 1. Volume & Value
    vol_icon = "✅" if result['volume_value_signal'] == "HIGH_VOLUME_HIGH_VALUE" else "⚠️"
    print(f"\n{vol_icon} 1. VOLUME & VALUE")
    print(f"   Current: {result['volume']:,} | Avg: {result['avg_volume']:,.0f}")
    print(f"   Value: ₹{result['trade_value']:,.2f} | Avg: ₹{result['avg_trade_value']:,.2f}")
    print(f"   📊 {result['volume_value_signal']}")
    
    # 2. VWAP
    vwap_icon = "✅" if result['vwap_signal'] == "PRICE_ABOVE_VWAP" else "⚠️"
    print(f"\n{vwap_icon} 2. VWAP POSITION")
    print(f"   Price: ₹{result['ltp']} | VWAP: ₹{result['vwap']}")
    print(f"   Difference: {result['ltp_vs_vwap']:+.2f}%")
    print(f"   📊 {result['vwap_signal']}")
    if result['ltp_vs_vwap'] > 0:
        print(f"   💡 BUYERS controlling the price")
    else:
        print(f"   💡 SELLERS controlling the price")
    
    # 3. Market Structure
    if result['market_structure'] != "N/A":
        struct_icon = "✅" if result['market_structure'] == "BULLISH_HH_HL" else "⚠️"
        print(f"\n{struct_icon} 3. MARKET STRUCTURE")
        print(f"   Previous 5m: High ₹{result['prev_high']}, Low ₹{result['prev_low']}")
        print(f"   Current 5m:  High ₹{result['curr_high']}, Low ₹{result['curr_low']}")
        print(f"   📊 {result['market_structure']}")
    else:
        print(f"\n⏭️  3. MARKET STRUCTURE")
        print(f"   📊 SKIPPED - Not enough data yet")
    
    # 4. EMA
    if result['ema_signal'] not in ["N/A", "INSUFFICIENT_DATA"]:
        ema_icon = "✅" if result['ema_signal'] == "EMA20_ABOVE_EMA50" else "⚠️"
        print(f"\n{ema_icon} 4. EMA TREND")
        print(f"   EMA 20: ₹{result['ema_20']} | EMA 50: ₹{result['ema_50']}")
        print(f"   📊 {result['ema_signal']}")
    else:
        print(f"\n⏭️  4. EMA TREND")
        print(f"   📊 SKIPPED - Need 250+ min of data")
    
    # 5. RSI
    if result['rsi_signal'] not in ["N/A", "INSUFFICIENT_DATA"]:
        rsi_icon = "✅" if result['rsi_signal'] == "RSI_BULLISH_ZONE" else "⚠️"
        print(f"\n{rsi_icon} 5. RSI MOMENTUM")
        print(f"   RSI: {result['rsi']:.2f}")
        print(f"   📊 {result['rsi_signal']}")
    else:
        print(f"\n⏭️  5. RSI MOMENTUM")
        print(f"   📊 SKIPPED - Need 75+ min of data")
    
    # Overall verdict
    print(f"\n{'='*70}")
    print("🎯 LIVE TREND VERDICT")
    print("="*70)
    
    score = result['bullish_score']
    max_score = result['max_score']
    print(f"\n📊 BULLISH SCORE: {score}/{max_score}")
    if max_score < 5:
        print(f"   ℹ️  Early session - using {max_score} available indicators")
    print(f"🎯 TREND: {result['overall_signal']}")
    
    # Trading decision
    print(f"\n{'='*70}")
    print("💼 TRADING DECISION (RIGHT NOW)")
    print("="*70)
    
    if score >= 4:
        print(f"\n🟢 STRONG BULLISH - BUY SIGNAL")
        print(f"   ✅ All indicators are aligned positively")
        print(f"   ✅ Strong institutional buying activity")
        print(f"   ✅ Price above VWAP (buyers in control)")
        print(f"   ✅ Clear uptrend structure forming")
        print(f"\n   💰 TRADE SETUP:")
        print(f"   📍 Entry: ₹{result['ltp']} (Current Price)")
        print(f"   🛑 Stop Loss: ₹{result['vwap']:.2f} (Below VWAP)")
        print(f"   🎯 Target 1: ₹{result['ltp'] * 1.01:.2f} (1% profit)")
        print(f"   🎯 Target 2: ₹{result['ltp'] * 1.015:.2f} (1.5% profit)")
        print(f"\n   ⚡ ACTION: Consider BUYING now for intraday")
        
    elif score == 3:
        print(f"\n🟡 MODERATE BULLISH - CAUTIOUS BUY")
        print(f"   ⚠️  Most indicators positive, but some weakness")
        print(f"   ⚠️  Trend is developing but not fully confirmed")
        print(f"\n   💰 TRADE SETUP (If you want to enter):")
        print(f"   📍 Entry: ₹{result['ltp']}")
        print(f"   🛑 Stop Loss: ₹{result['vwap']:.2f} (Tight stop)")
        print(f"   🎯 Target: ₹{result['ltp'] * 1.01:.2f} (1% profit)")
        print(f"\n   ⚡ ACTION: Can buy with tight stop loss")
        print(f"   ⚡ Watch for any breakdown below VWAP")
        
    elif score == 2:
        print(f"\n🟠 NEUTRAL - WAIT & WATCH")
        print(f"   ⏸️  Mixed signals, no clear direction")
        print(f"   ⏸️  Market is consolidating")
        print(f"\n   ⚡ ACTION: WAIT for clearer signals")
        print(f"   • Don't enter new positions now")
        print(f"   • Watch for breakout above VWAP")
        print(f"   • Monitor for improvement in indicators")
        
    else:
        print(f"\n🔴 BEARISH - AVOID OR EXIT")
        print(f"   ❌ Most indicators are negative")
        print(f"   ❌ Price below VWAP (sellers in control)")
        print(f"   ❌ Weak or downward trend")
        print(f"\n   ⚡ ACTION: DO NOT BUY")
        print(f"   • If holding, consider exiting")
        print(f"   • Look for better opportunities")
        print(f"   • Wait for trend reversal")
    
    print(f"\n{'='*70}")
    print(f"🕐 Analysis Time: {now.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    return result


# ═══════════════════════════════════════════════════════════════════════
#                    SCAN ALL TOKENS (RANKED)
# ═══════════════════════════════════════════════════════════════════════

def scan_all_tokens_live(db_path="market_data.db"):
    """Scan all tokens and rank them by opportunity"""
    now = datetime.now()
    
    print("\n" + "="*70)
    print("🔴 LIVE MARKET SCANNER")
    print("="*70)
    print(f"🕐 Current Time: {now.strftime('%H:%M:%S')}")
    
    if is_market_hours():
        print(f"🟢 Market Status: OPEN")
    else:
        print(f"🔴 Market Status: CLOSED")
    
    print("="*70 + "\n")
    
    # Get all tokens
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT token FROM market_ticks")
    tokens = [row[0] for row in cursor.fetchall()]
    conn.close()
    
    print(f"📊 Scanning {len(tokens)} tokens...\n")
    
    results = []
    
    for token in tokens:
        try:
            print(f"Analyzing {token}...", end=" ")
            result = analyze_live_trend(token, db_path)
            
            if result and "error" not in result:
                results.append({
                    "token": token,
                    "ltp": result['ltp'],
                    "score": result['bullish_score'],
                    "signal": result['overall_signal'],
                    "vwap_diff": result['ltp_vs_vwap'],
                    "recommendation": result['recommendation']
                })
                print("✓")
            else:
                print("✗ (insufficient data)")
                
        except Exception as e:
            print(f"✗ (error: {e})")
    
    # Summary
    if results:
        print("\n" + "="*70)
        print("📊 LIVE MARKET SUMMARY - RANKED BY OPPORTUNITY")
        print("="*70 + "\n")
        
        results.sort(key=lambda x: x['score'], reverse=True)
        
        for i, r in enumerate(results, 1):
            if r['score'] >= 4:
                icon = "🟢"
                action = "BUY NOW"
            elif r['score'] == 3:
                icon = "🟡"
                action = "CAUTIOUS BUY"
            elif r['score'] == 2:
                icon = "🟠"
                action = "WAIT"
            else:
                icon = "🔴"
                action = "AVOID"
            
            print(f"{i}. {icon} Token {r['token']} - {action}")
            print(f"   Price: ₹{r['ltp']} | Score: {r['score']}/5 | vs VWAP: {r['vwap_diff']:+.2f}%\n")
        
        # Best pick
        best = results[0]
        print("="*70)
        print("🏆 TOP PICK FOR RIGHT NOW")
        print("="*70)
        
        if best['score'] >= 4:
            print(f"\n✅ TOKEN {best['token']} - STRONG BUY")
            print(f"   Score: {best['score']}/5")
            print(f"   Price: ₹{best['ltp']}")
            print(f"   This is your best opportunity RIGHT NOW")
        elif best['score'] >= 3:
            print(f"\n⚠️  TOKEN {best['token']} - MODERATE")
            print(f"   Score: {best['score']}/5")
            print(f"   Can consider with caution")
        else:
            print(f"\n❌ NO STRONG OPPORTUNITIES RIGHT NOW")
            print(f"   Best score: {best['score']}/5")
            print(f"   Wait for better setups")
        
        print("="*70 + "\n")
    else:
        print("\n❌ No analyzable data. Market may have just opened.\n")
    
    return results


# ═══════════════════════════════════════════════════════════════════════
#                      INTERACTIVE MODE
# ═══════════════════════════════════════════════════════════════════════

def interactive_mode():
    """Interactive mode - select token and analyze"""
    print("\n" + "="*70)
    print("🔴 LIVE INTRADAY TREND ANALYZER")
    print("="*70)
    
    now = datetime.now()
    print(f"\n🕐 Current Time: {now.strftime('%H:%M:%S')}")
    
    if is_market_hours():
        print(f"🟢 Market: OPEN (Live Analysis Available)")
    else:
        current_time = now.time()
        if current_time < datetime_time(9, 15):
            print(f"🟡 Market: PRE-MARKET (Opens at 09:15)")
        else:
            print(f"🔴 Market: CLOSED (Opens tomorrow at 09:15)")
        print(f"\n💡 You can still analyze latest available data")
    
    # Get tokens from today
    conn = sqlite3.connect("market_data.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT token, COUNT(*) as ticks
        FROM market_ticks 
        WHERE received_at >= ?
        GROUP BY token
        ORDER BY ticks DESC
    """, (get_today_session_start(),))
    
    tokens_data = cursor.fetchall()
    conn.close()
    
    if not tokens_data:
        print("\n❌ No data from today's session!")
        print("   • Make sure ws_client.py is running")
        print("   • Wait for market to open (09:15 AM)\n")
        return
    
    print(f"\n📋 TOKENS WITH TODAY'S DATA ({len(tokens_data)} found):")
    print("="*70)
    
    for i, (token, ticks) in enumerate(tokens_data, 1):
        print(f"{i}. Token: {token} ({ticks:,} ticks today)")
    
    print(f"\n{len(tokens_data) + 1}. 🔍 SCAN ALL TOKENS (Live ranking)")
    print("="*70)
    
    # Get selection
    while True:
        try:
            choice = input(f"\n👉 Select token (1-{len(tokens_data) + 1}) or 'q' to quit: ").strip().lower()
            
            if choice == 'q':
                print("\n👋 Exiting...\n")
                return
            
            choice_num = int(choice)
            
            if choice_num == len(tokens_data) + 1:
                scan_all_tokens_live()
                break
            elif 1 <= choice_num <= len(tokens_data):
                selected_token = tokens_data[choice_num - 1][0]
                analyze_live_trend(selected_token)
                break
            else:
                print(f"❌ Please enter 1-{len(tokens_data) + 1}")
        except ValueError:
            print("❌ Please enter a valid number")
        except KeyboardInterrupt:
            print("\n\n👋 Exiting...\n")
            return


# ═══════════════════════════════════════════════════════════════════════
#                           MAIN
# ═══════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    import sys
    
    print("\n" + "="*70)
    print("     🚀 INTRADAY STOCK TREND ANALYZER")
    print("="*70)
    print("Analyzes live market trends with 5 technical indicators")
    print("Market Hours: 09:15 AM - 3:30 PM")
    print("="*70)
    
    if len(sys.argv) > 1:
        # Command line mode
        if sys.argv[1] == "all":
            scan_all_tokens_live()
        else:
            analyze_live_trend(sys.argv[1])
    else:
        # Interactive mode (default)
        interactive_mode()
