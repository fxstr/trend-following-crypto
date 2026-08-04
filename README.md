# Crypto Index Strategy

Momentum-based strategy that goes long a market-cap-weighted top-20 crypto index and moves to cash based on multi-lookback TheilSen CAGR. Rebalances weekly on Binance.

## Setup

```bash
poetry install
```

Create a `.env` file:

```bash
COINAPI_EXCHANGE=BINANCE
COINAPI_BASE_CURRENCY=USDT
BINANCE_API_KEY=
BINANCE_API_SECRET=
BINANCE_TEST_API=false          # set to true to use Binance testnet
```

## Run

**Pipeline** — fetch data, rebuild index, run backtest, export `signal.csv`. Run weekly via cron:

```bash
mkdir -p output && \
MARIMO_PIPELINE=1 poetry run marimo export html src/fetch_coinapi.py -o output/fetch_coinapi.html -f 2> >(grep -v "resource_tracker\|leaked semaphore" >&2) && \
MARIMO_PIPELINE=1 poetry run marimo export html src/create_index.py -o output/create_index.html -f 2> >(grep -v "resource_tracker\|leaked semaphore" >&2) && \
MARIMO_PIPELINE=1 poetry run marimo export html src/run_backtest.py -o output/run_backtest.html -f 2> >(grep -v "resource_tracker\|leaked semaphore" >&2)
```

The stderr filter drops a harmless `resource_tracker: leaked semaphore` warning that
Python's multiprocessing module occasionally emits from a background cleanup process
(unrelated to `bt`/sklearn's actual work) — cosmetic only, doesn't affect output or exit code.

Outputs land in `output/`. Open locally with `open output/*.html`, or on Hetzner serve them temporarily:

```bash
cd output && python -m http.server 8080
# then SSH tunnel: ssh -L 8080:localhost:8080 user@your-server
```

**Execute trades** — start the marimo app on the server (no browser needed server-side):

```bash
poetry run marimo run src/trade.py --headless --no-token --redirect-console-to-browser
```

`--redirect-console-to-browser` is required to see `print()` output (signal, holdings, planned
trades) in the browser — without it, `marimo run` sends console logs only to the server terminal.

Then open an SSH tunnel from your local machine and go to `http://localhost:2718`:

```bash
ssh -L 2718:localhost:2718 user@your-server
```

To explore or edit individual notebooks locally:

```bash
poetry run marimo edit src/run_backtest.py
```
