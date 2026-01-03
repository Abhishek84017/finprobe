import websocket
import json
from db_writer import insert_market_tick
from parse_response import parse_market_data

# ================= CONFIG =================
WS_URL = "wss://smartapisocket.angelone.in/smart-stream"

API_KEY = "YOUR_API_KEY"
FEED_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJ1c2VybmFtZSI6IlAxNzUyNTQiLCJpYXQiOjE3NjczNjgzNTUsImV4cCI6MTc2NzQ1NDc1NX0.lN4OYZH3__Y3578VituZNRu6VUmYVnSil2IPS4BVXxNhQNOSRFkdQ9rJ5hjtcyS51rcBSkd080wxPh9L9TRwhw"

SUBSCRIBE_MODE = 3  # 1=LTP, 2=QUOTE, 3=SNAPQUOTE

def on_open(ws):
    print("WebSocket connected")

    payload = {
        "action": 1,
        "params": {
            "mode": SUBSCRIBE_MODE,
            "tokenList": [
                {
                    "exchangeType": 1,          # NSE_CM
                    "tokens": ["17939", "11536"]
                }
            ]
        }
    }

    ws.send(json.dumps(payload))


def on_message(ws, message):
    if not isinstance(message, bytes):
        return

    try:
        parsed = parse_market_data(message)
        insert_market_tick(parsed)
        print(
            f"[TICK] "
            f"Token={parsed['token']} | "
            f"Time={parsed['exchange_timestamp_human']} | "
            f"LTP={parsed['ltp']:.2f}"
        )
    except Exception as e:
        print("Parse/DB error:", e)


def on_error(ws, error):
    print("WebSocket error:", error)


def on_close(ws, close_status_code, close_msg):
    print("WebSocket closed", close_status_code, close_msg)


def start():
    headers = {
        # "x-api-key": API_KEY,
        "x-feed-token": FEED_TOKEN
    }

    ws = websocket.WebSocketApp(
        WS_URL,
        header=[f"{k}: {v}" for k, v in headers.items()],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    ws.run_forever(ping_interval=20, ping_timeout=10)


if __name__ == "__main__":
    start()
