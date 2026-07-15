import os
from fyers_apiv3 import fyersModel

# --- Configuration ---
CLIENT_ID = "77QN6WHNT3-100"
SECRET_KEY = "DIJN19NKWM"
REDIRECT_URI = "https://127.0.0.1:5000"

def generate_fyers_access_token():
    print("🔑 Initiating Fyers API v3 Login Session...")
    print(f"📡 Using Redirect URI: '{REDIRECT_URI}'")
    
    # 1. Create session
    session = fyersModel.SessionModel(
        client_id=CLIENT_ID,
        secret_key=SECRET_KEY,
        redirect_uri=REDIRECT_URI,
        response_type="code",
        grant_type="authorization_code"
    )
    
    # 2. Generate Auth URL
    auth_url = session.generate_authcode()
    print("\n👉 STEP 1: Open the following URL in your web browser and log in with your Fyers credentials:")
    print("-" * 80)
    print(auth_url)
    print("-" * 80)
    
    # 3. Get Auth Code
    print("\n👉 STEP 2: After logging in, you will be redirected to a redirect page.")
    print("   Copy the entire redirected URL from your browser address bar and paste it below:")
    redirect_input = input("\nPaste Redirected URL here: ").strip()
    
    # Extract auth_code from URL
    auth_code = None
    if "auth_code=" in redirect_input:
        try:
            auth_code = redirect_input.split("auth_code=")[1].split("&")[0]
        except Exception:
            print("❌ Failed to parse auth_code from URL.")
    else:
        auth_code = redirect_input
        
    if not auth_code:
        print("❌ Invalid auth code input. Terminating.")
        return
        
    # 4. Generate Access Token
    print(f"\n👉 STEP 3: Requesting Access Token using Auth Code: {auth_code[:6]}...")
    session.set_token(auth_code)
    try:
        response = session.generate_token()
        if response and response.get('s') == 'ok':
            access_token = response.get('access_token')
            print("\n✅ LOGIN SUCCESSFUL!")
            print("=" * 80)
            print("YOUR DAILY ACCESS TOKEN IS:")
            print(access_token)
            print("=" * 80)
            print("\nSave this access token as your 'FYERS_ACCESS_TOKEN' environment variable.")
        else:
            print(f"❌ Failed to generate access token. Response: {response}")
    except Exception as e:
        print(f"❌ Error generating token: {e}")

if __name__ == "__main__":
    generate_fyers_access_token()
