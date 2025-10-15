import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression, TheilSenRegressor
from typing import NamedTuple

# To use apply/rolling, we must pass in a function that only takes the rolling window as an
# input; therefore, we define beforehand what type of data we wont to get returned.
def create_regression(type):

    def get_linear_regression(series: pd.Series) -> float:
        """
        Calculate the slope of a linear regression over a Series with datetime index.
        Respects irregular spacing between dates.

        Parameters
        ----------
        series : pd.Series
            A pandas Series with a DatetimeIndex and numeric values.

        Returns
        -------
        RegressionResult
            See above; cagr is change per year (4.12 for 4.12% per year)
        """
        series = series.dropna()
        if len(series) < 2:
            return np.nan
        
        # We backtest weekly. Only calculate linear regression for the day we trade on to speed
        # things up (calculations take a *lot* of time).
        # Trades happen on weekday 0
        if (series.index[-1].weekday() != 0):
            return np.nan

        # Convert datetime index to numeric (days since start)
        x_days = (series.index - series.index[0]).days.astype(float)
        x = np.asarray(x_days, dtype=float).reshape(-1, 1)
        y = np.asarray(series.values, dtype=float).reshape(-1)

        # If we use linear regression, intercept is sometimes very close to 0 (when slope is super
        # steep) – that leads to extreme cagrs (as dividing by 0 basically means infinity). 
        # Theil Sen is much more robust.
        model = TheilSenRegressor()
        model.fit(x, y)
        intercept = model.intercept_
        # coefficient is always daily / per tick
        coefficient = model.coef_[0]
        r2 = model.score(x, y)

        # Get CAGR; if we use intercept as 0-point, we might run into trobule as it might be
        # negative (and therefore the whole CAGR would turn negative even though we're growing).
        # Use effective y0 instead that can not be negative.
        # CAGR formula is (y1 - y0) / y0 * 365 / (x1 - x0)
        end_y = y[0] + coefficient * (x_days[-1])
        cagr = (end_y - y[0]) / y[0] * 365 / (x_days[-1])

        if (type == 'r2'):
            return r2
        elif (type == 'cagr'):
            return cagr
        elif (type == 'coefficient'):
            return coefficient
        elif (type == 'intercept'):
            return intercept
        else:
            raise ValueError(f'Unknown type {type}')

    return get_linear_regression