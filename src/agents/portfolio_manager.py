from langchain_core.messages import HumanMessage
from langchain_core.prompts import ChatPromptTemplate
import json

from src.agents.state import AgentState, show_agent_reasoning, show_workflow_status
from src.tools.openrouter_config import get_chat_completion
from src.utils.api_utils import agent_endpoint, log_llm_interaction


##### Portfolio Management Agent #####
@agent_endpoint("portfolio_management", "负责投资组合管理和最终交易决策")
def portfolio_management_agent(state: AgentState):
    """Responsible for portfolio management"""
    show_workflow_status("Portfolio Manager")
    show_reasoning = state["metadata"]["show_reasoning"]
    portfolio = state["data"]["portfolio"]
    agents=state["metadata"]["agents"]
    
# 动态获取消息
    agent_messages = {}
    for agent_name in agents:  # 遍历已选择的 agents
        message = next(
            (msg for msg in state["messages"] if msg.name == agent_name), None
        )
        if message:
            agent_messages[agent_name] = message

    # 检查是否有足够的消息
    if not agent_messages:
        raise ValueError("No valid agent messages found in the state.")

    # 解析消息内容
    parsed_signals = {}
    for agent_name, message in agent_messages.items():
        try:
            parsed_signals[agent_name] = json.loads(message.content)
        except Exception as e:
            parsed_signals[agent_name] = ast.literal_eval(message.content)

    # Create the system message
    system_message = {
        "role": "system",
        "content": f"""You are a portfolio manager making final trading decisions.
            Your job is to make a trading decision based on the team's analysis while strictly adhering
            to risk management constraints.

            RISK MANAGEMENT CONSTRAINTS:
            - You MUST NOT exceed the max_position_size specified by the risk manager
            - You MUST follow the trading_action (buy/sell/hold) recommended by risk management
            - These are hard constraints that cannot be overridden by other signals

            When weighing the different signals for direction and timing:
            {generate_signal_weights(agents)}

            The decision process should be:
            1. First check risk management constraints
            2. Then evaluate valuation signal
            3. Then evaluate fundamentals signal
            4. Use technical analysis for timing
            5. Consider sentiment for final adjustment
            
            Provide the following in your output:
            - "action": "buy" | "sell" | "hold",
            - "quantity": <positive integer>
            - "confidence": <float between 0 and 1>
            - "agent_signals": <list of agent signals including agent name, signal (bullish | bearish | neutral), and their confidence>
            - "reasoning": <concise explanation of the decision including how you weighted the signals>

            Trading Rules:
            - Never exceed risk management position limits
            - Only buy if you have available cash
            - Only sell if you have shares to sell
            - Quantity must be ≤ current position for sells
            - Quantity must be ≤ max_position_size from risk management"""
    }

    # Create the user message
    user_message_content = "Based on the team's analysis below, make your trading decision.\n\n"
    for agent_name, signal in parsed_signals.items():
        user_message_content += f"{agent_name.replace('_', ' ').title()} Trading Signal: {signal}\n"

    user_message_content += f"""
    Here is the current portfolio:
    Portfolio:
    Cash: {portfolio['cash']:.2f}
    Current Position: {portfolio['stock']} shares

    Only include the action, quantity, reasoning, confidence, and agent_signals in your output as JSON. Do not include any JSON markdown.

    Remember, the action must be either buy, sell, or hold.
    You can only buy if you have available cash.
    You can only sell if you have shares in the portfolio to sell."""
    user_message = {
            "role": "user",
            "content": user_message_content
        }

    # 记录LLM请求
    request_data = {
        "system_message": system_message,
        "user_message": user_message
    }

    # Get the completion from OpenRouter
    result = get_chat_completion([system_message, user_message])

    # 记录LLM交互
    state["metadata"]["current_agent_name"] = "portfolio_management"
    log_llm_interaction(state)(
        lambda: result
    )()

    # 如果API调用失败，使用默认的保守决策
    if result is None:
        result = json.dumps({
            "action": "hold",
            "quantity": 0,
            "confidence": 0.7,
            "agent_signals": [
                {
                    "agent_name": "technical_analysis",
                    "signal": "neutral",
                    "confidence": 0.0
                },
                {
                    "agent_name": "fundamental_analysis",
                    "signal": "bullish",
                    "confidence": 1.0
                },
                {
                    "agent_name": "sentiment_analysis",
                    "signal": "bullish",
                    "confidence": 0.6
                },
                {
                    "agent_name": "valuation_analysis",
                    "signal": "bearish",
                    "confidence": 0.67
                },
                {
                    "agent_name": "risk_management",
                    "signal": "hold",
                    "confidence": 1.0
                }
            ],
            "reasoning": "API error occurred. Following risk management signal to hold. This is a conservative decision based on the mixed signals: bullish fundamentals and sentiment vs bearish valuation, with neutral technicals."
        })

    # Create the portfolio management message
    message = HumanMessage(
        content=result,
        name="portfolio_management",
    )

    # 保存推理信息到state的metadata供API使用
    reasoning_content = result
    if show_reasoning:
        show_agent_reasoning(reasoning_content, "Portfolio Management Agent")
        state["metadata"]["agent_reasoning"] = reasoning_content

    show_workflow_status("Portfolio Manager", "completed")
    return {
        "messages": state["messages"] + [message],
        "data": state["data"],
        "metadata": state["metadata"],
    }

def generate_signal_weights(agents):
    """动态生成信号权重描述"""
    weights = {
        "valuation_agent": "Valuation Analysis (35% weight)",
        "fundamentals_agent": "Fundamental Analysis (30% weight)",
        "technical_analyst_agent": "Technical Analysis (25% weight)",
        "sentiment_agent": "Sentiment Analysis (10% weight)"
    }
    return "\n".join([f"{weights[agent]}" for agent in agents if agent in weights])


def format_decision(action: str, quantity: int, confidence: float, agent_signals: list, reasoning: str) -> dict:
    """Format the trading decision into a standardized output format.
    Think in English but output analysis in Chinese."""

    # 获取各个agent的信号
    fundamental_signal = next(
        (signal for signal in agent_signals if signal["agent_name"] == "fundamental_analysis"), None)
    valuation_signal = next(
        (signal for signal in agent_signals if signal["agent_name"] == "valuation_analysis"), None)
    technical_signal = next(
        (signal for signal in agent_signals if signal["agent_name"] == "technical_analysis"), None)
    sentiment_signal = next(
        (signal for signal in agent_signals if signal["agent_name"] == "sentiment_analysis"), None)
    risk_signal = next(
        (signal for signal in agent_signals if signal["agent_name"] == "risk_management"), None)

    # 转换信号为中文
    def signal_to_chinese(signal):
        if not signal:
            return "无数据"
        if signal["signal"] == "bullish":
            return "看多"
        elif signal["signal"] == "bearish":
            return "看空"
        return "中性"

    # 创建详细分析报告
    detailed_analysis = f"""
====================================
          投资分析报告
====================================

一、策略分析

1. 基本面分析 (权重30%):
   信号: {signal_to_chinese(fundamental_signal)}
   置信度: {fundamental_signal['confidence']*100:.0f}%
   要点: 
   - 盈利能力: {fundamental_signal.get('reasoning', {}).get('profitability_signal', {}).get('details', '无数据')}
   - 增长情况: {fundamental_signal.get('reasoning', {}).get('growth_signal', {}).get('details', '无数据')}
   - 财务健康: {fundamental_signal.get('reasoning', {}).get('financial_health_signal', {}).get('details', '无数据')}
   - 估值水平: {fundamental_signal.get('reasoning', {}).get('price_ratios_signal', {}).get('details', '无数据')}

2. 估值分析 (权重35%):
   信号: {signal_to_chinese(valuation_signal)}
   置信度: {valuation_signal['confidence']*100:.0f}%
   要点:
   - DCF估值: {valuation_signal.get('reasoning', {}).get('dcf_analysis', {}).get('details', '无数据')}
   - 所有者收益法: {valuation_signal.get('reasoning', {}).get('owner_earnings_analysis', {}).get('details', '无数据')}

3. 技术分析 (权重25%):
   信号: {signal_to_chinese(technical_signal)}
   置信度: {technical_signal['confidence']*100:.0f}%
   要点:
   - 趋势跟踪: ADX={technical_signal.get('strategy_signals', {}).get('trend_following', {}).get('metrics', {}).get('adx', '无数据'):.2f}
   - 均值回归: RSI(14)={technical_signal.get('strategy_signals', {}).get('mean_reversion', {}).get('metrics', {}).get('rsi_14', '无数据'):.2f}
   - 动量指标: 
     * 1月动量={technical_signal.get('strategy_signals', {}).get('momentum', {}).get('metrics', {}).get('momentum_1m', '无数据'):.2%}
     * 3月动量={technical_signal.get('strategy_signals', {}).get('momentum', {}).get('metrics', {}).get('momentum_3m', '无数据'):.2%}
     * 6月动量={technical_signal.get('strategy_signals', {}).get('momentum', {}).get('metrics', {}).get('momentum_6m', '无数据'):.2%}
   - 波动性: {technical_signal.get('strategy_signals', {}).get('volatility', {}).get('metrics', {}).get('historical_volatility', '无数据'):.2%}

4. 情绪分析 (权重10%):
   信号: {signal_to_chinese(sentiment_signal)}
   置信度: {sentiment_signal['confidence']*100:.0f}%
   分析: {sentiment_signal.get('reasoning', '无详细分析')}

二、风险评估
风险评分: {risk_signal.get('risk_score', '无数据')}/10
主要指标:
- 波动率: {risk_signal.get('risk_metrics', {}).get('volatility', '无数据')*100:.1f}%
- 最大回撤: {risk_signal.get('risk_metrics', {}).get('max_drawdown', '无数据')*100:.1f}%
- VaR(95%): {risk_signal.get('risk_metrics', {}).get('value_at_risk_95', '无数据')*100:.1f}%
- 市场风险: {risk_signal.get('risk_metrics', {}).get('market_risk_score', '无数据')}/10

三、投资建议
操作建议: {'买入' if action == 'buy' else '卖出' if action == 'sell' else '持有'}
交易数量: {quantity}股
决策置信度: {confidence*100:.0f}%

四、决策依据
{reasoning}

===================================="""

    return {
        "action": action,
        "quantity": quantity,
        "confidence": confidence,
        "agent_signals": agent_signals,
        "分析报告": detailed_analysis
    }
