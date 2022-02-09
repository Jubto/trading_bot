from threading import Thread, Event, enumerate as list_threads
from get_candles import Coin
from enums import INTERVALS, DEFAULT_TIMEFRAMES, DEFAULT_THRESHOLD
from datetime import datetime
from glob import glob
import subprocess
import time
import json
import csv
import sys
import re
import os

'''
Semantics with examples

__Coin = INJ
__Tradingpair = USDT
__Symbol = INJUSDT
__Timeframe = 5m
__Symbol_timeframe  = INJUSDT_5m

'''

class Notification_server():
    '''
    Start server with 0 or more coin symbols to monitor, for example: 
        <python3 notification_server.py INJ RVN MONA BTC>
    When no arguments entered, server will monitor all coins stored in database, or prompt user if none are stored. 
    Enter 'commands' to view all avaliable server commands  
    '''

    # Server enums
    SERVER_SPEED = 1 # Deafult server tick speed 5 seconds.
    REQUEST_INTERVAL = 60 # Deafult server Binance candle request interval.
    BULL_THRESHOLD = 25 # Deafult thresholds before notification sent. Each user can set their own threshold under their attributes. (eventually implement ML)
    BEAR_THRESHOLD = 25 # Eventually will make both of these dicts with keys as coins, value as threshold.
    MODE_2_REQUEST = 0 # Whenever a user thread requires a new update, this will handle that.
    
    def __init__(self, coins=[]):

        self.tickspeed_handler = Event() # Event object to handle server tick speed. 
        self.server_shutdown = Event() # Event object to handle server shutdown if command 'quit' is entered.
        self.tickspeed_handler.set()
        self.root_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = self.root_path + '/coindata'
        self.script_path = self.root_path + '/notification_scripts'
        self.attribute_path = self.script_path + '/server_attributes'
        if not os.path.exists(self.data_path):
            os.mkdir(self.data_path) # This acts like a database to store all users coins and anaylsis.

        self.monitored_coins = {} # Dict of coins server is currently monitoring - example  {coin:[symbol_timeframe, symbol_timeframe, ...]}
        self.coin_objs = {} # E.g. {'btc': btc_obj, 'rvn': rvn_obj}
        self.server_instruction = {'drop': '', "stdout": 0, 'stdout_detail': 0, 'request_interval': [], 'pause': 0, 'boost': 0, 'score': 0, 'new_user': ''}
        self.message_backlog = [] # List of messages for server_stdout() to process in order. 
        self.server_users = {} # Dict keeping track of server users and their attributes (coins, update_intervals, thresholds, previlages). 
        self.mode_1_messages = {} # Dict to store mode 1 (signal) like messages for server_user thread to read/send.
        self.mode_2_messages = {} # Dict to store mode 2 (update) like messages for server_user thread to read/send.
        self.outgoing_messages = {} # Dict of messages from all users which get seqentially delivered to each respective user email
        self.postfix_init = False
        self.server_owner_gmail = ''

        self.server_welcome()
        if coins:
            self.monitor_all_coins(coins=coins) # Monitor all coins given as arguments if valid.
        else:
            self.monitor_all_coins() # Monitor all coins stored in local storage, if no coins, then prompt user input. 
   
        Thread(target=self.server_tick_speed, name='server_tick', daemon=True).start() # Global server tick speed.
        Thread(target=self.request_interval_handler, name='server_intervals', daemon=True).start() # Global server timer for sending candle requests.
        Thread(target=self.server_stdout, name='server_stdout', daemon=True).start() # Handles smooth server stdout. 
        Thread(target=self.server_user_stdinput, name='server_input', daemon=True).start() # Ready server to intake user inputs


    def server_welcome(self):
        '''Server welcome'''

        print(f"Server has been initiated!")
        print(f"Server is ready to intake commands. Type 'commands' to view avaliable commands:")
        print(f"Enter command 'notify' to commence server gmail notification service")
        print(f"Enter command 'post' to receive your chosen coin scores and summaries\n")


    def server_commands(self):
        '''Prints description of each server command'''

        print(f"\nList of commands:")
        print('='*130)
        print(f"<commands>: Returns list of commands with description.")
        print(f"<monitor>: Allows user to add new multiple new coins, tradingpairs and timeframes to monitor.")
        print(f"<monitoring>: Server returns all coins it is currently monitoring.")
        print(f"<all>: Server will start monitoring all coins, tradingpairs and timeframes stored in the local database.")
        print(f"<drop>: Allows user to drop specific coins, tradingpairs and timeframes from monitoring or database.")
        print(f"<score>: Server will stdout the latest coin scores for all monitored coins.")
        print(f"<trend COIN X INTERVAL>: Enter which coin and X many past score reads at a given INTERVAL you want to see.")
        print(f"<graph COIN TYPE>: Enter which coin you want to see a summary of, either bar or line type.")
        print(f"<stdout>: Toggles server stdout between periodic and OFF - server starts off in OFF state.")
        print(f"<server_speed>: Allows user to modify server tick speed.")
        print(f"<request_interval>: Allows user to modify server communication interval with Binance for candle retreival (deafult 1 minute).")
        print(f"<notify>: Starts up the server notification mailing service. If first time, this will start the initialisation process.")
        print(f"<quit>: Shuts down server activity.")
        print('='*130 + '\n')


    def server_user_stdinput(self):
        '''Thread handles user inputs'''

        while True:
            user_input = input() # Pauses thread until user input.
            if user_input == 'commands':
                self.server_commands()
            elif user_input == 'quit':
                self.shutdown_server()
            elif user_input == 'score':
                self.server_instruction['score'] = 1
            elif user_input == 'trend':
                Thread(target=self.get_trend(), name='get_trends', daemon=True).start()
            elif user_input == 'retain':
                Thread(target=self.get_retain_scoring(), name='get_retain', daemon=True).start()
            elif user_input == 'graph1':
                Thread(target=self.get_look_ahead_graph(), name='get_look_ahead_graph', daemon=True).start()
            elif user_input == 'signals':
                self.get_latest_signals()
            elif user_input == 'stdout':
                self.toggle_stdout()
            elif user_input == 'stdout_detail':
                self.toggle_stdout_detail()                    
            elif user_input == 'request_interval':
                self.update_timers('request_interval')
            elif user_input == 'server_speed':
                self.update_timers('server_speed')
            elif user_input == 'monitoring':
                self.current_monitoring()
            elif user_input == 'monitor':
                self.input_monitor_new()
            elif user_input == 'all':
                self.monitor_all_coins()
            elif user_input == 'drop':
                self.input_drop_coin()
            elif user_input == 'notify':
                self.notification_init()
            elif user_input == 'debug':
                print(f"Server instruction settings are:\n{self.server_instruction}")
                self.debug()
            elif user_input == '':
                pass
            else:
                print(f"{user_input} is an invalid server command.")
                print(f"Enter 'commands' to view all avaliable commands.")


    def add_to_monitoring(self, to_monitor={}):
        '''Handles validating and adding items into the server monitoring dictionary monitored_coins'''
        
        # This section handles determining whether coin is valid with Binance, if so it will add to server monitoring.
        added_coins = set()
        for coin in to_monitor:
            for tradingpair in to_monitor[coin]:
                coin_obj = Coin(coin) # Create new coin object to monitor. 
                symbol_timeframes = coin_obj.get_symbol_timeframes() # Used to determine whether coin exists in local storage or not.
                timeframes = [interval.split('_')[-1] for interval in to_monitor[coin][tradingpair]]

                if len(symbol_timeframes) == 0:  
                    # This means coin had no local storage
                    if tradingpair != 'NA':
                        if coin_obj.get_candles(tradingpair=tradingpair, intervals=timeframes):
                            pass # Binance succesfully returned candles for coin-tradingpair/timeframe.
                        else:
                            print(f"{coin}{tradingpair} is not avaliable on Binance.")
                            continue # Binance rejected request.
                    elif coin_obj.get_candles(tradingpair='USDT', intervals=DEFAULT_TIMEFRAMES):
                        tradingpair = 'USDT' # No tradingpair specified so deafult tradingpair assigned to coin.
                    else:
                        print(f"{coin} is not avaliable on Binance.")
                        continue # This means coin provided is invalid for Binance.
                elif tradingpair != 'NA':
                    # Server has local storage of coin.
                    if coin_obj.get_candles(tradingpair=tradingpair, intervals=timeframes):
                        pass # This either added a new tradingpair or updated the existing stored one.
                    else:
                        print(f"{coin}{tradingpair} is not avaliable on Binance.")
                        continue # This means newly entered tradingpair is invalid for Binance. 
                print(f"Server will start monitoring {coin}{tradingpair}.\n") if tradingpair != 'NA' else print(f"Server will start monitoring {coin}.\n")
                added_coins.add(coin)

                # Add coin to server monitoring list
                if coin not in self.monitored_coins.keys():
                    self.monitored_coins[coin] = []
                    self.coin_objs[coin] = coin_obj
                symbol_timeframes = coin_obj.get_symbol_timeframes() # New coin csv files may have been added. 
                for symbol_timeframe in symbol_timeframes:
                    symbol = symbol_timeframe.split('_')[0].upper()
                    if tradingpair == 'NA' or symbol == coin_obj.coin + tradingpair:
                        if symbol_timeframe not in self.monitored_coins[coin]:
                            self.monitored_coins[coin].append(symbol_timeframe) # Append only tradingpair/timeframe which server will actively monitoring.
                self.monitored_coins[coin].sort()
        return added_coins # Return set of succesfully added coins. 


    def monitor_coin(self, coin):
        '''Thread starts the monitoring and score calculation of given coin. Handles external signals to drop activity'''

        coin_obj = self.coin_objs[coin]
        previous_bull_score = 0
        previous_bear_score = 0
        while True:
            self.tickspeed_handler.wait() # Releases every server tick.

            # Check to see whether coin drop instruction is activate.
            if self.server_instruction['drop'] and coin in self.server_instruction['drop']:    
                item_to_drop = self.server_instruction['drop']
                self.server_instruction['drop'] = ''
                if re.search(item_to_drop.rstrip('1')[1:], str(self.monitored_coins[coin])):
                    if '1' == item_to_drop[-1]:
                        item_to_drop = item_to_drop.rstrip('1')
                        if '1' == item_to_drop[0]:
                            coin_obj.remove_coin() # Remove from database. 
                        elif '2' == item_to_drop[0]:
                            coin_obj.remove_symbol(item_to_drop[1:]) # Remove from database. 
                        else:
                            coin_obj.remove_timeframe(item_to_drop[1:]) # Remove from database. 
                    clone_monitored_coins = self.monitored_coins[coin].copy()
                    for pair in clone_monitored_coins:
                        if item_to_drop[1:] == pair or item_to_drop[1:] in pair:
                            self.monitored_coins[coin].remove(pair)
                    print(f"The following has been dropped: {item_to_drop[1:]}")
                    if '1' == item_to_drop[0] or len(self.monitored_coins[coin]) == 0:
                        self.monitored_coins.pop(coin)
                        return 0 # Drop this coin thread.

            # Check to see whether request timer has activated.
            if coin in self.server_instruction['request_interval']:
                self.server_instruction['request_interval'].remove(coin) # Let's request_interval thread know which coins have started scoring.
                symbol_timeframes = self.monitored_coins[coin] # Only monitor specified tradingpairs.
                coin_score = coin_obj.current_score(to_monitor=symbol_timeframes) # Retreve coin score and analysis summary. 
                bull_score = coin_score[0][1]
                bear_score = coin_score[0][2]

                if re.search(coin, str(self.server_instruction['drop'])):
                    continue # If user just entered coin to drop when score already processed.
                if len(self.message_backlog) < len(self.monitored_coins):
                    self.message_backlog.append(coin_score) # Send data to stdout method. 
                try:
                    if self.mode_1_messages[coin] and not self.server_instruction['new_user']:
                        self.mode_1_messages.pop(coin) # To prevent recuring posting of mode1 type messages.
                except KeyError:
                    pass

                if bull_score > previous_bull_score or bear_score > previous_bear_score:
                    if coin_score[0][1] >= self.BULL_THRESHOLD:
                        coin_obj.generate_result_files(mode='signal') # Generate/replace signal graph/csv files in server_mail/outgoing for users to send
                        self.mode_1_messages[coin] = f"BULL_{self.BULL_THRESHOLD}" # Send message to all users subscribed to this coin
                    elif coin_score[0][2] >= self.BEAR_THRESHOLD:
                        coin_obj.generate_result_files(mode='signal')
                        self.mode_1_messages[coin] = f"BEAR_{self.BEAR_THRESHOLD}" 

                if self.MODE_2_REQUEST:
                    coin_obj.generate_result_files(mode='update')
                    self.MODE_2_REQUEST -= 1 # Once the value becomes zero, any user thread which is ready will send a mode 2 email.


    def current_monitoring(self, stored=False):
        '''Returns list of coins, trading pairs and timeframes server is currently monitoring'''

        coins_dict = {}
        if stored:
            for coin_path in glob(self.data_path + '/*'):
                coin = coin_path.split('/')[-1]
                coins_dict[coin] = [tradingpair.split('/')[-1][:-4] for tradingpair in glob(f"{coin_path}/{coin}*")]
        else:
            coins_dict = self.monitored_coins.copy()

        if coins_dict:
            if stored:
                print(f"Server has the following pairs in the database:")
            else:
                print(f"Server is currently monitoring:")

            for coin in coins_dict:
                print(f"coin {coin}:")
                tradingpairs = {}
                for symbol_timeframe in coins_dict[coin]:
                    tradingpair = symbol_timeframe.split('_')[0]
                    timeframe = symbol_timeframe.split('_')[-1]
                    try:
                        tradingpairs[tradingpair].append(timeframe)
                    except KeyError:
                        tradingpairs[tradingpair] = [timeframe]
                for tradingpair in tradingpairs:
                    print(tradingpair, ':', [timeframe for timeframe in sorted(tradingpairs[tradingpair], key= lambda i : INTERVALS.index(i))])
            print('')
            
        else:
            print(f"Server has no stored or monitored coins. Enter command 'monitor' to add new coins.")


    def monitor_all_coins(self, coins=None):
        '''Hanndles server coin monitoring initiation and 'all' command'''

        if not coins:
            paths = glob(self.data_path + '/*') 
            if len(paths) == 0:
                self.input_monitor_new() # If no coins are found in coindata directory, prompt user to enter coin.
            coins = [path.split('/')[-1] for path in paths] # Clean path to get only the directory name (i.e. coin).

        coins_to_add = set()
        coins_to_add = coins_to_add.union(self.add_to_monitoring(to_monitor= {coin.upper():{"NA":[]} for coin in coins})) # Validate each coin entered, add to monitoring
        self.add_new_coins(coins_to_add) # Start thread for each coin if one doesn't already exist.


    def get_trend(self):
        '''Returns the last x many score entries for a given interval for a given coin'''
        # TODO make a get_trends_graph, uses candle stick graph of PA, with score as line graph behind it

        query = input('Enter a symbol (coin_pair), number of past scores, and the interval you wish to see, E.g. `BTC_USDT 50 1h` >>> ').split()
        try:
            symbol, num_scores, interval = query
            coin = symbol.split('_')[0].upper()
            num_scores = int(num_scores)
            paths = glob(self.data_path + '/*')
            coins = [path.split('/')[-1] for path in paths]
            if len(query) != 3:
                print('Invalid number of arguments\n')
                return
            if coin not in coins:
                print(f'{coin} is not currently being monitored by this server. Please add it using `monitor` command first.\n')
                return
            if interval not in INTERVALS or '_' not in symbol:
                raise ValueError
            symbol = symbol.replace('_', '').upper()
            if symbol not in ''.join(self.monitored_coins[coin]):
                print(f'{symbol} is not currently being monitored by this server. Please add it using `monitor` command first.\n')
                return
        except ValueError:
            print('Invalid query, please enter a symbol (coin_pair), number of past scores, and an interval E.g.`trend BTC 50 1h`\n')
            return
        
        print(f'Gathering latest historical score data for {coin}...')
        interval_5min_mapping = {'5m':1, '15m':3, '30m':6, '1h':12, '2h':24, '3h':36, '4h':48, '6h':72, '8h':96, '12h':144, '1d':288, '3d':864, '1w':2016, '1M':8640}
        blocksize = (num_scores * interval_5min_mapping[interval])*46 + 230 # no of bytes to extract from csv
        self.coin_objs[coin].compute_historical_score(symbol)
        # TODO remember to set the stdout to OFF
        with open(self.data_path + f'/{coin.upper()}/historical/{symbol}_historical_scoring.csv') as f: #TODO again not happy, make into coin method
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
                print(f'Price: {row[1]:6}  | Bull: {row[2]} 1h_Bull: {row[6]}  | Bear: {row[3]} 1h_Bear: {row[5]}   | signal: {row[-1]}')
                if rows_printed == num_scores:
                    break
            print('\n')


    def get_retain_scoring(self):
        '''Generates a retain score file for the given coin + pair'''
        #TODO allow custom timeframes
        query = input('Enter a symbol (coin_pair) `BTC_USDT` >>> ')
        try:
            coin = query.split('_')[0].upper()
            symbol = query.replace('_', '').upper()
            paths = glob(self.data_path + '/*')
            coins = [path.split('/')[-1] for path in paths]
            if len(query.split()) != 1:
                print('Invalid number of arguments\n')
                return
            if coin not in coins:
                print(f'{coin} is not currently being monitored by this server. Please add it using `monitor` command first.\n')
                return
            if symbol not in ''.join(self.monitored_coins[coin]):
                print(f'{symbol} is not currently being monitored by this server. Please add it using `monitor` command first.\n')
                return
        except AttributeError:
            print('Invalid query, please enter a symbol (coin_pair) E.g. `retain BTC_USDT`\n')
            return
        
        self.coin_objs[coin].generate_retain_score(symbol)
        print(f'Retain score summary for {symbol} has completed. \
            See file located at: {self.data_path}/analysis/retain_scoring/{symbol}/')


    def get_look_ahead_graph(self):
        '''Generates a retain score graph for the given coin + pair'''
        #TODO allow custom timeframes
        query = input('Enter a symbol (coin_pair) `BTC_USDT` >>> ')
        try:
            coin = query.split('_')[0].upper()
            symbol = query.replace('_', '').upper()
            paths = glob(self.data_path + '/*')
            coins = [path.split('/')[-1] for path in paths]
            if len(query.split()) != 1:
                print('Invalid number of arguments\n')
                return
            if coin not in coins:
                print(f'{coin} is not currently being monitored by this server. Please add it using `monitor` command first.\n')
                return
            if symbol not in ''.join(self.monitored_coins[coin]):
                print(f'{symbol} is not currently being monitored by this server. Please add it using `monitor` command first.\n')
                return
        except AttributeError:
            print('Invalid query, please enter a symbol (coin_pair) E.g. `retain BTC_USDT`\n')
            return
        
        self.coin_objs[coin].graph_look_ahead_data(symbol)
        print(f'Graph summary for {symbol} has completed. \
            See file located at: {self.data_path}/analysis/graphs/look_aheads/{symbol}/')

    
    def get_trading_simulation_graph(self):
        pass

    
    def get_pa_signal_graph(self):
        pass


    def get_latest_signals(self):
        '''Returns the date of the latest peak, how many days ago, the price it was, the score, the timeframe scores, the max gains since then, the current gains'''

        #TODO I don't like how this accesses the coindata files, make into coin method
        blocksize = 25000
        monitored_symbols = set([f'{coin}_{symbol_tf.split("_")[0]}' for coin, symbol_tfs in self.monitored_coins.items() for symbol_tf in symbol_tfs])
        for coin_symbol in monitored_symbols:
            coin, symbol = coin_symbol.split('_')
            trading_pair = symbol.split(coin)[-1]
            self.coin_objs[coin].compute_historical_score(symbol)
            with open(f'{self.data_path}/analysis/historical_scoring/{symbol}/.csv') as f:
                header_chunk = f.read(500).split('\n')
                header_len = len(header_chunk[0].split(','))
                timeframes = [col.split('_')[1] for col in header_chunk[0].split(',')[5:-1:2]]
                threshold = int(((len(header_chunk[0].split(',')) - 6)*3)*0.5)
                max_score = int((len(header_chunk[0].split(',')) - 6)*3)
                f.seek(0, os.SEEK_END) # move to eof
                eof = f.tell()
                next_block = eof - blocksize
                peak_buffer, peak, peak_price = 0, 0, 0
                best_price = [float('inf'), 0] # min, max
                best_price_snapshot = []
                peak_row = []
                while next_block > 0:
                    f.seek(next_block)
                    data = f.read(blocksize).split('\n') # load the end of the csv
                    data.reverse()
                    if next_block == eof - blocksize:
                        latest_row = data[1].split(',')
                    next_block -= blocksize
                    for row in csv.reader(data):
                        if len(row) != header_len:
                            continue
                        peak_buffer -= 1
                        score = max(int(row[2]), int(row[3]))
                        best_price[0] = min(best_price[0], float(row[1]))
                        best_price[1] = max(best_price[1], float(row[1]))
                        if score >= threshold and score > peak:
                            peak = score
                            peak_price = float(row[1])
                            best_price_snapshot = best_price.copy()
                            peak_row = row
                            peak_buffer = 12
                            continue
                        elif peak and not peak_buffer:
                            signal = 'SELL' if int(peak_row[2]) > int(peak_row[3]) else 'BUY'
                            alt_action = 'BUY' if signal == 'SELL' else 'SELL'
                            desired_assest = coin if signal == 'SELL' else trading_pair
                            # max_gain = 100 - (best_price_snapshot[0] / peak_price)*100 if signal == 'SELL' else (best_price_snapshot[1] / peak_price)*100 - 100
                            # best_gain_price = best_price_snapshot[0] if signal == 'SELL' else best_price_snapshot[1]
                            # current_gain = 100 - (float(latest_row[1]) / peak_price)*100 if signal == 'SELL' else (float(latest_row[1]) / peak_price)*100 - 100
                            # The gain you get from responding to the latest signal (i.e. if signal was SELL, then the gain you make from BUYing now)
                            max_gain = (peak_price / best_price_snapshot[0])*100 - 100 if signal == 'SELL' else (best_price_snapshot[1] / peak_price)*100 - 100
                            best_gain_price = best_price_snapshot[0] if signal == 'SELL' else best_price_snapshot[1]
                            current_gain = (peak_price / float(latest_row[1]))*100 - 100 if signal == 'SELL' else (float(latest_row[1]) / peak_price)*100 - 100                            
                            tf_indexs = list(range(5, len(peak_row) - 1 ,2)) if signal == 'BUY' else list(range(6, len(peak_row) - 1 ,2))
                            tf_scores = [f'{timeframes[i]}: {score}' for i, score in enumerate([peak_row[i] for i in tf_indexs])]
                            uts = int(peak_row[0][:-3])
                            delta = int((datetime.now() - datetime.fromtimestamp(uts)).total_seconds() // 3600)
                            date = datetime.fromtimestamp(uts).strftime('%d/%m/%y %a %I:%M %p')
                            print(f'\n===================================== Signals for {symbol} =====================================')
                            print(f'{signal} signal {delta} hours ago at {date}')
                            print(f'Price was: {peak_row[1]}, score: {peak}/{max_score}, change score: {peak_row[4]}/{max_score}, timeframe scores: {", ".join(tf_scores)}')
                            print(f'Max gain from {alt_action} would be {max_gain:.2f}% of {desired_assest} at ${best_gain_price}, gain now from {alt_action} is {current_gain:.2f}% of {desired_assest} at ${latest_row[1]}\n')
                            next_block = -1000
                            break


    def request_interval_handler(self):
        '''Thread used to synchronise all monitor_coin method threads'''

        while True:
            threads = [str(thread).split(',')[0].split('(')[1] for thread in list_threads()] # List all activate threads.
            coins = [coin for coin in threads if coin in self.monitored_coins] # List only active coin threads.
            self.server_instruction['request_interval'] = coins # Change global variable to be list of coins ready to have scores checked.
            Thread(target=self.boost_speed, args=(0.1,), daemon=True).start() # Temporarily boost server speed for faster processing. 
            while self.server_instruction['request_interval'] != []:
                self.tickspeed_handler.wait() # Keep checking every server tick whether all coin threads have starting scoring.
            self.server_instruction['boost'] = 0 # Turn off boost thread.
            time.sleep(self.REQUEST_INTERVAL) # Releases every request_interval time. 


    def server_tick_speed(self):
        '''Thread server speed, every SERVER_SPEED time elapsed will release the tickspeed_handler object'''
        
        while True:
            self.tickspeed_handler.set() # Releases the event object for all active threads from waiting. 
            self.tickspeed_handler.wait() # Just a small measure to ensure all server .wait() methods are reached.
            self.tickspeed_handler.clear() # Locks server wide event object. 
            time.sleep(self.SERVER_SPEED)


    def server_stdout(self):
        '''Thread handles server stdout (so that thread stdouts don't overlap)'''

        messages = [] # list of score_dict
        while True:
            self.tickspeed_handler.wait() # Releases every server tick.
            if len(self.message_backlog) >= len(self.monitored_coins):
                messages = self.message_backlog.copy()
                self.message_backlog = [] # Empty message log.
                if self.server_instruction['stdout']:
                    self.server_instruction['score'] = 1 # Note, post can be turned on via user input also. 

            if self.server_instruction['score'] and messages:
                while True:
                    if self.server_instruction['pause']:
                        time.sleep(1)
                        continue
                    break
                print(datetime.now().strftime('%I:%M %p'))
                for message in messages:
                    if message[-1] == "coin_score":
                        for symbol_summary in message[:-1]:
                            max_score = len(symbol_summary[-1]) * 6
                            if self.server_instruction['stdout_detail']:
                                print('\n\n' + '='*130)
                                print(f"\nCoin pair {symbol_summary[0]} monitoring update:")
                                print(f"Current price: {symbol_summary[-2]}")   
                                print(f"Bull score: {symbol_summary[1]} out of {max_score}, change score: {symbol_summary[3]} out of {max_score}")
                                print(f"Bear score: {symbol_summary[2]} out of {max_score}, change score: {symbol_summary[4]} out of {max_score}")
                                print(f"Overview:")
                                print(json.dumps(symbol_summary[-1], indent=4))
                            else:
                                mood = 'BULL' if symbol_summary[1] > symbol_summary[2] else 'BEAR'
                                score = symbol_summary[1] if symbol_summary[1] > symbol_summary[2] else symbol_summary[2]
                                change = symbol_summary[3] if symbol_summary[3] > symbol_summary[4] else symbol_summary[4]
                                print(f'Coin: {symbol_summary[0]}, price: {symbol_summary[-2]}, {mood}: {score}/{max_score}, change: {change} signal: {symbol_summary[5]}')
                        if self.server_instruction['stdout_detail']:
                            print('='*130 + '\n\n')
                self.server_instruction['score'] = 0
                print()


    def toggle_stdout(self):
        '''Toggles server stdout between periodic and prompt only'''

        if self.server_instruction['stdout'] == 1:
            print('Server stdout has been toggled OFF.')
            self.server_instruction['stdout'] = 0
        else:
            detail = 'HIGH' if self.server_instruction['stdout_detail'] else 'LOW'
            print(f'Server stdout has been toggled ON. Stdout detail is {detail}.')
            self.server_instruction['stdout'] = 1


    def toggle_stdout_detail(self):
        '''Toggles detail of server stdout'''

        if self.server_instruction['stdout_detail'] == 1:
            print('Server stdout detail has been toggled to LOW.')
            self.server_instruction['stdout_detail'] = 0
        else:
            print('Server stdout detail has been toggled to HIGH.')
            self.server_instruction['stdout_detail'] = 1

    
    def update_timers(self, timer):
        '''Handles updating server clocks'''

        words = []
        if timer == 'request_interval':
            words.extend([' (minute)', 'request_interval'])
        elif timer == 'server_speed':
            words.extend([' (second)', 'tick speed'])

        self.server_instruction['pause'] = 1
        user_input = input(f"Please input a positive integer{words[0]} for new server {words[1]}: ")
        self.server_instruction['pause'] = 0
        try:
            user_input = int(user_input)
            if user_input > 0:
                print(f"Server {words[1]} updated to {user_input}{words[0]}.") 
                if timer == 'request_interval':
                    self.REQUEST_INTERVAL = user_input * 60
                elif timer == 'server_speed':
                    self.SERVER_SPEED = user_input
                return 1
        except ValueError:
            pass
        print(f"{user_input} is an invalid entry. Please input a positive integer.")


    def boost_speed(self, boost):
        '''Thread which toggles server speed from normal to responsive'''

        original_SERVER_SPEED = self.SERVER_SPEED
        self.SERVER_SPEED = boost
        self.server_instruction['boost'] = boost
        while self.server_instruction['boost']:
            time.sleep(boost)
        self.SERVER_SPEED = original_SERVER_SPEED

    
    def input_monitor_new(self):
        '''Handles user input for specifying multiple new coins, trading pairs or timeframes to monitor by the server'''

        input_coin_dict = {}

        self.server_instruction['pause'] = 1 # Stops all server stdout for cleaner user interaction.
        self.current_monitoring()
        self.current_monitoring(stored=True)
        print('='*10 + 'INSTRUCTIONS' + '='*10)
        print('>>> If multiple, seperate by spaces')
        print('>>> Enter coin(s) to monitor, choose their respective tradingpair(s) and Optionally list their timeframe(s)')
        print(f">>> If no tradingpairs are entered, deafult timeframes will be used: {DEFAULT_TIMEFRAMES}")
           
        while True:
            coins = str(input('Input coins: ')).upper() # TODO Make this also handle mail requests 
            if len(coins) == 0:
                continue
            if self.re_search(coins):
                continue
            break
        for coin in coins.split(' '):
            if coin == '':
                continue
            input_coin_dict[coin] = {} # Dictionary for tradingpairs.

        for coin in input_coin_dict:
            while True:
                tradingpairs = str(input(f"Input {coin} trading pairs: ")).upper() 
                if self.re_search(tradingpairs):
                    continue
                break
            tradingpairs = tradingpairs.split(' ')
            for tradingpair in tradingpairs:
                if tradingpair == '':
                    continue
                input_coin_dict[coin][tradingpair] = [] # List for timeframes of each tradingpair.
            for tradingpair in input_coin_dict[coin]:
                symbol = coin + tradingpair
                try:
                    for symbol_timeframe in self.monitored_coins[coin]:
                        if symbol == symbol_timeframe.split('_')[0]:
                            input_coin_dict[coin][tradingpair].append(symbol_timeframe.split('_')[1]) # Add all monitored timeframes for a given tradingpair.
                except KeyError:
                    pass # Means server is not monitoring coin.

                if input_coin_dict[coin][tradingpair]:
                    # This means coin is currently being monitored by server. User can add aditional trading pairs or timeframes.
                    print(f"Server currently monitoring {coin + tradingpair} with timeframes: {input_coin_dict[coin][tradingpair]}")
                else:
                    # This means coin entered is currently not being monitored by server (although it could be in the database). 
                    inspect_coin = Coin(coin) 
                    stored_timeframes = [symbol_tf for symbol_tf in inspect_coin.get_symbol_timeframes() if symbol in symbol_tf]
                    if stored_timeframes:
                        # This means server is not currently monitoring this tradingpair, however has its timeframes stored in database.
                        print(f"Server will start monitoring {coin + tradingpair} with stored timeframes: {stored_timeframes}")   
                        input_coin_dict[coin][tradingpair] = stored_timeframes   
                    else:
                        # This means server does not have any timeframes of this coin/trading pair stored. Deafult timeframes will be monitored.
                        print(f"Server will start monitoring {coin + tradingpair} with deafult timeframes: {DEFAULT_TIMEFRAMES}")
                        input_coin_dict[coin][tradingpair] = DEFAULT_TIMEFRAMES.copy()

                while True:
                    timeframes = input('OPTIONAL: Input additional timeframes: ') # White spaces will be handled in Coin.get_candles(). 
                    if self.re_search(timeframes):
                        continue
                    input_coin_dict[coin][tradingpair].extend(timeframes.split(' ')) # Add any additional timeframes on top of current ones. 
                    break
        self.server_instruction['pause'] = 0 # Unpause server stdout.
        added_coins = self.add_to_monitoring(to_monitor=input_coin_dict) # Verify all user entries and add them to monitoring.
        Thread(target=self.add_new_coins, args=(added_coins,), daemon=True).start() # Input all successful entries.


    def add_new_coins(self, added_coins):
        '''Handles creating new coin threads if they are currently not being monitored by server'''

        for coin in added_coins:
            if not [thread for thread in list_threads() if str(thread).split(',')[0].split('(')[1] == coin]:
                # Means server is not currently monitoring this coin, so start new thread. 
                Thread(target=self.monitor_coin, name=coin, args=(coin,), daemon=True).start()

    
    def input_drop_coin(self):
        '''Handles user input for dropping a coin, tradingpair or timeframe from being monitored and removes from database if requested'''

        input_coin_dict = {}
        to_drop = set()
        
        self.server_instruction['pause'] = 1 # Stops all server stdout for cleaner user interaction.
        self.current_monitoring()
        self.current_monitoring(stored=True)
        print('Enter a coins, coins/tradingpairs, or coins/tradingpairs/timeframes to drop in the list above, appending "-drop"s')
        print('='*10 + 'INSTRUCTIONS' + '='*10)
        print('>>> If multiple, seperate by spaces')
        print('>>> To drop all related pairs of a given entry, append "-drop" (e.g. INJ-drop drops all INJ pairs, INJBTC-drop drops all INJBTC pairs)')
        print('>>> To drop given entry from server database aswell, append "1" to "-drop" (e.g. INJ-drop1, INJBTC-drop1, RVNUSDT_6h1)')
        while True:
            coins = str(input('Input coins: ')).upper()
            if len(coins) == 0:
                continue
            if self.re_search(coins):
                continue
            break
        for coin in coins.split(' '):
            if coin == '':
                continue
            input_coin_dict[coin] = [] # List for tradingpairs.

        for coin in input_coin_dict:
            if '-DROP' in coin:
                to_drop.add(coin)
                continue # Skip rest of user input interaction. 
            while True:
                tradingpairs = str(input(f"Input {coin} trading pairs: ")).upper() 
                if self.re_search(tradingpairs):
                    continue
                tradingpairs = tradingpairs.split(' ')
                for tradingpair in tradingpairs:
                    if tradingpair == '':
                        continue
                    if '-DROP' in tradingpair:
                        to_drop.add(coin + '_' + tradingpair)
                        continue # Skip rest of user input interaction. 
                    input_coin_dict[coin].append(tradingpair) 
                break

            for tradingpair in input_coin_dict[coin]:
                while True:
                    timeframes = str(input(f"Input {coin + tradingpair} timeframes: "))
                    if self.re_search(timeframes):
                        continue
                    if not re.search('[^ ]', timeframes):
                        to_drop.add(coin + '_' + tradingpair) # This means the user just entered a white space.
                    for timeframe in timeframes.split(' '):
                        timeframe = timeframe.replace('-drop', '') # Incase user appended -drop, which is not needed.
                        if timeframe == '' or len(timeframe) > 4 or timeframe[-1] in '023456789':
                            continue # Remove impossible entries immediately.
                        if timeframe == '1m':
                            timeframe = '1M' # 1M month is the only timeframe with uppercase. 1m is for 1 minute however that should never be used. 
                        to_drop.add(coin + '_' + tradingpair + '_@' + timeframe)  
                    break
        Thread(target=self.drop_coins, args=(to_drop,), daemon=True).start()
        self.server_instruction['pause'] = 0 # Unpause server stdout.

    def drop_coins(self, to_drop):
        '''Handles removing given coin/tradingpair/timeframe from Server monitoring or database'''

        Thread(target=self.boost_speed, args=(0.5,), daemon=True).start() # Temporarily boost server speed for faster processing. 
        print(f'to_drop is: {to_drop}')
        for item in to_drop:
            item = item.replace('-DROP', '')
            item = item.split('_')
            if len(item) == 1:
                self.server_instruction['drop'] = '1' + item[0]
                while self.server_instruction['drop']:
                    self.tickspeed_handler.wait()
            elif len(item) == 2:
                self.server_instruction['drop'] = '2' + item[0] + item[1]
                print(f'to dorp is: {self.server_instruction["drop"]}')
                while self.server_instruction['drop']:
                    self.tickspeed_handler.wait()
            else:
                self.server_instruction['drop'] = '3' + item[0] + item[1] + item[2].replace('@', '_')
                while self.server_instruction['drop']:
                    self.tickspeed_handler.wait()
        self.server_instruction['boost'] = 0 # Turn off boost thread.

 
    @staticmethod
    def re_search(string):
        '''Performs search for invalid symbols'''
        if re.search('[,.|!~`@#$%^&*():;/_=+\[\]\{\}]', string): # TODO just do the inverse, list chars which are allowed only
            print(f"Invalid characters used in {string}.")
            return 1
        if re.search('-', string):
            if not re.search('-drop', string, re.IGNORECASE):
                print(f"Invalid characters used in {string}.")
                return 1


    def server_user(self, gmail, owner=False):
        '''Creates user. Each thread will handles one user. Each thread can create two modes of messages to be sent to the user via email.

        Mode 0 are periodic update messages (which can be toggled off). These messages contain score, metrics, summaries and graphs.

        Mode 1 are signalling messages, when one of the users coins have passed a certain threshold.

        Each user can tune into or drop coins to receive mail from relative to them, but also send requests to the server to monitor brand new ones
        
        '''
        Previous_scores = {}
        username = gmail.split('@')[0]
        if owner:
            coins = list(self.monitored_coins.keys())
            self.server_users[gmail] = {'username':username, 'gmail':gmail, 'privilege': 'admin', 'coins':coins, 'threshold':'ML', 'update_interval': 1}
        else:
            self.server_users[gmail] = {'username':username, 'gmail':gmail, 'privilege': 'user', 'coins':[], 'threshold':'ML', 'update_interval': 1}
        for coin in self.server_users[gmail]['coins']:
            Previous_scores[coin] = 0 

        Thread(target=self.server_user_mode_2_message_handler, name=f"server_user_message_handler_{username}", args=(self.server_users[gmail],), daemon=True).start()

        while True:
            if self.mode_1_messages: # Checks for any signals (due to a coin passing their threshold) - Note, these messages get cleared elsewhere above.
                coins = self.mode_1_messages.copy()
                for coin in coins:
                    score = coins[coin].split('_')[-1] 
                    mood = coins[coin].split('_')[0]
                    user_thresold = self.server_users[gmail]['threshold']
                    if coin in self.server_users[gmail]['coins'] and (user_thresold == 'ML' or score >= user_thresold):
                        if score < Previous_scores[coin]:
                            continue 
                        subject = f"SIGNAL ALERT: {coin} passed {mood}ish threshold!"
                        details = (f"{subject} SCORE: {score}#These events are rare and usually a good time to perform a swing trade.#"
                                    'The summary excel and historical score vs performance graphs have been attached to assist in your descision.')
                        files = ','.join(glob(f"{self.root_path}/server_mail/outgoing/{coin}_SIGNAL*"))
                        message = {'user':gmail, 'title':subject, 'details':details, 'files':files}
                        self.outgoing_messages[username] = message # Send mode1 email.
            
            try:
                message = self.mode_2_messages[gmail]
                self.outgoing_messages[gmail] = message # send mode2 email.
                self.mode_2_messages.pop(gmail)
            except KeyError:
                pass # After each users specified interval passes, their new mode2 message will become avaliable.
            
            self.tickspeed_handler.wait()


    def server_user_mode_2_message_handler(self, user_dict={}):
        '''Each user has a thread of this which waits for their specific update_interval before sending a mode 2 message'''

        # Thread will send mode 2 message upon creation, and then wait for update_interval time to send next one. 
        while True:
            self.MODE_2_REQUEST = len(self.monitored_coins)
            while self.MODE_2_REQUEST:
                self.tickspeed_handler.wait()
            update_message_timer = user_dict['update_interval'] * 3600 # seconds.
            gmail = user_dict['gmail']
            coins = user_dict['coins']
            subject = f"UPDATE for coins {coins}"
            details = (f"This is a periodic update email containing csv and graph data on your monitored coins.#"
                        f"Your coins are: {coins}#"
                        f"The next update will send in {update_message_timer/3600} hours.#"
                        'To scilence this type of message, email this address the command "silence".#' 
                        'To modify how often this type of message sends, email this address "update-X"')
            files = ','.join([','.join(file_group) for file_group in [glob(f"{self.root_path}/server_mail/outgoing/{coin}_UPDATE*") for coin in coins] if file_group != []])
            message = {'user':gmail, 'title':subject, 'details':details, 'files':files}
            self.mode_2_messages[gmail] = message
            
            time.sleep(update_message_timer) # If user decides to increase this frequency, destroy the thread and create new one
            #TODO For a situation where a new user joins, and the mode1 messages are passed thesholds, let this create a mode1 message just as their first message


    def server_user_attributes(self, coins):
        '''Handles adding or removing attributes to the server_users global variable'''

        #TODO potentially make a user class, with these methods, and attributes, in a seperate file - maybe 

        pass


    def recieve_mail_instructions(self):
        '''Thread which handles listening for emails from server users'''
        #TODO
        # Ideally waits in while loop, checking incoming mail each time (which come from script, generates new file for each mail) - by running recevie_mail.sh 
        # Once this checks the file, it deletes it (clearing inbox)
        # This will read the incoming.txt (where the received instructions are) and make/modify each outgoing.txt which then gets picked up by notification_send_gmail

        while self.postfix_init:
            self.tickspeed_handler.wait()

            # commands:
            # new_user: creates a new server_user thread
            # drop: Requires user + coin/tradingpair
            # monitor: requires user + coins etc.
            # update: requires interval
            # Silence: Stops server from sending mode 2 messages
            # request_coin: non-admin users can request a coin, which the server will store and present to the owner 
        # Instructions like: Add new user, monitor new coin, drop coin, send update, change notification etc. 


    def notification_settings(self):
        '''By deafult, server will determine the notification sensistivity based on the historical graph, this method handles the modulation of this sensititity'''

        # Also allow user to set whether the server can send a message once an 1hour just as a summery, with a different subject title in order to avoid phone buzz
        if self.postfix_init:
            pass 
        else:
            print(f"Please run the 'notify' command before trying to modify notifcation settings")


    def notification_send_gmail(self):
        '''Thread which handles sending emails to server users'''

        while self.postfix_init:
            while self.outgoing_messages:
                to_send = self.outgoing_messages.copy()
                print(f"self.outgoing_messages is: {self.outgoing_messages}")
                self.tickspeed_handler.wait()
                for user in to_send:
                    self.outgoing_messages.pop(user)
                    message = to_send[user]
                    sendmail_process = subprocess.run([self.script_path + '/send_mail.sh', *[message[header] for header in message]])
                    if sendmail_process.returncode == 0:
                        continue
                    else:
                        print(f"Error: message for {user} did not send, script returned exit {sendmail_process.returncode}.")
            self.tickspeed_handler.wait()


    def notification_init(self):
        '''Handles postfix initiation and SMTP communication with user gmail'''

        if not self.postfix_init:
            self.server_instruction['pause'] = 1 # Stops all server stdout for cleaner user interaction.
            notification_init_process = subprocess.run(['sudo', self.script_path + '/notification_init.sh'])
            if notification_init_process.returncode == 0:
                postfix_init_process = subprocess.run(['sudo', self.script_path + '/postfix_init.sh'])
                while True:
                    if postfix_init_process.returncode == 0:
                        print("Postfix server setup completed. Notifications service will now commence!")
                        self.postfix_init = True
                        owner = True
                        with open(self.attribute_path + '/postfix.txt') as users:
                            first_line = users.readline()
                            self.server_owner_gmail = first_line.split(':')[1]
                            gmail = first_line.split(':')[-1][:-1]
                        Thread(target=self.server_user, name='server_user_owner',args=(gmail, owner), daemon=True).start() 
                        Thread(target=self.notification_send_gmail, name='notification_send_gmail', daemon=True).start()
                        Thread(target=self.recieve_mail_instructions, name='recieve_mail_instructions', daemon=True).start()
                        break 
                    elif postfix_init_process.returncode == 1:
                        print("Server notification service will NOT commence. To retry, run 'notify' command again.")
                        break
                    elif postfix_init_process.returncode == 2:
                        postfix_init_process = subprocess.run(['sudo', self.script_path + '/postfix_init.sh'])
                    time.sleep(0.5)
                self.server_instruction['pause'] = 0 # Unpause server stdout.
                return
            print("Server notification service will NOT commence until this issue is resolved.")


    def debug(self):
        '''Helper method which returns all coin threads currently running on the server'''

        print('\nServer is currently running the following threads:\n')
        [print('Thread: ' + str(thread).split(',')[0].split('(')[1]) for thread in list_threads()]
        print(f"\nServer instructions are set as: \n{self.server_instruction}")
        print(f"Server tick speed: {self.SERVER_SPEED}")
        print(f"Server interval speed: {self.REQUEST_INTERVAL}")


    def shutdown_server(self):
        '''When keyword >quit< is receieved, server will shutdown'''

        print('Server is shutting down...')
        if subprocess.run(['sudo', self.script_path + '/shutdown.sh']).returncode == 0:
            self.server_shutdown.set() # Set event object flag as ON.
        else:
            print('WARNING: server shutdown process was NOT sucessful. Please wait for the admin.')
        
        #TODO remove all incoming/outgoing files


#TODO add a current score interval boost mode, i.e. make the stdout calculate score once every 5 sec instead of 5min

#TODO from the email side, make a PING command to check whether server is running
# RESTART 

if __name__ == '__main__':
    # Example: <python3 notification_server.py BTC LTC ETH INJ>
    server = Notification_server(coins=sys.argv[1:])
    server.server_shutdown.wait() # Pauses main thread until shutdown_server method is invoked.
    print("Server shut down.")
