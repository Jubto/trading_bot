# trading_bot
Trading bot server project (incomplete) 

# Server overview:

Server initiation:

![image](https://user-images.githubusercontent.com/71308285/111856442-cf325900-897e-11eb-8024-af6aef6e2673.png)

If this is the first time using the server, the user will be prompted to add any coins they would like to monitor. The image bellow is an example where the user chooses to monitor two coins (INJ and DOGE), selects their respective trading pairs (INJ-BTC, INJ-USDT, DOGE-BTC, DOGE-USDT, DOGE-AUD), and each trading pairs respective timeframes:

![image](https://user-images.githubusercontent.com/71308285/111856494-3fd97580-897f-11eb-8445-a1f810223c71.png)

The historical candlestick data for each pair is then stored in the server database, subsequent logins will allow you to choose whether to monitor these stored coins, or add new ones:

![image](https://user-images.githubusercontent.com/71308285/111856817-74e6c780-8981-11eb-89e6-c7490d500251.png)

Each csv contains a header which tells the server what it's most recent candlestick was, allowing for the server to efficently retreive only the lastest candlestick data from the Binance API.

Each json file contains ordered lists of various percentage changes assoicated with the csvs. When the server retreives new candle data, it computes that csvs various percentage changes, and compares those with the ordered lists within the json to determine the csvs ranking. A high ranking would suggest the lastest csvs (i.e. the current price action) is abnormally high, or abnormally low (bearish case), and this ranking is used to determine a scoring. 

When the user wants to have an update on their monitored coins, they can use the 'post' command. Currently, this command will return json summary data of each coin trading pair, along with the current scores - in future, this command will be updated to return a saved csv file which the user can view. The immage bellow is an example of one of the json objects returned to stdout (one out of many)

![image](https://user-images.githubusercontent.com/71308285/111859125-88e6f500-8992-11eb-9af4-414e9e72d527.png)

If the user would like to stop monitoring one 


#TODO Windows/pushbullet notification functionaility

#TODO Historical score and % amp/change analysis and storage

#TODO Graphing of historical and current analysis

#TODO Determining optimal notification settings based on historical data

  #TODO implement ML algo to determine best settings for a given coin - using profit as a heuristic 

#TODO Possibly add older exchanges with more historical data

#TODO Webpage to interact with server

#TODO Possibly add emergency trading functionaility 

#TODO Make a clear readme doc with images of commands and the outputs (coindata, csvs, json, graphs)
