import os
from langchain_community.chat_models import ChatTongyi
from langchain.agents import create_agent

# 自定义模块
from config import GRAPH_NAME
from tools import execute_cypher_query

# --- 1. 初始化模型 ---
llm = ChatTongyi(model_name="qwen-max", temperature=0)

# --- 2. 准备工具 ---
tools = [execute_cypher_query]

# --- 3. 定义 Prompt ---
system_prompt = f"""
你是一个 Apache AGE 图数据库专家。
图谱 Schema: 图名称 {GRAPH_NAME}，节点标签 :核查人, :防御区, :承载体，关系 :隶属。

【核心规则】
1. 只生成 MATCH/RETURN 语句，严禁生成 SQL。
2. 必须将返回字段封装在 Map 中：RETURN {{info: n}}。
"""

# --- 4. 创建 Agent (LangGraph版) ---
agent = create_agent(
    model=llm,
    tools=tools,
    system_prompt=system_prompt
)

# --- 5. 运行 ---
if __name__ == "__main__":
    print("🚀 Agent (LangGraph版) 启动中...")

    # 测试问题
    user_question = "有哪些防御区承载体关系？"
    
    # 根据文档，invoke 接收 messages 列表
    # 格式: {"messages": [{"role": "user", "content": "..."}]}
    
    input_data = {
        "messages": [
            {"role": "user", "content": user_question}
        ]
    }
    
    print(f"\n-----------------\n用户提问: {input_data['messages'][0]['content']}")
    
    try:
        # result 包含完整的状态，我们需要提取最后一条 AI 回复
        result = agent.invoke(input_data)
        
        # 打印最终回复
        last_message = result['messages'][-1]
        print("\n=== 最终答案 ===")
        print(last_message.content)

    except Exception as e:
        print(f"\n❌ 运行出错: {e}")