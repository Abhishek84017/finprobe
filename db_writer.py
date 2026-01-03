import sqlite3
import time
from threading import Lock

DB_FILE = "market_data.db"
_lock = Lock()

def get_connection():
    conn = sqlite3.connect(DB_FILE, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn

_conn = get_connection()
_cur = _conn.cursor()

def insert_market_tick(data: dict):
    with _lock:
        _cur.execute("""
            INSERT OR IGNORE INTO market_ticks (
                token, exchange_type, subscription_mode,
                sequence_number, exchange_timestamp, exchange_timestamp_human,
                ltp,

                last_traded_qty, avg_traded_price, volume,
                total_buy_qty, total_sell_qty,

                open, high, low, close,

                last_traded_time, open_interest, oi_change_percent,

                upper_circuit, lower_circuit, week_52_high, week_52_low,

                received_at
            )
            VALUES (
                ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?,
                ?, ?, ?, ?,
                ?, ?, ?,
                ?, ?, ?, ?,
                ?
            )
        """, (
            data.get("token"),
            data.get("exchange_type"),
            data.get("subscription_mode"),

            data.get("sequence_number"),
            data.get("exchange_timestamp"),
            data.get("exchange_timestamp_human"),

            data.get("ltp"),

            data.get("last_traded_qty"),
            data.get("avg_traded_price"),
            data.get("volume"),
            data.get("total_buy_qty"),
            data.get("total_sell_qty"),

            data.get("open"),
            data.get("high"),
            data.get("low"),
            data.get("close"),

            data.get("last_traded_time"),
            data.get("open_interest"),
            data.get("oi_change_percent"),

            data.get("upper_circuit"),
            data.get("lower_circuit"),
            data.get("week_52_high"),
            data.get("week_52_low"),

            int(time.time() * 1000)
        ))

        _conn.commit()
