import bt

def run(strategy_name, data, weights):
    # Weekly rebalance into a single asset (the index) with a time-varying target weight.
    # weights is a Series of 0/1 (or fractional) values aligned to data's index.
  strategy = bt.Strategy(
      strategy_name,
      [
        #   bt.algos.RunDaily(),
          bt.algos.RunWeekly(),
          # bt.algos.RunOnDate(*dates),
          # bt.algos.RunMonthly(),
          bt.algos.SelectAll(),
          bt.algos.WeighTarget(weights),
          bt.algos.Rebalance(),
      ],
  )

  test = bt.Backtest(strategy, data, initial_capital=100000)

  result = bt.run(
      test,
  )
  return result