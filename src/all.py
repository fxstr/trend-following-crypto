import papermill as pm

notebooks = [
    ('src/fetch_coinapi.ipynb', 'out/fetch_coinapi.ipynb'),
    ('src/create_index.ipynb', 'out/create_index.ipynb'),
    ('src/backtest.ipynb', 'out/backtest.ipynb'),
]

for input, output in notebooks:
    pm.execute_notebook(input, output, cwd='src')