import marimo

__generated_with = "0.23.9"
app = marimo.App(width="medium")


@app.cell
def __():
    import marimo as mo
    mo.md("""
    # Crypto Index Strategy — Workflow

    Run the three notebooks below in order:

    1. **`fetch_coinapi.py`** — Download new OHLCV data from CoinAPI
    2. **`create_index.py`** — Rebuild the index and index weights from raw data
    3. **`run_backtest.py`** — Run the backtest and export `signal.csv`
    4. **`trade.py`** — Execute trades on Binance based on the latest signal

    ```
    marimo run src/fetch_coinapi.py
    marimo run src/create_index.py
    marimo run src/run_backtest.py
    marimo run src/trade.py
    ```
    """)
    return ()


if __name__ == "__main__":
    app.run()
