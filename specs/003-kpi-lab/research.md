# Research Notes: KPI Lab

## Reference arm

The reference arm uses geometry-derived constructions and set-cover optimization. Greedy
maximum coverage is retained as the dependency-free baseline. CP-SAT is an optional
certificate path, not an automatic replacement.

## Solver dependency policy

An absent optional solver must produce a typed `SolverUnavailable` result. Silent fallback
would make experiment identity depend on the environment and invalidate comparisons. The
contract test blocks OR-Tools imports even on machines where it may be installed and proves
that the function fails closed.

## Statistical boundary

The lab compares arms at a fixed ticket budget. Sequential evidence uses an e-process;
negative controls and sealed-window guards must pass before a model-value conclusion is
permitted. Coverage is a geometric KPI and is not a lottery prize condition.

## Remaining research

- Compare greedy, LP randomized rounding, CP-SAT, and a separately declared MILP backend.
- Import and license-check published covering-design tables.
- Measure solver quality and runtime by game, pool size, and target sample size.
