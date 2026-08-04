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
    from datetime import date
    from pathlib import Path
    import os
    import coinapi_fetcher
    import time
    from dotenv import load_dotenv
    load_dotenv()
    src_dir = Path(__file__).parent
    return (coinapi_fetcher, date, os, pd, src_dir, time)


@app.cell
def __(os, src_dir):
    exchange = os.getenv('COINAPI_EXCHANGE')
    base_currency = os.getenv('COINAPI_BASE_CURRENCY')
    output_folder = src_dir.parent / f'{exchange.lower()}_data'
    print(f'Store files in {output_folder}')
    return (base_currency, exchange, output_folder)


@app.cell
def __(base_currency, coinapi_fetcher, exchange):
    active = coinapi_fetcher.get_active_symbols(exchange, base_currency=base_currency)
    historical = coinapi_fetcher.get_historical_symbols(exchange, base_currency=base_currency)
    symbols_to_fetch = list(set(active + historical))
    print(f'Got {len(active)} active and {len(historical)} historical, {len(symbols_to_fetch)} total symbols')
    return (active, historical, symbols_to_fetch)


@app.cell
def __(mo):
    run_fetch = mo.ui.run_button(label="Fetch data from CoinAPI")
    run_fetch
    return (run_fetch,)


@app.cell
def __(coinapi_fetcher, date, mo, os, output_folder, pd, run_fetch, symbols_to_fetch, time):
    mo.stop(not run_fetch.value and not os.getenv('MARIMO_PIPELINE'), mo.md("Click **Fetch data** to start downloading."))

    def _write_file(data, file_path):
        # Creates parent directories if needed, then writes data to CSV.
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        data.to_csv(file_path, index=True)
        print(f'Wrote file {file_path} with {len(data)} rows')

    def _get_existing_content(file_path):
        # Returns (existing_df, last_date) so the fetch loop can resume from where it left off.
        # Drops the last 2 rows before returning — they may contain partial intraday data.
        if os.path.exists(file_path):
            content = pd.read_csv(file_path)
            if 'date' not in content.columns:
                return (pd.DataFrame(), None)
            content = content.iloc[:-2]
            content['date'] = pd.to_datetime(content['date'])
            content.set_index('date', inplace=True)
            if len(content):
                return (content, content.index[-1].date())
            return (content, None)
        return (pd.DataFrame(), None)

    first_date = date(2010, 1, 1)
    total = len(symbols_to_fetch)
    errors = []

    for i, _symbol_id in enumerate(symbols_to_fetch):
        print(f'------ {i + 1}/{total}: {_symbol_id}')
        file_path = os.path.join(output_folder, 'historical', f'{_symbol_id}.csv')
        existing_content, start_date = _get_existing_content(file_path)
        if start_date is None:
            start_date = first_date
        end_date = date.today()
        if start_date >= end_date:
            print(f'Skip {_symbol_id}, up to date')
            continue
        try:
            new_content = coinapi_fetcher.get_history(_symbol_id, start_date, end_date)
        except Exception as e:
            errors.append(f'{_symbol_id}: {e}')
            continue
        if not new_content.empty:
            data = pd.concat([df for df in [existing_content, new_content] if not df.empty])
            _write_file(data, file_path)
        time.sleep(0.5)

    print(f'Done: {total} symbols processed')
    if errors:
        print(f'\n{len(errors)} errors:')
        for error in errors:
            print(error)
    return ()


@app.cell
def __(active, historical):
    for _symbol_id in active:
        if _symbol_id not in historical:
            print(f'!!!!! Active symbol {_symbol_id} not in historical list')
    return ()


if __name__ == "__main__":
    app.run()
