"""Focused tests for the explicit route and HITL approval subflow."""

from uuid import uuid4

import pytest

from agent.approval_workflow import resume_approval, start_approval
from agent.routing import node_for_route, route_name_for_intent


def test_legacy_intent_maps_to_explicit_route() -> None:
    assert route_name_for_intent("WORKFLOW") == "workflow"
    assert route_name_for_intent("KNOWLEDGE") == "rag"
    assert node_for_route({"intent": "TOOL", "route": "tool"}) == "plan_tool"


@pytest.mark.asyncio
async def test_approval_graph_can_pause_and_resume() -> None:
    approval_id = uuid4().hex
    await start_approval(approval_id)
    await resume_approval(approval_id, approved=True)
