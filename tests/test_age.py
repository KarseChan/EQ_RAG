import psycopg2
import json

# ================= 配置区 =================
DB_CONFIG = {
    "host": "192.168.104.129",
    "port": "5455",
    "database": "postgres",      # 替换为你的数据库名
    "user": "postgres",      # 替换为你的用户名
    "password": "postgres"   # 替换为你的密码
}

GRAPH_NAME = "kg_graph2"
# ==========================================

def test_connection():
    conn = None
    try:
        # 1. 连接数据库
        print(f"🔌 正在连接 PostgreSQL ({DB_CONFIG['host']}:{DB_CONFIG['port']})...")
        conn = psycopg2.connect(**DB_CONFIG)
        cursor = conn.cursor()
        print("✅ 数据库连接成功！")

        # 2. 初始化 AGE 环境 (关键步骤)
        # 如果不执行这步，会报 function cypher does not exist
        print("🛠️  正在加载 AGE 扩展...")
        cursor.execute("LOAD 'age';")
        cursor.execute("SET search_path = ag_catalog, '$user', public;")
        print("✅ AGE 环境加载成功！")

        # 3. 准备 SQL (完全使用你提供的 SQL)
        # 注意：这里使用了 Python 的三引号字符串，完美支持换行
        test_sql = f"""
        SELECT * from cypher('{GRAPH_NAME}', $$
        MATCH (V)-[R:核查]-(V2)
        RETURN V,R,V2
        $$) as (V agtype, R agtype, V2 agtype); 
        """

        print(f"🔍 正在查询图谱 '{GRAPH_NAME}'...")
        print(f"📜 执行 SQL: {test_sql.strip()}")
        
        # 4. 执行查询
        cursor.execute(test_sql)
        rows = cursor.fetchall()

        # 5. 打印结果
        print(f"\n🎉 查询成功！共找到 {len(rows)} 条结果：\n")
        
        for i, row in enumerate(rows):
            # row 是 (V, R, V2)
            # 使用 split('::')[0] 暴力切除末尾的 ::vertex 或 ::edge
            try:
                # 处理 V (节点)
                v_str = row[0].split('::')[0] 
                v_data = json.loads(v_str)
                
                # 处理 R (关系)
                r_str = row[1].split('::')[0]
                r_data = json.loads(r_str)
                
                # 处理 V2 (节点)
                v2_str = row[2].split('::')[0]
                v2_data = json.loads(v2_str)

                # 打印好看一点
                print(f"--- 结果 #{i+1} ---")
                print(f"防御区: {v_data['properties'].get('防御区唯一标识', '空')}")
                print(f"关系  : {r_data['label']}")
                print(f"核查人: {v2_data['properties'].get('姓名', '空')}")
                # print(f"原始数据: {v_data}") # 想看完整数据可以取消注释这一行
                
            except Exception as e:
                print(f"解析第 {i+1} 行时出错: {e}")
                print(f"原始数据: {row}")

    except psycopg2.Error as e:
        print("\n❌ 数据库错误:")
        print(e)
        print("\n💡 排查建议：")
        if "function cypher" in str(e):
            print(" -> 好像没加载 AGE，请检查 LOAD 'age' 是否执行。")
        elif "graph" in str(e) and "does not exist" in str(e):
            print(f" -> 图名称 '{GRAPH_NAME}' 不存在，请检查名字是否写错。")
        elif "password" in str(e):
            print(" -> 密码错误。")
            
    except Exception as e:
        print(f"\n❌ 其他错误: {e}")

    finally:
        if conn:
            conn.close()
            print("\n🔌 连接已关闭。")

if __name__ == "__main__":
    test_connection()