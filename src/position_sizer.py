def get_order_sizes(current, future):
    '''
    Gets order sizes from current and future position sizes. 

    Parameters:
        current: dict of current positions (symbol -> size)
        future: dict of future positions (symbol -> size)

    Returns:
        dict of order sizes (symbol -> size)
    '''

    orders = {}
    
    # Get all unique symbols from both current and future positions
    all_symbols = set(current.keys()) | set(future.keys())
    
    for symbol in all_symbols:
        current_size = current.get(symbol, 0)
        future_size = future.get(symbol, 0)
        order_size = future_size - current_size
        
        # Only include non-zero orders
        if order_size != 0:
            orders[symbol] = order_size
    
    return orders