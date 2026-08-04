import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def __():
    import marimo as mo
    return (mo,)


@app.cell
def __():
    import pandas as pd
    from matplotlib import pyplot as plt
    import coinbase_reader
    import os
    import re
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv()
    src_dir = Path(__file__).parent
    exchange = os.getenv('COINAPI_EXCHANGE')
    base_currency = os.getenv('COINAPI_BASE_CURRENCY')
    return (base_currency, coinbase_reader, exchange, os, pd, plt, re, src_dir)


@app.cell
def __(base_currency, coinbase_reader, exchange, os, pd, re, src_dir):
    data_dir = src_dir.parent / f'{exchange.lower()}_data'
    print(f'Reading data from {data_dir}')
    closes = coinbase_reader.read('close', data_dir=data_dir, exchange=exchange, base_currency=base_currency)
    volume = coinbase_reader.read('volume', data_dir=data_dir, exchange=exchange, base_currency=base_currency)

    # Drop leveraged tokens (e.g. BTCUP, ETHDOWN, ADABULL) — these are synthetic 3x
    # derivatives, not spot assets, and decay toward zero by design. Their price series
    # contain huge jumps (delisting/rebalancing events) that distort volume ranking and
    # any equal-weight backtest downstream.
    # Matching on suffix alone has false positives (JUP, SYRUP are real tokens ending
    # in "UP"), so also require the suffix-stripped remainder to be a real coin symbol
    # in our universe (BTCUP -> BTC exists; JUP -> J doesn't).
    leveraged_suffix = re.compile(r'(UP|DOWN|BULL|BEAR)$')
    all_coins = set(closes.columns)
    # sorted() over closes.columns (not the set) so the dropped list prints in a
    # stable order across runs — set iteration order is arbitrary.
    leveraged_cols = sorted(
        coin for coin in closes.columns
        if (match := leveraged_suffix.search(coin)) and len(coin[:match.start()]) >= 2
        and coin[:match.start()] in all_coins
    )
    if leveraged_cols:
        print(f'Dropping {len(leveraged_cols)} leveraged tokens:', leveraged_cols)
        closes = closes.drop(columns=leveraged_cols)
        volume = volume.drop(columns=leveraged_cols, errors='ignore')

    # Bridge short data gaps (exchange downtime, feed hiccups) by carrying the last
    # known price forward. Bounded to 5 days so a genuinely delisted coin doesn't
    # flatline forever with a stale nonzero price sitting in the index math — past
    # the limit it stays NaN and gets excluded/renormalized downstream instead.
    closes = closes.ffill(limit=5)

    # Drop coins with a single-day return so extreme it can only be a data artifact
    # (currency redenomination, decimal-point glitch) rather than a real price move —
    # e.g. LUNA's May 2022 depeg/relaunch shows a 177,000x single-day "return" from
    # concatenating the old and new token's price series. A 500% cutoff clears real
    # historical pumps (DOGE's Jan 2021 rally was ~390%) while catching these.
    daily_return_threshold = 5.0
    max_daily_return = closes.pct_change().abs().max()
    broken_data_cols = sorted(max_daily_return[max_daily_return > daily_return_threshold].index)
    if broken_data_cols:
        print(f'Dropping {len(broken_data_cols)} coins with broken price history:', broken_data_cols)
        closes = closes.drop(columns=broken_data_cols)
        volume = volume.drop(columns=broken_data_cols, errors='ignore')

    print(f'Got {len(closes.columns)} cryptos with max {len(closes)} lines')
    print('Cryptos:', closes.columns.to_list())
    return (closes, volume)


@app.cell
def __(closes, pd, plt, volume):
    window_size = 180
    # min_periods defaults to window_size, meaning a single missing day anywhere in
    # the trailing 180-day window (exchange downtime, one bad API pull) NaNs out the
    # entire rolling average until that one gap ages out of the window — up to 180
    # days of a real, liquid coin silently vanishing from the index. Tolerate up to
    # 10% missing observations instead of requiring a perfectly gapless window.
    min_periods = int(window_size * 0.9)
    mean_volume = volume.rolling(window=window_size, min_periods=min_periods).mean()
    nominal_volume = mean_volume * closes

    print('Most recent nominal volume:')
    print(nominal_volume.iloc[-1].dropna().sort_values(ascending=False))

    mean_nominal_volume = mean_volume * closes.rolling(window=window_size, min_periods=min_periods).mean()

    youngest = mean_nominal_volume.iloc[-200:]
    top20_cols = youngest.iloc[0].nlargest(20).index
    youngest[top20_cols].plot(figsize=(15, 6))
    plt.show()

    nominal_volume_threshold = 5_000_000
    index_nominal_volume = nominal_volume[mean_nominal_volume > nominal_volume_threshold]
    index_nominal_volume.dropna(axis=1, how='all', inplace=True)
    index_nominal_volume.dropna(axis=0, how='all', inplace=True)
    print(f'Out of {len(closes.columns)} cryptos, {len(index_nominal_volume.columns)} are relevant for the index:')
    print(index_nominal_volume.columns.to_list())
    return (index_nominal_volume, mean_nominal_volume, nominal_volume)


@app.cell
def __(index_nominal_volume, mean_nominal_volume, plt, src_dir):
    dates = index_nominal_volume.index.to_series()
    month_changes = dates[dates.dt.month != dates.shift(1).dt.month]

    index_weights = mean_nominal_volume.loc[month_changes.index]
    index_weights = index_weights.apply(lambda row: row.nlargest(20), axis=1)
    index_weights = index_weights.pow(0.5)
    index_weights.iloc[-20:].plot(figsize=(16, 8), kind='bar', stacked=True, legend=False)
    plt.show()

    index_weights.to_csv(src_dir / 'index_weights.csv')

    latest = index_weights.iloc[-1].dropna().sort_values(ascending=False)
    latest_percent = latest / latest.sum() * 100
    print('Latest weights:')
    print(latest_percent.apply(lambda x: f'{x:.2f}%'))
    return (index_weights,)


@app.cell
def __(mo):
    run_index = mo.ui.run_button(label="Compute raw index (slow)")
    run_index
    return (run_index,)


@app.cell
def __(closes, index_weights, mo, os, pd, plt, run_index, src_dir):
    mo.stop(not run_index.value and not os.getenv('MARIMO_PIPELINE'), mo.md("Click **Compute raw index** to build the index series (takes a while)."))

    # Only start the index once real weights exist. closes spans back to each coin's
    # first-ever trading day, but index_weights only starts once the 180-day volume
    # warmup completes. Without this clip, all dates before the first rebalance would
    # get priced using that first-ever top-20 basket applied backward in time — a
    # look-ahead leak (using a future weight snapshot for past prices).
    # Named differently from the `closes` param — marimo requires each variable to
    # be defined by exactly one cell, so reassigning the parameter itself here would
    # conflict with the cell that originally defines it.
    indexed_closes = closes.loc[index_weights.index[0]:]

    def _calculate_index_row(close_row, weight_row):
        # Restrict to coins that have both a price and a weight today, then
        # renormalize the weights over just those. Without this, a coin missing a
        # price that day (holiday, feed gap, delisting) would silently act as a
        # zero-weight position via NaN-skipping sum() — showing up as a fake index
        # dip instead of redistributing its share across the coins that do have a
        # price. Returns None if no basket coin has a price today at all.
        available = weight_row.index.intersection(close_row.index)
        weights = weight_row.loc[available]
        if weights.sum() == 0:
            return None
        weights = weights / weights.sum()
        return (close_row.loc[available] * weights).sum()

    adjustment_factor = 0.01
    current_weight_index = 0
    raw_index = {}
    last_value = None

    for current_date, row in indexed_closes.iterrows():
        current_closes = row.dropna()
        current_weights = index_weights.iloc[current_weight_index].dropna()
        value = _calculate_index_row(current_closes, current_weights)
        if value is None:
            # No coin in the current basket has a price today (should be rare after
            # ffill) — carry the last known index value forward rather than break
            # the chain-linked series with a NaN.
            value = last_value
        else:
            value = value * adjustment_factor

        # Chain-link into the next basket once we reach its rebalance date: price
        # both baskets on today's closes and rescale adjustment_factor so the index
        # stays continuous despite the composition change.
        # Must check against the NEXT basket's anchor date, not "any" rebalance
        # date — the current basket's own anchor date is trivially a rebalance
        # date too, which advanced the pointer after a single day and shifted
        # every basket a full period early (look-ahead: using data not yet known).
        if (
            current_weight_index + 1 < len(index_weights)
            and current_date >= index_weights.index[current_weight_index + 1]
        ):
            next_weights = index_weights.iloc[current_weight_index + 1].dropna()
            next_weight_value = _calculate_index_row(current_closes, next_weights)
            if next_weight_value:
                next_weight_value = next_weight_value * adjustment_factor
                adjustment_factor = adjustment_factor * (value / next_weight_value)
                current_weight_index += 1
            # else: none of the next basket's coins have a price yet today — keep
            # today's basket and retry the chain-link on the next date instead of
            # dividing by zero/NaN and corrupting adjustment_factor permanently.

        raw_index[current_date] = value
        last_value = value

    index = pd.Series(raw_index)
    index.name = 'value'
    index.index.name = 'date'

    print(f'Index from {index.index[0].date()} to {index.index[-1].date()}, {len(index)} rows')
    index.plot(figsize=(15, 10), legend=False)
    plt.show()

    index.to_csv(src_dir / 'index.csv')
    print('Saved index.csv')
    return (index,)


if __name__ == "__main__":
    app.run()
