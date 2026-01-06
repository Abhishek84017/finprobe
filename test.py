from calculate_indecator import calculate_intraday_indicators
from fetch_data import fetch_token_data


df = fetch_token_data(
    db_path="market_data.db",
    token="17939",
    exchange_type=1
)

result = calculate_intraday_indicators(df)
print(result)
