"""
Web测试用例上下文模块

该模块提供了Web测试用例的上下文管理功能，
包括WebDriver会话管理和Web关键字初始化。
"""

from typing import Optional

from selenium import webdriver

from HAT.core.global_context import GlobalContext
from HAT.keywords.api_keywords import ApiKeywords
from HAT.keywords.web_keywords import WebKeywords

# 全局WebDriver对象，用于会话复用
_global_driver_object = None


class WebCaseContext:
    """
    Web测试用例上下文类
    
    该类负责管理Web测试用例的上下文信息，
    包括WebDriver会话和Web关键字对象的初始化。
    
    Attributes:
        keywords: Web关键字对象
        driver: WebDriver对象
    """

    def __init__(self) -> None:
        """
        初始化Web测试用例上下文
        """
        self.keywords: Optional[ApiKeywords] = None
        self.driver = None

    def init_keywords(self) -> WebKeywords:
        """
        初始化Web关键字对象
        
        根据全局上下文中的WebDriver复用配置决定是否复用WebDriver会话。
        如果启用了会话复用且全局WebDriver对象不存在，则创建新的WebDriver对象；
        否则创建新的独立WebDriver对象。
        
        Returns:
            WebKeywords: 初始化后的Web关键字对象
            
        Example:
            >>> context = WebCaseContext()
            >>> keywords = context.init_keywords()
        """
        # 从全局上下文中获取WebDriver复用配置
        driver_reuse = GlobalContext().get_context("driver_reuse")

        # 根据配置决定是否复用WebDriver
        if driver_reuse is not None and driver_reuse is True:
            global _global_driver_object
            # 如果全局WebDriver对象不存在，则创建新的WebDriver
            if _global_driver_object is None:
                _global_driver_object = webdriver.Chrome()
            self.driver = _global_driver_object
        else:
            # 创建新的独立WebDriver对象
            self.driver = webdriver.Chrome()

        # 初始化Web关键字对象
        self.keywords = WebKeywords(self.driver)
        return self.keywords
