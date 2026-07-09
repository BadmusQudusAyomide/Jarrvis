from unittest.mock import patch

from app.agents.planning import Plan, PlanOrchestrator, PlanStep, should_plan_task


def test_should_plan_task_for_multi_step_coding_request():
    message = "Fix the chat flow and then update the planner file and README."
    assert should_plan_task(message) is True


def test_should_not_plan_simple_chat():
    assert should_plan_task("hello there") is False


def test_plan_round_trip(tmp_path):
    plan = Plan(
        id="abc12345",
        task="Fix the app",
        goal="Fix the app",
        title="Fix app",
        steps=[
            PlanStep(id="step_1", description="Inspect the bug"),
            PlanStep(id="step_2", description="Patch the bug"),
        ],
    )

    saved = plan.save(storage_dir=tmp_path)
    loaded = Plan.load("abc12345", storage_dir=tmp_path)

    assert saved.exists()
    assert loaded is not None
    assert loaded.id == "abc12345"
    assert loaded.steps[0].description == "Inspect the bug"


def test_plan_progress_and_dependencies(tmp_path):
    plan = Plan(
        id="dep12345",
        task="Refactor auth",
        goal="Refactor auth",
        title="Refactor auth",
        steps=[
            PlanStep(id="step_1", description="Inspect auth", status="done"),
            PlanStep(id="step_2", description="Patch auth", dependencies=["step_1"]),
            PlanStep(id="step_3", description="Verify auth", dependencies=["step_2"]),
        ],
        status="running",
    )

    plan.save(storage_dir=tmp_path)
    loaded = Plan.load("dep12345", storage_dir=tmp_path)

    assert loaded is not None
    assert loaded.step_ready(loaded.get_step("step_2"))
    assert not loaded.step_ready(loaded.get_step("step_3"))
    progress = loaded.progress()
    assert progress["done_steps"] == 1
    assert progress["next_step_id"] == "step_2"


def test_orchestrator_marks_step_failed_when_model_paraphrases_a_tool_error():
    """A step whose underlying tool call fails but whose final answer
    explains the failure in prose (no literal "Error" prefix) must still be
    marked failed. The orchestrator used to string-sniff the model's final
    text for "error", which native tool-calling's chattier final answers
    routinely dodge — it now relies on Agent.last_tool_error instead."""
    plan_id = "test_paraphrased_failure"
    plan = Plan(
        id=plan_id,
        task="do two things",
        goal="do two things",
        title="Two step plan",
        steps=[
            PlanStep(id="step_1", description="a step that succeeds"),
            PlanStep(id="step_2", description="a step whose tool fails but gets paraphrased"),
        ],
    )
    plan.save()

    call_count = {"n": 0}

    class FakeAgent:
        def __init__(self, model=None):
            self.last_tool_error = None

        def run(self, step_message, history, system_prompt, session_id=None):
            call_count["n"] += 1
            if call_count["n"] == 1:
                self.last_tool_error = None
                return "Done: successfully completed the first step."
            self.last_tool_error = "Error: File not found"
            return "I wasn't able to complete this step because the required file could not be found."

    try:
        with patch("app.agents.planning.Agent", FakeAgent):
            PlanOrchestrator().run(task="do two things", plan_id=plan_id, model="fake-model")

        loaded = Plan.load(plan_id)
        assert loaded.get_step("step_1").status == "done"
        assert loaded.get_step("step_2").status == "failed"
    finally:
        from app.agents.planning import PLAN_STORAGE_DIR
        (PLAN_STORAGE_DIR / f"{plan_id}.json").unlink(missing_ok=True)
