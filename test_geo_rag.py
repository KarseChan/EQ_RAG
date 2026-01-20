import json
import sys
from haystack import Document, Pipeline
from haystack.components.builders.prompt_builder import PromptBuilder
from haystack_integrations.components.generators.ollama import OllamaGenerator
from haystack_integrations.document_stores.chroma import ChromaDocumentStore
from haystack.components.writers import DocumentWriter
from haystack.components.embedders import SentenceTransformersDocumentEmbedder, SentenceTransformersTextEmbedder
from haystack_integrations.components.retrievers.chroma import ChromaEmbeddingRetriever
from tqdm import tqdm

# =================配置区域=================
# 模拟数据库 Home 表的数据 (实际场景中从 SQL 读取)
HOME_DB_DATA = [
    {"id": 1, "pyname": "yangguanghuayuan", "name": "阳光花园", "address": "广州市越秀区北京路12号", "x": 113.11, "y": 23.11, "geom": "POINT(...)"},
    {"id": 2, "pyname": "binjiangxiaoqu", "name": "滨江小区", "address": "广州市海珠区滨江东路88号", "x": 113.22, "y": 23.22, "geom": "POINT(...)"},
    {"id": 3, "pyname": "beijingluyihao", "name": "北京路一号公馆", "address": "广州市越秀区北京路步行街旁", "x": 113.12, "y": 23.12, "geom": "POINT(...)"},
    {"id": 4, "pyname": "tianhehuayuan", "name": "天河花园", "address": "广州市天河区天河路", "x": 113.33, "y": 23.33, "geom": "POINT(...)"}
]

CHROMA_PATH = "docs_db/geo_test/"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# =========================================

def generate_summary_with_llm(row_data):
    """
    Step 1: 利用 LLM 将结构化数据转化为自然语言综述 (Risk Profile / Semantic Profile)
    参考你的 testGenIntent.py
    """
    # 构造 Prompt，指导 LLM 生成包含地理位置和名称的描述
    prompt_template = """
    你是一个地理信息专家。请根据以下数据库字段，生成一段简短、流畅的中文综述。
    这段综述将用于向量检索，请重点包含地址(Address)和名称(Name)信息。
    
    字段信息:
    名称: {{ name }}
    地址: {{ address }}
    拼音: {{ pyname }}
    
    要求:
    1. 不要输出多余的解释，只输出综述段落。
    2. 示例输出: "位于广州市越秀区北京路的阳光花园小区，是一个地理位置优越的住宅区。"
    
    请生成:
    """

    # 这里为了演示方便，不直接调用 Ollama 服务以防你本地没开服务导致报错。
    # 如果你本地开了 Ollama (如 glm4)，请取消下方注释并注释掉 mock 部分。

    # --- 真实 LLM 调用代码 (参考 testGenIntent.py) ---
    # generator = OllamaGenerator(model="glm4", url="http://localhost:11434", generation_kwargs={"temperature": 0})
    # prompt_builder = PromptBuilder(template=prompt_template)
    # pipe = Pipeline()
    # pipe.add_component("prompt_builder", prompt_builder)
    # pipe.add_component("llm", generator)
    # pipe.connect("prompt_builder", "llm")
    # result = pipe.run({"prompt_builder": row_data})
    # summary = result["llm"]["replies"][0]

    # --- 模拟 LLM 生成 (用于快速测试逻辑) ---
    summary = f"该位置名为{row_data['name']}，具体地址位于{row_data['address']}。其拼音标识为{row_data['pyname']}。"
    # ---------------------------------------------

    return summary

def indexing_process():
    """
    Step 2: 生成综述 -> 向量化 -> 存入 Chroma
    参考你的 testHayStack_chroma.py
    """
    print(">>> 开始处理数据并构建索引...")

    documents = []

    for row in tqdm(HOME_DB_DATA, desc="Generating Summaries"):
        # 1. 让 LLM 生成语义化综述 (核心步骤)
        summary_text = generate_summary_with_llm(row)

        # 2. 构建 Document
        # content: 存放 LLM 生成的综述 (用于被向量化和检索)
        # meta: 存放原始结构化数据 (用于检索后提取 name, x, y 等)
        doc = Document(
            content=summary_text,
            meta={
                "original_id": row["id"],
                "name": row["name"],     # <--- 这是检索后你要取出的字段
                "address": row["address"],
                "x": row["x"],
                "y": row["y"]
            }
        )
        documents.append(doc)

    # 3. 初始化 Chroma 和 Embedder
    document_store = ChromaDocumentStore(persist_path=CHROMA_PATH)
    embedder = SentenceTransformersDocumentEmbedder(model=EMBEDDING_MODEL)
    embedder.warm_up()

    # 4. 写入流程
    docs_with_embeddings = embedder.run(documents)["documents"]
    document_store.write_documents(docs_with_embeddings)

    print(f">>> 已存入 {len(documents)} 条数据到 ChromaDB: {CHROMA_PATH}")

def retrieval_process(query_text):
    """
    Step 3: 接收 Query -> 向量化 -> 检索 -> 提取 Name
    """
    print(f"\n>>> 正在检索: '{query_text}'")

    document_store = ChromaDocumentStore(persist_path=CHROMA_PATH)

    # 构建检索 Pipeline
    retrieval_pipe = Pipeline()
    retrieval_pipe.add_component("text_embedder", SentenceTransformersTextEmbedder(model=EMBEDDING_MODEL))
    retrieval_pipe.add_component("retriever", ChromaEmbeddingRetriever(document_store=document_store))
    retrieval_pipe.connect("text_embedder.embedding", "retriever.query_embedding")

    # 运行检索
    result = retrieval_pipe.run({
        "text_embedder": {"text": query_text},
        "retriever": {"top_k": 3}  # 找最相似的2个
    })

    # 处理结果
    found_docs = result["retriever"]["documents"]

    results_list = []
    print(f"--- 检索结果 (Top {len(found_docs)}) ---")
    for doc in found_docs:
        # 从 meta 中提取原始字段
        target_name = doc.meta.get("name")
        target_address = doc.meta.get("address")
        score = doc.score

        print(f"匹配度: {score:.4f} | 提取名称: [{target_name}] | 依据综述: {doc.content}")
        results_list.append(target_name)

    return results_list

if __name__ == "__main__":
    # 1. 先执行一次索引 (如果数据变动)
    # 在实际使用中，数据入库只需执行一次，检索可以多次
    if not sys.argv[1:]: # 默认运行

        # 构建索引
        # indexing_process()

        # 2. 测试检索
        # 测试用例：提问包含“北京路”，看是否能找到“阳光花园”和“北京路一号公馆”
        user_query = "位于北京路的小区有哪些"
        names = retrieval_process(user_query)

        print("\n>>> 最终提取的小区名列表:")
        print(json.dumps(names, ensure_ascii=False, indent=4))

    # 支持命令行参数模式：python geo_rag_test.py "查询语句"
    else:
        query = sys.argv[1]
        retrieval_process(query)