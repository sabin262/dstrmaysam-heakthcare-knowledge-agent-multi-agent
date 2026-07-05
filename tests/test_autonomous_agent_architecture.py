from test_agent_contract import FakeLLM, fake_ai_message, make_agent


def _tool_call(name: str, query: str):
    return fake_ai_message(tool_calls=[{"name": name, "args": {"query": query}, "id": "call-1"}])


def _flow_kinds(result):
    return [step.get("kind") for step in result.metadata["performance"].get("agent_flow", [])]


def test_supervisor_selects_policy_agent_and_specialist_selects_policy_tool():
    fake_llm = FakeLLM(
        [
            _tool_call("policy_agent", "research data handling"),
            fake_ai_message("Research data handling is covered by policy evidence."),
        ]
    )
    agent = make_agent(fake_llm)

    result = agent.answer("user", "how do I handle research data", session_id="session")

    bound_tool_names = [tool.__name__ for tool in fake_llm.bound_tools]
    assert "policy_agent" in bound_tool_names
    assert "policy_search" not in bound_tool_names
    assert result.tools_used == ["policy_search"]
    assert result.metadata["performance"]["agent_flow"][0]["selected_agent"] == "PolicyAgent"
    assert "specialist_tool_decision" in _flow_kinds(result)
    assert result.metadata["performance"]["specialist_reports"][0]["agent"] == "PolicyAgent"


def test_catalog_agent_handles_inventory_without_policy_tool_selection():
    fake_llm = FakeLLM([_tool_call("catalog_agent", "list guideline documents")])
    agent = make_agent(fake_llm)

    result = agent.answer("user", "list guideline documents", session_id="session")

    assert result.tools_used == ["catalogue_search"]
    assert result.metadata["performance"]["agent_flow"][0]["selected_agent"] == "CatalogAgent"
    assert all(tool != "policy_search" for tool in result.tools_used)
    assert result.metadata["performance"]["specialist_reports"][0]["tools_called"] == ["catalogue_search"]


def test_safety_agent_review_is_represented_as_specialist_report():
    fake_llm = FakeLLM([_tool_call("safety_agent", "urgent escalation for patient safety")])
    agent = make_agent(fake_llm)

    result = agent.answer("user", "urgent escalation for patient safety", session_id="session")

    assert "safety_guard" in result.tools_used
    assert result.metadata["performance"]["agent_flow"][0]["selected_agent"] == "SafetyAgent"
    assert result.metadata["performance"]["specialist_reports"][0]["agent"] == "SafetyAgent"
