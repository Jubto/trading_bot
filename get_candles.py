from binance.client import Client
from binance.exceptions import BinanceAPIException
from config import API_KEY, API_SECRET
from glob import glob
from time import time
import json 
import csv
import os
import sys


#https://python-binance.readthedocs.io/en/latest/market_data.html#id7
client = Client(API_KEY, API_SECRET) # new client object 


# make different coin objects, e.g. INJ, BTC, FTM etc. 
class Coin():
	'''A class which retrieves candle stick data for a given coin avaliable on Binance, performs TA on the stored data, can return a score.'''

	INTERVALS = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '3h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'] # All avaliable intervals on binance
	EARLIEST_DATE = "1 Jan, 2017" # Date binance started

	def __init__(self, coin_symbol, coin_name=None):
		os.path.dirname(os.path.realpath(__file__))
		data_path = os.path.abspath('coindata')
		coin_path = os.path.join(data_path, coin_symbol)
		if not os.path.exists(coin_path):
			os.mkdir(coin_path)

		if type(coin_symbol) != str:
			raise Exception(f'Coin objects must be initialised with a string symbol and string name.')
		
		self.coin_symbol = coin_symbol
		self.coin_name = coin_name 
		self.coin_path = coin_path
		self.json_file = self.coin_path + '/' + 'analysis' + '_' +  self.coin_symbol + '.json'
		self.previous_update_UTC = None

	def get_candles(self, tradingpair, *intervals):
		'''
		Saves all historical candle data avliable from binance as csv in coindata directory with its own directory name.
		Deafult intervals retrieved will be: 1w/3d/1d/4h/1h - additional intervals can be specified.
			Avaliable intervals are: 1m, 3m, 5m, 15m, 30m, 1h, 2h, 3h, 4h, 6h, 8h, 12h, 1d, 3d, 1w, 1M 
		If method is called with existing data, any new candles will be appended.		
		'''
		timeframes = ['1w', '3d', '1d', '4h', '1h'] # Deafult timeframes used for this method

		if type(tradingpair) != str:
			raise Exception(f'get_candles method requires a string for tradingpair parameter.')

		if [interval for interval in intervals if interval != '']:
			[timeframes.append(str(interval)) for interval in intervals if str(interval) in self.INTERVALS]
			if len(timeframes) == 5:
				print(f"Warning: None of the optionals intervals in {intervals} will be added.\nEither they're already part of the deafult, or are invalid.")
		
		for timeframe in timeframes:
			datafile = self.csv_filename(tradingpair, timeframe)
			symbol = self.coin_symbol.upper() + tradingpair.upper()
			try:
				if os.path.exists(datafile):
					with open(datafile, 'r', newline='') as csvfile: # csvfile represents a file object
						final_candle = csvfile.readline().split(':')[0] # Read first line of csv to obtain most recent UTC candle time saved 
						klines = client.get_historical_klines(symbol, timeframe, int(final_candle)) # Retreve only new candles 
						# print(f'Timeframe: {timeframe} final_candle {final_candle} klines {len(klines)}')
						self.csv_maker(datafile, 'a', klines)
						self.csv_maker(datafile, 'r+', klines) # Update the latest UTC candle to the first line of .csv
				else:
					klines = client.get_historical_klines(symbol, timeframe, self.EARLIEST_DATE) # Get all candlestick data from earliest possible date from binance.
					self.csv_maker(datafile, 'w', klines)
			except BinanceAPIException:
				# If trading pair does not exist, coin object will remove all assoicated files and directories. 
				print(f'API exception, please ensure trading pair {symbol} exists.')
				if self.list_saved_files():
					self.remove_tradingpair(tradingpair.upper()) # Means coin symbol exists however trading pair does not exist in Binance.
				else:
					self.remove_coin() # Means coin symbol does not exist in Binance.
				return 0
		self.create_json_file()
		return 1

	def remove_timeframe(self, tradingpair, timeframe):
		'''Handles removal of timeframe for given coin'''

		datafile = self.csv_filename(tradingpair, timeframe)
		if os.path.exists(datafile):
			os.remove(datafile)
			print(f'{self.coin_symbol}{tradingpair} timeframe {timeframe} has been removed.')
		else:
			print(f'{self.coin_symbol}{tradingpair} does not have the timeframe {timeframe}')

	def remove_tradingpair(self, tradingpair):
		'''Handles removal of trading pair from given coin'''

		files = self.list_saved_files()
		trim = len(self.coin_symbol)
		for f in files:
			if tradingpair == f.split('_')[0][trim:]:
				os.remove(self.coin_path + '/' + f)
		print(f'All files assoicated with {self.coin_symbol}{tradingpair} have been removed.')

	def remove_coin(self):
		'''Handles removing coin'''

		files = self.list_saved_files()
		for f in files:
			os.remove(self.coin_path + '/' + f)
		os.rmdir(self.coin_path)
		print(f'All assoicated files for {self.coin_symbol} have been removed.')


	def csv_maker(self, file_path, mode, klines):
		'''Creates new or appends to existing csv files for coin objects. Inserts header in the first row
		   Header row contains: Final row UTC timestamp, number of rows, pointer position at EOF.'''

		with open(file_path, mode, newline='') as csvfile: 
			final_candle = klines[-1][0]
			num_rows = len(klines) - 1 # Last row is not added
			self.previous_update_UTC = int(str(final_candle)[:-3])

			if mode == 'w' or mode == 'r+':			
				if mode == 'w':
					# If block only activates when creating csv file for first time.
					csvfile.write(f'{0:0106}') # Temporary empty row for header.
				else:
					with open(file_path, 'a', newline='') as csvfile_temp:
						pointer = csvfile_temp.tell()
					header = csvfile.readline()
					num_rows = num_rows + int(header.split(':')[1].lstrip('0'))
					csvfile.seek(0)
					csvfile.write(f'{final_candle}:{num_rows:030}:{pointer:060}') # Add updated header to beginning. 
					return None

			csv_writer = csv.writer(csvfile, delimiter=',') # create csv writer object
			[csv_writer.writerow(kline) for kline in klines[:-1]] # Don't add final candle row as that candle hasn't closed yet
			
			if mode == 'w':
				# If block only activates when creating csv file for first time. 
				pointer = csvfile.tell()
				csvfile.seek(0)
				csvfile.write(f'{final_candle}:{num_rows:030}:{pointer:060}\n') # Add header, length always stays constant. 

	@staticmethod
	def percent_changes(candle_open, candle_high, candle_low, candle_close):
		'''Returns % change, % amplitude, max % up, max % down of a given candle / timeframe as a int tuple (%change, %amplitude, max%up, max%down).'''
		
		if (type(candle_open) and type(candle_high) and type(candle_low) and type(candle_close)) != float:
			raise Exception(f'percent_change static method requires floats as arguments.')

		candle_change = (candle_close / candle_open)*100 - 100
		candle_amplitude = (candle_high / candle_low)*100 - 100
		candle_max_up = (candle_high / candle_open)*100 - 100 
		candle_max_down = (candle_low / candle_open)*100 - 100

		return {'candle_change':round(candle_change, 1), 'candle_amplitude':round(candle_amplitude, 1),
		'candle_max_up':round(candle_max_up, 1), 'candle_max_down':round(candle_max_down, 1)}

	@staticmethod
	def average(nums):
		if len(nums) == 0:
			return None
		elif len(nums) == 1:
			return nums
		total = 0
		for num in nums:
			total += num
		return round((total) / len(nums), 1)

	def csv_filename(self, tradingpair, timeframe):
		'''Returns absolute path of coin objects specified csv file'''

		if (type(tradingpair) and type(timeframe)) != str:
			raise Exception(f'csv_filename method requires strings as arguments.') 

		symbol = self.coin_symbol.upper() + tradingpair.upper()
		datafile = symbol + '_' + timeframe
		return self.coin_path + '/' + datafile + '.csv'

	def list_saved_files(self):
		'''Returns a list of all csv files of coin object. If no csv files are present, raises exception.'''

		file_paths = self.coin_path + '/' + self.coin_symbol + '*'
		files = glob(file_paths)
		if len(files) == 0:
			# print(f'WARNING: database has no coin {self.coin_symbol} stored. Please run get_candles method to obtain its data.')
			return []
		return [f.split('/')[-1] for f in files] # List of csv file names, e.g. INJBTC_4h.csv (list does not include json file).


	def create_json_object(self, *options):
		'''This method will return a json string containing trading pair object (key) their timeframes (keys), and % changes (key + list)'''
		
		symbol_timeframe = {}
		csv_files = self.list_saved_files()

		if options:
			if 'print' not in options:
				csv_files = options[0]

		for csvfile in csv_files:
			symbol = csvfile.split('_')[0] # Parent key
			timeframe = {csvfile.split('_')[1].split('.')[0]:{'candle_change':[], 'candle_amplitude':[], 'candle_max_up':[], 'candle_max_down':[]}} 
			try:
				symbol_timeframe[symbol].update(timeframe)
			except KeyError:
				symbol_timeframe[symbol] = timeframe

		if 'print' in options:
			print(json.dumps(symbol_timeframe, indent=4))
		else:
			return json.dumps(symbol_timeframe, indent=4)

	def print_saved_data(self):
		'''Prints a summary of all the saved data of given coin object'''
		self.create_json_object('print')

	def create_json_file(self):
		'''Creates and returns a json object string'''

		if os.path.exists(self.json_file):
			return None

		coin_data = json.loads(self.create_json_object())
		with open(self.json_file, 'w') as jf:
			json.dump(coin_data, jf, indent=4)

		print(f'New json file for {self.coin_symbol} has been created in: {self.json_file}')

	def update_json(self):
		'''Method used to update a given coins json file if new csv files have since been generated.'''
		
		if not os.path.exists(self.json_file):
			print(f'New json file for {self.coin_symbol} will be created.')
			self.create_json_file()
		
		with open(self.json_file, 'r') as jf:
			coin_data = json.load(jf)

		# Find difference of all tradingpairs_timeframes of json file with Coin directory csv files
		csv_files = set(self.list_saved_files())
		json_data = set()
		for symbol in coin_data:
			for timeframe in coin_data[symbol]:
				json_data.add((str(symbol) + '_' + str(timeframe) + '.csv'))
		csv_files.difference_update(json_data)

		# If there's new csv files not stored in the json this adds them in
		if csv_files:
			new_data_json = json.loads(self.create_json_object(csv_files))
			for symbol in new_data_json:
				for timeframe in new_data_json[symbol]:
					timeframe_dict = {timeframe:new_data_json[symbol][timeframe]}
					try:
						coin_data[symbol].update(timeframe_dict)
					except KeyError:
						coin_data[symbol] = timeframe_dict
			with open(self.json_file, 'w') as jf:
				json.dump(coin_data, jf, indent=4)

	def add_data_to_json(self):
		if not os.path.exists(self.json_file):
			raise Exception(f'Coin {self.coin_symbol} has no json file.')

		with open(self.json_file, 'r') as jf:
			coin_data = json.load(jf)

		for symbol in coin_data:
			for timeframe in coin_data[symbol]:
				datafile = self.csv_filename(symbol.split(self.coin_symbol)[1], timeframe)
				with open(datafile) as csvfile:
					header = csvfile.readline()
					saved_data_len = int(header.split(':')[1].lstrip('0'))
					data_list = coin_data[symbol][timeframe]['candle_change']
					if len(data_list) < saved_data_len:
						skip = len(data_list)
						change_dict_list = []
						for row in csvfile:
							if skip > 0:
								skip -= 1
								continue
							candles = row.split(',')
							candle_open = candles[1]
							candle_high = candles[2]
							candle_low = candles[3]
							candle_close = candles[4]
							change_dict_list.append(self.percent_changes(float(candle_open), float(candle_high), float(candle_low), float(candle_close)))

						for new_data in change_dict_list:
							for data in coin_data[symbol][timeframe]:
								coin_data[symbol][timeframe][data].append(new_data[data])
						for data in coin_data[symbol][timeframe]:
							if data == 'candle_max_down':
								coin_data[symbol][timeframe][data].sort(reverse=False)
							else:
								coin_data[symbol][timeframe][data].sort(reverse=True)
						# print(f'{symbol} {timeframe} Has been updated.')
					# else:
						# print(f'{symbol} {timeframe} Up to date, file skipped!')
		
		with open(self.json_file, 'w') as jf:
			json.dump(coin_data, jf, indent=4)

	def update(self):
		'''Updates all csv and json files of given file object.'''
 
		# Each coin object will only update their database at most every hour.
		if self.previous_update_UTC == None or (time() - self.previous_update_UTC >= 3600):
			csv_files = self.list_saved_files()
			tradingpairs = set()
			trim = len(self.coin_symbol)
			for csvfile in csv_files:
				tradingpair = csvfile.split('_')[0][trim:]
				tradingpairs.add(tradingpair)
			for tradingpair in tradingpairs:
				self.get_candles(tradingpair)
			self.update_json()
			self.add_data_to_json()
			# print(f'All csv and json files of coin {self.coin_symbol} are up to date.')

	def current_score(self, tradingpairs=[], update=0):
		'''Returns current calculated score.
		   Candle_max_up means: how well the current price change compares with all the historical maxiumal price changes.'''

		if not os.path.exists(self.json_file):
			raise Exception(f'Coin {self.coin_symbol} has no json file.')
		
		if update == 1:
			self.update() # Only updates every hour to be more efficent.

		score_bull = 0
		score_bear = 0
		score_dict = {}
		csv_files = self.list_saved_files()
		if tradingpairs:
			csv_files = [csvfile for tradingpair in tradingpairs for csvfile in csv_files if tradingpair in csvfile] # Only look at certain trading pairs. 
		for csvfile in csv_files:
			symbol = csvfile.split('_')[0]
			timeframe = csvfile.split('_')[1].split('.')[0]
			csvfile = self.coin_path + '/' + csvfile
			with open(csvfile, 'r', newline='') as cf:
				final_candle = cf.readline().split(':')[0]
				klines = client.get_historical_klines(symbol, timeframe, int(final_candle))
				candles = klines[0]
				candle_open = candles[1]
				candle_high = candles[2]
				candle_low = candles[3]
				candle_close = candles[4]
				try:
					score_dict[symbol]
					score_dict[symbol][timeframe] = self.percent_changes(float(candle_open), float(candle_high), float(candle_low), float(candle_close))
				except KeyError:
					score_dict[symbol] = {timeframe:self.percent_changes(float(candle_open), float(candle_high), float(candle_low), float(candle_close))}			
					score_dict[symbol]['price'] = candle_close


		with open(self.json_file, 'r') as jf:
			coin_data = json.load(jf)

		for symbol in coin_data:
			if symbol not in score_dict.keys():
				continue
			for timeframe in coin_data[symbol]:
				current_change = score_dict[symbol][timeframe]['candle_change']
				amplitude_change = score_dict[symbol][timeframe]['candle_amplitude']
				# print(f'\n\ntimeframe: {timeframe} symbol {symbol} current_change {current_change} amplitude_change {amplitude_change}')
				for data in coin_data[symbol][timeframe]:
					historical_candles_changes = coin_data[symbol][timeframe][data]
					historical_average = self.average(coin_data[symbol][timeframe][data])
					rank = 0
					for change in historical_candles_changes:	
						rank += 1
						if data == 'candle_amplitude':
							if amplitude_change < change:	
								continue
						elif current_change < change or (data == 'candle_max_down' and current_change > change):	
							continue
						break	
					performance = round((rank / len(historical_candles_changes))*100, 1)
					if (data == 'candle_max_down' and current_change > 0) or (data == 'candle_max_up' and current_change < 0):
						performance = 'NA'
					score_dict[symbol][timeframe][data] = performance # Updating score_dict from storing %change to storing performance per timeframe.

					# print(f'symbol {symbol} timeframe {timeframe} data {data}')
					# print(f'rank: {rank} compared with len {len(historical_candles_changes)} === performance: {performance} current change was: {current_change}')

					# Highest Bull / Bear score possible is 60 - meaning the current price action is within the top 2.5% for all timeframes for all their respective historical max candle heights reached.
					if performance == 'NA':
						continue
					if data == 'candle_max_up':
						if performance <= 2.5:
							score_bull += 6
						elif performance <= 5:
							score_bull += 5
						elif performance <= 10:
							score_bull += 4
						elif performance <= 15:
							score_bull += 3
						elif performance <= 20:
							score_bull += 2
						elif performance <= 25:
							score_bull += 1
					elif data == 'candle_max_down':
						if performance <= 2.5:
							score_bear += 6
						elif performance <= 5:
							score_bear += 5
						elif performance <= 10:
							score_bear += 4
						elif performance <= 15:
							score_bear += 3
						elif performance <= 20:
							score_bear += 2
						elif performance <= 25:
							score_bear += 1

					if data == 'candle_amplitude':
						score_dict[symbol][timeframe][data] = str(performance) + '|' + str(amplitude_change) + '|' + str(historical_average) 
					else:
						score_dict[symbol][timeframe][data] = str(performance) + '|' + str(current_change) + '|' + str(historical_average) 
							
		for symbol in score_dict:
			for timeframe in score_dict[symbol]:
				if timeframe == 'price':
					continue
				for data in score_dict[symbol][timeframe]:
					if score_dict[symbol][timeframe][data] == 'NA':
						continue
					stats = score_dict[symbol][timeframe][data].split('|')
					performance = float(stats[0])
					change = stats[1]
					average = stats[2]

					# This means the current candle performed in the top 20% or above of all historical candles (i.e. bull - sell)
					if performance <= 20:
						if performance <=5:
							score_dict[symbol][timeframe][data] = "Rank is: " + str(performance) + '!!!' + f' | change is: {change}%' + f' | average is: {average}%' 
						else:
							score_dict[symbol][timeframe][data] = "Rank is: " + str(performance) + f' | change is: {change}%' + f' | average is: {average}%' 

					# This means the current candle performed in the bottom 80% or bellow all historical candles (i.e. bear - buy)
					elif performance >= 80:
						if performance >=95:
							score_dict[symbol][timeframe][data] = "Rank is: " + str(performance) + '!!!' + f' | change is: {change}%' + f' | average is: {average}%' 
						else:
							score_dict[symbol][timeframe][data] = "Rank is: " + str(performance) + f' | change is: {change}%' + f' | average is: {average}%' 
					else:
						# Nothing special, just ignore. 
						score_dict[symbol][timeframe][data] = 'AVERAGE'
		
		# print(f'The performance summary of {self.coin_symbol} is:\n{json.dumps(score_dict, indent=4)}')
		# print(f'Bull score: {score_bull}\nBear score: {score_bear}')
		return [f'{self.coin_symbol}', score_bull, score_bear, score_dict, 'coin_score']
		

	def historical_score(self):
		pass

	def sell_assest(self):
		'''Use only during emergency, sells asset on binance'''

	def notify(self):
		pass
