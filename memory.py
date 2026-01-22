# memory.py
from langchain_core.messages import HumanMessage

def build_chat_context(current_prompt: str, history: list, strategy: str = "window", k: int = 6):
    """
    根据策略构建发送给 Agent 的消息上下文。

    Args:
        current_prompt (str): 当前用户的新问题。
        history (list): session_state 中的历史消息列表。
        strategy (str): 记忆策略
            - "none": 不记忆 (只发当前问题)
            - "full": 全量记忆 (小心 Token 爆炸)
            - "window": 滑动窗口 (最近 k 条)
        k (int): 窗口大小，默认为 6。

    Returns:
        dict: 符合 LangGraph 输入要求的字典 {"messages": [...]}
    """
    
    # 1. 构造当前消息对象
    current_msg_obj = HumanMessage(content=current_prompt)
    
    # 2. 根据策略筛选历史
    if strategy == "none":
        # 模式一：无记忆
        final_messages = [current_msg_obj]
        
    elif strategy == "full":
        # 模式二：全量
        final_messages = history + [current_msg_obj]
        
    elif strategy == "window":
        # 模式三：滑动窗口 (默认)
        # 确保 k 是偶数比较合理（一问一答），且至少为 2
        safe_k = max(2, k)
        recent_history = history[-safe_k:] if history else []
        final_messages = recent_history + [current_msg_obj]
        
    else:
        # 默认回退到 window
        recent_history = history[-6:] if history else []
        final_messages = recent_history + [current_msg_obj]

    return {"messages": final_messages}