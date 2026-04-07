import os
import requests
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
from app import settings

load_dotenv()

UPSTOX_API_URL = "https://api.upstox.com/v2"

def get_upstox_token():
    return os.getenv("sandbox_token")

def fetch_historical_data(instrument_key: str, days_back: int = 60) -> pd.DataFrame:
    """
    Fetches historical daily candle data from Upstox AP for a given instrument.
    For swing trading, we typically need 40-60 days of data to calculate the 20-day SMA and RSI accurately.
    """
    token = get_upstox_token()
    if not token:
        raise ValueError("Sandbox token not found in .env file")

    headers = {
        'Accept': 'application/json',
        'Authorization': f'Bearer {token}'
    }
    
    # Calculate dates formatting as YYYY-MM-DD
    to_date = datetime.now()
    if hasattr(settings, 'BACKTEST_TARGET_DATE') and settings.BACKTEST_TARGET_DATE:
        try:
            to_date = datetime.strptime(settings.BACKTEST_TARGET_DATE, "%Y-%m-%d")
        except ValueError:
            pass # Fallback to today if invalid format
            
    from_date = to_date - timedelta(days=days_back)
    
    to_date_str = to_date.strftime("%Y-%m-%d")
    from_date_str = from_date.strftime("%Y-%m-%d")
    
    url = f"{UPSTOX_API_URL}/historical-candle/{instrument_key}/day/{to_date_str}/{from_date_str}"
    
    response = requests.get(url, headers=headers)
    
    if response.status_code != 200:
        print(f"Error fetching data for {instrument_key}: {response.text}")
        return pd.DataFrame()
        
    data = response.json()
    if "data" not in data or not data["data"] or "candles" not in data["data"]:
        return pd.DataFrame()
        
    candles = data["data"]["candles"]
    
    # Upstox returns data as: [timestamp, open, high, low, close, volume, open_interest]
    df = pd.DataFrame(candles, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume', 'open_interest'])
    
    # Data is sometimes returned in descending order (latest first), so we sort it
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.sort_values('timestamp').reset_index(drop=True)
    
    # Convert types to numeric
    cols_to_convert = ['open', 'high', 'low', 'close', 'volume']
    for col in cols_to_convert:
        df[col] = pd.to_numeric(df[col], errors='coerce')
        
    return df
