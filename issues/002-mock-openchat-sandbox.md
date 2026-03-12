# 002 - mock openchat sandbox for browser flow tests

- status: open
- owner: TBD
- expected_fix_time: 2026-03-12

## 问题描述
当前直接连真实站点做端到端验证，容易受到 Cloudflare、人机验证和账号状态影响，导致排障成本高且不稳定。

需要新增一个本地伪 openchat 站点，覆盖基础交互链路：
1. Cookie 同意弹窗。
2. Cloudflare 验证弹窗。
3. 任意用户名密码登录。
4. 对话窗口输入后返回符合模板要求的 JSON。

## 复现步骤
1. 启动 mock 站点服务。
2. 打开首页，按顺序完成 cookie -> verify -> login。
3. 在聊天输入框发送任意文本。
4. 确认返回 JSON 结构符合模板要求。

## 相关文件
- src/mock_openchat/site.py
- scripts/run_mock_openchat.py
- tests/test_mock_openchat_site.py
- README.md

## 处理记录
- 2026-03-11: 新增 mock 站点初版，支持 cookie/verify/login/chat 全流程与模板 JSON 输出。

## 完成标准
1. 站点流程可稳定复现，适配现有 openchat 选择器。
2. 提供单元/集成测试覆盖关键流程。
3. README 提供本地启动与接入说明。
