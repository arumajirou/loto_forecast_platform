from __future__ import annotations
import argparse, csv, hashlib, json
from pathlib import Path
from typing import Any
import yaml

BASELINE = {
    "input_size": 128,
    "encoder_hidden_size": 32,
    "context_size": 10,
    "decoder_hidden_size": 32,
    "kernel_size": 3,
    "dilations": [1, 2, 4],
    "learning_rate": 0.001,
    "scaler_type": "robust",
    "batch_size": 32,
}
LEVELS = {
    "input_size": [64, 128, 256],
    "encoder_hidden_size": [16, 32],
    "context_size": [5, 10],
    "decoder_hidden_size": [16, 32],
    "kernel_size": [2, 3],
    "dilations": [[1, 2], [1, 2, 4]],
    "learning_rate": [0.0003, 0.001],
    "scaler_type": ["standard", "robust"],
}
def args():
    p=argparse.ArgumentParser()
    p.add_argument("--base-config", type=Path, required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    return p.parse_args()
def cid(x: dict[str,Any])->str:
    return hashlib.sha256(json.dumps(x,sort_keys=True,separators=(",",":")).encode()).hexdigest()[:12]
def write_yaml(path:Path,obj:dict[str,Any])->None:
    path.write_text(yaml.safe_dump(obj,sort_keys=False,allow_unicode=True),encoding="utf-8")
def main():
    a=args(); a.output_dir.mkdir(parents=True,exist_ok=True)
    base=yaml.safe_load(a.base_config.read_text(encoding="utf-8"))
    rows=[{"design_id":"baseline","changed_factor":"baseline","changed_level":"baseline",**BASELINE}]
    for factor,levels in LEVELS.items():
        for level in levels:
            if level==BASELINE[factor]: continue
            row=dict(BASELINE); row[factor]=level
            rows.append({"design_id":f"{factor}-{cid(row)}","changed_factor":factor,"changed_level":json.dumps(level),**row})
    with (a.output_dir/"screening_design.csv").open("w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0]), lineterminator="\n"); w.writeheader(); w.writerows(rows)
    sd=a.output_dir/"screening"; sd.mkdir(exist_ok=True)
    for row in rows:
        cfg=json.loads(json.dumps(base))
        cfg["search"]={k:[row[k]] for k in LEVELS}
        cfg["search"]["batch_size"]=[32]
        cfg["experiment"]["seeds"]=[17,42,137]
        cfg["experiment"]["rolling_points"]=20
        cfg["runtime"]["deterministic"]="warn"
        cfg["runtime"]["precision"]="32-true"
        cfg["experiment"]["name"]="numbers3-n1-tcn-screening-"+row["design_id"]
        write_yaml(sd/f'{row["design_id"]}.yaml',cfg)
    full=json.loads(json.dumps(base))
    full["search"]={**LEVELS,"batch_size":[32]}
    full["experiment"]["seeds"]=[42]
    full["experiment"]["rolling_points"]=1
    write_yaml(a.output_dir/"full_grid_384.yaml",full)
    summary={"full_grid_combinations":384,"screening_configurations":len(rows),"screening_fits":len(rows)*3*20}
    (a.output_dir/"design_summary.json").write_text(json.dumps(summary,indent=2)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2))
if __name__=="__main__": main()
