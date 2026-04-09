"""
Layer 5: Middleware — 参数校验中间件

职责:
- 检查必选参数是否存在
- 检查参数类型（str/int/bool/dict/list）
- 检查数值范围（行号 ≥ 1, max_results > 0 等）
- 检查字符串非空（command/content 等关键参数）
- 尝试自动类型强转（str→int, str→bool）

校验失败统一抛 InvalidParameterError，不调用 next。

依赖:
- Layer 1: core (InvalidParameterError)
- Layer 4: handlers/base (RequestContext)
"""

from __future__ import annotations

import logging
from typing import Any

from ..core.errors import InvalidParameterError
from ..handlers.base import RequestContext
from .chain import NextFunc

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════
#  参数 Schema 定义
# ═══════════════════════════════════════════════════════

# 类型映射
STR = "str"
INT = "int"
FLOAT = "float"
BOOL = "bool"
DICT = "dict"
LIST = "list"
STR_OR_NONE = "str|None"
INT_OR_NONE = "int|None"
FLOAT_OR_NONE = "float|None"
BOOL_OR_NONE = "bool|None"
DICT_OR_NONE = "dict|None"
LIST_OR_NONE = "list|None"
TUPLE_INT_INT_OR_NONE = "tuple[int,int]|None"


class _Param:
    """参数定义"""

    __slots__ = ("name", "type", "required", "default", "min_value", "max_value", "non_empty")

    def __init__(
        self,
        name: str,
        type: str,
        required: bool = True,
        default: Any = None,
        min_value: int | float | None = None,
        max_value: int | float | None = None,
        non_empty: bool = False,
    ):
        self.name = name
        self.type = type
        self.required = required
        self.default = default
        self.min_value = min_value
        self.max_value = max_value
        self.non_empty = non_empty  # str 不可为空


def _p(
    name: str,
    type: str = STR,
    required: bool = True,
    default: Any = None,
    min_value: int | float | None = None,
    max_value: int | float | None = None,
    non_empty: bool = False,
) -> _Param:
    """快捷构建参数定义"""
    return _Param(
        name=name,
        type=type,
        required=required,
        default=default,
        min_value=min_value,
        max_value=max_value,
        non_empty=non_empty,
    )


# ── 每个方法的参数定义 ──

_METHOD_SCHEMAS: dict[str, list[_Param]] = {
    # ═══ FileHandler ═══
    "read_file": [
        _p("path", STR, required=True, non_empty=True),
        _p("encoding", STR_OR_NONE, required=False),
        _p("line_range", TUPLE_INT_INT_OR_NONE, required=False),
        _p("max_size", INT_OR_NONE, required=False, min_value=1),
    ],
    "stat_path": [
        _p("path", STR, required=True, non_empty=True),
        _p("follow_symlinks", BOOL, required=False, default=True),
    ],
    "exists": [
        _p("path", STR, required=True, non_empty=True),
    ],
    "list_directory": [
        _p("path", STR, required=True, non_empty=True),
        _p("pattern", STR_OR_NONE, required=False),
        _p("recursive", BOOL, required=False, default=False),
        _p("include_hidden", BOOL, required=False, default=False),
        _p("max_results", INT_OR_NONE, required=False, min_value=1),
    ],
    "create_file": [
        _p("path", STR, required=True, non_empty=True),
        _p("content", STR, required=False, default=""),
        _p("encoding", STR, required=False, default="utf-8"),
        _p("overwrite", BOOL, required=False, default=False),
    ],
    "write_file": [
        _p("path", STR, required=True, non_empty=True),
        _p("content", STR, required=True),
        _p("encoding", STR, required=False, default="utf-8"),
    ],
    "create_directory": [
        _p("path", STR, required=True, non_empty=True),
        _p("recursive", BOOL, required=False, default=True),
    ],
    "replace_range": [
        _p("path", STR, required=True, non_empty=True),
        _p("start_line", INT, required=True, min_value=1),
        _p("end_line", INT, required=True, min_value=1),
        _p("new_text", STR, required=True),
        _p("encoding", STR, required=False, default="utf-8"),
    ],
    "insert_text": [
        _p("path", STR, required=True, non_empty=True),
        _p("line", INT, required=True, min_value=1),
        _p("text", STR, required=True),
        _p("encoding", STR, required=False, default="utf-8"),
    ],
    "delete_range": [
        _p("path", STR, required=True, non_empty=True),
        _p("start_line", INT, required=True, min_value=1),
        _p("end_line", INT, required=True, min_value=1),
        _p("encoding", STR, required=False, default="utf-8"),
    ],
    "apply_patch": [
        _p("path", STR, required=True, non_empty=True),
        _p("patch", STR, required=True, non_empty=True),
        _p("dry_run", BOOL, required=False, default=False),
        _p("encoding", STR, required=False, default="utf-8"),
    ],
    "move_file": [
        _p("source", STR, required=True, non_empty=True),
        _p("dest", STR, required=True, non_empty=True),
        _p("overwrite", BOOL, required=False, default=False),
    ],
    "copy_file": [
        _p("source", STR, required=True, non_empty=True),
        _p("dest", STR, required=True, non_empty=True),
        _p("overwrite", BOOL, required=False, default=False),
    ],
    "delete_file": [
        _p("path", STR, required=True, non_empty=True),
    ],
    "move_directory": [
        _p("source", STR, required=True, non_empty=True),
        _p("dest", STR, required=True, non_empty=True),
    ],
    "delete_directory": [
        _p("path", STR, required=True, non_empty=True),
        _p("recursive", BOOL, required=False, default=False),
        _p("force", BOOL, required=False, default=False),
    ],

    # ═══ CommandHandler ═══
    "run_command": [
        _p("command", STR, required=True, non_empty=True),
        _p("cwd", STR_OR_NONE, required=False),
        _p("timeout", INT_OR_NONE, required=False, min_value=1),
        _p("env", DICT_OR_NONE, required=False),
    ],
    "create_task": [
        _p("command", STR, required=True, non_empty=True),
        _p("cwd", STR_OR_NONE, required=False),
        _p("timeout", INT_OR_NONE, required=False, min_value=1),
        _p("env", DICT_OR_NONE, required=False),
    ],
    "stop_task": [
        _p("task_id", STR, required=True, non_empty=True),
        _p("signal", STR, required=False, default="interrupt"),
    ],
    "kill_task": [
        _p("task_id", STR, required=True, non_empty=True),
    ],
    "get_task": [
        _p("task_id", STR, required=True, non_empty=True),
    ],
    "wait_task": [
        _p("task_id", STR, required=True, non_empty=True),
        _p("timeout", INT_OR_NONE, required=False, min_value=1),
    ],
    "list_tasks": [],
    "read_stdout": [
        _p("task_id", STR, required=True, non_empty=True),
        _p("max_chars", INT, required=False, default=8192, min_value=1),
    ],
    "read_stderr": [
        _p("task_id", STR, required=True, non_empty=True),
        _p("max_chars", INT, required=False, default=8192, min_value=1),
    ],
    "write_stdin": [
        _p("task_id", STR, required=True, non_empty=True),
        _p("data", STR, required=True),
        _p("eof", BOOL, required=False, default=False),
    ],

    # ═══ SearchHandler ═══
    "search_files": [
        _p("pattern", STR, required=True, non_empty=True),
        _p("root", STR_OR_NONE, required=False),
        _p("recursive", BOOL, required=False, default=True),
        _p("file_types", LIST_OR_NONE, required=False),
        _p("include_hidden", BOOL, required=False, default=False),
        _p("max_results", INT_OR_NONE, required=False, min_value=1),
    ],
    "search_content": [
        _p("query", STR, required=True, non_empty=True),
        _p("root", STR_OR_NONE, required=False),
        _p("file_pattern", STR, required=False, default="*"),
        _p("case_sensitive", BOOL, required=False, default=False),
        _p("is_regex", BOOL, required=False, default=False),
        _p("context_lines", INT, required=False, default=2, min_value=0, max_value=50),
        _p("include_hidden", BOOL, required=False, default=False),
        _p("max_results", INT_OR_NONE, required=False, min_value=1),
    ],
    "search_symbol": [
        _p("symbol", STR, required=True, non_empty=True),
        _p("root", STR_OR_NONE, required=False),
        _p("symbol_type", STR_OR_NONE, required=False),
        _p("file_pattern", STR, required=False, default="*"),
        _p("include_hidden", BOOL, required=False, default=False),
        _p("max_results", INT_OR_NONE, required=False, min_value=1),
    ],

    # ═══ SystemHandler ═══
    "ping": [],
    "get_version": [],
    "get_methods": [],
    "get_config": [],
    "set_workspace": [
        _p("root_path", STR, required=True, non_empty=True),
    ],
    "get_stats": [],
    "clear_cache": [
        _p("bucket", STR_OR_NONE, required=False),
    ],
}


# ═══════════════════════════════════════════════════════
#  类型强转
# ═══════════════════════════════════════════════════════

_BOOL_TRUE = frozenset({"true", "1", "yes", "on"})
_BOOL_FALSE = frozenset({"false", "0", "no", "off"})


def _coerce_value(value: Any, target_type: str, param_name: str) -> Any:
    """
    尝试将 JSON-RPC 传入的值转为目标类型

    JSON-RPC 的参数都是 JSON 基本类型 (str/int/float/bool/list/dict/null),
    但有些客户端可能将 int 作为 str 传入（如 "123"）。

    Args:
        value: 原始值
        target_type: 目标类型字符串
        param_name: 参数名（用于错误信息）

    Returns:
        转换后的值

    Raises:
        InvalidParameterError: 类型不匹配且无法转换
    """
    # None 值的处理
    if value is None:
        if "|None" in target_type:
            return None
        raise InvalidParameterError(
            f"参数 '{param_name}' 不可为 null",
            details={"param": param_name, "expected_type": target_type},
        )

    base_type = target_type.replace("|None", "")

    # str 类型
    if base_type == "str":
        if isinstance(value, str):
            return value
        # 数字/bool → str
        return str(value)

    # int 类型
    if base_type == "int":
        if isinstance(value, int) and not isinstance(value, bool):
            return value
        if isinstance(value, str):
            try:
                return int(value)
            except ValueError:
                pass
        if isinstance(value, float) and value == int(value):
            return int(value)
        raise InvalidParameterError(
            f"参数 '{param_name}' 类型错误: 期望 int，得到 {type(value).__name__}={value!r}",
            details={"param": param_name, "expected_type": "int", "actual_type": type(value).__name__},
        )

    # float 类型
    if base_type == "float":
        if isinstance(value, float):
            return value
        if isinstance(value, int) and not isinstance(value, bool):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except ValueError:
                pass
        raise InvalidParameterError(
            f"参数 '{param_name}' 类型错误: 期望 float，得到 {type(value).__name__}={value!r}",
            details={"param": param_name, "expected_type": "float", "actual_type": type(value).__name__},
        )

    # bool 类型
    if base_type == "bool":
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            low = value.lower()
            if low in _BOOL_TRUE:
                return True
            if low in _BOOL_FALSE:
                return False
        if isinstance(value, int):
            return bool(value)
        raise InvalidParameterError(
            f"参数 '{param_name}' 类型错误: 期望 bool，得到 {type(value).__name__}={value!r}",
            details={"param": param_name, "expected_type": "bool", "actual_type": type(value).__name__},
        )

    # dict 类型
    if base_type == "dict":
        if isinstance(value, dict):
            return value
        raise InvalidParameterError(
            f"参数 '{param_name}' 类型错误: 期望 dict，得到 {type(value).__name__}",
            details={"param": param_name, "expected_type": "dict", "actual_type": type(value).__name__},
        )

    # list 类型
    if base_type == "list":
        if isinstance(value, list):
            return value
        raise InvalidParameterError(
            f"参数 '{param_name}' 类型错误: 期望 list，得到 {type(value).__name__}",
            details={"param": param_name, "expected_type": "list", "actual_type": type(value).__name__},
        )

    # tuple[int,int] — JSON 中用 [start, end] 数组表示
    if base_type == "tuple[int,int]":
        if isinstance(value, (list, tuple)):
            if len(value) != 2:
                raise InvalidParameterError(
                    f"参数 '{param_name}' 需要恰好 2 个元素 [start, end]，得到 {len(value)} 个",
                    details={"param": param_name, "length": len(value)},
                )
            try:
                return (int(value[0]), int(value[1]))
            except (ValueError, TypeError):
                raise InvalidParameterError(
                    f"参数 '{param_name}' 的元素必须是整数: {value!r}",
                    details={"param": param_name, "value": str(value)},
                )
        raise InvalidParameterError(
            f"参数 '{param_name}' 类型错误: 期望 [start, end] 数组，得到 {type(value).__name__}",
            details={"param": param_name, "expected_type": "array[int,int]", "actual_type": type(value).__name__},
        )

    # 未知类型 — 不做转换，透传
    return value


# ═══════════════════════════════════════════════════════
#  ValidationMiddleware
# ═══════════════════════════════════════════════════════

class ValidationMiddleware:
    """
    参数校验中间件

    对每个请求:
    1. 根据 method 名查找参数 schema
    2. 检查必选参数是否存在
    3. 尝试类型强转
    4. 检查数值范围
    5. 检查字符串非空
    6. 填充缺省值

    对未注册的方法（schema 中没有的），透传不校验。
    """

    def __init__(self, strict: bool = False) -> None:
        """
        Args:
            strict: 严格模式下，如果请求参数中包含 schema 中未定义的字段，
                    会抛 InvalidParameterError。默认 False（忽略未知参数）。
        """
        self._strict = strict

    async def __call__(
        self, ctx: RequestContext, next_handler: NextFunc
    ) -> dict[str, Any]:
        schema = _METHOD_SCHEMAS.get(ctx.method)
        if schema is None:
            # 未注册的方法 — 可能是系统内部方法，透传
            logger.debug("方法 '%s' 无参数 schema，跳过校验", ctx.method)
            return await next_handler(ctx)

        # 空 schema = 不需要任何参数（但严格模式仍需检查未知参数）
        if not schema and not self._strict:
            return await next_handler(ctx)

        params = ctx.params
        known_names = set()

        for param_def in schema:
            known_names.add(param_def.name)
            value = params.get(param_def.name)

            # ── 1. 必选检查 ──
            if param_def.required and param_def.name not in params:
                raise InvalidParameterError(
                    f"缺少必选参数: '{param_def.name}'",
                    details={
                        "param": param_def.name,
                        "method": ctx.method,
                    },
                    suggestion=f"请提供 '{param_def.name}' 参数",
                )

            # ── 2. 缺省值填充 ──
            if param_def.name not in params:
                if param_def.default is not None:
                    params[param_def.name] = param_def.default
                continue

            # ── 3. 类型强转 ──
            value = _coerce_value(value, param_def.type, param_def.name)
            params[param_def.name] = value

            # 如果值为 None（nullable 类型）则跳过后续检查
            if value is None:
                continue

            # ── 4. 非空字符串检查 ──
            if param_def.non_empty and isinstance(value, str):
                stripped = value.strip()
                if not stripped:
                    raise InvalidParameterError(
                        f"参数 '{param_def.name}' 不可为空字符串",
                        details={"param": param_def.name, "method": ctx.method},
                    )

            # ── 5. 数值范围检查 ──
            if isinstance(value, (int, float)):
                if param_def.min_value is not None and value < param_def.min_value:
                    raise InvalidParameterError(
                        f"参数 '{param_def.name}' 值过小: {value}，最小值 {param_def.min_value}",
                        details={
                            "param": param_def.name,
                            "value": value,
                            "min": param_def.min_value,
                        },
                    )
                if param_def.max_value is not None and value > param_def.max_value:
                    raise InvalidParameterError(
                        f"参数 '{param_def.name}' 值过大: {value}，最大值 {param_def.max_value}",
                        details={
                            "param": param_def.name,
                            "value": value,
                            "max": param_def.max_value,
                        },
                    )

        # ── 6. 未知参数检查（严格模式）──
        if self._strict:
            unknown = set(params.keys()) - known_names
            if unknown:
                raise InvalidParameterError(
                    f"未知参数: {', '.join(sorted(unknown))}",
                    details={
                        "unknown_params": sorted(unknown),
                        "method": ctx.method,
                        "known_params": sorted(known_names),
                    },
                )

        return await next_handler(ctx)


def get_method_schema(method: str) -> list[_Param] | None:
    """查询指定方法的参数 schema（供外部使用，如自动生成文档）"""
    return _METHOD_SCHEMAS.get(method)


def get_registered_methods() -> list[str]:
    """返回所有已注册 schema 的方法名"""
    return sorted(_METHOD_SCHEMAS.keys())
