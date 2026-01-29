import os
import sys
# 确保能找到项目路径（如果需要）
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 【关键】设置国内镜像，解决你的 502 问题
os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"

from sentence_transformers import SentenceTransformer, CrossEncoder

# 定义模型保存的本地路径 (推荐放在项目目录下的 models 文件夹)
MODEL_DIR = "./models"

def download_all_models():
    # 1. 下载 BGE-Small (向量模型)
    print("⬇️ 正在下载 Embedding 模型...")
    # cache_folder 参数指定下载到哪里
    model_retriever = SentenceTransformer('BAAI/bge-small-zh-v1.5', cache_folder=MODEL_DIR)
    model_retriever.save(os.path.join(MODEL_DIR, 'bge-small-zh-v1.5'))
    print("✅ Embedding 模型已保存到 ./models/bge-small-zh-v1.5")

    # 2. 下载 BGE-Reranker (重排序模型)
    print("⬇️ 正在下载 Reranker 模型...")
    # CrossEncoder 没有直接的 cache_folder 参数，通常先加载再 save
    model_reranker = CrossEncoder('BAAI/bge-reranker-base')
    model_reranker.model.save_pretrained(os.path.join(MODEL_DIR, 'bge-reranker-base'))
    model_reranker.tokenizer.save_pretrained(os.path.join(MODEL_DIR, 'bge-reranker-base'))
    print("✅ Reranker 模型已保存到 ./models/bge-reranker-base")

if __name__ == "__main__":
    if not os.path.exists(MODEL_DIR):
        os.makedirs(MODEL_DIR)
    download_all_models()