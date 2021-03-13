

###############
# TODO Work will commence on this after MAY 2021 
# RESTful server 
# Currently focused on notification_server.py, get_candles.py, and notification_scripts
###############


import socket


class Webserver():
    '''
    This class will handle a website to view and use all the features provided by class Notification_server 
    '''

    PORT = 13337
    IP_ADDRESS = socket.gethostbyname(socket.gethostname())

    def __init__(self):
        pass

    
    def server_connect(self):
        '''Handles the establishment of connection with browser client'''
        pass


    def server_listen(self):
        '''Thread which listens for any request via server IP/PORT.'''

        # Listens for browser client 
        # This method will capture and interpret the HTTP requests and process them appropriately, Via the webpage we will make using HTML/Javascript
        pass

    def server_push(self, data):
        '''Sends push request to webpage with new data'''

        pass