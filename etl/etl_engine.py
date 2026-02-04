#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
ETL引擎 - 根据YAML配置自动执行数据转换
从GDB文件读取数据，按照配置规则转换为Ontology格式，输出JSON
"""

import yaml
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Optional
import geopandas as gpd
from shapely.geometry import mapping
import warnings

warnings.filterwarnings('ignore')


class ETLEngine:
    """ETL引擎类"""
    
    def __init__(self, config_path: str):
        """
        初始化ETL引擎
        
        Args:
            config_path: YAML配置文件路径
        """
        self.config_path = config_path
        self.config = self._load_config()
        self.gdb_path = self.config.get('global_config', {}).get('database_path', '')
        self.gdf_cache = {}  # 缓存GDB图层数据
        
    def _load_config(self) -> Dict:
        """加载YAML配置文件"""
        with open(self.config_path, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)
    
    def _read_gdb_layer(self, layer_name: str) -> gpd.GeoDataFrame:
        """
        读取GDB图层
        
        Args:
            layer_name: 图层名称
            
        Returns:
            GeoDataFrame对象
        """
        if layer_name in self.gdf_cache:
            return self.gdf_cache[layer_name]
        
        try:
            gdf = gpd.read_file(self.gdb_path, layer=layer_name)
            self.gdf_cache[layer_name] = gdf
            return gdf
        except Exception as e:
            print(f"读取图层 {layer_name} 失败: {e}")
            return gpd.GeoDataFrame()
    
    def _generate_key(self, row: Dict, key_rule: Dict) -> str:
        """
        根据规则生成主键
        
        Args:
            row: 数据行
            key_rule: 主键规则配置
            
        Returns:
            生成的主键字符串
        """
        prefix = key_rule.get('prefix', '')
        method = key_rule.get('method', 'direct')
        
        if method == 'md5':
            # 多字段组合生成MD5
            fields = key_rule.get('fields', [])
            values = [str(row.get(f, '')) for f in fields]
            combined = ''.join(values)
            hash_obj = hashlib.md5(combined.encode('utf-8'))
            return f"{prefix}{hash_obj.hexdigest()}"
        else:
            # 直接使用单个字段
            field = key_rule.get('field', '')
            return f"{prefix}{row.get(field, '')}"
    
    def _transform_value(self, value: Any, dtype: Optional[str] = None) -> Any:
        """
        转换值的数据类型
        
        Args:
            value: 原始值
            dtype: 目标数据类型
            
        Returns:
            转换后的值
        """
        if value is None or (isinstance(value, float) and value != value):  # 检查NaN
            return None
        
        if dtype == 'float':
            try:
                return float(value)
            except (ValueError, TypeError):
                return None
        elif dtype == 'int':
            try:
                return int(value)
            except (ValueError, TypeError):
                return None
        elif dtype == 'wkt':
            if hasattr(value, 'wkt'):
                return value.wkt
            return str(value)
        
        return value
    
    def _calc_sum_fields(self, row: Dict, columns: List[str]) -> int:
        """
        计算指定字段的总和
        
        Args:
            row: 数据行
            columns: 要求和的字段列表
            
        Returns:
            总和
        """
        total = 0
        for col in columns:
            val = row.get(col)
            if val is not None:
                try:
                    total += int(val)
                except (ValueError, TypeError):
                    pass
        return total
    
    def _process_attributes(self, row: Dict, attributes: List[Dict]) -> Dict:
        """
        处理属性映射
        
        Args:
            row: 原始数据行
            attributes: 属性映射配置列表
            
        Returns:
            处理后的属性字典
        """
        result = {}
        
        for attr in attributes:
            target = attr.get('target')
            source = attr.get('source')
            dtype = attr.get('dtype')
            transform_func = attr.get('transform_func')
            attr_type = attr.get('type')
            default = attr.get('default')
            
            if attr_type == 'nested':
                # 处理嵌套对象
                nested_result = {}
                children = attr.get('children', [])
                
                for child in children:
                    child_target = child.get('target')
                    child_source = child.get('source')
                    child_transform = child.get('transform_func')
                    child_params = child.get('params', {})
                    child_default = child.get('default')
                    
                    if child_transform == 'calc_sum_fields':
                        columns = child_params.get('columns', [])
                        nested_result[child_target] = self._calc_sum_fields(row, columns)
                    elif child_source:
                        value = row.get(child_source)
                        if value is None:
                            nested_result[child_target] = child_default
                        else:
                            nested_result[child_target] = self._transform_value(value)
                    else:
                        nested_result[child_target] = child_default
                    
                    # 处理子集
                    subsets = child.get('subsets', [])
                    if subsets:
                        subset_data = {}
                        for subset in subsets:
                            subset_target = subset.get('target')
                            subset_source = subset.get('source')
                            subset_default = subset.get('default')
                            
                            subset_value = row.get(subset_source)
                            if subset_value is None:
                                subset_data[subset_target] = subset_default
                            else:
                                subset_data[subset_target] = self._transform_value(subset_value)
                        
                        nested_result.update(subset_data)
                
                result[target] = nested_result
                
            elif transform_func == 'calc_sum_fields':
                params = attr.get('params', {})
                columns = params.get('columns', [])
                result[target] = self._calc_sum_fields(row, columns)
                
            elif source:
                value = row.get(source)
                if value is None:
                    result[target] = default
                else:
                    result[target] = self._transform_value(value, dtype)
            else:
                result[target] = default
        
        return result
    
    def _process_relationships(self, row: Dict, relationships: List[Dict]) -> List[Dict]:
        """
        处理关系映射
        
        Args:
            row: 原始数据行
            relationships: 关系映射配置列表
            
        Returns:
            关系列表
        """
        result = []
        
        for rel in relationships:
            relation = rel.get('relation')
            target_type = rel.get('target_type')
            foreign_key_field = rel.get('foreign_key_field')
            target_key_prefix = rel.get('target_key_prefix', '')
            dynamic_relation = rel.get('dynamic_relation')
            
            if dynamic_relation:
                # 动态关系
                source_column = dynamic_relation.get('source_column')
                rules = dynamic_relation.get('rules', [])
                
                source_value = row.get(source_column)
                relation_name = None
                
                for rule in rules:
                    match_value = rule.get('match_value')
                    if match_value == 'otherwise' or match_value == source_value:
                        relation_name = rule.get('relation_name')
                        break
                
                if relation_name:
                    foreign_key = row.get(foreign_key_field)
                    if foreign_key:
                        result.append({
                            'relation': relation_name,
                            'target_type': target_type,
                            'target_id': f"{target_key_prefix}{foreign_key}"
                        })
            else:
                # 静态关系
                foreign_key = row.get(foreign_key_field)
                if foreign_key:
                    result.append({
                        'relation': relation,
                        'target_type': target_type,
                        'target_id': f"{target_key_prefix}{foreign_key}"
                    })
        
        return result
    
    def _process_mapping(self, mapping_name: str, mapping_config: Dict) -> Dict:
        """
        处理单个映射配置
        
        Args:
            mapping_name: 映射名称
            mapping_config: 映射配置
            
        Returns:
            处理后的数据字典
        """
        source_layer = mapping_config.get('source_layer')
        entity_type = mapping_config.get('entity_type')
        key_rule = mapping_config.get('key_rule', {})
        attributes = mapping_config.get('attributes', [])
        relationships = mapping_config.get('relationships', [])
        
        # 读取GDB图层
        gdf = self._read_gdb_layer(source_layer)
        
        if gdf.empty:
            print(f"图层 {source_layer} 为空或不存在")
            return {
                'mapping_name': mapping_name,
                'entity_type': entity_type,
                'entities': []
            }
        
        # 处理去重策略
        dedup_policy = key_rule.get('deduplication_policy')
        entities_dict = {}  # 用于去重和合并
        
        for idx, row in gdf.iterrows():
            # 将GeoDataFrame的Series转换为字典
            row_dict = row.to_dict()
            
            # 生成主键
            key = self._generate_key(row_dict, key_rule)
            
            # 处理属性
            attrs = self._process_attributes(row_dict, attributes)
            
            # 处理关系
            rels = self._process_relationships(row_dict, relationships)
            
            if dedup_policy == 'merge_relation':
                # 合并关系模式
                if key in entities_dict:
                    # 合并关系
                    existing_rels = entities_dict[key].get('relationships', [])
                    for new_rel in rels:
                        # 检查关系是否已存在
                        is_duplicate = False
                        for existing_rel in existing_rels:
                            if (existing_rel.get('relation') == new_rel.get('relation') and
                                existing_rel.get('target_type') == new_rel.get('target_type') and
                                existing_rel.get('target_id') == new_rel.get('target_id')):
                                is_duplicate = True
                                break
                        if not is_duplicate:
                            existing_rels.append(new_rel)
                    entities_dict[key]['relationships'] = existing_rels
                else:
                    entities_dict[key] = {
                        'id': key,
                        'type': entity_type,
                        'attributes': attrs,
                        'relationships': rels
                    }
            else:
                # 默认模式：每行一个实体
                entities_dict[key] = {
                    'id': key,
                    'type': entity_type,
                    'attributes': attrs,
                    'relationships': rels
                }
        
        return {
            'mapping_name': mapping_name,
            'entity_type': entity_type,
            'entities': list(entities_dict.values())
        }
    
    def run(self) -> Dict[str, Dict]:
        """
        运行ETL流程
        
        Returns:
            所有映射的结果字典
        """
        results = {}
        
        # 跳过全局配置，只处理映射配置
        for key, value in self.config.items():
            if key == 'global_config':
                continue
            
            if isinstance(value, dict) and 'source_layer' in value:
                print(f"正在处理映射: {key}")
                result = self._process_mapping(key, value)
                results[key] = result
                print(f"  - 完成，共生成 {len(result['entities'])} 个实体")
        
        return results
    
    def save_to_json(self, results: Dict[str, Dict], output_dir: str = './output'):
        """
        将结果保存为JSON文件
        
        Args:
            results: ETL结果
            output_dir: 输出目录
        """
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        for mapping_name, data in results.items():
            file_path = output_path / f"{mapping_name}.json"
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            print(f"已保存: {file_path}")


def main():
    """主函数"""
    # 配置文件路径
    config_path = 'test.yaml'
    
    # 创建ETL引擎
    engine = ETLEngine(config_path)
    
    # 运行ETL
    results = engine.run()
    
    # 保存结果
    engine.save_to_json(results)
    
    print("\nETL流程完成！")


if __name__ == '__main__':
    main()
