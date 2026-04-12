# Axon API Reference

<div align="center">

**Complete API specification for Axon MCP Server**

Version 1.0.0 · [中文文档](API_CN.md)

</div>

---

## Table of Contents

- [Protocol](#protocol)
- [Error Codes](#error-codes)
- [System API](#system-api)
- [File API](#file-api)
- [Search API](#search-api)
- [Command API](#command-api)
- [Appendix](#appendix)

---

## Protocol

### JSON-RPC 2.0

Axon uses [JSON-RPC 2.0](https://www.jsonrpc.org/specification) over line-delimited JSON. Each message is one JSON object followed by `\n`.

**Only named parameters are supported** (`params` must be a JSON object).

### Request

```json
{"jsonrpc": "2.0", "method": "read_file", "params": {"path": "hello.txt"}, "id": 1}
```

### Success Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "path": "/workspace/hello.txt",
    "content": "Hello!",
    "encoding": "utf-8",
    "size": 6,
    "lines": 1,
    "truncated": false
  }
}
```

If warnings are present, the result includes `_warnings`:

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "result": {
    "...": "...",
    "_warnings": [
      {"code": "LARGE_FILE", "message": "文件较大: 5000000 字节", "details": {"size": 5000000}}
    ]
  }
}
```

### Error Response

```json
{
  "jsonrpc": "2.0",
  "id": 1,
  "error": {
    "code": -32602,
    "message": "Invalid params",
    "data": {
      "code": "INVALID_PARAMETER",
      "message": "参数 encoding 无效: gbk_wrong",
      "details": {"encoding": "gbk_wrong"},
      "suggestion": "使用 Python 支持的编码名，如 utf-8, gbk, cp936, latin-1 等",
      "timestamp": "2026-04-09T10:23:45.123456+00:00"
    }
  }
}
```

### Batch & Notifications

- **Batch**: Send an array of request objects; receive an array of responses.
- **Notification**: Request without `id` — no response returned.

---

## Error Codes

### Standard JSON-RPC

| Code | Name | Description |
|------|------|-------------|
| `-32700` | PARSE_ERROR | JSON parse failure |
| `-32600` | INVALID_REQUEST | Invalid request object |
| `-32601` | METHOD_NOT_FOUND | Method does not exist |
| `-32602` | INVALID_PARAMS | Invalid parameters |
| `-32603` | INTERNAL_ERROR | Server internal error |

### Application Errors (-32000 ~ -32099)

| Code | Name | Description |
|------|------|-------------|
| `-32000` | MCP_ERROR | General application error |
| `-32001` | MCP_RATE_LIMIT | Rate limit or concurrency exceeded |
| `-32002` | MCP_PERMISSION | Permission denied (403) |

### Error Types

| Error Code | Error Type | HTTP Status | JSON-RPC Code |
|------------|-----------|-------------|---------------|
| `INVALID_PARAMETER` | InvalidParameterError | 400 | -32602 |
| `ENCODING_ERROR` | EncodingError | 400 | -32602 |
| `PERMISSION_DENIED` | PermissionDeniedError | 403 | -32002 |
| `BLOCKED_PATH` | BlockedPathError | 403 | -32002 |
| `BLOCKED_COMMAND` | BlockedCommandError | 403 | -32002 |
| `PATH_OUTSIDE_WORKSPACE` | PathOutsideWorkspaceError | 403 | -32002 |
| `SYMLINK_ERROR` | SymlinkError | 403 | -32002 |
| `FILE_NOT_FOUND` | FileNotFoundError | 404 | -32000 |
| `TASK_NOT_FOUND` | TaskNotFoundError | 404 | -32000 |
| `TIMEOUT` | TimeoutError | 408 | -32000 |
| `TASK_ALREADY_RUNNING` | TaskAlreadyRunningError | 409 | -32000 |
| `CONCURRENT_MODIFICATION` | ConcurrentModificationError | 409 | -32000 |
| `SIZE_LIMIT_EXCEEDED` | SizeLimitExceededError | 413 | -32000 |
| `MAX_CONCURRENT_TASKS` | MaxConcurrentTasksError | 429 | -32001 |
| `RATE_LIMIT_EXCEEDED` | RateLimitError | 429 | -32001 |
| `TASK_FAILED` | TaskFailedError | 500 | -32000 |
| `INTERNAL_ERROR` | InternalError | 500 | -32603 |

### Warning Codes

| Code | Description |
|------|-------------|
| `OUTPUT_TRUNCATED` | Output exceeds buffer limit, truncated |
| `SLOW_OPERATION` | Operation took >5s |
| `LARGE_FILE` | File >1MB |
| `HIGH_MEMORY` | High memory usage |
| `PARTIAL_RESULT` | Result truncated or partially failed |

---

## System API

### get_system_info

Returns system environment information. **(AI tool)**

**Params**: none

**Response**:

```json
{
  "os": "windows",
  "arch": "AMD64",
  "python": "3.10.4",
  "shell": "powershell",
  "workspace": "C:\\Users\\user\\project",
  "axon_version": "1.0.0"
}
```

| Field | Type | Description |
|-------|------|-------------|
| `os` | str | `"windows"` / `"linux"` / `"darwin"` |
| `arch` | str | Processor architecture (`"x86_64"`, `"AMD64"`, `"arm64"`) |
| `python` | str | Python version |
| `shell` | str | Detected shell (`"powershell"`, `"cmd"`, `"bash"`, etc.) |
| `workspace` | str | Workspace absolute path |
| `axon_version` | str | Axon version |

---

## Web API

### fetch_webpage

Fetches the main content from a web page, automatically stripping HTML tags. **(AI tool)**

**Params**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `url` | str | ✅ | Web page URL (http:// or https://) |
| `query` | str | ❌ | Search keyword — returns matching paragraphs instead of full text |

**Response**:

```json
{
  "url": "https://example.com",
  "status": 200,
  "content": "Page text content...",
  "length": 12345,
  "truncated": false
}
```

| Field | Type | Description |
|-------|------|-------------|
| `url` | str | Requested URL |
| `status` | int | HTTP status code |
| `content` | str | Extracted text content |
| `length` | int | Returned text length |
| `truncated` | bool | Whether truncated (exceeds 100K characters) |

**Errors**: `INVALID_PARAMETER` (invalid URL format), `INTERNAL_ERROR` (network request failed/timeout)

---

### ping

Health check. **(Protocol method)**

**Params**: none

**Response**:

```json
{"status": "ok", "uptime_seconds": 3600.5}
```

---

### list_tools

Returns full tool schema for AI function calling. **(Protocol method)**

**Params**: none

**Response**:

```json
{
  "tools": {
    "file": [
      {
        "name": "read_file",
        "description": "读取文件内容，支持编码检测和行范围截取",
        "params": [
          {"name": "path", "type": "str", "required": true},
          {"name": "encoding", "type": "str|None", "required": false},
          {"name": "line_range", "type": "tuple[int,int]|None", "required": false},
          {"name": "max_size", "type": "int|None", "required": false}
        ],
        "is_write": false
      }
    ],
    "search": ["..."],
    "command": ["..."],
    "system": ["..."],
    "web": ["..."]
  },
  "total": 27
}
```

---

### get_config

Returns current configuration (sanitized). **(Protocol method)**

**Params**: none

**Response**:

```json
{
  "workspace": {"root_path": "/home/user/workspace", "max_depth": 10},
  "performance": {"max_concurrent_tasks": 50, "default_timeout_ms": 30000, "max_search_results": 1000},
  "logging": {"level": "INFO", "audit_enabled": true},
  "server": {"host": "127.0.0.1", "port": 9100}
}
```

---

### set_workspace

Switch workspace at runtime. **(Protocol method)**

**Params**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `root_path` | str | ✓ | New workspace absolute path |

**Response**:

```json
{"root_path": "/path/to/new/workspace", "message": "工作区已切换到: /path/to/new/workspace"}
```

**Side effect**: Clears directory, search, and metadata caches for the old workspace.

**Errors**: `INVALID_PARAMETER` (400), `BLOCKED_PATH` (403), `PERMISSION_DENIED` (403)

---

### get_stats

Cache and runtime statistics. **(Protocol method)**

**Params**: none

**Response**:

```json
{
  "uptime_seconds": 3600.5,
  "cache": {
    "metadata": {"entries": 150, "size_bytes": 15000},
    "directory": {"entries": 45, "size_bytes": 50000},
    "search": {"entries": 20, "size_bytes": 30000},
    "task": {"entries": 5, "size_bytes": 5000}
  }
}
```

---

### clear_cache

Clear cache. **(Protocol method)**

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `bucket` | str\|None | ✗ | None | Bucket name (`"metadata"`, `"directory"`, `"search"`, `"task"`). None = clear all |

**Response**:

```json
{"cleared": "all", "message": "缓存已清空: 全部"}
```

---

## File API

All file operations enforce workspace boundary. Relative paths are resolved against workspace root. Symlink traversal outside workspace is blocked.

### Lock Types

| Lock | Behavior |
|------|----------|
| `read` | Shared — multiple concurrent reads allowed |
| `write` | Exclusive — blocks all other reads/writes to same path |
| `write_dual` | Exclusive on both source and destination paths |
| `dir_write` | Exclusive on directory path |

---

### read_file

Read file content with auto-encoding detection.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `path` | str | ✓ | — | File path |
| `encoding` | str\|None | ✗ | None | Encoding (None = auto-detect) |
| `line_range` | tuple[int,int]\|None | ✗ | None | Line range `[start, end]`, 1-based inclusive |
| `max_size` | int\|None | ✗ | None | Max bytes to read |

**Response**:

```json
{
  "path": "/workspace/file.txt",
  "content": "line1\nline2\nline3",
  "encoding": "utf-8",
  "size": 18,
  "lines": 3,
  "truncated": false
}
```

**Errors**: `FILE_NOT_FOUND`, `SIZE_LIMIT_EXCEEDED`, `ENCODING_ERROR`, `INVALID_PARAMETER`

---

### write_file

Write file content. Creates the file (and parent directories) if it doesn't exist.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `path` | str | ✓ | — | File path |
| `content` | str | ✓ | — | File content |
| `encoding` | str | ✗ | `"utf-8"` | Write encoding |

**Response**:

```json
{"path": "/workspace/file.txt", "size": 1234, "encoding": "utf-8"}
```

When a new file is created, the response includes `"created": true`.

**Errors**: `ENCODING_ERROR`

---

### delete_file

Delete a file.

**Params**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `path` | str | ✓ | File path |

**Response**:

```json
{"path": "/workspace/file.txt", "deleted": true}
```

**Errors**: `FILE_NOT_FOUND`, `INVALID_PARAMETER` (not a file)

---

### stat_path

Get file/directory metadata.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `path` | str | ✓ | — | File or directory path |
| `follow_symlinks` | bool | ✗ | `true` | Follow symlinks |

**Response** (exists):

```json
{
  "path": "/workspace/file.txt",
  "exists": true,
  "type": "file",
  "size": 1234,
  "permissions": "0o644",
  "mtime": "2026-04-09T10:23:45.123456+00:00",
  "ctime": "2026-04-09T09:00:00.000000+00:00",
  "atime": "2026-04-09T10:20:00.000000+00:00",
  "is_hidden": false,
  "is_symlink": false,
  "attributes": {}
}
```

**Response** (not exists):

```json
{"path": "/workspace/nonexistent", "exists": false}
```

| Field | Type | Description |
|-------|------|-------------|
| `type` | str | `"file"` / `"directory"` / `"symlink"` / `"other"` |
| `size` | int | File size in bytes |
| `permissions` | str | Octal permissions (e.g. `"0o755"`) |
| `is_symlink` | bool | Whether it's a symlink |
| `symlink_target` | str | Symlink target (only when is_symlink=true) |
| `attributes` | dict | Platform-specific attributes |

---

### list_directory

List directory contents.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `path` | str | ✓ | — | Directory path |
| `pattern` | str\|None | ✗ | None | Glob filter (e.g. `"*.py"`) |
| `recursive` | bool | ✗ | `false` | Recurse into subdirectories |
| `include_hidden` | bool | ✗ | `false` | Include hidden files |
| `max_results` | int\|None | ✗ | None | Max entries to return |

**Response**:

```json
{
  "path": "/workspace/src",
  "entries": [
    {"name": "main.py", "type": "file", "size": 1234, "mtime": "2026-04-09T10:23:45+00:00", "is_hidden": false},
    {"name": "utils", "type": "directory", "size": null, "mtime": "2026-04-09T09:00:00+00:00", "is_hidden": false}
  ],
  "total": 2,
  "truncated": false
}
```

**Errors**: `FILE_NOT_FOUND`, `INVALID_PARAMETER` (not a directory)

---

### move_file

Move or rename a file.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source` | str | ✓ | — | Source file path |
| `dest` | str | ✓ | — | Destination path |
| `overwrite` | bool | ✗ | `false` | Overwrite if dest exists |

**Response**:

```json
{"source": "/workspace/old.txt", "dest": "/workspace/new.txt"}
```

**Errors**: `FILE_NOT_FOUND`, `CONCURRENT_MODIFICATION` (dest exists)

---

### copy_file

Copy a file.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `source` | str | ✓ | — | Source file path |
| `dest` | str | ✓ | — | Destination path |
| `overwrite` | bool | ✗ | `false` | Overwrite if dest exists |

**Response**:

```json
{"source": "/workspace/file.txt", "dest": "/workspace/copy.txt", "size": 1234}
```

**Errors**: `FILE_NOT_FOUND`, `CONCURRENT_MODIFICATION` (dest exists)

---

### move_directory

Move or rename a directory.

**Params**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `source` | str | ✓ | Source directory path |
| `dest` | str | ✓ | Destination path |

**Response**:

```json
{"source": "/workspace/old_dir", "dest": "/workspace/new_dir"}
```

**Errors**: `FILE_NOT_FOUND`, `INVALID_PARAMETER` (not a directory), `CONCURRENT_MODIFICATION` (dest exists)

---

### create_directory

Create directory (recursive by default).

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `path` | str | ✓ | — | Directory path |
| `recursive` | bool | ✗ | `true` | Create parent directories |

**Response**:

```json
{"path": "/workspace/new_dir", "created": true}
```

---

### delete_directory

Delete a directory.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `path` | str | ✓ | — | Directory path |
| `recursive` | bool | ✗ | `false` | Delete contents recursively |
| `force` | bool | ✗ | `false` | Force delete read-only files |

**Response**:

```json
{"path": "/workspace/old_dir", "deleted": true}
```

**Errors**: `FILE_NOT_FOUND`, `INVALID_PARAMETER` (non-empty and recursive=false)

---

### replace_string_in_file

Find `old_string` in a file and replace it with `new_string`. The `old_string` must match exactly and appear only once in the file.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `path` | str | ✓ | — | File path |
| `old_string` | str | ✓ | — | Text to find (must be unique in file) |
| `new_string` | str | ✓ | — | Replacement text |
| `encoding` | str | ✗ | `"utf-8"` | File encoding |

**Response**:

```json
{"path": "/workspace/file.txt", "replacements": 1, "total_lines": 50}
```

**Errors**: `FILE_NOT_FOUND`, `INVALID_PARAMETER` (not found or multiple matches), `ENCODING_ERROR`

---

### multi_replace_string_in_file

Batch text replacements. Each item in `replacements` must contain `path`, `old_string`, and `new_string`.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `replacements` | list | ✓ | — | Array of `{path, old_string, new_string}` |
| `encoding` | str | ✗ | `"utf-8"` | Default encoding |

**Response**:

```json
{
  "total": 3,
  "succeeded": 2,
  "failed": 1,
  "results": [
    {"index": 0, "path": "/workspace/a.py", "success": true},
    {"index": 1, "path": "/workspace/b.py", "success": true},
    {"index": 2, "path": "/workspace/c.py", "success": false, "error": "old_string not found"}
  ]
}
```

**Errors**: `PERMISSION_DENIED` (path outside workspace)

---

## Search API

### find_files

Search files by name or glob pattern.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `pattern` | str | ✓ | — | Glob pattern (e.g. `"*.py"`, `"test_*"`) |
| `root` | str\|None | ✗ | None | Search root (None = workspace) |
| `recursive` | bool | ✗ | `true` | Recurse into subdirectories |
| `file_types` | list[str]\|None | ✗ | None | Extension filter (e.g. `[".py", ".js"]`) |
| `include_hidden` | bool | ✗ | `false` | Include hidden files |
| `max_results` | int\|None | ✗ | None | Max matches to return |

**Response**:

```json
{
  "pattern": "*.py",
  "root": "/workspace",
  "matches": [
    {"path": "/workspace/main.py", "name": "main.py", "relative": "main.py", "size": 1234},
    {"path": "/workspace/src/utils.py", "name": "utils.py", "relative": "src/utils.py", "size": 5678}
  ],
  "total": 2,
  "truncated": false,
  "duration_ms": 125.5
}
```

**Errors**: `FILE_NOT_FOUND` (root doesn't exist), `INVALID_PARAMETER`

---

### search_text

Full-text search across files (supports regex).

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `query` | str | ✓ | — | Search term or regex |
| `root` | str\|None | ✗ | None | Search root (None = workspace) |
| `file_pattern` | str | ✗ | `"*"` | File name glob filter |
| `case_sensitive` | bool | ✗ | `false` | Case-sensitive matching |
| `is_regex` | bool | ✗ | `false` | Treat query as regex |
| `context_lines` | int | ✗ | `2` | Context lines (0–50) |
| `include_hidden` | bool | ✗ | `false` | Search hidden files |
| `max_results` | int\|None | ✗ | None | Max matching files to return |

**Response**:

```json
{
  "query": "def hello",
  "root": "/workspace",
  "matches": [
    {
      "path": "/workspace/main.py",
      "relative": "main.py",
      "hits": [
        {
          "line": 5,
          "content": "def hello(name):",
          "context": [
            {"line": 3, "content": "# Helper function"},
            {"line": 4, "content": ""},
            {"line": 5, "content": "def hello(name):"},
            {"line": 6, "content": "    print(f'Hello, {name}')"},
            {"line": 7, "content": ""}
          ]
        }
      ]
    }
  ],
  "total_files_searched": 10,
  "total_files_matched": 1,
  "total_hits": 1,
  "truncated": false,
  "duration_ms": 234.5
}
```

**Regex**: Full Python `re` module syntax. Query length capped at 10,000 characters (ReDoS protection).

**Errors**: `FILE_NOT_FOUND`, `INVALID_PARAMETER` (invalid regex or query too long)

---

### find_symbol

Search code symbols (functions, classes, variables).

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `symbol` | str | ✓ | — | Symbol name (supports regex) |
| `root` | str\|None | ✗ | None | Search root |
| `symbol_type` | str\|None | ✗ | None | `"function"` / `"class"` / `"variable"` (None = all) |
| `file_pattern` | str | ✗ | `"*"` | File name filter |
| `include_hidden` | bool | ✗ | `false` | Search hidden files |
| `max_results` | int\|None | ✗ | None | Max symbols to return |

**Response**:

```json
{
  "symbol": "hello",
  "root": "/workspace",
  "matches": [
    {
      "path": "/workspace/main.py",
      "relative": "main.py",
      "name": "hello",
      "type": "function",
      "line": 5,
      "context": "# Helper function\n\ndef hello(name):\n    print(f'Hello, {name}')\n"
    }
  ],
  "total": 1,
  "truncated": false,
  "duration_ms": 89.2
}
```

**Supported Languages**:

| Language | Functions | Classes | Variables |
|----------|-----------|---------|-----------|
| Python | ✓ | ✓ | ✓ |
| JavaScript / TypeScript | ✓ | ✓ | ✓ |
| Java / C# | ✓ | ✓ | |
| Go | ✓ | ✓ | |
| Rust | ✓ | ✓ | |

**Errors**: `FILE_NOT_FOUND`, `INVALID_PARAMETER`

---

## Command API

### Task Lifecycle

```
CREATED → RUNNING → COMPLETED (exit_code=0)
                   → FAILED    (exit_code≠0)
                   → STOPPED   (graceful stop)
                   → KILLED    (force kill)
                   → TIMED_OUT (timeout)
```

---

### run_command

Execute a command synchronously and wait for completion.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `command` | str | ✓ | — | Shell command |
| `cwd` | str\|None | ✗ | None | Working directory (None = workspace) |
| `timeout` | int\|None | ✗ | None | Timeout in ms (None = config default) |
| `env` | dict\|None | ✗ | None | Additional environment variables |

**Response**:

```json
{
  "task_id": "a1b2c3d4e5f6",
  "command": "python -m pytest",
  "exit_code": 0,
  "stdout": "...output...",
  "stderr": "",
  "duration_ms": 5234.5
}
```

**Errors**: `BLOCKED_COMMAND` (403), `MAX_CONCURRENT_TASKS` (429), `TIMEOUT` (408)

---

### create_task

Spawn an async background task.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `command` | str | ✓ | — | Shell command |
| `cwd` | str\|None | ✗ | None | Working directory |
| `timeout` | int\|None | ✗ | None | Timeout in ms |
| `env` | dict\|None | ✗ | None | Additional environment variables |

**Response**:

```json
{"task_id": "a1b2c3d4e5f6", "command": "python server.py", "pid": 12345, "state": "running"}
```

**Errors**: `BLOCKED_COMMAND` (403), `MAX_CONCURRENT_TASKS` (429)

---

### stop_task

Stop a running task.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `task_id` | str | ✓ | — | Task ID |
| `force` | bool | ✗ | `false` | `false`: interrupt → wait 5s → force kill. `true`: immediate kill |

**Response**: Full task dict (same as `task_status`), with `state` = `"stopped"` or `"killed"`.

**Errors**: `TASK_NOT_FOUND` (404)

---

### del_task

Delete a completed task and free memory (buffers + task record).

**Params**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | str | ✓ | Task ID |

**Response**:

```json
{"task_id": "a1b2c3d4e5f6", "deleted": true}
```

**Errors**: `TASK_NOT_FOUND` (404), `TASK_ALREADY_RUNNING` (409 — must `stop_task` first)

---

### task_status

Query current task state.

**Params**:

| Param | Type | Required | Description |
|-------|------|----------|-------------|
| `task_id` | str | ✓ | Task ID |

**Response**:

```json
{
  "task_id": "a1b2c3d4e5f6",
  "command": "python script.py",
  "cwd": "/workspace",
  "state": "running",
  "pid": 12345,
  "exit_code": null,
  "signal": null,
  "created_at": "2026-04-09T10:23:45.123456+00:00",
  "started_at": "2026-04-09T10:23:45.456789+00:00",
  "completed_at": null,
  "duration_ms": null,
  "stream": {
    "stdout": {"buffered": 1024, "eof": false},
    "stderr": {"buffered": 0, "eof": false}
  }
}
```

| Field | Type | Description |
|-------|------|-------------|
| `state` | str | `"running"` / `"completed"` / `"failed"` / `"stopped"` / `"killed"` / `"timed_out"` |
| `exit_code` | int\|null | Exit code (null while running) |
| `signal` | str\|null | Signal received (`"interrupt"`, `"kill"`) |
| `duration_ms` | float\|null | Duration in ms (null while running) |
| `stream` | dict | Buffer info per channel |

**Errors**: `TASK_NOT_FOUND` (404)

---

### wait_task

Block until task completes (or timeout).

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `task_id` | str | ✓ | — | Task ID |
| `timeout` | int\|None | ✗ | None | Timeout in ms |

**Response**: Same as `task_status` (final state).

**Errors**: `TASK_NOT_FOUND` (404), `TIMEOUT` (408)

---

### list_tasks

List all tasks.

**Params**: none

**Response**:

```json
{
  "tasks": [
    {"task_id": "a1b2c3d4e5f6", "command": "python script.py", "state": "running", "pid": 12345, "...": "..."},
    {"task_id": "x9y8z7w6v5u4", "command": "echo done", "state": "completed", "pid": 54321, "...": "..."}
  ],
  "total": 2,
  "active": 1
}
```

---

### read_stdout

Read task stdout incrementally (consumer-style).

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `task_id` | str | ✓ | — | Task ID |
| `max_chars` | int | ✗ | 8192 | Max characters to read |

**Response**:

```json
{"task_id": "a1b2c3d4e5f6", "output": "...new output since last call...", "eof": false}
```

Each call returns only **new data** since the previous call. Already-read data is not returned again.

**Errors**: `TASK_NOT_FOUND` (404)

---

### read_stderr

Read task stderr incrementally. Same interface as `read_stdout`.

---

### write_stdin

Write data to task's stdin.

**Params**:

| Param | Type | Required | Default | Description |
|-------|------|----------|---------|-------------|
| `task_id` | str | ✓ | — | Task ID |
| `data` | str | ✓ | — | Text to write |
| `eof` | bool | ✗ | `false` | Close stdin after writing |

**Response**:

```json
{"task_id": "a1b2c3d4e5f6", "written": 10, "eof": false}
```

**Errors**: `TASK_NOT_FOUND` (404), `INVALID_PARAMETER` (stdin not available)

---

## Appendix

### Tool Summary

| Group | Count | Methods |
|-------|-------|---------|
| **File** | 12 | `read_file` `write_file` `delete_file` `stat_path` `list_directory` `move_file` `copy_file` `move_directory` `create_directory` `delete_directory` `replace_string_in_file` `multi_replace_string_in_file` |
| **Search** | 3 | `find_files` `search_text` `find_symbol` |
| **Command** | 10 | `run_command` `create_task` `stop_task` `del_task` `task_status` `wait_task` `list_tasks` `read_stdout` `read_stderr` `write_stdin` |
| **System** | 1 | `get_system_info` |
| **Web** | 1 | `fetch_webpage` |
| **Protocol** | 6 | `ping` `list_tools` `get_config` `set_workspace` `get_stats` `clear_cache` |

**Total**: 27 AI tools + 6 protocol methods = 33 routes

### Write Operations

Only these methods modify the filesystem:

`write_file` · `delete_file` · `create_directory` · `delete_directory` · `move_file` · `copy_file` · `move_directory` · `replace_string_in_file` · `multi_replace_string_in_file`

### Streaming I/O Pattern

```python
# Non-blocking incremental stdout reading
task_id = response["result"]["task_id"]
while True:
    r = client.call("read_stdout", {"task_id": task_id})
    output = r["result"]["output"]
    eof = r["result"]["eof"]
    if output:
        print(output, end="")
    if eof:
        break
    time.sleep(0.1)
```
