"""Workflow A/Fを実行する依存性注入型Dispatcher。"""

from __future__ import annotations

import inspect
import logging
import uuid
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class WorkflowResult:
    """Workflow実行結果。"""

    def __init__(
        self,
        status: str,
        planner_called: bool = False,
        planner_plan: dict[str, Any] | None = None,
        executor_result: dict[str, Any] | None = None,
        validator_result: dict[str, Any] | None = None,
        retry_result: dict[str, Any] | None = None,
        error: str | None = None,
        handover_written: bool = False,
        validator_fresh: bool = False,
    ) -> None:
        self.status = status
        self.planner_called = planner_called
        self.planner_plan = planner_plan
        self.executor_result = executor_result
        self.validator_result = validator_result
        self.retry_result = retry_result
        self.error = error
        self.handover_written = handover_written
        self.validator_fresh = validator_fresh


class WorkflowDispatcher:
    """Workflow A/F Dispatcher。

    各コンポーネントはコンストラクターまたは生成後の属性代入で注入できます。
    """

    def __init__(
        self,
        planner: Any = None,
        executor: Any = None,
        validator: Any = None,
        retry_manager: Any = None,
        handover: Any = None,
        memory: Any = None,
        workflow: str = "F",
        output_dir: str | Path | None = None,
    ) -> None:
        self.planner = planner
        self.executor = executor
        self.validator = validator
        self.retry_manager = retry_manager
        self.handover = handover
        self.memory = memory
        self.workflow = workflow
        self.output_dir = Path(output_dir) if output_dir is not None else Path(".")

        self._logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

    def run(
        self,
        workflow: str,
        *,
        task: str,
        ctx: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """指定されたWorkflowを実行する正式な公開API。"""

        normalized_workflow = str(workflow).strip().upper()
        normalized_ctx = dict(ctx or {})

        if normalized_workflow == "A":
            return self._run_workflow_a(
                task=task,
                ctx=normalized_ctx,
            )

        if normalized_workflow == "F":
            return self._run_workflow_f(
                task=task,
                ctx=normalized_ctx,
            )

        raise ValueError(f"Unknown workflow: {workflow!r}. Expected 'A' or 'F'.")

    def dispatch(
        self,
        task: str,
        plan: dict[str, Any] | None = None,
    ) -> WorkflowResult:
        """Execute through the compatibility dispatch API.

        ``run()`` preserves the original Workflow A contract.  The
        compatibility ``dispatch()`` API hides the internal validation input
        from ``planner_plan`` and writes a handover when a handover component
        is configured.
        """
        result = self.run(
            self.workflow,
            task=task,
            ctx=dict(plan or {}),
        )

        if self.workflow != "A":
            return result

        result.planner_plan = None

        if self.handover is None:
            result.handover_written = False
            return result

        self.output_dir.mkdir(
            parents=True,
            exist_ok=True,
        )

        handover_path = self.output_dir / "workflow_a_handover.json"

        handover_data: dict[str, Any] = {
            "workflow": "A",
            "task": task,
            "planner_plan": None,
            "executor_result": result.executor_result,
            "validation": result.validator_result,
            "retry_decision": None,
        }

        self.handover.write(
            str(handover_path),
            handover_data,
        )

        result.handover_written = True
        return result

    def _run_workflow_a(
        self,
        *,
        task: str,
        ctx: dict[str, Any],
    ) -> WorkflowResult:
        """Workflow A。

        Planner、RetryManager、Handover、Memoryは使用しない。
        ExecutorとValidatorは同一sessionを使用する。
        """

        self._require_component("executor")
        self._require_component("validator")

        session_id = str(ctx.get("session_id") or uuid.uuid4())

        execution_plan: dict[str, Any] = dict(ctx)
        execution_plan.setdefault("task", task)
        execution_plan["session_id"] = session_id

        executor_result = self.executor.run_plan(execution_plan)

        if isinstance(executor_result, dict):
            executor_result.setdefault("session_id", session_id)
            validation_input = executor_result
        else:
            validation_input = {
                "task": task,
                "session_id": session_id,
                "result": executor_result,
            }

        validation = self.validator.validate(validation_input)

        return WorkflowResult(
            status="success",
            planner_called=False,
            planner_plan=self._as_dict(validation_input),
            executor_result=self._as_dict(executor_result),
            validator_result=self._as_dict(validation),
            retry_result=None,
            handover_written=False,
            validator_fresh=False,
        )

    def _run_workflow_f(
        self,
        *,
        task: str,
        ctx: dict[str, Any],
    ) -> WorkflowResult:
        """Workflow F。

        Plannerで計画を生成し、Executor、別sessionのValidator、
        RetryManager、Handover、Memoryを実行する。
        """

        self._require_component("planner")
        self._require_component("executor")
        self._require_component("validator")
        self._require_component("retry_manager")

        planner_plan = self._call_planner(
            task=task,
            ctx=ctx,
        )

        if not isinstance(planner_plan, dict):
            planner_plan = {
                "task": task,
                "plan": planner_plan,
            }

        executor_session_id = str(
            planner_plan.get("session_id") or ctx.get("session_id") or uuid.uuid4()
        )
        planner_plan.setdefault(
            "session_id",
            executor_session_id,
        )

        executor_result = self.executor.run_plan(planner_plan)

        validation = self.validator.validate(planner_plan)

        retry_decision = self.retry_manager.classify(
            validation,
            planner_plan,
        )

        final_plan = planner_plan
        final_executor_result = executor_result
        final_validation = validation

        should_retry = isinstance(retry_decision, dict) and bool(retry_decision.get("retry"))

        if should_retry:
            retry_ctx = dict(ctx)
            retry_ctx["previous_plan"] = planner_plan
            retry_ctx["previous_validation"] = validation
            retry_ctx["retry_decision"] = retry_decision

            replanned = self._call_planner(
                task=task,
                ctx=retry_ctx,
            )

            if not isinstance(replanned, dict):
                replanned = {
                    "task": task,
                    "plan": replanned,
                }

            retry_executor_session = str(replanned.get("session_id") or uuid.uuid4())
            replanned.setdefault(
                "session_id",
                retry_executor_session,
            )

            final_plan = replanned
            final_executor_result = self.executor.run_plan(final_plan)

            final_validation = self.validator.validate(final_plan)

        handover_written = False

        handover_data: dict[str, Any] = {
            "workflow": "F",
            "task": task,
            "planner_plan": final_plan,
            "executor_result": final_executor_result,
            "validation": final_validation,
            "retry_decision": retry_decision,
            "memory_status": (
                "recorded" if self.memory is not None else "disabled_not_implemented"
            ),
        }

        if self.handover is not None:
            self.output_dir.mkdir(
                parents=True,
                exist_ok=True,
            )

            handover_path = self.output_dir / "workflow_f_handover.json"

            self.handover.write(
                str(handover_path),
                handover_data,
            )
            handover_written = True

        if self.memory is not None:
            self.memory.write(
                f"workflow_f:{task}",
                handover_data,
            )

        return WorkflowResult(
            status="success",
            planner_called=True,
            planner_plan=final_plan,
            executor_result=self._as_dict(final_executor_result),
            validator_result=self._as_dict(final_validation),
            retry_result=self._as_dict(retry_decision),
            handover_written=handover_written,
            validator_fresh=True,
        )

    def _call_planner(
        self,
        *,
        task: str,
        ctx: dict[str, Any],
    ) -> Any:
        """Plannerの1引数・2引数形式の両方へ対応する。"""

        plan_method = self.planner.plan
        signature = inspect.signature(plan_method)

        positional_parameters = [
            parameter
            for parameter in signature.parameters.values()
            if parameter.kind
            in {
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            }
        ]

        if len(positional_parameters) >= 2:
            return plan_method(task, ctx)

        return plan_method(task)

    def _require_component(
        self,
        name: str,
    ) -> None:
        component = getattr(self, name, None)

        if component is None:
            raise RuntimeError(f"Workflow component is not configured: {name}")

    @staticmethod
    def _new_distinct_session(
        previous_session: str,
    ) -> str:
        while True:
            candidate = str(uuid.uuid4())

            if candidate != previous_session:
                return candidate

    @staticmethod
    def _as_dict(
        value: Any,
    ) -> dict[str, Any] | None:
        if value is None:
            return None

        if isinstance(value, dict):
            return value

        return {
            "value": value,
        }
