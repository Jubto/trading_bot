from binance.client import Client # Third party 
from binance.exceptions import BinanceAPIException # Third party 
from config import API_KEY, API_SECRET
from glob import glob
from time import time
from datetime import datetime
from collections import defaultdict
from statistics import stdev
from numpy import nan, arange
import matplotlib.pyplot as plt
import pandas as pd
import bisect
import json 
import csv
import os

'''
Semantics with examples

__Coin = INJ
__Tradingpair = USDT
__Symbol = INJUSDT
__Timeframe = 5m
__Symbol_timeframe  = INJUSDT_5m

'''

#https://python-binance.readthedocs.io/en/latest/market_data.html#id7
client = Client(API_KEY, API_SECRET) # TODO consider making this in the server, then passing it by reference as arg for coin.methods


# make different coin objects, e.g. INJ, BTC, FTM etc. 
class Coin():
	'''A class which retrieves candle stick data for a given coin avaliable on Binance, performs TA on the stored data, can return a score.'''

	INTERVALS = ['1m', '3m', '5m', '15m', '30m', '1h', '2h', '3h', '4h', '6h', '8h', '12h', '1d', '3d', '1w', '1M'] # All avaliable intervals on binance
	EARLIEST_DATE = "1 Jan, 2017" # Date binance started

	def __init__(self, coin):	
		if type(coin) != str:
			raise Exception(f"Coin objects must be initialised with a string.")

		self.coin = coin
		self.coin_path = os.path.join(os.path.dirname(os.path.realpath(__file__)) + "/coindata", coin)
		self.json_file = f"{self.coin_path}/analysis_{self.coin}.json"
		self.previous_update_UTS = None
		self.deafult_scoring_timeframes = ['1h', '4h', '12h', '1d', '3d'] # deafult set of timeframes used to compute score

		if not os.path.exists(self.coin_path):
			os.mkdir(self.coin_path)

	def get_candles(self, tradingpair, intervals = []):
		'''
		Handles the retreval of raw candle data from binance.
		If coin has no stored data (i.e. new coin for server) then this will retreve all historical data
		If coin has data stored, then this will retreve only the latest candle data. 	
		'''

		timeframes = [str(interval) for interval in intervals if str(interval) in self.INTERVALS] # Ensures all intervals provided are valid
		
		for timeframe in timeframes:
			datafile = self.csv_path(tradingpair, timeframe)
			symbol = self.coin.upper() + tradingpair.upper()
			try:
				if os.path.exists(datafile):
					with open(datafile, 'r', newline='') as csvfile: 
						final_candle = csvfile.readline().split(',')[0] # Read first line of csv to obtain most recent UTS candle time saved 
					klines = client.get_historical_klines(symbol, timeframe, int(final_candle)) # Retreve only new candles from Binance API
					self.csv_maker(datafile, 'a', klines) # Append only new candles
					self.csv_maker(datafile, 'r+', klines) # Update the latest UTS candle to the first line of .csv
					if timeframe == '1h':
						with open(datafile, 'r', newline='') as csvfile:
							self.previous_update_UTS = int(csvfile.readline().split(',')[0]) # Keeps track of the latest hour coin was updated.
				else:
					klines = client.get_historical_klines(symbol, timeframe, self.EARLIEST_DATE) # Get all candlestick data from earliest possible date from binance.
					self.csv_maker(datafile, 'w', klines)
			except BinanceAPIException:
				# If trading pair does not exist, remove all assoicated files and directories. 
				print(f"API exception, please ensure trading pair {symbol} exists.")
				if self.list_saved_filenames():
					self.remove_tradingpair(tradingpair.upper()) # Means coin symbol exists however trading pair does not exist in Binance.
				else:
					self.remove_coin() # Means coin symbol does not exist in Binance.
		if timeframes:
			self.create_json_file()


	def remove_timeframe(self, symbol_timeframe):
		'''Handles removal of timeframe for given coin'''

		datafile = f"{self.coin_path}/{symbol_timeframe}.csv"
		if os.path.exists(datafile):
			os.remove(datafile)
			print(f"{symbol_timeframe} has been removed.")
		else:
			print(f"{symbol_timeframe} is already not present in database.")
		if len(glob(self.coin_path + '/*')) == 0:
			self.remove_coin()


	def remove_tradingpair(self, symbol):
		'''Handles removal of trading pair from given coin'''

		files = self.list_saved_filenames()
		for f in files:
			if symbol == f.split('_')[0]:
				os.remove(self.coin_path + '/' + f)
		print(f"All files assoicated with {symbol} have been removed.")
		if len(glob(self.coin_path + '/*')) == 0:
			self.remove_coin()

	def remove_coin(self):
		'''Handles removing coin'''

		files = glob(self.coin_path + '/*')
		for path in files:
			os.remove(path)
		os.rmdir(self.coin_path)
		print(f"All assoicated files for {self.coin} have been removed.")


	def csv_maker(self, file_path, mode, klines): # TODO make private
		'''Creates new or appends to existing csv files for coin objects. Inserts header in the first row
		   Header row contains: Final row UTS timestamp, number of rows, pointer position at EOF.'''

		with open(file_path, mode, newline='') as csvfile: 
			final_candle = klines[-1][0]
			num_rows = len(klines) - 1 # Last row is not added
			if mode == 'w' or mode == 'r+':			
				if mode == 'w':
					csvfile.write(f"{0:0106}") # Temporary empty row for header.
				else:
					with open(file_path, 'a', newline='') as csvfile_temp:
						pointer = csvfile_temp.tell() # number of bytes to end of csv, used for skipping to end of csv
					header = csvfile.readline()
					num_rows = num_rows + int(header.split(',')[1].lstrip('0'))
					csvfile.seek(0)
					csvfile.write(f"{final_candle},{num_rows:030},{pointer:060}") # Add updated header to beginning. 
					return 1

			csv_writer = csv.writer(csvfile, delimiter=',') 
			[csv_writer.writerow(kline) for kline in klines[:-1]] # Don't add final candle row as that candle hasn't closed yet		
			if mode == 'w':
				pointer = csvfile.tell()
				csvfile.seek(0)
				csvfile.write(f"{final_candle},{num_rows:030},{pointer:060}\n") # Add header, length always stays constant. 


	def csv_path(self, tradingpair, timeframe): # TODO make private
		'''Returns absolute path of coin objects specified csv file'''

		return f"{self.coin_path}/{self.coin.upper() + tradingpair.upper()}_{timeframe}.csv"


	def list_saved_filenames(self):
		'''Returns a list of all csv files of coin object, e.g. returns [INJBTC_4h.csv, INJUSDT_4h.csv]'''

		files = glob(self.coin_path + '/' + self.coin + '*')
		return [f.split('/')[-1] for f in files if f.split('_')[-1][:2] != "5m"] # exclude 5m since this file is only intended for historical_commputation


	def create_json_object(self, *files): # TODO make private
		'''This method will return a json string containing trading pair object (key) their timeframes (keys), and % changes (key + list)'''
		
		symbol_timeframe = {}
		csv_files = self.list_saved_filenames()

		if files:
			csv_files = files

		for csvfile_name in csv_files:
			symbol = csvfile_name.split('_')[0]
			timeframe = {csvfile_name.split('_')[1].split('.')[0]:{'candle_change':[], 'candle_amplitude':[], 'candle_max_up':[], 'candle_max_down':[]}} 
			try:
				symbol_timeframe[symbol].update(timeframe)
			except KeyError:
				symbol_timeframe[symbol] = timeframe

		return json.dumps(symbol_timeframe, indent=4)


	def create_json_file(self): # TODO make private
		'''Creates and returns a json object string'''

		if os.path.exists(self.json_file):
			return None

		coin_data = json.loads(self.create_json_object())
		with open(self.json_file, 'w') as jf:
			json.dump(coin_data, jf, indent=4)

		print(f"New json file for {self.coin} has been created in: {self.json_file}")


	def update_json(self): # TODO make private
		'''Ensures stored csvfiles are synchronous with json by either adding or deleting csvfiles to/from json.'''
		
		if not os.path.exists(self.json_file):
			print(f"New json file for {self.coin} will be created.")
			self.create_json_file()
		
		with open(self.json_file, 'r') as jf:
			coin_data = json.load(jf)

		# Find difference of all tradingpairs_timeframes of json file with Coin directory csv files
		csv_files = set(self.list_saved_filenames())
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


	def add_data_to_json(self): # TODO make private
		'''Retreves candle data starting from last updated date and then updates the json'''

		with open(self.json_file, 'r') as jf:
			coin_data = json.load(jf)

		for symbol in coin_data:
			for timeframe in coin_data[symbol]:
				datafile = self.csv_path(symbol.split(self.coin)[1], timeframe)
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


	def update(self): # TODO make private
		'''Updates all csv and json files of given file object.'''
 
		# Perform this low cost update everytime update() is called. Ensures json file is synchronous with stored csvfiles. 
		need_update = False
		if self.update_json():
			need_update = True

		# More expensive update, only perform at most every hour (unless needed via need_update). This updates candle/json data.
		if need_update or self.previous_update_UTS == None or (time() - self.previous_update_UTS >= 3600):
			csv_files = self.list_saved_filenames()
			tradingpair_timeframes = {}
			for csvfile_name in csv_files:
				tradingpair = csvfile_name.split('_')[0].split(self.coin)[-1]
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
		   Bull/Bear score indicates how well the current price action performs compared to all histortical candle max/min spikes
		   change_score indicates how likely the current price will change_score based on all historical candle closes
		   Amplitude score indicates how volitile the current price action is compared to all historical candle closes
		   Optional parameter `to_monitor` which takes a list of symbol_timeframes to specifically calculate score for.'''

		self.update() # Get latest candles

		score_bull, score_bear, score_change, timefame_count, price, score_dict = 0, 0, 0, 0, 0, {}
		csv_files = self.list_saved_filenames()
		if to_monitor:
			csv_files = [csvfile_name for symbol_timeframe in to_monitor for csvfile_name in csv_files if symbol_timeframe in csvfile_name]
		with open(self.json_file, 'r') as jf:
			coin_data = json.load(jf)

		# loading in current price action
		for csvfile_name in sorted(csv_files, key= lambda i : Coin.INTERVALS.index(i.split("_")[-1].split(".")[0])):
			symbol = csvfile_name.split('_')[0]
			timeframe = csvfile_name.split('_')[1].split('.')[0]
			csvfile_name = f"{self.coin_path}/{csvfile_name}"
			with open(csvfile_name, 'r', newline='') as csvfile:
				final_candle = csvfile.readline().split(',')[0]
				klines = client.get_historical_klines(symbol, timeframe, int(final_candle))[0] # Get latest candles from Binance
				try:
					score_dict[symbol][timeframe] = self.percent_changes(float(klines[1]), float(klines[2]), float(klines[3]), float(klines[4]))
				except KeyError:
					score_dict[symbol] = {timeframe:self.percent_changes(float(klines[1]), float(klines[2]), float(klines[3]), float(klines[4]))}			
					price = klines[4]

		# compute score of current price action based on histortical data
		for symbol in score_dict:
			timefame_count += len(score_dict[symbol])
			for timeframe in score_dict[symbol]:
				current_change = score_dict[symbol][timeframe]['candle_change']
				score_dict[symbol][timeframe]['candle_change'] = str(current_change) + "%"
				amplitude_change = score_dict[symbol][timeframe]['candle_amplitude']
				if current_change > 0:
					metric = "candle_max_up"
					score_dict[symbol][timeframe]["candle_max_down"] = 'NA'
				else:
					metric = "candle_max_down"
					score_dict[symbol][timeframe]["candle_max_up"] = 'NA'
				amp_score = self.score_amplitude(
					amp_list= coin_data[symbol][timeframe]["candle_amplitude"],
					size= len(coin_data[symbol][timeframe]["candle_amplitude"]),
					amplitude_change= amplitude_change)
				score, change_score = self.score_performance(
					max_list= coin_data[symbol][timeframe][metric],
					change_list= coin_data[symbol][timeframe]["candle_change"],
					size= len(coin_data[symbol][timeframe][metric]),
					absolute_change= abs(current_change),
					current_percent_change= current_change)

				# Construct current scoring summary dict to send to server
				if amp_score > 0:
					historical_average = self.average(coin_data[symbol][timeframe]["candle_amplitude"])
					score_dict[symbol][timeframe]["candle_amplitude"] = f"Score: {amp_score} | Change: {amplitude_change}% | average: {historical_average}%"
				elif amp_score < 0:
					historical_average = self.average(coin_data[symbol][timeframe]["candle_amplitude"])
					score_dict[symbol][timeframe]["candle_amplitude"] = f"Unusually small amplitude | Change: {amplitude_change}% | average: {historical_average}%"
				else:
					score_dict[symbol][timeframe]["candle_amplitude"] = 'AVERAGE' # Means current price action is bellow the top 75% of history, i.e. not important
				
				if score:
					historical_average = self.average(coin_data[symbol][timeframe][metric])
					score_dict[symbol][timeframe][metric] = f"Score: {score} | Change score: {change_score} | Change: {current_change}% | average: {historical_average}%"
					if metric == "candle_max_up":
						score_bull += score
					else:
						score_bear += score
				else:
					score_dict[symbol][timeframe][metric] = 'AVERAGE'
				score_change += change_score

		return [self.coin, score_bull, score_bear, score_change, timefame_count, price, score_dict, "coin_score"] # final index represents type of information

	
	def compute_historical_score(self, symbol, custom_timeframes = [], custom_filename = ""):
		'''Calculates bull/bear/change_scorement score for all 5 minute intervals of the coins history.
		Each 5 minutes simulates running the current score method back in time, with information known only back during the 5minute interval
		Bull/Bear score indicates how well the current price action performs compared to all histortical candle data
		Retain_score indicates how likely the current price will change_score based on historical data
		If prior historical analysis is present, only the latest data will be computed and appended.'''

		self.update() # Get latest candles from Binance
		self.get_candles(symbol.split(self.coin)[-1], intervals=["5m"]) # update latest 5min data - this may take time due to Binance
		if custom_timeframes:
			symbol_timeframes = sorted([symbol + '_' + timeframe for timeframe in custom_timeframes], key= lambda i : Coin.INTERVALS.index(i.split("_")[-1]))
		else:
			symbol_timeframes = [symbol + '_' + timeframe for timeframe in self.deafult_scoring_timeframes]
		
		# make dataframe to hold all historical 5min intervals (i.e. real time price action from the past). Scores will be inserted at the end
		csv_filepath = f"{self.coin_path}/{symbol}_5m.csv"
		historical_rt_price_DF = pd.read_csv(csv_filepath, usecols=[0, 4], names=["UTS", "price"], header=None, skiprows=1) # store all 5m intervals
		bull_scores, bear_scores, change_scores = [], [], []
		score_tracker = {}
		for symbol_timeframe in symbol_timeframes:
			score_tracker[symbol_timeframe + "_BEAR"] = []
			score_tracker[symbol_timeframe + "_BULL"] = []
			

		# make symbol_timeframes_DF which has columns for UTS-date, open, high, low, close, of all symbol_timeframes
		symbol_timeframes_DF = pd.DataFrame()
		historical_percent_changes = {} # used to act like a dynamically growing analysis_coin.json
		for symbol_timeframe in symbol_timeframes:
			csv_filepath = f"{self.coin_path}/{symbol_timeframe}.csv"
			columns = [symbol_timeframe + "-UTS", symbol_timeframe + "-open", symbol_timeframe + "-high", symbol_timeframe + "-low", symbol_timeframe + "-close"]
			temp_DF = pd.read_csv(csv_filepath, usecols=[0, 1, 2, 3, 4], names=columns, header=None, skiprows=1)
			historical_percent_changes[symbol_timeframe] = {'candle_change':[], 'candle_max_up':[], 'candle_max_down':[]}
			symbol_timeframes_DF = symbol_timeframes_DF.merge(right=temp_DF, how="outer", left_index=True, right_index=True)

		# Load from previous data and skip until new data, else perform initilisation if no prior historical analysis found (skipping first 3 days due to messness)
		df_positiontracker = {} # To complement the symbol_timeframes_DF dataframe
		if os.path.exists(f"{self.coin_path}/historical/{symbol}_historical_scoring{custom_filename}.csv"):
			with open(f"{self.coin_path}/historical/{symbol}_historical_analysis{custom_filename}.json", 'r') as jf:
				historical_percent_changes = json.load(jf) 
			skip_UTS = pd.read_csv(f"{self.coin_path}/historical/{symbol}_historical_scoring{custom_filename}.csv").iloc[-1][0] # skip to where the last historical analysis ends
			for symbol_timeframe in symbol_timeframes:
				end_index = symbol_timeframes_DF[symbol_timeframes_DF[symbol_timeframe + '-UTS'].notnull()].shape[0] # get 1 past final index position for symbol_timeframe
				columns = [symbol_timeframe + "-UTS", symbol_timeframe + "-open", symbol_timeframe + "-high", symbol_timeframe + "-low", symbol_timeframe + "-close"]
				if symbol_timeframes_DF.index[symbol_timeframes_DF[symbol_timeframe + '-UTS'] >= skip_UTS].any():
					index = symbol_timeframes_DF.index[symbol_timeframes_DF[symbol_timeframe + '-UTS'] >= skip_UTS][0] - 1 # get index just before skip
					df_positiontracker[symbol_timeframe] = {
						"index":index,
						"end_index":end_index,
						"open_price":symbol_timeframes_DF.loc[index, [symbol_timeframe + "-open"]][0],
						"next_UTS": symbol_timeframes_DF.loc[index + 1, [symbol_timeframe + "-UTS"]][0],
						"columns": columns}		
				else: # no new symbol_timeframe candles added since last calculation, hence skip till end
					df_positiontracker[symbol_timeframe] = {
						"index":end_index - 1,
						"end_index":end_index,
						"open_price":symbol_timeframes_DF.loc[end_index - 1, [symbol_timeframe + "-open"]][0],
						"next_UTS": symbol_timeframes_DF.loc[end_index - 1, [symbol_timeframe + "-UTS"]][0],
						"columns": columns}		
		else:
			# initialise dataframe and json for the first 3 -> 21 days of price action 
			if not os.path.exists(self.coin_path + '/historical'):
				os.mkdir(self.coin_path + '/historical')
			first_3day_UTS = int(symbol_timeframes_DF.loc[3, [symbol + '_1d-UTS']]) # The first few days of price action are unreliable due to volitility in general
			skip_UTS = int(symbol_timeframes_DF.loc[21, [symbol + '_1d-UTS']]) # UTS date for 21 days of price action
			for symbol_timeframe in symbol_timeframes:
				columns = [symbol_timeframe + "-UTS", symbol_timeframe + "-open", symbol_timeframe + "-high", symbol_timeframe + "-low", symbol_timeframe + "-close"]
				percent_changes_list = [self.percent_changes(row[1],row[2],row[3],row[4]) for row in symbol_timeframes_DF[columns].to_numpy() if row[0] > first_3day_UTS and row[0] <= skip_UTS]
				first_3day_skip = symbol_timeframes_DF.index[symbol_timeframes_DF[symbol_timeframe + '-UTS'] >= first_3day_UTS][0]
				index = len(percent_changes_list) + first_3day_skip  # location of three week UTS index position in dataframe for each timeframe 
				df_positiontracker[symbol_timeframe] = {
					"index":index,
					"end_index":symbol_timeframes_DF[symbol_timeframes_DF[symbol_timeframe + '-UTS'].notnull()].shape[0],
					"open_price":symbol_timeframes_DF.loc[index, [columns[1]]][0],
					"next_UTS": symbol_timeframes_DF.loc[index + 1, [columns[0]]][0],
					"columns": columns}
				for metric in historical_percent_changes[symbol_timeframe]:
					historical_percent_changes[symbol_timeframe][metric] = [row[metric] for row in percent_changes_list]
					historical_percent_changes[symbol_timeframe][metric].sort()
		historical_rt_price_DF = historical_rt_price_DF.loc[historical_rt_price_DF.UTS > skip_UTS].reset_index().drop("index", axis=1) # skip until lastest calculation

		# Score every 5 minute interval of given coin with information known only during that time - (100 days of price action < 3 seconds)
		for row in historical_rt_price_DF.itertuples(name=None): 
			current_UTS, price, total_bull, total_bear, total_change_score = row[1], row[2], 0, 0, 0
			for symbol_timeframe in symbol_timeframes:
				if current_UTS >= df_positiontracker[symbol_timeframe]["next_UTS"]:
					index = df_positiontracker[symbol_timeframe]["index"] # get current index
					end_index = df_positiontracker[symbol_timeframe]["end_index"] # get 1 past final index
					if index + 1 == end_index:
						df_positiontracker[symbol_timeframe]["next_UTS"] = float('inf') # Reached the end for this timeframe
					else:
						index += 1
						if index + 1 == end_index:
							next_index, i = index, 0 # second last index for given timeframe
						else:
							next_index, i = index + 1, 1
							
						# update symbol_timeframe position in dataframe
						new_row = symbol_timeframes_DF.loc[index:next_index, df_positiontracker[symbol_timeframe]["columns"]].values		
						df_positiontracker[symbol_timeframe]["index"] = index
						df_positiontracker[symbol_timeframe]["open_price"] = new_row[0][1]
						df_positiontracker[symbol_timeframe]["next_UTS"] = new_row[i][0]
						
						# update dynamically growing performance ranking json 
						percent_changes = self.percent_changes(new_row[0][1], new_row[0][2], new_row[0][3], new_row[0][4])
						for metric in historical_percent_changes[symbol_timeframe]:
							bisect.insort(historical_percent_changes[symbol_timeframe][metric], percent_changes[metric]) # insert value into sorted list
				
				# calculate score
				current_percent_change = (price / df_positiontracker[symbol_timeframe]["open_price"])*100 - 100 # %change for given candle
				if current_percent_change > 0:
					metric = "candle_max_up"
				else:
					metric = "candle_max_down"
				score, change_score = self.score_performance(
					max_list= historical_percent_changes[symbol_timeframe][metric], 
					change_list= historical_percent_changes[symbol_timeframe]["candle_change"],
					size= len(historical_percent_changes[symbol_timeframe][metric]), 
					absolute_change= abs(current_percent_change), 
					current_percent_change= current_percent_change)	
				if metric == "candle_max_up":
					total_bull += score
					score_tracker[symbol_timeframe + "_BULL"].append(score)
					score_tracker[symbol_timeframe + "_BEAR"].append(0)
				else:
					total_bear += score
					score_tracker[symbol_timeframe + "_BEAR"].append(score)
					score_tracker[symbol_timeframe + "_BULL"].append(0)
				total_change_score += change_score

			bull_scores.append(total_bull)
			bear_scores.append(total_bear)
			change_scores.append(total_change_score)

		if os.path.exists(f"{self.coin_path}/historical/{symbol}_historical_scoring{custom_filename}.csv"):
			columns = ["bull_scores", "bear_scores", "change_scores", *[timeframe for timeframe in score_tracker]]
			column_data = [bull_scores, bear_scores, change_scores, *[score_tracker[timeframe] for timeframe in score_tracker]]
			newdata_DF = pd.DataFrame({column:data for column, data in zip(columns, column_data)})
			newdata_DF = historical_rt_price_DF.merge(right=newdata_DF, how="outer", left_index=True, right_index=True)
			newdata_DF.to_csv(f"{self.coin_path}/historical/{symbol}_historical_scoring{custom_filename}.csv", mode='a', header=False, index=False)
		else:
			historical_rt_price_DF.insert(2, "bull_scores", bull_scores)
			historical_rt_price_DF.insert(3, "bear_scores", bear_scores)
			historical_rt_price_DF.insert(4, "change_scores", change_scores)
			[historical_rt_price_DF.insert(5, timeframe, score_tracker[timeframe]) for timeframe in score_tracker]
			historical_rt_price_DF.to_csv(f"{self.coin_path}/historical/{symbol}_historical_scoring{custom_filename}.csv", index=False)
		
		with open(f"{self.coin_path}/historical/{symbol}_historical_analysis{custom_filename}.json", 'w') as jf:
			json.dump(historical_percent_changes, jf, indent=4) 


	def look_ahead_gains(self, symbol, custom_timeframes = [], peak_start_only = False, custom_filename = "", custom_csv_filename = ""):
		'''Searches through specificed historical_scoring csv to find bull/bear score peaks over a certain thresold.
		Once found, it calculates the % difference of if you sold/bought after 30min, 1h, 4h, 1d, 3d, 1w, 2w.
		Saves the data in 'look_ahead_gains.csv'
		'''

		# self.compute_historical_score(symbol, custom_timeframes, custom_filename)
		threshold_score = int(0.5 * (len(custom_timeframes) * 6)) if custom_timeframes else int(0.5 * (len(self.deafult_scoring_timeframes) * 6)) #TODO make 0?
		historical_score_csv = f"{self.coin_path}/historical/{symbol}_historical_scoring{custom_csv_filename}.csv"
		look_ahead_gains_csv = f"{self.coin_path}/historical/{symbol}_look_ahead_gains{custom_filename}.csv"
		historical_scoring_DF = pd.read_csv(historical_score_csv, usecols=[0, 1, 2, 3, 4], index_col= 0, header=None, skiprows=1)

		with open(look_ahead_gains_csv, 'a') as outfile, open(look_ahead_gains_csv, 'r') as infile:
			retain_csv_writer = csv.writer(outfile)
			skip_UTS = historical_scoring_DF.index[0]
			if (outfile.tell() == 0):
				retain_csv_writer.writerow(["UTC", "price", "peak_start", "peak_top", "change_score", "goal",
											"%diff_30min", "%diff_1h", "%diff_4h", "%diff_1d", "%diff_3d", "%diff_1w", "%diff_2w", "UTS"])
			else:
				infile.seek(outfile.tell() - 15) # skip to end of file, capture last UTS
				skip_UTS = infile.readline()

			peak_start = 0
			peak = 0
			peak_row = ()
			look_ahead = 12 # 12 iteration, where each iteration is 5min, so 1 hour look ahead
			best_prices = {6:0, 12:0, 48:0, 144:0, 288:0, 864:0, 2016:0, 4032:0} # key: look ahead time in 5min intervals, value: percentage diff

			for row in historical_scoring_DF.loc[skip_UTS:].itertuples(name=None):
				score = int((max(row[2:4])))
				if peak_start:
					if not peak_start_only and score > peak: # and not peakstart only
						peak, peak_row = score, row
						look_ahead = 12
					else:
						look_ahead -= 1
						if not look_ahead or (peak_start_only and peak_start > score): # or peakstart only
							best_price = float(peak_row[1])
							goal = "buy_back" if peak_row[2] > peak_row[3] else "sell_later"
							for row_look_ahead in historical_scoring_DF.loc[peak_row[0]:(peak_row[0] + 300000*4032)].itertuples(name=None):
								look_ahead += 1
								look_ahead_price = float(row_look_ahead[1])
								
								if (goal == "buy_back"): # where score was bull/max, hence you want to look ahead for lower prices, since you ideally sold
									if look_ahead_price < best_price:
										best_price = look_ahead_price
								else:
									if look_ahead_price > best_price:
										best_price = look_ahead_price

								if look_ahead in best_prices:
									best_prices[look_ahead] = int((best_price / peak_row[1]) * 100)
									best_price = look_ahead_price
							utc_time = datetime.utcfromtimestamp(int(str(peak_row[0])[:-3])).strftime('|%d-%m-%Y %H:%M:%S|')
							retain_csv_writer.writerow([utc_time, peak_row[1], peak_start, peak, peak_row[-1], goal, *[diff for diff in best_prices.values()], peak_row[0]])
							look_ahead = 12
							peak_start, peak = 0, 0
		
				elif score >= threshold_score:
					peak_start, peak, peak_row = score, score, row
					if peak_start_only:
						look_ahead = 0


	def retain_score(self, symbol, custom_filename = ""):
		'''Creates a score file summarising the data in look_ahead_gains.csv for given symbol
		'''

		retain_score_csv = f"{self.coin_path}/historical/{symbol}_retain_scoring{custom_filename}.csv"
		look_ahead_gains_csv = f"{self.coin_path}/historical/{symbol}_look_ahead_gains{custom_filename}.csv"
		if not os.path.exists(look_ahead_gains_csv):
			return f"No look_ahead_gains.csv {look_ahead_gains_csv} exists, please first run the Coin.look_ahead_gains method."

		bullscore_bestgain = defaultdict(list) # key = score, value = list of best %gains
		bearscore_bestgain = defaultdict(list)
		average_bestgain = {"buy_back":{"30m":[], "1h":[], "4h":[], "1d":[], "3d":[], "1w":[], "2w":[]},
							"sell_later":{"30m":[], "1h":[], "4h":[], "1d":[], "3d":[], "1w":[], "2w":[]}}

		with open(look_ahead_gains_csv, 'r') as infile, open(retain_score_csv, 'w') as outfile:
			lookahead_csv_reader = csv.reader(infile)
			
			next(lookahead_csv_reader)
			for row in lookahead_csv_reader:
				index = 6
				if row[5] == "buy_back":
					bullscore_bestgain[int(row[3])].append(min([int(i) for i in row[6:-1]]))
					for look_ahead in average_bestgain["buy_back"]:
						average_bestgain["buy_back"][look_ahead].append(int(row[index]))
						index += 1
				else:
					bearscore_bestgain[int(row[3])].append(max([int(i) for i in row[6:-1]]))
					for look_ahead in average_bestgain["sell_later"]:
						average_bestgain["sell_later"][look_ahead].append(int(row[index]))
						index += 1

			outfile.write("Bull scores:\n" + "="*130 + "\n%reduction of coin price if you were to have sold at this score peak (hence you want to buy back)\n")
			for score in sorted(bullscore_bestgain.keys()):
				outfile.write(f"{score}: Average = {self.average(bullscore_bestgain[score], 2):.2f}%, {bullscore_bestgain[score]}\n")
			outfile.write("\nBest average time to buy back:\n")
			for look_ahead in average_bestgain["buy_back"]:
				outfile.write(f"{look_ahead}: Average = {self.average(average_bestgain['buy_back'][look_ahead], 2):.2f}%\n")
			outfile.write("="*130)

			outfile.write("\n\nBear scores:\n" + "="*130 + "\n%increases of coin price if you were to have bought at this score peak (hence you want to sell later)\n")
			for score in sorted(bearscore_bestgain.keys()):
				outfile.write(f"{score}: Average = {self.average(bearscore_bestgain[score], 2):.2f}%, {bearscore_bestgain[score]}\n")
			outfile.write("\nBest average time to sell later:\n")
			for look_ahead in average_bestgain["sell_later"]:
				outfile.write(f"{look_ahead}: Average = {self.average(average_bestgain['sell_later'][look_ahead], 2):.2f}%\n")
			outfile.write("="*130)


	def graph_historical_data(self, symbol, graph_type="bar", custom_filename = ""):
		'''Generates either a bar graph or line graph summarising the potential gains from buying/selling at the given score peaks.'''

		look_ahead_gains_csv = f"{self.coin_path}/historical/{symbol}_look_ahead_gains{custom_filename}.csv"
		if not os.path.exists(look_ahead_gains_csv):
			return f"No look_ahead_gains.csv {look_ahead_gains_csv} exists, please first run the Coin.look_ahead_gains method."

		make_dict = lambda : {"30m":[], "1h":[], "4h":[], "1d":[], "3d":[], "1w":[], "2w":[]}
		best_gains = {"buy_back":defaultdict(make_dict), "sell_later":defaultdict(make_dict)}

		with open(look_ahead_gains_csv, 'r') as infile:
			lookahead_csv_reader = csv.reader(infile)		
			next(lookahead_csv_reader)
			for row in lookahead_csv_reader:
				index = 6
				if row[5] == "buy_back":
					for look_ahead in best_gains["buy_back"][int(row[3])]:
						best_gains["buy_back"][int(row[3])][look_ahead].append(int(row[index]))
						index += 1
				else:
					for look_ahead in best_gains["sell_later"][int(row[3])]:
						best_gains["sell_later"][int(row[3])][look_ahead].append(int(row[index]))
						index += 1

		fig, (ax_bull, ax_bear) = plt.subplots(nrows= 2, ncols= 1, figsize=(20, 16))
		plt.subplots_adjust(left=0.05, bottom=0.05, right=0.9, top=0.95, wspace=0.4, hspace=0.35)
		color_dict = {"30m":"indianred", "1h":"chocolate", "4h":"orange", "1d":"yellowgreen", "3d":"forestgreen", "1w":"mediumspringgreen", "2w":"mediumturquoise"}	
		scores = arange(15, 31)
		width = 0.11
		pos = -3

		for look_ahead, color in color_dict.items():
			averages = [self.average(best_gains["buy_back"][score][look_ahead]) for score in range(15, 31)]
			stdevs = [stdev(best_gains["buy_back"][score][look_ahead]) if len(best_gains["buy_back"][score][look_ahead]) > 1 else 0 for score in range(15, 31)]
			if graph_type == "bar":
				ax_bull.bar(scores + width*pos, averages, width, yerr= stdevs, label=look_ahead, color= color, edgecolor= "black")
			else:
				ax_bull.errorbar(scores, averages, yerr= stdevs, label=look_ahead)

			averages = [self.average(best_gains["sell_later"][score][look_ahead]) for score in range(15, 31)]
			stdevs = [stdev(best_gains["sell_later"][score][look_ahead]) if len(best_gains["sell_later"][score][look_ahead]) > 1 else 0 for score in range(15, 31)]
			if graph_type == "bar":
				ax_bear.bar(scores + width*pos, averages, width, yerr= stdevs, label=look_ahead, color= color, edgecolor= "black")
			else:
				ax_bear.errorbar(scores, averages, yerr= stdevs, label=look_ahead)
			pos += 1

		ax_bull.axhline(y=100, color="black", ls="--")
		ax_bull.set_ylabel(f"{self.coin} % gain after selling score peak", fontweight="demi", size="xx-large")
		ax_bull.set_xlabel("Bull Score", fontweight="demi", size="x-large")
		ax_bull.set_title("Buy-back graph", fontweight="demi", size="xx-large", y=1.025)
		ax_bull.legend(title="Post\nbuy/sell", title_fontsize="xx-large", loc='upper right', fontsize='xx-large', shadow=True, fancybox=True, bbox_to_anchor=(1.116, 0.125))

		ax_bear.axhline(y=100, color="black", ls="--")
		ax_bear.set_ylabel(f"{symbol.split(self.coin)[-1]} % gain after buying score peak", fontweight="demi", size="xx-large")
		ax_bear.set_xlabel("Bear Score", fontweight="demi", size="x-large")
		ax_bear.set_title("Sell-later graph", fontweight="demi", size="xx-large", y=1.025)

		plt.savefig(f"{self.coin_path}/historical/{symbol}_scoring_graph{custom_filename}.png")

	
	@staticmethod
	def score_performance(max_list, change_list, size, absolute_change, current_percent_change):
		'''Scoring method. Determines what rank the current price action holds against historical data
		If the performance is greater than the top 75% of price action history, then it can obtain some score.
		Once the price action is strong enough to generate a score, it then can also generate a change_score.
		To even have a change_score of 1, the price action has to be within the top 90% of %change in history.
		Hence, any change score is impressive, and indication that price is very unlikely to maintain this current candle.'''

		score, change_score = 0, 0
		if absolute_change >= max_list[int(size * 0.75)]:
			if absolute_change <= max_list[int(size * 0.8)]:
				score = 1
			elif absolute_change <= max_list[int(size * 0.85)]:
				score = 2
			elif absolute_change <= max_list[int(size * 0.9)]:
				score = 3
			elif absolute_change <= max_list[int(size * 0.95)]:
				score = 4
			elif absolute_change <= max_list[int(size * 0.985)]:
				score = 5
			else:
				score = 6
			if current_percent_change > 0 and current_percent_change >= change_list[int(size * 0.9)]:
				if current_percent_change <= change_list[int(size * 0.925)]:
					change_score = 1
				elif current_percent_change <= change_list[int(size * 0.95)]:
					change_score = 2
				elif current_percent_change <= change_list[int(size * 0.97)]:
					change_score = 3
				elif current_percent_change <= change_list[int(size * 0.98)]:
					change_score = 4
				elif current_percent_change <= change_list[int(size * 0.99)]:
					change_score = 5
				else:
					change_score = 6
			elif current_percent_change < 0 and current_percent_change <= change_list[int(size * 0.1)]:
				if current_percent_change >= change_list[int(size * 0.075)]:
					change_score = 1				
				elif current_percent_change >= change_list[int(size * 0.05)]:
					change_score = 2
				elif current_percent_change >= change_list[int(size * 0.03)]:
					change_score = 3
				elif current_percent_change >= change_list[int(size * 0.02)]:
					change_score = 4
				elif current_percent_change >= change_list[int(size * 0.01)]:
					change_score = 5
				else:
					change_score = 6
		return score, change_score


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
		elif amplitude_change <= amp_list[int(size * 0.05)]:
			return -1
		return 0


	@staticmethod
	def percent_changes(candle_open, candle_high, candle_low, candle_close):
		'''Returns % change, % amplitude, max % up, max % down of a given candle'''

		return {'candle_change':round((candle_close / candle_open)*100 - 100, 1),
				'candle_amplitude':round((candle_high / candle_low)*100 - 100, 1),
				'candle_max_up':round((candle_high / candle_open)*100 - 100, 1),
				'candle_max_down':round(abs((candle_low / candle_open)*100 - 100), 1)}


	@staticmethod
	def average(nums, precision=1):
		if len(nums) == 0:
			return nan
		elif len(nums) == 1:
			return nums[0]
		total = 0
		for num in nums:
			total += num
		return round((total) / len(nums), precision)


	def generate_all_result_files(self, mode):
		self.graph_historical_data(mode)
		# current score
		# retain scorer


	def sell_assest(self):
		'''Use only during emergency, sells asset on binance'''


# coin = Coin('INJ')
# coin.compute_historical_score('INJUSDT')
# coin.look_ahead_gains("INJUSDT", peak_start_only=True, custom_filename="peak_start_only")
# coin.retain_score("INJUSDT")
# coin.graph_historical_data("INJUSDT", custom_filename="peak_start_only")
# coin.look_ahead_gains("INJUSDT")
# coin.graph_historical_data("INJUSDT")