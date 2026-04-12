# Axon API 参考手册

<div align="center">

**Axon MCP Server 完整 API 规范**

版本 1.0.0 · [English](API.md)

</div>

---

## 目录

- [协议](#协议)
- [错误码](#错误码)
- [系统 API](#系统-api)
- [文件 API](#文件-api)
- [搜索 API](#搜索-api)
- [命令 API](#命令-api)
- [附录](#附录)

---

## 协议

### JSON-RPC 2.0

Axon 使用 [JSON-RPC 2.0](https://www.jsonrpc.org/specification) 协议，行分隔 JSON（每条消息 = 一行 JSON + `\n`）。

**仅支持命名参数**（`params` 必须是 JSON 对象）。

### 请求

```json
{"jsonrpc": "2.0", "method": "read_file", "params": {"path": "hello.txt"}, "id": 1}
```

### 成功响应

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

如有警告，result 中会包含 `_warnings`：

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

### 错误响应

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

### 批量请求与通知

- **批量请求**：发送请求数组，收到响应数组。
- **通知**：不带 `id` 的请求，不返回响应。

---

## 错误码

### JSON-RPC 标准错误码

| 码 | 名称 | 说明 |
|---|------|------|
| `-32700` | PARSE_ERROR | JSON 解析失败 |
| `-32600` | INVALID_REQUEST | 无效的请求对象 |
| `-32601` | METHOD_NOT_FOUND | 方法不存在 |
| `-32602` | INVALID_PARAMS | 参数无效 |
| `-32603` | INTERNAL_ERROR | 服务器内部错误 |

### 应用自定义错误码（-32000 ~ -32099）

| 码 | 名称 | 说明 |
|---|------|------|
| `-32000` | MCP_ERROR | 应用通用错误 |
| `-32001` | MCP_RATE_LIMIT | 限流或并发超限 |
| `-32002` | MCP_PERMISSION | 权限拒绝 |

### 错误类型映射

| 错误码 | 错误类型 | HTTP 状态 | JSON-RPC 码 |
|--------|---------|-----------|-------------|
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

### 警告码

| 码 | 说明 |
|---|------|
| `OUTPUT_TRUNCATED` | 输出超过缓冲区限制，已截断 |
| `SLOW_OPERATION` | 操作耗时 >5s |
| `LARGE_FILE` | 文件 >1MB |
| `HIGH_MEMORY` | 内存占用较高 |
| `PARTIAL_RESULT` | 结果被截断或部分失败 |

---

## 系统 API

### get_system_info

获取系统环境信息。**（AI 工具）**

**参数**：无

**返回值**：

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `os` | str | `"windows"` / `"linux"` / `"darwin"` |
| `arch` | str | 处理器架构（`"x86_64"`、`"AMD64"`、`"arm64"`） |
| `python` | str | Python 版本 |
| `shell` | str | 检测到的 Shell（`"powershell"`、`"cmd"`、`"bash"` 等） |
| `workspace` | str | 工作区绝对路径 |
| `axon_version` | str | Axon 版本号 |

---

## 网络 API

### fetch_webpage

抓取网页正文内容，自动去除 HTML 标签。**（AI 工具）**

**参数**：

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `url` | str | ✅ | 网页 URL（http:// 或 https://） |
| `query` | str | ❌ | 搜索关键词，返回匹配段落而非全文 |

**返回值**：

```json
{
  "url": "https://example.com",
  "status": 200,
  "content": "页面正文内容...",
  "length": 12345,
  "truncated": false
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `url` | str | 请求的 URL |
| `status` | int | HTTP 状态码 |
| `content` | str | 提取的文本内容 |
| `length` | int | 返回文本长度 |
| `truncated` | bool | 是否被截断（超过 100K 字符） |

**错误**：`INVALID_PARAMETER`（URL 格式错误）、`INTERNAL_ERROR`（网络请求失败/超时）

---

### ping

健康检查。**（协议方法）**

**参数**：无

**返回值**：

```json
{"status": "ok", "uptime_seconds": 3600.5}
```

---

### list_tools

返回完整工具 Schema（用于 AI function calling）。**（协议方法）**

**参数**：无

**返回值**：

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

获取当前配置（脱敏输出）。**（协议方法）**

**参数**：无

**返回值**：

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

运行时切换工作区。**（协议方法）**

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `root_path` | str | ✓ | 新工作区绝对路径 |

**返回值**：

```json
{"root_path": "/path/to/new/workspace", "message": "工作区已切换到: /path/to/new/workspace"}
```

**副作用**：自动清空与旧工作区相关的缓存。

**错误**：`INVALID_PARAMETER` (400)、`BLOCKED_PATH` (403)、`PERMISSION_DENIED` (403)

---

### get_stats

缓存和运行时统计。**（协议方法）**

**参数**：无

**返回值**：

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

清空缓存。**（协议方法）**

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `bucket` | str\|None | ✗ | None | 缓存桶名（`"metadata"`、`"directory"`、`"search"`、`"task"`），None 清空全部 |

**返回值**：

```json
{"cleared": "all", "message": "缓存已清空: 全部"}
```

---

## 文件 API

所有文件操作强制执行工作区边界检查。相对路径基于工作区根目录解析。符号链接不允许逃逸出工作区。

### 锁类型

| 锁 | 行为 |
|---|------|
| `read` | 共享锁 — 允许多个并发读取 |
| `write` | 排他锁 — 阻止同路径的所有其他读/写 |
| `write_dual` | 双路径排他锁（源 + 目标） |
| `dir_write` | 目录排他锁 |

---

### read_file

读取文件内容，支持自动编码检测。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | str | ✓ | — | 文件路径 |
| `encoding` | str\|None | ✗ | None | 编码（None = 自动检测） |
| `line_range` | tuple[int,int]\|None | ✗ | None | 行范围 `[start, end]`，1-based 闭区间 |
| `max_size` | int\|None | ✗ | None | 最大读取字节数 |

**返回值**：

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

**错误**：`FILE_NOT_FOUND`、`SIZE_LIMIT_EXCEEDED`、`ENCODING_ERROR`、`INVALID_PARAMETER`

---

### write_file

写入文件内容。文件不存在则自动创建（含父目录）。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | str | ✓ | — | 文件路径 |
| `content` | str | ✓ | — | 文件内容 |
| `encoding` | str | ✗ | `"utf-8"` | 写入编码 |

**返回值**：

```json
{"path": "/workspace/file.txt", "size": 1234, "encoding": "utf-8"}
```

新建文件时返回值会包含 `"created": true`。

**错误**：`ENCODING_ERROR`

---

### delete_file

删除文件。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `path` | str | ✓ | 文件路径 |

**返回值**：

```json
{"path": "/workspace/file.txt", "deleted": true}
```

**错误**：`FILE_NOT_FOUND`、`INVALID_PARAMETER`（不是文件）

---

### stat_path

获取文件/目录元信息。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | str | ✓ | — | 文件/目录路径 |
| `follow_symlinks` | bool | ✗ | `true` | 是否跟踪符号链接 |

**返回值**（存在）：

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

**返回值**（不存在）：

```json
{"path": "/workspace/nonexistent", "exists": false}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `type` | str | `"file"` / `"directory"` / `"symlink"` / `"other"` |
| `size` | int | 文件大小（字节） |
| `permissions` | str | 八进制权限（如 `"0o755"`） |
| `is_symlink` | bool | 是否为符号链接 |
| `symlink_target` | str | 符号链接目标（仅当 is_symlink=true） |
| `attributes` | dict | 平台特定属性 |

---

### list_directory

列出目录内容。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | str | ✓ | — | 目录路径 |
| `pattern` | str\|None | ✗ | None | glob 过滤模式（如 `"*.py"`） |
| `recursive` | bool | ✗ | `false` | 是否递归列出子目录 |
| `include_hidden` | bool | ✗ | `false` | 是否包含隐藏文件 |
| `max_results` | int\|None | ✗ | None | 最大返回条数 |

**返回值**：

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

**错误**：`FILE_NOT_FOUND`、`INVALID_PARAMETER`（不是目录）

---

### move_file

移动/重命名文件。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `source` | str | ✓ | — | 源文件路径 |
| `dest` | str | ✓ | — | 目标路径 |
| `overwrite` | bool | ✗ | `false` | 目标存在时是否覆写 |

**返回值**：

```json
{"source": "/workspace/old.txt", "dest": "/workspace/new.txt"}
```

**错误**：`FILE_NOT_FOUND`、`CONCURRENT_MODIFICATION`（目标存在）

---

### copy_file

复制文件。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `source` | str | ✓ | — | 源文件路径 |
| `dest` | str | ✓ | — | 目标路径 |
| `overwrite` | bool | ✗ | `false` | 目标存在时是否覆写 |

**返回值**：

```json
{"source": "/workspace/file.txt", "dest": "/workspace/copy.txt", "size": 1234}
```

**错误**：`FILE_NOT_FOUND`、`CONCURRENT_MODIFICATION`（目标存在）

---

### move_directory

移动/重命名目录。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `source` | str | ✓ | 源目录路径 |
| `dest` | str | ✓ | 目标路径 |

**返回值**：

```json
{"source": "/workspace/old_dir", "dest": "/workspace/new_dir"}
```

**错误**：`FILE_NOT_FOUND`、`INVALID_PARAMETER`（不是目录）、`CONCURRENT_MODIFICATION`（目标存在）

---

### create_directory

创建目录（默认递归）。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | str | ✓ | — | 目录路径 |
| `recursive` | bool | ✗ | `true` | 是否递归创建父目录 |

**返回值**：

```json
{"path": "/workspace/new_dir", "created": true}
```

---

### delete_directory

删除目录。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | str | ✓ | — | 目录路径 |
| `recursive` | bool | ✗ | `false` | 是否递归删除子项 |
| `force` | bool | ✗ | `false` | 是否强制删除只读文件 |

**返回值**：

```json
{"path": "/workspace/old_dir", "deleted": true}
```

**错误**：`FILE_NOT_FOUND`、`INVALID_PARAMETER`（非空且 recursive=false）

---

### replace_string_in_file

在文件中查找 `old_string` 并替换为 `new_string`。`old_string` 必须精确匹配且在文件中仅出现一次。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `path` | str | ✓ | — | 文件路径 |
| `old_string` | str | ✓ | — | 要查找的原始文本（必须在文件中唯一） |
| `new_string` | str | ✓ | — | 替换为的新文本 |
| `encoding` | str | ✗ | `"utf-8"` | 文件编码 |

**返回值**：

```json
{"path": "/workspace/file.txt", "replacements": 1, "total_lines": 50}
```

**错误**：`FILE_NOT_FOUND`、`INVALID_PARAMETER`（未找到或匹配多次）、`ENCODING_ERROR`

---

### multi_replace_string_in_file

批量文本替换。`replacements` 数组中每项包含 `path`、`old_string`、`new_string`。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `replacements` | list | ✓ | — | `{path, old_string, new_string}` 数组 |
| `encoding` | str | ✗ | `"utf-8"` | 默认编码 |

**返回值**：

```json
{
  "total": 3,
  "succeeded": 2,
  "failed": 1,
  "results": [
    {"index": 0, "path": "/workspace/a.py", "success": true},
    {"index": 1, "path": "/workspace/b.py", "success": true},
    {"index": 2, "path": "/workspace/c.py", "success": false, "error": "old_string 未找到匹配"}
  ]
}
```

**错误**：`PERMISSION_DENIED`（路径超出工作区范围）

---

## 搜索 API

### find_files

按文件名或 glob 模式搜索文件。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `pattern` | str | ✓ | — | glob 模式（如 `"*.py"`、`"test_*"`） |
| `root` | str\|None | ✗ | None | 搜索根目录（None = 工作区） |
| `recursive` | bool | ✗ | `true` | 是否递归搜索子目录 |
| `file_types` | list[str]\|None | ✗ | None | 扩展名过滤（如 `[".py", ".js"]`） |
| `include_hidden` | bool | ✗ | `false` | 是否包含隐藏文件 |
| `max_results` | int\|None | ✗ | None | 最多返回匹配数 |

**返回值**：

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

**错误**：`FILE_NOT_FOUND`（根目录不存在）、`INVALID_PARAMETER`

---

### search_text

全局全文搜索（支持正则表达式）。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `query` | str | ✓ | — | 搜索词或正则表达式 |
| `root` | str\|None | ✗ | None | 搜索根目录（None = 工作区） |
| `file_pattern` | str | ✗ | `"*"` | 文件名过滤 glob |
| `case_sensitive` | bool | ✗ | `false` | 是否区分大小写 |
| `is_regex` | bool | ✗ | `false` | query 是否为正则表达式 |
| `context_lines` | int | ✗ | `2` | 上下文行数（0–50） |
| `include_hidden` | bool | ✗ | `false` | 是否搜索隐藏文件 |
| `max_results` | int\|None | ✗ | None | 最多返回匹配文件数 |

**返回值**：

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

**正则表达式**：完全支持 Python `re` 模块语法。query 长度上限 10,000 字符（ReDoS 防护）。

**错误**：`FILE_NOT_FOUND`、`INVALID_PARAMETER`（无效正则或 query 过长）

---

### find_symbol

搜索代码符号（函数、类、变量定义）。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `symbol` | str | ✓ | — | 符号名（支持正则） |
| `root` | str\|None | ✗ | None | 搜索根目录 |
| `symbol_type` | str\|None | ✗ | None | `"function"` / `"class"` / `"variable"`（None = 全部） |
| `file_pattern` | str | ✗ | `"*"` | 文件名过滤 |
| `include_hidden` | bool | ✗ | `false` | 是否搜索隐藏文件 |
| `max_results` | int\|None | ✗ | None | 最多返回符号数 |

**返回值**：

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

**支持的语言**：

| 语言 | 函数 | 类 | 变量 |
|------|------|---|------|
| Python | ✓ | ✓ | ✓ |
| JavaScript / TypeScript | ✓ | ✓ | ✓ |
| Java / C# | ✓ | ✓ | |
| Go | ✓ | ✓ | |
| Rust | ✓ | ✓ | |

**错误**：`FILE_NOT_FOUND`、`INVALID_PARAMETER`

---

## 命令 API

### 任务生命周期

```
CREATED → RUNNING → COMPLETED  (exit_code=0)
                   → FAILED     (exit_code≠0)
                   → STOPPED    (优雅停止)
                   → KILLED     (强制终止)
                   → TIMED_OUT  (超时)
```

---

### run_command

同步执行命令并等待完成。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `command` | str | ✓ | — | Shell 命令 |
| `cwd` | str\|None | ✗ | None | 工作目录（None = 工作区） |
| `timeout` | int\|None | ✗ | None | 超时毫秒数（None = 配置默认值） |
| `env` | dict\|None | ✗ | None | 额外环境变量 |

**返回值**：

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

**错误**：`BLOCKED_COMMAND` (403)、`MAX_CONCURRENT_TASKS` (429)、`TIMEOUT` (408)

---

### create_task

创建并启动异步后台任务。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `command` | str | ✓ | — | Shell 命令 |
| `cwd` | str\|None | ✗ | None | 工作目录 |
| `timeout` | int\|None | ✗ | None | 超时毫秒数 |
| `env` | dict\|None | ✗ | None | 额外环境变量 |

**返回值**：

```json
{"task_id": "a1b2c3d4e5f6", "command": "python server.py", "pid": 12345, "state": "running"}
```

**错误**：`BLOCKED_COMMAND` (403)、`MAX_CONCURRENT_TASKS` (429)

---

### stop_task

停止运行中的任务。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `task_id` | str | ✓ | — | 任务 ID |
| `force` | bool | ✗ | `false` | `false`：中断 → 等 5s → 强杀。`true`：立即强杀 |

**返回值**：完整任务字典（同 `task_status`），`state` 为 `"stopped"` 或 `"killed"`。

**错误**：`TASK_NOT_FOUND` (404)

---

### del_task

删除已完成的任务，释放内存（缓冲区 + 任务记录）。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `task_id` | str | ✓ | 任务 ID |

**返回值**：

```json
{"task_id": "a1b2c3d4e5f6", "deleted": true}
```

**错误**：`TASK_NOT_FOUND` (404)、`TASK_ALREADY_RUNNING` (409 — 需先 `stop_task`)

---

### task_status

查询任务当前状态。

**参数**：

| 参数 | 类型 | 必需 | 说明 |
|------|------|------|------|
| `task_id` | str | ✓ | 任务 ID |

**返回值**：

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

| 字段 | 类型 | 说明 |
|------|------|------|
| `state` | str | `"running"` / `"completed"` / `"failed"` / `"stopped"` / `"killed"` / `"timed_out"` |
| `exit_code` | int\|null | 退出码（运行中为 null） |
| `signal` | str\|null | 收到的信号（`"interrupt"`、`"kill"`） |
| `duration_ms` | float\|null | 运行时长（运行中为 null） |
| `stream` | dict | 每个通道的缓冲区信息 |

**错误**：`TASK_NOT_FOUND` (404)

---

### wait_task

阻塞等待任务完成（或超时）。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `task_id` | str | ✓ | — | 任务 ID |
| `timeout` | int\|None | ✗ | None | 等待超时毫秒数 |

**返回值**：同 `task_status`（任务最终状态）。

**错误**：`TASK_NOT_FOUND` (404)、`TIMEOUT` (408)

---

### list_tasks

列出所有任务。

**参数**：无

**返回值**：

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

增量读取任务标准输出（消费式）。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `task_id` | str | ✓ | — | 任务 ID |
| `max_chars` | int | ✗ | 8192 | 最多读取字符数 |

**返回值**：

```json
{"task_id": "a1b2c3d4e5f6", "output": "...自上次调用以来的新输出...", "eof": false}
```

每次调用只返回**上次以来的新数据**，已读取的数据不再返回。

**错误**：`TASK_NOT_FOUND` (404)

---

### read_stderr

增量读取任务标准错误。接口同 `read_stdout`。

---

### write_stdin

向任务标准输入写入数据。

**参数**：

| 参数 | 类型 | 必需 | 默认值 | 说明 |
|------|------|------|--------|------|
| `task_id` | str | ✓ | — | 任务 ID |
| `data` | str | ✓ | — | 要写入的文本 |
| `eof` | bool | ✗ | `false` | 写入后是否关闭 stdin |

**返回值**：

```json
{"task_id": "a1b2c3d4e5f6", "written": 10, "eof": false}
```

**错误**：`TASK_NOT_FOUND` (404)、`INVALID_PARAMETER`（stdin 不可用）

---

## 附录

### 工具总览

| 分组 | 数量 | 方法 |
|------|------|------|
| **File** | 12 | `read_file` `write_file` `delete_file` `stat_path` `list_directory` `move_file` `copy_file` `move_directory` `create_directory` `delete_directory` `replace_string_in_file` `multi_replace_string_in_file` |
| **Search** | 3 | `find_files` `search_text` `find_symbol` |
| **Command** | 10 | `run_command` `create_task` `stop_task` `del_task` `task_status` `wait_task` `list_tasks` `read_stdout` `read_stderr` `write_stdin` |
| **System** | 1 | `get_system_info` |
| **Web** | 1 | `fetch_webpage` |
| **Protocol** | 6 | `ping` `list_tools` `get_config` `set_workspace` `get_stats` `clear_cache` |

**总计**：27 个 AI 工具 + 6 个协议方法 = 33 个路由

### 写操作列表

只有以下方法会修改文件系统：

`write_file` · `delete_file` · `create_directory` · `delete_directory` · `move_file` · `copy_file` · `move_directory` · `replace_string_in_file` · `multi_replace_string_in_file`

### 流式 I/O 模式

```python
# 非阻塞增量读取 stdout
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
