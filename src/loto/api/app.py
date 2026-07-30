from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import HTMLResponse, Response
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from loto.observability import metrics as _loto_metrics  # noqa: F401 -- register Prometheus collectors
from pydantic import BaseModel, Field

from loto.evaluation.shadow import score_combination
from loto.models.catalog import get_model_spec, list_model_specs
from loto.models.neuralforecast_adapter import AutoModelRequest, resolve_auto_model_plan
from loto.data.lotteries import load_lottery_specs
from loto.registry.full import PlatformRegistry
from loto.security import Identity, authenticate, parse_tokens, require_role
from loto.sealing.manifest import verify_seal


class ScoreRequest(BaseModel):
    actual: list[int] = Field(min_length=7, max_length=7)


class ApprovalRequest(BaseModel):
    object_type: str
    object_id: str
    action: str
    reason: str = Field(min_length=3)


class ApprovalDecision(BaseModel):
    object_type: str
    object_id: str
    action: str
    approved: bool


class ModelPlanRequest(BaseModel):
    model_name: str
    h: int = Field(default=1, ge=1)
    backend: str | None = None
    cpus: int = Field(default=4, ge=1)
    gpus: int = Field(default=0, ge=0)
    parallel_trials: int = Field(default=1, ge=1)
    num_samples: int = Field(default=10, ge=1)
    precision: str = "32-true"
    n_series: int | None = Field(default=None, ge=1)
    search_strategy: str = "auto"
    config: dict = Field(default_factory=dict)


def create_app(output_dir: str | Path = ".", *, registry_url: str | None = None) -> FastAPI:
    root = Path(output_dir)
    registry = PlatformRegistry(registry_url or os.environ.get("LOTO_REGISTRY_URL", root / "platform.sqlite3"))
    token_map = parse_tokens()
    app = FastAPI(title="Loto Forecast Platform API", version="2.1.0")

    def current_identity(authorization: Annotated[str | None, Header()] = None) -> Identity:
        if not token_map and os.environ.get("LOTO_AUTH_DISABLED", "0") == "1":
            return Identity("local", "administrator")
        if not authorization or not authorization.lower().startswith("bearer "):
            raise HTTPException(status_code=401, detail="Bearer token required")
        try:
            return authenticate(authorization.split(" ", 1)[1], token_map)
        except PermissionError as exc:
            raise HTTPException(status_code=401, detail=str(exc)) from exc

    def need(minimum: str):
        def dep(identity: Identity = Depends(current_identity)) -> Identity:
            try:
                require_role(identity, minimum)
            except PermissionError as exc:
                raise HTTPException(status_code=403, detail=str(exc)) from exc
            return identity
        return dep

    @app.get("/", response_class=HTMLResponse)
    def dashboard() -> str:
        return """<!doctype html><html lang='ja'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>Loto Forecast Platform v2.1</title>
<style>:root{color-scheme:light dark;--bg:#0b1020;--card:#151c31;--line:#33405f;--ok:#22c55e;--warn:#f59e0b}*{box-sizing:border-box}body{font-family:system-ui,sans-serif;max-width:1280px;margin:0 auto;padding:1.4rem;background:var(--bg);color:#e8eefc}.head{display:flex;gap:1rem;align-items:center;justify-content:space-between;flex-wrap:wrap}.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:1rem}.card{border:1px solid var(--line);padding:1rem;border-radius:.9rem;background:var(--card)}a{color:#93c5fd;font-weight:650}.status{display:inline-block;padding:.2rem .6rem;border-radius:99px;background:#166534}.metric{font-size:1.7rem;font-weight:700}.muted{opacity:.72}table{width:100%;border-collapse:collapse}td,th{padding:.5rem;border-bottom:1px solid var(--line);text-align:left;font-size:.9rem}code{word-break:break-all}</style></head><body>
<div class='head'><div><h1>Loto Forecast Platform <small>v2.1</small></h1><p class='muted'>Loto Trusted Vertical Slice compatible</p></div><span class='status' id='health'>loading</span></div>
<div class='grid'><div class='card'><div class='muted'>Models</div><div class='metric' id='models'>-</div><a href='/api/v2/models'>Registry</a></div><div class='card'><div class='muted'>Runs</div><div class='metric' id='runs'>-</div><a href='/api/v2/runs'>Run index</a></div><div class='card'><div class='muted'>Games</div><div class='metric' id='games'>-</div><a href='/api/v2/data/games'>Data sources</a></div><div class='card'><div class='muted'>Observability</div><a href='/metrics'>Prometheus</a> / <a href='/docs'>OpenAPI</a><p>events, resources, artifact status</p></div></div>
<h2>Model Parameter Lab</h2><div class='card'><div class='grid'><label>AutoModel<select id='lab-model'></select></label><label>Backend<select id='lab-backend'><option>optuna</option><option>ray</option></select></label><label>Horizon<input id='lab-h' type='number' min='1' value='1'></label><label>Trials<input id='lab-trials' type='number' min='1' value='10'></label></div><p><button id='lab-plan' type='button'>Resolve plan</button></p><pre id='lab-output' class='muted'>Select a model and resolve a non-executing plan.</pre></div><h2>Latest leaderboard</h2><div class='card'><table><thead><tr><th>Rank</th><th>Model</th><th>Score</th><th>±1</th><th>MAE</th></tr></thead><tbody id='leaderboard'><tr><td colspan='5'>No result</td></tr></tbody></table></div>
<script>const el=id=>document.getElementById(id);async function j(u,o){const r=await fetch(u,o);if(!r.ok)throw Error(r.status);return r.json()}Promise.allSettled([j('/health'),j('/api/v2/models'),j('/api/v2/runs'),j('/api/v2/data/games'),j('/api/v2/leaderboard')]).then(x=>{if(x[0].status==='fulfilled'){el('health').textContent=x[0].value.status;el('health').style.background='#166534'}el('models').textContent=x[1].status==='fulfilled'?x[1].value.length:'-';el('runs').textContent=x[2].status==='fulfilled'?x[2].value.length:'-';el('games').textContent=x[3].status==='fulfilled'?x[3].value.length:'-';if(x[1].status==='fulfilled'){el('lab-model').innerHTML=x[1].value.filter(m=>m.library==='neuralforecast_auto').map(m=>`<option value='${m.class_name}'>${m.class_name}</option>`).join('')}if(x[4].status==='fulfilled'){el('leaderboard').innerHTML=x[4].value.slice(0,10).map(r=>`<tr><td>${r.rank??''}</td><td>${r.model_id??''}</td><td>${Number(r.composite_score??0).toFixed(4)}</td><td>${Number(r.mean_within_1??0).toFixed(3)}</td><td>${Number(r.position_mae??0).toFixed(3)}</td></tr>`).join('')}});el('lab-plan').addEventListener('click',async()=>{try{const body={model_name:el('lab-model').value,backend:el('lab-backend').value,h:Number(el('lab-h').value),num_samples:Number(el('lab-trials').value)};el('lab-output').textContent=JSON.stringify(await j('/api/v2/model-plan',{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(body)}),null,2)}catch(e){el('lab-output').textContent='Plan unavailable: '+e}})</script></body></html>"""



    @app.get("/api/v2/models")
    def models(priority: str | None = None, available_only: bool = False,
               _identity: Identity = Depends(need("viewer"))) -> list[dict]:
        return [item.to_dict() for item in list_model_specs(priority=priority, available_only=available_only)]

    @app.get("/api/v2/models/{model_id}")
    def model_detail(model_id: str, _identity: Identity = Depends(need("viewer"))) -> dict:
        try:
            return get_model_spec(model_id).to_dict()
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/api/v2/model-plan")
    def model_plan(request: ModelPlanRequest,
                   _identity: Identity = Depends(need("viewer"))) -> dict:
        try:
            plan = resolve_auto_model_plan(AutoModelRequest(**request.model_dump()))
        except (TypeError, ValueError) as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        constructor = {
            key: value for key, value in plan.constructor_kwargs.items()
            if key not in {"config", "search_alg"}
        }
        return {
            "model_name": plan.model_name,
            "backend": plan.backend,
            "precision": plan.precision,
            "config": plan.config,
            "constructor": constructor,
            "search_algorithm": plan.search_algorithm,
            "adjustments": list(plan.adjustments),
        }

    def _run_directories() -> list[Path]:
        candidates: list[Path] = []
        for base in (root, root / "runs"):
            if base.exists() and base.is_dir():
                for item in base.iterdir():
                    if item.is_dir() and (item / "research_summary.json").exists():
                        candidates.append(item)
        if (root / "research_summary.json").exists():
            candidates.append(root)
        unique = {item.resolve(): item for item in candidates}
        return sorted(unique.values(), key=lambda item: item.stat().st_mtime, reverse=True)

    def _safe_run(run_id: str) -> Path:
        for item in _run_directories():
            try:
                summary = json.loads((item / "research_summary.json").read_text(encoding="utf-8"))
            except Exception:
                continue
            if summary.get("run_id") == run_id or item.name == run_id:
                return item
        raise HTTPException(status_code=404, detail="run not found")

    @app.get("/api/v2/data/games")
    def data_games(_identity: Identity = Depends(need("viewer"))) -> list[dict]:
        return [spec.__dict__ | {"candidate_numbers": list(spec.candidate_numbers)} for spec in load_lottery_specs().values()]

    @app.get("/api/v2/runs")
    def run_index(_identity: Identity = Depends(need("viewer"))) -> list[dict]:
        rows = []
        for item in _run_directories():
            try:
                summary = json.loads((item / "research_summary.json").read_text(encoding="utf-8"))
                rows.append({"path": str(item), **summary})
            except Exception as exc:
                rows.append({"path": str(item), "status": "CORRUPT", "error": str(exc)})
        return rows

    @app.get("/api/v2/runs/{run_id}")
    def run_summary(run_id: str, _identity: Identity = Depends(need("viewer"))) -> dict:
        item = _safe_run(run_id)
        return json.loads((item / "research_summary.json").read_text(encoding="utf-8"))

    @app.get("/api/v2/runs/{run_id}/events")
    def run_events(run_id: str, limit: int = 500, _identity: Identity = Depends(need("viewer"))) -> list[dict]:
        path = _safe_run(run_id) / "events.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-min(max(limit, 1), 5000):]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                rows.append({"status": "INVALID_JSON", "line": line[:500]})
        return rows

    @app.get("/api/v2/runs/{run_id}/resources")
    def run_resources(run_id: str, limit: int = 1000, _identity: Identity = Depends(need("viewer"))) -> list[dict]:
        path = _safe_run(run_id) / "resource_samples.jsonl"
        if not path.exists():
            return []
        rows = []
        for line in path.read_text(encoding="utf-8", errors="replace").splitlines()[-min(max(limit, 1), 5000):]:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return rows

    @app.get("/api/v2/runs/{run_id}/artifacts")
    def run_artifacts(run_id: str, _identity: Identity = Depends(need("viewer"))) -> dict:
        item = _safe_run(run_id)
        path = item / "artifact_status.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @app.get("/api/v2/leaderboard")
    def leaderboard(_identity: Identity = Depends(need("viewer"))) -> list[dict]:
        path = root / "model_leaderboard.csv"
        if not path.exists():
            raise HTTPException(status_code=404, detail="leaderboard not found")
        import pandas as pd
        return pd.read_csv(path).replace({float("nan"): None}).to_dict(orient="records")

    @app.get("/metrics", include_in_schema=False)
    def metrics() -> Response:
        return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "output_dir": str(root), "auth_enabled": bool(token_map)}

    @app.get("/forecasts/latest")
    def latest_forecast(_identity: Identity = Depends(need("viewer"))) -> dict:
        path = root / "forecast.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="forecast not found")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/forecasts/latest/verify")
    def verify_latest(_identity: Identity = Depends(need("viewer"))) -> dict:
        path = root / "forecast.sealed.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="sealed forecast not found")
        secret = os.environ.get("LOTO_SEAL_SECRET")
        if not secret:
            raise HTTPException(status_code=503, detail="seal secret is not configured")
        return {"verified": verify_seal(json.loads(path.read_text(encoding="utf-8")), secret.encode())}

    @app.post("/forecasts/{forecast_id}/score")
    def score_forecast(forecast_id: str, request: ScoreRequest,
                       identity: Identity = Depends(need("operator"))) -> dict:
        path = root / "forecast.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="forecast not found")
        forecast = json.loads(path.read_text(encoding="utf-8"))
        if forecast.get("forecast_id") != forecast_id:
            raise HTTPException(status_code=404, detail="forecast id not found")
        score = score_combination(forecast["combination"]["numbers"], request.actual)
        registry.score_forecast(forecast_id, score)
        registry.audit(identity.username, "score", "forecast", forecast_id, "actual draw registered", score)
        return score

    @app.get("/evaluation/latest")
    def latest_evaluation(_identity: Identity = Depends(need("viewer"))) -> dict:
        path = root / "evaluation.json"
        if not path.exists():
            raise HTTPException(status_code=404, detail="evaluation not found")
        return json.loads(path.read_text(encoding="utf-8"))

    @app.get("/registry/{table}")
    def registry_rows(table: str, limit: int = 100,
                      _identity: Identity = Depends(need("viewer"))) -> list[dict]:
        try:
            return registry.list_rows(table, limit=min(max(limit, 1), 500))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/approvals/request")
    def request_approval(request: ApprovalRequest,
                         identity: Identity = Depends(need("operator"))) -> dict:
        registry.request_approval(request.object_type, request.object_id, request.action,
                                  identity.username, request.reason)
        registry.audit(identity.username, "request_approval", request.object_type,
                       request.object_id, request.reason, {"action": request.action})
        return {"status": "PENDING"}

    @app.post("/approvals/decide")
    def decide_approval(request: ApprovalDecision,
                        identity: Identity = Depends(need("approver"))) -> dict:
        try:
            registry.decide_approval(request.object_type, request.object_id, request.action,
                                     identity.username, request.approved)
        except (KeyError, PermissionError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        registry.audit(identity.username, "decide_approval", request.object_type,
                       request.object_id, "approval decision", {"action": request.action, "approved": request.approved})
        return {"status": "APPROVED" if request.approved else "REJECTED"}

    return app


app = create_app(os.environ.get("LOTO_OUTPUT_DIR", "."))
