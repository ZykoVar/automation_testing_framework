"""
API测试用例上下文模块

该模块提供了API测试用例的上下文管理功能，
包括HTTP会话管理和API关键字初始化。
"""

from typing import Optional

import requests

from HAT.core.global_context import GlobalContext
from HAT.keywords.api_keywords import ApiKeywords

# 全局请求会话对象，用于会话复用
_global_request_object: Optional[requests.Session] = None


class ApiCaseContext:
    """
    API测试用例上下文类
    
    该类负责管理API测试用例的上下文信息，
    包括HTTP请求会话和API关键字对象的初始化。
    
    Attributes:
        keywords: API关键字对象
        request: HTTP请求会话对象
    """

    def __init__(self) -> None:
        """
        初始化API测试用例上下文
        """
        self.keywords: Optional[ApiKeywords] = None
        self.request: Optional[requests.Session] = None

    def init_keywords(self) -> ApiKeywords:
        """
        初始化API关键字对象
        
        根据全局上下文中的会话复用配置决定是否复用HTTP会话。
        如果启用了会话复用且全局会话对象不存在，则创建新的会话对象；
        否则创建新的独立会话对象。
        
        Returns:
            ApiKeywords: 初始化后的API关键字对象
            
        Example:
            >>> context = ApiCaseContext()
            >>> keywords = context.init_keywords()
        """
        # 从全局上下文中获取会话复用配置
        session_reuse = GlobalContext().get_context("session_reuse")

        # 根据配置决定是否复用会话
        if session_reuse is not None and session_reuse is True:
            global _global_request_object
            # 如果全局会话对象不存在，则创建新的会话
            if _global_request_object is None:
                _global_request_object = requests.session()
            self.request = _global_request_object
        else:
            # 创建新的独立会话对象
            self.request = requests.session()

        # 初始化API关键字对象
        self.keywords = ApiKeywords(self.request)
        return self.keywords
