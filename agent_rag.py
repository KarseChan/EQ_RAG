import os
# 1. 引入阿里云模型类 ChatTongyi
from langchain_community.chat_models import ChatTongyi
from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import create_sql_agent

# 2. 配置阿里云 API Key
# 建议在系统环境变量里设置 DASHSCOPE_API_KEY，或者直接在这里赋值
os.environ["DASHSCOPE_API_KEY"] = "sk-27517f51fada47f9b6249249dbf38278"  # 替换你的百炼 API Key

# 3. 连接数据库 (PostgreSQL + AGE)
# 格式: postgresql://用户名:密码@IP:端口/数据库名
db_uri = "postgresql://postgres:postgres@192.168.104.129:5455/postgres"
db = SQLDatabase.from_uri(db_uri)

# 4. 初始化阿里云百炼大模型
# model_name 推荐使用 'qwen-max' (逻辑最强) 或 'qwen-plus' (性价比高)
llm = ChatTongyi(
    model_name="qwen-max",
    temperature=0  # 设为0，让生成的 SQL 更稳定，不产生幻觉
)

# 5. 注入 Apache AGE 的“使用说明书” (Prompt)
# 通义千问对指令的理解能力很强，这里我们明确告诉它转换规则
age_instructions = """
你是一个精通 Apache AGE 图数据库的专家。
当前连接的 PostgreSQL 数据库安装了 AGE 扩展。
你的任务是将用户的自然语言转换为 AGE 支持的查询语句。

**必须严格遵守以下规则：**
1. 不要生成标准的 SQL JOIN 查询。
2. 必须生成 Cypher 查询，并将其包裹在 SQL 函数中。
3. 语法模板：SELECT * FROM cypher('my_graph_name', $$ MATCH (n) RETURN n $$) as (a agtype);
   (请注意：将 'my_graph_name' 替换为实际的图名称)
4. 图谱中的节点标签(Label)有: Person (联系人), Zone (防御区), Carrier (承载体)。
5. 关系有: (:Person)-[:MANAGES]->(:Zone), (:Zone)-[:CONTAINS]->(:Carrier)。
"""

# 6. 创建智能体
# 注意：对于非 OpenAI 模型，agent_type 使用 "zero-shot-react-description" 通常兼容性更好
agent_executor = create_sql_agent(
    llm=llm,
    db=db,
    agent_type="zero-shot-react-description",
    verbose=True, # 设为 True 可以看到 Qwen 的思考过程
    prefix=age_instructions,
    handle_parsing_errors=True # 如果模型输出格式稍微有点歪，允许 LangChain 自动纠正
)

# 7. 测试提问
try:
    print("正在思考中...")
    response = agent_executor.invoke("有哪些核查人？")
    print("\n=== 最终结果 ===")
    print(response['output'])
except Exception as e:
    print("\n发生错误:", e)