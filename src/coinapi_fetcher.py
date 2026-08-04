import pandas as pd
from datetime import date
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('COINAPI_API_KEY')
headers = {'X-CoinAPI-Key': API_KEY}

def get(url, params=None):
    # Thin wrapper around requests.get that injects the API key and raises on non-2xx.
    response = requests.get(url, headers=headers, params=params)
    if not response.ok:
        raise requests.HTTPError(f'{response.status_code} {response.reason}: {response.text}', response=response)
    return response.json()

def get_history(symbol, start_time, end_time=date.today()):
    # Fetches daily OHLCV bars for one symbol between start_time and end_time.
    # Returns an empty DataFrame if CoinAPI has no data for that range yet.
    # CoinAPI returns max 100 results; use fewer than this
    print(f'Fetching {symbol} from {start_time} to {end_time} …')
    # Fetch until end_time is reached *or* get the next full batch
    # request_end_time = min(end_time, start_time + timedelta(days=days_to_fetch))
    params = {
        'period_id': '1DAY',
        'time_start': start_time.isoformat(),
        'time_end': end_time.isoformat(),
        # 100000 is the max possible; equals to 274 years
        'limit': 100000,
    }
    data = get(f'https://rest.coinapi.io/v1/ohlcv/{symbol}/history', params)
    raw_df = pd.DataFrame(data)
    result = pd.DataFrame()
    print(f'Fetched {len(data)} bars')
    # If we start with an date, there might not yet be data available, the API will return [];
    # just jump to the next period.
    if (len(raw_df) > 0):
        result = convert_df(raw_df)
    return result

def get_active_symbols(exchange_id, base_currency='USD'):
    # Returns symbol_ids of currently-listed spot pairs quoted in base_currency.
    print(f'Get active symbols for {exchange_id}')
    params = {
        'filter_asset_id': base_currency,
    }
    active = get(f'https://rest.coinapi.io/v1/symbols/{exchange_id}/active', params)
    if active:
        print(f'Sample response item keys: {list(active[0].keys())}')
        print(f'Sample response item: {active[0]}')
    return [coin['symbol_id'] for coin in active if coin['symbol_id'].endswith(f'_{base_currency}')]

def get_historical_symbols(exchange_id, page=1, symbols=[], base_currency='USD'):
    # Returns symbol_ids of delisted pairs; paginates recursively since CoinAPI caps at 1k per page.
    print(f'Get historical symbols for {exchange_id}, adding to {len(symbols)} existing')
    params = {
        # 1k is the max allowed (or at least the max it returns)
        'limit': 1000,
        'page': page,
    }
    historical = get(f'https://rest.coinapi.io/v1/symbols/{exchange_id}/history', params)
    base_currency_history = [coin['symbol_id'] for coin in historical if coin['asset_id_quote'] == base_currency]
    print(f'Out of {len(historical)} historical, {len(base_currency_history)} are {base_currency}-based')
    all_symbols =  symbols + base_currency_history
    if len(historical) == 1000:
        return get_historical_symbols(exchange_id, page+1, all_symbols, base_currency)
    else:
        return all_symbols

def convert_df(coinapi_df):
    # Renames CoinAPI fields to shorter names and sets the date as index.
    new_df = pd.DataFrame()
    new_df['date'] = pd.to_datetime(coinapi_df['time_period_end'])
    new_df['open'] = coinapi_df['price_open']
    new_df['high'] = coinapi_df['price_high']
    new_df['low'] = coinapi_df['price_low']
    new_df['close'] = coinapi_df['price_close']
    new_df['volume'] = coinapi_df['volume_traded']
    new_df['trades'] = coinapi_df['trades_count']
    # Only set the index at the end; if we do it before, indexes of raw_df and new_df will differ
    # and we can't copy columns from raw to new.
    new_df.set_index('date', inplace=True)
    return new_df