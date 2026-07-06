import pandas as pd
from scipy import sparse
from pandas.api.types import CategoricalDtype
import numpy as np

from lightfm.datasets import fetch_stackexchange

data = fetch_stackexchange('crossvalidated',
                           test_set_fraction=0.1,
                           indicator_features=False,
                           tag_features=True)

# Create two sample DataFrames
df1 = pd.DataFrame({
    'ID': [1, 2, 3, 2],
    'Name': ['Alice', 'Bob', 'Charlie', 'David'],
    'Rating': [5, 4, 3, 2]
})

df2 = pd.DataFrame({
    'ID': [1, 2, 3, 4],
    'Designer': ['des1', 'des2', 'des3', 'des4'],
    'Status': [['Completed','In Progress'], ['In Progress'], ['Pending'], ['Cancelled']]
})

df2 = df2.explode('Status')[['ID','Status']]

print(df2.head())

statuses = df2['Status'].unique()
status_cat = CategoricalDtype(categories=sorted(statuses), ordered=True)
status_index = df2['Status'].astype(status_cat).cat.codes
print(status_index)
csr_sm = sparse.coo_matrix((status_index, (df2['ID'], status_index)))
print(csr_sm)


item_features = data['item_features']
tag_labels = data['item_feature_labels']

print(item_features)

