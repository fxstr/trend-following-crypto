import os
from pathlib import Path
import pandas as pd


def get_files(directory, exchange):
    # Returns full paths of all SPOT CSVs for the given exchange in directory.
    return [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.endswith('.csv') and f.startswith(f'{exchange.upper()}_SPOT_')
    ]

def read(column_name, data_dir, exchange, base_currency):
    # Reads one column (e.g. 'close') from all historical CSVs and returns a wide DataFrame
    # with one column per coin. Stablecoins/fiat pairs are excluded — they have no signal
    # for trend-following.

    # get_files() already returns full paths (os.path.join(directory, f)); don't re-join
    # data_dir onto them below.
    historical_files = get_files(os.path.join(data_dir, 'historical'), exchange=exchange)
    print(f'Got {len(historical_files)} historical files')

    all_crypto = {}

    prefix_to_remove = f'{exchange.upper()}_SPOT_'
    suffix_to_remove = f'_{base_currency.upper()}'
    print(f'Remove {prefix_to_remove} and {suffix_to_remove}')
    # Get all files as [name, path]
    files = [
        # Careful here; there's a crypto called COINBASE_SPOT_BTC_USD_5C85E9.csv; 5C8… must stay or
        # it will overwrite BTC.
        [Path(filename).stem.removeprefix(prefix_to_remove).removesuffix(suffix_to_remove), filename]
        for filename in historical_files
    ]
    print('Read files', files)

    # Get CSVs as DFs
    for [name, file_path] in files:
        df = pd.read_csv(file_path)
        # Things fail if there's not a single row; make sure there is before we parse dates
        if (len(df) > 0):
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            all_crypto[name] = df

    # Detect stablecoins/fiat pairs by price behaviour instead of a hand-maintained ticker
    # list — the list went stale (missed USD1, FDUSD, EUR, which all sat in the live index
    # basket). A real coin's daily-return std is at least 3%+ even for the least volatile
    # ones (BTC ~3.5%); every $1-pegged or fiat-tracking instrument checked is under 0.5%.
    stable_std_threshold = 0.01
    stable_names = [
        name for name, df in all_crypto.items()
        if df['close'].pct_change().std() < stable_std_threshold
    ]
    if stable_names:
        print(f'Excluding {len(stable_names)} stablecoin/fiat pairs (low volatility):', stable_names)
        for name in stable_names:
            del all_crypto[name]

    result = pd.concat([df[column_name].rename(name) for name, df in all_crypto.items()], axis=1)
    return result