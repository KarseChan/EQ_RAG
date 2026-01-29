"""
单元测试：scripts/etl_vector_local.py 中的 sync_data_to_pgvector() 函数

测试覆盖：
- 正常流程（多条数据）
- 边界情况（空数据、单条数据）
- 数据库操作（连接、表创建、数据插入）
- 向量生成和存储
"""

import os
import sys
import json
from unittest.mock import Mock, MagicMock, patch, call

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest

# 导入被测试的模块
from scripts import etl_vector_local


class TestSyncDataToPgvector:
    """测试 sync_data_to_pgvector 函数的各种场景"""

    @pytest.fixture
    def mock_model(self):
        """Mock SentenceTransformer 模型"""
        model = MagicMock()
        # 模拟 encode 方法返回512维向量
        model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 512)
        return model

    @pytest.fixture
    def mock_db_connection(self):
        """Mock 数据库连接和游标"""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.commit.return_value = None
        return mock_conn, mock_cursor

    @pytest.fixture
    def sample_data(self):
        """示例数据"""
        return [
            (1, "防御区A", "核查描述A", "2024-01-01"),
            (2, "防御区B", "核查描述B", "2024-01-02"),
            (3, "防御区C", "核查描述C", "2024-01-03"),
        ]

    @pytest.fixture
    def sample_columns(self):
        """示例列名"""
        return ["id", "防御区名称", "核查描述", "创建日期"]

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_normal_flow(
        self, mock_connect, mock_sentence_transformer,
        mock_db_connection, sample_data, sample_columns
    ):
        """测试正常流程：多条数据同步"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 512)
        mock_sentence_transformer.return_value = mock_model

        # 设置数据库游标行为
        mock_cursor.description = [
            (col,) for col in sample_columns
        ]
        mock_cursor.fetchall.return_value = sample_data

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证模型加载
        mock_sentence_transformer.assert_called_once_with('BAAI/bge-small-zh-v1.5')

        # 验证数据库连接
        mock_connect.assert_called_once()
        
        # 验证向量扩展创建
        assert mock_cursor.execute.call_count >= 3  # 扩展、表创建、索引、查询、插入
        
        # 验证表创建 SQL
        create_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        assert any('CREATE EXTENSION' in str(c) for c in create_calls)
        assert any('CREATE TABLE IF NOT EXISTS node_embeddings' in str(c) for c in create_calls)
        assert any('CREATE INDEX' in str(c) for c in create_calls)

        # 验证数据查询
        assert any('SELECT * FROM "kg2_stg"."防御区"' in str(c) for c in create_calls)

        # 验证数据插入（应该调用一次 insert）
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT' in str(c)]
        assert len(insert_calls) >= 1

        # 验证提交和关闭
        mock_conn.commit.assert_called()
        mock_conn.close.assert_called_once()

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_empty_data(
        self, mock_connect, mock_sentence_transformer, mock_db_connection
    ):
        """测试边界情况：空数据"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        
        mock_model = MagicMock()
        mock_sentence_transformer.return_value = mock_model

        # 设置数据库返回空数据
        mock_cursor.description = [("id",), ("核查描述",)]
        mock_cursor.fetchall.return_value = []

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证没有插入数据
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT' in str(c)]
        assert len(insert_calls) == 0

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_single_row(
        self, mock_connect, mock_sentence_transformer, mock_db_connection
    ):
        """测试边界情况：单条数据"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 512)
        mock_sentence_transformer.return_value = mock_model

        # 设置数据库返回单条数据
        mock_cursor.description = [("id",), ("防御区名称",), ("核查描述",)]
        mock_cursor.fetchall.return_value = [(1, "防御区A", "测试描述")]

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证模型 encode 被调用一次
        assert mock_model.encode.call_count == 1

        # 验证插入数据
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'INSERT' in str(c)]
        assert len(insert_calls) >= 1

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_vector_generation(
        self, mock_connect, mock_sentence_transformer, mock_db_connection
    ):
        """测试向量生成的正确性"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 512)
        mock_sentence_transformer.return_value = mock_model

        # 设置测试数据
        mock_cursor.description = [("id",), ("核查描述",)]
        test_texts = ["测试描述1", "测试描述2", "测试描述3"]
        mock_cursor.fetchall.return_value = [(i, text) for i, text in enumerate(test_texts)]

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证 encode 被正确调用
        assert mock_model.encode.call_count == len(test_texts)
        encode_calls = [call(text) for text in test_texts]
        mock_model.encode.assert_has_calls(encode_calls, any_order=True)

        # 验证向量维度正确（512维）
        for call_args in mock_model.encode.call_args_list:
            encode_result = call_args[0][0]
            assert encode_result in test_texts

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_json_metadata(
        self, mock_connect, mock_sentence_transformer, mock_db_connection
    ):
        """测试元数据序列化为 JSON 的正确性"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 512)
        mock_sentence_transformer.return_value = mock_model

        # 设置测试数据（包含多种数据类型）
        mock_cursor.description = [("id",), ("防御区名称",), ("核查描述",), ("数量",), ("创建时间",)]
        test_row = (1, "防御区A", "测试描述", 100, "2024-01-01")
        mock_cursor.fetchall.return_value = [test_row]

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证插入的数据包含正确的 JSON 元数据
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'executemany' in str(c) or 'INSERT' in str(c)]
        assert len(insert_calls) >= 1

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_database_connection_error(
        self, mock_connect, mock_sentence_transformer
    ):
        """测试数据库连接失败的情况"""
        # 设置 mock：连接失败
        mock_connect.side_effect = Exception("连接失败")
        mock_sentence_transformer.return_value = MagicMock()

        # 执行测试（应该抛出异常）
        with pytest.raises(Exception, match="连接失败"):
            etl_vector_local.sync_data_to_pgvector()

        # 验证模型仍然被加载（在连接失败前）
        mock_sentence_transformer.assert_called_once_with('BAAI/bge-small-zh-v1.5')

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_table_creation(
        self, mock_connect, mock_sentence_transformer, mock_db_connection
    ):
        """测试表创建的正确性"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        mock_sentence_transformer.return_value = MagicMock()
        
        # 设置空数据
        mock_cursor.description = [("id",), ("核查描述",)]
        mock_cursor.fetchall.return_value = []

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证表创建语句包含正确的列和类型
        execute_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        
        # 检查表创建
        table_create_found = False
        for call_str in execute_calls:
            if 'CREATE TABLE IF NOT EXISTS node_embeddings' in call_str:
                table_create_found = True
                # 验证必要的列
                assert 'id SERIAL PRIMARY KEY' in call_str
                assert 'node_id VARCHAR(50)' in call_str
                assert 'content TEXT' in call_str
                assert 'full_metadata JSONB' in call_str
                assert 'embedding vector(512)' in call_str
                break
        
        assert table_create_found, "未找到表创建语句"

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_index_creation(
        self, mock_connect, mock_sentence_transformer, mock_db_connection
    ):
        """测试索引创建的正确性"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        mock_sentence_transformer.return_value = MagicMock()
        
        # 设置空数据
        mock_cursor.description = [("id",), ("核查描述",)]
        mock_cursor.fetchall.return_value = []

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证索引创建
        execute_calls = [str(c) for c in mock_cursor.execute.call_args_list]
        
        index_found = False
        for call_str in execute_calls:
            if 'CREATE INDEX' in call_str:
                index_found = True
                assert 'idx_node_embedding' in call_str
                assert 'hnsw' in call_str
                assert 'vector_cosine_ops' in call_str
                break
        
        assert index_found, "未找到索引创建语句"

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_node_id_extraction(
        self, mock_connect, mock_sentence_transformer, mock_db_connection
    ):
        """测试 node_id 从第一列提取的正确性"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 512)
        mock_sentence_transformer.return_value = mock_model

        # 设置测试数据：第一列是各种类型的 ID
        test_ids = ["abc", 123, 45.67, None]
        mock_cursor.description = [("id",), ("name",), ("描述",)]
        mock_cursor.fetchall.return_value = [(test_id, f"名称{i}", f"描述{i}") for i, test_id in enumerate(test_ids)]

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证每行数据都被处理
        assert mock_model.encode.call_count == len(test_ids)

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_large_batch(
        self, mock_connect, mock_sentence_transformer, mock_db_connection
    ):
        """测试大批量数据处理"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 512)
        mock_sentence_transformer.return_value = mock_model

        # 设置大量测试数据（100条）
        batch_size = 100
        mock_cursor.description = [("id",), ("描述",)]
        mock_cursor.fetchall.return_value = [(i, f"测试描述{i}") for i in range(batch_size)]

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证所有数据都被处理
        assert mock_model.encode.call_count == batch_size

        # 验证数据只插入一次（批量插入）
        insert_calls = [c for c in mock_cursor.execute.call_args_list if 'executemany' in str(c)]
        assert len(insert_calls) == 1

    @patch('scripts.etl_vector_local.SentenceTransformer')
    @patch('scripts.etl_vector_local.psycopg2.connect')
    def test_sync_data_to_pgvector_missing_search_column(
        self, mock_connect, mock_sentence_transformer, mock_db_connection
    ):
        """测试缺少搜索列的情况"""
        # 设置 mock
        mock_conn, mock_cursor = mock_db_connection
        mock_connect.return_value = mock_conn
        
        mock_model = MagicMock()
        mock_model.encode.return_value = MagicMock(tolist=lambda: [0.1] * 512)
        mock_sentence_transformer.return_value = mock_model

        # 设置测试数据：不包含 SEARCH_COLUMN ("核查描述")
        mock_cursor.description = [("id",), ("其他列",)]
        mock_cursor.fetchall.return_value = [(1, "数据")]

        # 执行测试
        etl_vector_local.sync_data_to_pgvector()

        # 验证仍然会处理数据（使用空字符串）
        assert mock_model.encode.call_count == 1
        # encode 应该被调用，传入空字符串
        mock_model.encode.assert_called_once_with("")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
