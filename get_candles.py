from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import API_KEY, API_SECRET
import csv
import os

"""
https://python-binance.readthedocs.io/en/latest/market_data.html#id7
"""

client = Client(API_KEY, API_SECRET) # new client object 


# make different coin objects, e.g. INJ, BTC, FTM etc. 
# each object the following methods: Get all history of candles (for 1 day, 3 day, 1 W, 4 hr, 1 hr), Stream candles, returns score, returns warning, toggle notification
class Coin():
	INTERVALS = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '3h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'] # All avaliable intervals on binance
	EARLIEST_DATE = "1 Jan, 2017" # Date binance started

	def __init__(self, coin_symbol, coin_name):
		parent_path = os.path.abspath('coindata')
		coin_path = os.path.join(parent_path, coin_symbol)
		if os.path.exists(coin_path):
			raise Exception(f'Coin object {coin_symbol} already exists with data stored in {coin_path}.')
		os.mkdir(coin_path)

		if coin_symbol or coin_name != str:
			raise Exception(f'Coin objects must be initialised with a string symbol and string name.')

		self.coin_symbol = coin_symbol
		self.coin_name = coin_name 
		self.data_path = coin_path

		print(f'All candlestick related data for {self.coin_symbol} will be saved in {self.data_path}.')

	def get_all_candles(self, trading_pair, *intervals):
		'''
		Saves all historical candle data avliable from binance as csv in coindata directory with its own directory name.
		Deafult intervals retrieved will be: 1w/3d/1d/4h/1h - additional intervals can be specified.
			Avaliable intervals are: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M 
		If method is called with existing data, any new candles will be appended.		
		'''
		if type(trading_pair) != str:
			raise Exception(f'get_all_candles method requires a string for trading_pair parameter.')

		timeframes = {'1w', '3d', '1d', '4h', '1h'}

		if intervals:
			[timeframes.add(str(interval)) for interval in intervals if str(interval) in self.INTERVALS]
		
		for timeframe in timeframes:
			symbol = self.coin_symbol.upper() + trading_pair.upper()
			try:
				# Gets all candlestick data from earliest possible date from binance.
				klines = client.get_historical_klines(symbol, timeframe, self.EARLIEST_DATE)
			except BinanceAPIException:
				print(f'API exception, please ensure trading pair {symbol} exists.')
			
			datafile = symbol + '_' + timeframe
			with open(self.data_path + '/' + datafile, 'w', newline='') as csvfile: # csvfile represents a csv file object 
				csv_writer = csv.writer(csvfile, delimiter=',') # create csv writer object
				[csv_writer.writerow(kline) for kline in klines]


	def current_score(self):
		'''Returns current calculated score'''
		pass

	def sell_assest(self):
		'''Use only during emergency, sells asset on binance'''

# returns last 500 candles 
candles = client.get_klines(symbol='BNBBTC', interval=Client.KLINE_INTERVAL_30MINUTE) 
# [print(candle) for candle in candles]
# print(len(candles))
"""
[
  [
    1499040000000,      // Open time
    "0.01634790",       // Open
    "0.80000000",       // High
    "0.01575800",       // Low
    "0.01577100",       // Close
    "148976.11427815",  // Volume
    1499644799999,      // Close time
    "2434.19055334",    // Quote asset volume
    308,                // Number of trades
    "1756.87402397",    // Taker buy base asset volume
    "28.46694368",      // Taker buy quote asset volume
    "17928899.62484339" // Ignore.
  ]
]
"""