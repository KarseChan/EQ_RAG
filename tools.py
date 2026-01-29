import json, re
import psycopg2
from langchain_core.tools import tool
from streamlit_agraph import agraph, Node, Edge, Config
from sentence_transformers import SentenceTransformer, CrossEncoder

from config import DB_CONFIG, GRAPH_NAME, ORIGIN_NAME
from prompts import get_zero_results_hint

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
    print(f"\n[Tool] 收到 Cypher: {cypher_query}")
    
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

        print(f"\n[Tool] 组装 sql: {full_sql}")
        
        cursor.execute(full_sql)
        rows = cursor.fetchall()
        
        # 清洗结果
        results = [_clean_age_data(row[0]) for row in rows]
        # results = [row[0] for row in rows]

        # === 核心修改：零结果处理策略 ===
        if len(results) == 0:
            print("[Tool] ⚠️ 查询结果为空，返回引导提示")
            return get_zero_results_hint(query_info=cypher_query)
        # ===============================

        print(f"[Tool] 返回 {len(results)} 条数据")
        print(f"[Tool] ：{results}")
        return json.dumps(results, ensure_ascii=False)
        
    except Exception as e:
        error_msg = f"查询失败: {str(e)}"
        print(f"[Tool] ❌ 报错: {error_msg}")
        return error_msg
    finally:
        if conn:
            conn.close()

@tool
def search_knowledge_base(query: str) -> str:
    """
    语义检索工具。
    当需要查找具体的防御区信息、核查描述，或者根据模糊的描述（如"坡度陡峭"、"植被稀疏"）查找地点时，使用此工具。
    返回：最相关的防御区详细数据。
    """
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
            FROM "{ORIGIN_NAME}"."防御区_embeddings" 
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
        
        # 4. 格式化返回
        result_str = f"🔍 根据描述 '{query}'，为您找到最匹配的 5 个结果：\n\n"
        # 收集 ID 列表，显式告诉 Agent
        found_ids = []
        
        for item in final_top_5:
            data = item['data'] # full_metadata
            # 必须确保这里能取到你在 ETL 里存的 node_id (对应图谱里的 id)
            node_id = data.get('防御区编号') or data.get('id') 
            name = data.get('姓名', '未知点')
            desc = data.get('核查描述', '')
            
            found_ids.append(node_id)
            
            # 【关键】在返回文本里明确写出 ID，Agent 才能看懂
            result_str += f"- [ID: {node_id}] **{name}** (匹配度: {item['score']:.2f})\n"
            result_str += f"  描述: {desc}\n\n"
            
        # 【关键】在末尾加上这一句“提示词”，手把手教 Agent 下一步怎么做
        result_str += f"\n💡 系统提示: 如果用户需要查询这些地点的更多关联信息（如位置、负责人），" \
                      f"请使用工具 execute_cypher_query，并使用以下 ID 列表进行查询: {json.dumps(found_ids)}"
            
        return result_str

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