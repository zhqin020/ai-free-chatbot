# 006-provider-selector-auto-extract.md

## 问题描述

当前会话管理的“标记就绪”按钮仅修改会话状态，未自动提取和保存 chat 页面特征（如输入框、发送按钮、响应区域等 selector）。导致 provider adapter 无法自动检测 chat_ready，需手动配置 selectors，自动化适配效率低。

## 期望方案

- 扩展“标记就绪”功能：
  1. 操作者点击“标记就绪”后，后端自动分析当前页面，提取典型 chat 元素的 selector（如输入框、发送按钮、响应区）。
  2. 将 selector 信息与 provider 关联存储（如 provider_config 表、json 文件或 adapter 类）。
  3. 后续 provider adapter 读取这些 selector，实现自动化 chat_ready 检测。

## 解决方案

1. 在“标记就绪”API处理函数中，获取当前会话的 browser page。
2. 自动遍历页面，定位典型 chat 元素（input/textarea、button、消息区等），提取 selector。
3. 将 selector 信息写入 provider 配置（如数据库、json 文件或 adapter 类）。
4. adapter 读取这些 selector，实现自动检测。

## 处理计划
- [ ] 扩展“标记就绪”API，支持自动提取并保存 selector。
- [ ] 实现页面元素自动分析与 selector 提取逻辑。
- [ ] 设计 provider selector 配置存储方案。
- [ ] 修改 provider adapter 支持动态读取 selector。
- [ ] 测试全流程。

## 相关文件
- src/api/routers/sessions.py
- src/browser/providers/
- provider 配置存储方案（如数据库、json、py 文件）

## 负责人
- watson

## 期望修复时间
- 2026-03-16

---

如需详细设计或代码实现，请见后续 issue 更新。
