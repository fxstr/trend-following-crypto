# -*- coding: utf-8 -*-
# ---
# jupyter:
#   jupytext:
#     custom_cell_magics: kql
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.11.2
#   kernelspec:
#     display_name: Python 3
#     language: python
#     name: python3
# ---

# %% [markdown]
# - Make sure that you get new data first (fetch_coinapi.ipynb)
# - Make sure to update the index (create_index.ipynb)

# %%
# %reload_ext autoreload
# %autoreload 2

import pandas as pd
import time
import coinbase_reader
from matplotlib import pyplot as plt
import backtest
import simple_regression
import numpy as np
import ledoit_wolf
import os
from dotenv import load_dotenv
from pathlib import Path
# from pypfopt import HRPOpt, expected_returns, risk_models

load_dotenv()

base_dir = Path.cwd()
exchange = os.getenv('COINAPI_EXCHANGE')
base_currency = os.getenv('COINAPI_BASE_CURRENCY')

# %%
index = pd.read_csv('./index.csv', index_col=0, parse_dates=True)
# Index must be normalized for bt to work (in Binance where the index consists of very high numbers)
index = index / index.iloc[0] * 100  # Normalize to start at 100                                                                                    
index.name = 'value'
print(f'Got index with length {len(index)}')
index.plot(figsize=(16, 4))

# %%
# Benchmark: Our index
import bt
strategy = bt.Strategy(
    'benchmark',
    [
        bt.algos.RunOnce(),
        bt.algos.SelectAll(),
        bt.algos.WeighEqually(),
        bt.algos.Rebalance(),
    ],
)
test = bt.Backtest(strategy, index, initial_capital=100000)
result = bt.run(test)
result.display()
result.plot()

# %%
# The paper below favors 28 days as a lookback period and a 5-day holding period. Adding longer
# periods just takes more time, but does not improve the result.
lookback_periods = [10, 20, 30, 45, 60, 75]
index_cagrs = [
    index.rolling(window=lb).apply(simple_regression.create_regression('cagr'))
    for lb in lookback_periods
]
# index_r2s = [
#     index.rolling(window=lb).apply(simple_regression.create_regression('r2'))
#     for lb in lookback_periods
# ]

# %%
# Get the mean for the CAGRs and decide when we should go long
mean_cagrs = sum(index_cagrs[:]) / len(index_cagrs[:])
# Only preserve the cells in which there's cagr data for *all* lookback periods (period 10 has
# more data than 75 because the window starts earlier) – use the last lookback period as mask.
mean_cagrs = mean_cagrs[index_cagrs[-1].notna()]
# Terribly dangerous: Never bfill; this would apply future's knowledge to today's data. Always
# ffill (newer dates are lower down in our df)
# Drop all weekdays without data
cleaned_mean_cagrs = mean_cagrs.dropna()

# binary = [np.sign(df).dropna() for df in index_cagrs]
# binary_sum = sum(binary)
# binary_long = binary_sum >= len(lookback_periods)
# print(f'Binary long: {len(binary_long[binary_long].dropna())}')

# Adding r2 does not improve anything
# mean_r2s = sum(index_r2s) / len(index_r2s)
# mean_r2s = mean_r2s[index_r2s[-1].notna()].dropna()

# Go long when cagr is in the top third (compared to the past)
# Inspiration: https://acfr.aut.ac.nz/__data/assets/pdf_file/0009/918729/Time_Series_and_Cross_Sectional_Momentum_in_the_Cryptocurrency_Market_with_IA.pdf
# q67 = cleaned_mean_cagrs.expanding().quantile(0.75)
# Don't look back too far: If the past was too good, there won't be any positions in the future. 
# 100 equals 2 years as we have weekly data (100 weeks = 700 days = 2 years)
best_percent = cleaned_mean_cagrs.rolling(window=50).quantile(2/3)

# Also make sure that values are above/below 0, do not just use the relative ranking.
# Adding r2 (e.g. > 0 or > 0.5) does not improve anything.
is_top = (cleaned_mean_cagrs >= best_percent) & (cleaned_mean_cagrs > 0)
# Buying on growing CAGR does not improve anything
# & (cleaned_mean_cagrs > cleaned_mean_cagrs.shift(1))
go_long = is_top.astype(int)

print('Go long:')
print(go_long)

fig, ax = plt.subplots(3, 1,figsize=(15, 6), sharex=True, gridspec_kw={'height_ratios': [2, 3, 1]})
start = '2022-06-01'
end = None
ax[0].plot(index.loc[start:end])
cagrs_to_plot = cleaned_mean_cagrs['value']
cagrs_to_plot = cagrs_to_plot.loc[start:end].reindex(index.loc[start:end].index).ffill()
ax[1].bar(cagrs_to_plot.index, cagrs_to_plot.values)
ax[1].plot(best_percent[start:end], color='red')
ax[2].plot(go_long.loc[start:end])
plt.show()

print('Mean CAGRs - best percentile\nWe go long if > 0 (and if mean CAGR is > 0)')
print((cleaned_mean_cagrs - best_percent).iloc[-10:])

# %%
# See how we'd perform if we held the index on good times (top CAGR periods)
index_result = backtest.run('ledoit_wolf', index, go_long)
index_result.display()

index_rolling_max = index_result.prices.cummax()
index_drawdowns = (index_result.prices - index_rolling_max) / index_rolling_max

fig, ax = plt.subplots(4, 1,figsize=(16, 12), sharex=True)
index_result.prices.plot(ax=ax[0])
index.plot(ax=ax[1])
# ax[1].bar(mean_cagrs['value'].index, mean_cagrs['value'].values)
ax[2].plot(mean_cagrs.ffill())
ax[2].plot(best_percent, color='red')
index_drawdowns.plot(ax=ax[3])
plt.show()

# %%
# If we're not going long, we can stop here (no complex calculations and distribution needed)
# if go_long.iloc[-1].item() == 0:
#     sys.exit("Stopping execution because condition is met")

# Calculate CAGR / R2 for all index constituents
index_weights = pd.read_csv('index_weights.csv', index_col=0, parse_dates=True)
# Drop all cols that dont belong to the index
index_weights = index_weights.dropna(axis=1, how='all')
# Forward-fill so we know the index membership on any given date (index rebalances are sparse).
# Never bfill – that would introduce future knowledge.
index_weights_ffilled = index_weights.ffill()
# We calculate the CAGR for all constituents as we need them in the past; further down, we'll
# only use the index constituents of the given date.
constituent_names = index_weights.columns.to_list()

data_dir = os.path.join(base_dir, f'../{exchange.lower()}_data/')
print(f'Data dir is {data_dir}')
closes = coinbase_reader.read('close', data_dir=data_dir, exchange=exchange, base_currency=base_currency)
constituent_closes = closes[constituent_names]

print(f'Use {len(constituent_closes.columns)} cryptos with {len(closes)} rows')

# For simple experiments, limit our dataset
# lookback_periods = [75]
# constituent_closes = closes[['ETH']]

constituent_cagrs = []
# constituent_r2s = []
for lb in lookback_periods:
    start_time = time.time()
    print(f'Starting lookback period {lb} …')
    constituent_cagrs.append(
        constituent_closes.rolling(window=lb).apply(simple_regression.create_regression('cagr'))
    )
    # constituent_r2s.append(
    #     constituent_closes.rolling(window=lb).apply(simple_regression.create_regression('r2'))
    # )
    print(f'Lookback period {lb} done after {round(time.time() - start_time)} seconds')

# %%
# fig, ax = plt.subplots(2, 1, figsize=(15, 6), sharex=True)
# ax[0].plot(constituent_closes[['ETH', 'BTC']].loc[start:end])
# ax[1].plot(constituent_cagrs[0][['ETH', 'BTC']].loc[start:end].ffill())
# plt.show()

# %%
# With lookback period 10, we have more data than with lookback period 75. Why? Because we can
# start our calculations earlier (after 10 rows of non-nan data). Make sure we only preserve cells
# that have data in *all* lookback periods.
cagr_mask = np.logical_and.reduce([~df.isna() for df in constituent_cagrs])
# Apply the mask to each df
cleaned_constituent_cagrs = [df.where(cagr_mask) for df in constituent_cagrs]
mean_constituent_cagrs = sum(cleaned_constituent_cagrs[:]) / len(cleaned_constituent_cagrs[:])
mean_constituent_cagrs = mean_constituent_cagrs.dropna(how='all')

# r2_mask = np.logical_and.reduce([~df.isna() for df in constituent_r2s])
# cleaned_constituent_r2s = [df.where(r2_mask) for df in constituent_r2s]
# mean_constituent_r2s = sum(cleaned_constituent_r2s) / len(cleaned_constituent_r2s)
# mean_constituent_r2s = mean_constituent_r2s.dropna(how='all')

# Create default weights table with value 0
weights = pd.DataFrame(index=go_long.index, columns=constituent_names)
weights[:] = 0

# Window of 50 = 1 year lookback
# crypto_percentiles = mean_constituent_cagrs.rolling(window=100).quantile(0.75)

# up_cagrs = mean_constituent_cagrs > mean_constituent_cagrs.shift(1)

# Whenever the index tells us to go long, get the best performing cryptos (that are part of the
# index) at that time. 
# go_long is a df, we only need the first column (therefore the brackets).
for date, [is_long] in go_long.iterrows():
    if is_long == 1:
        # Get the best performing cryptos, restricted to index members at this date.
        # Use the last known index composition (ffilled) to avoid look-ahead bias.
        current_index_members = index_weights_ffilled.loc[:date].iloc[-1].dropna().index
        current_cagrs = mean_constituent_cagrs.loc[date]
        current_cagrs = current_cagrs[current_cagrs.index.isin(current_index_members)]

        # current_r2s = mean_constituent_r2s.loc[date]
        # current_cagrs = current_cagrs[current_r2s > 0.2]
        # top_cagrs = current_cagrs[current_cagrs > crypto_percentiles.loc[date]]
        best_cryptos = current_cagrs.sort_values(ascending=False)

        best_cryptos = best_cryptos.dropna()
        # Remove all cryptos with a cagr < x; why x=2? Because it works well.
        # best_cryptos = best_cryptos[best_cryptos > 2]
        best_cryptos = best_cryptos[:10]
        # Reduce weights of single instruments
        # best_cryptos = best_cryptos ** 0.5
        # Equal weights
        # best_cryptos[:] = 1
        # Normalize to sum of 1
        # print(f'Best performing on {date.date()}: {best_cryptos.to_dict()}')

        ledoit_period = pd.Timedelta(days=100)
        data_for_ledoit = constituent_closes.loc[date-ledoit_period:date, best_cryptos.index]

        ledoit_weights = ledoit_wolf.calculate_weights(data_for_ledoit)
        # print('Max Div', best_cryptos.index.to_list(), ledoit_weights)

        # changes = data_for_ledoit.pct_change().dropna()
        # cov_matrix_lw = risk_models.CovarianceShrinkage(data_for_ledoit).ledoit_wolf()

        # if (len(changes.columns) == 1):
        #     hrp_weights = [1]
        # else:
        #     hrp = HRPOpt(returns=changes, cov_matrix=cov_matrix_lw)
            # HRP.optimize returns an OrderedDict; just get the list of values.
        #     hrp_weights = list(hrp.optimize().values())
        # print('HRP', best_cryptos.index.to_list(), hrp_weights)

        # You can drop in hrp_weights here – but it does not improve anything
        weights.loc[date, best_cryptos.index] = ledoit_weights

        # best_cryptos = best_cryptos / best_cryptos.sum()
        # weights.loc[date, best_cryptos.index] = best_cryptos.values

# No weight over 25%, ever
# Does not improve anything.
# weights[weights > 0.2] = 0.2


weights.to_csv('weights.csv')

weights.plot(figsize=(16, 4), legend=False)
plt.show()

last_weights = weights[-50:]
last_weights.index = last_weights.index.date
# Drop all cols only containing 0
last_weights = last_weights.loc[:, (last_weights != 0).any(axis=0)]
last_weights.plot(kind='bar', stacked=True, figsize=(16, 4), legend=False)
plt.show()

# %%
current_weights = weights.iloc[-1]
current_weights = current_weights[current_weights != 0]
percentages = [f'{label}: {(value * 100):.1f}%' for (label, value) in current_weights.items()]
print(f'Current weights on {current_weights.name}: {percentages}')
current_balance = 32_300
current_distribution = [f'{label}: {value:.0f}' for (label, value) in (current_balance * current_weights).items()]
print(f'Current distribution:\n{current_distribution}')

# %%
# Make very sure that we have weights on all dates that we could trade because there's date to 
# do so.
# Terribly dangerous: Never bfill; this would apply future's knowledge to today's data. Always
# ffill (newer dates are lower down in our df)
weights = weights.reindex(constituent_closes.index).ffill().fillna(0)
constituent_closes = constituent_closes.ffill()

result = backtest.run('trend_following_index', constituent_closes, weights)
result.display()

rolling_max = result.prices.cummax()
drawdowns = (result.prices - rolling_max) / rolling_max
print('Latest prices')
print(result.prices.tail(20))
result_weights = result.get_security_weights()

fig, ax = plt.subplots(3, 1, sharex=True, figsize=(16, 12), gridspec_kw={'height_ratios': [3, 1, 2]})
result.prices.plot(ax=ax[0], label='prices')
drawdowns.plot(ax=ax[1])
index.plot(ax=ax[2], legend=False)
plt.show()
