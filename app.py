import streamlit as st
from langchain_community.chat_models import ChatTongyi
from langchain.agents import create_agent
from langchain_core.messages import HumanMessage, AIMessage

# 复用我们之前解耦好的模块
from config import GRAPH_NAME
from tools import execute_cypher_query

# 运行方式：
# streamlit run app.py
# streamlit run app.py --server.address 0.0.0.0

# ================== 1. 页面配置 ==================
st.set_page_config(
    page_title="图数据库智能助手",
    page_icon="🤖",
    layout="centered"
)

st.title(f"🤖 地灾数据智能问答助手")
st.caption(f"当前连接图谱: `{GRAPH_NAME}`")

# ================== 2. 初始化 Agent (带缓存) ==================
# 使用 cache_resource 装饰器，防止每次点击按钮都重新加载模型
@st.cache_resource
def get_agent():
    llm = ChatTongyi(model_name="qwen-max", temperature=0)
    tools = [execute_cypher_query]
    
    system_prompt = f"""
你是一个 Apache AGE 图数据库专家。
图谱 Schema: 
-图名称 {GRAPH_NAME}
-节点标签 :核查人、核查单位、防御区、承灾体
-关系类型 :隶属、核查、防御区承灾体关系

- **【重要属性规则】**: 
1. **名称/名字查询**: 用户输入名称（如张三、A区）时，属性键**固定为 '姓名'**。
   - 示例: "找张三" -> MATCH (n {{姓名: '张三'}})
2. **ID 查询**: 用户提供 "ID" 或 "编号" 时，必须根据节点类型选择对应的唯一标识字段：
   - 防御区 -> 属性键为 '防御区唯一标识'
   - 承灾体 -> 属性键为 '承灾体唯一标识'
   - 核查人 -> 属性键为 '姓名' 
   - 示例: "ID为123的防御区" -> MATCH (n:防御区 {{防御区唯一标识: '123'}})

【核心规则】
1. 只生成 MATCH/RETURN 语句，严禁生成 SQL。
2. **【强制】变量绑定规则**:
   在 MATCH 子句中，**必须**为关系指定变量名（通常用 `r`），**严禁**使用匿名关系！
   - ❌ 错误写法: `MATCH (a)-[:核查]->(b)` (会导致后面无法引用 r)
   - ✅ 正确写法: `MATCH (a)-[r:核查]->(b)` (必须显式定义 r)

3. **【关键】返回格式规范**：
   - **查节点时**：返回节点本身。MATCH (n:核查人) RETURN {{node: n}}
   - **查关系时**：必须同时返回【起点、关系、终点】组成的完整上下文。
     ✅ 正确：MATCH (a)-[r:隶属]->(b) RETURN {{source: a, rel: r, target: b}}
   
4. 必须将所有返回字段封装在一个 Map 对象中。
"""
    
    return create_agent(model=llm, tools=tools, system_prompt=system_prompt)

agent = get_agent()

# ================== 3. 管理聊天记录 ==================
# 如果 session_state 中没有 messages，初始化一个空的
if "messages" not in st.session_state:
    st.session_state.messages = []

# 在界面上重绘历史消息
for msg in st.session_state.messages:
    # 区分用户消息和 AI 消息的头像
    avatar = "🧑‍💻" if isinstance(msg, HumanMessage) else "🤖"
    with st.chat_message(msg.type, avatar=avatar):
        st.markdown(msg.content)

# ================== 4. 处理用户输入 ==================
if prompt := st.chat_input("请输入你想查询的内容（例如：有哪些核查人？）..."):
    # 1. 显示用户输入
    with st.chat_message("user", avatar="🧑‍💻"):
        st.markdown(prompt)
    # 将用户消息加入历史
    st.session_state.messages.append(HumanMessage(content=prompt))

    # 2. 调用 Agent
    with st.chat_message("assistant", avatar="🤖"):
        message_placeholder = st.empty()
        message_placeholder.markdown("🧠 正在思考并查询数据库...")
        
        try:
            # 构造 LangGraph 需要的输入格式
            # 注意：我们需要把整个历史记录传给 Agent，这样它才有上下文记忆
            # 但为了节省 Token，简单场景也可以只传最新的一条
            
            # 这里我们只传最新问题，避免把旧的 Tool 调用记录搞乱
            input_data = {
                "messages": [
                    {"role": "user", "content": prompt}
                ]
            }

            # 把 session_state 里的所有消息传给 Agent
            # full_history = st.session_state.messages
            # input_data = {
            #     "messages": full_history
            # }

            # 只取最后 6 条消息作为上下文
            # recent_history = st.session_state.messages[-6:] 
            # input_data = {
            #     "messages": recent_history
            # }
            
            # 执行调用
            result = agent.invoke(input_data)
            
            # 获取最终回复
            final_response = result['messages'][-1].content
            
            # 显示结果
            message_placeholder.markdown(final_response)
            
            # 将 AI 回复加入历史
            st.session_state.messages.append(AIMessage(content=final_response))
            
        except Exception as e:
            message_placeholder.error(f"❌ 发生错误: {str(e)}")