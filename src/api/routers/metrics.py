from __future__ import annotations

from pydantic import BaseModel

from fastapi import APIRouter
from src.analyzer import StatisticsAnalyzer

router = APIRouter(prefix="/api/metrics", tags=["metrics"])
analyzer = StatisticsAnalyzer()


class SummaryMetricsResponse(BaseModel):
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


class ProviderMetricsResponse(BaseModel):
	provider: str
	total_tasks: int
	completed_tasks: int
	failed_tasks: int
	success_rate: float
	timeout_count: int
	avg_latency_ms: int


@router.get("/summary", response_model=SummaryMetricsResponse)
def get_summary_metrics() -> SummaryMetricsResponse:
	summary = analyzer.get_summary_metrics()
	return SummaryMetricsResponse(
		total_tasks=summary.total_tasks,
		pending_tasks=summary.pending_tasks,
		dispatched_tasks=summary.dispatched_tasks,
		extracting_tasks=summary.extracting_tasks,
		completed_tasks=summary.completed_tasks,
		failed_tasks=summary.failed_tasks,
		success_rate=summary.success_rate,
		total_attempts=summary.total_attempts,
		timeout_count=summary.timeout_count,
		avg_latency_ms=summary.avg_latency_ms,
		schema_valid_count=summary.schema_valid_count,
		schema_invalid_count=summary.schema_invalid_count,
	)


@router.get("/providers", response_model=list[ProviderMetricsResponse])
def get_provider_metrics() -> list[ProviderMetricsResponse]:
	rows = analyzer.get_provider_metrics()
	return [
		ProviderMetricsResponse(
			provider=row.provider,
			total_tasks=row.total_tasks,
			completed_tasks=row.completed_tasks,
			failed_tasks=row.failed_tasks,
			success_rate=row.success_rate,
			timeout_count=row.timeout_count,
			avg_latency_ms=row.avg_latency_ms,
		)
		for row in rows
	]
