# Copilot Chat Conversation Export: 自动化提问与数据提取项目

**User:** @zhqin020
**Thread URL:** https://github.com/copilot/c/1f7635ff-e76e-4292-9556-0cfa928c6a6f

## @zhqin020

1. 创建一个项目，可以向多个已经开启的浏览器中的 AI  chat 自动提问，并且提取回复进行存储。
2. 回复的格式要求是 json 格式，比如对于法院文书，要求 ai chat 分析后，得出 包含以下几个元素的json： 案件状态（结案/正在进行）， 判决结果，各种节点的时间（立案、提交法官、庭审、判决）
3. 支持多个浏览器同时开启不同的chat 窗口，支持 openchat, gemini, grok, deepseek 等，提示用户登录并等待程序自动运行查询
4. 如果开启了多个浏览器，需要进行轮询，依次将多个问题发给不同的浏览器，等待回复后进行提取和存储，如果上一个浏览器没有回复，就切换到下一个浏览器继续发送 prompt，如果所有的浏览器都没有回复，应该等待一段时间后再次尝试
如果浏览器关闭了，应该重新启动浏览器并继续发送 prompt
5. 对话代理功能，提供api 接口，由其他程序发送对话请求并获取结果

需要提供操作界面提供以下功能：
1. 管理多个ai chat url 链接，可以增删改。可以在另一个页面打开链接，如果已经登录过，不需要再次登录
2. 测试接口，可以发送 prompt和正文，获取回复并提取结果，查看提取的结果是否正确
3. 作为服务，等待外部程序发送 prompt 和获取回复
4. 查看运行状态和日志，包括当前开启的浏览器，完成的对话数量（成功、失败的数量），按服务商分类统计，比如 openchat, gemini, grok, deepseek 等 

## Copilot

我来帮您创建一个自动化项目，用于向多个浏览器中的 AI chat 自动提问并提取结构化数据。让我先了解您的需求，然后创建相应的项目结构。

根据您的描述，这个项目需要：
1. **浏览器自动化** - 控制多个已开启的浏览器
2. **AI Chat 交互** - 自动提问
3. **回复提取** - 从 AI 回复中提取 JSON 格式的数据
4. **数据处理** - 存储和后续处理（以法院文书为例）

让我创建一个完整的项目框架：非常好！我已经为你创建了一个项目的初步规划。现在让我为你创建一个完整的 GitHub 项目结构，包括详细的 Issue 和项目框架。我已经为你初步分析了这个项目的需求和实现方案。现在让我为你在 GitHub 上创建一个标准的项目结构和相关的 Issue。

由于你还没有明确指定仓库，我先为你创建这个项目的主要 Issue，你可以选择在现有的仓库中使用，或新建一个专门的仓库。

## 项目概述：AI 自动提问与数据采集系统

这是一个面向法律文书分析的自动化工具，主要特性：

✅ **多浏览器自动控制**：支持同时操控多个已打开的浏览器标签页
✅ **智能提问发送**：自动构造标准化 prompt，批量向 AI chat 提问
✅ **结构化数据提取**：从 AI 回复中自动解析和验证 JSON 格式的结构化数据
✅ **法律文书专项**：针对法院文书设计的字段抽取（案件状态、判决结果、时间节点等）
✅ **数据存储与后处理**：支持数据本地化存储、查询、统计、导出等操作

---

## 建议的技术栈

| 层级 | 技术选择 | 说明 |
|------|--------|------|
| 浏览器控制 | Playwright / Selenium | 支持多浏览器、远程调试 |
| 后端框架 | Python (FastAPI/Flask) 或 Node.js (Express) | 提供任务管理、数据收集、存储服务 |
| 数据存储 | SQLite / PostgreSQL / 本地 JSON | 结构化存储采集的数据 |
| 前端配置界面 | Vue/React | 可选，用于配置和展示结果 |
| 浏览器插件 | Chrome Extension (Manifest V3) | 可选，用于与页面深度集成 |

---

## 核心 Issue 清单

 

### 📋 Issue 1：浏览器自动控制模块
**目标**：实现多浏览器批量操作  
实现使用 Playwright 或 Selenium 的多浏览器/多标签控制，支持：
- 自动打开/切换标签页
- 定位 AI chat 输入框并自动输入
- 监听回复并等待完全加载

### 📋 Issue 2：Prompt 构造与发送机制
**目标**：自动生成法律文书分析 prompt  
- 定义标准化 prompt 模板
- 支持批量导入法律文书
- 自动拼接文书内容并发送到 AI chat

### 📋 Issue 3：AI 回复的 JSON 提取与验证
**目标**：从自然语言回复中精准抽取 JSON  
- 实现 JSON 格式检测与容错
- 对不规范回复的自动重试或手动修正机制
- 支持针对特定字段的二次提问

### 📋 Issue 4：法律文书字段定义与数据模型
**目标**：标准化法院文书的结构化字段  
定义并实现以下字段的自动抽取：
```json
{
	"case_id": "string###",
  "case_status": "结案|正在进行",
  "judgment_result": "leave|grant|dismiss",
  "hearing": "yes|no",
  "timeline": {
    "filing_date": "YYYY-MM-DD",
    "Applicant_file_completed": "YYYY-MM-DD",
	"reply_memo": "YYYY-MM-DD",
	"Sent_to_Court": "YYYY-MM-DD",
    "judgment_date": "YYYY-MM-DD"
  }
}
```

### 📋 Issue 5：数据存储与数据库设计
**目标**：持久化存储采集数据  
- 设计数据库/文件存储方案
- 实现增删改查接口
- 支持数据导出（CSV、Excel、JSON）

### 📋 Issue 6：后处理与分析接口
**目标**：提供数据分析和统计功能  
- 案件统计分析（已结案数、胜诉率等）
- 时间线分析（各阶段用时）
- 数据校验和清洗

### 📋 Issue 7：Web 配置与结果展示界面
**目标**：提供用户界面  
- 配置批量任务
- 监控执行进度
- 查看和导出结果

## 🚀 项目初始化指南：ai-free-chatbot

### 第一步：创建 GitHub 仓库

请访问 https://github.com/new 并按以下配置：
- **Repository name**: `ai-free-chatbot`
- **Description**: `Automated AI chatbot interaction and structured data extraction tool`
- **Visibility**: Public (推荐) 或 Private
- **Initialize with**: README.md + .gitignore (Python)

### 第二步：项目结构

创建仓库后，我建议的目录结构如下：

```
ai-free-chatbot/
├── README.md
├── requirements.txt
├── .gitignore
├── .env.example
│
├── src/
│   ├── __init__.py
│   ├── config.py                    # 配置管理
│   ├── logger.py                    # 日志
│   │
│   ├── browser/                     # 浏览器自动化模块
│   │   ├── __init__.py
│   │   ├── browser_controller.py    # Playwright 浏览器控制
│   │   └── multi_browser_manager.py # 多浏览器管理
│   │
│   ├── prompt/                      # Prompt 构造模块
│   │   ├── __init__.py
│   │   ├── template.py              # Prompt 模板
│   │   └── generator.py             # Prompt 生成器
│   │
│   ├── parser/                      # 回复解析模块
│   │   ├── __init__.py
│   │   ├── response_extractor.py    # JSON 提取器
│   │   ├── json_validator.py        # JSON 验证器
│   │   └── retry_handler.py         # 失败重试处理
│   │
│   ├── models/                      # 数据模型
│   │   ├── __init__.py
│   │   ├── legal_document.py        # 法律文书模型
│   │   └── chat_result.py           # Chat 结果模型
│   │
│   ├── storage/                     # 数据存储模块
│   │   ├── __init__.py
│   │   ├── database.py              # 数据库连接
│   │   ├── json_storage.py          # JSON 文件存储
│   │   └── export.py                # 数据导出
│   │
│   ├── analyzer/                    # 数据分析模块
│   │   ├── __init__.py
│   │   ├── statistics.py            # 统计分析
│   │   └── data_processor.py        # 数据后处理
│   │
│   └── api/                         # API 接口（可选）
│       ├── __init__.py
│       └── main.py                  # FastAPI 应用
│
├── tests/
│   ├── __init__.py
│   ├── test_browser.py
│   ├── test_parser.py
│   └── test_storage.py
│
├── examples/
│   ├── sample_legal_document.txt
│   └── sample_config.yaml
│
├── docs/
│   ├── README.md
│   ├── installation.md
│   ├── usage.md
│   ��── api.md
│
└── scripts/
    ├── init_db.py
    └── batch_process.py
```

### 第三步：核心 Issue 清单（Python + Playwright）

创建好仓库后，我会为你创建以下 7 个核心 Issue：

---

## 📋 核心 Issue 列表

### **Issue #1: 浏览器自动化模块 - Playwright 多浏览器控制**
**标签**: `feature`, `browser-automation`, `高优先级`

**目标**: 实现使用 Playwright 的多浏览器批量操作

**需求**:
- [ ] 实现 `BrowserController` 类，支持 Chromium/Firefox/WebKit
- [ ] 实现 `MultiBrowserManager` 类，支持同时操控多个浏览器实例和标签页
- [ ] 支持自动登录 AI chat（如 ChatGPT、Claude、文心一言等）
- [ ] 实现消息发送和回复等待机制（可配置超时时间）
- [ ] 实现错误处理和自动重连

**技术栈**: Playwright, asyncio, Python 3.8+

**参考代码结构**:
```python
# src/browser/browser_controller.py
class BrowserController:
    async def init_browser(self, browser_type='chromium')
    async def open_page(self, url)
    async def send_message(self, page, selector, message)
    async def wait_for_response(self, page, timeout=30)
    async def close()
```

---

### **Issue #2: Prompt 构造与发送机制**
**标签**: `feature`, `prompt-engineering`, `中优先级`

**目标**: 自动生成和发送法律文书分析 prompt

**需求**:
- [ ] 定义法律文书分析的标准 prompt 模板
- [ ] 实现 `PromptGenerator` 类，支持动态拼接文书内容
- [ ] 支持批量导入法律文书（从文件、数据库或 API）
- [ ] 实现 prompt 的版本管理和 A/B 测试
- [ ] 记录所有发送的 prompt 和对应的 chat 平台

**标准 Prompt 模板示例**:
```
请分析以下法院文书，并输出标准JSON格式的结果。

必须遵循以下JSON结构：
{
	"case_id": "string###",
  "case_status": "结案|正在进行",
  "judgment_result": "leave|grant|dismiss",
  "hearing": "yes|no",
  "timeline": {
    "filing_date": "YYYY-MM-DD",
    "Applicant_file_completed": "YYYY-MM-DD",
	"reply_memo": "YYYY-MM-DD",
	"Sent_to_Court": "YYYY-MM-DD",
    "judgment_date": "YYYY-MM-DD"
  }
}

文书原文：
{document_content}
```

```
sample document content:
{
  "case_id": "IMM-3-24",
  "case_number": "IMM-3-24",
  "title": "ZOHREH MASHAYEKHI v. MCI",
  "court": "Montréal",
  "date": "2024-01-01",
  "case_type": "Immigration Matters",
  "action_type": "Immigration Matters",
  "nature_of_proceeding": "Imm - Appl. for leave & jud. review - Arising outside Canada",
  "filing_date": "2024-01-01",
  "office": "Montréal",
  "style_of_cause": "ZOHREH MASHAYEKHI v. MCI",
  "language": "French",
  "url": "https://www.fct-cf.ca/en/court-files-and-decisions/court-files",
  "html_content": "",
  "scraped_at": "2026-02-28T22:17:29.447267",
  "docket_entries": [
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 13,
      "entry_date": "2024-10-21",
      "entry_office": "Ottawa",
      "summary": "Delivery Receipt Notification Email - Decision sent to all parties placed on file on 21-OCT-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 12,
      "entry_date": "2024-10-11",
      "entry_office": "Ottawa",
      "summary": "(Final decision) Order rendered by The Honourable Mr. Justice Diner at Ottawa on 01-OCT-2024 dismissing the application for leave Decision endorsed on the record on Doc.1 received on 11-OCT-2024 Considered by the Court without personal appearance entered in J. & O. Book, volume 1238 page(s) 189 - 189 Certificate of the order sent to all parties Transmittal Letters placed on file."
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 11,
      "entry_date": "2024-06-14",
      "entry_office": "Ottawa",
      "summary": "Communication to the Court from the Registry dated 14-JUN-2024 re: Sent to Court for leave disposition. No A's Reply filed."
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 10,
      "entry_date": "2024-05-01",
      "entry_office": "Montréal",
      "summary": "Solicitor's certificate of service on behalf of Margarita Tzavelakos confirming service of Respondent's Memorandum of Argument upon Applicant by email on 01-MAY-2024 filed on 01-MAY-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 9,
      "entry_date": "2024-05-01",
      "entry_office": "Montréal",
      "summary": "Memorandum of argument on behalf of the respondent filed on 01-MAY-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 8,
      "entry_date": "2024-04-02",
      "entry_office": "Montréal",
      "summary": "Applicant's Record Number of copies received/prepared: 1 on behalf of Applicant with proof of service upon Respondent on 02-APR-2024 filed on 02-APR-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 7,
      "entry_date": "2024-02-28",
      "entry_office": "Ottawa",
      "summary": "Certified copy of the decision and reasons sent by IRCC, Case Processing Center-Ottawa on 28-FEB-2024 pursuant to Rule 9(2) Received on 28-FEB-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 6,
      "entry_date": "2024-02-21",
      "entry_office": "Ottawa",
      "summary": "Second request to IRCC, File No.: V339752907 pursuant to Rule 9 dated 21-FEB-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 5,
      "entry_date": "2024-02-05",
      "entry_office": "Ottawa",
      "summary": "First request to IRCC, File No.: V339752907 & UCI: 11-2323-8561 pursuant to Rule 9 dated 05-FEB-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 4,
      "entry_date": "2024-01-16",
      "entry_office": "Montréal",
      "summary": "Solicitor's certificate of service on behalf of Me Margarita Tzavelakos confirming service of the Notice of Appearance (doc.#2) upon Applicant and the tribunal by email on 16-JAN-2024 filed on 16-JAN-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 3,
      "entry_date": "2024-01-16",
      "entry_office": "Montréal",
      "summary": "Notice of appearance on behalf of the respondent filed on 16-JAN-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 2,
      "entry_date": "2024-01-02",
      "entry_office": "Montréal",
      "summary": "Acknowledgment of Receipt received from Respondent with respect to the ALJR (Doc. #1) placed on file on 02-JAN-2024"
    },
    {
      "id": null,
      "case_id": "IMM-3-24",
      "doc_id": 1,
      "entry_date": "2024-01-02",
      "entry_office": "Montréal",
      "summary": "Application for leave and judicial review against a decision rendered by IRCC on december 05, 2023 in the file V339752907 bearing the UCI 1123238561 refusing the applicant's application for tempoorary resident visa R133 service effected by the registry to the AGC as per covid-19 practice and direction. filed on 02-JAN-2024 Written reasons not received by the Applicant Tariff fee of $50.00 received"
    }
  ]
}
```


---

### **Issue #3: AI 回复解析与 JSON 提取验证**
**标签**: `feature`, `data-extraction`, `高优先级`

**目标**: 从 AI 回复中精准抽取并验证 JSON 数据

**需求**:
- [ ] 实现 `ResponseExtractor` 类，支持从自然语言中提取 JSON 块
- [ ] 实现 `JSONValidator` 类，验证提取的 JSON 是否符合预定义的 schema
- [ ] 实现失败重试机制（自动重新发送提问，要求 AI 重新输出）
- [ ] 支持部分字段缺失的容错处理
- [ ] 记录所有失败的提问和重试过程

**Pydantic Schema 示例**:
```python
from pydantic import BaseModel
from datetime import date
from enum import Enum

class CaseStatus(str, Enum):
    CLOSED = "结案"
    ONGOING = "正在进行"

class CaseTimeline(BaseModel):
    filing_date: date
    judge_assignment_date: date
    trial_date: date
    judgment_date: date

class LegalDocumentAnalysis(BaseModel):
    case_status: CaseStatus
    judgment_result: str
    timeline: CaseTimeline
```

---

### **Issue #4: 法律文书数据模型定义**
**标签**: `feature`, `data-model`, `中优先级`

**目标**: 标准化法律文书的结构化字段和数据模型

**需求**:
- [ ] 定义 `LegalDocument` 模型（存储原始文书信息）
- [ ] 定义 `CaseAnalysisResult` 模型（存储 AI 分析结果）
- [ ] 支持扩展字段（如律师信息、诉讼请求、争议焦点等）
- [ ] 实现模型的序列化���反序列化
- [ ] 提供模型验证和错误提示

**字段扩展建议**:
- 原告信息（名称、身份）
- 被告信息
- 审理法院信息
- 案件类型
- 诉讼请求
- 争议焦点

---

### **Issue #5: 数据存储与数据库设计**
**标签**: `feature`, `database`, `中优先级`

**目标**: 实现多种存储方案（JSON 文件、SQLite、PostgreSQL）

**需求**:
- [ ] 实现 `JSONStorage` 类，支持本地 JSON 文件存储
- [ ] 实现 `DatabaseStorage` 类，支持 SQLite 和 PostgreSQL
- [ ] 设计数据库 schema（表结构、索引、约束）
- [ ] 实现增删改查 (CRUD) 接口
- [ ] 实现数据迁移脚本
- [ ] 支持事务处理和异常回滚

**数据库表设计**:
```sql
-- legal_documents 表
CREATE TABLE legal_documents (
    id INTEGER PRIMARY KEY,
    document_name VARCHAR(255),
    document_content TEXT,
    upload_date TIMESTAMP,
    ai_platform VARCHAR(50),
    created_at TIMESTAMP
);

-- case_results 表
CREATE TABLE case_results (
    id INTEGER PRIMARY KEY,
    document_id INTEGER,
    case_status VARCHAR(20),
    judgment_result TEXT,
    filing_date DATE,
    judge_assignment_date DATE,
    trial_date DATE,
    judgment_date DATE,
    raw_response TEXT,
    extracted_at TIMESTAMP,
    FOREIGN KEY (document_id) REFERENCES legal_documents(id)
);
```

---

### **Issue #6: 数据分析与后处理**
**标签**: `feature`, `analytics`, `低优先级`

**目标**: 提供数据统计分析和后续处理功能

**需求**:
- [ ] 实现 `StatisticsAnalyzer` 类，支持：
  - 案件统计（总数、结案数、进行中数）
  - 胜诉率、败诉率统计
  - 各阶段平均用时计算
  - 判决结果分类统计
- [ ] 实现数据校验和清洗（如日期格式规范化）
- [ ] 生成统计报表（CSV、JSON）
- [ ] 支持按时间段、案件类型等维度的数据切片

**输出报表示例**:
```json
{
  "summary": {
    "total_cases": 100,
    "closed_cases": 80,
    "ongoing_cases": 20,
    "win_rate": 0.65
  },
  "timeline_analysis": {
    "avg_filing_to_judgment_days": 180
  }
}
```

---

### **Issue #7: Web API 与配置界面（可选）**
**标签**: `feature`, `api`, `低优先级`

**目标**: 提供 FastAPI 后端和配置界面

**需求**:
- [ ] 使用 FastAPI 构建 REST API
- [ ] 实现以下端点：
  - `POST /api/tasks` - 创建新的批处理任务
  - `GET /api/tasks/{task_id}` - 查询任务状态
  - `GET /api/results` - 获取分析结果列表
  - `POST /api/export` - 导出数据
- [ ] 实现任务队列和异步处理
- [ ] 支持 WebSocket 实时推送进度
- [ ] 提供简单的 Web UI（可选，使用 Streamlit 或 Vue）

---

## 📦 项目依赖列表 (requirements.txt)

```txt
# 浏览器自动化
playwright==1.40.0

# Web 框架（可选）
fastapi==0.104.1
uvicorn==0.24.0

# 数据库
sqlalchemy==2.0.23
psycopg2-binary==2.9.9

# 数据验证
pydantic==2.5.0

# 异步处理
aiohttp==3.9.1

# 日志
python-logging-loki==0.3.2

# 工具库
python-dotenv==1.0.0
click==8.1.7

# 测试
pytest==7.4.3
pytest-asyncio==0.21.1
```

---

## ✅ 后续步骤

1. **创建仓库** (zhqin020/ai-free-chatbot)
2. **初始化项目结构**（我可以帮你生成）
3. **创建上述 7 个 Issue**
4. **逐个开发模块**，从 Issue #1 开始
5. **编写单元测试和集成测试**
6. **生成完整文档**

---

 
