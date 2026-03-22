# Fix src/browser/worker.py SyntaxError & Restructure Plan

## Status: [IN PROGRESS] 

## Steps:
- [x] Step 1: Edit src/browser/worker.py - Restructure PooledProviderTaskProcessor: fix __init__, complete standalone process(), single top-level run_once() (remove nested duplicates), fix _inspect_adapter_page_state indentation/try-except. **DONE**
- [x] Step 2: Verify syntax: run `python3 -m py_compile src/browser/worker.py` **PENDING CONFIRM**
- [ ] Step 3: Test app startup: `python3 -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000` (expect clean logs, browser_controller starts)
- [ ] Step 4: Health/smoke test: curl localhost:8000/health or visit admin UI; verify no import errors.
- [ ] Step 5: Update TODO.md as [COMPLETED]

**Goal:** Enable FastAPI server startup by fixing SyntaxError: expected 'except' or 'finally' block in worker.py.

