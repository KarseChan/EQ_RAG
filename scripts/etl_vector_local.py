import os
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import psycopg2
from sentence_transformers import SentenceTransformer
from config import DB_CONFIG, GRAPH_NAME, ORIGIN_NAME

# 复用你脚本里的配置
MODEL_NAME = 'BAAI/bge-small-zh-v1.5'
SEARCH_COLUMN = "核查描述"

def sync_data_to_pgvector():
    print("1. 加载本地 Embedding 模型...")
    model = SentenceTransformer(MODEL_NAME)
    
    print("2. 连接数据库...")
    conn = psycopg2.connect(**DB_CONFIG)
    cursor = conn.cursor()
    
    # 确保向量插件开启
    cursor.execute("CREATE EXTENSION IF NOT EXISTS vector;")
    
    # 创建存储向量的表 (如果不存在)
    # 注意：bge-small-zh-v1.5 的维度是 512
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS "{ORIGIN_NAME}"."防御区_embeddings" (
            id SERIAL PRIMARY KEY,
            
            -- 这里存原始表的主键 (比如 '441302...')，作为连接图谱和向量的桥梁
            node_id VARCHAR(50),      
            
            -- 存原始内容 (给 LLM 看的)
            content TEXT,             
            
            -- 存完整 JSON (给前端展示用的)
            full_metadata JSONB,      
            
            -- 向量数据
            embedding vector(512)     
        );
        -- 创建索引
        CREATE INDEX IF NOT EXISTS idx_defense_embedding 
        ON "kg2_stg"."防御区_embeddings" USING hnsw (embedding vector_cosine_ops);
    """)
    conn.commit()

    # 3. 读取原始数据
    print("3. 读取原始数据...")
    # 注意：根据你的脚本，表名是 "ORIGIN_NAME"."防御区"
    cursor.execute(f'SELECT * FROM "{ORIGIN_NAME}"."防御区" WHERE "{SEARCH_COLUMN}" IS NOT NULL')
    columns = [desc[0] for desc in cursor.description]
    rows = cursor.fetchall()

    data_to_insert = []
    print(f"   准备处理 {len(rows)} 条数据...")

    # 4. 批量生成向量
    for row in rows:
        row_dict = dict(zip(columns, row))
        text_content = row_dict.get(SEARCH_COLUMN, "")
        
        # 获取业务ID (假设有一列叫 'id' 或 '防御区唯一标识'，根据你实际情况修改)
        # 这里为了演示，我假设第一列就是 ID
        node_id = str(row_dict.get('防御区编号', 'unknown_id'))

        # 生成向量 (转成 List 格式)
        vector = model.encode(text_content).tolist()
        
        # 准备插入的数据: (node_id, content, full_metadata, embedding)
        import json
        data_to_insert.append((
            node_id, 
            text_content, 
            json.dumps(row_dict, default=str), 
            vector
        ))

    # 5. 存入数据库
    print("4. 写入 pgvector 表...")
    insert_query = f"""
        INSERT INTO "{ORIGIN_NAME}"."防御区_embeddings" 
        (node_id, content, full_metadata, embedding) 
        VALUES (%s, %s, %s, %s)
    """
    cursor.executemany(insert_query, data_to_insert)
    conn.commit()
    
    print("✅ 完成！数据已持久化到数据库。")
    conn.close()

if __name__ == "__main__":
    sync_data_to_pgvector()