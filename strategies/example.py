import pandas as pd
from backtest.strategy import Strategy


class EMACrossover(Strategy):
    name     = "ema_crossover"
    lookback = 100   # need at least 100 ticks for slow EMA

    _FAST = 20
    _SLOW = 100

    def on_data(self, window: pd.DataFrame) -> int:
        ltp = window["ltp"]
        fast = ltp.ewm(span=self._FAST, adjust=False).mean().iloc[-1]
        slow = ltp.ewm(span=self._SLOW, adjust=False).mean().iloc[-1]

        if fast > slow:
            return 1
        elif fast < slow:
            return -1
        return 0
