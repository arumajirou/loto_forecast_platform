"""Workflow定義の型。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class WorkflowConfig:
    """Workflow実行オプションの定義。

    A: 軽量直接実行
    F: Planner→Executor→Validator(別session)→Retry→Handover
    """

    planning: bool = False
    executor: str = "direct"
    validator: str = "same_session"
    retry: str = "basic"
    memory: bool = False
    handover: bool = False

    def is_fresh_validator(self) -> bool:
        """別sessionのValidator利用の有無。"""
        return self.validator == "fresh_session"

    def requires_planner(self) -> bool:
        """Planner呼出が必要か。"""
        return self.planning

    def requires_handover(self) -> bool:
        """Handover出力が必要か。"""
        return self.handover

    def requires_retry(self) -> bool:
        """RetryManager呼出が必要か。"""
        return self.retry != "none"
