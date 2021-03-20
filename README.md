# trading_bot
Trading bot server project (in progress) 

# Server overview:

Server initiation:

![image](https://user-images.githubusercontent.com/71308285/111856442-cf325900-897e-11eb-8024-af6aef6e2673.png)

####Coin monitoring, posting and dropping

######Coin monitoring

If this is the first time using the server, the user will be prompted to add any coins they would like to monitor. The image bellow is an example where the user chooses to monitor two coins (INJ and DOGE), selecting their respective trading pairs (INJ-BTC, INJ-USDT, DOGE-BTC, DOGE-USDT, DOGE-AUD), and each trading pairs respective timeframes:

![image](https://user-images.githubusercontent.com/71308285/111856494-3fd97580-897f-11eb-8445-a1f810223c71.png)

The historical candlestick data for each pair is then stored in the server database, and subsequent logins will allow you to choose whether to monitor these stored coins, or add new ones:

![image](https://user-images.githubusercontent.com/71308285/111856817-74e6c780-8981-11eb-89e6-c7490d500251.png)

Each csv contains a header which tells the server what its most recent candlestick was, allowing for the server to efficiently retrieve only the latest candlestick data from the Binance API. 

Each json file contains ordered lists of various percentage changes associated with the csvs. When the server retrieves new candle data, it computes its various percentage changes, and compares those with the ordered lists within the json to determine the current price actions ranking. A high ranking would suggest the latest price action is abnormally  aggressively high, or abnormally low (bearish case), and this ranking is used to determine a scoring. 

When the user wants to have an update on their monitored coins, they can use the 'post' command. Currently, this command will return json summary data of each coin trading pair, along with the current scores - in future, this command will be updated to return a saved csv file which the user can view. The image bellow is an example of one of the json objects returned to stdout (one out of many)

######post

![image](https://user-images.githubusercontent.com/71308285/111859206-3f4ada00-8993-11eb-9792-18cc98dfe069.png)

Each trading pair (in this case INJUSDT) has all their timeframes, with each timeframe having four metrics (candle_change, candle_amp, candle_up, candle_down). Many of the ranks are 100, meaning if those timeframes were to close that very instant, they would rank the most poorly amongst all historical candles of that timeframe. However since most of these timeframes still have much time before they actually close, it is unlikely they will remain as rank 100 overtime. Some timeframes have 'AVERAGE', meaning their rank is between rank 20 - 80. The timeframes with 'NA' mean situations where for example, the candle has a negative % change, and the metric is for positive % change.

The only metrics which contribute to the scores are 'candle_max_up' and 'candle_max_down'. When candle_max_up metric has a rank of above 20, it will start adding up a bull score. A rank above 20 indicates that for that current timeframe, if it were to close this instant, it would place amongst the top 20 max% closes compared with all historical candles of that timeframe. If its rank is 15, the score is greater, and so on. The same applies to candle_max_down, however the scores are added to the bear score.

If multiple timeframes of a given coin suddenly starts accumulating scores, this will raise the overall score to a point where it may trigger the server notification process (covered later). Having a high bull score therefore means the coin is currently experiencing a very aggressive price increase, one which may be considered unsustainable, especially when looking at the rankings of the lower timeframes, and by looking at all the metrics/timeframes combined can give the user an indication of whether to sell or do nothing.

Eventually machine learning will be implemented to determine a better scoring system and sensitivity to further aid the user's choices.

######dropping

The user will have the ability to stop monitoring certain pairs, or drop the coin from the server database (only server owner can do this). Using the command "drop":

![image](https://user-images.githubusercontent.com/71308285/111863163-fb190300-89ad-11eb-8c2c-934d71cfa1d1.png)

Here the pair INJBTC_12h, INJUSDT_1M, and all of DOGEBTC are dropped from server monitoring, while all the pairs of DOGEAUD and the pair of DOGEUSDT_6h are dropped from the server database. The changes to the database can be seen in the image bellow (note the json file also has it's associated data updated)

![image](https://user-images.githubusercontent.com/71308285/111863187-1d128580-89ae-11eb-8c84-0495a9a6b847.png)

To see what the server is actively monitoring, use the "monitoring" command. It will only show pairs which have been requested to monitor, so not all database pairs will be shown (e.g. DOGEBTC which was dropped above)

![image](https://user-images.githubusercontent.com/71308285/111863202-30255580-89ae-11eb-9337-432346116c6b.png)


####Server notification service

In order to start the server notification service, use the command "notify". If this is the first time using the command, and the user does not have postfix installed, the server will run a script to set up the postfix server.

![image](https://user-images.githubusercontent.com/71308285/111863215-43382580-89ae-11eb-80dc-359129b3703e.png)

Once installed, another script will run to configure the postfix server, and then prompt the user to enter some details. First, the user will need to create a new Gmail account with the sole purpose of handling communications with this trading bot server. This Gmail account needs to have its 'less secure app access' switched on. The server will use this Gmail as a means of both inward and outwar communication.

![image](https://user-images.githubusercontent.com/71308285/111863239-682c9880-89ae-11eb-941a-476980c37ba5.png)

######Multiple users

The server is capable of supporting multiple users. The first user is the server owner (i.e. the user who is running the server), and any subsequent users can be added either by the server owner, or by the server receiving a join request via its Gmail (TODO). 

Each user can monitor their own set of coins, and will only receive their respective mode 1 or mode 2 emails (explained below). Each email will be about a specific coin, and only users which have elected those coins to monitor will receive the emails.

######Two different email modes

* Mode 1 emails are outbound emails which are only generated and sent if the server detects one of its monitored coins pass the score threshold. This threshold can either manually chosen, or eventually, it will be determined through machine learning. If the score continues to rise, an email will be sent for each rise. 
* Mode 2 emails are periodic outbound emails sent to the users. The frequency the emails are sent can be modified or turned off. 

Both emails will contain csv and graph data.

An example mode 2 email which was sent from the postfix server initiation above is shown below:

![image](https://user-images.githubusercontent.com/71308285/111863272-a1fd9f00-89ae-11eb-9529-674173133036.png)



#TODO complete server multi-user functionaility and inbound email command functionaility

#TODO Historical score and % amp/change analysis and storage using pandas

#TODO Graphing of historical and current analysis using matplotlib

#TODO Determining optimal notification settings based on historical data

  #TODO implement ML algo to determine best settings for a given coin - using profit as a heuristic 

#TODO Possibly add older exchanges with more historical data

#TODO Webpage to interact with server

#TODO Possibly add emergency trading functionaility 

#TODO Make a clear readme doc with images of commands and the outputs (coindata, csvs, json, graphs)
