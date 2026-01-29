import psycopg2
import pandas as pd
import torch
from sentence_transformers import SentenceTransformer, CrossEncoder, util
import json 

# =================配置区域=================
DB_CONFIG = {
    'host': '192.168.104.129',
    'port': '5455',
    'user': 'postgres',
    'password': 'postgres', 
    'dbname': 'postgres'
}

RETRIEVAL_MODEL_NAME = 'BAAI/bge-small-zh-v1.5'
RERANK_MODEL_NAME = 'BAAI/bge-reranker-base'

TOP_K_RETRIEVAL = 50 
TOP_K_RERANK = 5 

# 【新增配置】指定数据库中哪一列用于生成向量（语义搜索的核心字段）
SEARCH_COLUMN = "核查描述" 
# ==========================================

class SemanticSearchSystem:
    def __init__(self):
        print("正在加载模型，请稍候...")
        self.retriever = SentenceTransformer(RETRIEVAL_MODEL_NAME)
        self.reranker = CrossEncoder(RERANK_MODEL_NAME)
        
        self.corpus_texts = []      # 仅存储用于搜索的文本（如"核查描述"）
        self.corpus_rows = []       # 【新增】存储完整的数据库行数据（字典格式）
        self.corpus_embeddings = None 

    def load_data_from_db(self):
        print(f"正在连接数据库 {DB_CONFIG['host']}...")
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            cursor = conn.cursor()
            
            # 【修改点1】SQL语句改为 SELECT * 获取所有字段
            # 依然保留 WHERE 条件，防止用于搜索的字段为空导致报错
            sql = f'SELECT * FROM "kg2_stg"."防御区" WHERE "{SEARCH_COLUMN}" IS NOT NULL'
            
            print(f"正在执行 SQL: {sql}")
            cursor.execute(sql)
            
            # 获取列名，用于将 tuple 转为 dict
            columns = [desc[0] for desc in cursor.description]
            rows = cursor.fetchall()
            
            # 【修改点2】同时构建搜索文本列表和完整数据列表
            self.corpus_texts = []
            self.corpus_rows = []
            
            for row in rows:
                # 将元组转换为字典，方便通过列名访问
                row_dict = dict(zip(columns, row))
                
                # 1. 提取用于向量化的文本
                text_content = row_dict.get(SEARCH_COLUMN, "")
                self.corpus_texts.append(text_content)
                
                # 2. 存储完整数据
                self.corpus_rows.append(row_dict)
                
            print(f"成功加载 {len(self.corpus_texts)} 条数据。")
            
            cursor.close()
            conn.close()
            
        except Exception as e:
            print(f"数据库连接或查询失败: {e}")
            return False
            
        return True

    def build_index(self):
        if not self.corpus_texts:
            print("没有数据可建立索引。")
            return
            
        print("正在生成向量索引 (Embedding)...")
        # 这里只对 corpus_texts (核查描述) 进行向量化
        self.corpus_embeddings = self.retriever.encode(
            self.corpus_texts, 
            convert_to_tensor=True, 
            show_progress_bar=True
        )
        print("索引构建完成。")

    def search(self, query):
        print(f"\n======== 正在搜索: {query} ========")
        
        # 1. 向量召回
        query_embedding = self.retriever.encode(query, convert_to_tensor=True)
        hits = util.semantic_search(query_embedding, self.corpus_embeddings, top_k=TOP_K_RETRIEVAL)
        hits = hits[0]
        
        print(f"初筛 (Vector Retrieval) 找到了 {len(hits)} 个候选结果。")
        
        # 2. 重排序
        # 注意：这里 Cross-encoder 依然只计算 query 和 文本字段 的相似度
        cross_inp = [[query, self.corpus_texts[hit['corpus_id']]] for hit in hits]
        cross_scores = self.reranker.predict(cross_inp)
        
        for idx in range(len(hits)):
            hits[idx]['cross_score'] = cross_scores[idx]
            
        hits = sorted(hits, key=lambda x: x['cross_score'], reverse=True)
        
        # 3. 展示结果
        print(f"\n>>> 最终重排序 (Reranking) Top {TOP_K_RERANK} 结果:")
        for i in range(min(TOP_K_RERANK, len(hits))):
            hit = hits[i]
            doc_id = hit['corpus_id'] # 这是数据在列表中的索引
            
            # 根据 ID 获取对应的完整行数据
            full_row_data = self.corpus_rows[doc_id]
            
            print(f"\n[Rank {i+1}] (Score: {hit['cross_score']:.4f})")
            
            # ensure_ascii=False 确保中文正常显示
            print(json.dumps(full_row_data, indent=4, ensure_ascii=False, default=str))

if __name__ == "__main__":
    search_system = SemanticSearchSystem()
    
    if search_system.load_data_from_db():
        search_system.build_index()
        
        test_query = "坡度较低" 
        search_system.search(test_query) 