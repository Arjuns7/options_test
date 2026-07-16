import os
import time
import pandas as pd
import numpy as np
import threading
import urllib.request
import urllib.parse
import json
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from fyers_apiv3 import fyersModel

# --- Telegram Credentials ---
TELEGRAM_BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")

def send_telegram_message(message):
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "Markdown"
    }).encode("utf-8")
    
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=10) as res:
            res.read()
    except Exception as e:
        print(f"⚠️ Failed to send Telegram alert: {e}")

# --- Configuration ---
CLIENT_ID = "77QN6WHNT3-100"
SECRET_ID = os.environ.get("FYERS_SECRET_ID", "DIJN19NKWM")
FYERS_PIN = os.environ.get("FYERS_PIN")
ACCESS_TOKEN = None                       # Loaded dynamically
INDEX_SYMBOL = "NSE:NIFTY50-INDEX"        # Symbol for Nifty 50 Spot
EMA_PERIOD = 9
LOTS_MULTIPLIER = 2                       # Traded quantity multiplier
STOP_LOSS_PCT = 0.15                      # 15% Stop Loss (Optimal)
TARGET_PROFIT_PCT = 0.60                  # 60% Target Profit (Optimal)
ADX_FILTER_THRESHOLD = 25                 # ADX > 25 Trend Strength Filter

# --- Absolute File Paths ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TOKEN_DIR = os.environ.get("FYERS_TOKEN_DIR", BASE_DIR)
if not os.path.exists(TOKEN_DIR):
    try:
        os.makedirs(TOKEN_DIR, exist_ok=True)
    except Exception as e:
        print(f"⚠️ Error creating token directory {TOKEN_DIR}: {e}")
        TOKEN_DIR = BASE_DIR

ACCESS_TOKEN_FILE = os.path.join(TOKEN_DIR, "access_token.txt")
REFRESH_TOKEN_FILE = os.path.join(TOKEN_DIR, "refresh_token.txt")
LOG_FILE = os.path.join(TOKEN_DIR, "fyers_paper_trades.csv")

# --- Initialize Fyers Client as Global Variable ---
fyers = None

# --- State Variables ---
active_trade = None
session_authorized = False                # Tracks if API session is successfully connected

# --- Helper function to render HTML responses ---
def get_portal_html(status_class, status_text):
    auth_url = f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={CLIENT_ID}&redirect_uri=https%3A%2F%2F127.0.0.1%3A5000&response_type=code&state=None"
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Fyers Trading Bot Portal</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            background-color: #0b0f19;
            color: #f3f4f6;
            font-family: 'Outfit', -apple-system, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }}
        .card {{
            background: rgba(17, 24, 39, 0.7);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 32px;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            text-align: center;
        }}
        h1 {{
            font-size: 24px;
            margin-top: 0;
            margin-bottom: 8px;
            background: linear-gradient(135deg, #60a5fa, #3b82f6);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }}
        p {{
            color: #9ca3af;
            font-size: 14px;
            margin-bottom: 24px;
        }}
        .status-badge {{
            display: inline-block;
            padding: 6px 12px;
            border-radius: 20px;
            font-size: 12px;
            font-weight: 600;
            margin-bottom: 24px;
        }}
        .status-active {{
            background: rgba(16, 185, 129, 0.1);
            color: #34d399;
            border: 1px solid rgba(16, 185, 129, 0.2);
        }}
        .status-waiting {{
            background: rgba(239, 68, 68, 0.1);
            color: #f87171;
            border: 1px solid rgba(239, 68, 68, 0.2);
        }}
        input[type="text"] {{
            width: 100%;
            padding: 12px;
            background: #1f2937;
            border: 1px solid rgba(255, 255, 255, 0.1);
            border-radius: 8px;
            color: #ffffff;
            box-sizing: border-box;
            margin-bottom: 16px;
            font-size: 14px;
        }}
        input[type="text"]:focus {{
            outline: none;
            border-color: #3b82f6;
        }}
        button {{
            width: 100%;
            padding: 12px;
            background: #2563eb;
            color: #ffffff;
            border: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            cursor: pointer;
            transition: background 0.2s;
        }}
        button:hover {{
            background: #1d4ed8;
        }}
        a {{
            color: #3b82f6;
            text-decoration: none;
            font-weight: 600;
        }}
        a:hover {{
            text-decoration: underline;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>Fyers Algo Trading Portal</h1>
        <p>System status and session re-authorization dashboard.</p>
        <div class="status-badge {status_class}">{status_text}</div>
        
        <div style="margin-bottom: 20px; font-size: 14px;">
            👉 First, click here to log in: <a href="{auth_url}" target="_blank">Fyers Authentication Link</a>
        </div>
        
        <form method="POST" action="/submit">
            <input type="text" name="redirect_url" placeholder="Paste Fyers Redirected URL here..." required>
            <button type="submit">Submit Authorization URL</button>
        </form>
    </div>
</body>
</html>"""

def get_result_html(is_success, message):
    status_class = "status-active" if is_success else "status-waiting"
    status_text = "SUCCESS" if is_success else "ERROR"
    return f"""<!DOCTYPE html>
<html>
<head>
    <title>Fyers Trading Bot Portal</title>
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {{
            background-color: #0b0f19;
            color: #f3f4f6;
            font-family: 'Outfit', -apple-system, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
        }}
        .card {{
            background: rgba(17, 24, 39, 0.7);
            backdrop-filter: blur(12px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 16px;
            padding: 32px;
            width: 90%;
            max-width: 500px;
            box-shadow: 0 10px 30px rgba(0, 0, 0, 0.5);
            text-align: center;
        }}
        h1 {{
            font-size: 24px;
            margin-top: 0;
            margin-bottom: 8px;
            color: {"#34d399" if is_success else "#f87171"};
        }}
        p {{
            color: #d1d5db;
            font-size: 16px;
            margin-bottom: 24px;
            line-height: 1.5;
        }}
        .btn {{
            display: inline-block;
            padding: 10px 20px;
            background: #2563eb;
            color: #ffffff;
            text-decoration: none;
            border-radius: 8px;
            font-weight: 600;
            font-size: 14px;
            transition: background 0.2s;
        }}
        .btn:hover {{
            background: #1d4ed8;
        }}
    </style>
</head>
<body>
    <div class="card">
        <h1>{status_text}</h1>
        <p>{message}</p>
        <a href="/" class="btn">Back to Dashboard</a>
    </div>
</body>
</html>"""

# --- Background HTTP Health Check & Web Re-Authorization Server ---
class HealthCheckHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/":
            self.send_response(200)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            status_class = "status-active" if session_authorized else "status-waiting"
            active_trade_str = "Active Trade Open" if active_trade is not None else "No Active Trades"
            status_text = f"ACTIVE ({active_trade_str})" if session_authorized else "WAITING FOR MANUAL AUTHORIZATION"
            html = get_portal_html(status_class, status_text)
            self.wfile.write(html.encode('utf-8'))
        else:
            # Traditional simple text health check for Railway probes
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            status_msg = f"OK - Fyers Paper Trading Active. Session Authorized: {session_authorized}. Active Trade: {active_trade is not None}"
            self.wfile.write(status_msg.encode('utf-8'))
            
    def do_POST(self):
        if self.path == "/submit":
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length).decode('utf-8')
            params = urllib.parse.parse_qs(post_data)
            redirect_url = params.get('redirect_url', [None])[0]
            
            if redirect_url:
                auth_code = None
                if "auth_code=" in redirect_url:
                    try:
                        auth_code = redirect_url.split("auth_code=")[1].split("&")[0]
                    except Exception:
                        pass
                else:
                    auth_code = redirect_url.strip()
                    
                if auth_code:
                    success, msg = exchange_auth_code_for_tokens(auth_code)
                    if success:
                        self.send_response(200)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(get_result_html(True, "Fyers Session successfully authorized! The trading bot is now active and scanning for signals.").encode('utf-8'))
                        return
                    else:
                        self.send_response(400)
                        self.send_header("Content-type", "text/html")
                        self.end_headers()
                        self.wfile.write(get_result_html(False, f"Fyers Token exchange failed: {msg}").encode('utf-8'))
                        return
            
            self.send_response(400)
            self.send_header("Content-type", "text/html")
            self.end_headers()
            self.wfile.write(get_result_html(False, "Invalid submission. Please enter a valid redirect URL or Auth Code.").encode('utf-8'))
            
    def log_message(self, format, *args):
        # Suppress logging GET/POST requests to clean up terminal logs
        return

def exchange_auth_code_for_tokens(auth_code):
    global fyers, ACCESS_TOKEN, session_authorized
    try:
        session = fyersModel.SessionModel(
            client_id=CLIENT_ID,
            secret_key=SECRET_ID,
            redirect_uri="https://127.0.0.1:5000",
            response_type="code",
            grant_type="authorization_code"
        )
        session.set_token(auth_code)
        response = session.generate_token()
        
        if response and response.get('s') == 'ok':
            access_token = response.get('access_token')
            refresh_token = response.get('refresh_token')
            
            # Save locally
            with open(ACCESS_TOKEN_FILE, "w") as f:
                f.write(access_token)
            if refresh_token:
                with open(REFRESH_TOKEN_FILE, "w") as f:
                    f.write(refresh_token)
                    
            ACCESS_TOKEN = access_token
            fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=access_token, log_path=os.getcwd())
            session_authorized = True
            send_telegram_message("✅ *Fyers Session successfully authorized!* The trading bot is now ACTIVE.")
            print("✅ Manual web authentication successful! Session client active.")
            return True, "Success"
        else:
            return False, str(response)
    except Exception as e:
        return False, str(e)

def initialize_fyers_session():
    global fyers, ACCESS_TOKEN, session_authorized
    
    access_token = None
    refresh_token = None
    
    if os.path.exists(ACCESS_TOKEN_FILE):
        with open(ACCESS_TOKEN_FILE, "r") as f:
            access_token = f.read().strip()
            
    if os.path.exists(REFRESH_TOKEN_FILE):
        with open(REFRESH_TOKEN_FILE, "r") as f:
            refresh_token = f.read().strip()
            
    # Step 1: Verify current access token
    if access_token:
        fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=access_token, log_path=os.getcwd())
        try:
            # Use history call to verify full token authorization validity
            from_date = (datetime.today() - timedelta(days=2)).strftime('%Y-%m-%d')
            res = fyers.history(data={
                "symbol": INDEX_SYMBOL,
                "resolution": "15",
                "date_format": "1",
                "range_from": from_date,
                "range_to": datetime.today().strftime('%Y-%m-%d'),
                "cont_flag": "1"
            })
            if res and res.get('s') == 'ok':
                print("✅ Found active and valid Fyers session token.")
                ACCESS_TOKEN = access_token
                session_authorized = True
                return True
            else:
                print(f"⚠️ Session validation returned error response: {res}")
        except Exception as e:
            print(f"⚠️ Session validation failed with exception: {e}")
            
    # Step 2: Attempt auto-refresh via refresh_token
    if refresh_token and FYERS_PIN:
        print("🔄 Access token missing/expired. Attempting daily auto-refresh via API...")
        import hashlib
        import requests
        
        # Calculate appIdHash
        hash_input = f"{CLIENT_ID}:{SECRET_ID}"
        app_id_hash = hashlib.sha256(hash_input.encode()).hexdigest()
        
        payload = {
            "grant_type": "refresh_token",
            "appIdHash": app_id_hash,
            "refresh_token": refresh_token,
            "pin": FYERS_PIN
        }
        url = "https://api-t1.fyers.in/api/v3/validate-refresh-token"
        try:
            res = requests.post(url, json=payload, headers={"Content-Type": "application/json"})
            if res.status_code == 200:
                res_data = res.json()
                if res_data.get('s') == 'ok':
                    new_access_token = res_data.get('access_token')
                    with open(access_token_file, "w") as f:
                        f.write(new_access_token)
                    ACCESS_TOKEN = new_access_token
                    fyers = fyersModel.FyersModel(client_id=CLIENT_ID, token=new_access_token, log_path=os.getcwd())
                    session_authorized = True
                    print("✅ Daily access token refreshed successfully!")
                    send_telegram_message("🔄 *Fyers session auto-refreshed successfully!* Trading bot remains active.")
                    return True
                else:
                    print(f"⚠️ Auto-refresh API failed: {res_data}")
            else:
                print(f"⚠️ Auto-refresh POST failed (HTTP {res.status_code}): {res.text}")
        except Exception as e:
            print(f"⚠️ Exception during session refresh: {e}")
            
    # Step 3: Prompt user for manual re-auth
    session_authorized = False
    app_url = os.environ.get("RAILWAY_PUBLIC_DOMAIN", "http://localhost:8080")
    if not app_url.startswith("http"):
        app_url = f"https://{app_url}"
        
    auth_url = f"https://api-t1.fyers.in/api/v3/generate-authcode?client_id={CLIENT_ID}&redirect_uri=https%3A%2F%2F127.0.0.1%3A5000&response_type=code&state=None"
    
    msg = (f"🚨 *[FYERS SESSION EXPIRED]*\n"
           f"The daily Fyers session has expired or requires manual login.\n\n"
           f"1️⃣ Click this link to log in: [Fyers Login]({auth_url})\n"
           f"2️⃣ Open your Web Portal: {app_url}\n"
           f"3️⃣ Paste the redirected URL there to re-authorize.")
    send_telegram_message(msg)
    print("🚨 Session unauthorized. Please open the web dashboard to log in manually.")
    return False

def start_health_check_server():
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthCheckHandler)
    print(f"🏥 Health Check & Web Authorization portal listening on port {port}...")
    server.serve_forever()

# Start the health check server thread
threading.Thread(target=start_health_check_server, daemon=True).start()

# --- Helper Functions ---
def get_live_nifty_candles():
    """Fetch recent historical 15-minute candles to calculate the EMA."""
    # Fetch last 4 days of history to ensure we have a good warm-up period for the 9 EMA
    from_date = (datetime.today() - timedelta(days=4)).strftime('%Y-%m-%d')
    data = {
        "symbol": INDEX_SYMBOL,
        "resolution": "15",
        "date_format": "1",
        "range_from": from_date,
        "range_to": datetime.today().strftime('%Y-%m-%d'),
        "cont_flag": "1"
    }
    try:
        response = fyers.history(data=data)
        if response and response.get('s') == 'ok':
            # Parse candles: [Timestamp, Open, High, Low, Close, Volume]
            df = pd.DataFrame(response['candles'], columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['datetime'] = pd.to_datetime(df['timestamp'], unit='s')
            return df
        elif response and response.get('s') == 'no_data':
            # Suppress error print before market open or on holidays
            print("⏳ Fyers API connected: Waiting for market open (no data generated yet today).")
            return None
        else:
            err_msg = response.get('message') or response.get('Error') or response
            print(f"⚠️ Fyers API Error: {err_msg}")
    except Exception as e:
        print(f"Error fetching candles: {e}")
    return None

def calculate_indicators(df):
    """Calculate 9 EMA and 14-period Wilder's ADX on Nifty candles."""
    # 1. Calculate 9 EMA
    df['EMA'] = df['close'].ewm(span=EMA_PERIOD, adjust=False).mean()
    
    # 2. Calculate True Range (TR)
    df['h_l'] = df['high'] - df['low']
    df['h_pc'] = (df['high'] - df['close'].shift(1)).abs()
    df['l_pc'] = (df['low'] - df['close'].shift(1)).abs()
    df['tr'] = df[['h_l', 'h_pc', 'l_pc']].max(axis=1)
    
    # 3. Calculate Directional Movement
    df['up_move'] = df['high'] - df['high'].shift(1)
    df['down_move'] = df['low'].shift(1) - df['low']
    
    df['plus_dm'] = np.where((df['up_move'] > df['down_move']) & (df['up_move'] > 0), df['up_move'], 0.0)
    df['minus_dm'] = np.where((df['down_move'] > df['up_move']) & (df['down_move'] > 0), df['down_move'], 0.0)
    
    # 4. Smooth using Wilder's Smoothing (alpha = 1/14)
    df['tr_smoothed'] = df['tr'].ewm(alpha=1/14, adjust=False).mean()
    df['plus_dm_smoothed'] = df['plus_dm'].ewm(alpha=1/14, adjust=False).mean()
    df['minus_dm_smoothed'] = df['minus_dm'].ewm(alpha=1/14, adjust=False).mean()
    
    # 5. Calculate DI lines
    df['plus_di'] = 100 * (df['plus_dm_smoothed'] / df['tr_smoothed'])
    df['minus_di'] = 100 * (df['minus_dm_smoothed'] / df['tr_smoothed'])
    
    # 6. Calculate DX and ADX
    df['dx'] = 100 * ((df['plus_di'] - df['minus_di']).abs() / (df['plus_di'] + df['minus_di']).abs())
    df['ADX'] = df['dx'].ewm(alpha=1/14, adjust=False).mean()
    
    return df

def check_crossover(df):
    if len(df) < 2:
        return 'NONE'
    
    close1 = df['close'].iloc[-1]
    ema1 = df['EMA'].iloc[-1]
    
    close2 = df['close'].iloc[-2]
    ema2 = df['EMA'].iloc[-2]
    
    if close1 > ema1 and close2 <= ema2:
        return 'BULLISH'
    elif close1 < ema1 and close2 >= ema2:
        return 'BEARISH'
    
    return 'NONE'

def log_virtual_trade(trade_details):
    """Write paper trading logs to a local CSV file."""
    log_file = LOG_FILE
    df = pd.DataFrame([trade_details])
    if not os.path.isfile(log_file):
        df.to_csv(log_file, index=False)
    else:
        df.to_csv(log_file, mode='a', header=False, index=False)
    print(f"📄 Virtual Trade Logged: {trade_details}")

class LocalCandleBuilder:
    def __init__(self, historical_df):
        self.df = historical_df.copy()
        self.current_candle = None
        self.current_block_start = None
        
    def add_tick(self, spot, timestamp_dt):
        """
        Processes a live tick (Spot price and datetime).
        Returns a completed candle dict if a 15-min block just completed, else None.
        """
        # Find block start for this tick
        # e.g., 10:52:12 -> 10:45:00
        minute = (timestamp_dt.minute // 15) * 15
        block_start = timestamp_dt.replace(minute=minute, second=0, microsecond=0)
        
        # Verify market hours (9:15 AM to 3:30 PM)
        market_start = timestamp_dt.replace(hour=9, minute=15, second=0, microsecond=0)
        market_end = timestamp_dt.replace(hour=15, minute=30, second=0, microsecond=0)
        if not (market_start <= timestamp_dt < market_end):
            return None
            
        completed_candle = None
        
        # Check for gap (offline detection)
        if self.current_block_start is not None and (block_start - self.current_block_start).total_seconds() > 900:
            print("⚠️ Connection gap detected. Re-syncing candles from Fyers API...")
            raise ConnectionError("Gap in candles detected")
            
        # If we enter a new block
        if self.current_block_start is not None and block_start > self.current_block_start:
            # Finalize the previous candle
            completed_candle = {
                "timestamp": int(self.current_block_start.timestamp()),
                "open": self.current_candle["open"],
                "high": self.current_candle["high"],
                "low": self.current_candle["low"],
                "close": self.current_candle["close"],
                "volume": 0,
                "datetime": self.current_block_start
            }
            # Append to history
            new_row = pd.DataFrame([completed_candle])
            self.df = pd.concat([self.df, new_row], ignore_index=True)
            # Limit history to last 100 candles
            if len(self.df) > 100:
                self.df = self.df.iloc[-100:].reset_index(drop=True)
                
            self.current_candle = None
            
        # Update or initialize current candle
        if self.current_candle is None:
            self.current_block_start = block_start
            self.current_candle = {
                "open": spot,
                "high": spot,
                "low": spot,
                "close": spot
            }
        else:
            self.current_candle["high"] = max(self.current_candle["high"], spot)
            self.current_candle["low"] = min(self.current_candle["low"], spot)
            self.current_candle["close"] = spot
            
        return completed_candle

def get_real_option_contract(signal, current_spot):
    """
    Finds the nearest weekly expiry option contract symbol, its live LTP,
    expiry date, and target strike for the selected signal (BULLISH = CE, BEARISH = PE).
    """
    try:
        data = {
            "symbol": INDEX_SYMBOL,
            "strikecount": 8
        }
        res = fyers.optionchain(data=data)
        if res and res.get('s') == 'ok' and 'data' in res:
            expiry_data = res['data']['expiryData']
            if expiry_data:
                # Get the nearest weekly expiry date and timestamp
                nearest = sorted(expiry_data, key=lambda x: int(x['expiry']))[0]
                nearest_ts = int(nearest['expiry'])
                nearest_date = nearest['date']
                
                # Target strike calculation (ITM 1)
                atm_strike = round(current_spot / 50) * 50
                option_type = 'CE' if signal == 'BULLISH' else 'PE'
                target_strike = atm_strike - 50 if option_type == 'CE' else atm_strike + 50
                
                # Query chain for this specific expiry to fetch actual contract symbols
                res_spec = fyers.optionchain(data={
                    "symbol": INDEX_SYMBOL,
                    "strikecount": 12,
                    "timestamp": nearest_ts
                })
                if res_spec and res_spec.get('s') == 'ok':
                    chain = res_spec.get('data', {}).get('optionsChain', [])
                    for opt in chain:
                        if opt.get('strike_price') == target_strike and opt.get('option_type') == option_type:
                            symbol = opt.get('symbol')
                            ltp = opt.get('ltp')
                            if symbol and ltp:
                                return symbol, float(ltp), nearest_date, target_strike
    except Exception as e:
        print(f"⚠️ Error finding real option contract: {e}")
    return None, None, None, None

def get_live_option_price(symbol):
    """Fetch the live Last Traded Price (LTP) of a given option symbol."""
    try:
        res = fyers.quotes(data={"symbols": symbol})
        if res and res.get('s') == 'ok' and 'd' in res and res['d']:
            return float(res['d'][0]['v'].get('lp', 0.0))
    except Exception as e:
        print(f"⚠️ Error fetching live option price for {symbol}: {e}")
    return None

# --- Main Trading Loop ---
print("🚀 Fyers Nifty 15-Min EMA Paper Trading Engine Started...")

# Initial session setup
session_active = False
while not session_active:
    session_active = initialize_fyers_session()
    if not session_active:
        time.sleep(10)

# Startup: Fetch historical candles for warming up the EMA and initialize builder
builder = None
print("⏳ Initializing Local Candle Builder with historical data...")
while builder is None:
    if not session_authorized:
        print("⏳ Waiting for active session authorization to download warmup data...")
        time.sleep(10)
        continue
    hist_df = get_live_nifty_candles()
    if hist_df is not None and len(hist_df) > 0:
        builder = LocalCandleBuilder(hist_df)
        print(f"✅ Local Candle Builder initialized with {len(hist_df)} historical candles.")
    else:
        print("⚠️ Could not fetch warmup candles. Retrying in 10 seconds...")
        time.sleep(10)

send_telegram_message("🚀 *Fyers 15-Min EMA Paper Trading Engine Started* successfully with local candle building!")

last_init_date = None

while True:
    try:
        # Force time calculation to be in Indian Standard Time (IST) regardless of server location
        now = datetime.now(timezone(timedelta(hours=5, minutes=30))).replace(tzinfo=None)
        
        # Daily Session Check/Refresh (runs every day at 8:30 AM)
        current_date = now.strftime('%Y-%m-%d')
        if last_init_date != current_date and now.hour >= 8 and now.minute >= 30:
            print("⏰ Scheduled morning check: verifying Fyers session token...")
            session_active = False
            while not session_active:
                session_active = initialize_fyers_session()
                if not session_active:
                    time.sleep(10)
            last_init_date = current_date
            
        # If we lost authorization, suspend loop until authorized via web portal
        if not session_authorized:
            print("⏳ Trading suspended: waiting for Fyers session authorization...")
            time.sleep(10)
            continue
        
        # 1. Fetch current spot price via Quotes API (instant, no delay)
        spot_res = fyers.quotes(data={"symbols": INDEX_SYMBOL})
        if not spot_res or spot_res.get('s') != 'ok' or 'd' not in spot_res or not spot_res['d']:
            print("⚠️ Failed to fetch Nifty Spot quote. Retrying...")
            time.sleep(5)
            continue
            
        current_spot = float(spot_res['d'][0]['v'].get('lp', 0.0))
        
        # 2. Feed tick to builder
        completed_candle = None
        try:
            completed_candle = builder.add_tick(current_spot, now)
        except ConnectionError:
            # Re-sync builder
            hist_df = get_live_nifty_candles()
            if hist_df is not None and len(hist_df) > 0:
                builder = LocalCandleBuilder(hist_df)
                print("✅ Successfully re-synced Local Candle Builder.")
            continue
            
        # 3. If a candle completes, check for crossover signals
        signal = 'NONE'
        if completed_candle:
            df = builder.df
            df = calculate_indicators(df)
            raw_signal = check_crossover(df)
            adx_val = df['ADX'].iloc[-1]
            
            if raw_signal != 'NONE':
                if pd.isna(adx_val) or adx_val <= ADX_FILTER_THRESHOLD:
                    print(f"🔒 Candle Completed: {completed_candle['datetime'].strftime('%H:%M')} | Spot: {completed_candle['close']} | EMA: {round(df['EMA'].iloc[-1], 2)} | Signal {raw_signal} BLOCKED by ADX ({round(adx_val, 2)} <= {ADX_FILTER_THRESHOLD})")
                    signal = 'NONE'
                else:
                    print(f"🔒 Candle Completed: {completed_candle['datetime'].strftime('%H:%M')} | Spot: {completed_candle['close']} | EMA: {round(df['EMA'].iloc[-1], 2)} | Signal: {raw_signal} (ADX: {round(adx_val, 2)} > {ADX_FILTER_THRESHOLD})")
                    signal = raw_signal
            else:
                print(f"🔒 Candle Completed: {completed_candle['datetime'].strftime('%H:%M')} | Spot: {completed_candle['close']} | EMA: {round(df['EMA'].iloc[-1], 2)} | Signal: NONE (ADX: {round(adx_val, 2) if not pd.isna(adx_val) else 0.0})")
            
        # 4. Manage Active Paper Trade
        if active_trade:
            real_premium = get_live_option_price(active_trade['symbol'])
            if real_premium is not None:
                current_premium = real_premium
            else:
                print("⚠️ Failed to fetch live option price. Skipping this loop check.")
                time.sleep(5)
                continue
            
            pnl = (current_premium - active_trade['entry_premium']) * active_trade['qty']
            
            # Print live trade status update
            pnl_sign = '+' if pnl >= 0 else ''
            print(f"📊 [ACTIVE] Spot: ₹{current_spot} | Premium: ₹{round(current_premium, 2)} | P&L: {pnl_sign}₹{round(pnl, 2)}")
            sl_limit = active_trade['entry_premium'] * (1 - STOP_LOSS_PCT)
            tp_limit = active_trade['entry_premium'] * (1 + TARGET_PROFIT_PCT)
            
            close_reason = None
            if current_premium <= sl_limit:
                close_reason = "STOP_LOSS_HIT"
            elif current_premium >= tp_limit:
                close_reason = "TARGET_PROFIT_HIT"
            elif now.hour == 15 and now.minute >= 15:
                close_reason = "DAILY_SQUARE_OFF"
            
            if close_reason:
                active_trade['exit_time'] = now.strftime('%Y-%m-%d %H:%M:%S')
                active_trade['exit_spot'] = current_spot
                active_trade['exit_premium'] = round(current_premium, 2)
                active_trade['pnl'] = round(pnl, 2)
                active_trade['status'] = close_reason
                log_virtual_trade(active_trade)
                
                # Send exit Telegram alert
                msg = (f"🎯 *[PAPER TRADE EXIT - {close_reason}]*\n"
                       f"*Index*: NIFTY 50\n"
                       f"*Contract*: {active_trade['symbol']} (Expiry: {active_trade['expiry_date']})\n"
                       f"*Spot Price*: ₹{current_spot}\n"
                       f"*Exit Premium*: ₹{round(current_premium, 2)}\n"
                       f"*Net P&L*: **₹{round(pnl, 2)}** (Simulated)")
                send_telegram_message(msg)
                
                active_trade = None
                
        # 5. Check for Crossover Signals (only if no active trade)
        elif signal != 'NONE' and now.hour < 15:
            option_type = 'CE' if signal == 'BULLISH' else 'PE'
            
            # Fetch real contract details
            symbol, entry_premium, expiry_date, target_strike = get_real_option_contract(signal, current_spot)
            if not symbol or not entry_premium:
                print("⚠️ Failed to fetch real option contract from Fyers API. Skipping this signal.")
                time.sleep(5)
                continue
            
            active_trade = {
                "entry_time": now.strftime('%Y-%m-%d %H:%M:%S'),
                "symbol": symbol,
                "option_type": option_type,
                "strike": target_strike,
                "expiry_date": expiry_date,
                "qty": 75 * LOTS_MULTIPLIER, 
                "entry_spot": current_spot,
                "entry_premium": entry_premium,
                "exit_time": None,
                "exit_spot": None,
                "exit_premium": None,
                "pnl": 0.0,
                "status": "ACTIVE"
            }
            print(f"🔔 Signal Triggered: {signal}! Entered virtual trade: Buy Nifty {symbol} at Spot {current_spot} (LTP: {entry_premium})")
            
            # Send entry Telegram alert
            msg = (f"🔔 *[PAPER TRADE ENTRY]*\n"
                   f"*Index*: NIFTY 50\n"
                   f"*Signal*: {signal} 15-Min Cross\n"
                   f"*Contract*: BUY `{symbol}` ({LOTS_MULTIPLIER} Lots | Expiry: {expiry_date})\n"
                   f"*Spot Price*: ₹{current_spot}\n"
                     f"*Live Premium*: ₹{entry_premium}")
            send_telegram_message(msg)
            
        time.sleep(10)
    except Exception as e:
        print(f"⚠️ Loop Error: {e}")
        err_str = str(e).lower()
        if "token" in err_str or "authenticate" in err_str or "-15" in err_str or "-16" in err_str:
            print("🚨 Session authentication error detected! Suspending trading loop...")
            session_authorized = False
        time.sleep(10)
