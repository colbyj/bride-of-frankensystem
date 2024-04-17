import pandas
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

