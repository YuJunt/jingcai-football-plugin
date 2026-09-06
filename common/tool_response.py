#!/usr/bin/env python3
"""
MCP工具统一返回格式标准
所有工具必须返回此格式，确保workflow能统一解析
"""
import time
import traceback
from functools import wraps

TOOL_VERSION = "2.0.0"

def standard_response(tool_name: str, success: bool, data=None, error: str = None, 
                      meta: dict = None) -> dict:
    """
    生成标准工具返回格式
    
    Args:
        tool_name: 工具名称
        success: 是否成功
        data: 返回数据（成功时）
        error: 错误信息（失败时）
        meta: 元数据（执行时间等）
    
    Returns:
        标准格式字典
    """
    response = {
        'tool': tool_name,
        'success': success,
        'data': data if data is not None else {},
        'meta': {
            'version': TOOL_VERSION,
            'timestamp': time.time(),
            **(meta or {})
        }
    }
    if error:
        response['error'] = error
    return response

def ok(tool_name: str, data=None, **meta) -> dict:
    """成功响应快捷方式"""
    return standard_response(tool_name, True, data=data, meta=meta)

def fail(tool_name: str, error: str, data=None, **meta) -> dict:
    """失败响应快捷方式"""
    return standard_response(tool_name, False, data=data, error=error, meta=meta)

def safe_tool(tool_name: str):
    """
    装饰器：自动捕获异常，返回标准格式
    用法：@safe_tool('my_tool')
    """
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            start = time.time()
            try:
                result = func(*args, **kwargs)
                elapsed = time.time() - start
                # 如果已经是标准格式，直接返回
                if isinstance(result, dict) and 'tool' in result and 'success' in result:
                    result['meta']['duration'] = round(elapsed, 3)
                    return result
                # 否则包装成标准格式
                return ok(tool_name, result, duration=round(elapsed, 3))
            except Exception as e:
                elapsed = time.time() - start
                return fail(tool_name, str(e), 
                           data={'traceback': traceback.format_exc()[:500]},
                           duration=round(elapsed, 3))
        return wrapper
    return decorator

def parse_response(response: dict) -> dict:
    """
    解析工具返回，兼容新旧格式
    
    Args:
        response: 工具返回值
    
    Returns:
        标准化后的字典 {success, data, error}
    """
    if not isinstance(response, dict):
        return {'success': True, 'data': response, 'error': None}
    
    # 新格式：有tool和success字段
    if 'success' in response:
        return {
            'success': response['success'],
            'data': response.get('data', {}),
            'error': response.get('error'),
            'meta': response.get('meta', {})
        }
    
    # 旧格式1：{'success': True, 'data': {...}}
    if 'data' in response and 'success' not in response:
        return {'success': True, 'data': response['data'], 'error': None}
    
    # 旧格式2：直接返回数据
    return {'success': True, 'data': response, 'error': None}
