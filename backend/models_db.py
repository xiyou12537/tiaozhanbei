"""
数据库 ORM 模型 —— 用户、电路、任务、映射结果。

四个表：
  - User: 注册用户
  - Circuit: 上传的 QASM 电路
  - Task: 分区计算任务
  - Mapping: 芯片拓扑映射结果
"""

import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import relationship
from .database import Base


class User(Base):
    """用户表"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(200), nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    # 关联
    circuits = relationship("Circuit", back_populates="owner", cascade="all, delete-orphan")
    tasks = relationship("Task", back_populates="owner", cascade="all, delete-orphan")
    mappings = relationship("Mapping", back_populates="owner", cascade="all, delete-orphan")
    chat_messages = relationship("ChatMessage", back_populates="owner", cascade="all, delete-orphan")


class Circuit(Base):
    """电路表 —— 存储用户上传的 QASM 电路"""
    __tablename__ = "circuits"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    name = Column(String(200), default="未命名电路")
    qasm_content = Column(Text, nullable=False)
    num_qubits = Column(Integer, default=0)
    total_gates = Column(Integer, default=0)
    multi_qubit_gates = Column(Integer, default=0)
    qubit_list = Column(JSON, default=[])
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="circuits")
    tasks = relationship("Task", back_populates="circuit", cascade="all, delete-orphan")


class Task(Base):
    """任务表 —— 记录每次分区计算的状态和结果"""
    __tablename__ = "tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    circuit_id = Column(Integer, ForeignKey("circuits.id"), nullable=False)
    task_id = Column(String(20), unique=True, nullable=False, index=True)
    status = Column(String(20), default="queued")  # queued / running / completed / failed
    params_json = Column(JSON, default={})
    result_json = Column(JSON, default=None)
    error_message = Column(Text, default=None)
    elapsed_seconds = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="tasks")
    circuit = relationship("Circuit", back_populates="tasks")


class Mapping(Base):
    """映射表 —— 记录芯片拓扑映射结果"""
    __tablename__ = "mappings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    task_id = Column(Integer, ForeignKey("tasks.id"), nullable=False)
    topology_name = Column(String(100), default="自定义拓扑")
    topology_json = Column(JSON, default=[])
    mapping_json = Column(JSON, default={})
    subgraph_cost = Column(Float, default=0.0)
    epr_cost = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="mappings")


class ChatMessage(Base):
    """聊天消息表 —— 记录 AI 对话历史"""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # "user" or "assistant"
    content = Column(Text, nullable=False)
    created_at = Column(DateTime, default=datetime.datetime.utcnow)

    owner = relationship("User", back_populates="chat_messages")
