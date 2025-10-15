import os
from pathlib import Path
import pandas as pd


def get_files(directory):
    return [
        os.path.join(directory, f)
        for f in os.listdir(directory)
        if f.endswith('.csv') and f.startswith('COINBASE_SPOT_')
    ]

def read(column_name):
    '''
    Returns a DF with one column per crypto and a row for every date that cointains data.
    
    Parameters
    ----------
    column_name : str
        The name of the CSV column to read ('close', 'open', 'high', 'low', 'volume', 'trades')
    '''

    data_dir = '../coinapi_data/'
    historical_files = get_files(os.path.join(data_dir, 'historical'))

    all_crypto = {}

    # Filter out all stable coins – too boring to trade; source: ChatGPT
    stable_assets = ['USDT', 'USDC', 'BUSD', 'DAI', 'TUSD', 'FRAX', 'USDP', 'GUSD', 'PYUSD', 'EURS', 'EUROC', 'sEUR', 'XSGD', 'CNHT', 'BRZ', 'TRYB', 'JPYC', 'XAUT', 'PAXG', 'HUSD', 'USDN', 'UST', 'USTC', 'AMPL', 'FEI', 'sUSD']

    # Get all files as [name, path]
    files = [
        # Careful here; there's a crypto called COINBASE_SPOT_BTC_USD_5C85E9.csv; 5C8… must stay or
        # it will overwrite BTC.
        [Path(filename).stem.removeprefix('COINBASE_SPOT_').removesuffix('_USD'), os.path.join(data_dir, filename)]
        for filename in historical_files
    ]

    non_stables = [entry for entry in files if entry[0] not in stable_assets]

    # Get CSVs as DFs
    for [name, file_path] in non_stables:
        df = pd.read_csv(file_path)
        # Things fail if there's not a single row; make sure there is before we parse dates
        if (len(df) > 0):
            df['date'] = pd.to_datetime(df['date'])
            df.set_index('date', inplace=True)
            all_crypto[name] = df

    result = pd.concat([df[column_name].rename(name) for name, df in all_crypto.items()], axis=1)
    return result