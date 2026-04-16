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
# Why Coinapi?
# - Delisted symbols
# - Long history (back to the origins)
# - Cleaned data
# - Pricing quite fair and usage-based (Coinmarketcap costs $700/month for the same)

# %%
# %reload_ext autoreload
# %autoreload 2

import pandas as pd
from datetime import datetime, date
import os
from matplotlib import pyplot as plt
import coinapi_fetcher
import time
from dotenv import load_dotenv

load_dotenv()

exchange = os.getenv('COINAPI_EXCHANGE')
base_currency = os.getenv('COINAPI_BASE_CURRENCY')

output_folder = f'../{exchange.lower()}_data/'
print(f'Store files in {output_folder}')

# %%
# btc = coinapi_fetcher.get_history('COINBASE_SPOT_BTC_USD', datetime(2010, 1, 1))
# btc['close'].plot(figsize=(15, 6))
# plt.show()
# btc.to_csv(os.path.join(output_folder, 'COINBASE_SPOT_BTC_USD.csv'), index=True)

# %%
# Binance doesn't have base currency USD; use BTC and re-caculate (BINANCE has a market share
# of approx 40%)
# Problem: There is no BTC-BTC, so we don't get the BTC volume. Use Coinbase instead, as they
# directly quote USD.
exchange_id = exchange
active = coinapi_fetcher.get_active_symbols(exchange_id, base_currency=base_currency)
historical = coinapi_fetcher.get_historical_symbols(exchange_id, base_currency=base_currency)
symbols_to_fetch = list(set(active + historical))

print(f'Got {len(active)} active and {len(historical)} historical, {len(symbols_to_fetch)} total symbols')


# %%
def write_file(data, file_path):
    data.to_csv(file_path, index=True)
    print(f'Wrote file {file_path} with {len(data)} rows')

def get_existing_content(file_path):
    '''
    Returns the date of the last row in the file, if it exists, and its whole content (which
    is needed to append new data to later).
    '''
    if os.path.exists(file_path):
        print(f'File {file_path} exists, get last row')
        content = pd.read_csv(file_path)
        # When the file is empty, there's no 'date' column that we can use as index; return an
        # empty df so that all data is fetched from the crypto's start of existence.
        if ('date' not in content.columns):
            print('File is missing date column, return empty DataFrame')
            return (pd.DataFrame(), None)
        # Remove the last row; it may contain intraday data; make it 2 to be sure.
        content = content.iloc[:-2]
        content['date'] = pd.to_datetime(content['date'])
        content.set_index('date', inplace=True)
        print(f'Existing file has {len(content)} rows')
        if(len(content)):
            last_date = content.index[-1].date()
            print(f'Last date in existing file is {last_date}')
            return (content, last_date)
        return (content, None)
    else:
        return (pd.DataFrame(), None)

first_date = date(2010, 1, 1)

current_index = 90
total = len(symbols_to_fetch)
errors = []
# Historical contains *all* cryptos, delisted as well as active. Delisted ones just won't return
# any new data.
for symbol_id in symbols_to_fetch:
    current_index += 1
    print('------')
    print(f'Get {current_index}/{total}')
    file_path = os.path.join(output_folder, 'historical', f'{symbol_id}.csv')
    (existing_content, start_date) = get_existing_content(file_path)
    if (start_date):
        print(f'File {symbol_id} exists, 2nd latest row\'s date is {start_date}')
    else:
        start_date = first_date
        print(f'File {symbol_id} does not exist')
    end_date = date.today()
    if (start_date >= end_date):
        print(f'Skip {symbol_id}, start is on or after end')
        continue
    print(f'Get {symbol_id} from {start_date} to {end_date}')
    try:
        new_content = coinapi_fetcher.get_history(symbol_id, start_date, end_date)
    except Exception as e:
        errors.append(f'{symbol_id}: {e}')
        continue
    # Make sure that content was returned before we concat an empty DF (which would fail)
    if (not new_content.empty):
        data = pd.concat([df for df in [existing_content, new_content] if not df.empty])
        write_file(data, file_path)
    time.sleep(0.5)
print(f'Out of {total} cryptos, {current_index} were fetched')
if errors:
    print(f'\n{len(errors)} errors:')
    for error in errors:
        print(error)

# %%
# Turns out: /history returns active *and* delisted data
for symbol_id in active:
    if (symbol_id not in historical):
        print(f'!!!!! Active symbol {symbol_id} not in historical list')
#     file_path = f'{output_folder}/active/{symbol_id}.csv'
#     start_date = get_latest_entry_date(file_path) or first_date
#     end_date = date.today()
#     if (start_date >= end_date):
#         print(f'Skip {symbol_id}, start is on or after end')
#         continue
#     print(f'Get {symbol_id} from {start_date}')
#     data = coinapi_fetcher.get_history(symbol_id, start_date)
#     write_file(data, file_path)
#     time.sleep(1)

# print('Done')
