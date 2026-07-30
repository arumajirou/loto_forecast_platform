from pathlib import Path
import numpy as np
import pandas as pd

rng=np.random.default_rng(42)
rows=[]
for draw_no in range(1,161):
    nums=sorted(rng.choice(np.arange(1,38),size=7,replace=False).tolist())
    rows.append({"draw_no":draw_no,"draw_date":(pd.Timestamp("2023-01-06")+pd.Timedelta(7*(draw_no-1), unit="D")).date().isoformat(),**{f"n{i+1}":n for i,n in enumerate(nums)}})
out=Path(__file__).with_name("sample_loto7.csv")
pd.DataFrame(rows).to_csv(out,index=False)
print(out)
