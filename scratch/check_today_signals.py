import os
import pandas as pd
from datetime import datetime
from fyers_apiv3 import fyersModel

CLIENT_ID = "77QN6WHNT3-100"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIiwieDoyIl0sImF0X2hhc2giOiJnQUFBQUFCcVR3d215LWY5YzNrUWZzVk5pcTdpaEVXRmxYMFg2Y0ZRc0llbjFHUlpyNzIwbjFqbmdGcV9qeER5NTBBMGRkb3p2VTl1dFNkRmFWekR1WTdYRUZQaXc0NjFENmlRYlNkRnhpUVRKYnFRLU1lQlpVOD0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiJkY2JiMDk1YzBhM2ZhNmQzM2QxMTJjNGRlN2Y4MTM0YTVjODFiMThhMzQ0NTkwYTBiZDlkODRmOCIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImZ5X2lkIjoiRkFLMDQ0NTciLCJhcHBUeXBlIjoxMDAsImV4cCI6MTc4MzY0MzQwMCwiaWF0IjoxNzgzNTY1MzUwLCJpc3MiOiJhcGkuZnllcnMuaW4iLCJuYmYiOjE3ODM1NjUzNTAsInN1YiI6ImFjY2Vzc190b2tlbiJ9.5gc3pPjA8QuySUY0XG1IZbqzyDTJMd17Vs_MUsFnPa0"

fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=ACCESS_TOKEN)

def get_live_nifty_candles():
    data = {
        "symbol": "NSE:NIFTY50-INDEX",
        "resolution": "15",
        "date_format": "1",
        "range_from": datetime.today().strftime('%Y-%m-%d'),
        "range_to": datetime.today().strftime('%Y-%m-%d'),
        "cont_flag": "1"
    }
    try:
        response = fyers.history(data=data)
        if response and response.get('s') == 'ok':
            df = pd.DataFrame(response['candles'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            df['datetime'] = df['datetime'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
            return df
        else:
            print("Failed response:", response)
    except Exception as e:
        print(f"Error fetching candles: {e}")
    return None

df = get_live_nifty_candles()
if df is not None and not df.empty:
    df['EMA'] = df['close'].ewm(span=9, adjust=False).mean()
    print("Today's Nifty 15-Min Candles:")
    print("=" * 80)
    for idx, row in df.iterrows():
        time_str = row['datetime'].strftime('%I:%M %p')
        close = row['close']
        ema = row['EMA']
        position = "Above EMA" if close > ema else "Below EMA"
        print(f"Time: {time_str} | Nifty Close: {close:.2f} | 9 EMA: {ema:.2f} | Status: {position}")
    print("=" * 80)
else:
    print("No candles fetched.")
