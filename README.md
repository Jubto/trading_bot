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

When the user wants to have an update on their monitored coins, they can use the 'post' command. Currently, this command will return json summary data of each coin trading pair, along with the current scores - in future, this command will be updated to return a saved csv file which the user can view. The image bellow is an example of one of the json objects returned to stdout (one out of many)

![image](https://user-images.githubusercontent.com/71308285/111859206-3f4ada00-8993-11eb-9792-18cc98dfe069.png)

Each tradingpair (in this case INJUSDT) has all their timeframes, with each timeframe having four metrics (candle_change, candle_amp, candle_up, candle_down)
Many of the ranks are 100, meaning if those timeframes were to close that very instant, they would rank the most poorly amongst all historical candles of that timeframe. However since most of these timeframes still have much time before they actually close, it is unlikely they will remain as rank 100 overtime. Some timeframes have 'AVERAGE', meaning their rank is between rank 20 - 80. The timeframes with 'NA' mean situations where for example, the candle has a negative % change, and the metric is for positive % change.

The only metrics which contribute to the scores are 'candle_max_up' and 'candle_max_down'
When candle_max_up metric has a rank of above 20, it will start adding up a bull score. A rank above 20 indicates that for that current timeframe, if it were to close this instant, it would place amongst the top 20 max% closes compared with all historical candles of that timeframe. If its rank is 15, the score is greater, and so on.
The same applies to candle_max_down, however the scores are added to the bear score.

If multiple timeframes of a given coin suddenly starts accumulating scores, this will raise the overall score to a point where it may trigger the server notification process (covered later). Having a high bull score therefore means the coin is currently experiencing a very aggressive price increase, one which may be considered unsustainable, especially when looking at the rankings of the lower timeframes, and by looking at all the metrics/timeframes combined can give the user an indication of whether to sell or do nothing.

Eventually machince learning will be implmented to determine a better scoring system and sensitivity to futher aid the user's choices. 






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
