from threading import Thread, Event, enumerate as list_threads
from get_candles import Coin
from utility import get_filename_extension
from enums import INTERVALS, DEFAULT_TIMEFRAMES, STANDARD_TRADING_PAIRS
from datetime import datetime
from glob import glob
import subprocess
import time
import json
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
    SERVER_SPEED = 2 # Deafult server tick speed 2 seconds.
    REQUEST_INTERVAL = 60 # Deafult server Binance candle request interval.
    BULL_THRESHOLD = 25 # Deafult thresholds before notification sent. Each user can set their own threshold under their attributes. (eventually implement ML)
    BEAR_THRESHOLD = 25 # Eventually will make both of these dicts with keys as coins, value as threshold.
    MODE_2_REQUEST = 0 # Whenever a user thread requires a new update, this will handle that.
    
    def __init__(self, to_monitor=[]):

        # TODO Need a dictionary which stores all the thresholds for all monitored symbols - obtained from optimise signal threshold
        # Make a command which allows you to change it
        # make a command to print each threshold for each symbol
        # TODO consider making a seperate class all about the actual notication sending to email
        # TODO need to make it so the notification can notify windows too
        # TODO make all methods have types and return types
        # TODO make all methods be either private or public, I think make the static methods part of utilities

        self.tickspeed_handler = Event() # Event object to handle server tick speed. 
        self.server_shutdown = Event() # Event object to handle server shutdown if command 'quit' is entered.
        self.tickspeed_handler.set()
        self.root_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = self.root_path + '/coindata'
        self.script_path = self.root_path + '/notification_scripts'
        self.attribute_path = self.script_path + '/server_attributes'
        self.monitored_coins = {} # Coins server is currently monitoring {coin: symbol: [timeframe, timeframe...], coin2: symbol1: [...]}
        self.coin_objs = {} # E.g. {'btc': btc_obj, 'rvn': rvn_obj}
        self.server_instruction = {
            'to_drop': {'item':''},
            "stdout": 0,
            'stdout_detail': 0,
            'request_interval': [],
            'pause_stdout': 0,
            'boost': 0,
            'score': 0,
            'new_user': ''
        }      
        self.server_messages = {
            'current_monitoring':0,
            'removed_items':{},
            'new_monitorings':{},
            'current_score':{},
            'signals':{},
            'lastest_signals':{},
            'retain_score':[],
            'graph_trend':[],
            'graph_lookahead':[],
            'graph_PA':[],
            'graph_trade_simulation':[],
            'graph_binance_scan':''
        }
        self.server_users = {} # Keeps track of server users and their attributes (coins, update_intervals, thresholds, previlages). 
        self.mode_1_messages = {} # Stores mode 1 (signal) like messages for server_user thread to read/send.
        self.mode_2_messages = {} # Stores mode 2 (update) like messages for server_user thread to read/send.
        self.outgoing_messages = {} # Stores messages from all users which get seqentially delivered to each respective user email
        self.postfix_init = False
        self.server_owner_gmail = ''

        if not os.path.exists(self.data_path):
            os.mkdir(self.data_path) # This acts like a database to store all users coins and anaylsis.
        self.server_welcome()
        self.monitor_all_coins(to_monitor=to_monitor) # if nothing entered, all coins in db are monitored
        Thread(target=self.server_tick_speed, name='server_tick', daemon=True).start() # Global server tick speed.
        Thread(target=self.request_interval_handler, name='server_intervals', daemon=True).start() # Global server timer for sending candle requests.
        Thread(target=self.server_stdout, name='server_stdout', daemon=True).start() # Handles smooth server stdout. 
        Thread(target=self.server_user_stdinput, name='server_input', daemon=True).start() # Ready server to intake user inputs


    def server_welcome(self): # TODO private
        '''Server welcome'''

        print(f"Server has been initiated!")
        print(f"Server is ready to intake commands. Type 'commands' to view avaliable commands:")
        print(f"Enter command 'notify' to commence server gmail notification service")
        print(f"Enter command 'post' to receive your chosen coin scores and summaries\n")


    def server_commands(self): # TODO private, add to server_messages, make it call this function, activated via switch
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
        print(self.monitored_coins)


    def server_user_stdinput(self): # TODO private 
        '''
            Thread handles user inputs
        '''

        while True:
            user_input = input().strip().lower()
            if user_input == 'commands':
                self.server_commands()
            elif user_input == 'quit':
                self.shutdown_server()
            elif user_input == 'score':
                self.server_instruction['score'] = 1
            elif user_input == 'trend':
                Thread(target=self.get_trend_graph(), name='get_trends', daemon=True).start()
            elif user_input == 'retain':
                Thread(target=self.get_retain_scoring(), name='get_retain', daemon=True).start()
            elif user_input == 'graph1':
                Thread(target=self.get_look_ahead_graph(), name='get_look_ahead_graph', daemon=True).start()
            elif user_input == 'signals':
                self.get_latest_signals()
            elif user_input == 'clear signals':
                self.server_messages['signals'] = {}
            elif user_input == 'stdout':
                self.toggle_stdout()
            elif user_input == 'stdout_detail':
                self.toggle_stdout_detail()                    
            elif user_input == 'request_interval':
                self.update_timers('request_interval')
            elif user_input == 'server_speed':
                self.update_timers('server_speed')
            elif user_input == 'monitoring':
                self.server_messages['current_monitoring'] = 1
            elif user_input == 'monitor':
                self.monitor_new_coin()
            elif user_input == 'all':
                self.monitor_all_coins()
            elif user_input == 'drop':
                self.drop_coins()
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


    def monitor_all_coins(self, to_monitor=[]):
        '''
            Hanndles the server coin monitoring initiation
        '''

        if not to_monitor:
            to_monitor = self.get_stored_coins()
            if not to_monitor: # no coins in db
                self.monitor_new_coin() # prompt user to enter coin.
        self.server_messages['new_monitorings'] = {
            'added':set(),
            'invalid_syntax':set(),
            'invalid_timeframe':set(),
            'binance_exceptions':set(),
            'completed':0
        }
        print(f'monitor_all_coins output: {to_monitor}')
        Thread(target=self.add_to_monitoring, args=(to_monitor,), daemon=True).start()
        # self.create_coin_threads(self.add_to_monitoring(to_monitor)) # verify input and make new coin threads
        # self.create_coin_threads(Thread(target=self.add_to_monitoring, args=(to_monitor,), daemon=True).start())


    def monitor_new_coin(self):
        '''
            Handles user input for specifying multiple new coins, trading pairs or timeframes to monitor by the server
        '''

        self.server_messages['current_monitoring'] = 1
        print(f'\n{"="*10}INSTRUCTIONS{"="*10}')
        print('List coins, symbols or symbol_timeframes which you want to start monitoring.')
        print('If said coin or symbol is already present in the database, all their their timeframes will be monitored.')
        print(f'If the coin or symbol is not present in the database, they will be monitored with standard timeframes {DEFAULT_TIMEFRAMES} USDT pair.')
        print('Or you can specify a list of timeframes to monitor, use [] like `BTCUSDT[1h,4h,12h,1w,1M]`, use no spaces inbetween.')
        print('Or to specify single timeframes to monitor, use `ETHBTC_1d`')
        print('Example: `RVN INJBTC ETHUSDT_4h DOGE XRPBTC_3d DOTUSDT[30m,1h,4h,1w]`')
        print('Seperate entries by space.\n')
        self.server_instruction['pause_stdout'] = 1 # Stops all server stdout for cleaner user interaction.

        to_monitor = set(input('To monitor >>> ').split())
        self.server_messages['new_monitorings'] = {
            'added':set(),
            'invalid_syntax':set(),
            'invalid_timeframe':set(),
            'binance_exceptions':set(),
            'completed':0
        }
        self.server_instruction['pause_stdout'] = 0 # Unpause server stdout.
        # self.create_coin_threads(self.add_to_monitoring(to_monitor)) # verify input and make new coin threads
        Thread(target=self.add_to_monitoring, args=(to_monitor,), daemon=True).start()
        # self.create_coin_threads(Thread(target=self.add_to_monitoring, args=(to_monitor,), daemon=True).start()) # verify input and make new coin threads


    def create_coin_threads(self, added_coins):
        '''
            Handles creating new coin threads if they are currently not being monitored by server
        '''

        print(f'added coins were: {added_coins}')
        for coin in added_coins:
            if not [thread for thread in list_threads() if str(thread).split(',')[0].split('(')[1] == coin]:
                # Means server is not currently monitoring this coin, so start new thread. 
                Thread(target=self.monitored_coin, name=coin, args=(coin,), daemon=True).start()


    def drop_coins(self):
        '''
            Handles user input for dropping a coin, tradingpair or timeframe from being monitored and removes from database if requested
        '''

        self.server_messages['current_monitoring'] = 1
        print(f'\n{"="*10}INSTRUCTIONS{"="*10}')
        print('List coins, symbols or symbol_timeframes to stop monitoring. Append `-drop` to remove those from the database.')
        print('Entering a coin will drop all related symbols.')
        print('Entering a symbol drops all related symbol_timeframes.')
        print('Entering a symbol_timeframe drops only that symbol_timeframe.')
        print('Example: `RVN INJBTC ETHUSDT_4h DOGE-drop XRPBTC_3d-drop`')
        print('Seperate entries by space.\n')
        self.server_instruction['pause_stdout'] = 1 # Stops all server stdout for cleaner user interaction.

        to_drop = set(input('To drop >>> ').split())
        self.server_instruction['pause_stdout'] = 0 # Unpause server stdout.
        Thread(target=self.handle_coin_drop, args=(to_drop,), daemon=True).start()


    def handle_coin_drop(self, to_drop):
        '''
            Handles removing given coin/tradingpair/timeframe from Server monitoring or database
        '''

        Thread(target=self.boost_speed, args=(0.5,), daemon=True).start() # Temporarily boost server speed for faster processing. 
        print(f'to_drop is: {to_drop}')

        # self.server_messages['removed_items'] = {'to_drop':to_drop.copy(), 'initial_queries':to_drop.copy(), 'completed':0}
        self.server_messages['removed_items'] = {'dropped':set(), 'initial_queries':to_drop.copy(), 'completed':0}
        for query in to_drop:
            drop_from_db = True if '-drop' in query else False
            query = query.replace('-drop', '')
            query = query.upper() if '_' not in query else f'{query.split("_")[0].upper()}_{query.split("_")[-1]}' # safeguard
            self.server_instruction['to_drop'] = {'item':query, 'drop_db':drop_from_db}
            while self.server_instruction['to_drop']['item']:
                self.tickspeed_handler.wait()
        self.server_instruction['boost'] = 0 # Turn off boost thread.
        self.server_messages['removed_items']['completed'] = 1


    def add_to_monitoring(self, to_monitor): # TODO private
        '''
            Handles validating and adding coins, symbols or symbol_timeframes into the server monitoring and database
            An example input could be complex like `RVN INJBTC ETHUSDT_4h DOGE XRPBTC_3d, DOTUSDT[30m, 1h, 4h, 1w]`
        '''
        print(f'to_monitor: {to_monitor}')
        processed_to_monitor = self.process_to_monitor_query(to_monitor)
        print(f'to_monitor: {to_monitor}')
        print(f'to_monitor processed: {processed_to_monitor}')

        for item in processed_to_monitor:
            coin, tradingpair, symbol, timeframes = processed_to_monitor[item]

            if coin in self.get_stored_coins() and not symbol:
                self.coin_objs[coin] = Coin(coin)
                self.monitored_coins[coin] = self.coin_objs[coin].get_symbol_timeframes() # monitor all stored associated with coin
            elif symbol in self.get_stored_symbols():
                if not timeframes:
                    self.coin_objs[coin] = Coin(coin)
                    self.monitored_coins[coin][symbol] = self.coin_objs[coin].get_symbol_timeframes()[symbol] # monitor all stored associated with symbol
                for timeframe in timeframes:
                    if f'{symbol}_{timeframe}' not in self.get_stored_symbol_timeframes(): # new timeframe not in db
                        Coin(coin).get_candles(tradingpair, [timeframe]) # we know symbol is valid with Binance
            elif not tradingpair and not Coin(coin).get_candles(tradingpair:='USDT', timeframes:=DEFAULT_TIMEFRAMES):
                self.server_messages['new_monitorings']['binance_exceptions'].add(item)
                continue # rejected by Binance, invalid coin
            elif not timeframes and not Coin(coin).get_candles(tradingpair, timeframes:=DEFAULT_TIMEFRAMES):
                self.server_messages['new_monitorings']['binance_exceptions'].add(item)
                continue # rejected by Binance, invalid coin or tradingpair
            elif not Coin(coin).get_candles(tradingpair, timeframes):
                self.server_messages['new_monitorings']['binance_exceptions'].add(item)
                continue # rejected by Binance, invalid coin or tradingpair

            symbol = symbol if symbol else f'{coin}{tradingpair}'
            if coin in self.monitored_coins:
                if symbol in self.monitored_coins[coin]:
                    for timeframe in set(timeframes).difference(set(self.monitored_coins[coin][symbol])):
                        self.monitored_coins[coin][symbol].append(timeframe)
                else:
                    self.monitored_coins[coin][symbol] = timeframes
            else:
                self.coin_objs[coin] = Coin(coin)
                self.monitored_coins[coin] = {symbol:timeframes}
            self.server_messages['new_monitorings']['added'].add(item)
        
        self.server_messages['new_monitorings']['completed'] = 1
        print(f'self.server_messages is: {self.server_messages}')
        self.create_coin_threads(self.server_messages['new_monitorings']['added'])
        # return added_coins # Return succesfully added coins.


    def process_to_monitor_query(self, to_monitor): # TODO private
        '''
            Splits query into coin, symbol, tradingpair, timeframes and filters some invalid entires
        '''

        filtered_to_monitor = {}
        for item in to_monitor:
            # print(f'item: {item}')
            item_og = item
            coin, tradingpair, symbol, timeframes = '', '', '', []

            if len(item.split('_')) == 2:
                symbol, timeframe = item.split('_')
                print(f'item: {item} enters split with: {symbol} : {timeframe}')
                if timeframe not in INTERVALS:
                    self.server_messages['new_monitorings']['invalid_timeframe'].add(item)
                    continue # invalid timeframe
                timeframes.append(timeframe)
                item = item[:item.index('_')]
                print(f'timeframe split: item now {item}')
            elif '[' in item and ']' == item[-1]:
                print(f'item: {item} entered multi tf')
                timeframes.extend([tf.strip() for tf in item.split('[')[-1][:-1].split(',')])
                print(f'timeframes is now: {timeframes} and valid: {[timeframe for timeframe in timeframes if timeframe not in INTERVALS]}')
                if [tf for tf in timeframes if tf not in INTERVALS]:
                    self.server_messages['new_monitorings']['invalid_timeframe'].add(item)
                    continue # invalid timeframe present
                item = item.split('[')[0]
                print(f'Multiple timeframe split: item now {item}')
            item = item.upper()
            for std_tradingpair in STANDARD_TRADING_PAIRS:
                if std_tradingpair in item and len(item.split(std_tradingpair)[0]) >= 3:
                    coin, tradingpair = item.split(std_tradingpair)[0], std_tradingpair
                    symbol = item
                    print(f'item: {item} split into : {coin} and {tradingpair} ==== the split looks like: {item.split(std_tradingpair)}')
                    break
            if not coin and timeframes:
                self.server_messages['new_monitorings']['invalid_syntax'].add(item)
                continue # Invalid entry, e.g. BTC-30m, must include tradingpair
            elif not coin:
                coin = item
                print(f'coin is: {item}')
            filtered_to_monitor[item_og] = [coin, tradingpair, symbol, timeframes]
        return filtered_to_monitor


    def monitored_coin(self, coin):
        '''
            Thread starts the monitoring and score calculation of given coin. Handles external signals to drop activity
        '''
        print(f'new thread ------------------ {coin} ----------------------')
        print(f'monitoring:::: {self.monitored_coins}')
        coin_obj = self.coin_objs[coin]
        while True:
            self.tickspeed_handler.wait() # Releases every server tick.

            # Check to see whether coin needs to be dropped
            if coin in self.server_instruction['to_drop']['item']:
                to_drop = self.server_instruction['to_drop']
                print(f'THREAD: {coin} to_drop: {to_drop}')
                self.server_instruction['to_drop'] = {'item':''}
                if to_drop['item'] in self.get_stored_coins():
                    print(f'drop coin: {to_drop}')
                    if to_drop['drop_db']:
                        coin_obj.remove_coin() # Remove from database.
                    self.monitored_coins.pop(to_drop['item'])
                    self.server_messages['removed_items']['dropped'].add(to_drop['item'])
                elif to_drop['item'] in self.get_stored_symbols():
                    print(f'drop symbol: {to_drop}')
                    if to_drop['drop_db']:
                        coin_obj.remove_symbol(to_drop['item'])
                    self.monitored_coins[coin].pop(to_drop['item'])
                    self.server_messages['removed_items']['dropped'].add(to_drop['item'])
                elif to_drop['item'] in self.get_stored_symbol_timeframes():
                    symbol, timeframe = to_drop['item'].split('_')
                    print(f'drop timeframe: {symbol}_{timeframe}')
                    if to_drop['drop_db']:
                        coin_obj.remove_timeframe(to_drop['item'])
                    self.monitored_coins[coin][symbol].remove(timeframe)
                    self.server_messages['removed_items']['dropped'].add(to_drop['item'])
                if coin not in self.monitored_coins or not self.monitored_coins[coin]:
                    print(f'dropping thread: {coin}')
                    return 0 # Drop this coin thread.

            # Check to see whether request timer has activated.
            # if coin in self.server_instruction['request_interval']:
            #     self.server_instruction['request_interval'].remove(coin) # Let's request_interval thread know which coins have started scoring.
            #     for symbol in self.monitored_coins[coin]:
            #         score_summary = coin_obj.current_score(symbol, self.monitored_coins[coin][symbol])
            #         signal = score_summary[4]
            #         if coin in self.server_instruction['to_drop']['to_drop']:
            #             continue # If user just entered coin to drop when score already processed.
            #         if symbol not in self.server_messages['current_score']:
            #             self.server_messages['current_score'][symbol] = score_summary
            #         if signal:
            #             self.server_messages['signals'][symbol] = [
            #                 signal,
            #                 datetime.now().strftime("%I:%M %p"),
            #                 score_summary
            #             ]

            #         try:
            #             if self.mode_1_messages[coin] and not self.server_instruction['new_user']:
            #                 self.mode_1_messages.pop(coin) # To prevent recuring posting of mode1 type messages.
            #         except KeyError:
            #             pass

                if self.MODE_2_REQUEST:
                    # coin_obj.generate_result_files(mode='update')
                    self.MODE_2_REQUEST -= 1 # Once the value becomes zero, any user thread which is ready will send a mode 2 email.


    def get_retain_scoring(self):
        '''Generates a retain score file for the given coin + pair'''

        symbol = input('Enter a symbol, E.g. `BTCUSDT` >>> ').upper()
        if symbol not in self.get_stored_symbols():
            print(f'{symbol} not in database. Please add it using `monitor` command first.\n')
            return

        path = self.coin_objs[self.find_coin(symbol)].generate_retain_score(symbol, self.monitored_coins[symbol])
        self.server_messages['retain_score'] = [symbol, path]


    def get_latest_signals(self):
        '''
        For each monitored symbol this returns stats on how the latest signal performed
        '''

        signal_stats = {}
        for coin in self.monitored_coins:
            for symbol in self.monitored_coins[coin]:
                signal_stats[symbol] = self.coin_objs[coin].get_latest_signal_stats(symbol)
        for symbol in signal_stats:
            self.server_messages['lastest_signals'][symbol] = signal_stats[symbol]


    def get_trend_graph(self, advanced=False):
        '''Returns the last x many score entries for a given interval for a given coin'''

        # TODO  have the bull/bear/change score super imposed in the background
        symbol = input('Enter a symbol, E.g. `BTCUSDT` >>> ').upper()
        if symbol not in self.get_stored_symbols():
            print(f'{symbol} not in database. Please add it using `monitor` command first.\n') #TODO possible make an error message
            return

        path = self.coin_objs[self.find_coin(symbol)].graph_trend(symbol, self.monitored_coins[symbol])
        self.server_messages['graph_trend'] = [symbol, path]


    def get_look_ahead_graph(self):
        '''Generates a retain score graph for the given coin + pair'''

        symbol = input('Enter a symbol, E.g. `BTCUSDT` >>> ').upper()
        if symbol not in self.get_stored_symbols():
            print(f'{symbol} not in database. Please add it using `monitor` command first.\n')
            return

        path = self.coin_objs[self.find_coin(symbol)].graph_look_ahead_data(symbol, self.monitored_coins[symbol])
        self.server_messages['graph_lookahead'] = [symbol, path]

    
    def get_trading_simulation_graph(self):

        symbol = input('Enter a symbol, E.g. `BTCUSDT` >>> ').upper()
        if symbol not in self.get_stored_symbols():
            print(f'{symbol} not in database. Please add it using `monitor` command first.\n')
            return

        path = self.coin_objs[self.find_coin(symbol)].graph_trading_simulation(symbol, self.monitored_coins[symbol])
        self.server_messages['graph_trade_simulation'] = [symbol, path]

    
    def get_pa_signal_graph(self):

        symbol = input('Enter a symbol, E.g. `BTCUSDT` >>> ').upper()
        if symbol not in self.get_stored_symbols():
            print(f'{symbol} not in database. Please add it using `monitor` command first.\n')
            return

        path = self.coin_objs[self.find_coin(symbol)].graph_signal_against_pa(symbol, self.monitored_coins[symbol])
        self.server_messages['graph_PA'] = [symbol, path]


    def server_stdout(self):
        '''Thread handles server stdout (so that thread stdouts don't overlap)'''

        while True:
            self.tickspeed_handler.wait() # Releases every server tick.
            while True:
                if self.server_instruction['pause_stdout']:
                    time.sleep(1)
                    continue
                break

            new_messages = [m_type for m_type in self.server_messages if self.server_messages[m_type]
                        and m_type not in ['current_score', 'removed_items', 'new_monitorings']]

            if len(self.server_messages['current_score']) == sum([len(self.monitored_coins[coin]) for coin in self.monitored_coins]):
                if self.server_instruction['stdout']:
                    self.server_instruction['score'] = 1 
                if self.server_instruction['score']: # Can be turned on via user input also.
                    new_messages.append('score_ready') # Only stdout when all symbol scores have been calculated
            
            if self.server_messages['removed_items']:
                if self.server_messages['removed_items']['completed']:
                    new_messages.append('remove_msg_ready')
            
            if self.server_messages['new_monitorings']:
                if self.server_messages['new_monitorings']['completed']:
                    new_messages.append('monitoring_msg_ready')

            if new_messages:
                print(f'{"*"*25} NEW server messages {"*"*25}')
                print(f'Timestamp: {datetime.now().strftime("%d/%m/%y %I:%M %p")}\n')

                if 'monitoring_msg_ready' in new_messages:
                    newly_added_set = self.server_messages['new_monitorings']['added']
                    invalid_syntax_set = self.server_messages['new_monitorings']['invalid_syntax']
                    invalid_timeframes = self.server_messages['new_monitorings']['invalid_timeframe']
                    binance_exceptions = self.server_messages['new_monitorings']['binance_exceptions']
                    self.server_messages['new_monitorings'] = {}
                    print('Adding coins to server monitoring has completed!')
                    print(f'The following items will start being monitored: {newly_added_set}')
                    if invalid_syntax_set:
                        print(f'The following items won\'t be monitored due to invalid syntax: {invalid_syntax_set}')
                    if invalid_timeframes:
                        print(f'The following items won\'t be monitored due to invalid timeframes: {invalid_timeframes}')
                        print(f'All valid timeframes are: {INTERVALS}')
                    if binance_exceptions:
                        print(f'The following items won\'t be monitored as they\'re not listed in Binance: {binance_exceptions}')
                    self.server_messages['current_monitoring'] = 1 # stdout db and monitoring summary

                if 'remove_msg_ready' in new_messages:
                    removed_set = self.server_messages['removed_items']['dropped']
                    original_set = self.server_messages['removed_items']['initial_queries']
                    self.server_messages['removed_items'] = {}
                    failed_queries = original_set.difference(removed_set)
                    dropped_monitorings = []
                    dropped_databases = []
                    print('Drop command has completed!')
                    for query in removed_set:
                        if '-DROP' in query:
                            dropped_databases.append(query)
                        else:
                            dropped_monitorings.append(query)
                    if dropped_monitorings:
                        print(f'The following queries were removed from monitoring: {dropped_monitorings}')
                    if dropped_databases:
                        print(f'The following queries were removed from database: {dropped_databases}')
                    if failed_queries:
                        print(f'The following queries were invalid or not present: {failed_queries}')
                    self.server_messages['current_monitoring'] = 1

                if 'score_ready' in new_messages:
                    self.server_instruction['score'] = 0
                    symbol_scores = self.server_messages['current_score'].copy()
                    self.server_messages['current_score'] = {}
                    print('Current score updates >>>')
                    for symbol in symbol_scores:
                        summary = symbol_scores[symbol]
                        max_score = len(summary[-1]) * 6
                        if self.server_instruction['stdout_detail']:
                            print('\n' + '='*130)
                            print(f"\n{summary[0]} monitoring update:")
                            print(f"Current price: {summary[5]}")   
                            print(f"Bull score: {summary[1]} out of {max_score}, change score: {summary[3]} out of {max_score}")
                            print(f"Bear score: {summary[2]} out of {max_score}, change score: {summary[3]} out of {max_score}")
                            print(f'Signal >>> {summary[4]} <<<')
                            print(f"Overview:")
                            print(json.dumps(summary[-1], indent=4))
                            print('='*130 + '\n')
                        else:
                            mood = 'BULL' if summary[1] > summary[2] else 'BEAR'
                            score = summary[1] if summary[1] > summary[2] else summary[2]
                            print(f'{summary[0]} price: {summary[5]}, {mood} {score}/{max_score}, change: {summary[3]} signal: {summary[5]}')
                    print()

                if self.server_messages['current_monitoring']:
                    self.server_messages['current_monitoring'] = 0
                    if not self.get_stored_coins() or not self.monitored_coins:
                        print(f"Server has no stored or monitored coins. Enter command 'monitor' to add new coins.")
                    else:
                        print(f"Server has the following coins in the database:")
                        for coin in self.get_stored_coins():
                            stored_symbol_timeframes = Coin(coin).get_symbol_timeframes()
                            for symbol in stored_symbol_timeframes:
                                print(f'{symbol}: {stored_symbol_timeframes[symbol]}')
                        
                        print(f"\nServer is currently monitoring:")
                        for symbol in self.monitored_coins:
                            print(f'{symbol}: {self.monitored_coins[symbol]}')
                    print()

                if self.server_messages['signals']:
                    signals = self.server_messages['signals'].copy()
                    for symbol in signals:
                        signal, timestamp, summary = signals[symbol]
                        mood = 'BULL' if summary[1] > summary[2] else 'BEAR'
                        score = summary[1] if summary[1] > summary[2] else summary[2]
                        max_score = len(summary[-1]) * 6
                        print('!!!!!!!!!!!! ATTENTION !!!!!!!!!!!!')
                        print(f'{signal} signal for {symbol} at {timestamp}')
                        print(f'Price was: {summary[5]}, {mood} score {score}/{max_score}')
                    print('***To clear these signals, run the command "clear signals"***\n')

                if self.server_messages['lastest_signals']:
                    latest_signal_stats = self.server_messages['lastest_signals'].copy()
                    self.server_messages['lastest_signals'] = {}
                    for symbol in latest_signal_stats:
                        signal_stats = latest_signal_stats[symbol]
                        (symbol, signal, mood, score, change_score, max_score, signal_price, tf_scores, alt_action,
                        max_gain, desired_assest, best_gain_price, current_gain, current_price, delta_time, date) = signal_stats
                        print(f'\n{"="*25} Signal for {symbol} {"="*25}')
                        print(f'{signal} signal {delta_time} hours ago at {date}')
                        print(f'Price was: {signal_price}, {mood} score: {score}/{max_score},'
                            f'change score: {change_score}/{max_score}, timeframe scores: {", ".join(tf_scores)}')
                        print(f'Max gain from {alt_action} would be {max_gain:.2f}% of {desired_assest} at ${best_gain_price},'
                            f'gain now from {alt_action} is {current_gain:.2f}% of {desired_assest} at ${current_price}\n')

                if self.server_messages['retain_score']:
                    symbol, path = self.server_messages['retain_score']
                    timeframes = self.monitored_coins[self.find_coin(symbol)]
                    self.server_messages['retain_score'] = []
                    print(f'Retain scoring summary for {symbol} with timeframes {timeframes} has completed. File located at: {path}\n')

                if self.server_messages['graph_trend']:
                    symbol, path = self.server_messages['graph_trend']
                    timeframes = self.monitored_coins[self.find_coin(symbol)]
                    self.server_messages['graph_trend'] = []
                    print(f'Trend graph for {symbol} with timeframes {timeframes} has completed. File located at: {path}\n')

                if self.server_messages['graph_lookahead']:
                    symbol, path = self.server_messages['graph_lookahead']
                    timeframes = self.monitored_coins[self.find_coin(symbol)]
                    self.server_messages['graph_lookahead'] = []
                    print(f'Look ahead graph for {symbol} with timeframes {timeframes} has completed. File located at: {path}\n')
                
                if self.server_messages['graph_PA']:
                    symbol, path = self.server_messages['graph_PA']
                    timeframes = self.monitored_coins[self.find_coin(symbol)]
                    self.server_messages['graph_PA'] = []
                    print(f'PA and signal graph for {symbol} with timeframes {timeframes} has completed. File located at: {path}\n')

                if self.server_messages['graph_trade_simulation']:
                    symbol, path = self.server_messages['graph_trade_simulation']
                    timeframes = self.monitored_coins[self.find_coin(symbol)]
                    self.server_messages['graph_trade_simulation'] = []
                    print(f'Trade simulation for {symbol} with timeframes {timeframes} has completed. File located at: {path}\n')

                if self.server_messages['graph_binance_scan']:
                    pass

                print(f'{"*"*25} END server messages {"*"*25}')


    def get_stored_coins(self):
        '''returns list of coins stored in database'''

        return [path.split('/')[-1] for path in glob(f'{self.data_path}/*') if 'binance_scan' not in path]


    def get_stored_symbols(self):
        '''returns a dictionary containing all symbols stored in the database'''

        stored_symbols = []
        for coin in self.get_stored_coins():
            stored_symbols.extend(list(Coin(coin).get_symbol_timeframes()))
        return stored_symbols


    def get_stored_symbol_timeframes(self):
        '''returns a dictionary containing all symbol_timeframes stored in the database'''

        stored_symbol_timeframes = []
        for coin in self.get_stored_coins():
            for symbol, timeframes in Coin(coin).get_symbol_timeframes().items():
                stored_symbol_timeframes.extend([f'{symbol}_{tf}' for tf in timeframes])
        return stored_symbol_timeframes
    

    def find_coin(self, symbol):
        '''Returns coin from given symbol string'''
        coin = [symbol.split(tradingpair)[0] for tradingpair in STANDARD_TRADING_PAIRS if tradingpair in symbol]
        return coin[0] if coin else None


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


    def request_interval_handler(self):
        '''Thread used to synchronise all monitored_coin method threads'''

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

    
    def update_timers(self, timer):
        '''Handles updating server clocks'''

        words = []
        if timer == 'request_interval':
            words.extend([' (minute)', 'request_interval'])
        elif timer == 'server_speed':
            words.extend([' (second)', 'tick speed'])

        self.server_instruction['pause_stdout'] = 1
        user_input = input(f"Please input a positive integer{words[0]} for new server {words[1]}: ")
        self.server_instruction['pause_stdout'] = 0
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
            self.server_instruction['pause_stdout'] = 1 # Stops all server stdout for cleaner user interaction.
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
                self.server_instruction['pause_stdout'] = 0 # Unpause server stdout.
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
    server = Notification_server(to_monitor=sys.argv[1:])
    server.server_shutdown.wait() # Pauses main thread until shutdown_server method is invoked.
    print("Server shut down.")
