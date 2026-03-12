# API Examples

External programs can reuse these examples to call the service APIs.

## Prerequisites

1. Start API service at http://127.0.0.1:8000.
2. Optional: export API_BASE_URL if your service is not on 8000.
3. Optional: export API_TOKEN if your gateway enforces auth header.

## Environment

```bash
export API_BASE_URL=http://127.0.0.1:8000
export API_TOKEN=
```

## Run examples

```bash
python -m examples.example_sessions_api
python -m examples.example_tasks_api
python -m examples.example_test_extract_api
python -m examples.example_metrics_logs_api
```

## Files

1. client_common.py: shared HTTP client and pretty printer.
2. example_sessions_api.py: sessions CRUD and actions.
3. example_tasks_api.py: task create and query.
4. example_test_extract_api.py: extract API success/failure examples.
5. example_metrics_logs_api.py: metrics and logs query examples.
