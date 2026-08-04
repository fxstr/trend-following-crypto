import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def __():
    import marimo as mo
    return (mo,)


@app.cell
def __():
    import os
    import time
    import pandas as pd
    from datetime import datetime, timedelta
    from decimal import Decimal, ROUND_FLOOR
    from pathlib import Path
    from binance.client import Client
    from dotenv import load_dotenv
    import position_sizer
    load_dotenv()
    return (Client, Decimal, Path, ROUND_FLOOR, datetime, os, pd, position_sizer, time, timedelta)


@app.cell
def __(Client, os):
    COIN_NAME_MAP = {'CGLD': 'CELO'}
    CASH_ASSETS = {'USDT', 'USD'}
    BUYING_POWER_MARGIN = 0.98
    DUST_THRESHOLD_USDT = 1.0

    client = Client(
        os.getenv('BINANCE_API_KEY'),
        os.getenv('BINANCE_API_SECRET'),
        testnet=os.getenv('BINANCE_TEST_API', '').lower() == 'true',
    )
    return (BUYING_POWER_MARGIN, CASH_ASSETS, COIN_NAME_MAP, DUST_THRESHOLD_USDT, client)


@app.cell
def __(Decimal, ROUND_FLOOR, client):
    def round_to_lot_size(trading_pair, raw_amount, prices):
        # Binance rejects orders that don't conform to the symbol's LOT_SIZE/MARKET_LOT_SIZE
        # and MIN_NOTIONAL filters. Rounds down to the nearest valid step and returns None
        # if the result is below the minimum quantity or notional value.
        symbol_info = client.get_symbol_info(trading_pair)
        if not symbol_info:
            return None
        lot = next((f for f in symbol_info['filters'] if f['filterType'] == 'LOT_SIZE'), None)
        market_lot = next((f for f in symbol_info['filters'] if f['filterType'] == 'MARKET_LOT_SIZE'), None)
        notional = next((f for f in symbol_info['filters'] if f['filterType'] in {'MIN_NOTIONAL', 'NOTIONAL'}), None)
        if not lot or not market_lot:
            return None
        step_size = max(Decimal(lot['stepSize']), Decimal(market_lot['stepSize']))
        min_qty = max(Decimal(lot['minQty']), Decimal(market_lot['minQty']))
        max_qty = min(Decimal(lot['maxQty']), Decimal(market_lot['maxQty']))
        amount = Decimal(f'{raw_amount}')
        if amount < min_qty:
            return None
        amount = min(amount, max_qty)
        if step_size > 0:
            amount = (amount / step_size).to_integral_value(rounding=ROUND_FLOOR) * step_size
        if notional and float(amount) * prices.get(trading_pair, 0) < float(notional['minNotional']):
            return None
        return amount
    return (round_to_lot_size,)


@app.cell
def __(COIN_NAME_MAP, Path, datetime, mo, pd, timedelta):
    signal_file = Path(__file__).parent / 'signal.csv'
    signal_age = datetime.now() - datetime.fromtimestamp(signal_file.stat().st_mtime)
    if signal_age > timedelta(hours=24):
        raise RuntimeError(
            f'signal.csv is {signal_age.total_seconds() // 3600:.0f}h old — '
            f'run run_backtest.py first, or comment out this raise to override'
        )

    signal_history = pd.read_csv(signal_file, index_col='date', parse_dates=['date'])
    latest_signal = signal_history.iloc[-1]
    target_weights = latest_signal.rename(COIN_NAME_MAP)
    target_weights = target_weights[target_weights > 0]

    # print() isn't visible in `marimo run` app mode — use mo.md so this shows up on the page.
    _status = 'LONG' if len(target_weights) else 'CASH'
    _weights_line = f'Target weights: {target_weights.round(4).to_dict()}' if len(target_weights) else ''
    mo.md(f'Signal from {latest_signal.name.date()}: **{_status}**  \n{_weights_line}')
    return (signal_history, target_weights)


@app.cell
def __(BUYING_POWER_MARGIN, CASH_ASSETS, DUST_THRESHOLD_USDT, client, mo):
    ticker_prices = {t['symbol']: float(t['price']) for t in client.get_all_tickers()}

    account_balances = client.get_account()['balances']
    all_holdings = {
        bal['asset']: _total
        for bal in account_balances
        if (_total := float(bal['free']) + float(bal['locked'])) > 0
    }

    _notes = []
    cash_value_usdt = 0.0
    coin_value_usdt = 0.0
    for _coin, _amount in all_holdings.items():
        if _coin in CASH_ASSETS:
            cash_value_usdt += _amount
        elif f'{_coin}USDT' not in ticker_prices:
            _notes.append(f'No price for {_coin}USDT — ignored for buying power')
        else:
            usdt_value = _amount * ticker_prices[f'{_coin}USDT']
            if usdt_value >= DUST_THRESHOLD_USDT:
                coin_value_usdt += usdt_value
            else:
                _notes.append(f'Ignoring dust: {_coin} ({usdt_value:.4f} USDT)')

    total_value_usdt = cash_value_usdt + coin_value_usdt
    available_usdt = total_value_usdt * BUYING_POWER_MARGIN

    relevant_holdings = {
        _coin: _amount for _coin, _amount in all_holdings.items()
        if _coin not in CASH_ASSETS
        and _amount * ticker_prices.get(f'{_coin}USDT', 0) >= DUST_THRESHOLD_USDT
    }

    # print() isn't visible in `marimo run` app mode — use mo.md so this shows up on the page.
    # available_usdt (the tradeable amount) comes from live Binance account balances:
    # cash (USDT/USD) counted directly + every coin holding valued at its current
    # ticker price (dust under DUST_THRESHOLD_USDT excluded), times BUYING_POWER_MARGIN
    # (a 2% haircut for price drift between this valuation and order execution/fees).
    mo.md('  \n'.join([
        *_notes,
        f'Current relevant holdings: {relevant_holdings}',
        f'Cash: {cash_value_usdt:.2f} USDT + Coins: {coin_value_usdt:.2f} USDT = Portfolio: {total_value_usdt:.2f} USDT',
        f'Available (×{BUYING_POWER_MARGIN} margin): **{available_usdt:.2f} USDT**',
    ]))
    return (all_holdings, available_usdt, relevant_holdings, ticker_prices, total_value_usdt)


@app.cell
def __(available_usdt, mo, position_sizer, relevant_holdings, target_weights, ticker_prices):
    target_sizes = {
        _coin: (weight * available_usdt) / ticker_prices[f'{_coin}USDT']
        for _coin, weight in target_weights.items()
        if f'{_coin}USDT' in ticker_prices
    }

    order_deltas = position_sizer.get_order_sizes(relevant_holdings, target_sizes)
    order_deltas = dict(sorted(order_deltas.items(), key=lambda x: x[1]))

    # print() isn't visible in `marimo run` app mode (console logs stay on the
    # server, don't render on the page) — use mo.md so this is guaranteed to show
    # up before the Execute trades button, since it must be reviewed first.
    _rows = [
        f"| {_coin} | {relevant_holdings.get(_coin, 0):.6g} | {target_sizes.get(_coin, 0):.6g} | {_delta:+.6g} | {_delta * ticker_prices.get(f'{_coin}USDT', 0):+.0f} USDT |"
        for _coin, _delta in order_deltas.items()
    ]
    planned_changes_table = mo.md('\n'.join([
        '**Planned changes:**',
        '',
        '| Coin | Current | Target | Delta | ≈ USDT |',
        '|---|---|---|---|---|',
        *_rows,
    ])) if _rows else mo.md('**Planned changes:** none — already at target.')
    planned_changes_table
    return (order_deltas, target_sizes)


@app.cell
def __(mo):
    execute_button = mo.ui.run_button(label="Execute trades")
    mo.callout(mo.vstack([
        mo.md("**Review the planned changes above before executing.**"),
        execute_button,
    ]), kind="warn")
    return (execute_button,)


@app.cell
def __(client, execute_button, mo, order_deltas, round_to_lot_size, ticker_prices, time):
    mo.stop(not execute_button.value, mo.md("Click **Execute trades** above to place orders."))

    # print() isn't visible in `marimo run` app mode — accumulate lines and render
    # as mo.md once the loop finishes, so execution results actually show up.
    # progress_bar gives visible feedback during the loop itself — each order has a
    # 5s throttle sleep, so with several coins this can take a while with no output
    # otherwise, easy to mistake for the click having done nothing.
    _log = []
    with mo.status.progress_bar(total=len(order_deltas), title='Executing trades') as _bar:
        for _coin, _delta in order_deltas.items():
            _bar.update(subtitle=_coin, increment=0)
            _trading_pair = f'{_coin}USDT'
            _side = 'BUY' if _delta > 0 else 'SELL'
            _rounded_amount = round_to_lot_size(_trading_pair, abs(_delta), ticker_prices)
            if _rounded_amount is None:
                _log.append(f'Skipping {_coin}: below minimum or no symbol info')
                _bar.update()
                continue
            try:
                _order = client.create_order(symbol=_trading_pair, side=_side, type='MARKET', quantity=_rounded_amount)
                _commission = sum(float(fill['commission']) for fill in _order['fills'])
                _log.append(f'{_side} {_rounded_amount} {_coin} — done, commission: {_commission}')
            except Exception as e:
                _log.append(f'{_side} {_rounded_amount} {_coin} — **Error:** {e}')
            time.sleep(5)
            _bar.update()

    mo.md('  \n'.join(['**Execution log:**', *_log]) if _log else '**Execution log:** nothing to do.')
    return ()


@app.cell
def __(CASH_ASSETS, DUST_THRESHOLD_USDT, client, mo, target_sizes, ticker_prices):
    updated_balances = client.get_account()['balances']
    actual_holdings = {
        bal['asset']: _total
        for bal in updated_balances
        if (_total := float(bal['free']) + float(bal['locked'])) > 0
        and bal['asset'] not in CASH_ASSETS
        and _total * ticker_prices.get(f"{bal['asset']}USDT", 0) >= DUST_THRESHOLD_USDT
    }

    # print() isn't visible in `marimo run` app mode — use mo.md so this shows up on the page.
    _rows = []
    for _coin in sorted(set(target_sizes) | set(actual_holdings)):
        _expected = target_sizes.get(_coin, 0)
        _actual = actual_holdings.get(_coin, 0)
        _diff_str = f'{(_actual - _expected) / _expected * 100:+.1f}%' if _expected else 'n/a'
        _rows.append(f'| {_coin} | {_expected:.6g} | {_actual:.6g} | {_diff_str} |')

    mo.md('\n'.join([
        '**Post-trade check:**',
        '',
        '| Coin | Expected | Actual | Diff |',
        '|---|---|---|---|',
        *_rows,
    ]))
    return ()


if __name__ == "__main__":
    app.run()
