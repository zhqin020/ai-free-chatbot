# 自动脚本生成页面 UI 结构与交互设计

## 1. 页面结构

- 顶部标题栏：自动脚本生成
- 步骤区：
  1. Prompt 输入区
  2. JSON 模板可视化编辑区
  3. 代码预览与导出区

---

## 2. 详细分区说明

### 1. Prompt 输入区
- 单行/多行文本框，支持输入提取指令
- 示例占位符：如“请提取案件状态、判决结果和关键时间节点为 JSON...”

### 2. JSON 模板可视化编辑区
- 字段列表（表格/树形结构）：
  - 字段名
  - 数据类型（string/number/boolean/object/array）
  - 说明（可选）
  - 示例值（可选）
  - 操作（添加/删除/嵌套）
- 支持嵌套结构（object/array）
- 支持直接粘贴/编辑完整 JSON 字符串，自动解析为可视化结构
- 支持导出为 JSON 字符串

### 3. 代码预览与导出区
- 实时展示生成的 make_chat_request_payload Python 函数代码
- 支持一键复制/下载
- 可选：高亮显示 prompt 和 ret_json 部分

---

## 3. 交互流程
1. 用户输入 prompt
2. 用户通过可视化方式编辑 JSON 模板，或直接粘贴 JSON
3. 页面自动生成并展示 Python 函数代码
4. 用户可复制/下载代码

---

## 4. UI 组件建议
- Prompt 输入：el-input / textarea
- JSON 编辑：el-table + el-tree 或第三方 JSON Editor（如 jsoneditor）
- 代码高亮：monaco-editor / highlight.js
- 操作按钮：el-button

---

如需原型图可进一步补充。