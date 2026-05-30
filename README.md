# Axon

<div align="center">

<h3>⚡ Lightweight Cross-Platform MCP Server</h3>

<p>
  <a href="https://www.notion.so/product">
    <img src="https://img.shields.io/badge/Notion-Integrated-000000?logo=notion&logoColor=white" alt="Notion Integrated" />
  </a>
  <br/>
  15 built-in Notion tools for search, pages, databases, blocks, and comments.
</p>

**A JSON-RPC 2.0 file & command operation server designed for AI assistants**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20|%20Linux%20|%20macOS-blue.svg)]()

<table>
<tr>
<td align="center"><strong>42</strong><br/>AI Tools</td>
<td align="center"><strong>6</strong><br/>Protocol Methods</td>
<td align="center"><strong>15</strong><br/>Notion Tools</td>
<td align="center"><strong>TCP / Stdio</strong><br/>Dual Transport</td>
</tr>
</table>

<p>
  <a href="#overview">Overview</a> ·
  <a href="#architecture">Architecture</a> ·
  <a href="#quick-start">Quick Start</a> ·
  <a href="#tools">Tools</a> ·
  <a href="#configuration">Configuration</a>
</p>

[**中文文档**](README_CN.md)

</div>

---

<a id="overview"></a>

## ✨ What is Axon?

Axon is a lightweight **Model Context Protocol (MCP)** server that gives AI assistants the ability to read/write files, search code, execute commands, and manage async tasks — all through a simple JSON-RPC 2.0 interface over TCP or Stdio.

| Feature | Description |
|---------|-------------|
| 📁 **File Operations** | Read, write, create, delete, move, copy — with auto-encoding detection |
| 🔍 **Code Search** | Find files by glob, search content by text/regex, locate symbols across languages |
| ⚙️ **Command Execution** | Sync run or async task management with streaming stdout/stderr |
| 🔒 **Security Built-in** | Path boundary enforcement, dangerous command blocking (50+ patterns), rate limiting |
| 🧩 **Plugin Architecture** | Add new tools by dropping a single `.py` file — zero core changes needed |
| 📝 **Notion Integration** | Full Notion API: search, read, write, create, query databases, manage blocks and comments — 15 tools |
| 🌐 **Cross-Platform** | Windows, Linux, macOS — platform differences handled transparently |

<a id="architecture"></a>

## 🏗️ Architecture

```
┌──────────────────────────────────────────────────┐
│  Layer 6: Protocol                               │
│  JSON-RPC 2.0 Server (TCP / Stdio)              │
├──────────────────────────────────────────────────┤
│  Layer 5: Middleware                             │
│  Security → Validation → RateLimit → Concurrency │
│  → Audit                                         │
├──────────────────────────────────────────────────┤
│  Layer 4: Handlers                               │
│  File · Search · Command · System · Web · Notion           │
├──────────────────────────────────────────────────┤
│  Layer 3: Stream                                 │
│  Process stdout/stderr lifecycle management      │
├──────────────────────────────────────────────────┤
│  Layer 2: Platform                               │
│  Encoding · Signals · Filesystem · Defaults      │
├──────────────────────────────────────────────────┤
│  Layer 1: Core                                   │
│  Config · Security · Cache · Errors · FileLock · Resource │
└──────────────────────────────────────────────────┘
```

Strict downward dependency — no circular imports, each layer only depends on layers below it.

<a id="quick-start"></a>

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- pip

### Install Dependencies

```bash
pip install pydantic aiofiles aiohttp
```

### Run

```bash
# TCP mode (default, port 9100)
python -m src

# Specify workspace and port
python -m src --workspace /path/to/project --port 9100

# Stdio mode (for pipe/process communication)
python -m src --transport stdio
```

### Send a Request

```bash
# TCP: send a JSON-RPC request (one JSON per line)
echo '{"jsonrpc":"2.0","method":"ping","params":{},"id":1}' | nc localhost 9100
```

```json
{"jsonrpc":"2.0","id":1,"result":{"status":"ok","uptime_seconds":42.1}}
```

<a id="tools"></a>

## 🛠️ Tools

Axon exposes **42 AI tools** (auto-discovered plugins) and **6 protocol methods** (server management).

### File (12)

| Method | Description |
|--------|-------------|
| `read_file` | Read file content with auto-encoding detection |
| `write_file` | Write file content (creates if not exists) |
| `delete_file` | Delete a file |
| `stat_path` | Get file/directory metadata |
| `list_directory` | List directory contents with glob filter |
| `move_file` | Move or rename a file |
| `copy_file` | Copy a file |
| `move_directory` | Move or rename a directory |
| `create_directory` | Create directory (recursive) |
| `delete_directory` | Delete directory (recursive + force options) |
| `replace_string_in_file` | Find and replace exact text in a file |
| `multi_replace_string_in_file` | Batch text replacements across files |

### Search (3)

| Method | Description |
|--------|-------------|
| `find_files` | Search files by glob pattern |
| `search_text` | Search text/regex in file contents with context |
| `find_symbol` | Find code symbols (functions, classes, variables) across Python, JS/TS, Rust, Go, Java, C# |

### Command (10)

| Method | Description |
|--------|-------------|
| `run_command` | Execute command and wait for completion |
| `create_task` | Spawn async task, returns task_id |
| `stop_task` | Stop task — graceful by default (interrupt → 5s → force kill), `force=true` for immediate kill |
| `del_task` | Delete completed task and free memory |
| `task_status` | Query task state |
| `wait_task` | Wait for task completion |
| `list_tasks` | List all tasks |
| `read_stdout` | Read task stdout (consumer-style, incremental) |
| `read_stderr` | Read task stderr (consumer-style, incremental) |
| `write_stdin` | Write to task stdin |

### System (1)

| Method | Description |
|--------|-------------|
| `get_system_info` | Returns OS, architecture, Python version, shell, workspace, Axon version |

### Web (1)

| Method | Description |
|--------|-------------|
| `fetch_webpage` | Fetch web page content, auto-strip HTML tags, supports keyword-based paragraph extraction |

### Notion (15)

> **Setup**: Create an integration token at [![Notion Integrations](https://img.shields.io/badge/Notion-My%20Integrations-lightgray?logo=notion)](https://www.notion.so/my-integrations), then share individual pages with that integration. Pass `api_key` per request — Axon does not store credentials.

<details>
<summary>Show all Notion tools</summary>

| Method | Description |
|--------|-------------|
| `notion_search` | Search Notion pages and databases |
| `notion_get_page` | Get page metadata and block content (supports `max_blocks` + `start_cursor` pagination) |
| `notion_get_block_children` | Paginated reading of block children — use when `notion_get_page` returns `has_more` |
| `notion_query_database` | Query a Notion database and return lightweight page results |
| `notion_get_comments` | Get comments on a page or block |
| `notion_list_users` | List workspace members |
| `notion_create_page` | Create a Notion page or database entry |
| `notion_update_page` | Update a page title or properties |
| `notion_archive_page` | Archive (trash) a page — recoverable from Notion UI |
| `notion_append_blocks` | Append paragraph, heading, list, quote, or code blocks |
| `notion_update_block` | Update the content of a block |
| `notion_delete_block` | Delete (archive) a block |
| `notion_create_database` | Create an inline database inside a page |
| `notion_update_database` | Update a database title or property schema |
| `notion_create_comment` | Add a comment to a page |

</details>

### Protocol Methods (6)

These are server management methods — not injected into AI tool lists, but callable via JSON-RPC.

| Method | Description |
|--------|-------------|
| `ping` | Health check |
| `list_tools` | List all registered AI tools with full JSON schema |
| `get_config` | Current config (sanitized) |
| `set_workspace` | Switch workspace at runtime |
| `get_stats` | Cache and task statistics |
| `clear_cache` | Clear cache (all or by bucket) |

<a id="configuration"></a>

## ⚙️ Configuration

### CLI Arguments

| Argument | Short | Default | Description |
|----------|-------|---------|-------------|
| `--config` | `-c` | — | Config file path (JSON) |
| `--transport` | `-t` | `tcp` | Transport mode: `tcp` or `stdio` |
| `--host` | — | `127.0.0.1` | TCP listen address |
| `--port` | `-p` | `9100` | TCP listen port |
| `--workspace` | `-w` | `.` | Workspace root path |
| `--log-level` | — | `INFO` | Log level: DEBUG, INFO, WARNING, ERROR |

### Config File (JSON)

```json
{
  "workspace": {
    "root_path": ".",
    "allowed_extensions": [],
    "max_depth": 20
  },
  "security": {
    "blocked_paths": [],
    "blocked_commands": [],
    "allowed_shells": [],
    "max_file_size_mb": 100,
    "follow_symlinks": false
  },
  "performance": {
    "max_concurrent_tasks": 10,
    "cache_ttl": 60,
    "default_timeout_ms": 30000,
    "max_search_results": 1000,
    "max_output_buffer_mb": 10
  },
  "server": {
    "host": "127.0.0.1",
    "port": 9100,
    "transport": "tcp"
  },
  "logging": {
    "level": "INFO",
    "audit_enabled": true,
    "log_file": null
  }
}
```

## 🔒 Security

- **Path Boundary** — All file operations confined to workspace root, symlink escape prevented
- **Command Blocking** — 50+ regex patterns detect dangerous commands (rm -rf, format, reverse shells, privilege escalation, etc.)
- **Environment Blacklist** — Blocks injection via LD_PRELOAD, PATH, PYTHONPATH, etc.
- **Rate Limiting** — Sliding window: ~10 req/s global, stricter for write operations
- **Concurrency Control** — Reader/writer file locks prevent data races, sorted dual-lock prevents deadlocks
- **Audit Logging** — Every request logged with method, duration, success/failure

## 📁 Project Structure

```
Axon/
├── src/
│   ├── __init__.py          # Version
│   ├── __main__.py          # CLI entry point
│   ├── core/                # L1: Config, Security, Cache, Errors, FileLock, Resource
│   ├── platform/            # L2: Encoding, Signals, Filesystem, Defaults
│   ├── stream/              # L3: OutputBuffer, StreamManager
│   ├── handlers/            # L4: File, Search, Command, System, Web, Notion handlers
│   ├── middleware/          # L5: Security, Validation, RateLimit, Concurrency, Audit
│   ├── protocol/            # L6: JSON-RPC codec, Router, Server, Transport
│   └── tools/               # Tool definitions (auto-discovered plugins)
│       ├── file/            # 12 file operation tools
│       ├── search/          # 3 search tools
│       ├── command/         # 10 command/task tools
│       ├── system/          # 1 system tool
│       ├── web/             # 1 web tool
│       └── notion/          # 15 Notion API tools
└── tests/                   # Test suites
```

## 🤝 Protocol

**JSON-RPC 2.0** over line-delimited JSON (each message = one JSON line + `\n`).

**Request:**
```json
{"jsonrpc": "2.0", "method": "read_file", "params": {"path": "hello.txt"}, "id": 1}
```

**Response:**
```json
{"jsonrpc": "2.0", "id": 1, "result": {"path": "/workspace/hello.txt", "content": "Hello!", "encoding": "utf-8", "size": 6, "lines": 1, "truncated": false}}
```

**Error:**
```json
{"jsonrpc": "2.0", "id": 1, "error": {"code": -32002, "message": "路径不在工作区内", "data": {"code": "PATH_OUTSIDE_WORKSPACE"}}}
```

Supports batch requests (array of requests) and notifications (requests without `id`).

## License

[MIT](LICENSE)