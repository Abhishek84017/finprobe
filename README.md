# 📊 Live Intraday Stock Trend Analyzer

Analyze real-time stock market trends during trading hours (09:15 - 15:30) with **5 technical indicators** and get clear **BUY/AVOID** signals for intraday trading.

---

## 🚀 Quick Start

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Setup Database (First Time Only)
```bash
python3 init_db.py
```

### 3. Start Data Collection (Run Before Market Opens)
```bash
python3 ws_client.py
```
*Keep this running throughout market hours (09:15 - 15:30)*

### 4. Analyze Trends (Anytime During Market)
```bash
python3 live_trend_analyzer.py
```
*Select token or scan all for ranked opportunities*

---

## 📊 What It Does

### **5 Technical Indicators Analyzed:**

1. **Volume & Value** - Detects institutional buying/selling
2. **VWAP** - Shows buyer/seller control
3. **Market Structure** - Identifies Higher High + Higher Low patterns
4. **EMA 20 & 50** - Trend direction confirmation
5. **RSI** - Momentum indicator (55-70 is optimal)

### **Bullish Score System:**
- **Score 5/5 or 4/5** → 🟢 **STRONG BUY** - All indicators aligned
- **Score 3/5** → 🟡 **CAUTIOUS BUY** - Most indicators positive
- **Score 2/5** → 🟠 **WAIT** - Mixed signals
- **Score 0/5 or 1/5** → 🔴 **AVOID** - Weak/bearish signals

---

## 💻 Usage

### **Interactive Mode (Recommended)**
```bash
python3 live_trend_analyzer.py
```
Shows menu → Select token → Get analysis

### **Scan All Tokens**
```bash
python3 live_trend_analyzer.py all
```
Analyzes all tokens and ranks them by opportunity

### **Analyze Specific Token**
```bash
python3 live_trend_analyzer.py 17939
```
Direct analysis of token 17939

---

## 📈 Example Output

```
═══════════════════════════════════════════════════════════════════════
📊 LIVE MARKET TREND ANALYSIS
═══════════════════════════════════════════════════════════════════════
🕐 Current Time: 14:30:00
📈 Token: 17939
🟢 Market Status: OPEN (Trading Hours)
═══════════════════════════════════════════════════════════════════════

📸 CURRENT MARKET SNAPSHOT
═══════════════════════════════════════════════════════════════════════
💰 Current Price (LTP): ₹525.50
📊 VWAP: ₹523.20 (+0.44%)
📈 Today's Range: ₹518.00 - ₹528.00
🔄 Volume: 15,234

═══════════════════════════════════════════════════════════════════════
🎯 LIVE TECHNICAL INDICATORS
═══════════════════════════════════════════════════════════════════════

✅ 1. VOLUME & VALUE
   Current: 15,234 | Avg: 12,450
   📊 HIGH_VOLUME_HIGH_VALUE

✅ 2. VWAP POSITION
   Price: ₹525.50 | VWAP: ₹523.20
   📊 PRICE_ABOVE_VWAP
   💡 BUYERS controlling the price

✅ 3. MARKET STRUCTURE
   Previous 5m: High ₹524, Low ₹522
   Current 5m:  High ₹526, Low ₹524
   📊 BULLISH_HH_HL

✅ 4. EMA TREND
   EMA 20: ₹524.50 | EMA 50: ₹522.80
   📊 EMA20_ABOVE_EMA50

✅ 5. RSI MOMENTUM
   RSI: 65.50
   📊 RSI_BULLISH_ZONE

═══════════════════════════════════════════════════════════════════════
🎯 LIVE TREND VERDICT
═══════════════════════════════════════════════════════════════════════

📊 BULLISH SCORE: 5/5
🎯 TREND: STRONG_BULLISH

═══════════════════════════════════════════════════════════════════════
💼 TRADING DECISION (RIGHT NOW)
═══════════════════════════════════════════════════════════════════════

🟢 STRONG BULLISH - BUY SIGNAL
   ✅ All indicators are aligned positively
   ✅ Strong institutional buying activity
   ✅ Price above VWAP (buyers in control)
   ✅ Clear uptrend structure forming

   💰 TRADE SETUP:
   📍 Entry: ₹525.50 (Current Price)
   🛑 Stop Loss: ₹523.20 (Below VWAP)
   🎯 Target 1: ₹530.76 (1% profit)
   🎯 Target 2: ₹533.59 (1.5% profit)

   ⚡ ACTION: Consider BUYING now for intraday
```

---

## 📁 Project Structure

### **Essential Files:**

| File | Purpose |
|------|---------|
| `live_trend_analyzer.py` | 🌟 **MAIN TOOL** - Complete trend analysis |
| `ws_client.py` | Data collection from WebSocket |
| `db_writer.py` | Database operations |
| `parse_response.py` | Parse WebSocket data |
| `init_db.py` | Database initialization |
| `requirements.txt` | Python dependencies |
| `market_data.db` | SQLite database |

---

## ⚙️ Configuration

Edit tokens in `ws_client.py`:

```python
"tokens": [
    "17939",   # Your token 1
    "17851",   # Your token 2
    "17971",   # Your token 3
    # Add more...
]
```

---

## 📝 Daily Workflow

### **Morning (Before 9:15 AM):**
```bash
python3 ws_client.py
```
Leave it running to collect data

### **During Market (9:15 AM - 3:30 PM):**
```bash
python3 live_trend_analyzer.py
```
Check trends anytime:
- **10:00 AM** - After initial volatility
- **11:30 AM** - Mid-morning check
- **2:00 PM** - Afternoon momentum
- **3:00 PM** - Final hour opportunities

### **What to Look For:**
- ✅ Score 4-5 only
- ✅ Price above VWAP
- ✅ High volume + high value
- ✅ EMA 20 > EMA 50
- ✅ RSI 55-70

---

## 💡 Trading Tips

### **✅ DO:**
- Only trade Score 4-5 (Strong Bullish)
- Always use stop loss (below VWAP)
- Target 1-2% profit for intraday
- Exit immediately if stop loss hit
- Wait 60-90 min after market opens

### **❌ DON'T:**
- Never trade Score ≤ 2
- Never ignore VWAP signal
- Don't force trades
- Don't hold losing positions
- Don't trade right at market open

---

## 🔧 Requirements

- Python 3.9+
- pandas
- numpy
- websocket-client
- SQLite3

Install all:
```bash
pip install -r requirements.txt
```

---

## 📊 How Indicators Work

### 1. **Volume & Value**
- **High Vol + High Value** → Institutions buying (Good)
- **High Vol + Low Value** → Retail activity (Weak)
- **Price Up + Low Vol** → Move may not sustain (Risky)

### 2. **VWAP**
- **Price > VWAP** → Buyers control (Bullish)
- **Price < VWAP** → Sellers control (Bearish)

### 3. **Market Structure**
- **Higher High + Higher Low** → Uptrend (Bullish)
- **No HH/HL** → No clear trend (Neutral/Bearish)

### 4. **EMA Crossover**
- **EMA 20 > EMA 50** → Short-term uptrend (Bullish)
- **EMA 20 < EMA 50** → Short-term downtrend (Bearish)

### 5. **RSI**
- **55-70** → Good momentum (Bullish)
- **> 70** → Overbought (Risk)
- **< 55** → Weak momentum (Bearish)

---

## ❓ Troubleshooting

**"No data from today's session"**
- Make sure `ws_client.py` is running
- Check if market is open (09:15-15:30)
- Verify FEED_TOKEN in ws_client.py is valid

**"Not enough 5m candles"**
- Need at least 75-90 minutes of data
- Wait for more data to accumulate
- Market needs to run longer

**"WebSocket ping/pong timed out"**
- Network issue
- Script will auto-reconnect (max 5 attempts)
- Check internet connection

---

## 📞 Support

Edit tokens and feed token in `ws_client.py`:
```python
FEED_TOKEN = "your_feed_token_here"
```

Get feed token from Angel One SmartAPI authentication.

---

## ⚡ Quick Commands

```bash
# Setup (first time only)
python3 init_db.py

# Start data collection (keep running)
python3 ws_client.py

# Analyze trends (interactive)
python3 live_trend_analyzer.py

# Scan all tokens
python3 live_trend_analyzer.py all

# Analyze specific token
python3 live_trend_analyzer.py 17939
```

---

## 🎯 Success Tips

1. **Patience** - Wait for Score 4-5 signals
2. **Discipline** - Always use stop loss
3. **Timing** - Best trades after 10:00 AM
4. **Risk Management** - Exit losers quickly
5. **Consistency** - Follow the signals, don't override

---

**Happy Trading! 📈✨**

*Remember: This tool assists your decisions. Always use proper risk management.*
