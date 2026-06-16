from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Only needed for the type hint; importing it at runtime would pull in pandas
    # (~60-90 MB) just to load this module. The actual work is done via methods on
    # the df_grouped object passed in, so no runtime pandas import is required here.
    from pandas.core.groupby import DataFrameGroupBy


class SummaryStats(object):
    def __init__(self, df_grouped: DataFrameGroupBy, field_name: str):
        self.field_name = field_name

        n = df_grouped[field_name].count()
        min = df_grouped[field_name].min()
        max = df_grouped[field_name].max()
        mean = df_grouped[field_name].mean()
        median = df_grouped[field_name].median()
        std = df_grouped[field_name].std()
        sem = df_grouped[field_name].sem()
        var = df_grouped[field_name].var()

        self.condition = list(df_grouped.groups.keys())
        self.n = list(n)
        self.min = list(min)
        self.max = list(max)
        self.mean = list(mean)
        self.median = list(median)
        self.std = list(std)
        self.sem = list(sem)
        self.var = list(var)
