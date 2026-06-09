"""Gateway Command resume 行为测试。"""

from __future__ import annotations

from typing import Any, TypedDict

import pytest
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph
from langgraph.types import Command, interrupt


class _ResumeState(TypedDict, total=False):
    """最小中断恢复测试状态。"""

    goal: str
    firstAnswer: Any
    secondAnswer: Any


def _make_two_interrupt_graph():
    workflow = StateGraph(_ResumeState)

    def ask_first(state: _ResumeState) -> _ResumeState:
        answer = interrupt({"question": "第一次确认？", "goal": state["goal"]})
        return {"firstAnswer": answer}

    def ask_second(state: _ResumeState) -> _ResumeState:
        answer = interrupt({"question": "第二次确认？", "firstAnswer": state["firstAnswer"]})
        return {"secondAnswer": answer}

    workflow.add_node("ask_first", ask_first)
    workflow.add_node("ask_second", ask_second)
    workflow.add_edge(START, "ask_first")
    workflow.add_edge("ask_first", "ask_second")
    workflow.add_edge("ask_second", END)
    return workflow.compile(checkpointer=MemorySaver())


@pytest.mark.anyio
async def test_command_resume_wakes_latest_interrupt_across_multiple_rounds():
    graph = _make_two_interrupt_graph()
    config = {"configurable": {"thread_id": "thread-command-resume"}}

    first_chunks = [chunk async for chunk in graph.astream({"goal": "造订单"}, config=config, stream_mode="values")]
    assert "__interrupt__" in first_chunks[-1]

    second_chunks = [chunk async for chunk in graph.astream(Command(resume={"approved": True}), config=config, stream_mode="values")]
    assert second_chunks[-1]["firstAnswer"] == {"approved": True}
    assert "__interrupt__" in second_chunks[-1]

    final_chunks = [chunk async for chunk in graph.astream(Command(resume="继续"), config=config, stream_mode="values")]
    assert final_chunks[-1]["firstAnswer"] == {"approved": True}
    assert final_chunks[-1]["secondAnswer"] == "继续"
    assert "__interrupt__" not in final_chunks[-1]
