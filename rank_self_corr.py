import os
import pandas as pd

from check import s, get_self_corr, get_self_corr_xin_plus
from config import RECORDS_PATH

submitable_file = os.path.join(RECORDS_PATH, "submitable_alpha.csv")
out_file = os.path.join(RECORDS_PATH, "self_corr_rank.csv")

df = pd.read_csv(submitable_file)
ids = df["id"].dropna().astype(str).unique().tolist()

rows = []
for aid in ids:
    api_df = get_self_corr(s, aid)
    if not api_df.empty and "correlation" in api_df.columns:
        self_corr = float(api_df["correlation"].max())
        source = "api_self_corr"
    else:
        self_corr = float(get_self_corr_xin_plus(s, aid))
        source = "xin_plus_fallback"

    base = df[df["id"] == aid].iloc[-1]
    rows.append({
        "id": aid,
        "self_corr": self_corr,
        "source": source,
        "sharpe": base.get("sharpe", None),
        "fitness": base.get("fitness", None),
        "margin": base.get("margin", None),
        "turnover": base.get("turnover", None),
        "tag": str(base.get("tags", "")),
        "code": str(base.get("code", "")),
    })

rank = pd.DataFrame(rows)

# 主排序：自相关低优先；同分再看 sharpe/fitness/margin 高优先，turnover 低优先
rank = rank.sort_values(
    by=["self_corr", "sharpe", "fitness", "margin", "turnover"],
    ascending=[True, False, False, False, True]
)

rank.to_csv(out_file, index=False, encoding="utf-8-sig")
print(rank.to_string(index=False))
print(f"\n已输出: {out_file}")
