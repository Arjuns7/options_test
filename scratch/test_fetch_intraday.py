import os
from fyers_apiv3 import fyersModel
from datetime import datetime, timedelta

CLIENT_ID = "77QN6WHNT3-100"
ACCESS_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJhdWQiOlsiZDoxIiwiZDoyIiwieDowIiwieDoxIiwieDoyIl0sImF0X2hhc2giOiJnQUFBQUFCcVVHRGdtLVlkUGI1Mk5jVUdpYTNZSFRLckZ6ZWxXSlZLb3d1M3pST2NNOWhTZ2VCckxWN3hxcGx1Q2pHd2N5UXp3TnR6VEg4bkNCaHk5anJkeVlDXzRZMzMyTm1SbDI2OUVpVVVVNm91YkJQQktSUT0iLCJkaXNwbGF5X25hbWUiOiIiLCJvbXMiOiJLMSIsImhzbV9rZXkiOiI1ODRkYWY0MjEzZmFmMzdkYzExYWQ3YjFhMDVmNzVhYmU3MGVkNzEzZjU4ZThlNTUxMzliOTBlNiIsImlzRGRwaUVuYWJsZWQiOiJOIiwiaXNNdGZFbmFibGVkIjoiTiIsImZ5X2lkIjoiRkFLMDQ0NTciLCJhcHBUeXBlIjoxMDAsImV4cCI6MTc4MzcyOTgwMCwiaWF0IjoxNzgzNjUyNTc2LCJpc3MiOiJhcGkuZnllcnMuaW4iLCJuYmYiOjE3ODM2NTI1NzYsInN1YiI6ImFjY2Vzc190b2tlbiJ9.9DQFSyRA-TiOArs0od7dWmNjTx4UnjiYZoqE2470B6Q"

fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=ACCESS_TOKEN)

try:
    data = {
        "symbol": "NSE:NIFTY50-INDEX",
        "resolution": "15",
        "date_format": "1",
        "range_from": (datetime.today() - timedelta(days=2)).strftime('%Y-%m-%d'),
        "range_to": datetime.today().strftime('%Y-%m-%d'),
        "cont_flag": "1"
    }
    res = fyers.history(data=data)
    if res and res.get('s') == 'ok':
        candles = res.get('candles', [])
        print(f"Fetched {len(candles)} candles.")
        if candles:
            print("First candle:", candles[0])
            # Timestamp to datetime
            dt = datetime.fromtimestamp(candles[0][0])
            print("First candle time:", dt.strftime('%Y-%m-%d %H:%M:%S'))
    else:
        print("API Error:", res)
except Exception as e:
    print("Error:", e)
