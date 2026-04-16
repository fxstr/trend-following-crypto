# ---
# jupyter:
#   jupytext:
#     text_representation:
#       extension: .py
#       format_name: percent
#       format_version: '1.3'
#       jupytext_version: 1.19.1
#   kernelspec:
#     display_name: 2025-04-crypto-py3.12 (3.12.11)
#     language: python
#     name: python3
# ---

# %%
# %reload_ext autoreload
# %autoreload 2

import pandas as pd
import time
import position_sizer
from datetime import date, timedelta
from binance.client import Client
from dotenv import load_dotenv
import os
from decimal import Decimal, ROUND_FLOOR

# %%
# CGLD on CoinAPI is CELO on Binance. Make sure we map them: CoinAPI ➝ Binance
name_map = {
  'CGLD': 'CELO'
}

load_dotenv()
client = Client(
    os.getenv('BINANCE_API_KEY'),
    os.getenv('BINANCE_API_SECRET'),
    testnet=os.getenv('BINANCE_TEST_API'),
)

# %%
# Get current positions (symbol and amount of instruments we hold)
balances = client.get_account()['balances']
current_position_sizes = [
    (bal['asset'], total)
    for bal in balances
    if (total := float(bal.get('free', 0)) + float(bal.get('locked', 0))) > 0
]

print(f'Currently holding {len(current_position_sizes)} positions: {dict(current_position_sizes)}')

# %%
# Get the positions we want to hold in the future (symbol and weight)
# Check if data is recent enough (so that we don't try to open old positions)

theoretical_positions = pd.read_csv('weights.csv', index_col='date', parse_dates=['date'])
renamed_positions = theoretical_positions.rename(columns=name_map)
# TODO: Fix -2! We currently don't hold positions, so fo testing purposes, we have to use the
# last row of weights.csv where we actually held something.
all_future_weights = renamed_positions.iloc[-1]
future_weights = all_future_weights[all_future_weights != 0]
future_weights_date = future_weights.name.date()

weights_to_print = [(key, f'{value:.2f}') for (key, value) in future_weights.to_dict().items()]
print(f'Future weights are: {weights_to_print}')

# Throw if position change is older than 2 days; things might not have been updated and we don't
# hold to trade outdated positions.
# TODO: Fix amount of days
if (future_weights_date < date.today() - timedelta(days=80)):
  raise Exception(f'Future position sizes are too old: From {future_weights_date} while they should not be older than 2 days')


# %%
# Get current prices

prices = client.get_all_tickers()
print(f'Got {len(prices)} prices')
price_dict = { item['symbol']: float(item['price']) for item in prices }

# %%
# Get buying power by multiplying current positions with their current values

relevant_current_position_sizes = []
current_position_values = []

for i, (symbol, position_size) in enumerate(current_position_sizes):
    usdt_symbol = f'{symbol}USDT'
    # Well, in that case … assume USDT is stable
    if (usdt_symbol == 'USDTUSDT'):
        # Price equals 1; we can therefore just use the position_size as the value
        current_position_values.append((symbol, position_size))
        relevant_current_position_sizes.append((symbol, position_size))
    elif (usdt_symbol in price_dict):
        price = price_dict[usdt_symbol]
        position_value = position_size * price
        if (position_value < 1):
            print(f'➖ Position value for {symbol} is {position_value}; ignoring dust')
            continue
        print(f'✅ Current price for {usdt_symbol} is {price}, position value is {position_size * price}')
        current_position_values.append((symbol, position_value))
        relevant_current_position_sizes.append((symbol, position_size))
    else:
        # This is especially the case in our original test data, and mostly for fiat currencies
        # that have no data available on weekends.
        print(f'⚠️ WARNING: No price for {usdt_symbol}; ignoring symbol for buying power')
print(f'Current position values are {current_position_values}')
buying_power = sum([value for (_, value) in current_position_values])
print(f'Current buying power is {buying_power}')
print(f'Out of {len(current_position_sizes)} positions, {len(relevant_current_position_sizes)} are valid: {relevant_current_position_sizes}')

relative_values = [
    (symbol, f'{(value / buying_power):.2f}')
    for (symbol, value) in current_position_values
]

print('---')
print(f'Relative current position values: {relative_values}')
print(f'Relative future position values: {weights_to_print}')


# %%
# Calculate future abslute position sizes

# Prices may have changed; give it some margin
available_buying_power = buying_power * 0.98
print(f'Available buying power is {available_buying_power:.0f}')

future_position_values = [
    (symbol, relative_size * available_buying_power)
    for (symbol, relative_size) in future_weights.to_dict().items()
]
print(f'Using {sum([size for (_, size) in future_position_values]):.0f} for future positions')
print(f'Future position values: {[(symbol, f'{size:.0f}') for (symbol, size) in future_position_values]}')

future_position_sizes = [
    (symbol, value / price_dict[f'{symbol}USDT'])
    for (symbol, value) in future_position_values
]
print(f'Future position sizes: {[(symbol, f'{size:.0f}') for (symbol, size) in future_position_sizes]}')

# %%
orders = position_sizer.get_order_sizes(dict(relevant_current_position_sizes), dict(future_position_sizes))
print(f'Order sizes are {orders}')

# Do negative orders (sell / reduce) first; we don't go short, so that's fine
sorted_orders = dict(sorted(orders.items(), key=lambda x: x[1]))
print(f'Sorted orders sizes are: {sorted_orders}')


# %%
# Ensures that we trade in the right granularity (respect LOT_SIZE of the symbol); we could also
# respect min and max size, but that has not yet been an issue.
def get_tradeable_size(symbol, size):
    info = client.get_symbol_info(symbol)
    lot_info = next((i for i in info['filters'] if i.get('filterType') == 'LOT_SIZE'), None)
    market_lot_info = next((i for i in info['filters'] if i.get('filterType') == 'MARKET_LOT_SIZE'), None)
    if (not lot_info or not market_lot_info):
        print(f'⚠️ No lot or market lot information found for symbol {symbol}; can\'t be traded; info is {info}.')
        return 0
    # Using float can lead to wrong precision (e.g. 0.010150000000000001 instead of 0.1015); use
    # Decimal instead
    step_size = Decimal(lot_info['stepSize'])
    min_size = Decimal(lot_info['minQty'])
    max_size = Decimal(lot_info['maxQty'])
    market_step_size = Decimal(market_lot_info['stepSize'])
    market_min_size = Decimal(market_lot_info['minQty'])
    market_max_size = Decimal(market_lot_info['maxQty'])
    print(f'Lot step size {step_size}, min size {min_size}, max size {max_size}; market step size {market_step_size}, min size {market_min_size}, max size {market_max_size}.')
    # If we pass a float to Decimal, many, many figures may be added
    decimal_size = Decimal(f'{size}')
    result = decimal_size
    # Respect min and max quantity
    if result < min_size or result < market_min_size:
        print(f'⚠️ Size {result} is smaller min. size {min_size} or market min size {market_min_size}; not trading as we should not enlarge desired positions.')
        return 0
    if result > max_size or result > market_max_size:
        print(f'Size {result} is larger than max. size {max_size} or market max. size {market_max_size}; adjusting.')
        result = min(max_size, market_max_size)
    # Adjust step size *after* min/max, as min/max may be more precise than step_size (yes, this
    # did happen)
    # If step size is 0, try not to divice by 0; assume that step_size and
    # market_step_size are compatible (one does not exclude the other as e.g. with 0.35 and 0.25,
    # but that the larger includes the smaller one)
    relevant_step_size = max(step_size, market_step_size)
    if relevant_step_size != 0:
        result = (result / relevant_step_size).to_integral_value(rounding=ROUND_FLOOR) * relevant_step_size

    print(f'Adjusted size from {size} to {result}')
    return result

# get_tradeable_size('BTCUSDT', 0.01)


# %%
# Trade single symbols (e.g. to clear the test account; fiat can e.g. not be tradeda gainst USDT
# sometimes)

# def order_btc(name, against):
#     symbol = f'{against}{name}'
#     side = 'BUY'
#     current_value = next((p[1] for p in current_positions if p[0] == name), None)
#     print(f'Create {side} order for {current_value} of {symbol}')
#     order = client.create_order(
#         symbol=symbol,
#         side=side,
#         type='MARKET',
#         # quantity=abs(size),
#         quoteOrderQty=current_value
#     )
#     print(f'Order done: {order}')

# names = ['BTC']
# for name in names:
#     against = 'USDT'
#     try:
#         order_btc(name, against)
#     except Exception as e:
#         print(f'Error when trading {name} for {against}: {e}')

# %%
# exchange_info = client.get_exchange_info()
# import json
# print(json.dumps(exchange_info, indent=4))
# print(f'Exchange info: {exchange_info}')

for (name, size) in sorted_orders.items():
    # No need to sell USDT: This is our base currency
    if (name == 'USDT'):
        continue
    side = 'BUY' if size > 0 else 'SELL'
    symbol = f'{name}USDT'
    print(f'Order {side} for {abs(size)} of {name} (trading {symbol})')
    info = client.get_symbol_info(symbol)
    if (not info):
        print(f'⚠️ No information found for symbol {symbol}; can\'t be traded')
        continue
    adjusted_size = get_tradeable_size(symbol, abs(size))
    # We must use abs() here; if we don't and amount is negative, we will round down to an amount
    # that is too big.
    print(f'Adjusted size is {adjusted_size} (from {size})')

    try:
        order = client.create_order(
            symbol=symbol,
            side=side,
            type='MARKET',
            # Use size / quanitty here, not value; why? When closing a position, prices may
            # have changed in the meantime and we're trying to sell more than we have (which
            # will result in an exception); using a treshold is not nice as this will leave us
            # with a small position.
            quantity=adjusted_size,
        )
        commission = sum([
            float(fill['commission'])
            for fill in order['fills']
        ])
        print(f'Order done, commission is {commission}: {order}')
    except Exception as e:
        print(f'🚨 Error creating order for {symbol}: {e}')

    time.sleep(5)
