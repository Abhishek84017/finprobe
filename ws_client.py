import websocket
import json
import time
from db_writer import insert_market_tick
from parse_response import parse_market_data

# ================= CONFIG =================
WS_URL = "wss://smartapisocket.angelone.in/smart-stream"

API_KEY = "YOUR_API_KEY"
FEED_TOKEN = "eyJhbGciOiJIUzUxMiJ9.eyJ1c2VybmFtZSI6IlAxNzUyNTQiLCJpYXQiOjE3Njg4ODQ3NzAsImV4cCI6MTc2ODk3MTE3MH0.iu6244ZttG7vS5jx7NZitf3TTvpUi2DDR6piDYZokeVBhGO0gkpMPbe04EdbrdJ1BgjFFjB84oKpAMfBL50OKQ"

SUBSCRIBE_MODE = 3  # 1=LTP, 2=QUOTE, 3=SNAPQUOTE

# Reconnection settings
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY = 5  # Initial delay in seconds
reconnect_count = 0

def on_open(ws):
    global reconnect_count
    reconnect_count = 0  # Reset reconnection counter on successful connection
    print("WebSocket connected successfully!")

    payload = {
        "action": 1,
        "params": {
            "mode": SUBSCRIBE_MODE,
            "tokenList": [
                {
                    "exchangeType": 1,          # NSE_CM
                    "tokens": [
                        "17939",
                        "17851",
                        "17971",
                        "18035",
                        "17801"
                    ]
                }
            ]
        }
    }

    ws.send(json.dumps(payload))
    print(f"Subscribed to tokens in mode {SUBSCRIBE_MODE}")


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
    print(f"WebSocket error: {error}")


def on_close(ws, close_status_code, close_msg):
    global reconnect_count
    print(f"WebSocket closed - Status: {close_status_code}, Message: {close_msg}")
    
    if reconnect_count < MAX_RECONNECT_ATTEMPTS:
        reconnect_count += 1
        delay = RECONNECT_DELAY * (2 ** (reconnect_count - 1))  # Exponential backoff
        print(f"Reconnecting in {delay} seconds... (Attempt {reconnect_count}/{MAX_RECONNECT_ATTEMPTS})")
        time.sleep(delay)
        start()
    else:
        print("Max reconnection attempts reached. Exiting.")


def start():
    headers = {
        # "x-api-key": API_KEY,
        "x-feed-token": FEED_TOKEN
    }

    print(f"Connecting to {WS_URL}...")
    ws = websocket.WebSocketApp(
        WS_URL,
        header=[f"{k}: {v}" for k, v in headers.items()],
        on_open=on_open,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
    )

    # Increased timeout values to prevent premature disconnections
    # ping_interval=40 means send a ping every 40 seconds
    # ping_timeout=30 means wait up to 30 seconds for a pong response
    # Note: ping_interval MUST be greater than ping_timeout
    ws.run_forever(
        ping_interval=40,
        ping_timeout=30,
        skip_utf8_validation=True  # Improves performance for binary data
    )


if __name__ == "__main__":
    start()
