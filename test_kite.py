import os
from datetime import datetime, timedelta
from dotenv import load_dotenv
from kiteconnect import KiteConnect

load_dotenv()
kite = KiteConnect(api_key=os.getenv("KITE_API_KEY"))
kite.set_access_token(os.getenv("KITE_ACCESS_TOKEN"))

inst = kite.instruments("NSE")
print("instruments:", len(inst))

token = next(i["instrument_token"] for i in inst if i["tradingsymbol"] == "RELIANCE")
end = datetime.now()
bars = kite.historical_data(token, end - timedelta(days=5), end, "60minute")
print("60m bars:", len(bars))