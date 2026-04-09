# Axon

<div align="center">

<h3>⚡ 轻量级跨平台 MCP Server</h3>

**为 AI 助手设计的 JSON-RPC 2.0 文件与命令操作服务**

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)
[![Platform](https://img.shields.io/badge/Platform-Windows%20|%20Linux%20|%20macOS-blue.svg)]()

[**English**](README.md)

</div>

---

## ✨ Axon 是什么？

Axon 是一个轻量级 **MCP (Model Context Protocol)** 服务器，通过 JSON-RPC 2.0 协议（TCP / Stdio），为 AI 助手提供文件读写、代码搜索、命令执行和异步任务管理能力。

| 特性 | 说明 |
|------|------|
| 📁 **文件操作** | 读写、创建、删除、移动、复制、补丁 — 自动编码检测 |
| 🔍 **代码搜索** | 按 glob 搜文件、按文本/正则搜内容、跨语言搜符号 |
| ⚙️ **命令执行** | 同步执行或异步任务管理，支持流式读取 stdout/stderr |
| 🔒 **内置安全** | 路径边界、危险命令拦截（50+ 模式）、限流 |
| 🧩 **插件架构** | 新增工具只需添加一个 `.py` 文件，无需改核心代码 |
| 🌐 **跨平台** | Windows / Linux / macOS，平台差异透明处理 |

## 🏗️ 架构

```
┌──────────────────────────────────────────────────┐
│  Layer 6: 协议层                                  │
│  JSON-RPC 2.0 Server（TCP / Stdio）              │
├──────────────────────────────────────────────────┤
│  Layer 5: 中间件                                  │
│  安全 → 校验 → 限流 → 并发控制 → 审计            │
├──────────────────────────────────────────────────┤
│  Layer 4: 处理器                                  │
│  File · Search · Command · System                │
├──────────────────────────────────────────────────┤
│  Layer 3: 流管理                                  │
│  进程 stdout/stderr 生命周期管理                  │
├──────────────────────────────────────────────────┤
│  Layer 2: 平台抽象                                │
│  编码 · 信号 · 文件系统 · 默认值                  │
├──────────────────────────────────────────────────┤
│  Layer 1: 核心                                    │
│  配置 · 安全 · 缓存 · 错误 · 文件锁              │
└──────────────────────────────────────────────────┘
```

严格的向下依赖 — 零循环引用，每层只依赖下层。

## 🚀 快速开始

### 环境要求

- Python 3.10+
- pip

### 安装依赖

```bash
pip install pydantic aiofiles
```

### 启动

```bash
# TCP 模式（默认，端口 9100）
python -m src

# 指定工作区和端口
python -m src --workspace /path/to/project --port 9100

# Stdio 模式（用于管道/进程通信）
python -m src --transport stdio
```

### 发送请求

```bash
# TCP: 发送 JSON-RPC 请求（每行一个 JSON）
echo '{"jsonrpc":"2.0","method":"ping","params":{},"id":1}' | nc localhost 9100
```

```json
{"jsonrpc":"2.0","id":1,"result":{"status":"ok","uptime_seconds":42.1}}
```

## 🛠️ 工具列表

Axon 提供 **28 个 AI 工具**（自动发现插件）和 **6 个协议方法**（服务端管理）。

### 文件（14）

| 方法 | 说明 |
|------|------|
| `read_file` | 读取文件内容，自动检测编码 |
| `write_file` | 覆写已有文件 |
| `create_file` | 创建新文件（可选覆写） |
| `delete_file` | 删除文件 |
| `stat_path` | 获取文件/目录元信息 |
| `list_directory` | 列出目录内容，支持 glob 过滤 |
| `move_file` | 移动/重命名文件 |
| `copy_file` | 复制文件 |
| `move_directory` | 移动/重命名目录 |
| `create_directory` | 创建目录（递归） |
| `delete_directory` | 删除目录（递归 + 强制选项） |
| `replace_range` | 替换文件中指定行 |
| `insert_text` | 在指定行插入文本 |
| `delete_range` | 删除指定行范围 |

### 搜索（3）

| 方法 | 说明 |
|------|------|
| `find_files` | 按 glob 模式搜索文件 |
| `search_text` | 在文件内容中搜索文本/正则，附带上下文 |
| `find_symbol` | 搜索代码符号（函数、类、变量），支持 Python、JS/TS、Rust、Go、Java、C# |

### 命令（10）

| 方法 | 说明 |
|------|------|
| `run_command` | 执行命令并等待完成 |
| `create_task` | 创建异步任务，返回 task_id |
| `stop_task` | 停止任务 — 默认优雅停止（中断 → 5s → 强杀），`force=true` 立即强杀 |
| `del_task` | 删除已完成任务，释放内存 |
| `task_status` | 查询任务状态 |
| `wait_task` | 等待任务完成 |
| `list_tasks` | 列出所有任务 |
| `read_stdout` | 读取任务标准输出（消费式，增量读取） |
| `read_stderr` | 读取任务标准错误（消费式，增量读取） |
| `write_stdin` | 写入任务标准输入 |

### 系统（1）

| 方法 | 说明 |
|------|------|
| `get_system_info` | 返回操作系统、架构、Python 版本、Shell、工作区、Axon 版本 |

### 协议方法（6）

服务端管理方法 — 不会注入 AI 工具列表，但可通过 JSON-RPC 调用。

| 方法 | 说明 |
|------|------|
| `ping` | 健康检查 |
| `list_tools` | 列出所有已注册的 AI 工具，包含完整 JSON Schema |
| `get_config` | 当前配置（脱敏输出） |
| `set_workspace` | 运行时切换工作区 |
| `get_stats` | 缓存和任务统计 |
| `clear_cache` | 清空缓存 |

## ⚙️ 配置

### 命令行参数

| 参数 | 简写 | 默认值 | 说明 |
|------|------|--------|------|
| `--config` | `-c` | — | 配置文件路径（JSON） |
| `--transport` | `-t` | `tcp` | 传输模式：`tcp` 或 `stdio` |
| `--host` | — | `127.0.0.1` | TCP 监听地址 |
| `--port` | `-p` | `9100` | TCP 监听端口 |
| `--workspace` | `-w` | `.` | 工作区根路径 |
| `--log-level` | — | `INFO` | 日志级别 |

### 配置文件（JSON）

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

## 🔒 安全机制

- **路径边界** — 所有文件操作限制在工作区内，防止符号链接逃逸
- **命令拦截** — 50+ 正则模式检测危险命令（rm -rf、format、反向 shell、提权等）
- **环境变量黑名单** — 阻止通过 LD_PRELOAD、PATH、PYTHONPATH 等注入
- **限流** — 滑动窗口：全局 ~10 req/s，写操作更严格
- **并发控制** — 读写锁防止数据竞争，排序双锁防止死锁
- **审计日志** — 每个请求记录方法、耗时、成功/失败

## 📁 项目结构

```
Axon/
├── src/
│   ├── __init__.py          # 版本号
│   ├── __main__.py          # CLI 入口
│   ├── core/                # L1: 配置、安全、缓存、错误、文件锁、资源管理
│   ├── platform/            # L2: 编码、信号、文件系统、平台默认值
│   ├── stream/              # L3: 输出缓冲区、流管理器
│   ├── handlers/            # L4: 文件、搜索、命令、系统处理器
│   ├── middleware/          # L5: 安全、校验、限流、并发、审计
│   ├── protocol/            # L6: JSON-RPC 编解码、路由、服务器、传输
│   └── tools/               # 工具定义（自动发现插件）
│       ├── file/            # 14 个文件工具
│       ├── search/          # 3 个搜索工具
│       ├── command/         # 10 个命令工具
│       └── system/          # 1 个系统工具
└── tests/                   # 测试套件
```

## 🤝 协议

**JSON-RPC 2.0**，行分隔 JSON（每条消息 = 一行 JSON + `\n`）。

**请求：**
```json
{"jsonrpc": "2.0", "method": "read_file", "params": {"path": "hello.txt"}, "id": 1}
```

**响应：**
```json
{"jsonrpc": "2.0", "id": 1, "result": {"path": "/workspace/hello.txt", "content": "Hello!", "encoding": "utf-8", "size": 6, "lines": 1, "truncated": false}}
```

**错误：**
```json
{"jsonrpc": "2.0", "id": 1, "error": {"code": -32002, "message": "路径不在工作区内", "data": {"code": "PATH_OUTSIDE_WORKSPACE"}}}
```

支持批量请求（请求数组）和通知（无 id 的请求）。

## License

[MIT](LICENSE)
