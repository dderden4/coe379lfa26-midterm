"""Milestone 3: implement three selected validation responsibilities."""

from __future__ import annotations
from xml.parsers.expat import errors

from .agent_models import ToolCallDecision
from .models import AgentResponse, LabRequest, TraceEvent
from .policy_context import ReservationContext, build_reservation_context


def validate_request_binding(
    decision: ToolCallDecision,
    *,
    request: LabRequest,
) -> list[str]:
    """Prevent identity and resolved-field substitution."""
    errors = []
    arguments = decision.arguments

    if "user_id" in arguments:
        if arguments["user_id"] != request.authenticated_user_id:
            errors.append("user_id_must_match_authenticated_user")

    for field in ("project_id", "resource_id", "start", "end"):
        if field not in arguments:
            continue

        requested_value = getattr(request, field)
        proposed_value = arguments[field]

        if requested_value is None:
            errors.append(f"{field}_unresolved_in_request")
        elif proposed_value != requested_value:
            errors.append(f"{field}_does_not_match_request")

    return errors


def validate_reservation_preconditions(context: ReservationContext) -> list[str]:
    """Return errors for failed reservation preconditions."""
    checks = {
        "arguments_complete": "reservation_arguments_incomplete",
        "policy_retrieved": "required_policy_not_retrieved",
        "authorizations_checked": "user_authorizations_not_checked",
        "resource_status_checked": "resource_status_not_checked",
        "project_authorized": "project_not_authorized",
        "qualification_current": "required_qualification_missing",
        "resource_available": "resource_not_available",
        "calibration_current": "calibration_not_current",
        "maintenance_clear": "maintenance_not_clear",
        "after_hours_approval_satisfied": "after_hours_approval_missing",
    }

    errors = []

    for field, error_code in checks.items():
        if not getattr(context, field):
            errors.append(error_code)

    return errors


def validate_proposed_tool_call(
    decision: ToolCallDecision,
    *,
    request: LabRequest,
    trace: list[TraceEvent],
) -> list[str]:
    """Supplied wrapper. Do not modify this function."""
    errors = validate_request_binding(decision, request=request)
    if decision.tool == "reserve_resource":
        context = build_reservation_context(decision, trace)
        errors.extend(validate_reservation_preconditions(context))
    return errors


def retrieved_passage_ids(trace: list[TraceEvent]) -> set[str]:
    """Supplied helper. Do not modify this function."""
    identifiers: set[str] = set()
    for event in trace:
        if event.observation.tool != "search_lab_documents" or not event.observation.ok:
            continue
        identifiers.update(
            passage["passage_id"]
            for passage in event.observation.data.get("passages", [])
        )
    return identifiers


def validate_final_response(
    response: AgentResponse, trace: list[TraceEvent]
) -> list[str]:
    """Validate citations, completed actions, and final status."""
    errors = []

    retrieved_ids = retrieved_passage_ids(trace)

    for citation in response.citations:
        if citation not in retrieved_ids:
            errors.append("citations_not_retrieved")

    successful_actions = {
        event.observation.tool
        for event in trace
        if event.mutating and event.observation.ok
    }

    for action in response.completed_actions:
        if action not in successful_actions:
            errors.append("completed_action_not_in_successful_trace")

    if response.status == "completed":
        if not successful_actions:
            errors.append("completed_without_successful_mutation")
        if not response.completed_actions:
            errors.append("completed_without_claimed_action")
    else:
        if response.completed_actions:
            errors.append("non_completed_with_claimed_actions")
        if successful_actions:
            errors.append("successful_mutation_not_reported")
    return errors
