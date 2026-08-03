from dataclasses import dataclass

from loto.probabilistic.resources import ProbabilisticResourcePolicy, ResourceAwareDispatcher


@dataclass
class Trial:
    trial_id: str
    resource_class: str
    backend: str = "pymc"


def test_dispatcher_does_not_exceed_resource_limits() -> None:
    policy = ProbabilisticResourcePolicy(
        outer_workers=8,
        max_heavy_cpu_jobs=2,
        max_gpu_jobs=1,
        gpu_priority=True,
        gpu_backends=("numpyro", "pyro"),
        native_device="cuda",
    )
    trials = [
        *[Trial(f"h{i}", "heavy_cpu") for i in range(5)],
        *[Trial(f"g{i}", "heavy_cpu", backend="numpyro") for i in range(3)],
        *[Trial(f"l{i}", "light_cpu", backend="builtin") for i in range(10)],
    ]
    dispatcher = ResourceAwareDispatcher(policy, trials)
    selected = []
    for _ in range(8):
        trial = dispatcher.pop_ready()
        assert trial is not None
        selected.append(trial)
    counts = dispatcher.running_by_resource()
    assert counts["heavy_cpu"] <= 2
    assert counts["gpu"] <= 1
    assert sum(counts.values()) == 8
    assert dispatcher.resource_for(trials[5]) == "gpu"
    for trial in selected:
        dispatcher.release(trial)
    assert dispatcher.running_count() == 0
    audit = dispatcher.audit()
    assert audit["peak_running_total"] == 8
    assert audit["peak_running_by_resource"]["gpu"] == 1


def test_gpu_is_selected_first() -> None:
    policy = ProbabilisticResourcePolicy(
        outer_workers=2,
        max_heavy_cpu_jobs=1,
        max_gpu_jobs=1,
        gpu_priority=True,
        gpu_backends=("pyro",),
        native_device="cuda",
    )
    trials = [
        Trial("cpu", "light_cpu", "builtin"),
        Trial("gpu", "heavy_cpu", "pyro"),
    ]
    dispatcher = ResourceAwareDispatcher(policy, trials)
    assert dispatcher.pop_ready().trial_id == "gpu"
