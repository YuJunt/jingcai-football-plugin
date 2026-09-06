#!/usr/bin/env python3
"""
统一错误处理模块
为所有MCP工具提供统一的错误处理、输入验证和结构化响应
"""
import functools
import traceback
import sys
import json
from typing import Any, Callable, Dict, Optional


def make_error_response(
    error: str,
    error_type: str = "unknown",
    suggestion: str = "",
    details: Optional[Dict] = None
) -> Dict[str, Any]:
    """
    生成统一格式的错误响应

    Args:
        error: 错误描述
        error_type: 错误类型 (validation/runtime/value_error/type_error/unknown)
        suggestion: 修复建议
        details: 额外详情

    Returns:
        结构化错误响应字典
    """
    response = {
        "success": False,
        "error": error,
        "error_type": error_type,
        "suggestion": suggestion,
    }
    if details:
        response["details"] = details
    return response


def make_success_response(data: Any, message: str = "") -> Dict[str, Any]:
    """
    生成统一格式的成功响应

    Args:
        data: 响应数据
        message: 可选消息

    Returns:
        结构化成功响应字典
    """
    response = {
        "success": True,
        "data": data,
    }
    if message:
        response["message"] = message
    return response


def validate_required(params: Dict, required_fields: list) -> Optional[Dict]:
    """
    验证必填参数

    Args:
        params: 参数字典
        required_fields: 必填字段列表

    Returns:
        如果有缺失字段返回错误响应，否则返回None
    """
    missing = []
    for field in required_fields:
        if field not in params or params[field] is None:
            missing.append(field)

    if missing:
        return make_error_response(
            error=f"缺少必填参数: {', '.join(missing)}",
            error_type="validation",
            suggestion=f"请提供以下参数: {', '.join(missing)}"
        )
    return None


def validate_type(value: Any, expected_type: type, field_name: str) -> Optional[Dict]:
    """
    验证参数类型

    Args:
        value: 参数值
        expected_type: 期望类型
        field_name: 字段名

    Returns:
        如果类型错误返回错误响应，否则返回None
    """
    if not isinstance(value, expected_type):
        return make_error_response(
            error=f"参数 {field_name} 类型错误: 期望 {expected_type.__name__}, 实际 {type(value).__name__}",
            error_type="validation",
            suggestion=f"请确保 {field_name} 是 {expected_type.__name__} 类型"
        )
    return None


def validate_range(value: float, min_val: float, max_val: float, field_name: str) -> Optional[Dict]:
    """
    验证数值范围

    Args:
        value: 数值
        min_val: 最小值
        max_val: 最大值
        field_name: 字段名

    Returns:
        如果超出范围返回错误响应，否则返回None
    """
    if value < min_val or value > max_val:
        return make_error_response(
            error=f"参数 {field_name} 超出范围: 期望 [{min_val}, {max_val}], 实际 {value}",
            error_type="validation",
            suggestion=f"请确保 {field_name} 在 {min_val} 到 {max_val} 之间"
        )
    return None


def safe_tool(func: Callable) -> Callable:
    """
    MCP工具安全执行装饰器
    自动捕获所有异常，返回结构化错误信息，避免MCP通信中断

    使用方式:
        @mcp.tool()
        @safe_tool
        def my_tool(param1: str, param2: int) -> Dict:
            # 工具逻辑
            return {"result": ...}

    Args:
        func: 被装饰的工具函数

    Returns:
        包装后的函数
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
            # 如果工具已经返回了带success字段的字典，直接返回
            if isinstance(result, dict) and "success" in result:
                return result
            # 否则包装成成功响应
            return make_success_response(result)
        except ValueError as e:
            error_msg = str(e)
            print(f"[ValueError] {func.__name__}: {error_msg}", file=sys.stderr)
            return make_error_response(
                error=error_msg,
                error_type="value_error",
                suggestion="请检查输入参数的值是否合理"
            )
        except TypeError as e:
            error_msg = str(e)
            print(f"[TypeError] {func.__name__}: {error_msg}", file=sys.stderr)
            return make_error_response(
                error=error_msg,
                error_type="type_error",
                suggestion="请检查输入参数的类型是否正确"
            )
        except KeyError as e:
            error_msg = f"缺少关键字段: {e}"
            print(f"[KeyError] {func.__name__}: {error_msg}", file=sys.stderr)
            return make_error_response(
                error=error_msg,
                error_type="key_error",
                suggestion="请确保输入数据包含所有必需字段"
            )
        except FileNotFoundError as e:
            error_msg = str(e)
            print(f"[FileNotFoundError] {func.__name__}: {error_msg}", file=sys.stderr)
            return make_error_response(
                error=error_msg,
                error_type="file_not_found",
                suggestion="请检查文件路径是否正确，文件是否存在"
            )
        except json.JSONDecodeError as e:
            error_msg = f"JSON解析失败: {e}"
            print(f"[JSONDecodeError] {func.__name__}: {error_msg}", file=sys.stderr)
            return make_error_response(
                error=error_msg,
                error_type="json_error",
                suggestion="请检查JSON格式是否正确"
            )
        except Exception as e:
            error_msg = str(e)
            tb = traceback.format_exc()
            print(f"[Exception] {func.__name__}: {error_msg}", file=sys.stderr)
            print(tb, file=sys.stderr)
            return make_error_response(
                error=error_msg,
                error_type="runtime",
                suggestion="工具执行时发生未知错误，请检查输入参数或稍后重试",
                details={"traceback": tb[-500:] if len(tb) > 500 else tb}
            )

    return wrapper


# 便捷导入
__all__ = [
    'make_error_response',
    'make_success_response',
    'validate_required',
    'validate_type',
    'validate_range',
    'safe_tool',
]
