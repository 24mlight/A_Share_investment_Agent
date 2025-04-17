from langchain_core.messages import HumanMessage
from src.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from src.utils.api_utils import agent_endpoint, log_llm_interaction
import json
import ast


@agent_endpoint("researcher_bear", "空方研究员，从看空角度分析市场数据并提出风险警示")
def researcher_bear_agent(state: AgentState):
    """Analyzes signals from a bearish perspective and generates cautionary investment thesis."""

    show_workflow_status("Bearish Researcher")
    show_reasoning = state["metadata"]["show_reasoning"]

    agents=state["metadata"]["agents"]
    
    
    agent_messages = {}
    for agent_name in agents:  # 遍历已选择的 agents
        message = next(
            (msg for msg in state["messages"] if msg.name == agent_name), None
        )
        if message:
            agent_messages[agent_name] = message

    parsed_signals = {}
    for agent_name, message in agent_messages.items():
        try:
            parsed_signals[agent_name] = json.loads(message.content)
        except Exception as e:
            parsed_signals[agent_name] = ast.literal_eval(message.content)

    # 动态获取消息
    agent_messages = {}

    for agent_name in agents:  # 遍历已选择的 agents
        message = next(
            (msg for msg in state["messages"] if msg.name == agent_name), None
        )
        if message:
            agent_messages[agent_name] = message

    # 解析消息内容
    parsed_signals = {}
    for agent_name, message in agent_messages.items():
        try:
            parsed_signals[agent_name] = json.loads(message.content)
        except Exception as e:
            parsed_signals[agent_name] = ast.literal_eval(message.content)

    # 动态分析每个选中的 agent
    bearish_points = []
    confidence_scores = []

    if "technical_analyst_agent" in parsed_signals:
        technical_signals = parsed_signals["technical_analyst_agent"]
        if technical_signals["signal"] == "bearish":
            bearish_points.append(
                f"Technical indicators show bearish momentum with {technical_signals['confidence']} confidence"
            )
            confidence_scores.append(
                float(str(technical_signals["confidence"]).replace("%", "")) / 100
            )
        else:
            bearish_points.append(
                "Technical rally may be temporary, suggesting potential reversal"
            )
            confidence_scores.append(0.3)

    if "fundamentals_agent" in parsed_signals:
        fundamental_signals = parsed_signals["fundamentals_agent"]
        if fundamental_signals["signal"] == "bearish":
            bearish_points.append(
                f"Concerning fundamentals with {fundamental_signals['confidence']} confidence"
            )
            confidence_scores.append(
                float(str(fundamental_signals["confidence"]).replace("%", "")) / 100
            )
        else:
            bearish_points.append(
                "Current fundamental strength may not be sustainable"
            )
            confidence_scores.append(0.3)

    if "sentiment_agent" in parsed_signals:
        sentiment_signals = parsed_signals["sentiment_agent"]
        if sentiment_signals["signal"] == "bearish":
            bearish_points.append(
                f"Negative market sentiment with {sentiment_signals['confidence']} confidence"
            )
            confidence_scores.append(
                float(str(sentiment_signals["confidence"]).replace("%", "")) / 100
            )
        else:
            bearish_points.append(
                "Market sentiment may be overly optimistic, indicating potential risks"
            )
            confidence_scores.append(0.3)

    if "valuation_agent" in parsed_signals:
        valuation_signals = parsed_signals["valuation_agent"]
        if valuation_signals["signal"] == "bearish":
            bearish_points.append(
                f"Stock appears overvalued with {valuation_signals['confidence']} confidence"
            )
            confidence_scores.append(
                float(str(valuation_signals["confidence"]).replace("%", "")) / 100
            )
        else:
            bearish_points.append(
                "Current valuation may not fully reflect downside risks"
            )
            confidence_scores.append(0.3)

    # Calculate overall bearish confidence
    avg_confidence = sum(confidence_scores) / len(confidence_scores)

    message_content = {
        "perspective": "bearish",
        "confidence": avg_confidence,
        "thesis_points": bearish_points,
        "reasoning": "Bearish thesis based on comprehensive analysis of selected factors",
    }

    message = HumanMessage(
        content=json.dumps(message_content),
        name="researcher_bear_agent",
    )



    if show_reasoning:
        show_agent_reasoning(message_content, "Bearish Researcher")
        # 保存推理信息到metadata供API使用
        state["metadata"]["agent_reasoning"] = message_content

    show_workflow_status("Bearish Researcher", "completed")
    return {
        "messages": state["messages"] + [message],
        "data": state["data"],
        "metadata": state["metadata"],
    }
