"""Summaries of the time to halfway: a pitch the market never priced within a minute is slow, not missing."""
import numpy as np
import pandas as pd

from analysis import hq


def test_a_pitch_never_priced_counts_as_slower_than_any_that_was():
    s = pd.Series([1.0, 2.0, np.nan, np.nan, 3.0])
    assert hq(s) == 3.0                            # 1, 2, 3, never, never: the middle one is 3
    assert s.median() == 2.0                       # dropping the two never-priced pitches would say 2
    assert np.isnan(hq(pd.Series([1.0, np.nan, np.nan])))     # a median past a minute is reported as unknown
