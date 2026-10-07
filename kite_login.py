import os
from dotenv import load_dotenv, set_key
from kiteconnect import KiteConnect

load_dotenv()
kite = KiteConnect(api_key=os.getenv("KITE_API_KEY"))

print("Open this link, log in, then copy the request_token from the address bar:")
print(kite.login_url())

request_token = input("Paste request_token here: ").strip()
session = kite.generate_session(request_token, api_secret=os.getenv("KITE_API_SECRET"))
set_key(".env", "KITE_ACCESS_TOKEN", session["access_token"])
print("Done. Token saved to .env")