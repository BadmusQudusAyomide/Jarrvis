from __future__ import annotations

import json
import logging
import os
import re
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import requests

from app.agents.core_agent import Agent
from app.config import CODING_MODEL, DEFAULT_MODEL, get_system_prompt
from app.llm.router import route_model

logger = logging.getLogger(__name__)

GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_API_KEY_CODING = os.getenv("GROQ_API_KEY_CODING", "").strip() or GROQ_API_KEY
GROQ_MODEL_CODING = os.getenv("GROQ_MODEL_CODING", "qwen-qwq-32b").strip()
GROQ_BASE_URL = os.getenv("GROQ_BASE_URL", "https://api.groq.com/openai/v1").rstrip("/")
GROQ_TIMEOUT = int(os.getenv("GROQ_TIMEOUT", "60"))

PLAN_STORAGE_DIR = Path(os.getenv("PLAN_STORAGE_DIR", "data/plans"))


def should_plan_task(message: str) -> bool:
    """Heuristic gate for multi-step work.

    We only plan when the request looks like actual work that benefits from
    decomposition. This keeps simple chat and one-off tool calls fast.
    """
    text = (message or "").strip().lower()
    if not text:
        return False

    coding_score = sum(
        1 for pattern in (
            "fix", "debug", "refactor", "implement", "build", "create", "update",
            "rewrite", "migrate", "feature", "bug", "error", "issue", "workflow",
            "api", "class", "function", "file", "module", "project", "code"
        )
        if pattern in text
    )

    multi_step_markers = [
        " and then ",
        " then ",
        " after that ",
        " first ",
        " next ",
        " finally ",
        "also",
        "\n- ",
        "\n1.",
        "\n2.",
    ]

    file_mentions = len(re.findall(r"\b[\w\-./]+\.(?:py|js|ts|tsx|jsx|json|md|html|css|yaml|yml)\b", text))
    sentence_count = len([part for part in re.split(r"[.!?]+", text) if part.strip()])
    if coding_score >= 2:
        return True

    if coding_score >= 1 and (file_mentions >= 1 or sentence_count >= 2):
        return True

    if coding_score >= 1 and any(marker.strip() in text for marker in multi_step_markers):
        return True

    if coding_score >= 1 and len(text) >= 220:
        return True

    return False


@dataclass
class PlanStep:
    id: str
    description: str
    status: str = "pending"
    result: Optional[str] = None
    retry_count: int = 0
    dependencies: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "PlanStep":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
            description=str(data.get("description") or "").strip(),
            status=str(data.get("status") or "pending"),
            result=data.get("result"),
            retry_count=int(data.get("retry_count") or 0),
            dependencies=list(data.get("dependencies") or []),
        )


@dataclass
class Plan:
    id: str
    task: str
    goal: str
    title: str
    steps: list[PlanStep]
    status: str = "pending"
    summary: Optional[str] = None
    current_step_id: Optional[str] = None
    last_error: Optional[str] = None
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def next_pending_step(self) -> Optional[PlanStep]:
        for step in self.steps:
            if step.status == "pending":
                return step
        return None

    def all_dependencies_satisfied(self, step: PlanStep) -> bool:
        if not step.dependencies:
            return True
        done_ids = {item.id for item in self.steps if item.status == "done"}
        return all(dep in done_ids for dep in step.dependencies)

    def step_ready(self, step: PlanStep) -> bool:
        return step.status in {"pending", "failed"} and self.all_dependencies_satisfied(step)

    def mark_in_progress(self, step_id: str) -> None:
        step = self.get_step(step_id)
        if step:
            step.status = "in_progress"
            self.current_step_id = step_id
            self.last_error = None

    def mark_done(self, step_id: str, result: str) -> None:
        step = self.get_step(step_id)
        if step:
            step.status = "done"
            step.result = result
            self.current_step_id = step_id

    def mark_failed(self, step_id: str, error: str) -> None:
        step = self.get_step(step_id)
        if step:
            step.status = "failed"
            step.result = error
            self.current_step_id = step_id
            self.last_error = error

    def mark_blocked(self, step_id: str, reason: str) -> None:
        step = self.get_step(step_id)
        if step:
            step.status = "blocked"
            step.result = reason
            self.current_step_id = step_id
            self.last_error = reason

    def get_step(self, step_id: str) -> Optional[PlanStep]:
        for step in self.steps:
            if step.id == step_id:
                return step
        return None

    def progress(self) -> dict[str, Any]:
        total = len(self.steps)
        done = sum(1 for step in self.steps if step.status == "done")
        failed = sum(1 for step in self.steps if step.status == "failed")
        blocked = sum(1 for step in self.steps if step.status == "blocked")
        in_progress = next((step.id for step in self.steps if step.status == "in_progress"), None)
        next_step = next((step.id for step in self.steps if self.step_ready(step)), None)
        return {
            "total_steps": total,
            "done_steps": done,
            "failed_steps": failed,
            "blocked_steps": blocked,
            "percent_complete": round((done / total) * 100, 1) if total else 0,
            "current_step_id": self.current_step_id or in_progress,
            "next_step_id": next_step,
        }

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "goal": self.goal,
            "title": self.title,
            "steps": [step.to_dict() for step in self.steps],
            "status": self.status,
            "summary": self.summary,
            "current_step_id": self.current_step_id,
            "last_error": self.last_error,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Plan":
        return cls(
            id=str(data.get("id") or uuid.uuid4().hex[:8]),
            task=str(data.get("task") or "").strip(),
            goal=str(data.get("goal") or "").strip(),
            title=str(data.get("title") or "Planned task").strip(),
            steps=[PlanStep.from_dict(item) for item in data.get("steps", []) if isinstance(item, dict)],
            status=str(data.get("status") or "pending"),
            summary=data.get("summary"),
            current_step_id=data.get("current_step_id"),
            last_error=data.get("last_error"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )

    def save(self, storage_dir: Path = PLAN_STORAGE_DIR) -> Path:
        storage_dir.mkdir(parents=True, exist_ok=True)
        now = datetime.utcnow().isoformat()
        if not self.created_at:
            self.created_at = now
        self.updated_at = now
        path = storage_dir / f"{self.id}.json"
        path.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @classmethod
    def load(cls, plan_id: str, storage_dir: Path = PLAN_STORAGE_DIR) -> Optional["Plan"]:
        path = storage_dir / f"{plan_id}.json"
        if not path.exists():
            return None
        try:
            return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
        except Exception as exc:
            logger.warning(f"Failed to load plan {plan_id}: {exc}")
            return None


def _extract_json_candidate(text: str) -> Optional[str]:
    if not text:
        return None

    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)

    if "</think>" in stripped:
        post_think = stripped.split("</think>", 1)[1].strip()
        if post_think:
            stripped = post_think

    if stripped.startswith("{") and stripped.endswith("}"):
        return stripped

    start = None
    depth = 0
    for idx, char in enumerate(stripped):
        if char == "{":
            if depth == 0:
                start = idx
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0 and start is not None:
                return stripped[start : idx + 1]

    return None


def _normalize_plan_payload(payload: dict[str, Any], task: str) -> Plan:
    raw_steps = payload.get("steps", [])
    steps: list[PlanStep] = []

    if isinstance(raw_steps, list):
        for index, item in enumerate(raw_steps, start=1):
            if isinstance(item, str):
                description = item.strip()
                if description:
                    steps.append(PlanStep(id=f"step_{index}", description=description))
            elif isinstance(item, dict):
                description = str(item.get("description") or item.get("task") or "").strip()
                if not description:
                    continue
                step_id = str(item.get("id") or f"step_{index}")
                deps = item.get("dependencies") or []
                if not isinstance(deps, list):
                    deps = []
                steps.append(
                    PlanStep(
                        id=step_id,
                        description=description,
                        dependencies=[str(dep) for dep in deps if str(dep).strip()],
                    )
                )

    if not steps:
        steps = [PlanStep(id="step_1", description=task.strip() or "Complete the original request")]

    title = str(payload.get("title") or "Planned task").strip()
    goal = str(payload.get("goal") or task).strip()

    return Plan(
        id=uuid.uuid4().hex[:8],
        task=task.strip(),
        goal=goal,
        title=title,
        steps=steps,
    )


def _chat_with_groq(messages: list[dict[str, str]], api_key: str, model: str) -> str:
    if not api_key:
        return "Error: GROQ_API_KEY is not set"

    url = f"{GROQ_BASE_URL}/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": model,
        "messages": messages,
        "stream": False,
        "temperature": 0.2,
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=GROQ_TIMEOUT)
        if resp.status_code != 200:
            return f"Error talking to Groq: HTTP {resp.status_code}"
        return resp.json().get("choices", [{}])[0].get("message", {}).get("content", "")
    except Exception as exc:
        return f"Error talking to Groq: {exc}"


class Planner:
    """Create a compact execution plan from a user request."""

    def __init__(self, model: str = GROQ_MODEL_CODING):
        self.model = model

    def create_plan(self, task: str, history: Optional[list[dict[str, str]]] = None, system_prompt: Optional[str] = None) -> Plan:
        history = history or []
        prompt = system_prompt or get_system_prompt(profile="coding")

        planner_prompt = (
            "You are a planning assistant for a coding agent.\n"
            "Break the task into a short, actionable JSON plan.\n"
            "Return ONLY valid JSON with this shape:\n"
            "{"
            '"title":"short title",'
            '"goal":"one-sentence goal",'
            '"steps":[{"id":"step_1","description":"...","dependencies":[]}]'
            "}\n"
            "Rules:\n"
            "- Keep it to 3 to 7 steps.\n"
            "- Each step must be concrete and independently executable.\n"
            "- Use concise step descriptions.\n"
            "- Do not include markdown, commentary, or extra text.\n"
        )

        messages = [{"role": "system", "content": prompt + "\n\n" + planner_prompt}]
        if history:
            messages.extend(history[-8:])
        messages.append({"role": "user", "content": task})

        raw = _chat_with_groq(messages, api_key=GROQ_API_KEY_CODING, model=self.model)
        candidate = _extract_json_candidate(raw)
        if not candidate:
            logger.warning("Planner returned non-JSON output, falling back to single-step plan.")
            return Plan(
                id=uuid.uuid4().hex[:8],
                task=task.strip(),
                goal=task.strip(),
                title="Fallback plan",
                steps=[PlanStep(id="step_1", description=task.strip() or "Complete the original request")],
            )

        try:
            payload = json.loads(candidate)
            if not isinstance(payload, dict):
                raise ValueError("Plan payload was not an object")
        except Exception as exc:
            logger.warning(f"Could not parse planner JSON: {exc}")
            return Plan(
                id=uuid.uuid4().hex[:8],
                task=task.strip(),
                goal=task.strip(),
                title="Fallback plan",
                steps=[PlanStep(id="step_1", description=task.strip() or "Complete the original request")],
            )

        return _normalize_plan_payload(payload, task)


class PlanOrchestrator:
    """Plan first, then execute each step using the existing Agent loop."""

    def __init__(self, planner: Optional[Planner] = None, max_step_retries: int = 2):
        self.planner = planner or Planner()
        self.max_step_retries = max_step_retries

    def _build_step_message(self, task: str, plan: Plan, step: PlanStep, completed_results: list[str]) -> str:
        context = []
        context.append(f"Original task: {task}")
        context.append(f"Plan title: {plan.title}")
        context.append(f"Current step: {step.description}")
        if step.dependencies:
            context.append(f"Dependencies: {', '.join(step.dependencies)}")
        if completed_results:
            context.append("Completed step results so far:")
            for result in completed_results[-3:]:
                context.append(f"- {result}")
        context.append("Execute only this step and return the result clearly.")
        return "\n".join(context)

    def _execute_step(self, step_message: str, history: list[dict[str, str]], system_prompt: str, model: str) -> tuple[str, bool]:
        """Run one plan step. Returns (result_text, succeeded).

        succeeded comes from the agent's own record of whether its last tool
        call failed (Agent.last_tool_error), not from guessing based on the
        model's final wording — the model routinely explains a failure in
        its own prose ("I wasn't able to find that file...") without ever
        literally saying "Error", so string-sniffing the result text misses
        real failures.
        """
        agent = Agent(model=model)
        result = agent.run(step_message, history, system_prompt)
        return result, agent.last_tool_error is None

    def _load_or_create_plan(self, task: str, plan_id: str, history: list[dict[str, str]], system_prompt: str) -> Plan:
        existing = Plan.load(plan_id)
        if existing:
            existing.task = task.strip() or existing.task
            if not existing.goal:
                existing.goal = task.strip()
            return existing

        plan = self.planner.create_plan(task, history=history, system_prompt=system_prompt)
        plan.id = plan_id
        return plan

    def run(
        self,
        task: str,
        history: Optional[list[dict[str, str]]] = None,
        system_prompt: Optional[str] = None,
        model: Optional[str] = None,
        plan_id: Optional[str] = None,
    ) -> str:
        history = history or []
        system_prompt = system_prompt or get_system_prompt(profile="coding")

        plan_id = plan_id or uuid.uuid4().hex[:8]
        plan = self._load_or_create_plan(task, plan_id, history, system_prompt)
        plan.status = "running"
        plan.save()

        executor_model = model or route_model(task, DEFAULT_MODEL, CODING_MODEL)
        completed_results: list[str] = []

        for step in plan.steps:
            if step.status == "done":
                completed_results.append(f"{step.id}: {step.result}" if step.result else f"{step.id}: done")
                continue

            if not plan.step_ready(step):
                plan.mark_blocked(step.id, "Waiting on dependencies")
                plan.save()
                continue

            remaining_attempts = (self.max_step_retries + 1) - step.retry_count
            if remaining_attempts <= 0:
                plan.mark_blocked(step.id, "Retry limit reached")
                plan.save()
                continue

            plan.mark_in_progress(step.id)
            step_message = self._build_step_message(task, plan, step, completed_results)
            last_result = ""
            last_succeeded = False

            for attempt in range(remaining_attempts):
                last_result, last_succeeded = self._execute_step(step_message, history, system_prompt, executor_model)
                if not last_succeeded:
                    step.retry_count += 1
                    if attempt < remaining_attempts - 1:
                        step.result = last_result
                        plan.save()
                        continue
                break

            if not last_succeeded:
                plan.mark_failed(step.id, last_result)
                completed_results.append(f"{step.id}: failed with {last_result}")
                plan.status = "partial"
                plan.summary = "Plan completed with some failures."
                plan.save()
                continue

            plan.mark_done(step.id, last_result)
            completed_results.append(f"{step.id}: {last_result}")
            plan.save()

        done_steps = sum(1 for step in plan.steps if step.status == "done")
        failed_steps = sum(1 for step in plan.steps if step.status == "failed")
        blocked_steps = sum(1 for step in plan.steps if step.status == "blocked")
        plan.status = "completed" if failed_steps == 0 and blocked_steps == 0 else "partial"
        plan.summary = f"Completed {done_steps}/{len(plan.steps)} steps."
        plan.save()

        summary_lines = [
            f"I broke this into {len(plan.steps)} steps and completed {done_steps}.",
        ]
        if failed_steps:
            summary_lines.append(f"{failed_steps} step(s) failed and were left for follow-up.")
        if blocked_steps:
            summary_lines.append(f"{blocked_steps} step(s) are waiting on dependencies.")
        if completed_results:
            summary_lines.append("Results:")
            summary_lines.extend(f"- {line}" for line in completed_results)
        return "\n".join(summary_lines)


def run_planned_task(
    task: str,
    history: Optional[list[dict[str, str]]] = None,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    session_id: str = "local",
    task_id: Optional[str] = None,
) -> str:
    """Background-task friendly entry point for the planning pipeline."""
    orchestrator = PlanOrchestrator()
    return orchestrator.run(task=task, history=history, system_prompt=system_prompt, model=model, plan_id=task_id)
