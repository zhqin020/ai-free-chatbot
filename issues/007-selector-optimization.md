# 007 - Optimize Chat Page Selector Extraction

**Description**:
Currently, chat page selectors are identified via hardcoded candidate templates and saved continuously into a single `ready_selectors_json` string. This approach is inaccurate (especially for the reply area) and hard to maintain.

**Plan**:
1. When the user clicks "Mark Ready" (or "Identify Selectors"), the worker thread automatically sends a simple "hello" message if the input box can be found.
2. The worker retrieves the page DOM (simplified to remove excessive styling/scripts).
3. The worker sends the minimized DOM to the internal proxy LLM (via `POST /v1/chat/completions`) and extracts 4 key selectors.
4. The selectors are separated into distinct fields for independent maintenance, and the simplified DOM is stored in `dom_sample`.

**Responsible**:
AI Assistant

**Expected Fix Time**:
1-2 hours

**Status**:
closed

**Resolution Summary**:
Implemented LLM-powered selector identification using the system's internal task mechanism. 
1. The worker thread now extracts a minimized DOM after sending a test "hello" message.
2. An internal Task is created and assigned to another READY provider (built-in).
3. The response is parsed to extract `new_chat_selector`, `input_selector`, `send_button_selector`, and `reply_selector`.
4. These are stored in dedicated database fields for better maintainability.
5. Added `dom_sample` field for validation and manual override support in Admin UI.
