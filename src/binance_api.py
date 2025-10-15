import requests
import time
import hmac
import hashlib
from urllib.parse import urlencode
import json

# Binance API endpoints
# BASE_URL = 'https://api.binance.com'  # For Spot (if needed)
BASE_URL = 'https://testnet.binance.vision'

def get_signature(params, secret):
    """Generate HMAC SHA256 signature"""
    query_string = urlencode(params)
    signature = hmac.new(
        secret.encode('utf-8'),
        query_string.encode('utf-8'),
        hashlib.sha256
    ).hexdigest()
    return signature

def get_current_positions():
    """
    Get current positions; size is amount of cryptos (not money invested)
    """
    endpoint = '/api/v3/account'
    
    # Prepare parameters
    params = {
        'timestamp': int(time.time() * 1000)
    }
    
    # Add signature
    params['signature'] = get_signature(params, API_SECRET)
    
    # Set headers
    headers = {
        'X-MBX-APIKEY': API_KEY
    }
    
    # Make request
    url = BASE_URL + endpoint
    print(f'Requesting current positions on {url}')
    response = requests.get(url, headers=headers, params=params)
    
    if response.status_code == 200:
        account_data = response.json()
        print(f'Raw response is {account_data}')

        if not account_data['balances']:
            print('Key \'balances\' not found in response')
            return None

        balances = account_data['balances']

        holdings = [
            (bal['asset'], float(bal.get('free', 0)) + float(bal.get('locked', 0)))
            for bal in balances
        ]
        # print('All holdings:')
        # print(holdings)

        active_holdings = dict([
            h for h in holdings if h[1] > 0
        ])
        
        # print(f'Current balances are {active_holdings}')
        
        return active_holdings
    else:
        print(f"Error: {response.status_code}")
        print(response.text)
        return None
    

def get_symbols():
    response = requests.get(f'{BASE_URL}/api/v3/exchangeInfo', timeout=30)
    if (response.status_code != 200):
        raise Exception(f'Error: Invalid status code {response.status_code}')
    data = response.json()
    symbols = data['symbols']
    print('Prices for symbols')
    print(symbols)
    trading = [
        s['symbol'] for s in symbols
        if s['status'] == 'TRADING'
    ]
    print(f'Fetched {len(symbols)} symbols of which {len(trading)} are trading')
    return trading


def place_spot_order(symbol, side, order_type, quantity=None, quote_quantity=None, price=None):
    """
    Place a spot order
    
    Args:
        symbol: Trading pair (e.g., 'BTCUSDT')
        side: 'BUY' or 'SELL'
        order_type: 'MARKET', 'LIMIT', 'STOP_LOSS_LIMIT', etc.
        quantity: Amount of base asset (e.g., 0.001 BTC)
        quote_quantity: Amount in quote asset (e.g., 100 USDT) - only for MARKET orders
        price: Price for LIMIT orders
    """
    endpoint = '/api/v3/order'
    
    # Prepare parameters
    params = {
        'symbol': symbol,
        'side': side,
        'type': order_type,
        'timestamp': int(time.time() * 1000)
    }
    
    # Add quantity (use either quantity OR quoteOrderQty, not both)
    if quantity:
        params['quantity'] = quantity
    elif quote_quantity and order_type == 'MARKET':
        params['quoteOrderQty'] = quote_quantity
    
    # Add price for LIMIT orders
    if order_type == 'LIMIT':
        if not price:
            raise ValueError("Price is required for LIMIT orders")
        params['price'] = price
        params['timeInForce'] = 'GTC'  # Good Till Cancel
    
    # Add signature
    params['signature'] = get_signature(params, API_SECRET)
    
    # Set headers
    headers = {
        'X-MBX-APIKEY': API_KEY
    }
    
    # Make request
    url = BASE_URL + endpoint
    response = requests.post(url, headers=headers, params=params)
    
    if response.status_code == 200:
        order_data = response.json()
        print("\n✅ Order placed successfully!")
        print(f"Symbol: {order_data['symbol']}")
        print(f"Order ID: {order_data['orderId']}")
        print(f"Side: {order_data['side']}")
        print(f"Type: {order_data['type']}")
        print(f"Status: {order_data['status']}")
        if 'executedQty' in order_data:
            print(f"Executed Quantity: {order_data['executedQty']}")
        if 'cummulativeQuoteQty' in order_data:
            print(f"Total Cost: {order_data['cummulativeQuoteQty']}")
        return order_data
    else:
        print(f"\n❌ Error: {response.status_code}")
        print(response.json())
        return None

def get_price(symbol):
    """
    Get current prices for multiple symbols from Binance
    
    Args:
        symbols: List of trading pairs (e.g., ['BTCUSDT', 'ETHUSDT'])
    """
    url = f'{BASE_URL}/api/v3/ticker/price'
    
    # Format symbols as JSON array string
    params = {
        'symbol': symbol
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        price = response.json()['price']
        return float(price)
    except requests.exceptions.RequestException as e:
        print(f"Error fetching prices: {e}")
        return None    

def get_symbol_info(symbol):
    """Get trading rules for a symbol (min quantity, price precision, etc.)"""
    endpoint = '/api/v3/exchangeInfo'
    
    params = {'symbol': symbol}
    response = requests.get(BASE_URL + endpoint, params=params)
    
    if response.status_code == 200:
        data = response.json()
        if data['symbols']:
            return data['symbols'][0]
    return None
