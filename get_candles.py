from binance.client import Client # Third party 
from binance.exceptions import BinanceAPIException # Third party 
from config import API_KEY, API_SECRET
from glob import glob
from time import time
import pandas as pd
import json 
import csv
import os
import sys
import re


#https://python-binance.readthedocs.io/en/latest/market_data.html#id7
client = Client(API_KEY, API_SECRET) # new client object 


# make different coin objects, e.g. INJ, BTC, FTM etc. 
class Coin():
	'''A class which retrieves candle stick data for a given coin avaliable on Binance, performs TA on the stored data, can return a score.'''

	# All avaliable intervals on binance
	INTERVALS = {'1m':'p', '3m':'o', '5m':'n', '15m':'m', '30m':'l', '1h':'k', '2h':'j', '3h':'i',
				 '4h':'h', '6h':'g', '8h':'f', '12h':'e', '1d':'d', '3d':'c', '1w':'b', '1M':'a'}
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
		self.deafult_scoring_timeframes = ['30m', '1h', '4h', '12h', '1d', '3d'] # deafult set of timeframes used to compute score


	def get_candles(self, tradingpair, intervals = []):
		'''
		Handles the retreval of raw candle data from binance.
		If coin has no stored data (i.e. new coin for server) then this will retreve all historical data
		If coin has data stored, then this will retreve only the latest candle data. 	
		'''

		timeframes = [] 

		if type(tradingpair) != str:
			raise Exception(f'get_candles method requires a string for tradingpair parameter.') # TODO remove once everything is done, since only server uses this method

		[timeframes.append(str(interval)) for interval in intervals if str(interval) in self.INTERVALS] # Ensure all intervals provided are valid.
		if len(timeframes) != len(intervals):
			invalid = [entry for entry in intervals if entry not in timeframes and entry != '']
			if invalid:
				print(f"Warning: None of the optionals intervals in {invalid} will be added.\nEither they're already part of the deafult, or are invalid.")
		
		for timeframe in timeframes:
			datafile = self.csv_filename(tradingpair, timeframe)
			symbol = self.coin_symbol.upper() + tradingpair.upper()
			try:
				if os.path.exists(datafile):
					with open(datafile, 'r', newline='') as csvfile: 
						final_candle = csvfile.readline().split(':')[0] # Read first line of csv to obtain most recent UTC candle time saved 
					klines = client.get_historical_klines(symbol, timeframe, int(final_candle)) # Retreve only new candles from Binance API
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

		symbol_timeframe = symbol_timeframe[1:] # Remove leading 3
		datafile = self.coin_path + '/' + symbol_timeframe + '.csv'
		if os.path.exists(datafile):
			os.remove(datafile)
			print(f'{symbol_timeframe} has been removed.')
		else:
			print(f'{symbol_timeframe} is already not present in database.')
		if len(glob(self.coin_path + '/*')) == 0:
			self.remove_coin()


	def remove_tradingpair(self, symbol):
		'''Handles removal of trading pair from given coin'''

		symbol = symbol[1:] # Remove leading 2
		files = self.list_saved_files()
		for f in files:
			if symbol == f.split('_')[0]:
				os.remove(self.coin_path + '/' + f)
		print(f'All files assoicated with {symbol} have been removed.')
		if len(glob(self.coin_path + '/*')) == 0:
			self.remove_coin()

	def remove_coin(self):
		'''Handles removing coin'''

		files = glob(self.coin_path + '/*')
		for path in files:
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
					# Only activates when creating csv file for first time.
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
		
		# if (type(candle_open) and type(candle_high) and type(candle_low) and type(candle_close)) != float:
		# 	raise Exception(f'percent_change static method requires floats as arguments.')

		candle_change = (candle_close / candle_open)*100 - 100
		candle_amplitude = (candle_high / candle_low)*100 - 100
		candle_max_up = (candle_high / candle_open)*100 - 100 
		candle_max_down = abs((candle_low / candle_open)*100 - 100)

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
							coin_data[symbol][timeframe][data].sort()
	
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
				self.get_candles(tradingpair, intervals=stored_timeframes)
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


	def current_score(self, to_monitor=[]):
		'''Returns current calculated score.
		   Candle_max_up means: how well the current price change compares with all the historical maxiumal price changes.'''

		if not os.path.exists(self.json_file):
			raise Exception(f'Coin {self.coin_symbol} has no json file.')	
		self.update() # Only updates every hour to be more efficent.

		score_bull = 0
		score_bear = 0
		price = 0
		score_dict = {}
		csv_files = self.list_saved_files()
		if to_monitor:
			csv_files = [csvfile_name for symbol_timeframe in to_monitor for csvfile_name in csv_files if symbol_timeframe in csvfile_name] # Only look at certain trading pairs. 

		for csvfile_name in csv_files:
			symbol = csvfile_name.split('_')[0]
			timeframe = csvfile_name.split('_')[1].split('.')[0]
			csvfile_name = self.coin_path + '/' + csvfile_name
			with open(csvfile_name, 'r', newline='') as csvfile:
				final_candle = csvfile.readline().split(':')[0]
				klines = client.get_historical_klines(symbol, timeframe, int(final_candle))[0]
				try:
					score_dict[symbol]
					score_dict[symbol][timeframe] = self.percent_changes(float(klines[1]), float(klines[2]), float(klines[3]), float(klines[4]))
				except KeyError:
					score_dict[symbol] = {timeframe:self.percent_changes(float(klines[1]), float(klines[2]), float(klines[3]), float(klines[4]))}			
					price = klines[4]

		with open(self.json_file, 'r') as jf:
			coin_data = json.load(jf)

		for symbol in score_dict:
			for timeframe in score_dict[symbol]:
				current_change = score_dict[symbol][timeframe]['candle_change']
				amplitude_change = score_dict[symbol][timeframe]['candle_amplitude']
				score_dict[symbol][timeframe] = ''
				if current_change > 0:
					change = "candle_max_up"
				else:
					change = "candle_max_down"
				for metric in ("candle_amplitude", change):
					historical_candles_changes = coin_data[symbol][timeframe][metric]
					historical_average = self.average(coin_data[symbol][timeframe][metric])
					size = len(coin_data[symbol][timeframe][metric])
					left, right, mid = (0, size, 0)
					while left <= right: # binary search O(logn)
						mid = (left + right) // 2
						if historical_candles_changes[mid] == current_change:
							break
						if mid == 0 or mid == size - 1:
							break
						if historical_candles_changes[mid - 1] > current_change and historical_candles_changes[mid + 1] < current_change:
							break
						elif current_change > historical_candles_changes[mid]:
							right = mid - 1
						else:
							left = mid + 1
					performance = round((mid / size)*100, 1)
					score = self.score_performance(performance)
					if metric == "candle_amplitude":
						score_dict[symbol][timeframe][metric] = [performance, amplitude_change, historical_average]
					elif metric == "candle_max_up":
						score_bull += score
						score_dict[symbol][timeframe][metric] = [performance, current_change, historical_average]
					else:
						score_bear += score
						score_dict[symbol][timeframe][metric] = [performance, current_change, historical_average]
			
		for symbol in score_dict:
			for timeframe in score_dict[symbol]:
				for metric in score_dict[symbol][timeframe]:
					performance = score_dict[symbol][timeframe][metric][0]
					change = score_dict[symbol][timeframe][metric][1]
					average = score_dict[symbol][timeframe][metric][2]

					# This means the current candle performed in the top 20% or above of all historical candles (i.e. bull - sell)
					if performance <= 20:
						score_dict[symbol][timeframe][metric] = "Rank is: " + str(performance) + f' | change is: {change}%' + f' | average is: {average}%' 
					# This means the current candle performed in the bottom 80% or bellow all historical candles (i.e. bear - buy)
					elif performance >= 80:
						score_dict[symbol][timeframe][metric] = "Rank is: " + str(performance) + f' | change is: {change}%' + f' | average is: {average}%' 
					else:
						# Nothing special, just ignore. 
						score_dict[symbol][timeframe][metric] = 'AVERAGE'

		return [f'{self.coin_symbol}', score_bull, score_bear, price, score_dict, 'coin_score']
		

	def generate_result_files(self, mode):
		self.generate_summary_csv(mode)
		self.graph_historical_data(mode)


	def generate_summary_csv(self, mode):
		pass

	
	def score_performance(self, performance):
		if performance <= 2.5:
			return 6
		elif performance <= 5:
			return 5
		elif performance <= 10:
			return 4
		elif performance <= 15:
			return 3
		elif performance <= 20:
			return 2
		elif performance <= 25:
			return 1
		return 0


	def get_most_recent_candles(self, symbol_timeframe):
		
		# symbol_timeframe in the form BTCUSDT_4h
		csvfile_name = self.coin_path + '/' + symbol_timeframe + '.csv'
		if os.path.exists(csvfile_name):
			with open(csvfile_name, 'r', newline='') as csvfile:
				final_candle = csvfile.readline().split(':')[0]
				klines = client.get_historical_klines(symbol_timeframe.split('_')[0], symbol_timeframe.split('_')[1], int(final_candle))
				return klines[0]
		raise Exception(f'Coin {symbol_timeframe} has no csv file.')
		

	
	def compute_historical_score(self, symbol, custom_timeframes = []):
		'''Returns calculated score.
		   Candle_max_up means: how well the current price change compares with all the historical maxiumal price changes.'''

		# just do one symbol
		# This function will compute the whole thing in one run
		# Store all 5m symbol csv into dataframe - each four columns are new symbol, e.g. injbtc-open injbtc-low injbtc-high injbtc-close injusdt-open, each row is 5m
		# infact, to compute the real time percentage changes, you can slice the dataframe per day/3day etc.

		# symbols -> e.g. [INJBTC, INJUSDT, INJBNB] - so always will be of a single coin since it's per coin object
		# custom_timeframes are for when you want to find historical scoring on timeframes other than deafult ['30m', '1h', '4h', '12h', '1d', '3d']


		# if not os.path.exists(self.json_file):
		# 	raise Exception(f'Coin {self.coin_symbol} has no json file.')	
		# self.update() # Only updates every hour to be more efficent.
		
		symbol_timeframes = []
		if custom_timeframes:
			symbol_timeframes = [symbol + '_' + timeframe for timeframe in custom_timeframes]
		else:
			symbol_timeframes = [symbol + '_' + timeframe for timeframe in self.deafult_scoring_timeframes]

		# make historical_realtime_priceaction_DF which has columns UTC-date, open, high, low, close for 5min timeframe, and bull/bear/amp columns for each timeframe
		csv_filepath = self.coin_path + '/' + symbol + "_5m.csv"
		columns = ["UTC", symbol + "-open", symbol + "-high", symbol + "-low", symbol + "-close"]
		historical_realtime_priceaction_DF = pd.read_csv(csv_filepath, usecols=[0, 1, 2, 3, 4], names=columns, header=None, skiprows=1)

		# make dataframe to store 5min price, bull bear amplitude info for each timeframe
		historical_scoring_DF = pd.DataFrame()
		historical_scoring_DF["bull_score"] = ""
		historical_scoring_DF["bear_score"] = ""
		for symbol_timeframe in symbol_timeframes:
			historical_scoring_DF[symbol_timeframe] = list # [bull, bear, amplitude]

		# make symbol_timeframes_DF which has columns for UTC-date, open, high, low, close, of all timeframes in symbol_timeframes
		df_positiontracker = {}
		historical_percent_changes = {}
		symbol_timeframes_DF = pd.DataFrame()
		for symbol_timeframe in symbol_timeframes:
			csv_filepath = self.coin_path + '/' + symbol_timeframe + '.csv'
			columns = [symbol_timeframe + "-UTC", symbol_timeframe + "-open", symbol_timeframe + "-high", symbol_timeframe + "-low", symbol_timeframe + "-close"]
			temp_DF = pd.read_csv(csv_filepath, usecols=[0, 1, 2, 3, 4], names=columns, header=None, skiprows=1)
			df_positiontracker[symbol_timeframe] = {"index":0, "open_price":temp_DF.loc[0,[columns[1]]],
													"high_price":temp_DF.loc[0, [columns[2]]],
													"low_price":temp_DF.loc[0, [columns[3]]],
													"next_UTC":temp_DF.loc[1, [columns[0]]]}
			previous_UTC = temp_DF.loc[0, [columns[0]]]
			next_UTC = temp_DF.loc[1, [columns[0]]]
			temp_series = historical_realtime_priceaction_DF.loc[historical_realtime_priceaction_DF.UTC.between(previous_UTC, next_UTC), symbol + "-close"] 
			df_positiontracker[symbol_timeframe]["max_5min"] = temp_series.max()
			df_positiontracker[symbol_timeframe]["min_5min"] = temp_series.min()
			historical_percent_changes[symbol_timeframe] = {'candle_amplitude':[], 'candle_max_up':[], 'candle_max_down':[]}
			symbol_timeframes_DF = symbol_timeframes_DF.merge(right=temp_DF, how="outer", left_index=True, right_index=True)
		

		# initialise reference json to contain the first 21 days of price action percentage changes (candle_amplitude, candle_max_up, candle_max_down)
		week_3_UTC = int(symbol_timeframes_DF.loc[21, [symbol + '_1d-UTC']]) # UTC date for 21 days of price action
		print(f"3 week UTC: {week_3_UTC}")
		for symbol_timeframe in symbol_timeframes:
			columns = [symbol_timeframe + "-UTC", symbol_timeframe + "-open", symbol_timeframe + "-high", symbol_timeframe + "-low", symbol_timeframe + "-close"]
			percent_changes_list = [self.percent_changes(row[1],row[2],row[3],row[4]) for row in symbol_timeframes_DF[columns].to_numpy() if row[0] <= week_3_UTC]
			for metric in historical_percent_changes[symbol_timeframe]:
				historical_percent_changes[symbol_timeframe][metric] = [row[metric] for row in percent_changes_list]
			historical_percent_changes[symbol_timeframe][metric].sort()
		
		# percent_changes(candle_open, candle_high, candle_low, candle_close):
		# scoring mechanism: 
			# compute the current percentage change - using 5 min 
				# provide the percent_changes() method with: open, high, low of given timeframe (using lambda min/max) + close (5min)
				# capture the current_change only, and use that for the bellow calc
			# if positive, then compare current change with sorted historical max_up_change percentages - give ranking, compute bull score
			# if negative, then compare current change with sorted historical max_down_change percentages - give ranking, compute bear score
			# also add the amplitude change 
			# we don't actually need 'candle_change' metrix, rather, only need the current_change
		
		# loop through every 5 minutes (acting as histroical realtime)
		# for every 5 minutes 
		for row in historical_realtime_priceaction_DF.itertuples(name=None): # itertuples is 100x faster than iterrows
			(current_UTC, high_5m, low_5m, close_5m) = row[0, 2, 3, 4]
			total_bull, total_bear = 0, 0
			if current_UTC <= week_3_UTC:
				continue
			for symbol_timeframe in symbol_timeframes:
				if current_UTC < df_positiontracker[symbol_timeframe]["next_UTC"]:
					index = df_positiontracker[symbol_timeframe]["index"]
					if index + 1 == symbol_timeframes_DF.shape[0]:
						continue

					index += 1
					previous_UTC = df_positiontracker[symbol_timeframe]["next_UTC"]
					if index + 1 == symbol_timeframes_DF.shape[0]:
						next_index = index
						previous_UTC = symbol_timeframes_DF.loc[index - 1, [columns[0]]]
					else:
						next_index = index + 1

					columns = [symbol_timeframe + "-UTC", symbol_timeframe + "-open", symbol_timeframe + "-high", symbol_timeframe + "-low", symbol_timeframe + "-close"]
					df_positiontracker[symbol_timeframe] = {"index":index, "open_price":symbol_timeframes_DF.loc[index, [columns[1]]],
															"high_price":symbol_timeframes_DF.loc[index, [columns[2]]],
															"low_price":symbol_timeframes_DF.loc[index, [columns[3]]], 
															"next_UTC":symbol_timeframes_DF.loc[next_index, [columns[0]]]}
					next_UTC = df_positiontracker[symbol_timeframe]["next_UTC"]
					temp_series = historical_realtime_priceaction_DF.loc[historical_realtime_priceaction_DF.UTC.between(previous_UTC, next_UTC), symbol + "-close"]
					df_positiontracker[symbol_timeframe]["max_5min"] = temp_series.max()
					df_positiontracker[symbol_timeframe]["min_5min"] = temp_series.min()

					# update reference json here
					percent_changes_symboltimeframe = self.percent_changes(df_positiontracker[symbol_timeframe]["open_price"],
																			df_positiontracker[symbol_timeframe]["high_price"],
																			df_positiontracker[symbol_timeframe]["low_price"],
																			df_positiontracker[symbol_timeframe]["close_price"])
					for metric in historical_percent_changes[symbol_timeframe]:
						historical_percent_changes[symbol_timeframe][metric].append(percent_changes_symboltimeframe[metric])
						historical_percent_changes[symbol_timeframe][metric].sort() #nlogn - however list is already pre-sorted

					# make this above into a function
				if high_5m == df_positiontracker[symbol_timeframe]["max_5min"]:
					high_5m = df_positiontracker[symbol_timeframe]["high_price"] # note remember if you wanted amplitude info per 5min, use local_max_5min
				if low_5m == df_positiontracker[symbol_timeframe]["min_5min"]:
					low_5m = df_positiontracker[symbol_timeframe]["low_price"]
				
				percent_changes_5m = self.percent_changes(df_positiontracker[symbol_timeframe]["open_price"], high_5m, low_5m, close_5m)
				current_percent_change = percent_changes_5m["candle_change"]
				if current_percent_change > 0:
					metric = "candle_max_up"
				else:
					metric = "candle_max_down"
				size = len(historical_percent_changes[symbol_timeframe][metric])
				left, right, mid = (0, size, 0)
				while left <= right: # binary search O(logn)
					mid = (left + right) // 2
					if historical_percent_changes[symbol_timeframe][metric][mid] == current_percent_change:
						break
					if mid == 0 or mid == size - 1:
						break
					if historical_percent_changes[symbol_timeframe][metric][mid - 1] > current_percent_change and historical_percent_changes[symbol_timeframe][metric][mid + 1] < current_percent_change:
						break
					elif current_percent_change > historical_percent_changes[symbol_timeframe][metric][mid]:
						right = mid - 1
					else:
						left = mid + 1
				performance = round((mid / size)*100, 1)
				score = self.score_performance(performance)
				if metric == "candle_max_up":
					total_bull += score
					historical_scoring_DF.loc[current_UTC, symbol_timeframe] = [score, 0]
				else:
					total_bear += score
					historical_scoring_DF.loc[current_UTC, symbol_timeframe] = [0, score]
			historical_scoring_DF.loc[current_UTC, "bull_score"] = total_bull
			historical_scoring_DF.loc[current_UTC, "bear_score"] = total_bear




	def historical_score(self):
		# Do this using pandas
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

		# Note: so the 5 minute time frames are used to simulate the 1h, 4h etc. timeframes to then compute the scores - 
		# I think to start we need at least 3 weeks of data 
		
		# scoring function: 
			# for all coins, the following timeframes are required for computing score
			# 30 min, 1h, 4h, 12h, 1d, 3d
			# potentially make it so you can additionally add 1w and 1M if there's a lot of history
			# return both the total score, and the score for each timeframe (e.g. 30min has 5, 1h was 6, 4h was 1 etc.) to give clearer idea
			# input: current percentrages for those timeframes + json of those timeframes
				# function will be used by realtime and historical (via 5 min)
			# implementation: simply break up the method above into a printing method and scoring method 

		# later on, I want to see if I can add other exchanges which have older data, maybe like bitrex

		#TODO I think I will make two kinds of csvs - one for presentation (i.e. for emailing) and one for computation (i.e. scoring)
		# The scoring csvs will be loaded into pandas df -> anaylsis -> then using pandas plotting for the graphing 
		pass
		# stanard variable naming
		# BTC == coin_symbol
		# USDT == trading_pair
		# 4h == timeframe
		# BTCUSDT == symbol
		# BTCUSDT_4h == symbol_timeframe

	def graph_historical_data(self, mode):
		# Do this using matplotlib/pandas
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

coin = Coin('INJ')
coin.compute_historical_score('INJUSDT')