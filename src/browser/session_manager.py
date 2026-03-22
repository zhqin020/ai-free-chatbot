from src.browser.session_pool import get_global_provider_session_pool, get_or_create_provider_session
from src.storage.repositories import SessionRepository
from src.models.session import SessionConfig
import threading

class SessionManager:
    """
    统一管理 session 生命周期，保证数据库与内存 pool_entry 状态同步。
    """
    def __init__(self, session_pool: object = None, session_repo: SessionRepository = None):
        self.session_pool = session_pool or get_global_provider_session_pool()
        self.session_repo = session_repo or SessionRepository()

    async def get_or_create(self, session_id: str, provider: str, chat_url: str, owner: str):
        # 1. 数据库 upsert
        config = SessionConfig(
            id=session_id,
            provider=provider,
            chat_url=chat_url,
            owner=owner,
        )
        self.session_repo.upsert(config)
        # 2. 内存 pool_entry 同步
        # get_or_create_provider_session 会自动创建 pool_entry
        page = await get_or_create_provider_session(provider, session_id, chat_url)
        return page

    def update(self, session_id: str, **kwargs):
        # 1. 更新数据库
        self.session_repo.update(session_id, **kwargs)
        # 2. 更新 pool_entry
        entry = self.session_pool.get_entry(session_id)
        if entry:
            for k, v in kwargs.items():
                setattr(entry, k, v)

    def remove(self, session_id: str):
        # 1. 移除数据库
        self.session_repo.remove(session_id)
        # 2. 移除 pool_entry
        self.session_pool.remove_entry(session_id)

    async def sync_all(self):
        """
        强制同步数据库和 pool_entry，修正不一致。
        """
        db_sessions = {row.id: row for row in self.session_repo.list()}
        pool_entries = self.session_pool.list_entries()
        # 补全 pool 中缺失的 session
        for sid, row in db_sessions.items():
            if not self.session_pool._entries.get(row.provider):
                await get_or_create_provider_session(row.provider, row.id, row.chat_url)
        # 移除 pool 中多余的 entry
        for entry in pool_entries:
            if entry.session_id not in db_sessions:
                self.session_pool.remove_entry(entry.session_id)

    def get(self, session_id: str):
        # 返回数据库和 pool_entry 信息
        db_row = self.session_repo.get(session_id)
        entry = self.session_pool.get_entry(session_id)
        return db_row, entry
