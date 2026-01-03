import json
import struct
from typing import Dict, Any, List


# ================= Binary Reader =================
class BinaryReader:
    __slots__ = ("data", "offset")

    def __init__(self, data: bytes):
        self.data = data
        self.offset = 0

    def read(self, fmt: str):
        value = struct.unpack_from(fmt, self.data, self.offset)[0]
        self.offset += struct.calcsize(fmt)
        return value

    def skip(self, size: int):
        self.offset += size

    def read_int8(self):
        return self.read("<b")

    def read_int16(self):
        return self.read("<h")

    def read_int32(self):
        return self.read("<i")

    def read_int64(self):
        return self.read("<q")

    def read_double(self):
        return self.read("<d")

    def read_string(self, length: int):
        raw = self.data[self.offset:self.offset + length]
        self.offset += length
        return raw.split(b"\x00", 1)[0].decode("utf-8")


# ================= Price Normalizer =================
def normalize_price(value: int, exchange_type: int) -> float:
    if value is None:
        return None
    # Currency (CDE)
    if exchange_type == 13:
        return value / 10_000_000
    # All others
    return value / 100


# ================= Best Five =================
def parse_best_five(reader: BinaryReader, exchange_type: int) -> List[Dict[str, Any]]:
    result = []

    for _ in range(10):
        side_flag = reader.read_int16()
        qty = reader.read_int64()
        raw_price = reader.read_int64()
        orders = reader.read_int16()

        result.append({
            "side": "buy" if side_flag == 1 else "sell",
            "quantity": qty,
            "price": normalize_price(raw_price, exchange_type),
            "orders": orders
        })

    return result


# ================= Main Parser =================
def parse_market_data(binary_data: bytes) -> Dict[str, Any]:
    r = BinaryReader(binary_data)
    out: Dict[str, Any] = {}

    # ---- Header ----
    out["subscription_mode"] = r.read_int8()
    out["exchange_type"] = r.read_int8()
    out["token"] = r.read_string(25)
    out["sequence_number"] = r.read_int64()
    out["exchange_timestamp"] = r.read_int64()

    # ---- LTP ----
    raw_ltp = r.read_int32()
    out["ltp"] = normalize_price(raw_ltp, out["exchange_type"])
    r.skip(4)  # padding

    if out["subscription_mode"] == 1:
        return out

    # ---- Quote ----
    out["last_traded_qty"] = r.read_int64()

    raw_avg_price = r.read_int64()
    out["avg_traded_price"] = normalize_price(raw_avg_price, out["exchange_type"])

    out["volume"] = r.read_int64()
    out["total_buy_qty"] = r.read_double()
    out["total_sell_qty"] = r.read_double()

    raw_open = r.read_int64()
    raw_high = r.read_int64()
    raw_low = r.read_int64()
    raw_close = r.read_int64()

    out["open"] = normalize_price(raw_open, out["exchange_type"])
    out["high"] = normalize_price(raw_high, out["exchange_type"])
    out["low"] = normalize_price(raw_low, out["exchange_type"])
    out["close"] = normalize_price(raw_close, out["exchange_type"])

    if out["subscription_mode"] == 2:
        return out

    # ---- Snap Quote ----
    out["last_traded_time"] = r.read_int64()
    out["open_interest"] = r.read_int64()
    out["oi_change_percent"] = r.read_double()

    out["best_five"] = parse_best_five(r, out["exchange_type"])

    raw_upper = r.read_int64()
    raw_lower = r.read_int64()
    raw_52_high = r.read_int64()
    raw_52_low = r.read_int64()

    out["upper_circuit"] = normalize_price(raw_upper, out["exchange_type"])
    out["lower_circuit"] = normalize_price(raw_lower, out["exchange_type"])
    out["week_52_high"] = normalize_price(raw_52_high, out["exchange_type"])
    out["week_52_low"] = normalize_price(raw_52_low, out["exchange_type"])

    return out


# ---------- Example ----------
if __name__ == "__main__":
    raw = (
        "\u0002\u000117939\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u00007Ðs\u0000\u0000\u0000\u0000\u0000Ú\u001ds\u0001\u0000\u0000ÕÊ\u0000\u0000\u0000\u0000\u0000\u0000\u0011\u0001\u0000\u0000\u0000\u0000\u0000\u0000Í\u0000\u0000\u0000\u0000\u0000\u0000\u000bqB\u0003\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0000\u0004+AA\u0000\u0000\u0000\u0013\u0019RA\bÏ\u0000\u0000\u0000\u0000\u0000\u0000\u0019Ò\u0000\u0000\u0000\u0000\u0000\u0000,É\u0000\u0000\u0000\u0000\u0000\u0000WÐ\u0000\u0000\u0000\u0000\u0000\u0000"
    ).encode("latin1")

    parsed = parse_market_data(raw)
    print(json.dumps(parsed, indent=2))
