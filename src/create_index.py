# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
#   kernelspec:
#     display_name: 2025-04-crypto-py3.12 (broken)
#     language: python
#     name: python3
# ---

# %%
# %reload_ext autoreload
# %autoreload 2

import pandas as pd
from matplotlib import pyplot as plt
import coinbase_reader
import os
from dotenv import load_dotenv
from pathlib import Path

load_dotenv()

base_dir = Path.cwd()
exchange = os.getenv('COINAPI_EXCHANGE')
base_currency = os.getenv('COINAPI_BASE_CURRENCY')

# Make charts interactive
# # %matplotlib widget
# %matplotlib inline

# %%
data_dir = os.path.join(base_dir, f'../{exchange.lower()}_data')
print(f'Reading data from {data_dir}')
closes = coinbase_reader.read('close', data_dir=data_dir, exchange=exchange, base_currency=base_currency)
volume = coinbase_reader.read('volume', data_dir=data_dir, exchange=exchange, base_currency=base_currency)

print(f'Got {len(closes.columns)} cryptos with max {len(closes)} lines')
print('Cryptos are:')
print(closes.columns.to_list())

# %%
# Slow down volume for index; we don't want to add / remove cryptos constantly
window_size = 180
mean_volume = volume.rolling(window=window_size).mean()
nominal_volume = mean_volume * closes

print('Most recent nominal volume:')
print(nominal_volume.iloc[-1].dropna().sort_values(ascending=False));
print('Highest mean volume:')
print(mean_volume.iloc[-1].sort_values(ascending=False));
print('Highest closes:')
print(closes.iloc[-1].sort_values(ascending=False));

# Use average volume * average price as the weight for the instruments for the index (for the next
# period)
mean_nominal_volume = mean_volume * closes.rolling(window=window_size).mean()

youngest = mean_nominal_volume.iloc[-200:]
top20_cols = youngest.iloc[0].nlargest(20).index
youngest[top20_cols].plot(figsize=(15, 6))
plt.show()

# Use a hard cut for small nominal volumes
nominal_volume_threshold = 5_000_000
index_nominal_volume = nominal_volume[mean_nominal_volume > nominal_volume_threshold]
index_nominal_volume.dropna(axis=1, how='all', inplace=True)
index_nominal_volume.dropna(axis=0, how='all', inplace=True)
print(f'Out of {len(closes.columns)} cryptos, {len(index_nominal_volume.columns)} are relevant for the index:')
print(index_nominal_volume.columns.to_list())

# %%
# for index, row in index_nominal_volume.iterrows():
#   print(f'{index}: {row.dropna().to_dict()}')

# index_nominal_volume.iloc[-20:].plot(kind='bar', stacked=True, legend=False)
# plt.show()

dates = index_nominal_volume.index.to_series()
month_changes = dates[dates.dt.month != dates.shift(1).dt.month]
index_weights = pd.DataFrame()
adjustment = 1

index_weights = mean_nominal_volume.loc[month_changes.index]
index_weights = index_weights.apply(lambda row: row.nlargest(20), axis=1)
# Using pow(0.5) gives more weight to small constituents and reduces the weight of large ones;
# if we don't, Bitcoin has a share of approx. 30%
index_weights = index_weights.pow(0.5)
# index_weights = index_weights.pow(2)
# index_weights[:] = 0
# index_weights['BTC'] = 0.9
# index_weights['ETH'] = 0.1
index_weights.iloc[-20:].plot(figsize=(16, 8), kind='bar', stacked=True, legend=False)
plt.show()

index_weights.to_csv('index_weights.csv')

print('Latest data')
latest = index_weights.iloc[-1].dropna().sort_values(ascending=False)
latest_percent = latest / latest.sum() * 100
latest_percent_formatted = latest_percent.apply(lambda x: f'{x:.2f}%')
print(latest_percent_formatted)

# %%
raw_index = {}

def calculate_index_row(close_row, weight_row):
    return (close_row * weight_row).sum()

# Index: 1000 on 2018-01-01
adjustment_factor = 0.01
print('initial factor', adjustment_factor)
current_weight_index = 0
for current_index, row in closes.iterrows():
    print(current_index)
    current_weights = index_weights.iloc[current_weight_index].dropna()
    current_closes = closes.loc[current_index].dropna()
    print(current_closes.to_dict())
    print(current_weights.to_dict())
    # Month change: Update the adjustment_factor. Get the value of the current closes with the
    # previous weights and then the new weights; adjust the new weights so that the value exactly
    # matches the previous one.
    value = calculate_index_row(current_closes, current_weights) * adjustment_factor
    if current_index in index_weights.index and current_weight_index + 1 < len(index_weights):
        print('---')
        next_weights = index_weights.iloc[current_weight_index + 1].dropna()
        next_weight_value = calculate_index_row(current_closes, next_weights) * adjustment_factor
        print(f'prev {value}, next {next_weight_value}')
        adjustment_factor = adjustment_factor * (value / next_weight_value)
        current_weight_index += 1
        print('adj', adjustment_factor)
        print('---')
    print(value)
    raw_index[current_index] = value

index = pd.Series(raw_index)
index.name = 'value'
index.index.name = 'date'

# %%
print('2018-01-01')
print(index['2018-01-01'])
print(index)
index.plot(figsize=(15, 10), legend=False)
plt.show()
recent_relative = index.iloc[-10:] / index.iloc[-10]
print(recent_relative)
recent_relative.plot(figsize=(15, 10), legend=False)
plt.show()

index.to_csv('./index.csv')
