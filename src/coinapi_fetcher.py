import pandas as pd
from datetime import date
import requests
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('COINAPI_API_KEY')
headers = {'X-CoinAPI-Key': API_KEY}

def get(url, params=None):
    request = requests.get(url, headers=headers, params=params)
    if request.status_code != 200:
        raise ValueError(f'HTTP status code {request.status_code}: {request.text}')
    return request.json()

def get_history(symbol, start_time, end_time=date.today()):
    '''
    Get historical data for a symbol.
    '''
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
    '''
    Gets active symbols; returns their symbol_ids
    '''
    print(f'Get active symbols for {exchange_id}')
    params = {
        'filter_asset_id': base_currency,
    }
    active = get(f'https://rest.coinapi.io/v1/symbols/{exchange_id}/active', params)
    return [coin['symbol_id'] for coin in active if coin['symbol_id'].endswith(f'_{base_currency}')]

def get_historical_symbols(exchange_id, page=1, symbols=[], base_currency='USD'):
    '''
    Gets "delisted" symbols; needs pagination; returns their symbol_ids
    '''
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
        return get_historical_symbols(exchange_id, page+1, all_symbols)
    else:
        return all_symbols

def convert_df(coinapi_df):
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