# Execution Schedule

This schedule is gate-based rather than a calendar guarantee.

| Gate | Work | Exit |
|---|---|---|
| G0 | latest main/PR/settings/permission audit | no duplicate or ownership conflict |
| G1 | Experiment Plan Contract | focused/static gates pass |
| G2 | Issue Forms/Templates | schema and safe trigger tests pass |
| G3 | Project capability/config | exported field/view evidence |
| G4 | GitHub App contract | least-privilege fake API tests |
| G5 | Local Agent foundation | fake queue/executor recovery tests |
| G6 | Actions control workflows | actionable Actions run exists |
| G7 | Evidence Index | remote/fake verification and tamper tests |
| G8 | Paid API lane | budget and secret gates pass |
| G9 | Campaign release | tag/release identity tests |
| G10 | target-host E2E | duplicate/restart/outage/reconcile pass |

Parallel work is allowed only when path ownership and dependencies are independent. GPU execution is
serialized by default. CPU/data preparation may use up to eight workers.
