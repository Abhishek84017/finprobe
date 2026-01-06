import sqlite3
import pandas as pd

def fetch_token_data(db_path, token, exchange_type, limit=5000):
    conn = sqlite3.connect(db_path)

    query = """
        SELECT
            exchange_timestamp,
            ltp,
            last_traded_qty,
            volume,
            open,
            high,
            low,
            close
        FROM market_ticks
        WHERE token = ?
          AND exchange_type = ?
          AND exchange_timestamp_human <= "2026-01-05 15:00:00"
        ORDER BY exchange_timestamp ASC
        LIMIT ?
    """

    df = pd.read_sql_query(
        query,
        conn,
        params=(token, exchange_type, limit)
    )

    conn.close()
    return df
