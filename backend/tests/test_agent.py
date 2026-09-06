# -*- coding: utf-8 -*-
"""智能体编排测试：Fake 模型跑通 LangGraph 全流程（不依赖真实模型）"""
import uuid

import pytest
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage

from app.agent import flow as agent_flow
from app.agent import skills


@pytest.fixture
def fake_model_pack(monkeypatch):
    """脚本化模型输出：flow 默认画布 LLM 调用顺序 = 研究 → 起草 → 质检"""
    scripted = FakeMessagesListChatModel(responses=[
        AIMessage(content="要点：先接情绪，再给承诺"),
        AIMessage(content="1. 好的，周末回家吃饭\n2. 哈哈行，我带奶茶\n3. 嗯，周六见"),
        AIMessage(content="PASS"),
    ])
    monkeypatch.setattr(agent_flow, "resolve_model",
                        lambda db, user_id, spec, temperature: (scripted, "fake", ""))
    return scripted


def test_skill_matching():
    hits = skills.match_skills("领导突然表扬我")
    assert any(s["name"] == "职场沟通" for s in hits)
    hits2 = skills.match_skills("周末一起吃饭吗")
    assert any(s["name"] == "邀约应答" for s in hits2)
    # 自定义 JSON 技能被热加载
    assert any(s["name"] == "学生党社交" for s in skills.load_skills())


def test_flow_pipeline(fake_model_pack):
    """默认画布：开始→检索→研究→起草→质检→输出（脚本顺序 = 研究/起草/质检）"""
    result = agent_flow.run_flow(
        db=None, user_id="u1", username="tester",
        message="领导突然在群里表扬我", person="同事小王",
        history="", model_spec="fake|test", engine="agent")
    assert len(result["candidates"]) == 3
    assert result["candidates"][0].startswith("好的，周末")
    nodes = [t["node"] for t in result["trace"]]
    assert "retrieve" in [n for n in nodes] and nodes.count("draft") >= 1
    assert result["engine"] == "flow"


def test_flow_taboo_redraft(monkeypatch):
    """质检 FAIL → 沿 fail 边进入重写 LLM → 二审 PASS（画布循环门控）"""
    responses = [
        AIMessage(content="要点：略"),                                      # 研究
        AIMessage(content="1. 借你五百不还\n2. 嘲讽说教版\n3. 一般"),      # 起草 v1（含金钱+说教）
        AIMessage(content="FAIL:包含金钱承诺与说教"),                      # 质检 v1
        AIMessage(content="1. 这周手头紧，帮不上\n2. 哈哈我也想啊\n3. 下次吧"),  # 重写
        AIMessage(content="PASS"),                                        # 质检 v2
    ]
    scripted = FakeMessagesListChatModel(responses=responses)
    monkeypatch.setattr(agent_flow, "resolve_model",
                        lambda db, user_id, spec, temperature: (scripted, "fake", ""))

    result = agent_flow.run_flow(
        db=None, user_id="u1", username="tester",
        message="借我五百块周转", person="同事", history="",
        model_spec="fake|test", engine="agent")
    assert result["candidates"][0].startswith("这周手头紧")
    nodes = [t["node"] for t in result["trace"]]
    # 重写 LLM 节点执行了两次（初稿 + 否决后重写）
    assert nodes.count("draft") == 2


def test_tools_and_skills_listing(client, auth):
    tools = client.get("/api/agent/tools", headers=auth).json()
    builtin_names = {t["name"] for t in tools["builtin"]}
    assert {"kb_search", "relationship_profile", "history_recall", "current_time"} <= builtin_names
    assert any("weather" in p["name"] for p in tools["plugin"])

    skill_names = [s["name"] for s in client.get("/api/agent/skills", headers=auth).json()]
    assert "职场沟通" in skill_names and "学生党社交" in skill_names
