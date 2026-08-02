from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np, pandas as pd

def args():
    p=argparse.ArgumentParser()
    p.add_argument("--runs-root",type=Path,required=True)
    p.add_argument("--design",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    return p.parse_args()
def ci(x,repeats=5000):
    x=np.asarray(x,float)
    if len(x)==0:return (np.nan,np.nan)
    rng=np.random.default_rng(20260802)
    m=x[rng.integers(0,len(x),size=(repeats,len(x)))].mean(1)
    return tuple(np.quantile(m,[.025,.975]))
def main():
    a=args(); a.output.mkdir(parents=True,exist_ok=True)
    design=pd.read_csv(a.design)
    preds=[]; trials=[]
    for cfgp in a.runs_root.glob("*/resolved_config.json"):
        run=cfgp.parent
        pp=run/"predictions.parquet"; tp=run/"trial_results.parquet"
        if not pp.exists() or not tp.exists(): continue
        cfg=json.loads(cfgp.read_text(encoding="utf-8"))
        name=cfg.get("config",{}).get("experiment",{}).get("name","")
        if "tcn-screening-" not in name: continue
        did=name.split("tcn-screening-",1)[1]
        y = pd.read_parquet(tp)

        if y.empty:
            continue

        if not (y["status"] == "PASS").all():
            continue

        x = pd.read_parquet(pp)

        if x.empty:
            continue

        x["design_id"] = did
        y["design_id"] = did
        x["run_mtime_ns"] = pp.stat().st_mtime_ns
        y["run_mtime_ns"] = tp.stat().st_mtime_ns

        preds.append(x)
        trials.append(y)
    if not preds: raise SystemExit("No screening runs")
    p = pd.concat(
        preds,
        ignore_index=True,
    )
    t = pd.concat(
        trials,
        ignore_index=True,
    )

    # Keep only the latest completed run for each design.
    latest = (
        p.groupby("design_id")[
            "run_mtime_ns"
        ]
        .max()
        .rename("latest_mtime_ns")
    )

    p = p.merge(
        latest,
        on="design_id",
        how="inner",
    )
    p = p[
        p["run_mtime_ns"]
        == p["latest_mtime_ns"]
    ].copy()

    t = t.merge(
        latest,
        on="design_id",
        how="inner",
    )
    t = t[
        t["run_mtime_ns"]
        == t["latest_mtime_ns"]
    ].copy()

    duplicate_keys = p.duplicated(
        subset=[
            "design_id",
            "seed",
            "test_index",
        ],
        keep=False,
    )

    if duplicate_keys.any():
        raise RuntimeError(
            "Duplicate screening prediction keys "
            "remain after latest-run filtering"
        )
    b=p[p.design_id=="baseline"][["seed","test_index","within_1","digit_abs_error","digit_squared_error","prediction_raw"]]
    b=b.rename(columns={"within_1":"b_hit","digit_abs_error":"b_mae","digit_squared_error":"b_mse","prediction_raw":"b_raw"})
    z=p.merge(b,on=["seed","test_index"],how="inner")
    z["d_hit"]=z.within_1-z.b_hit; z["d_mae"]=z.digit_abs_error-z.b_mae; z["d_mse"]=z.digit_squared_error-z.b_mse; z["d_raw"]=z.prediction_raw-z.b_raw
    rows=[]
    for did,g in z.groupby("design_id"):
        d=design[design.design_id==did].iloc[0]
        h1,h2=ci(g.d_hit); m1,m2=ci(g.d_mae)
        rows.append({"design_id":did,"changed_factor":d.changed_factor,"changed_level":d.changed_level,"n":len(g),
                     "hit":g.within_1.mean(),"mae":g.digit_abs_error.mean(),"mse":g.digit_squared_error.mean(),
                     "rmse":np.sqrt(g.digit_squared_error.mean()),"delta_hit":g.d_hit.mean(),"delta_hit_ci_low":h1,
                     "delta_hit_ci_high":h2,"delta_mae":g.d_mae.mean(),"delta_mae_ci_low":m1,"delta_mae_ci_high":m2,
                     "raw_delta_abs_mean":g.d_raw.abs().mean()})
    s=pd.DataFrame(rows)
    speed=t.groupby("design_id",as_index=False).agg(fit_seconds_median=("fit_seconds","median"),
        predict_seconds_median=("predict_seconds","median"),peak_vram_mib_max=("peak_vram_mib","max"),
        failed=("status",lambda x:int((x!="PASS").sum())))
    s=s.merge(speed,on="design_id",how="left").sort_values(["delta_hit","delta_mae"],ascending=[False,True])
    s.to_csv(a.output/"screening_effects.csv",index=False); z.to_parquet(a.output/"paired_predictions.parquet",index=False)
    rec=s[(s.changed_factor!="baseline") & ((s.delta_hit.abs()>=.03)|(s.delta_mae.abs()>=.10)|
        (s.delta_hit_ci_low>0)|(s.delta_hit_ci_high<0)|(s.delta_mae_ci_high<0)|(s.delta_mae_ci_low>0))]
    rec.to_csv(a.output/"recommended_interaction_factors.csv",index=False)
    out={"completed_designs":int(s.design_id.nunique()),"paired_rows":len(z),
         "recommended_factors":sorted(rec.changed_factor.unique().tolist())}
    (a.output/"analysis_summary.json").write_text(json.dumps(out,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps(out,indent=2,ensure_ascii=False))
if __name__=="__main__":main()
