from atlas_agent.agent_models import ToolCallDecision
from atlas_agent.models import LabRequest
from atlas_agent.validation import validate_request_binding


def test_student_rejects_user_identity_substitution(environment):
    """Reject a reservation attempted under another user's identity."""

    from atlas_agent.agent import run_agent
    from atlas_agent.llm import ScriptedLLM

    request = LabRequest(
        authenticated_user_id="alice",
        text="Reserve tensile-01 for polymer-study.",
        project_id="polymer-study",
        resource_id="tensile-01",
        start="2026-10-15T10:00:00",
        end="2026-10-15T11:00:00",
    )

    decisions = [
        {
            "kind": "tool_call",
            "tool": "reserve_resource",
            "arguments": {
                "user_id": "bob",
                "project_id": "polymer-study",
                "resource_id": "tensile-01",
                "start": "2026-10-15T10:00:00",
                "end": "2026-10-15T11:00:00",
            },
            "reasoning_summary": "Attempt reservation under a different identity.",
        },
        {
            "kind": "final",
            "response": {
                "status": "blocked",
                "message": "Reservation denied because the user identity does not match.",
                "citations": [],
                "completed_actions": [],
            },
        },
    ]

    run = run_agent(
        request,
        llm=ScriptedLLM(decisions),
        environment=environment,
    )

    assert run.response.status == "blocked"
    assert run.termination_reason == "model_finished"
    assert len(run.trace) == 1
    assert run.trace[0].observation.error_code == "action_gate_denied"
    assert "user_id_must_match_authenticated_user" in run.trace[0].observation.message
    assert len(environment.simulator.state["reservations"]) == 1


def test_student_rejects_false_completion_after_denied_reservation(environment):
    """Reject a completed response when the reservation was denied."""

    from atlas_agent.agent import run_agent
    from atlas_agent.llm import ScriptedLLM

    request = LabRequest(
        authenticated_user_id="alice",
        text="Reserve tensile-01 for polymer-study from 10:00 to 11:00.",
        project_id="polymer-study",
        resource_id="tensile-01",
        start="2026-10-15T10:00:00",
        end="2026-10-15T11:00:00",
    )

    decisions = [
        {
            "kind": "tool_call",
            "tool": "reserve_resource",
            "arguments": {
                "user_id": "alice",
                "project_id": "polymer-study",
                "resource_id": "tensile-01",
                "start": "2026-10-15T10:00:00",
                "end": "2026-10-15T11:00:00",
            },
            "reasoning_summary": "Attempt reservation without checking required evidence.",
        },
        {
            "kind": "final",
            "response": {
                "status": "completed",
                "message": "Your reservation was successfully created.",
                "citations": [],
                "completed_actions": ["reserve_resource"],
            },
        },
    ]

    run = run_agent(
        request,
        llm=ScriptedLLM(decisions),
        environment=environment,
    )

    assert run.response.status == "failed"
    assert run.termination_reason == "invalid_final_response"
    assert len(run.trace) == 1
    assert run.trace[0].observation.error_code == "action_gate_denied"
    assert "completed_action_not_in_successful_trace" in run.response.message
    assert len(environment.simulator.state["reservations"]) == 1


def test_student_rejects_fabricated_citation(environment):
    """Reject a final response citing a document that was never retrieved."""

    from atlas_agent.agent import run_agent
    from atlas_agent.llm import ScriptedLLM

    request = LabRequest(
        authenticated_user_id="alice",
        text="What are the laboratory safety requirements?",
    )

    decisions = [
        {
            "kind": "final",
            "response": {
                "status": "blocked",
                "message": "The laboratory requires safety training.",
                "citations": ["FAKE-999#safety-policy"],
                "completed_actions": [],
            },
        },
    ]

    run = run_agent(
        request,
        llm=ScriptedLLM(decisions),
        environment=environment,
    )

    assert run.response.status == "failed"
    assert run.termination_reason == "invalid_final_response"
    assert "citations_not_retrieved" in run.response.message
    assert len(run.trace) == 0
