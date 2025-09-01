"""Test configuration - simple approach."""

import os

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine, text


# 設定測試環境變數
os.environ["POSTGRES_DB"] = "ticketing_test_db"

from src.main import app
from src.shared.database import Base


# 用同步引擎只做資料清理
SYNC_DATABASE_URL = "postgresql://py_arch_lab:py_arch_lab@localhost:5432/ticketing_test_db"
sync_engine = create_engine(SYNC_DATABASE_URL)

# 確保表存在
Base.metadata.create_all(bind=sync_engine)


@pytest.fixture(autouse=True)
def clean_database():
    """每個測試前後清理資料庫 - 自動清理所有表。"""
    with sync_engine.begin() as conn:
        # 取得所有表名（排除 alembic_version）
        result = conn.execute(text("""
            SELECT tablename FROM pg_tables 
            WHERE schemaname = 'public'
            AND tablename != 'alembic_version'
        """))
        tables = [row[0] for row in result]
        
        # 使用 TRUNCATE CASCADE 清理所有表（更快且會處理外鍵）
        if tables:
            conn.execute(text(f"TRUNCATE {', '.join(tables)} CASCADE"))
    
    yield


@pytest.fixture(scope="session")
def client():
    """提供測試客戶端 - session scope 避免重建。"""
    with TestClient(app) as client:
        yield client
