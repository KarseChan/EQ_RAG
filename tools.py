import json
import psycopg2
from langchain_core.tools import tool
# 引用 config，实现解耦
from config import DB_CONFIG, GRAPH_NAME

def _clean_age_data(raw_data):
    """(内部函数) 清洗 AGE 返回的数据，去除 ::vertex 等后缀"""
    print(f"[Tool] 清洗前的数据：{raw_data}")
    if isinstance(raw_data, str):
        clean_str = raw_data.split('::')[0]
        try:
            return json.loads(clean_str)
        except:
            return clean_str
    return raw_data

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
        # results = [_clean_age_data(row[0]) for row in rows]
        results = [row[0] for row in rows]
        
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