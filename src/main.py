import sys
import argparse
import uuid  # Import uuid for run IDs
import threading  # Import threading for background task
import uvicorn  # Import uvicorn to run FastAPI

from datetime import datetime, timedelta
from langgraph.graph import END, StateGraph
from langchain_core.messages import HumanMessage
import pandas as pd
import akshare as ak

# --- Agent Imports ---
from src.agents.valuation import valuation_agent
from src.agents.state import AgentState
from src.agents.sentiment import sentiment_agent
from src.agents.risk_manager import risk_management_agent
from src.agents.technicals import technical_analyst_agent
from src.agents.portfolio_manager import portfolio_management_agent
from src.agents.market_data import market_data_agent
from src.agents.fundamentals import fundamentals_agent
from src.agents.researcher_bull import researcher_bull_agent
from src.agents.researcher_bear import researcher_bear_agent
from src.agents.debate_room import debate_room_agent

# --- Logging and Backend Imports ---
from src.utils.output_logger import OutputLogger
# 导入原始函数，但不再进行猴子补丁
from src.tools.openrouter_config import get_chat_completion
from src.utils.llm_interaction_logger import (
    log_agent_execution,
    set_global_log_storage
)
from backend.dependencies import get_log_storage
from backend.main import app as fastapi_app  # Import the FastAPI app
import questionary

# --- Initialize Logging ---

# 1. Initialize Log Storage
log_storage = get_log_storage()
set_global_log_storage(log_storage)  # Set storage in context for the wrapper

# 移除猴子补丁逻辑
# 2. Wrap the original LLM call function
# logged_get_chat_completion = wrap_llm_call(original_get_chat_completion)

# 3. Monkey-patch the function in its original module
# src.tools.openrouter_config.get_chat_completion = logged_get_chat_completion
# Optional: Confirmation message
# print("--- Patched get_chat_completion for logging ---")

# Initialize standard output logging
# This will create a timestamped log file in the logs directory
sys.stdout = OutputLogger()


# --- Run the Hedge Fund Workflow ---
def run_hedge_fund(run_id: str, ticker: str, start_date: str, end_date: str, portfolio: dict, show_reasoning: bool = False, num_of_news: int = 5,agent_choices=None):
    print(f"--- Starting Workflow Run ID: {run_id} ---")

    # 设置backend的run_id
    try:
        from backend.state import api_state
        api_state.current_run_id = run_id
        print(f"--- API State updated with Run ID: {run_id} ---")
    except Exception as e:
        print(f"Note: Could not update API state: {str(e)}")

    initial_state = {
        "messages": [
            HumanMessage(
                content="Make a trading decision based on the provided data.",
            )
        ],
        "data": {
            "ticker": ticker,
            "portfolio": portfolio,
            "start_date": start_date,
            "end_date": end_date,
            "num_of_news": num_of_news,
        },
        "metadata": {
            "show_reasoning": show_reasoning,
            "run_id": run_id,  # Pass run_id in metadata
            "agents" : agent_choices
        },

        

    }

    # 使用backend的workflow_run上下文管理器（如果可用）
    try:
        from backend.utils.context_managers import workflow_run
        with workflow_run(run_id):
            final_state = app.invoke(initial_state)
            print(f"--- Finished Workflow Run ID: {run_id} ---")
    except ImportError:
        # 如果未能导入，直接执行
        final_state = app.invoke(initial_state)
        print(f"--- Finished Workflow Run ID: {run_id} ---")

        # 尝试更新API状态（如果可用）
        try:
            api_state.complete_run(run_id, "completed")
        except Exception:
            pass

    # 保持原有的返回格式：最后一条消息的内容
    return final_state["messages"][-1].content



ANALYST_ORDER = [

    ("Technical Analyst", technical_analyst_agent),
    ("Fundamentals Agent", fundamentals_agent),
    ("Sentiment Agent", sentiment_agent),
    ("Valuation Agent", valuation_agent),
]

# 使用 questionary 让用户选择 agents
choices = questionary.checkbox(
    "Select your AI analysts.",
    choices=[questionary.Choice(display, value=value) for display, value in ANALYST_ORDER],
    instruction="\n\nInstructions: \n1. Press Space to select/unselect analysts.\n2. Press 'a' to select/unselect all.\n3. Press Enter when done to run the hedge fund.\n",
    validate=lambda x: len(x) > 0 or "You must select at least one analyst.",
    style=questionary.Style(
        [
            ("checkbox-selected", "fg:green"),
            ("selected", "fg:green noinherit"),
            ("highlighted", "noinherit"),
            ("pointer", "noinherit"),
        ]
    ),
).ask()

print(choices)
# 打印用户选择的 agents
print("\n您选择启用的 agents 是：")
for agent in choices:
    print(f"- {agent}")

# 模拟动态添加到 workflow
workflow = {}
for agent in choices:
    agent_name = agent.__name__ if hasattr(agent, '__name__') else str(agent)
    workflow[agent] = f"{agent}_function"  # 假设每个 agent 有对应的函数




# --- Define the Workflow Graph ---
workflow = StateGraph(AgentState)

# Add nodes - Remove explicit log_agent_execution calls
# The @agent_endpoint decorator now handles logging to BaseLogStorage
for agent in choices:
    agent_name = agent.__name__ if hasattr(agent, '__name__') else str(agent)
    workflow.add_node(agent_name, agent)


workflow.add_node("market_data_agent", market_data_agent)
workflow.add_node("researcher_bull_agent", researcher_bull_agent)
workflow.add_node("researcher_bear_agent", researcher_bear_agent)
workflow.add_node("debate_room_agent", debate_room_agent)
workflow.add_node("risk_management_agent", risk_management_agent)
workflow.add_node("portfolio_management_agent", portfolio_management_agent)



# Define the workflow edges (remain unchanged)
workflow.set_entry_point("market_data_agent")


# Market Data to Analysts
for analyst in choices:
        analyst_name = analyst.__name__ if hasattr(analyst, '__name__') else str(analyst)
        workflow.add_edge("market_data_agent", analyst_name)

# workflow.add_edge("market_data_agent", "technical_analyst_agent")
# workflow.add_edge("market_data_agent", "fundamentals_agent")
# workflow.add_edge("market_data_agent", "sentiment_agent")
# workflow.add_edge("market_data_agent", "valuation_agent")


# Analysts to Researchers
for analyst in choices:
        analyst_name = analyst.__name__ if hasattr(analyst, '__name__') else str(analyst)
        workflow.add_edge(analyst_name, "researcher_bull_agent")

for analyst in choices:
        analyst_name = analyst.__name__ if hasattr(analyst, '__name__') else str(analyst)
        workflow.add_edge(analyst_name, "researcher_bear_agent")



# workflow.add_edge("technical_analyst_agent", "researcher_bull_agent")
# workflow.add_edge("fundamentals_agent", "researcher_bull_agent")
# workflow.add_edge("sentiment_agent", "researcher_bull_agent")
# workflow.add_edge("valuation_agent", "researcher_bull_agent")

# workflow.add_edge("technical_analyst_agent", "researcher_bear_agent")
# workflow.add_edge("fundamentals_agent", "researcher_bear_agent")
# workflow.add_edge("sentiment_agent", "researcher_bear_agent")
# workflow.add_edge("valuation_agent", "researcher_bear_agent")

# Researchers to Debate Room
workflow.add_edge("researcher_bull_agent", "debate_room_agent")
workflow.add_edge("researcher_bear_agent", "debate_room_agent")

# Debate Room to Risk Management
workflow.add_edge("debate_room_agent", "risk_management_agent")

# Risk Management to Portfolio Management
workflow.add_edge("risk_management_agent", "portfolio_management_agent")
workflow.add_edge("portfolio_management_agent", END)

# 打印 workflow 的节点和边
print("\n--- Workflow Nodes ---")
for node in workflow.nodes:
    print(f"Node: {node}")

print("\n--- Workflow Edges ---")
for edge in workflow.edges:
    print(f"Edge: {edge}")


# Compile the workflow graph
app = workflow.compile()


# --- FastAPI Background Task ---
def run_fastapi():
    print("--- Starting FastAPI server in background (port 8000) ---")
    # Note: Change host/port/log_level as needed
    # Disable Uvicorn's own logging config to avoid conflicts with app's logging
    uvicorn.run(fastapi_app, host="0.0.0.0", port=8000, log_config=None)


# --- Main Execution Block ---
if __name__ == "__main__":
    # Start FastAPI server in a background thread
    fastapi_thread = threading.Thread(target=run_fastapi, daemon=True)
    fastapi_thread.start()

    # --- Argument Parsing (remains the same) ---
    parser = argparse.ArgumentParser(
        description='Run the hedge fund trading system')
    # ... (keep existing parser arguments) ...
    parser.add_argument('--ticker', type=str, required=True,
                        help='Stock ticker symbol')
    parser.add_argument('--start-date', type=str,
                        help='Start date (YYYY-MM-DD). Defaults to 1 year before end date')
    parser.add_argument('--end-date', type=str,
                        help='End date (YYYY-MM-DD). Defaults to yesterday')
    parser.add_argument('--show-reasoning', action='store_true',
                        help='Show reasoning from each agent')
    parser.add_argument('--num-of-news', type=int, default=5,
                        help='Number of news articles to analyze for sentiment (default: 5)')
    parser.add_argument('--initial-capital', type=float, default=100000.0,
                        help='Initial cash amount (default: 100,000)')
    parser.add_argument('--initial-position', type=int, default=0,
                        help='Initial stock position (default: 0)')

    args = parser.parse_args()

    # --- Date Handling (remains the same) ---
    current_date = datetime.now()
    yesterday = current_date - timedelta(days=1)
    end_date = yesterday if not args.end_date else min(
        datetime.strptime(args.end_date, '%Y-%m-%d'), yesterday)

    if not args.start_date:
        start_date = end_date - timedelta(days=365)
    else:
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d')

    if start_date > end_date:
        raise ValueError("Start date cannot be after end date")
    if args.num_of_news < 1:
        raise ValueError("Number of news articles must be at least 1")
    if args.num_of_news > 100:
        raise ValueError("Number of news articles cannot exceed 100")

    # --- Portfolio Setup (remains the same) ---
    portfolio = {
        "cash": args.initial_capital,
        "stock": args.initial_position
    }

    # --- Execute Workflow ---
    # Generate run_id here when running directly
    main_run_id = str(uuid.uuid4())

    print(choices)
    print('######################')
    agent_names=[]
    for analyst in choices:
        agent_names.append(analyst.__name__ if hasattr(analyst, '__name__') else str(analyst))

    print(agent_names)

    result = run_hedge_fund(
        run_id=main_run_id,  # Pass the generated run_id
        ticker=args.ticker,
        start_date=start_date.strftime('%Y-%m-%d'),
        end_date=end_date.strftime('%Y-%m-%d'),
        portfolio=portfolio,
        show_reasoning=args.show_reasoning,
        num_of_news=args.num_of_news,
        agent_choices=agent_names
    )
    print("\nFinal Result:")
    print(result)

# --- Historical Data Function (remains the same) ---


def get_historical_data(symbol: str) -> pd.DataFrame:
    # ... (keep existing function implementation) ...
    current_date = datetime.now()
    yesterday = current_date - timedelta(days=1)
    end_date = yesterday
    target_start_date = yesterday - timedelta(days=365)

    print(f"\n正在获取 {symbol} 的历史行情数据...")
    print(f"目标开始日期：{target_start_date.strftime('%Y-%m-%d')}")
    print(f"结束日期：{end_date.strftime('%Y-%m-%d')}")

    try:
        df = ak.stock_zh_a_hist(symbol=symbol,
                                period="daily",
                                start_date=target_start_date.strftime(
                                    "%Y%m%d"),
                                end_date=end_date.strftime("%Y%m%d"),
                                adjust="qfq")

        actual_days = len(df)
        target_days = 365

        if actual_days < target_days:
            print(f"提示：实际获取到的数据天数({actual_days}天)少于目标天数({target_days}天)")
            print(f"将使用可获取到的所有数据进行分析")

        print(f"成功获取历史行情数据，共 {actual_days} 条记录\n")
        return df

    except Exception as e:
        print(f"获取历史数据时发生错误: {str(e)}")
        print("将尝试获取最近可用的数据...")

        try:
            df = ak.stock_zh_a_hist(
                symbol=symbol, period="daily", adjust="qfq")
            print(f"成功获取历史行情数据，共 {len(df)} 条记录\n")
            return df
        except Exception as e:
            print(f"获取历史数据失败: {str(e)}")
            return pd.DataFrame()
