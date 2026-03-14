# 004-auto-script-gen.md

## 标题
管理后台支持自动生成 make_chat_request_payload 脚本

## 问题描述

为提升自定义提取任务的效率，需在管理后台增加“自动脚本生成”功能，支持用户通过界面输入 prompt 及目标 JSON 模板（ret_json），自动生成 Python 脚本函数（如 make_chat_request_payload），便于快速集成到 examples/example_test_extract_api.py 等脚本中。

### 需求细节
1. 支持输入 prompt（提取指令）。
2. 支持可视化编辑 JSON 模板（ret_json）：
   - 字段增删、类型选择、说明、示例填写
   - 支持嵌套结构
   - 支持直接粘贴/填写完整 JSON 字符串
3. 自动生成 Python 函数代码，包含 prompt 和 ret_json，格式与 examples/example_test_extract_api.py 中 make_chat_request_payload 一致。
4. 支持一键复制/下载生成的代码。

## 实施计划

### 1. 前端
- 新增“自动脚本生成”入口，页面表单支持 prompt 输入。
- 提供 JSON 模板可视化编辑器（字段增删、类型、说明、示例、嵌套）。
- 支持直接粘贴/编辑 JSON 字符串。
- 生成 Python 函数代码并展示，支持一键复制/下载。

### 2. 后端
- 如需后端辅助代码生成，提供 API 接口（可选，前端也可直接生成）。
- 代码生成逻辑复用 examples/example_test_extract_api.py 的模板。

### 3. 脚本模板
- 规范 make_chat_request_payload 代码模板，便于后续维护和扩展。

### 4. 测试与验收
- 前端交互测试，确保生成代码可用。
- 生成的函数可直接集成到 examples/example_test_extract_api.py 并通过端到端测试。

---

如有补充需求请在本 issue 下追加。