import pytest
import threading
import asyncio
import os
from datetime import UTC, datetime
from src.models.task import TaskCreate, TaskStatus
from src.storage.repositories import TaskRepository, SessionRepository
from src.browser.session_pool import get_global_provider_session_pool
from src.browser.worker import PooledProviderTaskProcessor
from src.storage.database import init_db

class DummyAdapter:
    async def run(self, page, decision):
        return type('Result', (), {'ok': True, 'raw_response': f'ok-{decision.task_id}'})()

class DummyPage:
    def is_closed(self):
        return False

class DummyController:
    async def start(self, *a, **k): pass
    async def open_page(self, url): return DummyPage()
    async def is_page_healthy(self, page, required_selector=None): return True
    async def close(self): pass

def run_worker_create_and_process(pool, task_repo, prompt, doc, result_dict, cross_owner=None):
    import threading as th
    thread_id = str(th.get_ident())
    # owner 可指定为 cross_owner 用于交叉测试
    owner = cross_owner if cross_owner else thread_id
    t = TaskCreate(prompt=prompt, document_text=doc, owner=owner)
    row = task_repo.create(t)
    processor = PooledProviderTaskProcessor(
        provider="test",
        adapter=DummyAdapter(),
        session_pool=pool,
        task_repo=task_repo,
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(processor.run_once())
    task = task_repo.get(row.id)
    result_dict['status'] = task.status
    result_dict['id'] = row.id

def run_worker_process_only(pool, task_repo, task_id, result_dict):
    processor = PooledProviderTaskProcessor(
        provider="test",
        adapter=DummyAdapter(),
        session_pool=pool,
        task_repo=task_repo,
    )
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    loop.run_until_complete(processor.run_once())
    task = task_repo.get(task_id)
    result_dict['status'] = task.status

def test_task_owner_thread_binding_and_worker_isolation(tmp_path):
    # 使用独立sqlite测试库，避免表结构不一致
    db_path = tmp_path / "test_task_owner_thread_binding.db"
    os.environ["DB_URL"] = f"sqlite:///{db_path}"
    init_db()
    pool = get_global_provider_session_pool()
    task_repo = TaskRepository()
    session_repo = SessionRepository()

    # worker 1: 创建任务并处理
    result1 = {}
    t1 = threading.Thread(target=run_worker_create_and_process, args=(pool, task_repo, "p1", "d1", result1))
    t1.start()
    t1.join()
    assert result1['status'] != TaskStatus.PENDING

    # worker 2: 创建任务并处理
    result2 = {}
    t2 = threading.Thread(target=run_worker_create_and_process, args=(pool, task_repo, "p2", "d2", result2))
    t2.start()
    t2.join()
    assert result2['status'] != TaskStatus.PENDING

    # 交叉运行，不能处理对方任务
    # 先用 worker 1 创建任务
    cross_result = {}
    t3 = threading.Thread(target=run_worker_create_and_process, args=(pool, task_repo, "p3", "d3", cross_result))
    t3.start()
    t3.join()
    # 用 worker 2 处理 worker 1 的任务（owner 不同）
    cross_check = {}
    t4 = threading.Thread(target=run_worker_process_only, args=(pool, task_repo, cross_result['id'], cross_check))
    t4.start()
    t4.join()
    assert cross_check['status'] == TaskStatus.PENDING

    
