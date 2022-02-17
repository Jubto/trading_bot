from binance.exceptions import BinanceAPIException # Third party 
from config import client
from enums import INTERVALS, EARLIEST_DATE, BEAR_MARKETS, BULL_MARKETS, STANDARD_TRADING_PAIRS, DEFAULT_SCORING_TIMEFRAMES
from utility import filter_market_periods, get_filename_extension
from glob import glob
from time import time
from datetime import datetime
from collections import defaultdict
from statistics import stdev
from numpy import nan, arange
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
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

class Coin():
    '''
    Retrieves, stores and analyses historical candlestick data from Binance API.
    Primary function is to generate a signal (buy or sell) based on current price action.

    This signal is generated based on a simple custom made scoring system. Proper technical analysis was not used to
    generate the signal due to lacking expertise in that area. The class will look at historical data and perform trading
    simulations to determine optimal score thresholds to use for generating signals. Users can simply make a new coin
    object and then let the object start generating signals.

    This class also generates three different graphs:
        - The average gains made after 30m, 1h, 4h, 1d, 3d, 1w from signal.
        - The simulated trading performance of the top x threshold settings when blindly following the signals.
        - The latest candlestick data plotted with the signals superimposed.
    
    Future plans will be for this class to send signals to a trading bot to perform the actions.
    '''

    def __init__(self, coin):	

        self.coin = coin.upper()
        self.holdings = None
        self.coin_path = os.path.dirname(os.path.realpath(__file__)) + f"/coindata/{self.coin}"
        self.candlestick_path = f'{self.coin_path}/candlestick_data'
        self.historical_scoring_path = f'{self.coin_path}/historical_scorings'
        self.look_ahead_path = f'{self.coin_path}/look_aheads'
        self.retain_scoring_path = f'{self.coin_path}/retain_scorings'
        self.trading_simulation_path = f'{self.coin_path}/trading_simulations'
        self.graph_path = f'{self.coin_path}/graphs'
        self.json_file = f"{self.coin_path}/analysis_{self.coin}.json"
        self.previous_update_UTS = None
        self.previous_updated_simulations = []
        self.deafult_scoring_timeframes = DEFAULT_SCORING_TIMEFRAMES # deafult set of timeframes used to compute score
        if not os.path.exists(self.coin_path):
            os.mkdir(self.coin_path)
            os.mkdir(self.candlestick_path)
            os.mkdir(self.historical_scoring_path)
            os.mkdir(self.look_ahead_path)
            os.mkdir(self.retain_scoring_path)
            os.mkdir(self.trading_simulation_path)
            os.mkdir(self.graph_path)
            os.mkdir(f'{self.graph_path}/look_aheads')
            os.mkdir(f'{self.graph_path}/trading_simulations')
            os.mkdir(f'{self.graph_path}/price_action_overlays')           


    def get_candles(self, tradingpair, timeframes):
        '''
        Handles the retreval of raw candle data from binance.
        If coin has no stored data (i.e. new coin for server) then this will retreve all historical data
        If coin has data stored, then this will retreve only the latest candle data. 	
        '''
        print(f'get_candle COIN: {self.coin} got: {tradingpair} | {timeframes}')
        return
        symbol = self.coin.upper() + tradingpair.upper()
        for timeframe in timeframes:
            candlestick_path = self.get_candlestick_path(symbol, timeframe)
            try:
                if os.path.exists(candlestick_path):
                    latest_candle = self.get_latest_stored_uts(candlestick_path)
                    klines = client.get_historical_klines(symbol, timeframe, latest_candle) # Retreve only new candles from Binance API
                    self.candlestick_data_file_marker(candlestick_path, 'r+', klines) # Append only new candles
                else:
                    klines = client.get_historical_klines(symbol, timeframe, EARLIEST_DATE) # Get all candlesticks from earliest possible date from binance.
                    self.candlestick_data_file_marker(candlestick_path, 'w', klines)
                if timeframe == '1h':
                    self.previous_update_UTS = self.get_latest_stored_uts(candlestick_path) # Keeps track of the latest hour coin was updated.
            except BinanceAPIException:
                try:
                    standard_symbol = self.coin + 'USDT'
                    client.get_historical_klines(standard_symbol, timeframe, "1 Jan, 2022")
                    print(f"Binance API exception, the coin {self.coin} does not have a trading pair {tradingpair.upper()}.")
                except BinanceAPIException:
                    print(f"Binance API exception, the coin {self.coin} is not listed on Binance.")
                    self.remove_coin() # remove all trace of invalid coin from db
                return 0
        return 1


    def candlestick_data_file_marker(self, file_path, mode, klines): # TODO make private
        '''
        Creates or updates data storage for all historical candlestick data for coin.
        '''

        with open(file_path, mode, newline='') as f:
            csv_writer = csv.writer(f, delimiter=',')
            columns = [
                    'open_uts',
                    'open',
                    'high',
                    'low',
                    'close',
                    'volumne',
                    'close_time',
                    'asset_vol',
                    'num_trades',
                    'base_buyer_vol',
                    'quote_buyer_vol',
                    f'{0:030}'
                ]
            if mode == 'w':
                num_new_closed_rows = len(klines[:-1]) # don't count latest kline since that hasn't yet closed
                columns[-1] = f'{num_new_closed_rows:030}'
                csv_writer.writerow(columns)
                [csv_writer.writerow(kline) for kline in klines]
            else:
                num_new_closed_rows = int(f.readline().split(',')[-1].lstrip('0')) + len(klines[:-1])
                columns[-1] = f'{num_new_closed_rows:030}'
                f.seek(0)
                csv_writer.writerow(columns)
                f.seek(0, os.SEEK_END)
                self.modify_candlestick_data_file(csv_writer, f, klines[0])
                [csv_writer.writerow(kline) for kline in klines[1:]]


    def modify_candlestick_data_file(self, csv_writer, file_obj, kline):
        '''
        Modifies the final row of given candlestick csv file in-place
        '''

        latest_kline_string = ','.join([str(col) if type(col) == int else col for col in kline])
        latest_kline_string_byte_size = len(latest_kline_string.encode('utf-8'))
        file_obj.seek(0, os.SEEK_END)
        eof = file_obj.tell()
        file_obj.seek(eof - 500) # jump close to eof
        final_stored_row = file_obj.readlines()[-1] # grab the final row
        final_stored_row_byte_size = len(final_stored_row.encode('utf-8'))
        alignment = 0 if '\r' in final_stored_row else 1 # windows may have \r in row string
        file_obj.seek(eof - final_stored_row_byte_size - alignment) # seek to precisely start of last row
        if latest_kline_string_byte_size >= final_stored_row_byte_size:
            csv_writer.writerow(latest_kline_string.split(','))
        else:
            buffer_size = final_stored_row.split(',')[-1][1:].count('0')
            overflow = final_stored_row_byte_size - latest_kline_string_byte_size
            overflow -= 1 if alignment else 2 # \n or \r\n
            if buffer_size < overflow:
                addition = overflow
            else:
                addition = buffer_size
            latest_kline_string += '0' * addition
            csv_writer.writerow(latest_kline_string.split(','))
                

    def get_latest_stored_uts(self, candle_csv_path):
        '''
        returns the latest uts for given candlestick csv file
        '''

        with open(candle_csv_path, 'r') as f:
            f.seek(0, os.SEEK_END)
            eof = f.tell()
            f.seek(eof - 500) # get final row
            return int(f.readlines()[-1].split(',')[0])


    def get_symbol_timeframes(self, as_list=False):
        '''
        Returns all symbol timeframes stored for given coin, as_list: [INJBTC_4h, INJUSDT_4h, ...], as_dict: {BTCUSDT:[1h, 4h,...],}
        '''

        stored_symbols = [f.split('/')[-1] for f in glob(f'{self.candlestick_path}/*')]
        symbol_timeframes_list = []
        symbol_timeframes_dict = {}
        for symbol in stored_symbols:
            stored_timeframes = [f.split('/')[-1].split('_')[-1].split('.')[0] for f in glob(f'{self.candlestick_path}/{symbol}/*')]
            stored_timeframes.sort(key=lambda tf : INTERVALS.index(tf))
            symbol_timeframes_dict[symbol] = stored_timeframes
            symbol_timeframes_list.extend([f'{symbol}_{tf}' for tf in stored_timeframes])

        return symbol_timeframes_list if as_list else symbol_timeframes_dict


    def remove_timeframe(self, symbol_timeframe):
        '''
        Handles removal of specific candlestick csv file from database
        '''

        symbol, timeframe = symbol_timeframe.split('_')
        datafile = self.get_candlestick_path(symbol, timeframe)
        if os.path.exists(datafile):
            os.remove(datafile)


    def remove_symbol(self, symbol):
        '''
        Handles removal of all files of a given symbol from database
        '''

        stored_symbol_timeframes = self.get_symbol_timeframes()
        if symbol not in stored_symbol_timeframes:
            return 1
       
        for base_path in glob(f'{self.coin_path}/*'):
            for symbol_path in glob(f'{base_path}/{symbol}/*'):
                os.remove(symbol_path)
            if base_path == self.graph_path:
                for graph_path in glob(f'{self.graph_path}/*'):
                    for symbol_path in glob(f'{graph_path}/{symbol}/*'):
                        os.remove(symbol_path)
                os.rmdir(f'{self.graph_path}/{symbol}')
            else:
                os.rmdir(f'{base_path}/{symbol}')
        if not self.get_symbol_timeframes():
            self.remove_coin() # When no more symbols remaining, remove coin folder
        return 0


    def remove_coin(self):
        '''
        Handles removal of all files of a given coin from database
        '''

        stored_symbol_timeframes = self.get_symbol_timeframes()
        for symbol in stored_symbol_timeframes:
            self.remove_symbol(symbol)
        os.rmdir(self.coin_path)


    def create_tradingpair_folders(self, symbol):
        '''
        Creates all symbol folders for given coin
        '''

        os.mkdir(f'{self.candlestick_path}/{symbol}')
        open(f'{self.candlestick_path}/{symbol}/{symbol}_analysis.json', 'w').close()
        os.mkdir(f'{self.historical_scoring_path}/{symbol}')
        os.mkdir(f'{self.look_ahead_path}/{symbol}')
        os.mkdir(f'{self.retain_scoring_path}/{symbol}')
        os.mkdir(f'{self.trading_simulation_path}/{symbol}')
        os.mkdir(f'{self.graph_path}/look_aheads/{symbol}')
        os.mkdir(f'{self.graph_path}/trading_simulations/{symbol}')
        os.mkdir(f'{self.graph_path}/price_action_overlays/{symbol}')


    def get_candlestick_path(self, symbol, timeframe): # TODO make private
        '''
        Returns absolute path of candlestick csv file for given symbol and timeframe
        '''

        if not os.path.exists(f'{self.candlestick_path}/{symbol}'):
            self.create_tradingpair_folders(symbol)
        return f"{self.candlestick_path}/{symbol}/{symbol}_{timeframe}.csv" 


    def synchronize_score_jsons(self): # TODO make private
        '''
        Ensures stored csvfiles are synchronous with json by either adding or deleting csvfiles to/from json.
        '''
        
        stored_symbol_timeframes = self.get_symbol_timeframes()
        for symbol in stored_symbol_timeframes:
            with open(f'{self.candlestick_path}/{symbol}/{symbol}_analysis.json', 'r') as jf:
                scoring_json = json.load(jf)
                stored_json_timeframes = set(scoring_json.keys())
                stored_csv_timeframes = set(stored_symbol_timeframes[symbol])
                new_timeframes = stored_csv_timeframes.difference(stored_json_timeframes)
                outdated_timeframes = stored_json_timeframes.difference(stored_csv_timeframes)

                for new_timeframe in new_timeframes:
                    scoring_json[new_timeframe] = {
                        'candle_change':[],
                        'candle_amplitude':[],
                        'candle_max_up':[],
                        'candle_max_down':[]
                    }
                for outdated_timeframe in outdated_timeframes:
                    scoring_json.pop(outdated_timeframe)

            if new_timeframes or outdated_timeframes:
                with open(f'{self.candlestick_path}/{symbol}/{symbol}_analysis.json', 'w') as jf:
                    json.dump(scoring_json, jf, indent=4)
                return 1 # update performed
            return 0 # no update performed


    def update_score_jsons(self): # TODO make private
        '''
        Retreves candle data starting from last updated date and then updates the json
        '''

        stored_symbol_timeframes = self.get_symbol_timeframes()
        for symbol in stored_symbol_timeframes:
            with open(f'{self.candlestick_path}/{symbol}/{symbol}_analysis.json', 'r') as jf:
                scoring_json = json.load(jf)
            for timeframe in stored_symbol_timeframes[symbol]:
                with open(self.get_candlestick_path(symbol, timeframe)) as f:
                    csv_reader = csv.reader(f)
                    header = csv_reader.__next__()
                    csv_data_len = int(header[-1].lstrip('0'))
                    json_data_len = len(scoring_json[timeframe]['candle_change'])
                    if csv_data_len < json_data_len:
                        skip = json_data_len # Skip rows of csvfile until new data is reached. 
                        change_dict_list = []
                        for row in csv_reader:
                            if skip > 0:
                                skip -= 1
                                continue
                            change_dict_list.append(
                                self.percent_changes(float(row[1]),
                                float(row[2]),
                                float(row[3]),
                                float(row[4]))
                            )
                        change_dict_list.pop() # final row has not yet closed

                    for new_data in change_dict_list:
                        for metric in scoring_json[timeframe]:
                            bisect.insort(scoring_json[timeframe][metric], new_data[metric]) # add to sorted list
    
            with open(f'{self.candlestick_path}/{symbol}/{symbol}_analysis.json', 'w') as jf:
                json.dump(scoring_json, jf, indent=4)


    def update_database(self): # TODO make private
        '''
        Updates all csv and json files of given coin.
        '''
 
        # More expensive update, only perform at most every hour or when need update.
        if self.synchronize_score_jsons() or not self.previous_update_UTS or (time() - self.previous_update_UTS >= 3600):
            symbol_timeframes = self.get_symbol_timeframes()
            for symbol in symbol_timeframes:
                tradingpair = symbol.split(self.coin)[-1]
                timeframes = symbol_timeframes[symbol]
                self.get_candles(tradingpair, timeframes)
            self.update_score_jsons()


    def current_score(self, symbol, custom_timeframes, custom_threshold=None):
        '''
        Returns current calculated score.
        Bull/Bear score indicates how well the current price action performs compared to all histortical candle max/min spikes
        change_score indicates how likely the current price will change_score based on all historical candle closes
        Amplitude score indicates how volitile the current price action is compared to all historical candle closes
        Optional parameter `server_monitored_timeframes` which takes a list of symbol_timeframes to specifically calculate score for.
        '''

        self.update_database()
        if not custom_threshold:
            custom_threshold = self.optimise_signal_threshold(symbol, custom_timeframes) # TODO optimise with threading
        bear_threshold, bull_threshold = [threshold.split(':')[-1] for threshold in custom_threshold.split('|')]
        print(f'current_score: input {symbol} : {custom_timeframes}, bull_threshold: {bear_threshold}, bear_threshold: {bull_threshold}')

        score_dict = {}
        latest_price = 0
        for timeframe in sorted(custom_timeframes, key=lambda timeframe : INTERVALS.index(timeframe)):
            latest_candle = self.get_latest_stored_uts(self.get_candlestick_path(symbol, timeframe))
            klines = client.get_historical_klines(symbol, timeframe, latest_candle)[0] # TODO add volumn data
            score_dict[timeframe] = self.percent_changes(float(klines[1]), float(klines[2]), float(klines[3]), float(klines[4]))
            latest_price = klines[4]

        with open(f'{self.candlestick_path}/{symbol}/{symbol}_analysis.json', 'r') as jf:
            scoring_json = json.load(jf)
        for timeframe in score_dict:
            bull_score, bear_score, change_score = 0, 0, 0
            current_change = score_dict[timeframe]['candle_change']
            amplitude_change = score_dict[timeframe]['candle_amplitude']
            if current_change > 0:
                metric = "candle_max_up"
                score_dict[symbol][timeframe]["candle_max_down"] = 'NA'
            else:
                metric = "candle_max_down"
                score_dict[symbol][timeframe]["candle_max_up"] = 'NA'
            amp_score = self.score_amplitude(
                amp_list=scoring_json[timeframe]["candle_amplitude"],
                size=len(scoring_json[timeframe]["candle_amplitude"]),
                amplitude_change=amplitude_change
                )
            score, change_score_ = self.score_performance(
                max_list=scoring_json[timeframe][metric],
                change_list=scoring_json[timeframe]["candle_change"],
                size=len(scoring_json[timeframe][metric]),
                absolute_change=abs(current_change),
                current_percent_change=current_change
                )

            # Construct current scoring summary dict to send to server
            if amp_score > 0:
                historical_average = self.average(scoring_json[timeframe]["candle_amplitude"])
                score_dict[timeframe]["candle_amplitude"] = \
                    f"Score: {amp_score} | Change: {amplitude_change}% | average: {historical_average}%"
            elif amp_score < 0:
                historical_average = self.average(scoring_json[timeframe]["candle_amplitude"])
                score_dict[timeframe]["candle_amplitude"] = \
                    f"Unusually small amplitude | Change: {amplitude_change}% | average: {historical_average}%"
            else:
                score_dict[timeframe]["candle_amplitude"] = 'AVERAGE'
            
            if score:
                historical_average = self.average(scoring_json[timeframe][metric])
                score_dict[timeframe][metric] = \
                    f"Score: {score} | Change score: {change_score} | Change: {current_change}% | average: {historical_average}%"
                if metric == "candle_max_up":
                    bull_score += score
                else:
                    bear_score += score
                change_score += change_score_
            else:
                score_dict[timeframe][metric] = 'AVERAGE'

        signal = ''
        if bull_score >= bull_threshold and bear_score >= bear_threshold:
            signal = ''
        elif bull_score >= bull_threshold and bull_score > bear_score:
            signal = 'SELL'
        elif bear_score >= bear_threshold and bear_score > bull_score:
            signal = 'BUY'

        return [symbol, bull_score, bear_score, change_score, signal, latest_price, score_dict]

    
    def compute_historical_score(self, symbol, custom_timeframes):
        '''
        Calculates bull/bear/change_scorement score for all 5 minute intervals of the coins history.
        Each 5 minutes simulates running the current score method back in time, with information known only back during the 5minute interval
        Bull/Bear score indicates how well the current price action performs compared to all histortical candle data
        Retain_score indicates how likely the current price will change_score based on historical data
        If prior historical analysis is present, only the latest data will be computed and appended.
        '''

        print(f'computing historical score for {symbol}...')
        self.update_database() # Get latest candles from Binance
        self.get_candles(symbol.split(self.coin)[-1], ["5m"]) # update latest 5min data - this may take time due to Binance
        print('Latest candle data aquired! Comencing score calculation...')
        filename_ext = get_filename_extension(custom_timeframes)
        if custom_timeframes:
            symbol_timeframes = sorted([symbol + '_' + tf for tf in custom_timeframes], key= lambda i : INTERVALS.index(i.split("_")[-1]))
        else:
            symbol_timeframes = [symbol + '_' + tf for tf in self.deafult_scoring_timeframes]
    
        # make dataframe to hold all historical 5min intervals (i.e. real time price action from the past).
        historical_rt_price_DF = pd.read_csv(f"{self.coin_path}/{symbol}_5m.csv", usecols=[0, 4], names=["UTS", "price"], header=None, skiprows=1)
        bull_scores, bear_scores, change_scores = [], [], []
        score_tracker = {}
        timeframe_cols = {}
        for symbol_tf in symbol_timeframes:
            score_tracker[symbol_tf + "_BEAR"] = []
            score_tracker[symbol_tf + "_BULL"] = []
            timeframe_cols[symbol_tf] = [symbol_tf + "-UTS", symbol_tf + "-open", symbol_tf + "-high", symbol_tf + "-low", symbol_tf + "-close"]

        # make symbol_timeframes_DF which has columns for UTS-date, open, high, low, close, of all symbol_timeframes
        symbol_timeframes_DF = pd.DataFrame()
        historical_percent_changes = {} # used to act like a dynamically growing analysis_coin.json
        for symbol_tf in symbol_timeframes:
            temp_DF = pd.read_csv(f"{self.coin_path}/{symbol_tf}.csv", usecols=[0, 1, 2, 3, 4], names=timeframe_cols[symbol_tf], header=None, skiprows=1)
            historical_percent_changes[symbol_tf] = {'candle_change':[], 'candle_max_up':[], 'candle_max_down':[]}
            symbol_timeframes_DF = symbol_timeframes_DF.merge(right=temp_DF, how="outer", left_index=True, right_index=True)

        # Load from previous data and skip until new data, else perform initilisation
        df_positiontracker = {} # To complement the symbol_timeframes_DF dataframe
        historical_scoring_csv_path = f"{self.historical_scoring_path}/{symbol}/historical_scoring_{symbol}_{filename_ext}.csv"
        historical_analysis_json_path = f"{self.historical_scoring_path}/{symbol}/historical_analysis_{symbol}_{filename_ext}.json"        
        if os.path.exists(historical_scoring_csv_path):
            with open(historical_analysis_json_path, 'r') as jf:
                historical_percent_changes = json.load(jf) 
            skip_UTS = pd.read_csv(historical_scoring_csv_path).iloc[-1][0] # skip to where the last historical analysis ends
            for symbol_tf in symbol_timeframes:
                end_index = symbol_timeframes_DF[symbol_timeframes_DF[symbol_tf + '-UTS'].notnull()].shape[0] # get 1 past final index position
                if symbol_timeframes_DF.index[symbol_timeframes_DF[symbol_tf + '-UTS'] >= skip_UTS].any():
                    index = symbol_timeframes_DF.index[symbol_timeframes_DF[symbol_tf + '-UTS'] >= skip_UTS][0] - 1 # get index just before skip
                    df_positiontracker[symbol_tf] = {
                        "index":index,
                        "end_index":end_index,
                        "open_price":symbol_timeframes_DF.loc[index, [symbol_tf + "-open"]][0],
                        "next_UTS": symbol_timeframes_DF.loc[index + 1, [symbol_tf + "-UTS"]][0],
                        "columns": timeframe_cols[symbol_tf]}		
                else: # no new symbol_timeframe candles added since last calculation, hence skip till end
                    df_positiontracker[symbol_tf] = {
                        "index":end_index - 1,
                        "end_index":end_index,
                        "open_price":symbol_timeframes_DF.loc[end_index - 1, [symbol_tf + "-open"]][0],
                        "next_UTS": symbol_timeframes_DF.loc[end_index - 1, [symbol_tf + "-UTS"]][0],
                        "columns": timeframe_cols[symbol_tf]}		
        else:
            # initialise dataframe and json for the first 3 -> 21 days of price action 
            first_3day_UTS = int(symbol_timeframes_DF.loc[3, [symbol + '_1d-UTS']]) # Skip because unreliable due to volitility in general
            skip_UTS = int(symbol_timeframes_DF.loc[21, [symbol + '_1d-UTS']]) # UTS date for 21 days of price action
            for symbol_tf in symbol_timeframes:
                columns = timeframe_cols[symbol_tf]
                percent_changes_list = [
                    self.percent_changes(row[1],row[2],row[3],row[4]) for row in symbol_timeframes_DF[columns].to_numpy()
                    if row[0] > first_3day_UTS and row[0] <= skip_UTS]
                first_3day_skip = symbol_timeframes_DF.index[symbol_timeframes_DF[symbol_tf + '-UTS'] >= first_3day_UTS][0]
                index = len(percent_changes_list) + first_3day_skip  # location of three week UTS index position in dataframe for each timeframe 
                df_positiontracker[symbol_tf] = {
                    "index":index,
                    "end_index":symbol_timeframes_DF[symbol_timeframes_DF[symbol_tf + '-UTS'].notnull()].shape[0],
                    "open_price":symbol_timeframes_DF.loc[index, [columns[1]]][0],
                    "next_UTS": symbol_timeframes_DF.loc[index + 1, [columns[0]]][0],
                    "columns": columns}
                for metric in historical_percent_changes[symbol_tf]:
                    historical_percent_changes[symbol_tf][metric] = [row[metric] for row in percent_changes_list]
                    historical_percent_changes[symbol_tf][metric].sort()

        # Score every 5 minute interval of given coin with information known only during that time
        historical_rt_price_DF = historical_rt_price_DF.loc[historical_rt_price_DF.UTS > skip_UTS].reset_index().drop("index", axis=1) # skip to lastest
        for row in historical_rt_price_DF.itertuples(name=None): 
            current_UTS, price, total_bull, total_bear, total_change_score = row[1], row[2], 0, 0, 0
            for symbol_tf in symbol_timeframes:
                if current_UTS >= df_positiontracker[symbol_tf]["next_UTS"]:
                    index = df_positiontracker[symbol_tf]["index"] # get current index
                    end_index = df_positiontracker[symbol_tf]["end_index"] # get 1 past final index
                    if index + 1 == end_index:
                        df_positiontracker[symbol_tf]["next_UTS"] = float('inf') # Reached the end for this timeframe
                    else:
                        index += 1
                        if index + 1 == end_index:
                            next_index, i = index, 0 # second last index for given timeframe
                        else:
                            next_index, i = index + 1, 1
                            
                        # update symbol_timeframe position in dataframe
                        new_row = symbol_timeframes_DF.loc[index:next_index, df_positiontracker[symbol_tf]["columns"]].values		
                        df_positiontracker[symbol_tf]["index"] = index
                        df_positiontracker[symbol_tf]["open_price"] = new_row[0][1]
                        df_positiontracker[symbol_tf]["next_UTS"] = new_row[i][0]
                        
                        # update dynamically growing performance ranking json 
                        percent_changes = self.percent_changes(new_row[0][1], new_row[0][2], new_row[0][3], new_row[0][4])
                        for metric in historical_percent_changes[symbol_tf]:
                            bisect.insort(historical_percent_changes[symbol_tf][metric], percent_changes[metric]) # insert value into sorted list
                
                # calculate score
                current_percent_change = (price / df_positiontracker[symbol_tf]["open_price"])*100 - 100 # %change for given candle
                if current_percent_change > 0:
                    metric = "candle_max_up"
                else:
                    metric = "candle_max_down"
                score, change_score = self.score_performance(
                    max_list= historical_percent_changes[symbol_tf][metric], 
                    change_list= historical_percent_changes[symbol_tf]["candle_change"],
                    size= len(historical_percent_changes[symbol_tf][metric]), 
                    absolute_change= abs(current_percent_change), 
                    current_percent_change= current_percent_change)	
                if metric == "candle_max_up":
                    total_bull += score
                    score_tracker[symbol_tf + "_BULL"].append(score)
                    score_tracker[symbol_tf + "_BEAR"].append(0)
                else:
                    total_bear += score
                    score_tracker[symbol_tf + "_BEAR"].append(score)
                    score_tracker[symbol_tf + "_BULL"].append(0)
                total_change_score += change_score

            bull_scores.append(total_bull)
            bear_scores.append(total_bear)
            change_scores.append(total_change_score)

        if os.path.exists(historical_scoring_csv_path):
            columns = ["bull_scores", "bear_scores", "change_scores", *[timeframe for timeframe in score_tracker], "Signal"]
            column_data = [bull_scores, bear_scores, change_scores, *[score_tracker[timeframe] for timeframe in score_tracker]]
            newdata_DF = pd.DataFrame({column:data for column, data in zip(columns, column_data)}) # column is string, data is list
            newdata_DF = historical_rt_price_DF.merge(right=newdata_DF, how="outer", left_index=True, right_index=True)
            newdata_DF.to_csv(historical_scoring_csv_path, mode='a', header=False, index=False)
        else:
            historical_rt_price_DF.insert(2, "bull_scores", bull_scores)
            historical_rt_price_DF.insert(3, "bear_scores", bear_scores)
            historical_rt_price_DF.insert(4, "change_scores", change_scores)
            [historical_rt_price_DF.insert(5 + count, timeframe, score_tracker[timeframe]) for count, timeframe in enumerate(score_tracker)]
            historical_rt_price_DF.to_csv(historical_scoring_csv_path, index=False)
        
        with open(historical_analysis_json_path, 'w') as jf:
            json.dump(historical_percent_changes, jf, indent=4) 


    def generate_look_ahead_gains(self, symbol, custom_timeframes, custom_threshold=None):
        '''
        Searches through specificed historical_scoring csv to find bull/bear score peaks over a certain thresold.
        Once found, it calculates the % difference of if you sold/bought after 30min, 1h, 4h, 1d, 3d, 1w, 2w.
        Saves the data in 'look_ahead_gains.csv'
        '''

        print('computing look ahead gains...')
        threshold_strat = ''
        if custom_threshold:
            threshold_strat = custom_threshold
            self.compute_historical_score(symbol, timeframes)
        else:
            threshold_strat = self.optimise_signal_threshold(symbol, timeframes)
        bull_threshold, bear_threshold = [int(threshold.split(':')[-1]) for threshold in threshold_strat.split('|')]

        filename_ext = get_filename_extension(custom_timeframes)
        historical_score_path = f"{self.historical_scoring_path}/{symbol}/historical_scoring_{symbol}_{filename_ext}.csv"
        look_ahead_gains_csv = f"{self.look_ahead_path}/{symbol}/look_ahead_gains_{symbol}_{filename_ext}.csv"
        historical_scoring_DF = pd.read_csv(historical_score_path, index_col= 0, header=None, skiprows=1)

        with open(look_ahead_gains_csv, 'a') as outfile, open(look_ahead_gains_csv, 'r') as infile:
            retain_csv_writer = csv.writer(outfile)
            skip_UTS = historical_scoring_DF.index[0]
            if (outfile.tell() == 0):
                timeframes = custom_timeframes if custom_timeframes else self.deafult_scoring_timeframes
                retain_csv_writer.writerow(["UTC", "price", "peak_start", "change_score", "goal",
                                            "%diff_30min", "%diff_1h", "%diff_4h", "%diff_12h", "%diff_1d",
                                            "%diff_3d", "%diff_1w", "%diff_2w", *timeframes, "UTS"])
            else:
                infile.seek(outfile.tell() - 15) # skip to end of file, capture last UTS
                skip_UTS = infile.readline()

            peak_start = 0
            peak_row = []
            best_prices = {6:0, 12:0, 48:0, 144:0, 288:0, 864:0, 2016:0, 4032:0} # number of 5min look ahead intervals
            uts_5min = 300000

            for row in historical_scoring_DF.loc[skip_UTS:].itertuples(name=None):
                bull_score, bear_score = row[2:4]
                if peak_start:
                    # Binance exchange updates causes missing rows, hence DF is sliced with safe buffer of 4500 5 min intervals rather than 4032
                    look_ahead_DF = historical_scoring_DF.loc[peak_row[0]:(peak_row[0] + uts_5min*4500)]
                    if (look_ahead_DF.shape[0] < 4032):
                        break # Less than 2 weeks of look ahead data avaliable, so end process

                    best_price = float(peak_row[1])
                    goal = "buy_back" if peak_row[2] > peak_row[3] else "sell_later"
                    for row_look_ahead in look_ahead_DF.itertuples(name=None):
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
                            if look_ahead == 4032:
                                break
                    tf_start = 6 if goal == 'buy_back' else 5
                    tf_scores = [peak_row[i] for i in range(tf_start, len(peak_row) - 1, 2)]
                    utc_time = datetime.utcfromtimestamp(int(str(peak_row[0])[:-3])).strftime('|%d-%m-%Y %H:%M:%S|')
                    retain_csv_writer.writerow([
                        utc_time, peak_row[1], peak_start, peak_row[4], goal,
                        *[diff for diff in best_prices.values()], *tf_scores, peak_row[0]
                    ])
                    look_ahead = 12
                    peak_start = 0

                if bull_score >= bull_threshold and bear_score >= bear_threshold:
                    continue
                elif bull_score >= bull_threshold and bull_score > bear_score:
                    peak_start, peak_row = bull_score, row
                elif bear_score >= bear_threshold and bear_score > bull_score:
                    peak_start, peak_row = bear_score, row
        return look_ahead_gains_csv


    def generate_retain_score(self, symbol, custom_timeframes):
        '''
        Creates a score file summarising the data in look_ahead_gains.csv for given symbol
        '''

        print('computing retain score...')
        filename_ext = get_filename_extension(custom_timeframes)
        retain_score_csv = f"{self.retain_scoring_path}/{symbol}/retain_scoring_{symbol}_{filename_ext}.csv"
        look_ahead_gains_csv = f"{self.look_ahead_path}/{symbol}/look_ahead_gains_{symbol}_{filename_ext}.csv"
        self.generate_look_ahead_gains(symbol, custom_timeframes)

        bullscore_bestgain = defaultdict(list) # key = score, value = list of best %gains
        bearscore_bestgain = defaultdict(list)
        average_bestgain = {"buy_back":{"30m":[], "1h":[], "4h":[], "12h":[], "1d":[], "3d":[], "1w":[], "2w":[]},
                            "sell_later":{"30m":[], "1h":[], "4h":[], "12h":[], "1d":[], "3d":[], "1w":[], "2w":[]}}

        with open(look_ahead_gains_csv, 'r') as infile, open(retain_score_csv, 'w') as outfile:
            lookahead_csv_reader = csv.reader(infile)
            next(lookahead_csv_reader)
            for row in lookahead_csv_reader:
                index = 5
                if row[4] == "buy_back":
                    bullscore_bestgain[int(row[2])].append(min([int(i) for i in row[5:13]]))
                    for look_ahead in average_bestgain["buy_back"]:
                        average_bestgain["buy_back"][look_ahead].append(int(row[index]))
                        index += 1
                else:
                    bearscore_bestgain[int(row[2])].append(max([int(i) for i in row[5:13]]))
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


    def simulate_trading(self, symbol, custom_timeframes, single_threshold='', single_metric='overall'):
        # TODO investigate why peak top strat didn't work, perhaps use PA graph to help
        # if you work it out, then implment peak_top options for the other methods - but for now, it's pointless

        filename_ext = get_filename_extension(custom_timeframes)
        historical_score_path = f'{self.historical_scoring_path}/{symbol}/historical_scoring_{symbol}_{filename_ext}.csv'
        if os.path.exists(historical_score_path):
            # run this function once every hour at most per parameters
            if time() - self.get_latest_stored_uts(historical_score_path) < 3600:
                if filename_ext in self.previous_updated_simulations:
                    return
                else:
                    self.previous_updated_simulations.append(filename_ext)
        self.compute_historical_score(symbol, custom_timeframes)
        historical_DF = pd.read_csv(historical_score_path, index_col= 0, usecols=[0, 1, 2, 3, 4], header=None, skiprows=1)

        max_threshold = int(len(historical_score_path.split('_')[-1].split('-'))*6)
        bull_start_threshold = 2 if not single_threshold else int(single_threshold.split('|')[0].split(':')[-1])
        bull_end_threshold = max_threshold if not single_threshold else bull_start_threshold + 1
        bear_start_threshold = 2 if not single_threshold else int(single_threshold.split(':')[-1])
        bear_end_threshold = max_threshold if not single_threshold else bear_start_threshold + 1
        trading_pair = symbol.split(self.coin)[-1]
        inital_coin_price = historical_DF.iloc[0, 0]
        inital_pair_holdings = 10000 if trading_pair in STANDARD_TRADING_PAIRS else 5
        inital_coin_holdings = round(10000 / inital_coin_price, 3)
        start_uts = historical_DF.iloc[0].name
        final_uts = historical_DF.iloc[-1].name
        summary = {'overall':{}, 'max':{}}
        analysis_cols = {}

        trade_simulation_path = f'{self.trading_simulation_path}/{symbol}/trade_simulation_{symbol}_{filename_ext}.csv'
        if os.path.exists(trade_simulation_path) and not single_threshold:
            with open(trade_simulation_path, 'r') as f:
                f.readline()
                for strat_gain in f.readline().split(',')[1:]:
                    analysis_cols[f'{strat_gain.split("=")[0]}_holdings_log'] = [float(strat_gain.split('=')[-1])]
                csv_reader = csv.reader(f)
                for row in csv_reader:
                    if 'UTS' in row[0]:
                        strat = row[0].split('_')[-1]
                        analysis_cols[strat] = [[
                            f'UTS_{strat}',
                            'prev_price',
                            'price',
                            'action',
                            'coin_holdings',
                            'pair_holdings',
                            'action_coin_profit',
                            'action_pair_profit',
                            'action_coin_gain',
                            'action_pair_gain'
                        ]]
                    else:
                        analysis_cols[strat].append([
                            int(row[0]),
                            float(row[1]),
                            float(row[2]),
                            row[3],
                            float(row[4]),
                            float(row[5]),
                            float(row[6]),
                            float(row[7]),
                            float(row[8]),
                            float(row[9])
                        ])

        for bull_threshold in range(bull_start_threshold, bull_end_threshold):
            for bear_threshold in range(bear_start_threshold, bear_end_threshold):
                strat = f'BULL:{bull_threshold}|BEAR:{bear_threshold}'
                if strat in analysis_cols:
                    latest_row = analysis_cols[strat][-1]
                    skip_uts = int(latest_row[0])
                    prev_price = float(latest_row[2])
                    prev_signal = 'SELL' if latest_row[3] == 'BUY' else 'BUY'
                    holdings = float(latest_row[4]) if float(latest_row[4]) else float(latest_row[5])
                    move_made = True
                    signal = ''
                else:
                    analysis_cols[strat] = [[
                        f'UTS_{strat}',
                        'prev_price',
                        'price',
                        'action',
                        'coin_holdings',
                        'pair_holdings',
                        'action_coin_profit',
                        'action_pair_profit',
                        'action_coin_gain',
                        'action_pair_gain'
                    ]]
                    analysis_cols[f'{strat}_holdings_log'] = []
                    skip_uts = start_uts
                    prev_price = 0
                    prev_signal = 'SELL'
                    holdings = 10000 if trading_pair in STANDARD_TRADING_PAIRS else 5 # Alternates between coin and pair.
                    move_made = False
                    signal = ''
                for row in historical_DF.loc[skip_uts:].itertuples(name=None):
                    bull_score = row[2] # i.e. massive surge up, hence you want to SELL
                    bear_score = row[3] # i.e. massive surge down, hence you want to BUY
                    if bull_score >= bull_threshold and bear_score >= bear_threshold:
                        continue # indecision
                    if bull_score >= bull_threshold and bull_score > bear_score:
                        signal = 'SELL'
                    elif bear_score >= bear_threshold and bear_score > bull_score:
                        signal = 'BUY'
                    if prev_signal != signal:
                        if bull_score >= bull_threshold or bear_score >= bear_threshold:
                            if not move_made:
                                move_made = True
                                coin_holdings, coin_profit, coin_gain, pair_holdings, pair_profit, pair_gain = 0, 0, 0, 0, 0, 0
                                if prev_price == 0:
                                    prev_price = row[1]
                                if signal == 'BUY':
                                    coin_holdings = round(holdings / row[1], 5)
                                    coin_profit = round(coin_holdings - (holdings / prev_price), 5)
                                    coin_gain = round((prev_price / row[1])*100 - 100, 3)
                                else:
                                    pair_holdings = round(holdings * row[1], 5)
                                    pair_profit = round(pair_holdings - (holdings * prev_price), 5)
                                    pair_gain = round((row[1] / prev_price)*100 - 100, 3)
                                analysis_cols[strat].append([
                                    row[0],
                                    prev_price,
                                    row[1],
                                    signal,
                                    coin_holdings,
                                    pair_holdings,
                                    coin_profit,
                                    pair_profit,
                                    coin_gain,
                                    pair_gain
                                ])
                                analysis_cols[f'{strat}_holdings_log'].append(coin_holdings)
                                holdings = coin_holdings if coin_holdings else pair_holdings
                                prev_price = row[1]
                        elif move_made:
                            prev_signal = signal
                            move_made = False        
                summary['overall'][strat] = analysis_cols[strat][-1][4] if analysis_cols[strat][-1][4] else analysis_cols[strat][-2][4]
                summary['max'][strat] = max(analysis_cols[f'{strat}_holdings_log'])

        sorted_summary = {'overall':{}, 'max':{}}
        sorted_summary['overall'] = {k: v for k, v in sorted(summary['overall'].items(), key=lambda kv: kv[1], reverse=True)}
        sorted_summary['max'] = {k: v for k, v in sorted(summary['max'].items(), key=lambda kv: kv[1], reverse=True)}

        if single_threshold:
            analysis_cols['metric'] = single_metric
            return analysis_cols[sorted_summary[single_metric].popitem()[0]]
        else:
            ranked_best_max_strats = [f'{strat}={gain}' for strat, gain in sorted_summary['max'].items()]
            with open(trade_simulation_path, 'w') as f:
                csv_writer = csv.writer(f, delimiter=',')
                csv_writer.writerow([
                    'inital_coin',
                    inital_coin_holdings,
                    'inital_pair',
                    inital_pair_holdings,
                    'start_uts',
                    start_uts,
                    'final_uts',
                    final_uts
                ])
                csv_writer.writerow(['ranked_max_performing_strats', *ranked_best_max_strats])
                for strat in sorted_summary['overall']:
                    for row in analysis_cols[strat]:
                        csv_writer.writerow(row)


    def optimise_signal_threshold(self, symbol, custom_timeframes, metric='overall'):
        '''
        By default this will return the rank 1 best overall threshold setting used for the given symbol/parameters
        If the metric function parameter is set to 'max' then the rank 1 best max threshold will be returned
        '''

        # TODO definetly use threading
        filename_ext = get_filename_extension(custom_timeframes)
        self.simulate_trading(symbol, custom_timeframes)
        with open(f'{self.trading_simulation_path}/{symbol}/trade_simulation_{symbol}_{filename_ext}.csv', 'r') as f:
            csv_reader = csv.reader(f)
            csv_reader.__next__()
            best_max_gains_strat = csv_reader.__next__()[1].split('=')[0]
            best_overall_strat = csv_reader.__next__()[0].split('_')[-1]
            if metric == 'overall':
                return best_overall_strat # best overall strat
            else:
                return best_max_gains_strat # Best max gain strat


    def graph_look_ahead_data(self, symbol, custom_timeframes, graph_type="bar"):
        '''
        Generates either a bar graph or line graph summarising the potential gains from buying/selling at the given score peaks.
        using from looking ahead data
        '''

        #TODO remove line graph option

        print('computing graph...')
        filename_ext = get_filename_extension(custom_timeframes)
        look_ahead_gains_csv = f"{self.look_ahead_path}/{symbol}/look_ahead_gains_{symbol}_{filename_ext}.csv"
        filename_ext += '' if graph_type == 'bar' else '_line'
        self.generate_look_ahead_gains(symbol, custom_timeframes)

        make_dict = lambda : {"30m":[], "1h":[], "4h":[], "1d":[], "3d":[], "1w":[], "2w":[]}
        best_gains = {"buy_back":defaultdict(make_dict), "sell_later":defaultdict(make_dict)}

        with open(look_ahead_gains_csv, 'r') as infile:
            lookahead_csv_reader = csv.reader(infile)		
            next(lookahead_csv_reader)
            for row in lookahead_csv_reader:
                index = 5
                if row[4] == "buy_back":
                    for look_ahead in best_gains["buy_back"][int(row[2])]:
                        best_gains["buy_back"][int(row[2])][look_ahead].append(int(row[index]))
                        index += 1
                else:
                    for look_ahead in best_gains["sell_later"][int(row[2])]:
                        best_gains["sell_later"][int(row[2])][look_ahead].append(int(row[index]))
                        index += 1

        fig, (ax_bull, ax_bear) = plt.subplots(nrows= 2, ncols= 1, figsize=(20, 16))
        plt.subplots_adjust(left=0.05, bottom=0.05, right=0.9, top=0.95, wspace=0.4, hspace=0.35)
        color_dict = {"30m":"indianred", "1h":"chocolate", "4h":"orange", "1d":"yellowgreen", "3d":"forestgreen", "1w":"mediumspringgreen", "2w":"mediumturquoise"}	
        scores = arange(15, 31) # TODO find the min and max from the rows and make that the range
        width = 0.11
        pos = -3

        for look_ahead, color in color_dict.items():
            averages = [self.average(best_gains["buy_back"][score][look_ahead]) for score in range(15, 31)]
            stdevs = [stdev(best_gains["buy_back"][score][look_ahead]) if len(best_gains["buy_back"][score][look_ahead]) > 1 else 0 for score in range(15, 31)]
            print(f'scores: {scores}')
            print(f'averages: {averages}')
            print(f'stdevs: {stdevs}')
            if graph_type == "bar":
                ax_bull.bar(scores + width*pos, averages, width, yerr= stdevs, label=look_ahead, color= color, edgecolor= "black")
            elif graph_type == "line":
                ax_bull.errorbar(scores, averages, yerr= stdevs, label=look_ahead)

            averages = [self.average(best_gains["sell_later"][score][look_ahead]) for score in range(15, 31)]
            stdevs = [stdev(best_gains["sell_later"][score][look_ahead]) if len(best_gains["sell_later"][score][look_ahead]) > 1 else 0 for score in range(15, 31)]
            if graph_type == "bar":
                ax_bear.bar(scores + width*pos, averages, width, yerr= stdevs, label=look_ahead, color= color, edgecolor= "black")
            elif graph_type == "line":
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

        plt.savefig(f"{self.graph_path}/look_aheads/{symbol}/look_ahead_graph_{symbol}_{filename_ext}.png")

    
    def graph_trading_simulation(self, symbol, custom_timeframes, top_x=20):
        '''
        Graphs out the percentage gain compared to inital holding from blindly trading the signals generated by thresholds
        Specifically, this graphs the gains of the coin of interest, as well as its tradingpair. The first graph is the best overall
        performing thresholds, the second graph is this same graph however showing the tradingpair gains, and the final graph is
        the thresholds which resulted in the highest historical gains.
        '''

        filename_ext = get_filename_extension(custom_timeframes)
        self.simulate_trading(symbol, custom_timeframes)
        fig, (ax_overall, ax_pair, ax_max) = plt.subplots(nrows= 3, ncols= 1, figsize=(25, 21))
        with open(f'{self.trading_simulation_path}/{symbol}/trade_simulation_{symbol}_{filename_ext}.csv', 'r') as f:
            header = f.readline().split(',')
            inital_coin_holding = float(header[1])
            inital_pair_holding = float(header[3])
            start_uts = datetime.fromtimestamp(int(header[5][:-3]))
            final_uts = datetime.fromtimestamp(int(header[-1].strip()[:-3]))
            bear_markets = filter_market_periods(BEAR_MARKETS, start_uts, final_uts)
            bull_markets = filter_market_periods(BULL_MARKETS, start_uts, final_uts)
            max_gains_thresholds_topx = [strat_gain.split('=')[0] for strat_gain in f.readline().split(',')[1:]][:top_x]
            csv_reader = csv.reader(f)
            ranked_overall = {}
            ranked_max = {}
            overall_done = False
            for row in csv_reader:
                uts = row[0]
                coin_holding = row[4]
                pair_holding = row[5]
                if coin_holding == '0' or coin_holding == '0.0':
                    if not overall_done:
                        ranked_overall[strat]['pair_uts'].append(datetime.fromtimestamp(int(uts[:-3])))
                        ranked_overall[strat]['pair_holding_gains'].append(round((float(pair_holding) / inital_pair_holding)*100 - 100, 2))
                        ranked_overall[strat]['pair_successful_trades'] += 1 if '-' != row[-1][0] else 0
                elif 'UTS' in uts:
                    strat = uts.split('_')[-1]
                    overall_done = True if len(ranked_overall) == top_x else False
                    if len(ranked_overall) < top_x:
                        ranked_overall[strat] = {
                            'coin_uts':[],
                            'coin_holding_gains':[],
                            'coin_successful_trades':0,
                            'pair_uts':[],
                            'pair_holding_gains':[],
                            'pair_successful_trades':0
                        }
                    if strat in max_gains_thresholds_topx:
                        if len(ranked_max) < top_x:
                            ranked_max[strat] = {
                                'coin_uts':[],
                                'coin_holding_gains':[],
                                'coin_successful_trades':0,
                                'pair_uts':[],
                                'pair_holding_gains':[],
                                'pair_successful_trades':0
                            }
                        else: break
                else:
                    if not overall_done:
                        ranked_overall[strat]['coin_uts'].append(datetime.fromtimestamp(int(uts[:-3])))
                        ranked_overall[strat]['coin_holding_gains'].append(round((float(coin_holding) / inital_coin_holding)*100 - 100, 2))
                        ranked_overall[strat]['coin_successful_trades'] += 1 if '-' != row[-2][0] else 0
                    if strat in max_gains_thresholds_topx:
                        ranked_max[strat]['coin_uts'].append(datetime.fromtimestamp(int(uts[:-3])))
                        ranked_max[strat]['coin_holding_gains'].append(round((float(coin_holding) / inital_coin_holding)*100 - 100, 2))
                        ranked_max[strat]['coin_successful_trades'] += 1 if '-' != row[-2][0] else 0

            # plotting for overall best performing thresholds for coin
            for strat, data in ranked_overall.items():
                success_ratio = round(data["coin_successful_trades"]/len(data["coin_uts"]), 2)
                data['coin_uts'].append(final_uts)
                data['coin_holding_gains'].append(data['coin_holding_gains'][-1])
                ax_overall.plot(
                    data['coin_uts'],
                    data['coin_holding_gains'],
                    label=f'{strat:<16} {len(data["coin_uts"]):<5} {success_ratio:<5} {int(data["coin_holding_gains"][-1])}'
                )
            for bear_market in bear_markets:
                ax_overall.axvspan(*bear_market, ymax=1, color ='firebrick', alpha=0.1)
            for bull_market in bull_markets:
                ax_overall.axvspan(*bull_market, ymax=1, color ='limegreen', alpha=0.1)
            for label in ax_overall.get_xticklabels(which='major'):
                label.set(rotation=30, horizontalalignment='right')
            ax_overall.plot([start_uts, final_uts], [0, 0], linestyle="--", color='yellowgreen')
            ax_overall.plot([start_uts, final_uts], [100, 100], linestyle="--", color='mediumspringgreen')
            ax_overall.plot([start_uts, final_uts], [-100, -100], linestyle="--", color='red')
            ax_overall.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
            ax_overall.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax_overall.xaxis.set_minor_locator(mdates.MonthLocator(interval=1))
            ax_overall.margins(x=0.01)

            # plotting for overall best performing thresholds for pair
            for strat, data in ranked_overall.items():
                success_ratio = round(data["pair_successful_trades"]/len(data["pair_uts"]), 2)
                data['pair_uts'].append(final_uts)
                data['pair_holding_gains'].append(data['pair_holding_gains'][-1])
                ax_pair.plot(
                    data['pair_uts'],
                    data['pair_holding_gains'],
                    label=f'{strat:<16} {len(data["pair_uts"]):<5} {success_ratio:<5} {int(data["pair_holding_gains"][-1])}'
                )
            for bear_market in bear_markets:
                ax_pair.axvspan(*bear_market, ymax=1, color ='firebrick', alpha=0.1)
            for bull_market in bull_markets:
                ax_pair.axvspan(*bull_market, ymax=1, color ='limegreen', alpha=0.1)
            for label in ax_pair.get_xticklabels(which='major'):
                label.set(rotation=30, horizontalalignment='right')
            ax_pair.plot([start_uts, final_uts], [0, 0], linestyle="--", color='yellowgreen')
            ax_pair.plot([start_uts, final_uts], [100, 100], linestyle="--", color='mediumspringgreen')
            ax_pair.plot([start_uts, final_uts], [-100, -100], linestyle="--", color='red')
            ax_pair.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
            ax_pair.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax_pair.xaxis.set_minor_locator(mdates.MonthLocator(interval=1))
            ax_pair.margins(x=0.01)

            # plotting for highest max gains achieved thresholds
            for strat in max_gains_thresholds_topx:
                data = ranked_max[strat]
                success_ratio = round(data["coin_successful_trades"]/len(data["coin_uts"]), 2)
                data['coin_uts'].append(final_uts)
                data['coin_holding_gains'].append(data['coin_holding_gains'][-1])
                ax_max.plot(
                    data['coin_uts'],
                    data['coin_holding_gains'],
                    label=f'{strat:<16} {len(data["coin_uts"]):<5} {success_ratio:<5} {int(max(data["coin_holding_gains"]))}'
                )
            for bear_market in bear_markets:
                ax_max.axvspan(*bear_market, ymax=1, color ='firebrick', alpha=0.1)
            for bull_market in bull_markets:
                ax_max.axvspan(*bull_market, ymax=1, color ='limegreen', alpha=0.1)
            for label in ax_max.get_xticklabels(which='major'):
                label.set(rotation=30, horizontalalignment='right')
            ax_max.plot([start_uts, final_uts], [0, 0], linestyle="--", color='yellowgreen')
            ax_max.plot([start_uts, final_uts], [100, 100], linestyle="--", color='mediumspringgreen')
            ax_max.plot([start_uts, final_uts], [-100, -100], linestyle="--", color='red')
            ax_max.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%b'))
            ax_max.xaxis.set_major_locator(mdates.MonthLocator(interval=2))
            ax_max.xaxis.set_minor_locator(mdates.MonthLocator(interval=1))
            ax_max.margins(x=0.01)

        ax_overall.set_title(f"{symbol}: {self.coin} trading graph overall best {self.coin} gain thresholds",fontweight="demi", size="xx-large", y=1.025)
        ax_overall.set_ylabel(f"% {self.coin} gain from inital", fontweight="demi", size="xx-large")
        ax_overall.legend(title=f"Top {top_x} strats | trades | SR | %gain", title_fontsize="x-large",
                                        fontsize='large', shadow=True, fancybox=True, bbox_to_anchor=(1.025, 1.025))

        ax_pair.set_title(f"{symbol}: {symbol.split(self.coin)[-1]} trading graph for overall best {self.coin} gain thresholds", fontweight="demi", size="xx-large", y=1.025)
        ax_pair.set_ylabel(f"% {symbol.split(self.coin)[-1]} gain from inital", fontweight="demi", size="xx-large")
        ax_pair.set_xlabel("Time", fontweight="demi", size="x-large")
        ax_pair.legend(title=f"Top {top_x} strats | trades | SR | %gain", title_fontsize="x-large",
                                        fontsize='large', shadow=True, fancybox=True, bbox_to_anchor=(1.02, 1.025))

        ax_max.set_title(f"{symbol}: {self.coin} trading graph for highest max {self.coin} gain thresholds", fontweight="demi", size="xx-large", y=1.025)
        ax_max.set_ylabel(f"% {self.coin} gain from inital", fontweight="demi", size="xx-large")
        ax_max.set_xlabel("Time", fontweight="demi", size="x-large")
        ax_max.legend(title=f"Top {top_x} strats | trades | SR | %gain", title_fontsize="x-large",
                                        fontsize='large', shadow=True, fancybox=True, bbox_to_anchor=(1.02, 1.025))

        plt.tight_layout(pad=2)
        filename_ext += '' if top_x == 20 else f'_top{top_x}'
        plt.savefig(f"{self.graph_path}/trading_simulation/{symbol}/trade_simulation_{symbol}_{filename_ext}.png")


    def graph_signal_against_pa(self, symbol, custom_timeframes, custom_threshold=None, interval='1d'):
        ''''''
        # map signals against real candle PA, however also map a little mark for each max gain after signal before the next signal
        # signals will be background vertical lines, max gains can just be a tiny red dotted line or something

        # Deafult run will make a graph with BEST overall threshold trades superimposed
        # but you can change settings to be BEST max thresholds
        # and you can specify the threshold settings too
        # The default run will use the optimise_threshold function to just find the best threshold
        pass


    def graph_trend(self, symbol, custom_timeframes, custom_threshold=None, interval='1d'):
        pass # TODO make a get_trends_graph, uses candle stick graph of PA, with score as line graph behind it


    def get_trend_stdout(self, symbol, num_scores, interval, custom_timeframes=[], custom_threshold=None):
        '''
        returns a list of entries from the historical scoring data, and will show signals if they crossed given threshold
        '''
        #TODO deprecate, make get_trend_graph instead

        filename_ext = get_filename_extension(custom_timeframes)
        threshold_strat = ''
        if custom_threshold:
            threshold_strat = custom_threshold
            self.compute_historical_score(symbol, custom_timeframes)
        else:
            threshold_strat = self.optimise_signal_threshold(symbol, custom_timeframes)
        bull_threshold, bear_threshold = [int(threshold.split(':')[-1]) for threshold in threshold_strat.split('|')]

        interval_5min_mapping = {'5m':1, '15m':3, '30m':6, '1h':12, '2h':24, '3h':36, '4h':48,
                                 '6h':72, '8h':96, '12h':144, '1d':288, '3d':864, '1w':2016, '1M':8640}
        blocksize = (num_scores * interval_5min_mapping[interval])*46 + 230 # no of bytes to extract from csv
        trend_stdout = []
        with open(f'{self.historical_scoring_path}/{symbol}/historical_scoring_{symbol}_{filename_ext}.csv') as f:
            f.seek(0, os.SEEK_END) # move to eof
            eof = f.tell()
            try:
                f.seek(eof - blocksize)
            except ValueError:
                print('Error: Not enough historical data.')
                return
            data = f.read(blocksize) # load the end of the csv
            print(f'The last {num_scores} many {interval} scores for {coin} are >>>')
            to_skip = -1
            rows_printed = 0
            rows_count = 0
            for row in csv.reader(data.split('\n')[1:]):
                rows_count += 1
                if to_skip > 1 or not row:
                    to_skip -= 1
                    continue
                to_skip = interval_5min_mapping[interval]
                rows_printed += 1
                signal = '___'
                bull_score = int(row[2])
                bear_score = int(row[3])
                if bull_score > bull_threshold and bull_score > bear_score:
                    signal = 'SELL'
                elif bear_score > bear_threshold and bear_score > bull_score:
                    signal = 'BUY'
                trend_stdout.append(f'Price: {row[1]:6}  | Bull: {bull_score} 1h_Bull: {row[6]}  | Bear: {bear_score} 1h_Bear: {row[5]}   | signal: {signal}')
                if rows_printed == num_scores:
                    break
        return trend_stdout

    
    def get_latest_signal_stats(self, symbol, timeframes, custom_threshold=None):
        
        filename_ext = get_filename_extension(timeframes)
        threshold_strat = ''
        if custom_threshold:
            threshold_strat = custom_threshold
            self.compute_historical_score(symbol, timeframes)
        else:
            threshold_strat = self.optimise_signal_threshold(symbol, timeframes)
        bull_threshold, bear_threshold = [int(threshold.split(':')[-1]) for threshold in threshold_strat.split('|')]

        with open(f'{self.historical_scoring_path}/{symbol}/historical_scoring_{symbol}_{filename_ext}.csv') as f:
            f.seek(0, os.SEEK_END) # move to eof
            eof = f.tell()
            blocksize = 25000
            next_block = eof - blocksize
            max_score = int((len(timeframes))*6)
            peak_price = 0
            best_price = [float('inf'), 0] # min, max
            signal = ''
            while next_block > 0:
                f.seek(next_block)
                data = f.read(blocksize).split('\n')[:-1] # load the end of the csv
                data.reverse()
                if next_block == eof - blocksize:
                    latest_row = data[0].split(',')
                next_block -= blocksize
                for row in csv.reader(data):
                    bull_score = float(row[2]) # i.e. massive surge up, hence you want to SELL
                    bear_score = float(row[3]) # i.e. massive surge down, hence you want to BUY
                    best_price[0] = min(best_price[0], float(row[1]))
                    best_price[1] = max(best_price[1], float(row[1]))
                    if bull_score >= bull_threshold and bull_score > bear_score:
                        signal = 'SELL'
                    elif bear_score >= bear_threshold and bear_score > bull_score:
                        signal = 'BUY'
                    if signal:
                        peak_price = float(row[1])
                        alt_action = 'BUY' if signal == 'SELL' else 'SELL'
                        mood = 'BULL' if signal == 'SELL' else 'BEAR'
                        score = bull_score if signal == 'SELL' else bear_score
                        desired_assest = self.coin if signal == 'SELL' else symbol.split(self.coin)[-1]
                        max_gain = (peak_price / best_price[0])*100 - 100 if signal == 'SELL' else (best_price[1] / peak_price)*100 - 100
                        best_gain_price = best_price[0] if signal == 'SELL' else best_price[1]
                        current_gain = (peak_price / float(latest_row[1]))*100 - 100 if signal == 'SELL' else (float(latest_row[1]) / peak_price)*100 - 100                            
                        tf_indexs = list(range(5, len(row) - 1 ,2)) if signal == 'BUY' else list(range(6, len(row) - 1 ,2))
                        tf_scores = [f'{timeframes[i]}: {score}' for i, score in enumerate([row[i] for i in tf_indexs])]
                        uts = int(row[0][:-3])
                        delta_time = int((datetime.now() - datetime.fromtimestamp(uts)).total_seconds() // 3600)
                        date = datetime.fromtimestamp(uts).strftime('%d/%m/%y %a %I:%M %p')
                        change_score = row[5]
                        signal_price = row[1]
                        current_price = latest_row[1]

                        return [symbol, signal, mood, score, change_score, max_score, signal_price, tf_scores, alt_action, 
                            max_gain, desired_assest, best_gain_price, current_gain, current_price, delta_time, date]

    
    @staticmethod
    def score_performance(max_list, change_list, size, absolute_change, current_percent_change):
        '''
        Scoring method. Determines what rank the current price action holds against historical data
        If the performance is greater than the top 75% of price action history, then it can obtain some score.
        Once the price action is strong enough to generate a score, it then can also generate a change_score.
        To even have a change_score of 1, the price action has to be within the top 90% of %change in history.
        Hence, any change score is impressive, and indication that price is very unlikely to maintain this current candle.
        '''

        score, change_score = 0, 0
        #TODO use bisect https://stackoverflow.com/questions/11290767/how-to-find-an-index-at-which-a-new-item-can-be-inserted-into-sorted-list-and-ke
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
        '''
        Returns current amplitude score
        '''

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
        '''
        Returns % change, % amplitude, max % up, max % down of a given candle
        '''

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


    def sell_assest(self):
        '''
        Use only during emergency, sells asset on binance
        '''

        # I am make a seperate file and class called trading bot, where each coin object has their own trading bot object
        # This method will be involved in the literally selling/buying swing trading
        # Makes descisions based on combining fib, bull/bear, history, and horitizonal supports/volumns
        # needs to pass on to bot the following info:
            # coin/symbol, holdings

        # interface with trading_bot class
            

    def view_profits(self):
        pass
        # returns profits for the given coin
        # interface with trading_bot class


    def add_holdings(self):
        # interface with trading_bot class
        pass


    def remove_holdings(self):
        # interface with trading_bot class
        pass


    def view_trade_histroy(self):
        # interface with trading_bot class
        pass
        #returns the trades recorded by the trading bot


if __name__ == "__main__":
    coin = Coin('INJ')
    # coin.compute_historical_score('INJUSDT')
    # # coin.generate_look_ahead_gains("INJUSDT", peak_start_only=True)
    # coin.generate_look_ahead_gains("INJUSDT")
    # coin.generate_retain_score("INJUSDT")
    # # coin.graph_look_ahead_data("INJUSDT")
    # # coin.generate_look_ahead_gains("INJUSDT")
    coin.graph_look_ahead_data("INJUSDT", graph_type="bar")

    # # btc
    # coin.compute_historical_score('INJBTC')
    # coin.generate_look_ahead_gains("INJBTC")
    # coin.generate_retain_score("INJBTC")
    # coin.graph_look_ahead_data("INJBTC")    
    

    # coin.compute_historical_score('INJUSDT', custom_timeframes=['1h', '4h', '1d', '3d', '1w'])
    # coin.generate_look_ahead_gains("INJUSDT", custom_timeframes=['1h', '4h', '1d', '3d', '1w'])
    # coin.generate_retain_score("INJUSDT", custom_timeframes=['1h', '4h', '1d', '3d', '1w'])
    # coin.graph_look_ahead_data("INJUSDT", custom_timeframes=['1h', '4h', '1d', '3d', '1w'])   
    # coin.analyse_peaks('INJUSDT', custom_timeframes=['1h', '4h', '1d', '3d', '1w'])     


    #BTC
    # coin = Coin('BTC')
    # coin.compute_historical_score('BTCUSDT')
    # coin.generate_look_ahead_gains("BTCUSDT")
    # coin.generate_retain_score("BTCUSDT")
    # coin.graph_look_ahead_data("BTCUSDT")  
    pass