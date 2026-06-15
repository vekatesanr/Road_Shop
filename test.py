import pandas as pd

df = pd.read_excel("data/sales.xlsx")

print(df.columns.tolist())
print(df.head())