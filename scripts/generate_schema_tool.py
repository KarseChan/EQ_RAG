# scripts/generate_schema_tool.py
import pandas as pd
import json

# ================= 配置区 =================
EXCEL_PATH = "mapping.xlsx"  # 你的Excel文件路径
SHEET_NAME = "Sheet1"

# Excel 列名映射 (根据你手头的表格实际列名修改这里)
COL_LABEL = "节点类型"
COL_PROP = "字段名"
COL_DESC = "字段含义" 
COL_TYPE = "字段类型"  # 标记是 ID、Name 还是普通属性

# ================= 核心逻辑 =================
def generate_schema_code():
    try:
        # 1. 读取 Excel
        df = pd.read_excel(EXCEL_PATH, sheet_name=SHEET_NAME)
        
        # 填充空值，防止报错
        df.fillna("", inplace=True)
        
        schema_dict = {}

        # 2. 遍历每一行数据
        for _, row in df.iterrows():
            label = str(row[COL_LABEL]).strip()
            prop = str(row[COL_PROP]).strip()
            desc = str(row[COL_DESC]).strip()
            p_type = str(row[COL_TYPE]).strip().lower()

            # 如果这个 label 还没处理过，初始化结构
            if label not in schema_dict:
                schema_dict[label] = {
                    "desc": f"{label}实体", # 默认描述，稍后可手动优化
                    "query_key": "姓名",    # 默认兜底
                    "properties": []
                }

            # 3. 根据类型填充 schema
            if p_type == "id":
                schema_dict[label]["id_key"] = prop
            elif p_type == "name":
                schema_dict[label]["query_key"] = prop
            else:
                # 普通属性加入列表
                if prop: # 防止空行
                    schema_dict[label]["properties"].append(prop)
                    
            # (可选) 如果这一行是对节点的整体描述，可以覆盖 desc
            # if p_type == "entity_desc":
            #     schema_dict[label]["desc"] = desc

        # 4. 生成 Python 代码字符串
        # 我们不直接 dump JSON，因为生成的 Python 代码需要在 schema.py 里被引用
        # 这里的 output 是为了让你直接复制粘贴
        
        output_code = "# Auto-generated from Excel mapping\n"
        output_code += "GRAPH_SCHEMA = {\n"
        
        for label, config in schema_dict.items():
            output_code += f'    "{label}": {{\n'
            output_code += f'        "desc": "{config["desc"]}",\n'
            output_code += f'        "query_key": "{config["query_key"]}",\n'
            
            if "id_key" in config:
                output_code += f'        "id_key": "{config["id_key"]}",\n'
                
            # 属性列表格式化
            props_list = str(config["properties"]).replace("'", '"')
            output_code += f'        "properties": {props_list}\n'
            output_code += f'    }},\n'
            
        output_code += "}\n"

        print("✅ 转换成功！内容如下：\n")
        print("-" * 30)
        print(output_code)
        print("-" * 30)
        
        # 5. (可选) 直接写入文件
        # with open("schema.py", "w", encoding="utf-8") as f:
        #     f.write(output_code)
        #     print("已写入 schema.py")

    except Exception as e:
        print(f"❌ 发生错误: {e}")

if __name__ == "__main__":
    generate_schema_code()