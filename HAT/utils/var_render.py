"""
变量渲染工具模块

该模块提供了基于Jinja2模板引擎的变量替换功能，
可以将字符串中的模板变量替换为上下文中的实际值。
"""

from typing import Any, Dict, Optional, Union

from jinja2 import Template


def refresh(target: Optional[Union[str, Any]], context: Dict[str, Any]) -> Optional[str]:
    """
    使用Jinja2模板引擎渲染字符串，将模板中的变量替换为上下文中的实际值
    
    该函数支持使用Jinja2语法的模板字符串，如{{ variable_name }}，
    并使用提供的上下文字典进行变量替换。
    
    Args:
        target: 目标模板字符串，可以包含Jinja2格式的变量占位符，如{{ variable_name }}
                如果为None，则直接返回None
        context: 包含变量名和对应值的字典，用于替换模板中的变量占位符
        
    Returns:
        str: 渲染后的字符串，其中所有变量占位符都被替换为对应的值
        None: 如果输入的target为None，则返回None
        
    Example:
        >>> template = "Hello, {{ name }}! Today is {{ date }}."
        >>> data_context = {"name": "Alice", "date": "2023-01-01"}
        >>> refresh(template, data_context)
        'Hello, Alice! Today is 2023-01-01.'
        
        >>> refresh(None, data_context)
        None
    """
    # 如果目标字符串为None，直接返回None
    if target is None:
        return None
    
    # 将目标转换为字符串并使用Jinja2模板进行渲染
    return Template(str(target)).render(context)
