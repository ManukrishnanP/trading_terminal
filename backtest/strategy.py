from abc import ABC, abstractmethod
import pandas as pd


class Strategy(ABC):
    """
    Subclass this and implement on_data(). Declare `name` and `lookback` as class attributes.

    Example
    -------
    class MyStrat(Strategy):
        name     = "my_strat"
        lookback = 20          # engine feeds a rolling window of this many ticks

        def on_data(self, window: pd.DataFrame) -> int:
            # window has exactly `lookback` rows, most-recent last
            # cols: timestamp, ltp, open, high, low, close, atp, vtt, oi,
            #       tbq, tsq, bid1_p..bid5_q, ask1_p..ask5_q
            sma = window["ltp"].mean()
            return 1 if window["ltp"].iloc[-1] > sma else -1
    """

    name: str = "strategy"
    lookback: int = 1

    @abstractmethod
    def on_data(self, window: pd.DataFrame) -> int:
        """
        Called for each tick once `lookback` history is available.

        Parameters
        ----------
        window : DataFrame with exactly `lookback` rows (index reset to 0..lookback-1),
                 oldest row first, newest last.

        Returns
        -------
        1   buy / go long
        -1  sell / go short
        0   hold / no position
        """
        ...
