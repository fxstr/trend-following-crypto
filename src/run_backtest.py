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
#     display_name: .venv
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
index_result.prices.iloc[-100:].plot(figsize=(16, 4), title='Index result – last 100 days')
plt.show()
