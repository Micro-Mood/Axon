# Axon

<div align="center">

<h3>⚡ Lightweight Cross-Platform MCP Server</h3>

**A JSON-RPC 2.0 file & command operation server designed for AI assistants**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20|%20Linux%20|%20macOS-blue.svg)]()

[**中文文档**](README_CN.md)

</div>

---

## ✨ What is Axon?

Axon is a lightweight **Model Context Protocol (MCP)** server that gives AI assistants the ability to read/write files, search code, execute commands, and manage async tasks — all through a simple JSON-RPC 2.0 interface over TCP or Stdio.

| Feature | Description |
|---------|-------------|
| 📁 **File Operations** | Read, write, create, delete, move, copy, patch — with auto-encoding detection |
| 🔍 **Code Search** | Find files by glob, search content by text/regex, locate symbols across languages |
| ⚙️ **Command Execution** | Sync run or async task management with streaming stdout/stderr |
| 🔒 **Security Built-in** | Path boundary enforcement, dangerous command blocking (50+ patterns), rate limiting |
| 🧩 **Plugin Architecture** | Add new tools by dropping a single `.py` file — zero core changes needed |
| 🌐 **Cross-Platform** | Windows, Linux, macOS — platform differences handled transparently |

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
│  File · Search · Command · System                │
├──────────────────────────────────────────────────┤
│  Layer 3: Stream                                 │
│  Process stdout/stderr lifecycle management      │
├──────────────────────────────────────────────────┤
│  Layer 2: Platform                               │
│  Encoding · Signals · Filesystem · Defaults      │
├──────────────────────────────────────────────────┤
│  Layer 1: Core                                   │
│  Config · Security · Cache · Errors · FileLock   │
└──────────────────────────────────────────────────┘
```

Strict downward dependency — no circular imports, each layer only depends on layers below it.

## 🚀 Quick Start

### Prerequisites

- Python 3.10+
- pip

### Install Dependencies

```bash
pip install pydantic aiofiles
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

## 🛠️ Tools (36 methods)

### File (16)

| Method | Description |
|--------|-------------|
| `read_file` | Read file content with auto-encoding detection |
| `write_file` | Overwrite existing file |
| `create_file` | Create new file (optional overwrite) |
| `delete_file` | Delete a file |
| `stat_path` | Get file/directory metadata |
| `exists` | Check if path exists |
| `list_directory` | List directory contents with glob filter |
| `move_file` | Move or rename a file |
| `copy_file` | Copy a file |
| `move_directory` | Move or rename a directory |
| `create_directory` | Create directory (recursive) |
| `delete_directory` | Delete directory (recursive + force options) |
| `replace_range` | Replace lines in a file |
| `insert_text` | Insert text at a specific line |
| `delete_range` | Delete a range of lines |
| `apply_patch` | Apply unified diff patch |

### Search (3)

| Method | Description |
|--------|-------------|
| `find_files` | Search files by glob pattern |
| `find_content` | Search text/regex in file contents with context |
| `find_symbol` | Find code symbols (functions, classes, variables) across Python, JS/TS, Rust, Go, Java, C# |

### Command (10)

| Method | Description |
|--------|-------------|
| `run_command` | Execute command and wait for completion |
| `create_task` | Spawn async task, returns task_id |
| `stop_task` | Graceful stop (sends interrupt/terminate signal) |
| `kill_task` | Force kill |
| `task_status` | Query task state |
| `wait_task` | Wait for task completion |
| `list_tasks` | List all tasks |
| `read_stdout` | Read task stdout (consumer-style) |
| `read_stderr` | Read task stderr (consumer-style) |
| `write_stdin` | Write to task stdin |

### System (7)

| Method | Description |
|--------|-------------|
| `ping` | Health check |
| `get_version` | Server version info |
| `get_methods` | List all registered methods |
| `get_config` | Current config (sanitized) |
| `set_workspace` | Switch workspace at runtime |
| `get_stats` | Cache and task statistics |
| `clear_cache` | Clear cache (all or by bucket) |

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
    "max_depth": 20
  },
  "security": {
    "blocked_paths": [],
    "blocked_commands": [],
    "max_file_size_mb": 100,
    "follow_symlinks": false
  },
  "performance": {
    "max_concurrent_tasks": 10,
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
    "audit_enabled": true
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
│   ├── handlers/            # L4: File, Search, Command, System handlers
│   ├── middleware/          # L5: Security, Validation, RateLimit, Concurrency, Audit
│   ├── protocol/            # L6: JSON-RPC codec, Router, Server, Transport
│   └── tools/               # Tool definitions (auto-discovered plugins)
│       ├── file/            # 16 file operation tools
│       ├── search/          # 3 search tools
│       ├── command/         # 10 command/task tools
│       └── system/          # 7 system tools
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