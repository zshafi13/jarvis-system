import yfinance as yf
import requests
from datetime import datetime, timedelta

# Extended common-name to ticker mapping
symbol_map = {
    "tesla": "TSLA",
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "google": "GOOG",
    "alphabet": "GOOG",
    "meta": "META",
    "facebook": "META",
    "amazon": "AMZN",
    "netflix": "NFLX",
    "intel": "INTC",
    "paypal": "PYPL",
    "amd": "AMD",
    "qualcomm": "QCOM"
}

def get_stock(symbol="TSLA"):
    try:
        symbol = symbol.lower()
        symbol = symbol_map.get(symbol, symbol.upper())

        stock = yf.Ticker(symbol)
        data = stock.history(period="1d")

        if data.empty:
            return f"Couldn't find stock data for {symbol.upper()}."

        latest = data.iloc[-1]
        price = latest["Close"]
        change = latest["Close"] - latest["Open"]
        change_percent = (change / latest["Open"]) * 100
        direction = "up" if change > 0 else "down" if change < 0 else "unchanged"

        return f"{symbol.upper()} is at ${price:.2f}, {direction} {abs(change_percent):.2f}% today."

    except Exception as e:
        print("[Stock error]:", e)
        return "Couldn't fetch stock data right now, sir."