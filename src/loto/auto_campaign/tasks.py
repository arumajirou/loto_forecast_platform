from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass

from .contracts import CampaignConfig, CampaignStage
from .registry import AutoModelRecord


@dataclass(frozen=True)
class CampaignTask:
    stage: str
    model_name: str
    track: str
    position: int | None
    seed: int
    fold: int | None = None
    origin: int | None = None
    backend: str = "ray"
    config_index: int | None = None

    @property
    def key(self) -> str:
        parts = [self.stage, self.model_name, self.track, f"seed_{self.seed}"]
        if self.position is not None:
            parts.append(f"p{self.position}")
        if self.fold is not None:
            parts.append(f"fold_{self.fold:02d}")
        if self.origin is not None:
            parts.append(f"origin_{self.origin:06d}")
        if self.config_index is not None:
            parts.append(f"config_{self.config_index:06d}")
        parts.append(self.backend)
        return "/".join(parts)

    def as_dict(self) -> dict[str, object]:
        return asdict(self)


def _tracks(
    record: AutoModelRecord, config: CampaignConfig, *, smoke: bool
) -> Iterable[tuple[str, int | None]]:  # noqa: E501
    if record.is_hint:
        if "h_hint" in config.include_tracks:
            yield "h_hint", None
        return
    if record.requires_n_series:
        if "m_joint" in config.include_tracks:
            yield "m_joint", None
        return
    if "u_shared" in config.include_tracks:
        yield "u_shared", None
    if not smoke and "u_local" in config.include_tracks:
        for position in range(1, 6):
            yield "u_local", position


def build_tasks(
    records: list[AutoModelRecord],
    config: CampaignConfig,
    *,
    stage: CampaignStage,
    smoke: bool = False,
    backends: tuple[str, ...] | None = None,
) -> list[CampaignTask]:
    included = set(config.include_models or [record.name for record in records])
    included -= set(config.exclude_models)
    backends = backends or (config.search.backend,)
    seeds = (
        (config.model_seeds[0],)
        if stage in {CampaignStage.SMOKE, CampaignStage.HPO, CampaignStage.COVERAGE}
        else tuple(config.model_seeds)
    )  # noqa: E501
    tasks: list[CampaignTask] = []
    for record in records:
        if record.name not in included:
            continue
        for track, position in _tracks(record, config, smoke=smoke):
            for backend in backends:
                if record.is_hint and backend == "optuna":
                    # NeuralForecast 3.2.0 explicitly rejects Optuna for AutoHINT.
                    continue
                for seed in seeds:
                    tasks.append(
                        CampaignTask(
                            stage=stage.value,
                            model_name=record.name,
                            track=track,
                            position=position,
                            seed=seed,
                            backend=backend,
                        )
                    )
    tasks.sort(key=lambda task: task.key)
    if config.max_tasks is not None:
        tasks = tasks[: config.max_tasks]
    return tasks
