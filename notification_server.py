from threading import Thread, Event, enumerate as list_threads
from get_candles import Coin 
from glob import glob
import sys
import os
import socket
import time
import json 


class Notification_server():
    '''
    Start server with 0 or more coin symbols to monitor, for example: 

    python3 notification_server.py INJ RVN MONA BTC 

    When 0 args are given, server will monitor all coins stored in database. 

    Enter 'commands' to view all avaliable server commands.  
    '''

    PORT = 13337 
    IP_ADDRESS = socket.gethostbyname(socket.gethostname())
    SERVER_SPEED = 5 # Deafult server tick speed.
    REQUEST_INTERVAL = 60 # Deafult server Binance candle request interval.
    MONITORED_COINS = {} # Dict of coins server is currently monitoring. 
    MESSAGE_BACKLOG = [] # List of messages for server_stdout() to process in order. 
    SERVER_COMMANDS = ['']
    SERVER_INSTRUCTION = {"commands": 0, "monitor": 0, 'quit': 0, 'drop': 0, "current_score": 0, "monitoring": 0, "added_coin" : 0, "add_tradingpair": 0, 
                        "add_timeframe": 0, "coin_info": 0, "stdout": 1, "server_speed": 0, 'request_interval': 0, 'pause': 0, 'debug': 0, 'boost': 0}

    tickspeed_handler = Event() # Create event object to handle server tick speed. 
    server_shutdown = Event()
    
    def __init__(self, coin_symbols=[]):

        self.tickspeed_handler.set()
        self.root_path = os.path.dirname(os.path.realpath(__file__))
        self.data_path = self.root_path + '/coindata'
        if not os.path.exists(self.data_path):
            os.mkdir(self.data_path)

        if coin_symbols:
            for coin_symbol in coin_symbols:
                coin_symbol = coin_symbol.upper()
                Thread(target=self.monitor_coin, name=coin_symbol, args=(coin_symbol,), daemon=True).start() # Start monitoring each coin in their own named thread.
        else:
            self.monitor_all_saved_coins() # Monitor all coins stored in coindata, if no coins, then prompt user input. 

        self.server_start()
        Thread(target=self.server_tick_speed, daemon=True).start() # Global server tick speed.
        Thread(target=self.request_interval_handler, daemon=True).start() # Global server timer for sending candle requests.
        Thread(target=self.server_stdout, daemon=True).start() # Handles smooth server stdout. 
        Thread(target=self.server_user_stdinput, daemon=True).start() # Ready server to intake user inputs
        Thread(target=self.server_listen, daemon=True).start() # Ready server to receive HTTP requests from client (i.e. trading_bot webpage)


    def server_start(self):
        '''Let's user know server has successfully been initiated.'''
        print(f'Sever has been initiated!')
        print(f'Server is ready to intake commands. Type "commands" to view avaliable commands:\n')

    def monitor_coin(self, coin_symbol, tradingpair=None, coin_name=None, timeframes=[]):
        '''This method starts the monitoring thread of given coin. This thread allows the server to monitor multiple coins at once.'''

        coin = Coin(coin_symbol, coin_name) # Create new coin object to monitor. If coin isn't saved locally, new coin will be saved if valid.
        files = coin.list_saved_files()

        if len(files) == 0:     
            if tradingpair:
                if coin.get_candles(tradingpair, *timeframes):
                    print(f'\nServer will start monitoring {coin_symbol}{tradingpair}.')
                else:
                    print(f'{coin_symbol} is not avaliable on Binance.1')
                    return 0 # Close thread.
            elif coin.get_candles('USDT', *timeframes):
                tradingpair = 'USDT'
                print(f'\nServer will start monitoring {coin_symbol}USDT by deafult.')
            else:
                print(f'{coin_symbol} is not avaliable on Binance.2')
                return 0 # Close thread. 
        elif tradingpair:
            # Server already has coin, potentially adding new tradingpair.
            if coin.get_candles(tradingpair, *timeframes):
                print(f'Server will start monitoring {coin_symbol}{tradingpair}.')
            else:
                print(f'{coin_symbol}{tradingpair} is not avaliable on Binance.3')
                return 0 # Close thread. 
        
        files = coin.list_saved_files() # Files may have had additional csv added to it. 
        self.SERVER_INSTRUCTION['added_coin'] = 1 # Notify that a coin, tradingpair or timeframe has been added.
        self.MONITORED_COINS[coin_symbol] = []
        print(f'Server will start monitoring {coin_symbol + tradingpair}.\n') if tradingpair else print(f'Server will start monitoring {coin_symbol}.\n')
        for c in files:
            c = c.split('.')[0]
            self.MONITORED_COINS[coin_symbol].append(c)

        # Thread core, checks for request_interval time every server tick.
        while True:
            self.tickspeed_handler.wait() # Releases every server tick
            if self.SERVER_INSTRUCTION['drop']:
                coin_to_drop = self.SERVER_INSTRUCTION['drop'] # coin specified to drop
                if coin_to_drop == coin.coin_symbol:
                    self.SERVER_INSTRUCTION['drop'] = 0
                    return 0 # Drop thread
            time.sleep(self.SERVER_SPEED / 10) # Allow time for request_interval_handler to update value of SERVER_INSTRUCTION. 
            if self.SERVER_INSTRUCTION['request_interval']:
                coin_score = coin.current_score(1) # Updates database of given coin with latest candles and anaylsis.
                self.server_push(coin_score) # Sends data to webpage.
                if self.SERVER_INSTRUCTION['stdout']:
                    self.MESSAGE_BACKLOG.append(coin_score)

    def monitored_coins(self):
        print(f'Server is currently monitoring:\n\t\t\t')
        for coin in self.MONITORED_COINS:
            print(coin, self.MONITORED_COINS[coin])  


    def request_interval_handler(self):
        '''Used to synchronise all monitor_coin method threads.'''

        while True:
            self.tickspeed_handler.wait() # Releases every server tick.
            self.SERVER_INSTRUCTION['request_interval'] = 1 # Change class variable value.
            time.sleep(self.SERVER_SPEED / 5) # Keep request_interval value at 1 for a short amount of time.
            self.SERVER_INSTRUCTION['request_interval'] = 0
            time.sleep(self.REQUEST_INTERVAL) # Releases every request_interval time. 

    def server_tick_speed(self):
        '''Server speed, every SERVER_SPEED time elapsed, the server object will release the tickspeed_handler event object.'''
        
        while True:
            self.tickspeed_handler.set()
            time.sleep(self.SERVER_SPEED / 10)
            self.tickspeed_handler.clear()
            time.sleep(self.SERVER_SPEED)

    def server_stdout(self):
        '''Handles server stdout (so that thread stdouts don't overlap)'''

        while True:
            self.tickspeed_handler.wait() # Releases every server tick.
            if len(self.MESSAGE_BACKLOG) == 0:
                continue
            messages = self.MESSAGE_BACKLOG
            self.MESSAGE_BACKLOG = [] # Empty message log.

            while True:
                # This is used for when user is actively inputting inputs into server (excluding commands).
                if self.SERVER_INSTRUCTION['pause'] == 1:
                    time.sleep(1) 
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

    def server_user_stdinput(self):
        '''Handles user inputs.'''

        while True:
            user_input = input() # Pauses thread until user input.
            if user_input in self.SERVER_INSTRUCTION:
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
                    self.monitor_new()
                elif user_input == 'all':
                    self.monitor_all_saved_coins()
                elif user_input == 'drop':
                    self.drop_coin()
                elif user_input == 'notify':
                    self.notification_settings()
                elif user_input == 'debug':
                    print(f'Server instruction settings are:\n{self.SERVER_INSTRUCTION}')
            else:
                print(f'{user_input} is an invalid server command.')
                print(f'Enter "commands" to view all avaliable commands.')

    def server_commands(self):
        '''Prints description of each server command.'''
        #TODO
        print(f'\nList of commands: \n')
        print('Enter keyword "monitor coin_symbol coin_name" to monitor additional coins.')
        print(f'')
    #     {"commands": 0, "monitor": 0, 'quit': 0, 'drop': 0, "to_drop": '', "current_score": 0, "monitoring": 0, "add_coin" : 0, "add_tradingpair": 0, 
    # "add_timeframe": 0, "coin_info": 0, "stdout": 1, "server_speed": SERVER_SPEED, 'request_interval': 0}
        pass

    def toggle_stdout(self):
        '''Toggles server stdout'''

        if self.SERVER_INSTRUCTION['stdout'] == 1:
            print('Server stdout has been toggled OFF.')
            self.SERVER_INSTRUCTION['stdout'] = 0
        else:
            print('Server stdout has been toggled ON.')
            self.SERVER_INSTRUCTION['stdout'] = 1

    
    def update_timers(self, timer):
        '''Handles updating server clocks.'''

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
        '''Toggles server speed from normal to responsive'''

        original_SERVER_SPEED = self.SERVER_SPEED
        self.SERVER_SPEED = boost
        self.SERVER_INSTRUCTION['boost'] = boost
        while self.SERVER_INSTRUCTION['boost']:
            time.sleep(boost)
        self.SERVER_SPEED = original_SERVER_SPEED

    def current_monitoring(self):
        '''Returns list of coins, trading pairs and timeframes server is currently monitoring.'''

        print(f'\nServer is currently monitoring:')
        for coin in self.MONITORED_COINS:
            print(f'\ncoin {coin}:')
            for pair in self.MONITORED_COINS[coin]:
                print(pair)
    
    def monitor_new(self):
        '''Handles user input for specifying a new coin, trading pair or timeframe to monitor by the server'''

        self.SERVER_INSTRUCTION['pause'] = 1 # Stops all server stdout for cleaner user interaction.
        while True:
            coin_symbol = str(input('Please input coin symbol to monitor: ')).upper()
            if len(coin_symbol) == 0:
                continue
            break
        while True:
            tradingpairs = str(input('Please input trading pair(s) - seperated by spaces: ')).upper()
            if len(tradingpairs) == 0:
                continue     
            break
        tradingpairs = tradingpairs.split(' ')
        coin_name = str(input('OPTIONAL: input coin name: '))

        monitored_timeframes = {}
        for tradingpair in tradingpairs:
            if tradingpair == ' ':
                continue
            symbol = coin_symbol + tradingpair
            monitored_timeframes[tradingpair] = [] 
            deafult_timeframes = ['1w', '3d', '1d', '4h', '1h']
            for coin in self.MONITORED_COINS:
                for pair in self.MONITORED_COINS[coin]:
                    if symbol == pair.split('_')[0]:
                        monitored_timeframes[tradingpair].append(pair.split('_')[1])
                if len(monitored_timeframes[tradingpair]) > 0:
                    break
        for tradingpair in monitored_timeframes:
            if len(monitored_timeframes[tradingpair]) > 0:
                # This means coin is currently being monitored by server. User can add aditional trading pairs or timeframes.
                print(f'Server is currently monitoring {coin_symbol + tradingpair} with the following timeframes: {monitored_timeframes[tradingpair]}')
                timeframes = input('OPTIONAL: input additional timeframes (seperated by spaces): ')
            else:
                # This means coin entered is currently not being monitored by server (although it could be in the database). 
                print(f'Server will monitor {coin_symbol + tradingpair} with the following timeframes: {deafult_timeframes}')
                timeframes = input('OPTIONAL: input additional timeframes (seperated by spaces): ')
            monitored_timeframes[tradingpair].append(timeframes.split(' '))
        self.SERVER_INSTRUCTION['pause'] = 0 
        for tradingpair in monitored_timeframes:
            self.add_new_coin(coin_symbol, tradingpair, coin_name, monitored_timeframes[tradingpair][-1])
        

    def add_new_coin(self, coin_symbol, tradingpair=None, coin_name=None, timeframes=[]):
        '''Handles adding a new coin, trading pair, or timeframe to monitor by server'''

        self.SERVER_INSTRUCTION['added_coin'] = 0
        Thread(target=self.boost_speed, args=(0.5,), daemon=True).start() # Temporarily increase speed for better responsivness for user.
        if [thread for thread in list_threads() if str(thread).split(',')[0].split('(')[1] == coin_symbol]:
            # Means server currently has activate thread for coin_symbol
            self.SERVER_INSTRUCTION['drop'] = coin_symbol # Drop thread
            self.tickspeed_handler.wait()
            thread = Thread(target=self.monitor_coin, name=coin_symbol, args=(coin_symbol, tradingpair, coin_name, timeframes), daemon=True)
            thread.start()
            while True:
                if self.SERVER_INSTRUCTION['added_coin']:
                    # User entered valid tradingpair, new thread has been created.
                    self.SERVER_INSTRUCTION['added_coin'] = 0
                    break
                elif not thread.is_alive():
                    # User entered invalid tradingpair according to Binance. Revive original thread.
                    print(f'Server found pair {coin_symbol}{tradingpair} is not avaliable on Binance.')
                    Thread(target=self.monitor_coin, name=coin_symbol, args=(coin_symbol,), daemon=True).start()
                    break
                self.tickspeed_handler.wait()
        else:
            # Means server is not currently monitoring this coin, so start new thread. 
            Thread(target=self.monitor_coin, name=coin_symbol, args=(coin_symbol, tradingpair, coin_name, timeframes), daemon=True).start()
        self.SERVER_INSTRUCTION['boost'] = 0 # Turn off boost thread.

    def monitor_all_saved_coins(self):
        '''When invoked, server will start monitoring all coins saved locally'''

        coins = glob(self.data_path) 
        if len(coins) == 0:
            self.monitor_new()
            return 0
        for coin in coins:
            coin = coin.split('/')[-1]
            self.add_new_coin(coin)
    
    def drop_coin(self):
        '''Handles dropping a coin, tradingpair or timeframe from being monitored and removes from database if requested'''
        pass
        #TODO

    def server_listen(self):
        '''Listens for any request via server IP/PORT.'''

        # bind socket etc. This method thread would only be used if you have this server actually running a web page, and from the browser CLIENT (i.e the client
        # is already made for you) this method will capture and interpret the HTTP requests and process them appropriately, Via the webpage we will make using HTML/Javascript
        pass

    def server_push(self, data):
        '''Sends push request to webpage with new data.'''
        pass

    def notification_settings(self):
        '''Handles modifying server notification settings'''

        pass
    
    def notify(self):
        '''Handles server notification'''

        pass


    def shutdown_server(self):
        '''When keyword >quit< or HTTP requires 2.0 is receieved, server will shutdown.'''

        print('Server is shutting down...')
        self.server_shutdown.set() # Set event object flag as ON.

# Server can be started with <python3 notification_server.py>
# Optional coin_symbols can be added, example: <python3 notification_server.py BTC LTC ETH INJ>
# Once the server is running, to view commands enter <commands> 
user_start_arguments = sys.argv
if len(user_start_arguments) > 0:
    if len(user_start_arguments) == 1:
        server = Notification_server()
    elif len(user_start_arguments) > 1:
        coins = user_start_arguments[1:]
        server = Notification_server(coin_symbols=coins)
    server.server_shutdown.wait() # Pauses main thread until shutdown_server method is invoked.
else:
    print("Invalid entry, please run server with following format: 'python3 notification_server.py coin_symbol coin_name 5' (final argument optional)")

print("Server shut down.")
# Main thread ends here. 