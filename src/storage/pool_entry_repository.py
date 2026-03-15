# -*- coding: utf-8 -*-
"""
PoolEntryRepository: 提供 pool_entries 表的增删查改接口
"""
from datetime import datetime
from sqlalchemy.orm import Session
from src.models.pool_entry import PoolEntryORM, PageStatus

class PoolEntryRepository:
    def __init__(self, db: Session):
        self.db = db

    def upsert(self, provider: str, session_id: str, url: str, page_status: PageStatus = PageStatus.ACTIVE, extra_info: str = None):
        entry = self.db.query(PoolEntryORM).filter_by(provider=provider, session_id=session_id).first()
        now = datetime.utcnow()
        if entry:
            entry.url = url
            entry.page_status = page_status
            entry.last_seen = now
            if extra_info is not None:
                entry.extra_info = extra_info
        else:
            entry = PoolEntryORM(
                provider=provider,
                session_id=session_id,
                url=url,
                page_status=page_status,
                last_seen=now,
                extra_info=extra_info,
            )
            self.db.add(entry)
        self.db.commit()
        return entry

    def get(self, provider: str, session_id: str):
        return self.db.query(PoolEntryORM).filter_by(provider=provider, session_id=session_id).first()

    def list_active(self):
        return self.db.query(PoolEntryORM).filter_by(page_status=PageStatus.ACTIVE).all()

    def update_status(self, provider: str, session_id: str, page_status: PageStatus):
        entry = self.get(provider, session_id)
        if entry:
            entry.page_status = page_status
            entry.last_seen = datetime.utcnow()
            self.db.commit()
        return entry

    def delete(self, provider: str, session_id: str):
        entry = self.get(provider, session_id)
        if entry:
            self.db.delete(entry)
            self.db.commit()
        return entry
