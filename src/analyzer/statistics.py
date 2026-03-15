from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass

from src.models.task import TaskStatus
from src.storage.database import ExtractedResultORM, TaskAttemptORM, TaskORM, session_scope


@dataclass
class SummaryMetrics:
    total_tasks: int
    pending_tasks: int
    dispatched_tasks: int
    extracting_tasks: int
    completed_tasks: int
    failed_tasks: int
    success_rate: float
    total_attempts: int
    timeout_count: int
    avg_latency_ms: int
    schema_valid_count: int
    schema_invalid_count: int


@dataclass
class ProviderMetrics:
    provider: str
    total_tasks: int
    completed_tasks: int
    failed_tasks: int
    success_rate: float
    timeout_count: int
    avg_latency_ms: int


class StatisticsAnalyzer:
    def get_summary_metrics(self) -> SummaryMetrics:
        with session_scope() as session:
            tasks = session.query(TaskORM).all()
            attempts = session.query(TaskAttemptORM).all()
            extracted = session.query(ExtractedResultORM).all()

        total_tasks = len(tasks)
        pending = sum(1 for t in tasks if t.status == TaskStatus.PENDING)
        dispatched = sum(1 for t in tasks if t.status == TaskStatus.DISPATCHED)
        extracting = sum(1 for t in tasks if t.status == TaskStatus.EXTRACTING)
        completed = sum(1 for t in tasks if t.status == TaskStatus.COMPLETED)
        failed = sum(1 for t in tasks if t.status == TaskStatus.FAILED)

        total_attempts = len(attempts)
        timeout_count = sum(
            1
            for a in attempts
            if (a.error_message or "").lower().find("timeout") >= 0
        )

        latency_values = [a.latency_ms for a in attempts if a.latency_ms is not None]
        avg_latency_ms = int(sum(latency_values) / len(latency_values)) if latency_values else 0

        schema_valid_count = sum(1 for r in extracted if r.valid_schema)
        schema_invalid_count = sum(1 for r in extracted if not r.valid_schema)
        success_rate = (completed / total_tasks * 100.0) if total_tasks else 0.0

        return SummaryMetrics(
            total_tasks=total_tasks,
            pending_tasks=pending,
            dispatched_tasks=dispatched,
            extracting_tasks=extracting,
            completed_tasks=completed,
            failed_tasks=failed,
            success_rate=round(success_rate, 2),
            total_attempts=total_attempts,
            timeout_count=timeout_count,
            avg_latency_ms=avg_latency_ms,
            schema_valid_count=schema_valid_count,
            schema_invalid_count=schema_invalid_count,
        )

    def get_provider_metrics(self) -> list[ProviderMetrics]:
        with session_scope() as session:
            tasks = session.query(TaskORM).all()
            attempts = session.query(TaskAttemptORM).all()

        task_by_provider: dict[str, list[TaskORM]] = defaultdict(list)
        for task in tasks:
            provider_key = task.provider_hint if task.provider_hint is not None else "unknown"
            task_by_provider[provider_key].append(task)

        attempts_by_task: dict[str, list[TaskAttemptORM]] = defaultdict(list)
        for attempt in attempts:
            attempts_by_task[attempt.task_id].append(attempt)

        rows: list[ProviderMetrics] = []
        for provider, provider_tasks in sorted(task_by_provider.items(), key=lambda x: x[0]):
            total = len(provider_tasks)
            completed = sum(1 for t in provider_tasks if t.status == TaskStatus.COMPLETED)
            failed = sum(1 for t in provider_tasks if t.status == TaskStatus.FAILED)

            provider_attempts: list[TaskAttemptORM] = []
            for t in provider_tasks:
                provider_attempts.extend(attempts_by_task.get(t.id, []))

            timeout_count = sum(
                1
                for a in provider_attempts
                if (a.error_message or "").lower().find("timeout") >= 0
            )
            latency_values = [a.latency_ms for a in provider_attempts if a.latency_ms is not None]
            avg_latency_ms = int(sum(latency_values) / len(latency_values)) if latency_values else 0
            success_rate = (completed / total * 100.0) if total else 0.0

            rows.append(
                ProviderMetrics(
                    provider=provider,
                    total_tasks=total,
                    completed_tasks=completed,
                    failed_tasks=failed,
                    success_rate=round(success_rate, 2),
                    timeout_count=timeout_count,
                    avg_latency_ms=avg_latency_ms,
                )
            )

        return rows
