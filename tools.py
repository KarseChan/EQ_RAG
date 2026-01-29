import json, re
import psycopg2
from langchain_core.tools import tool
from streamlit_agraph import agraph, Node, Edge, Config
from sentence_transformers import SentenceTransformer, CrossEncoder

from config import DB_CONFIG, GRAPH_NAME, ORIGIN_NAME
from prompts import get_zero_results_hint


# 定义映射关系：Agent 传过来的 category -> 数据库里的表名
TABLE_MAP = {
    "defense_area": "防御区_embeddings",  # 防御区
    "checker": "核查人_embeddings",       # 核查人 (举例)
    "device": "设备_embeddings"           # 设备 (举例)
}


# 全局加载模型 (避免每次调用工具都重新加载，耗时)
# 注意：Streamlit 启动时会执行这里，可能会稍微慢几秒
print("⏳ 正在加载检索模型...")
RETRIEVER = SentenceTransformer('BAAI/bge-small-zh-v1.5')
RERANKER = CrossEncoder('BAAI/bge-reranker-base')
print("✅ 模型加载完毕")

def _clean_age_data(raw_data):
    """
    (内部函数) 使用正则清洗 AGE 返回的数据，去除 ::vertex, ::edge, ::numeric 等后缀
    """
    # 1. 如果不是字符串（比如已经是数字或None），直接返回
    if not isinstance(raw_data, str):
        return raw_data

    # print(f"[Debug] 清洗前: {raw_data}")

    # 2. 核心修改：使用正则替换，将 "::xxxx" 替换为空字符串
    # r'::\w+' 匹配双冒号后跟任意字母/数字/下划线
    clean_str = re.sub(r'::\w+', '', raw_data)

    # 3. 尝试解析 JSON
    try:
        return json.loads(clean_str)
    except json.JSONDecodeError:
        # 如果不是 JSON（比如只是普通字符串 "Hello"），就返回清洗后的字符串
        return clean_str

@tool
def execute_cypher_query(cypher_query: str) -> str:
    """
    执行 Cypher 查询。
    输入必须是纯 Cypher 语句，例如: MATCH (n:核查人) RETURN {info: n}
    不要包含 SQL 包装。
    """
    print(f"\n[图谱精准检索] 大模型生成的Cypher: {cypher_query}")
    
    conn = None
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 初始化 AGE
        cursor.execute("LOAD 'age';")
        cursor.execute("SET search_path = ag_catalog, '$user', public;")
        
        # SQL 包装器 (单列返回策略)
        full_sql = f"""
        SELECT * FROM cypher('{GRAPH_NAME}', $$
            {cypher_query}
        $$) as (result agtype);
        """

        # print(f"\n[图谱精准检索] 组装的sql: {full_sql}")
        
        cursor.execute(full_sql)
        rows = cursor.fetchall()
        
        # 清洗结果
        results = [_clean_age_data(row[0]) for row in rows]
        # results = [row[0] for row in rows]

        # === 核心修改：零结果处理策略 ===
        if len(results) == 0:
            print("[图谱精准检索] ⚠️ 查询结果为空，返回引导提示")
            return get_zero_results_hint(query_info=cypher_query)
        # ===============================

        print(f"[图谱精准检索] 返回 {len(results)} 条数据")
        print(f"[图谱精准检索] 内容：{results}")
        return json.dumps(results, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"查询失败: {str(e)}"
        print(f"[Tool] ❌ 报错: {error_msg}")
        return error_msg
    finally:
        if conn:
            conn.close()

@tool
def search_knowledge_base(query: str, category: str = "defense_area") -> str:
    """
    通用语义检索工具。
    返回：匹配到的原始 JSON 数据列表。
    """
    # 1. 确定要查哪张表
    target_table = TABLE_MAP.get(category)
    if not target_table:
        return f"系统错误: 未知的分类 '{category}'，请检查工具调用参数。"

    conn = None
    try:
        # 1. 将用户问题转向量
        query_vector = RETRIEVER.encode(query).tolist()
        
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        
        # 2. 数据库向量初筛 (Top 50)
        # 使用 <=> 操作符计算余弦距离
        sql = f"""
            SELECT content, full_metadata, (embedding <=> %s::vector) as distance
            FROM "{ORIGIN_NAME}"."{target_table}" 
            ORDER BY distance ASC
            LIMIT 50
        """
        cursor.execute(sql, (json.dumps(query_vector),))
        rows = cursor.fetchall()
        
        if not rows:
            return "未找到相关信息。"
            
        # 3. 重排序 (Reranking) - 提升精度的关键
        # 准备数据对: [[query, doc1], [query, doc2]...]
        pairs = [[query, row[0]] for row in rows]
        
        # 计算相关性分数
        scores = RERANKER.predict(pairs)
        
        # 将分数和原始数据绑定
        ranked_results = []
        for i in range(len(rows)):
            ranked_results.append({
                "score": float(scores[i]),
                "data": rows[i][1] # full_metadata (JSON格式)
            })
            
        # 按分数降序排列，取 Top 5
        ranked_results.sort(key=lambda x: x["score"], reverse=True)
        final_top_5 = ranked_results[:5]

        print(f"[语义检索] 内容： {final_top_5}")
        
        # 4. 格式化返回 (通用化改造)
        final_response = {
            # 1. 元数据 (Meta Info)：告诉 LLM 这是怎么来的
            "meta_context": {
                "source_tool": "vector_semantic_search", # 明确告知是向量检索
                "retrieval_query": query,                # 明确告知用的什么关键词查的
                "target_category": category,             # 明确告知查的什么分类
                "record_count": len(final_top_5),     # 查到了几条
                "description": "The following data was retrieved based on vector semantic similarity. Please use this context to answer the user's question."
            },
            
            # 2. 数据载荷 (Payload)：纯净的原始数据列表
            "search_results": final_top_5
        }

        # 返回整个大的 JSON 对象
        return json.dumps(final_response, ensure_ascii=False, indent=2)

    except Exception as e:
        return f"检索出错: {str(e)}"
    finally:
        if conn: conn.close()


def generate_graph_from_data(data_list):
    """
    将 AGE 返回的 [{source:..., rel:..., target:...}, ...] 转换为 agraph 的节点和边
    """
    nodes = []
    edges = []
    node_ids = set() # 用于去重，防止重复添加同一个节点炸裂

    for item in data_list:
        # 1. 解析 Source 节点
        if "source" in item:
            src = item["source"]
            src_id = str(src.get("id")) # ID 转字符串
            # 尝试获取显示名称：优先找 '姓名'，其次 'name'，最后用 'label'
            src_label = src.get("properties", {}).get("姓名") or \
                        src.get("properties", {}).get("name") or \
                        src.get("label")
            
            if src_id not in node_ids:
                # size=25 是节点大小，color 是颜色
                nodes.append(Node(id=src_id, label=str(src_label), size=25, shape="dot"))
                node_ids.add(src_id)

        # 2. 解析 Target 节点
        if "target" in item:
            tgt = item["target"]
            tgt_id = str(tgt.get("id"))
            tgt_label = tgt.get("properties", {}).get("姓名") or \
                        tgt.get("properties", {}).get("name") or \
                        tgt.get("label")
            
            if tgt_id not in node_ids:
                nodes.append(Node(id=tgt_id, label=str(tgt_label), size=25, shape="dot"))
                node_ids.add(tgt_id)

        # 3. 解析 Relationship 边
        if "rel" in item and "source" in item and "target" in item:
            rel = item["rel"]
            # start_id 和 end_id 必须和上面 Node 的 id 对应
            # AGE 返回的边包含 start_id 和 end_id
            source_id_ref = str(rel.get("start_id"))
            target_id_ref = str(rel.get("end_id"))
            label = rel.get("label") # 关系名称，如 "核查"
            
            edges.append(Edge(source=source_id_ref, 
                              target=target_id_ref, 
                              label=label,
                              type="CURVE_SMOOTH")) # 线条样式

    # 配置图的物理引擎效果
    config = Config(width="100%", 
                    height=400, 
                    directed=True, 
                    nodeHighlightBehavior=True, 
                    highlightColor="#F7A7A6", # 鼠标悬停颜色
                    collapsible=False)
    
    return nodes, edges, config