# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

**All terminal commands must use `uv run python` prefix. Never use bare `python` or `pytest` commands.**

**Terminal management: Always close terminal windows after use.**

## Code Standards

**File Line Limit:**
- No single code file shall exceed **500 lines**
- Files exceeding 500 lines must be split by functionality into separate files (e.g., into `nodes/`, `tools/`, `utils/` subdirectories)
- Splitting principle: one file per clearly-defined functional module

## Project Overview

A LangGraph-based intelligent data analysis agent that automates data cleaning, code generation, and visualization. The agent uses a state machine with 7 nodes and supports self-healing retry loops with LLM caching.

## Commands

```bash
# Install dependencies
uv install

# Run the agent (interactive CLI)
uv run python main.py

# Run the agent (interactive CLI - alias)
uv run python -m agent.cli

# Run the API server
uv run python api/main.py

# Run node tests
uv run python -m pytest test/ -v

# Run a single test file
uv run python test/node1_test.py
```

## Architecture

### State Machine (LangGraph)

The agent is built as a directed graph in `agent/graph.py`. Each node is a pure function that receives `AgentState` and returns a dict of state updates.

**Node flow (linear):**
```
data_clean → code_generator → sanity_checker → code_executor → self_reviewer → image_analysis → report_output
```

**Conditional edges (loops):**
- `sanity_checker` → if unsafe, loops back to `code_generator` (max 3 retries via `retry_count`)
- `self_reviewer` → if error detected in execution log, loops back to `code_generator` for self-healing

**Key state fields (`agent/states.py`):**
- `data_profile` — data shape, columns, dtypes, missing stats from cleaner
- `cleaning_policy` — JSON strategy dict (optional, auto_clean used by default)
- `generated_code` — code string produced by code_generator
- `execution_log` — captured stdout from code execution
- `visualization_paths` — accumulated list of chart files (uses `operator.add` across retries)
- `current_visualization_paths` — charts from current turn only (overwrite mode)
- `image_analysis_results` — list of dicts with chart_name, chart_path, analysis
- `review_feedback` — "safe"/"unsafe"/"error"/"pass" signal controlling routing
- `retry_count` — tracks code_generator retries (max 3)
- `thread_id` — for LangGraph checkpoint persistence

### Nodes (`agent/nodes.py`)

| Node | Role |
|------|------|
| `data_clean_node` | Calls `DataCleaner.auto_clean()` — profiles, fills missing, removes duplicates |
| `code_generator_node` | Streams LLM output (qwen3.6-flash via Dashscope), caches responses, supports self-healing retry |
| `sanity_checker_node` | Static keyword scan for dangerous ops (`os.remove`, `shutil.rmtree`, `subprocess`) |
| `code_executor_node` | Calls `tools.code_executor.execute_code()` — runs generated code via `exec()` |
| `self_reviewer_node` | Checks `execution_log` for Traceback, sets `review_feedback` to route flow |
| `imag_analysis_code` | Parallel image analysis via `call_mllm_image()` (ThreadPoolExecutor, max 4 workers) |
| `report_output_node` | Writes/extends Markdown report to `output/Agent_Final_Report.md` |

### Tools (`tools/`)

- `code_executor.py` — `execute_code(code, data_file, output_dir)` runs code via `exec()`, captures stdout, detects new chart files
- `data_clean.py` — `DataCleaner` class with `auto_clean()`, `profile()`, `save_clean_data()`

### Utils (`utils/`)

- `logger.py` — `get_logger()` returns a Logger with both console and file handlers
- `path_tool.py` — `get_abs_path(file_name)`, `get_output_folder(file_path)`, `list_csv_files()`
- `prompt_loader.py` — loads `data_analysis_prompt`, `code_healing_prompt`, `image_analysis_prompt` from `prompts/`
- `llm_cache.py` — `get_cached_response()` / `store_cached_response()` for LLM prompt caching
- `image_base64.py` — `encode_images_to_base64()` for multimodal LLM calls
- `thread_check.py` — `list_threads()`, `delete_thread()` for CLI session management

### Memory/Checkpointing (`memory/`)

- `checkpointer.py` — `SqliteSaver` checkpointer persisting LangGraph state to `checkpoints.db`
- `session.py` — `get_session_config()` for thread_id-based session config generation

### LLM Integration (`agent/llm.py`)

- `llm` — `ChatOpenAI` (qwen3.6-flash via Dashscope), streaming enabled
- `call_mllm_image()` — multimodal LLM for image analysis with streaming output
- `get_embedding()` — Dashscope text embedding (tongyi-embedding-vision-flash)

### API (`api/`)

- FastAPI app in `api/main.py` with routes for files, threads, and workflow execution
- Routes: `file_routes.py`, `thread_routes.py`, `workflow_routes.py`
- Static file serving for `output/` and `static/`

### Prompt Templates (`prompts/`)

- `data_analysis_prompt.txt` — for initial code generation
- `code_healing_prompt.txt` — for self-healing retry with execution error feedback
- `image_analysis_prompt.txt` — for multimodal LLM chart analysis

## Data Flow

```
User input (file_path + user_prompt)
  → data_clean (auto_clean, saves cleaned CSV)
  → code_generator (LLM streaming, caching)
  → sanity_checker (keyword scan)
  → code_executor (exec sandbox)
  → self_reviewer (error detection → retry loop)
  → image_analysis (parallel chart analysis)
  → report_output (Markdown report)
```

Output charts: `output/*.png`
Logs: `logs/*.log`
Checkpoints: `checkpoints.db`
LLM cache: `llm_cache/`
