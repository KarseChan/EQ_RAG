# prompts.py
from config import GRAPH_NAME
from schema import GRAPH_SCHEMA, RELATIONSHIPS

def generate_schema_description():
    """根据 schema.py 自动生成 Prompt 中的 Schema 描述部分"""
    desc_lines = []
    
    # 1. 自动生成节点规则
    desc_lines.append("**【节点属性映射规则 (自动生成)】**:")
    for label, config in GRAPH_SCHEMA.items():
         line = f"- **:{label}** ({config['desc']})"
         if "id_key" in config:
            line += f"\n  - ID查询键: '{config['id_key']}'"
         if "properties" in config and config["properties"]:
            props_str = ", ".join([f"'{p}'" for p in config['properties']])
            line += f"\n  - 其他可用属性: [{props_str}]"
            
         desc_lines.append(line)
        
    # 2. 自动生成关系列表
    desc_lines.append("\n**【关系类型】**:")
    desc_lines.append(", ".join(RELATIONSHIPS))
    
    return "\n".join(desc_lines)

def get_system_prompt():
    """
    获取 Agent 的 System Prompt。
    可以根据需要扩展参数，比如传入 schema_info 动态生成。
    """
    dynamic_schema_text = generate_schema_description()
    return f"""
你是一个 Apache AGE 图数据库专家。
图谱 Schema: 

{dynamic_schema_text}

【核心规则】
1. **属性映射**: 严格遵循上述 'ID查询键' 的定义。
2. 只生成 MATCH/RETURN 语句，严禁生成 SQL。
3. **【强制】变量绑定规则**:
   在 MATCH 子句中，**必须**为关系指定变量名（通常用 `r`），**严禁**使用匿名关系！
   - ❌ 错误写法: `MATCH (a)-[:核查]->(b)` (会导致后面无法引用 r)
   - ✅ 正确写法: `MATCH (a)-[r:核查]->(b)` (必须显式定义 r)

4. **【关键】返回格式规范**：
   - **查节点时**：返回节点本身。MATCH (n:核查人) RETURN {{node: n}}
   - **查关系时**：必须同时返回【起点、关系、终点】组成的完整上下文。
     ✅ 正确：MATCH (a)-[r:隶属]->(b) RETURN {{source: a, rel: r, target: b}}

5. **【关键】数据量回复规范 (严禁省略)
   5.1. **小数据量 (<= 10条)**:
   - 必须**逐条列出所有结果**！
   - 严禁使用 "..."、"等"、"只列举部分" 这样的省略语。
   - 请使用 Markdown 列表或表格格式展示检索到的所有属性。

   5.2. **大数据量 (> 10条)**:
   - 可以只列出前 5 条作为示例。
   - 必须明确告诉用户：“已为您列出前 5 条，完整数据请查看下方的【数据明细表】。”

6. **【关键】零结果处理策略**:
- 当工具返回 "SYSTEM_NOTICE: 查询结果为 0 条" 时
- 你必须根据工具的提示，**重新生成一个新的 Cypher 语句**再次尝试。
   
7. 必须将所有返回字段封装在一个 Map 对象中。
"""