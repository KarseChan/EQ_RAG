# 🌍 地质灾害知识图谱智能助手 (Geo-Hazard Graph RAG Agent)

这是一个基于 **大模型 (LLM)** 和 **图数据库 (Apache AGE)** 的智能问答系统。它结合了 **Graph RAG (图检索增强)** 和 **Vector Search (向量检索)** 技术，能够处理复杂的自然语言查询，提供精准的结构化数据分析与可视化。

## ✨ 核心功能

- **🧠 智能问答 (Text-to-Cypher)**: 将自然语言自动转换为 Cypher 查询语句，直接从图数据库中提取答案。
- **🕸️ 混合检索 (Hybrid Search)**:
  - **图检索**: 基于 Apache AGE，处理多跳关系查询（如“朱炳湖核查了哪些高风险区域？”）。
  - **向量检索**: 基于 `pgvector`，处理抽象语义查询（如“哪里容易发生泥石流？”）。【待实现】
- **📊 可视化交互**: 集成 `streamlit-agraph`，动态展示知识图谱节点关系。
- **🛡️ 智能纠错**: 具备自我反思机制，当查询无结果时自动尝试模糊匹配或放宽条件。
- **📉 数据导出**: 支持将查询结果导出为 CSV/Excel 表格。

## 🛠️ 技术栈

- **Frontend**: Streamlit
- **LLM Framework**: LangChain, LangGraph
- **Database**: PostgreSQL (扩展: Apache AGE, pgvector)
- **Model**: Qwen (通义千问) via DashScope
- **Visualization**: Streamlit-AGraph, Pandas

## 🚀 快速开始

### 1. 环境准备

确保你的本地或服务器已安装：

- Python 3.8+
- PostgreSQL 12+ (需安装 `age` 和 `vector` 插件)



### 2. 安装依赖

克隆项目并安装 Python 依赖库：

Bash

```
git clone https://github.com/your-username/your-repo-name.git
cd your-repo-name

# 创建虚拟环境 (推荐)
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# 安装依赖
pip install -r requirements.txt
```



### 3. 配置数据库与环境变量

本项目使用 `config.py` 读取环境变量。请在项目根目录下创建一个 `.env` 文件，并填入以下配置：

**创建 `.env` 文件:**

```
# .env 示例
# === 数据库配置 ===
DB_HOST=localhost
DB_PORT=5432
DB_NAME=postgres
DB_USER=postgres
DB_PASSWORD=your_password
GRAPH_NAME=kg_graph2  # 你的图谱名称

# === 大模型配置 (以通义千问为例) ===
DASHSCOPE_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxx
LLM_MODEL_NAME=qwen-max
EMBEDDING_MODEL_NAME=text-embedding-v1
```



### 4. 启动应用

Bash

```
streamlit run app.py
```

启动后，浏览器将自动打开 `http://localhost:8501`。



## 📂 项目结构

```
├── app.py                  # Streamlit 主程序入口 (UI逻辑)
├── config.py               # 配置加载器 (读取 .env)
├── schema.py               # 图谱 Schema 定义 (节点/属性映射)
├── memory.py               # 对话历史记忆管理 (滑动窗口)
├── prompts.py              # System Prompts 与 提示词工程
├── tools.py                # LangChain 工具集 (Cypher查询/向量检索)
├── utils.py                # 通用工具函数 (图数据清洗/可视化转换)
├── requirements.txt        # 项目依赖
├── .env                    # 环境变量 (不要提交到 git)
└── scripts/
    └── generate_schema_tool.py  # 从 Excel 自动生成 schema.py
```



## 📄 License

[MIT](https://www.google.com/search?q=LICENSE)