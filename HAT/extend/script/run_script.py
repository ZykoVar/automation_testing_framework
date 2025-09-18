"""
脚本执行工具模块

该模块提供了动态执行Python脚本字符串的功能，
可以用于执行测试用例中的前置和后置脚本。
"""

from typing import Any, Dict, Optional


def exec_script(script: Optional[str], context: Dict[str, Any]) -> None:
    """
    执行Python脚本字符串
    
    该函数使用Python内置的exec()函数来动态执行传入的脚本字符串。
    脚本可以访问名为"context"的全局变量，其中包含传入的上下文数据。
    
    Args:
        script: 要执行的Python脚本字符串，如果为None则不执行任何操作
        context: 脚本可以访问的上下文数据字典
        
    Returns:
        None
        
    Example:
        >>> context_data = {"name": "Alice", "value": 42}
        >>> script_code = "print(f'Hello {context[\"name\"]}, value is {context[\"value\"]}')"
        >>> exec_script(script_code, context_data)
        Hello Alice, value is 42
        
    Note:
        使用exec()函数执行动态脚本可能存在安全风险，
        应确保脚本内容是可信的。
    """
    # 如果脚本为空，则直接返回
    if script is None:
        return
    
    # 执行脚本，将context作为全局命名空间中的变量提供给脚本使用
    exec(script, {"context": context})
