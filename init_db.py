import sqlite3

conn = sqlite3.connect("market_data.db")
cur = conn.cursor()

# ---------------- TABLE ----------------
cur.execute("""
CREATE TABLE IF NOT EXISTS market_ticks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,

    token TEXT,
    exchange_type INTEGER,
    subscription_mode INTEGER,

    sequence_number INTEGER,
    exchange_timestamp INTEGER,
    exchange_timestamp_human TEXT,

    ltp REAL,

    last_traded_qty INTEGER,
    avg_traded_price REAL,
    volume INTEGER,
    total_buy_qty REAL,
    total_sell_qty REAL,

    open REAL,
    high REAL,
    low REAL,
    close REAL,

    last_traded_time INTEGER,
    open_interest INTEGER,
    oi_change_percent REAL,

    upper_circuit REAL,
    lower_circuit REAL,
    week_52_high REAL,
    week_52_low REAL,

    received_at INTEGER
);
""")

# ---------------- INDEXES ----------------
# For fast queries
cur.execute("""
CREATE INDEX IF NOT EXISTS idx_token_ts
ON market_ticks (token, exchange_timestamp);
""")

# 🔒 CRITICAL: prevent duplicate ticks
cur.execute("""
CREATE UNIQUE INDEX IF NOT EXISTS uniq_token_exchange_ts
ON market_ticks (token, exchange_timestamp);
""")

# ---------------- PERFORMANCE ----------------
cur.execute("PRAGMA journal_mode=WAL;")
cur.execute("PRAGMA synchronous=NORMAL;")

conn.commit()
conn.close()

print("SQLite DB initialized with deduplication")
