# -*- coding: utf-8 -*-
"""
数据库表：pool_entries
用于跨进程共享 browser session pool 的页面注册与状态。
"""
from sqlalchemy import Column, String, DateTime, Enum, Text, func
from src.storage.database import Base
import enum

class PageStatus(str, enum.Enum):
    ACTIVE = "active"
    CLOSED = "closed"
    UNKNOWN = "unknown"

class PoolEntryORM(Base):
    __tablename__ = "pool_entries"
    provider = Column(String(64), primary_key=True)
    session_id = Column(String(128), primary_key=True)
    url = Column(Text, nullable=False)
    page_status = Column(Enum(PageStatus), default=PageStatus.ACTIVE, nullable=False)
    last_seen = Column(DateTime, default=func.now(), onupdate=func.now(), nullable=False)
    extra_info = Column(Text, nullable=True)

    def __repr__(self):
        return f"<PoolEntryORM(provider={self.provider}, session_id={self.session_id}, url={self.url}, status={self.page_status}, last_seen={self.last_seen})>"
