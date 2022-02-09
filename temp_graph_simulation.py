import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from enums import BEAR_MARKETS, BULL_MARKETS
import csv

symbol = 'ETHUSDT'
coin = [symbol.split(tradingpair)[0] for tradingpair in ['USDT', 'BUSD', 'BTC', 'ETH'] if tradingpair in symbol][0]
tradingpair = symbol.split(coin)[-1]
mode = 'strict'
top_x = 20

fig, (ax_overall, ax_pair, ax_max) = plt.subplots(nrows= 3, ncols= 1, figsize=(25, 21))
for metric in ['overall', 'max']:
    with open(f'/home/jubto/projects/testings/simulation_tests/{symbol}_top{top_x}_{metric}.csv', 'r') as f:
        header = f.readline().split(',')
        inital_coin_holding = float(header[1])
        inital_pair_holding = float(header[3])
        start_uts = datetime.fromtimestamp(int(header[5][:-3]))
        final_uts = datetime.fromtimestamp(int(header[-1].strip()[:-3]))
        bear_markets = []
        bull_markets = []
        for bear_market in BEAR_MARKETS:
            bear_market_start, bear_market_end = bear_market
            if (bear_market_start - final_uts).days > 0:
                continue # bear market out of range
            if (start_uts - bear_market_end).days > 0:
                continue # bear market out of range
            if (start_uts - bear_market_start).days > 0:
                bear_market_start = start_uts
            if (bear_market_end - final_uts).days > 0:
                bear_market_end = final_uts
            bear_markets.append([bear_market_start, bear_market_end])
        for bull_market in BULL_MARKETS:
            bull_market_start, bull_market_end = bull_market
            if (bull_market_start - final_uts).days > 0:
                continue # bull market out of range
            if (start_uts - bull_market_end).days > 0:
                continue # bull market out of range
            if (start_uts - bull_market_start).days > 0:
                bull_market_start = start_uts
            if (bull_market_end - final_uts).days > 0:
                bull_market_end = final_uts
            bull_markets.append([bull_market_start, bull_market_end])
        csv_reader = csv.reader(f)
        uts_holdings = {}
        strat = ''
        for row in csv_reader:
            uts = row[0]
            coin_holding = row[4]
            pair_holding = row[5]
            if coin_holding == '0':
                if metric != 'overall':
                    continue
                uts_holdings[strat]['pair_uts'].append(datetime.fromtimestamp(int(uts[:-3])))
                uts_holdings[strat]['pair_holding_gains'].append(round((float(pair_holding) / inital_pair_holding)*100 - 100, 2))
            elif 'UTS' in uts:
                strat = uts.split('_')[-1]
                uts_holdings[strat] = {'coin_uts':[], 'coin_holding_gains':[], 'pair_uts':[], 'pair_holding_gains':[]}
            else:
                uts_holdings[strat]['coin_uts'].append(datetime.fromtimestamp(int(uts[:-3])))
                uts_holdings[strat]['coin_holding_gains'].append(round((float(coin_holding) / inital_coin_holding)*100 - 100, 2))
        if metric == 'overall':
            # plotting for overall best performing thresholds for coin
            for strat, data in uts_holdings.items():
                ax_overall.plot(data['coin_uts'], data['coin_holding_gains'], label=f'{strat:16} {len(data["coin_uts"])}')
                ax_pair.plot(data['pair_uts'], data['pair_holding_gains'], label=f'{strat:16} {len(data["pair_uts"])}')
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
        else:
            # plotting for highest max gains achieved thresholds
            for strat, data in uts_holdings.items():
                ax_max.plot(data['coin_uts'], data['coin_holding_gains'], label=f'{strat:16} {len(data["coin_uts"])}')
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

ax_overall.set_title(f"{symbol}: {coin} trading graph overall best {coin} gain thresholds", fontweight="demi", size="xx-large", y=1.025)
ax_overall.set_ylabel(f"% {coin} gain from inital", fontweight="demi", size="xx-large")
ax_overall.legend(title=f"Top {top_x} strats", title_fontsize="x-large", fontsize='large', shadow=True, fancybox=True, bbox_to_anchor=(1.025, 1.025))

ax_pair.set_title(f"{symbol}: {tradingpair} trading graph for overall best {coin} gain thresholds", fontweight="demi", size="xx-large", y=1.025)
ax_pair.set_ylabel(f"% {tradingpair} gain from inital", fontweight="demi", size="xx-large")
ax_pair.set_xlabel("Time", fontweight="demi", size="x-large")
ax_pair.legend(title=f"Top {top_x} strats", title_fontsize="x-large", fontsize='large', shadow=True, fancybox=True, bbox_to_anchor=(1.02, 1.025))

ax_max.set_title(f"{symbol}: {coin} trading graph for highest max {coin} gain thresholds", fontweight="demi", size="xx-large", y=1.025)
ax_max.set_ylabel(f"% {coin} gain from inital", fontweight="demi", size="xx-large")
ax_max.set_xlabel("Time", fontweight="demi", size="x-large")
ax_max.legend(title=f"Top {top_x} strats", title_fontsize="x-large", fontsize='large', shadow=True, fancybox=True, bbox_to_anchor=(1.02, 1.025))

plt.tight_layout(pad=2) 
plt.savefig(f"/home/jubto/projects/testings/simulation_tests/graphs/{symbol}_{mode}_graph_TESTing3.png")
