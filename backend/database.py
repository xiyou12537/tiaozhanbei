"""
数据库配置 —— SQLite + SQLAlchemy。

为本地单机使用设计，数据库文件存储在项目根目录下的 data/ 文件夹中。
"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base
import os

# 数据库文件路径：项目根目录/data/partitioning.db
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(ROOT_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DATABASE_URL = f"sqlite:///{os.path.join(DATA_DIR, 'partitioning.db')}"

# SQLAlchemy 引擎（check_same_thread=False 是 SQLite 多线程需要的）
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False}, echo=False)

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 基类
Base = declarative_base()


def get_db():
    """FastAPI 依赖注入：每次请求获取一个数据库会话，请求结束后自动关闭。"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """创建所有数据库表（如果不存在）。"""
    Base.metadata.create_all(bind=engine)
