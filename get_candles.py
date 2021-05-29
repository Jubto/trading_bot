from typing import final
from binance.client import Client # Third party 
from binance.exceptions import BinanceAPIException # Third party 
from config import API_KEY, API_SECRET
from glob import glob
from time import time, sleep
import pandas as pd
import bisect
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
		self.deafult_scoring_timeframes = ['1h', '4h', '12h', '1d', '3d'] # deafult set of timeframes used to compute score

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
						final_candle = csvfile.readline().split(',')[0] # Read first line of csv to obtain most recent UTC candle time saved 
					klines = client.get_historical_klines(symbol, timeframe, int(final_candle)) # Retreve only new candles from Binance API
					self.csv_maker(datafile, 'a', klines) # Append only new candles
					self.csv_maker(datafile, 'r+', klines) # Update the latest UTC candle to the first line of .csv
					if timeframe == '1h':
						with open(datafile, 'r', newline='') as csvfile:
							self.previous_update_UTC = int(csvfile.readline().split(',')[0]) # Keeps track of the latest hour coin was updated.
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
					num_rows = num_rows + int(header.split(',')[1].lstrip('0'))
					csvfile.seek(0)
					csvfile.write(f'{final_candle},{num_rows:030},{pointer:060}') # Add updated header to beginning. 
					return 1

			csv_writer = csv.writer(csvfile, delimiter=',') 
			[csv_writer.writerow(kline) for kline in klines[:-1]] # Don't add final candle row as that candle hasn't closed yet		
			if mode == 'w':
				# If block only activates when creating csv file for first time. 
				pointer = csvfile.tell()
				csvfile.seek(0)
				csvfile.write(f'{final_candle},{num_rows:030},{pointer:060}\n') # Add header, length always stays constant. 


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
					csv_reader = csv.reader(csvfile)
					header = csv_reader.__next__()
					saved_data_len = int(header[1].lstrip('0'))
					data_list = coin_data[symbol][timeframe]['candle_change']
					if len(data_list) < saved_data_len:
						skip = len(data_list) # Skip rows of csvfile until new data is reached. 
						change_dict_list = []
						for row in csv_reader:
							if skip > 0:
								skip -= 1
								continue
							change_dict_list.append(self.percent_changes(float(row[1]), float(row[2]), float(row[3]), float(row[4])))

						for new_data in change_dict_list:
							for metric in coin_data[symbol][timeframe]:
								bisect.insort(coin_data[symbol][timeframe][metric], new_data[metric]) # add to sorted list
	
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
			tradingpair_timeframes = {}
			for csvfile_name in csv_files:
				tradingpair = csvfile_name.split('_')[0].split(self.coin_symbol)[-1]
				timeframe = csvfile_name.split('_')[1].split('.')[0]
				if timeframe == '5m':
					continue # 5min should only be updated for historical score method
				if tradingpair in tradingpair_timeframes:
					tradingpair_timeframes[tradingpair].append(timeframe)
				else:
					tradingpair_timeframes[tradingpair] = [timeframe]
			for tradingpair in tradingpair_timeframes:
				self.get_candles(tradingpair, intervals=tradingpair_timeframes[tradingpair])
			self.add_data_to_json() # Adds latests candle data to json 


	def current_score(self, to_monitor=[]):
		'''Returns current calculated score.
		   Bull/Bear score indicates how well the current price action performs compared to all histortical candle data
		   Retain_score indicates how likely the current price will retain based on historical data
		   Amplitude score indicates how volitile the current price action is compared to history'''

		if not os.path.exists(self.json_file):
			raise Exception(f'Coin {self.coin_symbol} has no json file.')	
		self.update() # Only updates every hour to be more efficent.

		score_bull, score_bear, price, score_dict = 0, 0, 0, {}
		csv_files = self.list_saved_files()
		if to_monitor:
			csv_files = [csvfile_name for symbol_timeframe in to_monitor for csvfile_name in csv_files if symbol_timeframe in csvfile_name] # Only look at certain trading pairs. 
		with open(self.json_file, 'r') as jf:
			coin_data = json.load(jf)

		# loading in current price action
		for csvfile_name in csv_files:
			symbol = csvfile_name.split('_')[0]
			timeframe = csvfile_name.split('_')[1].split('.')[0]
			csvfile_name = self.coin_path + '/' + csvfile_name
			with open(csvfile_name, 'r', newline='') as csvfile:
				final_candle = csvfile.readline().split(',')[0]
				klines = client.get_historical_klines(symbol, timeframe, int(final_candle))[0] # Get latest candles
				try:
					score_dict[symbol][timeframe] = self.percent_changes(float(klines[1]), float(klines[2]), float(klines[3]), float(klines[4]))
				except KeyError:
					score_dict[symbol] = {timeframe:self.percent_changes(float(klines[1]), float(klines[2]), float(klines[3]), float(klines[4]))}			
					price = klines[4]

		# compute score of current price action based on histortical data
		for symbol in score_dict:
			for timeframe in score_dict[symbol]:
				current_change = score_dict[symbol][timeframe]['candle_change']
				amplitude_change = score_dict[symbol][timeframe]['candle_amplitude']
				score_dict[symbol][timeframe] = ''
				if current_change > 0:
					metric = "candle_max_up"
				else:
					metric = "candle_max_down"
				amp_score = self.score_amplitude(
					amp_list= coin_data[symbol][timeframe]["candle_amplitude"],
					size= len(coin_data[symbol][timeframe]["candle_amplitude"]),
					amplitude_change= amplitude_change)
				score, retain_score = self.score_performance(
					max_list= coin_data[symbol][timeframe][metric],
					change_list= coin_data[symbol][timeframe]["candle_change"],
					size= len(coin_data[symbol][timeframe][metric]),
					absolute_change= abs(current_change),
					current_percent_change= current_change)

				# Construct current scoring summary dict to send to server
				if amp_score:
					historical_average = self.average(coin_data[symbol][timeframe]["candle_amplitude"])
					score_dict[symbol][timeframe]["candle_amplitude"] = f"Score: {amp_score} | Current change: {amplitude_change}% | average: {historical_average}%"
				else:
					score_dict[symbol][timeframe][metric] = 'AVERAGE' # Means current price action is bellow the top 75% of history, i.e. not important
				
				if score:
					historical_average = self.average(coin_data[symbol][timeframe][metric])
					score_dict[symbol][timeframe][metric] = f"Score: {score} | Retainment score: {retain_score} | Current change: {current_change}% | average: {historical_average}%"
					if metric == "candle_max_up":
						score_bull += score
					else:
						score_bear += score
				else:
					score_dict[symbol][timeframe][metric] = 'AVERAGE'
		return [self.coin_symbol, score_bull, score_bear, price, score_dict, 'coin_score']

	
	def compute_historical_score(self, symbol, custom_timeframes = []):
		'''Calculates bull/bear/retainment score for all 5 minute intervals of the coins history.
		Each 5 minutes simulates running the current score method back in time, with information known only back during the 5minute interval
		Bull/Bear score indicates how well the current price action performs compared to all histortical candle data
		Retain_score indicates how likely the current price will retain based on historical data
		If prior historical analysis is present, only the latest data will be computed and appended.'''

		# Get latest candles
		self.update() # Only updates at most every hour.
		self.get_candles(symbol.split(self.coin_symbol)[-1], intervals=["5m"]) # update latest 5min data - this will take time due to binance API
		if custom_timeframes:
			symbol_timeframes = [symbol + '_' + timeframe for timeframe in custom_timeframes] # todo: need to uniquely name csv file based on which timeframes used
		else:
			symbol_timeframes = [symbol + '_' + timeframe for timeframe in self.deafult_scoring_timeframes]
		
		# make dataframe to hold all historical 5min intervals. Scores will be inserted at the end
		csv_filepath = self.coin_path + '/' + symbol + "_5m.csv"
		columns = ["UTC", "price"]
		historical_realtime_priceaction_DF = pd.read_csv(csv_filepath, usecols=[0, 4], names=columns, header=None, skiprows=1)
		bull_scores = []
		bear_scores = []
		retain_scores = [] # the degree to which the current price will retain it's price based on history
		timeframe_score_tracker = {}
		for symbol_timeframe in symbol_timeframes:
			timeframe_score_tracker[symbol_timeframe + "_BULL"] = []
			timeframe_score_tracker[symbol_timeframe + "_BEAR"] = []

		# make symbol_timeframes_DF which has columns for UTC-date, open, high, low, close, of all timeframes in symbol_timeframes
		historical_percent_changes = {}
		symbol_timeframes_DF = pd.DataFrame()
		for symbol_timeframe in symbol_timeframes:
			csv_filepath = self.coin_path + '/' + symbol_timeframe + '.csv'
			columns = [symbol_timeframe + "-UTC", symbol_timeframe + "-open", symbol_timeframe + "-high", symbol_timeframe + "-low", symbol_timeframe + "-close"]
			temp_DF = pd.read_csv(csv_filepath, usecols=[0, 1, 2, 3, 4], names=columns, header=None, skiprows=1)
			historical_percent_changes[symbol_timeframe] = {'candle_change':[], 'candle_max_up':[], 'candle_max_down':[]}
			symbol_timeframes_DF = symbol_timeframes_DF.merge(right=temp_DF, how="outer", left_index=True, right_index=True)

		# Perform initilisation if no prior historical analysis found, else load from previous data and skip until new data
		df_positiontracker = {}
		if os.path.exists(self.coin_path + f"/historical/{symbol}_historical_scoring.csv"):
			with open(self.coin_path + f"/historical/{symbol}_historical_analysis.json", 'r') as jf:
				historical_percent_changes = json.load(jf) 
			skip = pd.read_csv(self.coin_path + f"/historical/{symbol}_historical_scoring.csv").iloc[-1][0] # skip to where the last historical analysis ends
			for symbol_timeframe in symbol_timeframes:
				if symbol_timeframes_DF.index[symbol_timeframes_DF[symbol_timeframe + '-UTC'] >= skip].any():
					index = symbol_timeframes_DF.index[symbol_timeframes_DF[symbol_timeframe + '-UTC'] >= skip][0] # get first index past skip
					df_positiontracker[symbol_timeframe] = {
						"index":index,
						"open_price":symbol_timeframes_DF.loc[index - 1, [symbol_timeframe + "-open"]][0],
						"next_UTC": symbol_timeframes_DF.loc[index, [symbol_timeframe + "-UTC"]][0]}
				else:
					index = symbol_timeframes_DF[symbol_timeframes_DF[symbol_timeframe + '-UTC'].notnull()].shape[0] - 1 # get final index position
					df_positiontracker[symbol_timeframe] = {
						"index":index,
						"open_price":symbol_timeframes_DF.loc[index, [symbol_timeframe + "-open"]][0],
						"next_UTC": symbol_timeframes_DF.loc[index, [symbol_timeframe + "-UTC"]][0]}
		else:
			# initialise dataframe and json for the first 3 -> 21 days of price action 
			if not os.path.exists(self.coin_path + '/historical'):
				os.mkdir(self.coin_path + '/historical')
			first_3day_UTC = int(symbol_timeframes_DF.loc[3, [symbol + '_1d-UTC']]) # The first few days of price action are unreliable due to volitility in general
			skip = int(symbol_timeframes_DF.loc[21, [symbol + '_1d-UTC']]) # UTC date for 21 days of price action
			for symbol_timeframe in symbol_timeframes:
				columns = [symbol_timeframe + "-UTC", symbol_timeframe + "-open", symbol_timeframe + "-high", symbol_timeframe + "-low", symbol_timeframe + "-close"]
				percent_changes_list = [self.percent_changes(row[1],row[2],row[3],row[4]) for row in symbol_timeframes_DF[columns].to_numpy() if row[0] > first_3day_UTC and row[0] <= skip]
				first_3day_skip = symbol_timeframes_DF.index[symbol_timeframes_DF[symbol_timeframe + '-UTC'] >= first_3day_UTC][0]
				index = len(percent_changes_list) + first_3day_skip  # location of three week UTC index position in dataframe for each timeframe 
				df_positiontracker[symbol_timeframe] = {
					"index":index,
					"open_price":symbol_timeframes_DF.loc[index, [columns[1]]][0],
					"next_UTC": symbol_timeframes_DF.loc[index + 1, [columns[0]]][0]}			
				for metric in historical_percent_changes[symbol_timeframe]:
					historical_percent_changes[symbol_timeframe][metric] = [row[metric] for row in percent_changes_list]
					historical_percent_changes[symbol_timeframe][metric].sort()
		historical_realtime_priceaction_DF = historical_realtime_priceaction_DF.loc[historical_realtime_priceaction_DF.UTC > skip].reset_index().drop("index", axis=1) 

		# Score every 5 minute interval of given coin with information known only during that time - (100 days of price action < 5 seconds)
		for row in historical_realtime_priceaction_DF.itertuples(name=None): 
			current_UTC, price, total_bull, total_bear, total_retain = row[1], row[2], 0, 0, 0
			for symbol_timeframe in symbol_timeframes:

				if current_UTC >= df_positiontracker[symbol_timeframe]["next_UTC"]:
					index = df_positiontracker[symbol_timeframe]["index"] # get current index
					final_index = symbol_timeframes_DF[symbol_timeframes_DF[symbol_timeframe + '-UTC'].notnull()].shape[0] # get final index
					if index + 1 == final_index:
						df_positiontracker[symbol_timeframe]["next_UTC"] = float('inf') # Reached the end for this timeframe
					else:
						index += 1
						if index + 1 == final_index:
							next_index, i = index, 0 # second last index for given timeframe
						else:
							next_index, i = index + 1, 1
							
						# update symbol_timeframe position in dataframe
						columns = [symbol_timeframe + "-UTC", symbol_timeframe + "-open", symbol_timeframe + "-high", symbol_timeframe + "-low", symbol_timeframe + "-close"]
						current_symbol_row = symbol_timeframes_DF.loc[index:next_index, columns].values		
						df_positiontracker[symbol_timeframe] = {
							"index":index, "open_price":current_symbol_row[0][1],
							"high_price":current_symbol_row[0][2],
							"low_price":current_symbol_row[0][3],
							"close_price":current_symbol_row[0][4],
							"next_UTC":current_symbol_row[i][0]}						
						
						# update dynamically growing performance ranking json 
						percent_changes_symboltimeframe = self.percent_changes(
							df_positiontracker[symbol_timeframe]["open_price"],
							df_positiontracker[symbol_timeframe]["high_price"],
							df_positiontracker[symbol_timeframe]["low_price"],
							df_positiontracker[symbol_timeframe]["close_price"])
						for metric in historical_percent_changes[symbol_timeframe]:
							bisect.insort(historical_percent_changes[symbol_timeframe][metric], percent_changes_symboltimeframe[metric]) # insert value into sorted list
				
				# calculate score
				current_percent_change = (price / df_positiontracker[symbol_timeframe]["open_price"])*100 - 100
				if current_percent_change > 0:
					metric = "candle_max_up"
				else:
					metric = "candle_max_down"
				score, retain_score = self.score_performance(
					max_list= historical_percent_changes[symbol_timeframe][metric], 
					change_list= historical_percent_changes[symbol_timeframe]["candle_change"],
					size= len(historical_percent_changes[symbol_timeframe][metric]), 
					absolute_change= abs(current_percent_change), 
					current_percent_change= current_percent_change)
				total_retain += retain_score
				if metric == "candle_max_up":
					total_bull += score
					timeframe_score_tracker[symbol_timeframe + "_BULL"].append(score)
					timeframe_score_tracker[symbol_timeframe + "_BEAR"].append(0)
				else:
					total_bear += score
					timeframe_score_tracker[symbol_timeframe + "_BEAR"].append(score)
					timeframe_score_tracker[symbol_timeframe + "_BULL"].append(0)

			bull_scores.append(total_bull)
			bear_scores.append(total_bear)
			retain_scores.append(total_retain)

		if os.path.exists(self.coin_path + f"/historical/{symbol}_historical_scoring.csv"):
			columns = ["bull_scores", "bear_scores", "retain_scores", *[timeframe for timeframe in timeframe_score_tracker]]
			column_data = [bull_scores, bear_scores, retain_scores, *[timeframe_score_tracker[timeframe] for timeframe in timeframe_score_tracker]]
			newdata_DF = pd.DataFrame({column:data for column, data in zip(columns, column_data)})
			newdata_DF = historical_realtime_priceaction_DF.merge(right=newdata_DF, how="outer", left_index=True, right_index=True)
			newdata_DF.to_csv(self.coin_path + f"/historical/{symbol}_historical_scoring.csv", mode='a', header=False, index=False)
		else:
			historical_realtime_priceaction_DF.insert(2, "bull_scores", bull_scores)
			historical_realtime_priceaction_DF.insert(3, "bear_scores", bear_scores)
			historical_realtime_priceaction_DF.insert(4, "retain_scores", retain_scores)
			[historical_realtime_priceaction_DF.insert(5, timeframe, timeframe_score_tracker[timeframe]) for timeframe in timeframe_score_tracker]
			historical_realtime_priceaction_DF.to_csv(self.coin_path + f"/historical/{symbol}_historical_scoring.csv", index=False)
		
		with open(self.coin_path + f"/historical/{symbol}_historical_analysis.json", 'w') as jf:
			json.dump(historical_percent_changes, jf, indent=4) 


	@staticmethod
	def score_performance(max_list, change_list, size, absolute_change, current_percent_change):
		'''Scoring method. Determines what rank the current price action holds against historical data
		If the performance is greater than the top 75% of price action history, then it can obtain some score.'''

		score, retain = 0, 0
		if absolute_change >= max_list[int(size * 0.75)]: 
			if absolute_change <= max_list[int(size * 0.8)]:
				score = 1
			elif absolute_change <= max_list[int(size * 0.85)]:
				score = 2
			elif absolute_change <= max_list[int(size * 0.9)]:
				score = 3
			elif absolute_change <= max_list[int(size * 0.95)]:
				score = 4
			elif absolute_change <= max_list[int(size * 0.975)]:
				score = 5
			else:
				score = 6
			if current_percent_change > 0 and current_percent_change >= change_list[int(size * 0.9)]:
				retain = 1
				if current_percent_change <= change_list[int(size * 0.95)]:
					retain = 2
				elif current_percent_change <= change_list[int(size * 0.97)]:
					retain = 3
				elif current_percent_change <= change_list[int(size * 0.98)]:
					retain = 4
				elif current_percent_change <= change_list[int(size * 0.99)]:
					retain = 5
				else:
					retain = 6
			elif current_percent_change < 0 and current_percent_change <= change_list[int(size * 0.1)]:
				retain = 1
				if current_percent_change >= change_list[int(size * 0.05)]:
					retain = 2
				elif current_percent_change >= change_list[int(size * 0.03)]:
					retain = 3
				elif current_percent_change >= change_list[int(size * 0.02)]:
					retain = 4
				elif current_percent_change >= change_list[int(size * 0.01)]:
					retain = 5
				else:
					retain = 6
		return score, retain


	@staticmethod
	def score_amplitude(amp_list, size, amplitude_change):
		'''Returns current amplitude score'''

		if amplitude_change >= amp_list[int(size * 0.75)]: 
			if amplitude_change <= amp_list[int(size * 0.8)]:
				return 1
			elif amplitude_change <= amp_list[int(size * 0.85)]:
				return 2
			elif amplitude_change <= amp_list[int(size * 0.9)]:
				return 3
			elif amplitude_change <= amp_list[int(size * 0.95)]:
				return 4
			elif amplitude_change <= amp_list[int(size * 0.975)]:
				return 5
			else:
				return 6
		return 0


	@staticmethod
	def percent_changes(candle_open, candle_high, candle_low, candle_close):
		'''Returns % change, % amplitude, max % up, max % down of a given candle'''
		
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


	def historical_score(self):
		pass
		
		# make a graph which shows the profit/loss from selling/buying 1h, 4h, 1day, 2day, 3day, 1week from each pair
		# This notifications will be based on: first calculating the current bull/bear score + retain score, then seeing how those scores compare with
		# the historical scores, if the current score is the highest among all previous scores, then clearly it's a big deal
		# stanard variable naming
		# BTC == coin_symbol
		# USDT == trading_pair
		# 4h == timeframe
		# BTCUSDT == symbol
		# BTCUSDT_4h == symbol_timeframe

	def graph_historical_data(self, mode):
		# Do this using matplotlib/pandas
		# Two graphs, Bull and bear: have top 15 scores (i.e. score 30 -> 15) as x_axis, for each one, have three virticle bars
			# incorporate the retain_score, the higher the retain_score - e.g. 30 score would be basically never in history
			# has the price close at this price% change accross all timeframes - thus indicating it's very, very likely to go in the opposite direction.
		# where bar1 == profit made from selling after 1h, bar2 profit made from selling after 12h, bar3 profit made after selling 1day etc.
		# so the Y axis is profit 
		pass 

	def generate_result_files(self, mode):
		self.generate_summary_csv(mode)
		self.graph_historical_data(mode)


	def generate_summary_csv(self, mode):
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

		# The server will regularly compute the current score -> compare the score with historical scores, if the score is in say the top 5%, it will notify user
		# and generate graph, which will show the likely hood of profit/gain (for 1h, 1d, 3d etc.) if you were to buy/sell now 
		# Using the bull/bear score combined with retainment score
		pass
