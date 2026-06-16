"""
Example strategy: simple moving-average crossover.

The strategy goes long when the last LTP crosses above its lookback-window SMA,
and short when it crosses below. It holds the position until the opposite
cross occurs.

Use this as a template — copy the file, rename the class, change `name`, and
implement your own `on_data` logic.
"""

import pandas as pd
from backtest.strategy import Strategy


class SMACrossover(Strategy):
    name     = "sma_crossover"
    lookback = 30           # engine feeds the last 30 ticks each call

    def on_data(self, window: pd.DataFrame) -> int:
        """
        window: DataFrame with `lookback` rows (oldest first, newest last).
        Available columns: timestamp, ltp, open, high, low, close, atp, vtt,
                           oi, tbq, tsq, bid1_p..bid5_q, ask1_p..ask5_q
        """
        ltp = window["ltp"]
        sma = ltp.mean()
        last = ltp.iloc[-1]

        if last > sma:
            return 1    # price above average → long
        elif last < sma:
            return -1   # price below average → short
        return 0
