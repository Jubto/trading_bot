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
		data_path = os.path.dirname(os.path.realpath(__file__)) + '/' + 'coindata'
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
		Handles the retreval of raw candle data from binance.
		If coin has no stored data (i.e. new coin for server) then this will retreve all historical data
		If coin has data stored, then this will retreve only the latest candle data. 	
		'''

		timeframes = [] 

		if type(tradingpair) != str:
			raise Exception(f'get_candles method requires a string for tradingpair parameter.') # TODO remove once everything is done, since only server uses this method

		[timeframes.append(str(interval)) for interval in intervals if str(interval) in self.INTERVALS] # Ensure all intervals provided are valid.
		if not timeframes:
			print(f"Warning: None of the optionals intervals in {intervals} will be added.\nEither they're already part of the deafult, or are invalid.")
		
		for timeframe in timeframes:
			datafile = self.csv_filename(tradingpair, timeframe)
			symbol = self.coin_symbol.upper() + tradingpair.upper()
			try:
				if os.path.exists(datafile):
					with open(datafile, 'r', newline='') as csvfile: 
						final_candle = csvfile.readline().split(':')[0] # Read first line of csv to obtain most recent UTC candle time saved 
					klines = client.get_historical_klines(symbol, timeframe, int(final_candle)) # Retreve only new candles from Binance 
					self.csv_maker(datafile, 'a', klines) # Append only new candles
					self.csv_maker(datafile, 'r+', klines) # Update the latest UTC candle to the first line of .csv
					if timeframe == '1h':
						with open(datafile, 'r', newline='') as csvfile:
							self.previous_update_UTC = int(csvfile.readline().split(':')[0]) # Keeps track of the latest hour coin was updated.
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
		if timeframes:
			self.create_json_file()
			return 1


	def remove_timeframe(self, symbol_timeframe):
		'''Handles removal of timeframe for given coin'''

		datafile = self.coin_path + '/' + symbol_timeframe + '.csv'
		if os.path.exists(datafile):
			os.remove(datafile)
			print(f'{symbol_timeframe} has been removed.')
		else:
			print(f'{symbol_timeframe} is already not present in database.')


	def remove_tradingpair(self, symbol):
		'''Handles removal of trading pair from given coin'''

		if symbol[-1:] == '1':
			symbol = symbol[:-1] # Removing ending 1
		print(f'planning to remove {symbol}')
		files = self.list_saved_files()
		for f in files:
			if symbol == f.split('_')[0]:
				os.remove(self.coin_path + '/' + f)
		print(f'All files assoicated with {symbol} have been removed.')


	def remove_coin(self):
		'''Handles removing coin'''

		files = glob(self.coin_path + '/*')
		for path in files:
			print(f'removing path {path}')
			os.remove(path)
		os.rmdir(self.coin_path)
		print(f'All assoicated files for {self.coin_symbol} have been removed.')


	def csv_maker(self, file_path, mode, klines):
		'''Creates new or appends to existing csv files for coin objects. Inserts header in the first row
		   Header row contains: Final row UTC timestamp, number of rows, pointer position at EOF.'''

		with open(file_path, mode, newline='') as csvfile: 
			final_candle = klines[-1][0]
			num_rows = len(klines) - 1 # Last row is not added
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
					return 1

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
		return [f.split('/')[-1] for f in files] # List of csv file names, e.g. INJBTC_4h.csv (list does not include json file intentionally).


	def create_json_object(self, *files):
		'''This method will return a json string containing trading pair object (key) their timeframes (keys), and % changes (key + list)'''
		
		symbol_timeframe = {}
		csv_files = self.list_saved_files()

		if files:
			csv_files = files

		for csvfile_name in csv_files:
			symbol = csvfile_name.split('_')[0] # Parent key
			timeframe = {csvfile_name.split('_')[1].split('.')[0]:{'candle_change':[], 'candle_amplitude':[], 'candle_max_up':[], 'candle_max_down':[]}} 
			try:
				symbol_timeframe[symbol].update(timeframe)
			except KeyError:
				symbol_timeframe[symbol] = timeframe

		return json.dumps(symbol_timeframe, indent=4)


	def create_json_file(self):
		'''Creates and returns a json object string'''

		if os.path.exists(self.json_file):
			return None

		coin_data = json.loads(self.create_json_object())
		with open(self.json_file, 'w') as jf:
			json.dump(coin_data, jf, indent=4)

		print(f'New json file for {self.coin_symbol} has been created in: {self.json_file}')


	def update_json(self):
		'''Ensures stored csvfiles are synchronous with json by either adding or deleting csvfiles to/from json.'''
		
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
		new_csvfiles = csv_files.difference(json_data) # Set contains files stored which are not stored in json
		old_json_data = json_data.difference(csv_files) # Set contains files stored in json but not stored locally anymore
		
		if csv_files.symmetric_difference(json_data):
			# If there's new csv files not stored in database but not in json this adds them in.
			if new_csvfiles:
				new_data_json = json.loads(self.create_json_object(*new_csvfiles))
				for symbol in new_data_json:
					for timeframe in new_data_json[symbol]:
						timeframe_dict = {timeframe:new_data_json[symbol][timeframe]}
						try:
							coin_data[symbol].update(timeframe_dict)
						except KeyError:
							coin_data[symbol] = timeframe_dict

			# If there's csvfiles stored in json but not anymore in database this removes them from json.
			if old_json_data:
				for old_csvfile_name in old_json_data:
					symbol = old_csvfile_name.split('_')[0]
					timeframe = old_csvfile_name.split('_')[1].split('.')[0]
					coin_data[symbol].pop(timeframe)
					if len(coin_data[symbol]) == 0:
						coin_data.pop(symbol)

			with open(self.json_file, 'w') as jf:
				json.dump(coin_data, jf, indent=4) # Update json file.
			
			return 1 # To indicate an update of json file as occurred.


	def add_data_to_json(self):
		'''Retreves candle data starting from last updated date and then updates the json'''

		if not os.path.exists(self.json_file):
			raise Exception(f'Coin {self.coin_symbol} has no json file.')

		with open(self.json_file, 'r') as jf:
			coin_data = json.load(jf)

		to_remove = {} # Store list of keys to remove if json file is not up to date to stored csvfiles. 
		for symbol in coin_data:
			for timeframe in coin_data[symbol]:
				datafile = self.csv_filename(symbol.split(self.coin_symbol)[1], timeframe)
				with open(datafile) as csvfile:
					header = csvfile.readline()
					saved_data_len = int(header.split(':')[1].lstrip('0'))
					data_list = coin_data[symbol][timeframe]['candle_change']
					if len(data_list) < saved_data_len:
						skip = len(data_list) # Skip rows of csvfile until new data is reached. 
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
	
		with open(self.json_file, 'w') as jf:
			json.dump(coin_data, jf, indent=4)


	def update(self):
		'''Updates all csv and json files of given file object.'''
 
		# Perform this low cost update everytime update() is called. Ensures json file is synchronous with stored csvfiles. 
		need_update = False
		if self.update_json():
			need_update = True

		# More expensive update, only perform at most every hour (unless needed via need_update). This updates candle/json data.
		if need_update or self.previous_update_UTC == None or (time() - self.previous_update_UTC >= 3600):
			csv_files = self.list_saved_files()
			tradingpairs = set()
			trim = len(self.coin_symbol)
			for csvfile_name in csv_files:
				tradingpair = csvfile_name.split('_')[0][trim:]
				tradingpairs.add(tradingpair)
			for tradingpair in tradingpairs:
				stored_timeframes = self.get_timeframes(self.coin_symbol + tradingpair)
				self.get_candles(tradingpair, *stored_timeframes)
			self.add_data_to_json() # Adds latests candle data to json 


	def get_timeframes(self, symbol):
		'''Given a coin-trading pair, returns a list of stored timeframes.'''

		files = self.list_saved_files()
		stored_timeframes = []
		if files:
			for csvfile_name in files:
				symbol_timeframe = csvfile_name.split('.')[0]
				if symbol in symbol_timeframe:
					stored_timeframes.append(symbol_timeframe.split('_')[1])
		return stored_timeframes


	def current_score(self, tradingpairs=[]):
		'''Returns current calculated score.
		   Candle_max_up means: how well the current price change compares with all the historical maxiumal price changes.'''

		if not os.path.exists(self.json_file):
			raise Exception(f'Coin {self.coin_symbol} has no json file.')
		
		self.update() # Only updates every hour to be more efficent.

		score_bull = 0
		score_bear = 0
		score_dict = {}
		csv_files = self.list_saved_files()
		if tradingpairs:
			csv_files = [csvfile_name for tradingpair in tradingpairs for csvfile_name in csv_files if tradingpair in csvfile_name] # Only look at certain trading pairs. 
		for csvfile_name in csv_files:
			symbol = csvfile_name.split('_')[0]
			timeframe = csvfile_name.split('_')[1].split('.')[0]
			csvfile_name = self.coin_path + '/' + csvfile_name
			with open(csvfile_name, 'r', newline='') as csvfile:
				final_candle = csvfile.readline().split(':')[0]
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
			for timeframe in coin_data[symbol]:
				current_change = score_dict[symbol][timeframe]['candle_change']
				amplitude_change = score_dict[symbol][timeframe]['candle_amplitude']
				# print(f'timeframe: {timeframe} symbol {symbol} current_change {current_change} amplitude_change {amplitude_change}') #debug
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
					# print(f'symbol {symbol} timeframe {timeframe} data {data}: ' + str(performance) + '|' + str(current_change) + '|' + str(historical_average))
							
		for symbol in score_dict:
			for timeframe in score_dict[symbol]:
				if timeframe == 'price':
					continue
				for data in score_dict[symbol][timeframe]:
					if score_dict[symbol][timeframe][data] == 'NA':
						continue
					# print(f'symbol {symbol} timeframe {timeframe} data {data}: {score_dict[symbol][timeframe][data]} type is {type(score_dict[symbol][timeframe][data])}')
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
		#TODO: This will be a fairly complex method. 
		#Tasks: obtain 5min candle data to store ONLY as csv. Use each 5min row data as input into the historical_score method. Each row acts like real time measurments back in time.
		# These real time measurments will be used to create what the relative bull/bear score was back then. The goal is to use all these data points to create a graph 
		# This graph can be shown on the github readme to clearly show the program working and the product of the program
		# Additional metrixs of the graph will be: The % amp and % change PER 5 min, per timeframe (1h, 1d, 3d etc), so a lot of data.
		# The goal would be to be able to toggle on and off some of the lines, and try to find places where the score peaks, with %amp/%change peaking at ALH, then
		# also adding the price action to see whether you can deduce some clear moments to sell
		# in fact, using the historical price action, you can then determine customised bull/bear scores for a given coin
		# note: running this would take ages, so it should only be run once, then stored as a file with all the data. 
		# possibly add volumn data to this.

		# in terms of how: So image we have out dataset. We create a new json file which will dynamically grow, Starting from the beginning, each timeframe the passes, you update
		# the json file with the resulting % changes, but every 5 min you use this new small json file to run a current_score like method to get the bull/bear score and store that
		# in new csv - so a csv with all 5min from beginning and their relative scores + also append to each row (5min) the %change and %amp for each timeframe
		# so the new json will NOT contain 5min tf, but will contain 1h etc. and grow from size 0 up to the latest version, but each time it grows you do all these things.  

		# later on, I want to see if I can add other exchanges which have older data, maybe like bitrex
		pass

	def graph_historical_data(self):
		# Take notes from project-falcon
		# Perhaps make a class dedicated to graphing
		pass 

	def volumn(self):
		# convert INJ volumne data to usdt - add this data to graph 
		pass

	def volumn_score(self):
		# compare given candle volumne with all other historical volumns to generate a single score - add this data to graph 
		pass 

	def sell_assest(self):
		'''Use only during emergency, sells asset on binance'''

	def notify(self):
		pass
