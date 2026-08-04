import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def __():
    # Marimo import — must be the first cell.
    import marimo as mo
    return (mo,)


@app.cell
def __():
    # Imports and env setup. Anchors all paths to this file so export works from any CWD.
    import pandas as pd
    import bt
    import simple_regression
    import os
    from matplotlib import pyplot as plt
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv()
    src_dir = Path(__file__).parent
    exchange = os.getenv('COINAPI_EXCHANGE')
    base_currency = os.getenv('COINAPI_BASE_CURRENCY')
    return (base_currency, bt, exchange, os, pd, plt, simple_regression, src_dir)


@app.cell
def __(pd, plt, src_dir):
    # Loads the aggregate index from CSV, normalises to 100 at inception, and plots it.
    index = pd.read_csv(src_dir / 'index.csv', index_col=0, parse_dates=True)
    index = index / index.iloc[0] * 100
    index.name = 'value'
    print(f'Got index with length {len(index)}')
    index.plot(figsize=(16, 4))
    plt.show()
    return (index,)


@app.cell
def __(index, simple_regression):
    # Computes TheilSen CAGR for 6 lookback windows over the index.
    lookback_periods = [10, 20, 30, 45, 60, 75]
    index_cagrs = [
        index.rolling(window=lb).apply(simple_regression.create_regression('cagr'))
        for lb in lookback_periods
    ]
    return (index_cagrs, lookback_periods)


@app.cell
def __(index_cagrs, plt, index):
    # Averages the 6 lookback CAGRs, derives the go_long signal via a rolling 2/3-quantile
    # threshold, and plots index, CAGR bars, and signal together.
    mean_cagrs = sum(index_cagrs[:]) / len(index_cagrs[:])
    # Trim rows where the longest lookback hasn't warmed up yet.
    mean_cagrs = mean_cagrs[index_cagrs[-1].notna()]
    cleaned_mean_cagrs = mean_cagrs.dropna()

    # Go long only when CAGR is in the top third of its own rolling history AND positive —
    # the rolling quantile adapts the bar to the current regime rather than using a fixed threshold.
    best_percent = cleaned_mean_cagrs.rolling(window=50).quantile(2/3)
    is_top = (cleaned_mean_cagrs >= best_percent) & (cleaned_mean_cagrs > 0)
    go_long = is_top.astype(int)

    fig, ax = plt.subplots(3, 1, figsize=(15, 6), sharex=True, gridspec_kw={'height_ratios': [2, 3, 1]})
    start = '2022-06-01'
    ax[0].plot(index.loc[start:])
    # cleaned_mean_cagrs only has one row per week (Mondays) — plot it directly
    # instead of reindexing/ffilling to daily, so each bar is one real week's value.
    cagrs_to_plot = cleaned_mean_cagrs['value'].loc[start:]
    ax[1].bar(cagrs_to_plot.index, cagrs_to_plot.values, width=5)
    ax[1].plot(best_percent[start:], color='red')
    ax[2].plot(go_long.loc[start:])
    plt.show()

    print('Mean CAGRs - best percentile (go long if > 0):')
    print((cleaned_mean_cagrs - best_percent).iloc[-10:])
    return (best_percent, cleaned_mean_cagrs, go_long, mean_cagrs)


@app.cell
def __(best_percent, cleaned_mean_cagrs, index, pd, plt):
    # Zooms the CAGR-bars-vs-threshold panel to the trailing 365 days for detail,
    # with the index itself on a separate panel above for context.
    _recent_start = index.index[-1] - pd.Timedelta(days=365)
    _fig, (_ax_index, _ax) = plt.subplots(2, 1, figsize=(15, 7), sharex=True, gridspec_kw={'height_ratios': [2, 3]})
    _ax_index.plot(index.loc[_recent_start:])
    _ax_index.set_title('Index – last year')
    _cagrs_to_plot = cleaned_mean_cagrs['value'].loc[_recent_start:]
    _ax.bar(_cagrs_to_plot.index, _cagrs_to_plot.values, width=5)
    _ax.plot(best_percent.loc[_recent_start:], color='red')
    _ax.set_title('Mean CAGR vs. rolling 2/3 threshold – last year')
    plt.show()
    return ()


@app.cell
def __(pd, src_dir):
    # Loads the monthly index-constituent weight snapshots from CSV.
    index_weights = pd.read_csv(src_dir / 'index_weights.csv', index_col=0, parse_dates=True)
    return (index_weights,)


@app.cell
def __(base_currency, exchange, index_weights, pd, src_dir):
    # Loads per-coin closes for all index constituents (no TheilSen — closes only).
    _data_dir = src_dir.parent / f'{exchange.lower()}_data'
    _closes = {}
    for _coin in index_weights.columns:
        _file = _data_dir / 'historical' / f'{exchange.upper()}_SPOT_{_coin}_{base_currency.upper()}.csv'
        if _file.exists():
            _df = pd.read_csv(_file, index_col='date', parse_dates=True)
            _closes[_coin] = _df['close']
    coin_closes = pd.DataFrame(_closes)
    print(f'Loaded closes for {len(coin_closes.columns)} coins')
    return (coin_closes,)


@app.cell
def __(go_long, index_weights, pd, src_dir):
    # Builds signal_history: per-coin position weights for the "buy the cryptos"
    # strategy. Cash (all zeros) when go_long is 0.
    #
    # Each constituent's weight is its index weight (sqrt of trailing $-volume,
    # from create_index.py) cubed — i.e. ($-volume)^1.5, which UNDOES that sqrt
    # dampening and then some, pushing weight even harder toward the biggest/most-
    # liquid coins (BTC, ETH, ...) than a plain $-volume weighting would.
    #
    # Why: the smaller coins in the top-20 basket are what drag both return and
    # risk in the wrong direction — cutting their weight (without dropping them
    # outright, which loses upside during real breakouts) improves both CAGR and
    # drawdown at once. Empirically compared against equal-weight, plain index-
    # weight, squared, top-10, and top-5 variants on the same signal/coins:
    #   equal-weight        31.75% CAGR / -46.69% DD
    #   index-weight (sqrt) 37.86% CAGR / -43.83% DD
    #   squared              43.78% CAGR / -40.85% DD
    #   cubed (this one)     46.23% CAGR / -40.47% DD   <- best on every metric
    #   top-10               43.69% CAGR / -43.11% DD
    #   top-5                43.67% CAGR / -40.76% DD
    # Cubing beat trimming the coin count (top-10/top-5) too — concentrating
    # weight is a stronger lever here than concentrating coin count.
    def _strip_timezone(df):
        if df.index.tz is not None:
            df = df.copy()
            df.index = df.index.tz_localize(None)
        return df

    _index_weights = _strip_timezone(index_weights)
    _signal = _strip_timezone(go_long)

    rows = []
    for date, signal_row in _signal.iterrows():
        past_rebalances = _index_weights.index[_index_weights.index <= date]
        if not len(past_rebalances):
            continue
        constituent_weights = _index_weights.loc[past_rebalances[-1]]
        constituent_weights = constituent_weights[constituent_weights > 0]
        is_long = int(signal_row.iloc[0])
        if is_long:
            cubed_weights = constituent_weights.pow(3)
            target_weights = cubed_weights / cubed_weights.sum()
        else:
            target_weights = pd.Series(0.0, index=constituent_weights.index)
        rows.append(target_weights.rename(date))

    signal_history = pd.concat(rows, axis=1).T.fillna(0)
    signal_history.index.name = 'date'

    signal_history.to_csv(src_dir / 'signal.csv')
    last_row = signal_history.iloc[-1]
    long_coins = last_row[last_row > 0]
    print(f"signal.csv: {len(signal_history)} rows, latest: {'LONG' if len(long_coins) else 'CASH'} on {signal_history.index[-1].date()}")
    if len(long_coins):
        print(f"Active coins ({len(long_coins)}): {long_coins.round(3).to_dict()}")
    return (signal_history,)


@app.cell
def __(bt, coin_closes, go_long, index, signal_history):
    # Three strategies compared side by side:
    #   - index_always_long: buy-and-hold the aggregate index, no timing
    #   - index_timed:       aggregate index, in/out via the go_long signal
    #   - coins_cubed_timed: actual coins, cubed-weighted, in/out via go_long
    _index_data = index.copy()
    if _index_data.index.tz is not None:
        _index_data.index = _index_data.index.tz_localize(None)

    _go_long_weights = go_long.copy()
    if _go_long_weights.index.tz is not None:
        _go_long_weights.index = _go_long_weights.index.tz_localize(None)

    index_always_long = bt.Backtest(
        bt.Strategy('index_always_long', [
            bt.algos.RunOnce(),
            bt.algos.SelectAll(),
            bt.algos.WeighEqually(),
            bt.algos.Rebalance(),
        ]),
        _index_data,
        initial_capital=100000,
    )

    index_timed = bt.Backtest(
        bt.Strategy('index_timed', [
            bt.algos.RunWeekly(),
            bt.algos.SelectAll(),
            bt.algos.WeighTarget(_go_long_weights),
            bt.algos.Rebalance(),
        ]),
        _index_data,
        initial_capital=100000,
    )

    _coins = [c for c in signal_history.columns if c in coin_closes.columns]
    _coin_data = coin_closes[_coins].copy()
    if _coin_data.index.tz is not None:
        _coin_data.index = _coin_data.index.tz_localize(None)
    # Bounded like coinbase_reader.py's closes.ffill(limit=5) — an unbounded ffill here
    # would flatline a coin with a real multi-month data gap (e.g. FTT's 311-day void
    # spanning the Nov 2022 FTX collapse) at its last pre-gap price instead of letting
    # it drop out, silently pricing the backtest on a stale value during exactly the
    # week it should have been crashing.
    _coin_data = _coin_data.ffill(limit=5)

    coins_cubed_timed = bt.Backtest(
        bt.Strategy('coins_cubed_timed', [
            bt.algos.RunWeekly(),
            bt.algos.SelectHasData(),
            bt.algos.WeighTarget(signal_history[_coins]),
            bt.algos.Rebalance(),
        ]),
        _coin_data,
        initial_capital=100000,
    )

    combined_result = bt.run(index_always_long, index_timed, coins_cubed_timed)
    combined_result.display()
    return (combined_result,)


@app.cell
def __(combined_result, plt):
    # Plots the last year of all three strategies' equity curves.
    combined_result.prices.iloc[-365:].plot(figsize=(16, 4), title='Strategy – last year')
    plt.show()
    return ()


@app.cell
def __(combined_result, plt):
    # Plots the full-history money curve of all three strategies, with drawdown on a separate axis below.
    _fig, (ax_equity, ax_dd) = plt.subplots(2, 1, figsize=(20, 16), sharex=True, gridspec_kw={'height_ratios': [3, 1]})
    combined_result.prices.plot(ax=ax_equity, title='Strategy – full history')
    combined_result.prices.to_drawdown_series().plot(ax=ax_dd, legend=False, title='Drawdown')
    plt.show()
    return ()


if __name__ == "__main__":
    app.run()
