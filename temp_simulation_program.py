import pandas as pd
import csv

symbol = 'ETHUSDT'
top_x = 20
delay_trading = 1 #weeks *
stats_path = f'/home/jubto/projects/testings/{symbol}_historical_scoring.csv'
historical_DF = pd.read_csv(stats_path, index_col= 0, usecols=[0, 1, 2, 3, 4], header=None, skiprows=1)

def add_to_analysis(analysis_cols, strat, holdings, uts, prev_price, price, action):

    coin_holdings, coin_profit, coin_gain, pair_holdings, pair_profit, pair_gain = 0, 0, 0, 0, 0, 0
    if prev_price == 0:
        prev_price = price
    # print(f'{gcount} {uts} {strat} inital holding: {holdings}, prev price: {prev_price}, current price: {price}, action: {action}')
    if action == 'BUY':
        coin_holdings = round(holdings / price, 5)
        coin_profit = round(coin_holdings - (holdings / prev_price), 5)
        coin_gain = round((prev_price / price)*100 - 100, 3)
        # print(f'New holding COIN: {coin_holdings}, coin profit: {coin_profit}, coin gain: {coin_gain}')
    else:
        pair_holdings = round(holdings * price, 5)
        pair_profit = round(pair_holdings - (holdings * prev_price), 5)
        pair_gain = round((price / prev_price)*100 - 100, 3)
        # print(f'New holding PAIR: {pair_holdings}, pair profit: {pair_profit}, pair gain: {pair_gain}')
    analysis_cols[strat].append([uts, prev_price, price, action, coin_holdings, pair_holdings, coin_profit, pair_profit, coin_gain, pair_gain])
    analysis_cols[f'{strat}_holdings_log'].append(coin_holdings)

    
# TODO this can all be a function, which takes in a bull/bear_threshold range, so you can use it for just 1 combination for like graphing
# Have like two modes, single combination which returns something, or mass scan which produces some csv
# single mode takes in two parameters, bull score and bear score, which you can use the range +1
# The reason you want this is for overlayying the signals against the PA candle stick graph
# overall theory is, we want to see whether there's a clear bear mode and clear bull mode threshold settings, which you can toggle depending on the market

# implement a delay in starting, e.g. start trading after at least 2 weeks etc.

with open(f'/home/jubto/projects/testings/{symbol}_historical_scoring.csv', 'r') as f:
    cols = f.readline()

max_threshold = int((len(cols.split(',')) - 6)*3)
trading_pair = 'USDT'
inital_coin_price = historical_DF.iloc[0, 0]
inital_pair_holdings = 10000 if trading_pair in ['USDT', 'BUSD'] else 5
inital_coin_holdings = round(10000 / inital_coin_price, 3)
start_uts = historical_DF.iloc[0].name
final_uts = historical_DF.iloc[-1].name
delay_trading *= 2016
summary = {'overall':{}, 'max':{}}
analysis_cols = {}
strict = True

for bull_threshold in range(2, max_threshold):
    for bear_threshold in range(2, max_threshold):
        move_made = False
        signal = ''
        prev_signal = 'SELL'
        prev_bull_peak = 0
        prev_bear_peak = 0
        prev_price = 0
        holdings = 10000 if trading_pair in ['USDT', 'BUSD'] else 5 # Alternates between coin and pair.

        strat = f'BULL:{bull_threshold}|BEAR:{bear_threshold}'
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

        for row in historical_DF.iloc[delay_trading:].itertuples(name=None):
            bull_score = row[2] # i.e. massive surge up, hence you want to SELL
            bear_score = row[3] # i.e. massive surge down, hence you want to BUY
            if bull_score >= bull_threshold and bear_score >= bear_threshold:
                continue # indecision
            if strict:
                if bull_score >= bull_threshold and bull_score > bear_score:
                    signal = 'SELL'
                elif bear_score >= bear_threshold and bear_score > bull_score:
                    signal = 'BUY'
            else:
                if bull_score >= bull_threshold:
                    signal = 'SELL'
                elif bear_score >= bear_threshold:
                    signal = 'BUY'
            if prev_signal != signal:
                if bull_score >= bull_threshold or bear_score >= bear_threshold:
                    if not move_made:
                        move_made = True
                        add_to_analysis(analysis_cols, strat, holdings, row[0], prev_price, row[1], signal)
                        holdings = analysis_cols[strat][-1][4] if analysis_cols[strat][-1][4] else analysis_cols[strat][-1][5]
                        prev_price = row[1]
                        prev_bull_peak = bull_score
                        prev_bear_peak = bear_score
                elif prev_bull_peak >= bull_threshold or prev_bear_peak >= bear_threshold:
                    prev_signal = signal
                    prev_bull_peak = 0
                    prev_bear_peak = 0
                    move_made = False            
        summary['overall'][strat] = analysis_cols[strat][-1][4] if analysis_cols[strat][-1][4] else analysis_cols[strat][-2][4]
        summary['max'][strat] = max(analysis_cols[f'{strat}_holdings_log'])

sorted_summary = {'overall':{}, 'max':{}}
sorted_summary['overall'] = {k: v for k, v in sorted(summary['overall'].items(), key=lambda kv: kv[1], reverse=True)}
sorted_summary['max'] = {k: v for k, v in sorted(summary['max'].items(), key=lambda kv: kv[1], reverse=True)}
# [print(f'{mode}\n{data}') for mode, data in sorted_summary.items()]

for metric, sorted_strats in sorted_summary.items():
    with open(f'/home/jubto/projects/testings/simulation_tests/{symbol}_top{top_x}_{metric}.csv', 'w') as f:
        csv_writer = csv.writer(f, delimiter=',')
        csv_writer.writerow(['inital_coin', inital_coin_holdings, 'inital_pair', inital_pair_holdings, 'start_uts', start_uts, 'final_uts', final_uts])
        for rank, strat in enumerate(sorted_strats, start=1):
            for row in analysis_cols[strat]:
                csv_writer.writerow(row)
            if rank == top_x:
                break


# sorted_summary =  {k: v for k, v in sorted(summary['overall'].items(), key=lambda kv: kv[1])}
# # print(sorted_summary)
# with open('/home/jubto/projects/testings/900_simulation_INJUSDT_TEST3.txt', 'w') as f:
#     print(sorted_summary, file=f)
# [print(f'{col}\n{data}') for col, data in sorted_summary.items()]

# with open('/home/jubto/projects/testings/temp.txt', 'w') as f:
#     print(analysis_cols, file=f)
# [print(f'threshold: {col}: {analysis_cols[col]["coin_holdings"][-1:-4:-1]}') for col in analysis_cols]


# [print(f'\n{strat} len:{len(analysis_cols[strat]["coin_holdings"])}\ncoin_holding:\n{analysis_cols[strat]["coin_holdings"]}\npair_holding:\n{analysis_cols[strat]["pair_holdings"]}') for strat in analysis_cols]
# print(analysis_cols['BULL:3 | BEAR:2']['coin_holdings'])
# print(summary_max)
# print(sum(analysis_cols['BULL:14 | BEAR:3']['action_coin_profit']))
# print(len(analysis_cols['BULL:15 | BEAR:3']['action']))
# [print(f'\n{col}\n{data}\n') for col, data in analysis_cols['BULL:15 | BEAR:3'].items()]

# sorted_summary_max =  {k: v for k, v in sorted(summary['max'].items(), key=lambda kv: kv[1])}
# print(sorted_summary_max)
