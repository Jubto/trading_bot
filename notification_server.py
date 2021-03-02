from threading import Thread, Event, enumerate as list_threads
from get_candles import Coin 
from glob import glob
import re
import sys
import os
import socket
import time
import json 


class Notification_server():
    '''
    Start server with 0 or more coin symbols to monitor, for example: 
        <python3 notification_server.py INJ RVN MONA BTC>

    When no arguments entered, server will monitor all coins stored in database, or prompt user if none are stored. 

    Enter 'commands' to view all avaliable server commands  
    '''

    PORT = 13337 
    IP_ADDRESS = socket.gethostbyname(socket.gethostname())
    SERVER_SPEED = 5 # Deafult server tick speed 5 seconds.
    REQUEST_INTERVAL = 60 # Deafult server Binance candle request interval.
    MONITORED_COINS = {} # Dict of coins server is currently monitoring. 
    MESSAGE_BACKLOG = [] # List of messages for server_stdout() to process in order. 
    SERVER_COMMANDS = ['commands', 'monitor', 'all', 'now', 'drop', 'monitoring', 'request_interval', 'quit', 'stdout', 'server_speed', 'notify', 'debug']
    SERVER_INSTRUCTION = {'drop': 0, "stdout": 1, 'request_interval': [], 'pause': 0, 'boost': 0}

    tickspeed_handler = Event() # Event object to handle server tick speed. 
    server_shutdown = Event() # Event object to handle server shutdown if command 'quit' is entered.
    
    def __init__(self, coin_symbols=[]):

        self.tickspeed_handler.set()
        self.root_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = self.root_path + '/coindata'
        if not os.path.exists(self.data_path):
            os.mkdir(self.data_path)
        self.server_start()

        if coin_symbols:
            self.monitor_all_coins(coins=coin_symbols) # Monitor all coins given as arguments if valid.
        else:
            self.monitor_all_coins() # Monitor all coins stored in local storage, if no coins, then prompt user input. 
   
        Thread(target=self.server_tick_speed, name='server_tick', daemon=True).start() # Global server tick speed.
        Thread(target=self.request_interval_handler, name='server_intervals', daemon=True).start() # Global server timer for sending candle requests.
        Thread(target=self.server_stdout, name='server_stdout', daemon=True).start() # Handles smooth server stdout. 
        Thread(target=self.server_user_stdinput, name='server_input', daemon=True).start() # Ready server to intake user inputs
        Thread(target=self.server_listen, name='server_listen', daemon=True).start() # Ready server to receive HTTP requests from client (i.e. trading_bot webpage)

    def server_start(self):
        '''Server welcome'''

        print(f'Sever has been initiated!')
        print(f'Server is ready to intake commands. Type "commands" to view avaliable commands:\n')

    def server_commands(self):
        '''Prints description of each server command'''

        print(f'\nList of commands:')
        print('='*130)
        print(f'<commands>: Returns list of commands with description.')
        print(f'<monitor>: Allows user to add new multiple new coins, tradingpairs and timeframes to monitor.')
        print(f'<monitoring>: Server returns all coins it is currently monitoring.')
        print(f'<all>: Server will start monitoring all coins, tradingpairs and timeframes stored in the local database.')
        print(f'<drop>: Allows user to drop specific coins, tradingpairs and timeframes from monitoring or database.')            
        print(f'<stdout>: Toggles server stdout.')
        print(f'<server_speed>: Allows user to modify server tick speed.')
        print(f'<request_interval>: Allows user to modify server communication interval with Binance for candle retreival (deafult 1 minute).')
        print(f'<notify>: Allows user to modify the bull/bear score threshold required for server to notify user.')
        print(f'<quit>: Shuts down server activity.')
        print('='*130 + '\n')

    def server_user_stdinput(self):
        '''Thread handles user inputs'''

        while True:
            user_input = input() # Pauses thread until user input.
            if user_input in self.SERVER_COMMANDS:
                if user_input == 'commands':
                    self.server_commands()
                elif user_input == 'quit':
                    self.shutdown_server()
                elif user_input == 'stdout':
                    self.toggle_stdout()
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
                    self.notification_settings()
                elif user_input == 'debug':
                    print(f'Server instruction settings are:\n{self.SERVER_INSTRUCTION}')
                    self.debug()
            else:
                print(f'{user_input} is an invalid server command.')
                print(f'Enter "commands" to view all avaliable commands.')


    def add_to_monitoring(self, coin_symbol=None, input_dict=None):
        '''Handles validating and adding items into the server monitoring dictionary MONITORED_COINS'''
        
        # This case is for server start up only
        if coin_symbol:
            input_dict = {}
            input_dict[coin_symbol] = {'NA':[]} 

        # This section handles determining whether coin is valid with Binance, if so it will add to server monitoring.
        added_coins = set()
        for coin_symbol in input_dict:
            for tradingpair in input_dict[coin_symbol]:
                coin = Coin(coin_symbol) # Create new coin object to monitor. 
                files = coin.list_saved_files() # Used to determine whether coin exists in local storage or not.
                timeframes = input_dict[coin_symbol][tradingpair]
                deafult_timeframes = ['1w', '3d', '1d', '4h', '1h']

                if len(files) == 0:  
                    # This means coin had no local storage   
                    if tradingpair != 'NA':
                        if coin.get_candles(tradingpair, *timeframes):
                            pass # Binance succesfully returned candles for coin-tradingpair/timeframe.
                        else:
                            print(f'{coin_symbol}{tradingpair} is not avaliable on Binance.')
                            continue # Binance rejected request.
                    elif coin.get_candles('USDT', *deafult_timeframes):
                        tradingpair = 'USDT' # No tradingpair specified so deafult tradingpair assigned to coin.
                        print(f'\nServer will monitor {coin_symbol}USDT by deafult.')
                    else:
                        print(f'{coin_symbol} is not avaliable on Binance.')
                        continue # This means coin provided is invalid for Binance.
                elif tradingpair != 'NA':
                    # Server has local storage of coin.
                    if coin.get_candles(tradingpair, *timeframes):
                        pass # This either added a new tradingpair or updated the existing stored one.
                    else:
                        print(f'{coin_symbol}{tradingpair} is not avaliable on Binance.')
                        continue # This means newly entered tradingpair is invalid for Binance. 
                print(f'Server will start monitoring {coin_symbol}{tradingpair}.\n') if tradingpair != 'NA' else print(f'Server will start monitoring {coin_symbol}.\n')
                added_coins.add(coin_symbol)

                # Add coin to server monitoring list
                if coin_symbol not in self.MONITORED_COINS.keys():
                    self.MONITORED_COINS[coin_symbol] = []
                files = coin.list_saved_files() # New coin csv files may have been added. 
                for csvfile_name in files:
                    symbol_timeframe = csvfile_name.split('.')[0]
                    symbol = symbol_timeframe.split('_')[0]
                    if tradingpair == 'NA' or symbol == coin.coin_symbol + tradingpair:
                        if symbol_timeframe not in self.MONITORED_COINS[coin_symbol]:
                            self.MONITORED_COINS[coin_symbol].append(symbol_timeframe) # Append only tradingpair/timeframe which server will actively monitoring.  
        return added_coins # Return set of succesfully added coins. 

    def monitor_coin(self, coin_symbol):
        '''Thread starts the monitoring and score calculation of given coin. Handles external signals to drop activity'''

        coin = Coin(coin_symbol) # Create coin object.
        trim = len(coin_symbol)
        while True:
            self.tickspeed_handler.wait() # Releases every server tick.

            # Check to see whether coin drop instruction is activate.
            if self.SERVER_INSTRUCTION['drop'] != 0 and self.SERVER_INSTRUCTION['drop'][1:trim + 1] == coin_symbol:    
                item_to_drop = self.SERVER_INSTRUCTION['drop']
                self.SERVER_INSTRUCTION['drop'] = 0
                if re.search(item_to_drop.rstrip('1')[1:], str(self.MONITORED_COINS[coin_symbol])):
                    if '1' == item_to_drop[-1]:
                        item_to_drop = item_to_drop.rstrip('1')
                        if '1' == item_to_drop[0]:
                            coin.remove_coin() # Remove from database. 
                        elif '2' == item_to_drop[0]:
                            coin.remove_tradingpair(item_to_drop) # Remove from database. 
                        else:
                            coin.remove_timeframe(item_to_drop) # Remove from database. 
                    clone_MONITORED_COINS = self.MONITORED_COINS[coin_symbol].copy()
                    for pair in clone_MONITORED_COINS:
                        if item_to_drop[1:] == pair or item_to_drop[1:] in pair:
                            self.MONITORED_COINS[coin_symbol].remove(pair)
                    if '1' == item_to_drop[0] or len(self.MONITORED_COINS[coin_symbol]) == 0:
                        self.MONITORED_COINS.pop(coin_symbol)
                        return 0 # Drop this coin thread.
                    print(f'The following has been dropped: {item_to_drop[1:]}')

            # Check to see whether request timer has activated.
            if coin_symbol in self.SERVER_INSTRUCTION['request_interval']:
                self.SERVER_INSTRUCTION['request_interval'].remove(coin_symbol) # Let's request_interval thread know which coins have started scoring.
                symbol_timeframes = self.MONITORED_COINS[coin_symbol] # Only monitor specified tradingpairs.
                coin_score = coin.current_score(monitoring=symbol_timeframes) # Retreve coin score and analysis summary. 
                if re.search(coin_symbol, str(self.SERVER_INSTRUCTION['drop'])):
                    continue # Situation where user inputs drop just before server sends out data.
                self.server_push(coin_score) # Sends data to webpage.
                if self.SERVER_INSTRUCTION['stdout']:
                    self.MESSAGE_BACKLOG.append(coin_score) # Send data to stdout method. 
                #TODO Add a file option. I think having a file which re-writes itself with the latest score will be easier to work with, and turn of stdout Be like coin.to_csv() 


    def current_monitoring(self):
        '''Returns list of coins, trading pairs and timeframes server is currently monitoring'''

        print(f'\nServer is currently monitoring:')
        for coin in self.MONITORED_COINS:
            print(f'\ncoin {coin}:')
            for pair in self.MONITORED_COINS[coin]:
                print(pair)

    def current_monitoring_list(self):
        '''Returns list of all pairs monitored and stored in the database'''

        currently_monitoring = [tradingpair for coin in self.MONITORED_COINS 
                                for tradingpair in self.MONITORED_COINS[coin] if coin.split('_')[-1] != 'tradingpairs']
        
        stored_tradingpairs = [tradingpair.split('/')[-1][:-4] for coin in glob(self.data_path + '/*') 
                                for tradingpair in glob(self.data_path + '/' + coin.split('/')[-1] + '/*') if tradingpair.split('.')[-1] != 'json']

        return currently_monitoring, stored_tradingpairs


    def monitor_all_coins(self, coins=None):
        '''Hanndles server coin monitoring initiation and 'all' command'''

        if not coins:
            paths = glob(self.data_path + '/*') 
            if len(paths) == 0:
                self.input_monitor_new() # If no coins are found in coindata directory, prompt user to enter coin.
            coins = [path.split('/')[-1] for path in paths] # Clean path to get only the directory name (i.e. coin_symbol).

        coins_to_add = set()
        for coin in coins:
            coins_to_add = coins_to_add.union(self.add_to_monitoring(coin.upper())) # Validate each coin entered, add to monitoring
        self.add_new_coins(coins_to_add) # Start thread for each coin if one doesn't already exist.


    def request_interval_handler(self):
        '''Thread used to synchronise all monitor_coin method threads'''

        while True:
            threads = [str(thread).split(',')[0].split('(')[1] for thread in list_threads()] # List all activate threads.
            coins = [coin for coin in threads if coin in self.MONITORED_COINS] # List only active coin threads.
            self.SERVER_INSTRUCTION['request_interval'] = coins # Change global variable to be list of coins ready to have scores checked.
            Thread(target=self.boost_speed, args=(0.1,), daemon=True).start() # Temporarily boost server speed for faster processing. 
            while self.SERVER_INSTRUCTION['request_interval'] != []:
                self.tickspeed_handler.wait() # Keep checking every server tick whether all coin threads have starting scoring.
            self.SERVER_INSTRUCTION['boost'] = 0 # Turn off boost thread.
            time.sleep(self.REQUEST_INTERVAL) # Releases every request_interval time. 

    def now(self):
        '''When invoked, server will print all coin data once immediately rather than wait for request interval'''
        pass

    def server_tick_speed(self):
        '''Thread server speed, every SERVER_SPEED time elapsed will release the tickspeed_handler object'''
        
        while True:
            self.tickspeed_handler.set() # Releases the event object for all active threads from waiting.
            time.sleep(self.SERVER_SPEED / 10) # Just a simple measure to ensure all threads get released, not worth being more sophisticated. 
            self.tickspeed_handler.clear() # Locks server wide event object. 
            time.sleep(self.SERVER_SPEED)


    def server_stdout(self):
        '''Thread handles server stdout (so that thread stdouts don't overlap)'''

        while True:
            self.tickspeed_handler.wait() # Releases every server tick.
            if len(self.MESSAGE_BACKLOG) == 0:
                continue
            messages = self.MESSAGE_BACKLOG
            self.MESSAGE_BACKLOG = [] # Empty message log.

            while True:         
                if self.SERVER_INSTRUCTION['pause'] == 1:
                    time.sleep(1) # This is used for when user is actively inputting inputs into server (excluding commands).
                    continue
                break

            for message in messages:
                if message[-1] == 'coin_score':
                    print('\n\n' + '='*130)
                    print(f'\nCoin {message[0]} monitoring update:')
                    print(f'Overview:')
                    print(json.dumps(message[3], indent=4))
                    print(f'Bull score: {message[1]} out of 60')
                    print(f'Bear score: {message[2]} out of 60')
                    print('='*130 + '\n\n')


    def toggle_stdout(self):
        '''Toggles server stdout'''

        if self.SERVER_INSTRUCTION['stdout'] == 1:
            print('Server stdout has been toggled OFF.')
            self.SERVER_INSTRUCTION['stdout'] = 0
        else:
            print('Server stdout has been toggled ON.')
            self.SERVER_INSTRUCTION['stdout'] = 1

    
    def update_timers(self, timer):
        '''Handles updating server clocks'''

        words = []
        if timer == 'request_interval':
            words.extend([' (minute)', 'request_interval'])
        elif timer == 'server_speed':
            words.extend([' (second)', 'tick speed'])

        self.SERVER_INSTRUCTION['pause'] = 1
        user_input = input(f'Please input a positive integer{words[0]} for new server {words[1]}: ')
        self.SERVER_INSTRUCTION['pause'] = 0
        try:
            user_input = int(user_input)
            if user_input > 0:
                print(f'Server {words[1]} updated to {user_input}{words[0]}.') 
                if timer == 'request_interval':
                    self.REQUEST_INTERVAL = user_input * 60
                elif timer == 'server_speed':
                    self.SERVER_SPEED = user_input
                return 1
        except ValueError:
            pass
        print(f'{user_input} is an invalid entry. Please input a positive integer.')

    def boost_speed(self, boost):
        '''Thread which toggles server speed from normal to responsive'''

        original_SERVER_SPEED = self.SERVER_SPEED
        self.SERVER_SPEED = boost
        self.SERVER_INSTRUCTION['boost'] = boost
        while self.SERVER_INSTRUCTION['boost']:
            time.sleep(boost)
        self.SERVER_SPEED = original_SERVER_SPEED

    
    def input_monitor_new(self):
        '''Handles user input for specifying multiple new coins, trading pairs or timeframes to monitor by the server'''

        currently_monitoring, stored_tradingpairs = self.current_monitoring_list()
        input_coin_dict = {}
        deafult_timeframes = ['1w', '3d', '1d', '4h', '1h']

        self.SERVER_INSTRUCTION['pause'] = 1 # Stops all server stdout for cleaner user interaction.
        print(f'Server is currently monitoring:\n{currently_monitoring}\n')
        print(f'Server has the following pairs in the database:\n {stored_tradingpairs}\n')
        print('='*10 + 'INSTRUCTIONS' + '='*10)
        print('>>> If multiple, seperate by spaces')
        print('>>> Enter coin(s) to monitor, choose their respective tradingpair(s) and Optionally list their timeframe(s)')
        print(f'>>> If no tradingpairs are entered, deafult timeframes will be used: {deafult_timeframes}')
           
        while True:
            coin_symbols = str(input('Input coins: ')).upper()
            if len(coin_symbols) == 0:
                continue
            if self.re_search(coin_symbols):
                continue
            break
        for coin in coin_symbols.split(' '):
            if coin == '':
                continue
            input_coin_dict[coin] = {} # Dictionary for tradingpairs.

        for coin in input_coin_dict:
            while True:
                tradingpairs = str(input(f'Input {coin} trading pairs: ')).upper() 
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
                    for monitored_symbol_timeframe in self.MONITORED_COINS[coin]:
                        if symbol == monitored_symbol_timeframe.split('_')[0]:
                            input_coin_dict[coin][tradingpair].append(monitored_symbol_timeframe.split('_')[1]) # Add all monitored timeframes for a given tradingpair.
                except KeyError:
                    pass # Means server is not monitoring coin.

                if input_coin_dict[coin][tradingpair]:
                    # This means coin is currently being monitored by server. User can add aditional trading pairs or timeframes.
                    print(f'Server currently monitoring {coin + tradingpair} with timeframes: {input_coin_dict[coin][tradingpair]}')
                else:
                    # This means coin entered is currently not being monitored by server (although it could be in the database). 
                    inspect_coin = Coin(coin) 
                    stored_timeframes = inspect_coin.get_timeframes(coin + tradingpair)
                    if stored_timeframes:
                        # This means server is not currently monitoring this tradingpair, however has its timeframes stored in database.
                        print(f'Server will start monitoring {coin + tradingpair} with stored timeframes: {stored_timeframes}')   
                        input_coin_dict[coin][tradingpair] = stored_timeframes   
                    else:
                        # This means server does not have any timeframes of this coin/trading pair stored. Deafult timeframes will be monitored.
                        print(f'Server will start monitoring {coin + tradingpair} with deafult timeframes: {deafult_timeframes}')
                        input_coin_dict[coin][tradingpair] = deafult_timeframes

                while True:
                    timeframes = input('OPTIONAL: Input additional timeframes: ') # White spaces will be handled in Coin.get_candles(). 
                    if self.re_search(timeframes):
                        continue
                    input_coin_dict[coin][tradingpair].extend(timeframes.split(' ')) # Add any additional timeframes on top of current ones. 
                    break
        
        self.SERVER_INSTRUCTION['pause'] = 0 # Unpause server stdout.
        added_coins = self.add_to_monitoring(input_dict=input_coin_dict) # Verify all user entries and add them to monitoring.
        Thread(target=self.add_new_coins, args=(added_coins,), daemon=True).start() # Input all successful entries.


    def add_new_coins(self, added_coins):
        '''Handles creating new coin threads if they are currently not being monitored by server'''

        for coin_symbol in added_coins:
            if not [thread for thread in list_threads() if str(thread).split(',')[0].split('(')[1] == coin_symbol]:
                # Means server is not currently monitoring this coin, so start new thread. 
                Thread(target=self.monitor_coin, name=coin_symbol, args=(coin_symbol,), daemon=True).start()

    
    def input_drop_coin(self):
        '''Handles user input for dropping a coin, tradingpair or timeframe from being monitored and removes from database if requested'''

        currently_monitoring, stored_tradingpairs = self.current_monitoring_list()
        input_coin_dict = {}
        to_drop = set()
        
        self.SERVER_INSTRUCTION['pause'] = 1 # Stops all server stdout for cleaner user interaction.
        print(f'Server is currently monitoring:\n{currently_monitoring}\n')
        print(f'Server has the following pairs in the database:\n {stored_tradingpairs}\n')
        print('Enter a coins, coins/tradingpairs, or coins/tradingpairs/timeframes to drop in the list above, appending "-drop"s')
        print('='*10 + 'INSTRUCTIONS' + '='*10)
        print('>>> If multiple, seperate by spaces')
        print('>>> To drop all related pairs of a given entry, append "-drop" (e.g. INJ-drop drops all INJ pairs, INJBTC-drop drops all INJBTC pairs)')
        print('>>> To drop given entry from server database aswell, append "1" to "-drop" (e.g. INJ-drop1, INJBTC-drop1, RVNUSDT_6h1)')
        while True:
            coin_symbols = str(input('Input coins: ')).upper()
            if len(coin_symbols) == 0:
                continue
            if self.re_search(coin_symbols):
                continue
            break
        for coin in coin_symbols.split(' '):
            if coin == '':
                continue
            input_coin_dict[coin] = [] # List for tradingpairs.

        for coin in input_coin_dict:
            if '-DROP' in coin:
                to_drop.add(coin)
                continue # Skip rest of user input interaction. 
            while True:
                tradingpairs = str(input(f'Input {coin} trading pairs: ')).upper() 
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
                    timeframes = str(input(f'Input {coin + tradingpair} timeframes: '))
                    if self.re_search(timeframes):
                        continue
                    if not re.search('[^ ]', timeframes):
                        to_drop.add(coin + '_' + tradingpair) # This means the user just entered a white space.
                    for timeframe in timeframes.split(' '):
                        if timeframe == '' or len(timeframe) != 2 or timeframe[-1] in '0123456789':
                            continue # Remove impossible entries.
                        if timeframe == '1m':
                            timeframe = '1M' # 1M month is the only timeframe with uppercase. 1m is for 1 minute however that should never be used. 
                        to_drop.add(coin + '_' + tradingpair + '_@' + timeframe)  
                    break
        Thread(target=self.drop_coins, args=(to_drop,), daemon=True).start()
        self.SERVER_INSTRUCTION['pause'] = 0 # Unpause server stdout.

    def drop_coins(self, to_drop):
        '''Handles removing given coin/tradingpair/timeframe from Server monitoring or database'''

        Thread(target=self.boost_speed, args=(0.5,), daemon=True).start() # Temporarily boost server speed for faster processing. 
        for item in to_drop:
            item = item.replace('-DROP', '')
            item = item.split('_')
            print(f'SERVER drop self.SERVER_INSTRUCTION will be {item}') #TODO remove
            if len(item) == 1:
                self.SERVER_INSTRUCTION['drop'] = '1' + item[0]
                while self.SERVER_INSTRUCTION['drop'] != 0:
                    self.tickspeed_handler.wait()
            elif len(item) == 2:
                self.SERVER_INSTRUCTION['drop'] = '2' + item[0] + item[1]
                while self.SERVER_INSTRUCTION['drop'] != 0:
                    self.tickspeed_handler.wait()
            else:
                self.SERVER_INSTRUCTION['drop'] = '3' + item[0] + item[1] + item[2].replace('@', '_')
                while self.SERVER_INSTRUCTION['drop'] != 0:
                    self.tickspeed_handler.wait()
        self.SERVER_INSTRUCTION['boost'] = 0 # Turn off boost thread.

 
    @staticmethod
    def re_search(string):
        '''Performs search for invalid symbols'''
        if re.search('[,.|!~`@#$%^&*():;/_=+\[\]\{\}]', string):
            print(f'Invalid characters used in {string}.')
            return 1
        if re.search('-', string):
            if not re.search('(-DROP)', string):
                print(f'Invalid characters used in {string}.')
                return 1

    def server_listen(self):
        '''Listens for any request via server IP/PORT.'''

        # bind socket etc. This method thread would only be used if you have this server actually running a web page, and from the browser CLIENT (i.e the client
        # is already made for you) this method will capture and interpret the HTTP requests and process them appropriately, Via the webpage we will make using HTML/Javascript
        pass

    def server_push(self, data):
        '''Sends push request to webpage with new data'''
        pass

    def graph_historical_score(self):
        '''Handles the analysis of all historical data to generate a comprehensive graph'''

        pass

    def notification_settings(self):
        '''By deafult, server will determine the notification sensistivity based on the historical graph, this method handles the modulation of this sensititity'''

        pass 

    def notify(self):
        '''Handles server notification settings to Windows and pushbullet'''

        pass

    def debug(self):
        '''Helper method which returns all coin threads currently running on the server'''

        print('\nServer is currently running the following threads:\n')
        [print('Thread: ' + str(thread).split(',')[0].split('(')[1]) for thread in list_threads()]

    def shutdown_server(self):
        '''When keyword >quit< or HTTP requires 2.0 is receieved, server will shutdown'''

        print('Server is shutting down...')
        self.server_shutdown.set() # Set event object flag as ON.

if __name__ == '__main__':
    # Server can be started with <python3 notification_server.py>
    # Optional coin_symbols can be added, example: <python3 notification_server.py BTC LTC ETH INJ>
    # Once the server is running, to view commands enter <commands> 
    user_start_arguments = sys.argv
    if len(user_start_arguments) == 1:
        server = Notification_server()
    elif len(user_start_arguments) > 1:
        coins = user_start_arguments[1:]
        server = Notification_server(coin_symbols=coins)
    server.server_shutdown.wait() # Pauses main thread until shutdown_server method is invoked.
    print("Server shut down.")
# Main thread ends here. 