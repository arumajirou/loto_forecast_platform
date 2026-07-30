from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from loto.contracts import CandidateProbability, ForecastPackage
from loto.data.canonical import canonicalize_loto7, save_manifest, to_candidate_table
from loto.decoding.hybrid import decode_hybrid
from loto.evaluation.metrics import brier_score, evaluate_draws, log_loss
from loto.events.publisher import EventPublisher
from loto.features.pipeline import build_candidate_features, build_next_candidate_features, feature_manifest
from loto.models.baselines import FrequencyCandidateAdapter, UniformCandidateAdapter
from loto.models.position import PositionFrequencyAdapter
from loto.observability.gpu import collect_gpu_evidence
from loto.observability.metrics import FORECAST_SEALED, STAGE_TOTAL
from loto.observability.mlflow_bridge import MlflowBridge
from loto.registry.release import create_release_bundle
from loto.registry.sqlite import Registry
from loto.registry.full import PlatformRegistry
from loto.registry.artifacts import ArtifactStore
from loto.sealing.manifest import seal_payload, verify_seal

STAGES = ["INGEST","VALIDATE","CANONICALIZE","BUILD_FEATURES","TRAIN","CALIBRATE","DECODE","EVALUATE","SEAL_FORECAST","REGISTER"]


def _candidate_targets(numbers: list[int]) -> np.ndarray:
    target=np.zeros(37,dtype=float); target[np.asarray(numbers)-1]=1; return target


def run_trusted_vertical_slice(input_csv: str | Path, output_dir: str | Path, *, secret: bytes,
                               backtest_draws: int = 20, windows: tuple[int,...]=(10,30,100)) -> dict:
    output=Path(output_dir); output.mkdir(parents=True,exist_ok=True)
    run_id=f"run-{uuid.uuid4().hex[:12]}"; registry=Registry(output/"registry.sqlite3"); publisher=EventPublisher(output/"events.jsonl")
    platform_registry=PlatformRegistry(os.environ.get("LOTO_REGISTRY_URL", str(output/"platform.sqlite3")))
    platform_registry.create_run(run_id)
    platform_registry.update_run(run_id,status="RUNNING",current_stage="INGEST")
    evidence=collect_gpu_evidence(gpu_required=False)
    (output/"resource_evidence.json").write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding="utf-8")
    def stage(name,status="SUCCEEDED",payload=None):
        body=payload or {}
        registry.record_stage(run_id,name,status,body)
        task_status = "RUNNING" if status == "STARTED" else status
        platform_registry.record_task(run_id,name,task_status,output_uri=body.get("artifact_uri"))
        platform_registry.update_run(run_id,status="RUNNING" if task_status not in {"FAILED"} else "FAILED",current_stage=name,error=body if task_status=="FAILED" else None)
        publisher.publish("run.stage.changed",{"run_id":run_id,"stage":name,"status":status,"payload":body})
        if STAGE_TOTAL is not None:
            STAGE_TOTAL.labels(stage=name,status=status).inc()
    stage("INGEST","STARTED",{"input":str(input_csv)})
    raw=pd.read_csv(input_csv); stage("INGEST",payload={"rows":len(raw)})
    master, manifest=canonicalize_loto7(raw,source=str(input_csv)); stage("VALIDATE",payload={"data_version":manifest.data_version})
    master.to_csv(output/"canonical.csv",index=False); save_manifest(manifest,output/"dataset_manifest.json"); stage("CANONICALIZE",payload={"sha256":manifest.sha256})
    features=build_candidate_features(master,windows=windows); feat_manifest=feature_manifest(features,manifest.data_version,windows)
    features.to_csv(output/"candidate_features.csv",index=False)
    (output/"feature_manifest.json").write_text(json.dumps(feat_manifest.model_dump(mode="json"),indent=2),encoding="utf-8")
    stage("BUILD_FEATURES",payload={"feature_set_id":feat_manifest.feature_set_id,"rows":len(features)})

    start=max(8,len(master)-max(1,backtest_draws)); actuals=[]; preds_uniform=[]; preds_frequency=[]; targets=[]; probs_u=[]; probs_f=[]
    for idx in range(start,len(master)):
        history=master.iloc[:idx]; current=master.iloc[idx]; hist_candidates=to_candidate_table(history)
        query=pd.DataFrame({"candidate_number":range(1,38)})
        u=UniformCandidateAdapter().fit(hist_candidates).predict(query)
        f=FrequencyCandidateAdapter().fit(hist_candidates).predict(query)
        pos=PositionFrequencyAdapter().fit(history).predict_matrix()
        du=decode_hybrid(u["rank_score"].to_numpy(),pos,top_k=1)[0].numbers
        df=decode_hybrid(f["rank_score"].to_numpy(),pos,top_k=1)[0].numbers
        actual=[int(current[f"n{i}"]) for i in range(1,8)]
        actuals.append(actual); preds_uniform.append(du); preds_frequency.append(df)
        targets.append(_candidate_targets(actual)); probs_u.append(u["probability"].to_numpy()); probs_f.append(f["probability"].to_numpy())
    if actuals:
        act=np.asarray(actuals); pu=np.asarray(preds_uniform); pf=np.asarray(preds_frequency); y=np.asarray(targets)
        metrics_u=evaluate_draws(act,pu)|{"brier":brier_score(y,np.asarray(probs_u)),"log_loss":log_loss(y,np.asarray(probs_u))}
        metrics_f=evaluate_draws(act,pf)|{"brier":brier_score(y,np.asarray(probs_f)),"log_loss":log_loss(y,np.asarray(probs_f))}
    else:
        metrics_u=metrics_f={"mean_hits_at_7":0.0,"position_mae":0.0,"position_mse":0.0,"within_1_rate":0.0,"brier":0.0,"log_loss":0.0}
    champion="frequency" if (metrics_f["mean_hits_at_7"]>metrics_u["mean_hits_at_7"] and metrics_f["brier"]<=metrics_u["brier"]*1.02) else "uniform"
    stage("TRAIN",payload={"models":["uniform","frequency"],"selected":champion}); stage("CALIBRATE",payload={"method":"identity-v1"})

    all_candidates=to_candidate_table(master); query=build_next_candidate_features(master,windows=windows)
    model=FrequencyCandidateAdapter().fit(all_candidates) if champion=="frequency" else UniformCandidateAdapter().fit(all_candidates)
    pred=model.predict(query); pos=PositionFrequencyAdapter().fit(master).predict_matrix(); combos=decode_hybrid(pred["rank_score"].to_numpy(),pos,top_k=20)
    stage("DECODE",payload={"top":combos[0].numbers})
    report={"uniform":metrics_u,"frequency":metrics_f,"champion":champion,"backtest_draws":len(actuals)}
    (output/"evaluation.json").write_text(json.dumps(report,indent=2),encoding="utf-8"); stage("EVALUATE",payload=report)

    created=datetime.now(UTC); draw_time=max(created+timedelta(minutes=1),master["draw_date"].max().to_pydatetime()+timedelta(days=7))
    forecast=ForecastPackage(forecast_id=f"forecast-{uuid.uuid4().hex[:12]}",draw_id=f"loto7-{int(master.draw_no.max())+1}",
        model_id=model.model_id,data_version=manifest.data_version,feature_set_id=feat_manifest.feature_set_id,
        created_at=created,draw_time=draw_time,combination=combos[0],
        candidates=[CandidateProbability(candidate_number=int(r.candidate_number),probability=float(r.probability),rank_score=float(r.rank_score)) for r in pred.itertuples()],
        metadata={"run_id":run_id,"decoder":"hybrid-dp-v1","champion_selection":champion})
    payload=forecast.model_dump(mode="json"); sealed=seal_payload(payload,secret); verified=verify_seal(sealed,secret)
    (output/"forecast.json").write_text(json.dumps(payload,ensure_ascii=False,indent=2),encoding="utf-8")
    (output/"forecast.sealed.json").write_text(json.dumps(sealed,ensure_ascii=False,indent=2),encoding="utf-8")
    stage("SEAL_FORECAST",payload={"forecast_id":forecast.forecast_id,"verified":verified})
    publisher.publish("forecast.sealed",{"run_id":run_id,"forecast_id":forecast.forecast_id,"verified":verified})
    if FORECAST_SEALED is not None:
        FORECAST_SEALED.inc()
    registry.record_forecast(forecast.forecast_id,run_id,sealed,verified)
    platform_registry.register_forecast(forecast.forecast_id,run_id,forecast.draw_id,sealed,verified)
    stage("REGISTER",payload={"forecast_id":forecast.forecast_id})
    base_artifacts=[output/name for name in ("dataset_manifest.json","feature_manifest.json","evaluation.json","forecast.json","forecast.sealed.json","resource_evidence.json","events.jsonl")]
    bridge=MlflowBridge(os.environ.get("MLFLOW_TRACKING_URI","http://127.0.0.1:5050"),os.environ.get("MLFLOW_EXPERIMENT_NAME","loto-trusted-vertical-slice"))
    flat_metrics={f"{champion}_{k}":float(v) for k,v in report[champion].items()}
    mlflow_status=bridge.record_run(run_id,{"champion":champion,"data_version":manifest.data_version,"feature_set_id":feat_manifest.feature_set_id},flat_metrics,base_artifacts)
    (output/"mlflow_status.json").write_text(json.dumps(mlflow_status,ensure_ascii=False,indent=2),encoding="utf-8")
    release_id=f"release-{run_id}"
    publisher.publish("release.bundle.created",{"run_id":run_id,"release_id":release_id})
    artifacts=[*base_artifacts,output/"mlflow_status.json"]
    bundle=create_release_bundle(release_id,artifacts,output/"release_bundle.json")
    store=ArtifactStore(os.environ.get("LOTO_ARTIFACT_STORE", str(output/"artifact_store")))
    artifact_index={Path(p).name:store.put_file(p,namespace=run_id) for p in artifacts+[output/"release_bundle.json"]}
    (output/"artifact_index.json").write_text(json.dumps(artifact_index,ensure_ascii=False,indent=2),encoding="utf-8")
    platform_registry.register_model(model.model_id,champion,artifact_index["release_bundle.json"]["uri"],report[champion],{"run_id":run_id,"data_version":manifest.data_version})
    platform_registry.update_run(run_id,status="SUCCEEDED",current_stage="REGISTER",release_id=release_id)
    platform_registry.audit("system","complete","run",run_id,"trusted vertical slice completed",{"release_id":release_id})
    return {"run_id":run_id,"forecast":payload,"seal_verified":verified,"evaluation":report,"release_id":bundle["release_id"],"output_dir":str(output)}
