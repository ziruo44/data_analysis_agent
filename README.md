# 数据分析师智能体 (Data Analyst Agent)

**版本: v0.1.0** | 基于 LangGraph 的智能数据分析系统，通过 REST API + Web 前端提供交互式数据分析服务。系统自动完成数据清洗、LLM 代码生成、安全审查、沙盒执行、自愈重试、多模态图表解读，最终生成 Markdown 格式的分析报告并转换为 HTML 前端展示。

---

## 目录

- [版本历史](#版本历史)
- [核心架构](#核心架构)
- [工作流节点详解](#工作流节点详解)
- [条件边与自愈循环](#条件边与自愈循环)
- [AgentState 状态结构](#agentstate-状态结构)
- [技术栈](#技术栈)
- [项目结构](#项目结构)
- [功能详解](#功能详解)
- [API 接口文档](#api-接口文档)
- [安装与运行](#安装与运行)
- [输出报告结构](#输出报告结构)
- [开发指南](#开发指南)

---

## 版本历史

| 版本 | 日期 | 说明 |
|------|------|------|
| v0.1.0 | 2026-04 | 初始版本：完整 7 节点工作流 + FastAPI + 前端界面 + 检查点持久化 + 自愈重试 |

---

## 核心架构

### 整体架构图

```
┌─────────────┐    ┌───────────┐    ┌──────────────┐
│  前端页面    │◄──►│ FastAPI   │◄──►│  LangGraph   │
│ (HTML+JS)   │    │ REST API  │    │  状态机      │
└─────────────┘    └───────────┘    └──────┬───────┘
                                           │
                    ┌──────────────────────┼──────────────────────┐
                    ▼                      ▼                      ▼
             ┌───────────┐         ┌──────────────┐      ┌──────────────┐
             │ SQLite    │         │ LLM (通义千问)│      │ 沙盒执行环境 │
             │ 检查点DB  │         │ + 多模态视觉 │      │ exec + 捕获  │
             └───────────┘         └──────────────┘      └──────────────┘
```

### 工作流节点流程

```
START → (检查 cleaned_file_path)
  ├── 有 → 跳过 data_clean → code_generator → sanity_checker → code_executor → self_reviewer → image_analysis → report_output → END
  └── 无 → data_clean → code_generator → sanity_checker → code_executor → self_reviewer → image_analysis → report_output → END
  
                ↑                            ↑                            │
                │        ┌───────────────────┘                            │
                │        │  (review_feedback: unsafe)                     │
                └────────┤                                                │
                         │            (review_feedback: error)            │
                         └────────────────────────────────────────────────┘
```

**入口智能路由**：当 `cleaned_file_path` 已存在时跳过 `data_clean` 节点，直接进入 `code_generator`，实现多轮会话的增量分析而无需重复清洗。

### 模块分层

| 层级 | 目录 | 职责 |
|------|------|------|
| **接口层** | `api/`、`main.py` | FastAPI + REST API + 静态文件服务 |
| **前端层** | `static/` | Web 聊天界面 (HTML + JS) |
| **工作流层** | `agent/graph.py`、`agent/nodes.py` | LangGraph 状态机定义与节点实现 |
| **LLM 层** | `agent/llm.py` | 大模型客户端封装（文本 + 多模态视觉） |
| **工具层** | `tools/` | 数据清洗、代码执行、状态检查等核心工具 |
| **持久化层** | `memory/` | SQLite 检查点持久化与会话管理 |
| **基础设施** | `utils/` | 日志、路径解析、字体配置、提示词加载等 |

---

## 工作流节点详解

系统由 7 个节点组成，每个节点负责一个独立的数据处理阶段。

### 1. data_clean (数据清洗节点)

调用 `DataCleaner` 类对原始 CSV/Excel 数据执行全自动清洗管道：

| 步骤 | 方法 | 说明 |
|------|------|------|
| 数据探查 | `profile()` | 生成数据画像：shape、列名、类型、缺失值统计、重复行数 |
| 高缺失列删除 | `auto_clean(missing_threshold=0.8)` | 缺失率 > 80% 的列自动删除 |
| 数值列填充 | 中位数填充 | 抗极端值干扰，比均值更稳健 |
| 文本列填充 | 众数填充 | 取出现频率最高的值 |
| 重复行去除 | `drop_duplicates()` | 删除完全重复的行 |
| 重复列去除 | `drop_duplicated_columns()` | 删除列名重复的列 |
| 文本标准化 | `standardize_text_columns()` | 去除首尾空格、统一大写 |
| 保存结果 | `save_clean_data()` | 支持 CSV / Excel 格式输出 |

**流式事件阶段**：`初始化` → `分析数据` → `清洗数据` → `保存结果` → `完成`

### 2. code_generator (代码生成节点)

核心代码生成节点，通过 LLM 流式生成 Python 数据分析代码：

- **首次生成**：加载 `data_analysis_prompt.txt`，注入 `{user_prompt}` 和 `{data_profile}`，调用 `llm.stream()` 流式输出代码
- **自愈重试**：加载 `code_healing_prompt.txt`，注入 `{old_code}` + `{execution_log}` + `{feedback}`，生成修复后的完整代码
- **熔断保护**：`retry_count >= 3` 时终止并返回致命错误
- **代码保存**：生成的代码按 `{数据文件名}_generated_code.py` 格式保存到输出目录
- **流式输出**：LLM 的 token 逐块在终端实时显示，同时通过 writer 推送 WebSocket 事件

**流式事件阶段**：`准备提示词`/`自愈模式` → `LLM生成中` → `保存代码` → `完成`

### 3. sanity_checker (安全审查节点)

对 LLM 生成的代码进行静态安全扫描，拦截危险操作：

| 危险关键字 | 拦截动作 |
|-----------|---------|
| `os.remove` | 设置 `review_feedback = "unsafe"` |
| `shutil.rmtree` | 设置 `review_feedback = "unsafe"` |
| `os.system` | 设置 `review_feedback = "unsafe"` |
| `subprocess` | 设置 `review_feedback = "unsafe"` |

通过后设置 `review_feedback = "safe"`，路由到执行节点。

**流式事件阶段**：`扫描代码` → `危险!` / `通过`

### 4. code_executor (代码执行节点)

在隔离的沙盒环境中执行 LLM 生成的代码：

- **预注入变量**：`pd`, `plt`, `os`, `data_file`, `output_dir`
- **环境隔离**：独立的 `exec_globals` 字典，避免污染全局命名空间
- **stdout 捕获**：通过 `contextlib.redirect_stdout` 捕获所有 `print()` 输出
- **plt.show() 拦截**：替换为 `logging.warning` 并重定向到 `plt.savefig()`，防止服务器在无头环境阻塞
- **图表文件检测**：对比执行前后 `output_dir` 中的文件变化，自动收集新生成的 `.png` / `.jpg` / `.html` 文件
- **中文字体**：执行前自动调用 `setup_chinese_font()` 配置 matplotlib 中文显示

**流式事件阶段**：`准备执行` → `执行中` → `完成`

### 5. self_reviewer (自我审查节点)

检测代码执行结果，决定工作流路由：

- **错误检测**：在 `execution_log` 中搜索 `Traceback` 或 `执行代码时出错` 关键字
- **路由决策**：
  - 有错误 → `review_feedback = "error"` → 路由回 `code_generator` 进行自愈重试
  - 无错误 → `review_feedback = "pass"` → 路由到 `image_analysis`

**流式事件阶段**：`审查中` → `发现问题` / `通过`

### 6. image_analysis (图表分析节点)

调用多模态大模型（MLLM）逐张分析新生成的图表：

- **图片编码**：通过 `encode_images_to_base64()` 将 PNG/JPG 转换为 `data:image/{type};base64,...` 格式
- **去重分析**：只分析本轮新增的图表（`current_visualization_paths`），已有的分析结果（`image_analysis_results`）直接复用
- **并发分析**：使用 `ThreadPoolExecutor(max_workers=4)` 并行分析多张图表
- **分析内容**：图表类型识别、数据模式发现（趋势/周期性/异常点）、业务洞察提炼
- **加载提示词**：从 `image_analysis_prompt.txt` 加载专业分析模板

**流式事件阶段**：`准备图片` → `分析第X张` → `完成`

### 7. report_output (报告输出节点)

汇总整个工作流的所有结果生成 Markdown 报告：

- **首次报告**：生成完整报告，包含数据概况、清洗策略、生成代码、执行日志、可视化图表、图表分析
- **增量追加**：检测到报告已存在时，只追加新图表及其分析结果
- **路径修正**：报告中的图表使用相对路径，便于前端展示
- **对话记录**：每次报告输出都记录 `chat_history`，供多轮对话使用

**流式事件阶段**：`生成报告` → `写入文件` / `追加内容` → `完成`

---

## 条件边与自愈循环

### 入口路由

| 条件 | 目标 | 说明 |
|------|------|------|
| `cleaned_file_path` 为空 | `data_clean` | 新会话，需要执行数据清洗 |
| `cleaned_file_path` 存在 | `code_generator` | 已有清洗数据，跳过清洗直接生成代码 |

### 安全审查条件边

| 源节点 | 条件 | 目标节点 | 说明 |
|--------|------|----------|------|
| `sanity_checker` | `review_feedback` 含 "unsafe" | `code_generator` | 危险代码打回 LLM 重写 |
| `sanity_checker` | `review_feedback` = "safe" | `code_executor` | 安全通过，进入执行 |

### 自愈重试条件边

| 源节点 | 条件 | 目标节点 | 说明 |
|--------|------|----------|------|
| `self_reviewer` | `review_feedback` 含 "error"/"fail" | `code_generator` | 执行报错打回 LLM 修复 |
| `self_reviewer` | `review_feedback` = "pass" | `image_analysis` | 执行成功，进入图表分析 |

**重试限制**：`retry_count >= 3` 时终止重试，返回 `review_feedback = "fatal_error"`，避免无限循环。

---

## AgentState 状态结构

```python
class AgentState(TypedDict):
    # ── 基础信息 ──
    file_path: str                        # 原始数据文件路径
    cleaned_file_path: str                # 清洗后数据文件路径（存在时跳过 data_clean）
    user_prompt: str                      # 用户分析需求

    # ── 数据清洗 ──
    data_profile: str                     # 数据诊断报告文本
    cleaning_policy: dict                 # 清洗策略配置

    # ── 代码生成 ──
    generated_code: str                   # LLM 生成的 Python 代码（覆盖模式）

    # ── 代码执行 ──
    execution_log: str                    # 代码执行捕获的 stdout 输出

    # ── 图表路径（双轨设计） ──
    visualization_paths: Annotated[List[str], operator.add]    # 跨轮次累积（历史图表保留）
    current_visualization_paths: List[str]                      # 仅本轮新图表（每轮清零）

    # ── 图表分析 ──
    image_analysis_results: List[dict]    # 多模态 LLM 详细分析结果
    chart_insights: List[str]             # 图表洞察摘要

    # ── 路由控制 ──
    review_feedback: str                  # 路由信号：safe/unsafe/error/pass/fatal_error
    retry_count: int                      # 重试计数器（达 3 次终止）

    # ── 输出与会话 ──
    output_folder: str                    # 输出隔离目录（按数据名+时间戳）
    thread_id: str                        # 会话线程 ID
    chat_history: Annotated[List[dict], operator.add]  # 多轮对话历史
```

### 双图表路径设计

- **`visualization_paths`**（`operator.add` 累加模式）：跨轮次累积所有历史图表路径，在最终报告中展示全部图表
- **`current_visualization_paths`**（覆盖模式）：仅保留本轮新生成的图表路径，用于图片分析和当期报告输出

---

## 技术栈

| 技术/库 | 版本要求 | 用途 |
|---------|---------|------|
| Python | >= 3.12 | 开发语言 |
| LangGraph | >= 1.1.6 | 状态机 + 条件边 + 检查点持久化 |
| LangChain-OpenAI | >= 1.1.12 | 通义千问 API 适配（Dashscope 兼容接口） |
| FastAPI | >= 0.135.3 | REST API + Web 服务 |
| Uvicorn | >= 0.44.0 | ASGI 服务器 |
| Pandas | >= 3.0.2 | 数据处理与清洗 |
| Matplotlib | >= 3.10.8 | 数据可视化（Agg 无头后端） |
| Seaborn | >= 0.13.2 | 高级统计图表 |
| SQLite | - | 检查点持久化数据库 |
| python-dotenv | >= 1.2.2 | 环境变量管理 |
| python-multipart | >= 0.0.26 | 文件上传支持 |
| aiosqlite | >= 0.22.1 | 异步 SQLite 支持 |
| openai | >= 2.30.0 | OpenAI 兼容客户端 |

### LLM 配置

系统使用阿里云通义千问（Dashscope）大模型，通过 OpenAI 兼容接口调用：

- **文本模型**：`qwen3.6-flash`（`ChatOpenAI`），用于代码生成与自愈
- **多模态模型**：`qwen3.6-flash`（`mllm`），用于图表分析
- **配置参数**：`temperature=0.1`（低随机性保证代码稳定性），`timeout=300`（5分钟超时），`max_retries=2`

---

## 项目结构

```
data_analysis_agent/
│
├── main.py                          # CLI 交互式入口（终端菜单导航）
├── pyproject.toml                   # 项目配置与依赖管理
├── README.md                        # 本文档
│
├── agent/                           # LangGraph 核心逻辑
│   ├── graph.py                     # 状态机构建（7 节点 + 3 条件边 + 编译）
│   ├── graph_run.py                 # 工作流执行入口 + 继续对话
│   ├── nodes.py                     # 7 个节点完整实现
│   ├── states.py                    # AgentState 类型定义 + 路由常量
│   ├── llm.py                       # 通义千问 LLM + 多模态 MLLM 客户端
│   ├── app_cache.py                 # 编译图单例缓存（避免重复编译）
│   └── cli.py                       # 旧版 CLI 入口（兼容引用）
│
├── api/                             # FastAPI 后端
│   ├── main.py                      # FastAPI 应用初始化 + CORS + 路由注册
│   ├── models.py                    # Pydantic 请求/响应模型
│   ├── state.py                     # 共享状态（线程输出映射 + writer 抑制）
│   └── routes/
│       ├── file_routes.py           # 文件管理（列表 / 上传）
│       ├── thread_routes.py         # 会话管理（列表 / 详情 / 状态 / 删除）
│       └── workflow_routes.py       # 工作流（启动 / 状态查询 / 继续 / 报告）
│
├── static/                          # 前端静态文件
│   ├── index.html                   # 聊天界面（深色主题，类似 ChatGPT 风格）
│   └── js/
│       └── chat.js                  # 前端逻辑（会话列表 / 文件选择 / 轮询状态）
│
├── tools/                           # 核心工具库
│   ├── code_executor.py             # 沙盒代码执行（exec + stdout 捕获 + 图表收集）
│   ├── data_clean.py                # DataCleaner 全自动数据清洗类
│   └── check_node_state.py          # SQLite 检查点交互式查看工具
│
├── utils/                           # 基础设施工具
│   ├── logger.py                    # 双输出日志（控制台 INFO + 文件 DEBUG）
│   ├── path_tool.py                 # 路径解析 + 时间戳输出目录创建
│   ├── prompt_loader.py             # 提示词懒加载（缺失时自动降级）
│   ├── image_base64.py              # 图片 Base64 编码（支持批量 + 并发）
│   ├── setup_font.py                # Matplotlib 中文字体配置
│   ├── download_font.py             # OTF 中文字体自动下载脚本
│   ├── info_loader.py               # 报告加载器（Markdown → HTML 转换）
│   └── thread_check.py              # 线程管理（列表 / 历史浏览 / 删除）
│
├── memory/                          # 持久化层
│   ├── checkpointer.py              # SQLite 检查点（SqliteSaver）
│   └── session.py                   # 会话配置构建器
│
├── prompts/                         # LLM 提示词模板
│   ├── data_analysis_prompt.txt     # 数据分析代码生成提示词
│   ├── code_healing_prompt.txt      # 代码自愈修复提示词
│   └── image_analysis_prompt.txt    # 多模态图表解读提示词
│
├── config/                          # 配置文件
│   └── mock_session.py              # 开发测试用 Mock 会话配置
│
├── storage/                         # 数据文件存储
│   ├── earthquake_data_tsunami.csv
│   ├── 31f876ba_sleeptime_prediction_dataset.csv
│   └── test_sales_data.csv
│
├── output/                          # 输出目录（按数据名+时间戳自动隔离）
│   └── workflow_YYYYMMDD_HHMMSS/    # 单次运行输出（代码、图表、报告）
│
├── db/                              # 数据库
│   └── checkpoints.db               # SQLite 检查点数据库
│
└── logs/                            # 日志文件
    └── agent_YYYYMMDD.log           # 按日滚动的日志文件
```

---

## 功能详解

### 1. REST API 服务

基于 FastAPI 构建的完整后端，提供 RESTful API：

- **文件管理**：列出可用 CSV 文件、上传新文件
- **工作流执行**：异步启动新工作流、查询状态、继续已有会话
- **会话管理**：查看所有会话、获取会话详情和状态、删除会话
- **报告获取**：将 Markdown 报告渲染为 HTML 供前端展示
- **静态文件**：`/output/*` 路径映射到输出目录，图表可直接通过 URL 访问
- **CORS**：全来源开放，支持前端跨域访问

### 2. Web 前端界面

`static/index.html` + `static/js/chat.js` 提供类 ChatGPT 的聊天界面：

- **深色主题**：侧边栏 + 主聊天区布局，风格类似 ChatGPT
- **文件选择**：从存储目录中选择 CSV 数据文件
- **会话管理**：侧边栏列出历史会话，支持切换和继续对话
- **消息展示**：用户消息 + 智能体回复的对话式展示
- **报告渲染**：HTML 格式报告展示，包含文字和图表的完整分析结果
- **状态轮询**：后台异步轮询工作流执行状态
- **图片展示**：图表图片直接嵌入聊天界面

### 3. 数据自动清洗

`DataCleaner` 类（`tools/data_clean.py`）实现全自动清洗管道：

**探查阶段** (`profile()`)：
- 数据形状（行数 × 列数）
- 每列的缺失值数量与比例
- 重复行数
- 列类型推断

**清洗阶段** (`auto_clean()`)：
1. 删除缺失率超过阈值的列（默认 80%）
2. 数值列用中位数填充（抗离群值）
3. 文本列用众数填充
4. 删除重复行
5. 删除列名重复的列
6. 文本列标准化（去空格 + 首字母大写）

**输出阶段**：
- 保存清洗后的 CSV/Excel 文件
- 生成数据画像字符串供 LLM 参考
- 支持链式调用（`.profile().auto_clean().save_clean_data()`）

### 4. 多模态图表分析

图表分析节点使用通义千问多模态模型（兼容 OpenAI Vision API）：

- **Base64 编码**：通过 `image_base64.py` 将图表文件编码为 `data:image/png;base64,...` 格式
- **批量并发**：使用 `ThreadPoolExecutor` 并行分析多张图表
- **去重机制**：自动跳过已分析过的图表（基于 `chart_path` 去重）
- **智能提示词**：从 `image_analysis_prompt.txt` 加载专业分析模板，要求 LLM 分析图表类型、趋势、异常值、业务洞察

### 5. 安全沙盒执行

`tools/code_executor.py` 提供安全的代码执行环境：

| 安全措施 | 实现方式 |
|---------|---------|
| 无头模式 | `matplotlib.use('Agg')` 在 WSL/服务器无 GUI 环境运行 |
| plt.show 拦截 | 替换为 `logging.warning`，防止阻塞 |
| stdout 捕获 | `contextlib.redirect_stdout` 收集所有 print 输出 |
| 图表自动收集 | 对比执行前后文件差异，自动识别新生成的图表 |
| 命名空间隔离 | 独立的 `exec_globals` 字典，不影响全局 |
| 异常捕获 | 完整的 try/except，Traceback 保存到 execution_log |

### 6. 自愈重试机制

当 `self_reviewer` 检测到执行错误时：

1. **诊断注入**：将 `{old_code}` + `{execution_log}` + `{feedback}` 注入 `code_healing_prompt.txt`
2. **LLM 修复**：调用 `llm.stream()` 生成修复后的完整代码（非增量补丁，全量重写）
3. **安全审查**：修复后的代码仍需经过 `sanity_checker` 安全审查
4. **重复执行**：重新进入 `code_executor` 执行
5. **熔断保护**：`retry_count >= 3` 时返回 `fatal_error`，工作流终止，避免死循环

### 7. SQLite 检查点持久化

基于 `langgraph.checkpoint.sqlite.SqliteSaver`：

- **自动保存**：每个节点执行完毕后自动保存当前状态
- **断点恢复**：`app.get_state(config)` 获取最新状态
- **状态历史**：`app.get_state_history(config)` 回溯完整执行链
- **会话隔离**：不同 `thread_id` 的状态完全隔离
- **数据表**：`checkpoints` 表存储状态快照，`writes` 表存储节点写入

### 8. 会话与线程管理

完整的会话生命周期管理：

- **创建**：每次工作流启动生成唯一 `UUID` thread_id
- **继续**：从 checkpoint 恢复状态，复用输出目录，支持多轮增量分析
- **浏览**：命令行交互式浏览所有会话及其检查点历史
- **删除**：删除检查点记录及关联的输出文件
- **API 支持**：REST API 提供完整的 CRUD 操作

### 9. 图表路径双轨设计

| 字段 | 聚合模式 | 用途 |
|------|---------|------|
| `visualization_paths` | `operator.add`（跨轮次累加） | 最终报告中展示所有历史图表 |
| `current_visualization_paths` | 覆盖（每轮清零） | 仅本轮新图表，用于图片分析和当期报告 |

这种设计确保多轮对话中：
- 旧图表不会丢失（累积到 `visualization_paths`）
- 图表分析只处理新图表（读取 `current_visualization_paths`）

### 10. 入口智能路由

当 `cleaned_file_path` 已经存在时（多轮会话场景）：

```
START → 检查 cleaned_file_path → 存在 → 跳过 data_clean → 直接 code_generator
```

避免重复清洗已处理过的数据，提升多轮对话效率。

### 11. 多轮对话支持

基于检查点持久化和入口路由：

- **CLI 模式**：选择查看历史 → 选择线程 → 输入新提示词 → 继续分析
- **API 模式**：`POST /api/workflow/{thread_id}/continue` + 新提示词
- **状态继承**：复用原输出目录和清洗文件，只更新 `user_prompt`
- **增量报告**：报告检测到已存在时，只追加新图表和分析

### 12. 报告加载与 HTML 渲染

`utils/info_loader.py` 将 Markdown 报告转换为前端可渲染的 HTML：

- **图片路径修正**：将绝对路径 `/mnt/d/...` 转换为 Web 可访问的 `/output/...` URL
- **Markdown -> HTML**：支持标题、代码块、列表、图片、内联样式等 Markdown 元素的转换
- **响应式设计**：图片设置 `max-width:100%` 自适应容器

### 13. Matplotlib 中文支持

`utils/setup_font.py` 为无头环境配置中文字体：

- **字体下载**：`download_font.py` 从 GitHub 自动下载 NotoSansCJKsc / SourceHanSansSC
- **无头模式**：`matplotlib.use('Agg')` 确保在 WSL/服务器端正常运行
- **自动配置**：代码执行前自动加载字体，LLM 生成的代码只需调用 `setup_chinese_font()`

### 14. CLI 交互式界面

`main.py` 提供完整的终端交互体验：

```
 数据分析智能体
 ==================================================
   1. 查看会话历史
   2. 开始新对话
   3. 继续已有对话
   4. 删除会话
   0. 退出
```

- 自动扫描 `storage/` 目录列出可用 CSV 文件
- 支持文件编号选择或手动输入路径
- 继续对话时回显当前会话状态和历史图表
- 删除会话时提示是否同时清理输出文件

---

## API 接口文档

### 文件管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/files` | 列出 storage 目录下所有 CSV 文件 |
| POST | `/api/upload` | 上传 CSV 文件到 storage 目录 |

### 工作流

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/workflow` | 启动新的数据分析工作流 |
| GET | `/api/workflow/{thread_id}/status` | 查询工作流执行状态 |
| POST | `/api/workflow/{thread_id}/continue` | 继续已有会话 |
| GET | `/api/workflow/{thread_id}/report` | 获取渲染后的报告 HTML |
| DELETE | `/api/workflow/{thread_id}` | 删除工作流及关联数据 |

### 会话管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/threads` | 获取所有会话列表 |
| GET | `/api/threads/{thread_id}` | 获取指定会话详情 |
| GET | `/api/threads/{thread_id}/state` | 获取会话完整状态 |

### 请求/响应模型

**启动工作流**：
```json
POST /api/workflow
{
    "file_path": "storage/earthquake_data_tsunami.csv",
    "user_prompt": "请分析该数据并生成可视化图表"
}

响应:
{
    "thread_id": "uuid-string",
    "status": "started"
}
```

**查询状态**：
```json
GET /api/workflow/{thread_id}/status

响应:
{
    "status": "running" | "completed" | "error" | "not_found",
    "result": { ... },
    "output_folder": "output/workflow_20260427_201424/"
}
```

**继续会话**：
```json
POST /api/workflow/{thread_id}/continue
{
    "user_prompt": "再画一个帕累托图"
}

响应:
{
    "thread_id": "uuid-string",
    "status": "continued"
}
```

---

## 安装与运行

### 前置条件

- Python >= 3.12（推荐 3.13）
- uv 包管理器

### 环境配置

```bash
# 克隆项目
cd data_analysis_agent

# 安装依赖
uv install

# 配置环境变量（创建 .env 文件）
# DASHSCOPE_API_KEY=your_dashscope_api_key_here
```

### 运行方式

#### 方式一：Web 服务（推荐）

```bash
uv run python -m api.main
# 服务启动于 http://localhost:8000
# 打开浏览器即可使用数据分析聊天界面
```

#### 方式二：CLI 交互模式

```bash
uv run python main.py
# 进入终端交互菜单，选择文件和分析需求
```

#### 方式三：编程调用

```python
from agent.graph_run import run_workflow

result = run_workflow(
    file_path="storage/earthquake_data_tsunami.csv",
    user_prompt="请分析该数据并生成可视化图表"
)
```

### 可用数据文件

项目内置的示例数据位于 `storage/` 目录：

- `earthquake_data_tsunami.csv` — 地震与海啸数据
- `31f876ba_sleeptime_prediction_dataset.csv` — 睡眠时间预测数据
- `test_sales_data.csv` — 测试销售数据

---

## 输出报告结构

最终报告 `Agent_Final_Report.md` 按**轮次组织**，每轮包含完整的内容块：

```markdown
# 数据分析智能体报告

## 第 1 轮：[用户问题]

### 数据概况
- 原始数据 shape、列类型、缺失值统计

### 清洗策略
- 删除的高缺失列、填充方式、去重行数

### 生成的代码
- 完整可复现的 Python 分析脚本

### 终端执行输出
- 代码运行时的 stdout 捕获结果

### 可视化图表
- 本轮生成的图表（Markdown 图片格式）

### 图片分析
- 每张图表的 AI 多模态分析结果

## 第 2 轮：[新的用户问题]
...
```

每轮独立记录数据概况、清洗策略、生成代码、执行输出、图表及分析，不存在共享 header。多轮对话中，新的图表和分析自动追加到报告末尾。

---

## 开发指南

### 代码规范

- **行数限制**：单文件不超过 500 行，超限需按功能模块拆分
- **类型注解**：所有函数需标注参数和返回类型
- **日志规范**：使用 `utils.logger.logger` 统一日志输出

### 添加新节点

1. 在 `agent/nodes.py` 中实现节点函数
2. 在 `agent/graph.py` 中注册节点（`workflow.add_node()`）
3. 添加条件边（如需）：在 `agent/graph.py` 中定义路由函数并调用 `workflow.add_conditional_edges()`
4. 更新 `agent/states.py` 中的 `AgentState`（如需新增状态字段）

### 添加新提示词

1. 在 `prompts/` 目录下创建新的 `.txt` 文件
2. 在 `utils/prompt_loader.py` 中添加加载函数（使用 `partial(load_prompt, ...)`）
3. 在代码中通过 `load_xxx_prompt()` 调用

### 添加新工具

1. 在 `tools/` 或 `utils/` 目录下创建工具模块
2. 在节点函数中导入并使用

### 运行测试

```bash
# 运行所有测试
uv run python -m pytest test/ -v

# 运行单个测试
uv run python test/node1_test.py
```

### 依赖管理

依赖在 `pyproject.toml` 中声明，使用 `uv` 管理：

```bash
uv add package_name    # 添加依赖
uv remove package_name # 移除依赖
uv sync                # 同步依赖
```

---

## 功能清单

### 已实现功能

- [x] LangGraph 7 节点状态机（清洗 → 生成 → 安全审查 → 执行 → 自审 → 图表分析 → 报告）
- [x] 入口智能路由（跳过/执行 data_clean 的动态决策）
- [x] 条件边自愈循环（代码报错自动打回 LLM 修复，最多 3 次）
- [x] 安全审查关键字拦截（os.remove / subprocess / shutil.rmtree / os.system）
- [x] FastAPI Web 服务 + REST API
- [x] Web 前端聊天界面（深色主题 + 会话管理 + 报告展示）
- [x] 通义千问流式代码生成（token 级实时输出）
- [x] 多模态 LLM 图表解读（Base64 + 并发分析）
- [x] DataCleaner 全自动数据清洗
- [x] SQLite 检查点持久化（断点恢复 + 状态历史）
- [x] 沙盒代码执行（stdout 捕获 + plt.show 拦截 + 图表自动收集）
- [x] CLI 交互式界面（菜单导航 + 会话管理 + 文件选择）
- [x] 多轮对话（状态恢复 + 增量报告 + 图表累积）
- [x] 会话 CRUD（列表 / 详情 / 历史 / 删除）
- [x] Matplotlib 中文字体 + Agg 无头后端
- [x] 时间戳输出目录隔离
- [x] Markdown 报告生成 + HTML 渲染
- [x] 报告增量追加（多轮对话场景）
- [x] 文件上传与管理
- [x] 双图表路径设计（跨轮次累加 + 每轮覆盖）

### 待完善功能

- [ ] PostgresSaver 生产级检查点（替代 SQLite）
- [ ] Memory Store 跨对话长期记忆
- [ ] 更多数据源支持（Excel / Parquet / 数据库直连）
- [ ] 分析模板市场（预设分析场景选择）
- [ ] 代码生成结果缓存（相同分析需求避免重复调用 LLM）
- [ ] WebSocket 实时推送节点进度（目前走 REST 轮询）
- [ ] 更细粒度的错误分类与修复策略
- [ ] LLM 生成代码的单元测试自动生成

---

## 许可证

内部项目，仅限授权使用。
