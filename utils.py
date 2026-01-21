from langchain_core.messages import HumanMessage

def get_chat_history(prompt: str, history_messages: list, strategy: str = "recent", k: int = 6):
    """
    根据策略获取构建给 Agent 的上下文消息列表。
    
    Args:
        prompt (str): 当前用户的新问题。
        history_messages (list): 存储在 session_state 中的历史消息对象列表。
        strategy (str): 策略模式，可选值:
            - "none": 不使用历史，只传当前问题 (最省 Token，无记忆)。
            - "full": 使用全部历史 (记忆最强，容易爆 Token 或出错)。
            - "recent": 使用最近 k 条历史 (推荐，平衡方案)。
        k (int): 当 strategy="recent" 时，截取的历史条数。默认为 6。
        
    Returns:
        dict: 符合 LangGraph 输入要求的字典，如 {"messages": [...]}
    """
    
    # 1. 构造当前用户的新消息对象
    current_message = HumanMessage(content=prompt)
    
    # 2. 根据策略选择历史
    if strategy == "none":
        # 模式一：纯净模式，只有当前问题
        final_messages = [current_message]
        
    elif strategy == "full":
        # 模式二：全量模式，历史 + 当前
        # 注意：history_messages 里应该只包含过去产生的对话，不含当前这个 prompt
        # 如果你的主逻辑是先 append 再调这个函数，这里就不需要再加 current_message
        final_messages = history_messages + [current_message]
        
    elif strategy == "recent":
        # 模式三：滑动窗口模式 (推荐)
        # 取最后 k 条历史，防止 token 溢出
        recent_history = history_messages[-k:] if history_messages else []
        final_messages = recent_history + [current_message]
        
    else:
        # 默认回退到 none
        final_messages = [current_message]

    return {"messages": final_messages}