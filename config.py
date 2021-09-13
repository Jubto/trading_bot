import os
from binance.client import Client # Third party 

# Users must mannually add their Binance API key to your systems environment variables TODO make shell script to auto this
API_KEY = os.environ.get('BINANCE_API_KEY')
API_SECRET = os.environ.get('BINANCE_API_SECRET')

#https://python-binance.readthedocs.io/en/latest/market_data.html#id7
client = Client(API_KEY, API_SECRET)
