"""
Web自动化测试关键字模块

该模块提供了Web自动化测试的核心关键字实现，
包括元素定位、等待、操作等常用功能。
"""

import sys
from typing import Any, Optional, List

from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.remote.webelement import WebElement

from HAT.core.global_context import GlobalContext


class WebKeywords:
    """
    Web自动化测试关键字类
    
    提供Web自动化测试所需的各种关键字方法，包括浏览器操作、元素定位和交互等。
    """

    def __init__(self, driver: WebDriver) -> None:
        """
        初始化Web关键字对象
        
        Args:
            driver: WebDriver实例
        """
        self.driver = driver

    def wait(self, **kwargs: Any) -> WebDriverWait:
        """
        创建WebDriverWait对象
        
        Args:
            **kwargs: 可变关键字参数
                timeout (int): 等待超时时间，默认为10秒
                
        Returns:
            WebDriverWait: WebDriverWait实例
        """
        timeout = kwargs.get("timeout", 10)
        return WebDriverWait(self.driver, timeout)

    def wait_for_all_elements_visibility(self, locator: tuple[str, str]) -> Optional[List[WebElement]]:
        """
        等待所有指定元素可见
        
        Args:
            locator: 元素定位器 (By, value) 元组
            
        Returns:
            list: 可见的元素列表，如果超时未找到则返回None
        """
        try:
            elements = self.wait().until(
                ec.visibility_of_all_elements_located(locator)
            )
            return elements
        except Exception as e:
            print(e)

    def wait_for_element_clickable(self, locator: tuple[str, str]) -> Optional[WebElement]:
        """
        等待元素可点击
        
        Args:
            locator: 元素定位器 (By, value) 元组
            
        Returns:
            WebElement: 可点击的元素对象，如果超时未找到则返回None
        """
        try:
            element = self.wait().until(
                ec.element_to_be_clickable(locator)
            )
            return element
        except Exception as e:
            print(e)

    def maximize_window(self) -> None:
        """
        最大化浏览器窗口
        """
        self.driver.maximize_window()

    def open_url(self, **kwargs: Any) -> None:
        """
        打开指定URL
        
        Args:
            **kwargs: 可变关键字参数
                request_url (str): 要打开的URL地址
        """
        self.driver.get(kwargs["request_url"])
        self.maximize_window()

    def find_element_visibility(self, **kwargs: Any) -> WebElement:
        """
        查找可见元素
        
        Args:
            **kwargs: 可变关键字参数
                locating_method (str): 定位方式，如 "By.XPATH"
                expression (str): 定位表达式
                index (int): 元素索引，默认为0
                
        Returns:
            WebElement: 找到的元素对象
        """
        locating_method = kwargs["locating_method"]
        if isinstance(locating_method, str):
            from selenium.webdriver.common.by import By
            locating_method = getattr(By, locating_method.split(".")[-1])
        locator = (locating_method, kwargs["expression"])
        element_list = self.wait_for_all_elements_visibility(locator)
        if len(element_list) == 1:
            return element_list[0]
        else:
            index = int(kwargs.get("index", 0))
            return element_list[index]

    def find_element_clickable(self, **kwargs: Any) -> WebElement:
        """
        查找可点击元素
        
        Args:
            **kwargs: 可变关键字参数
                locating_method (str): 定位方式，如 "By.XPATH"
                expression (str): 定位表达式
                
        Returns:
            WebElement: 可点击的元素对象
        """
        locating_method = kwargs["locating_method"]
        if isinstance(locating_method, str):
            from selenium.webdriver.common.by import By
            locating_method = getattr(By, locating_method.split(".")[-1])
        locator = (locating_method, kwargs["expression"])
        return self.wait_for_element_clickable(locator)

    def click_element(self, **kwargs: Any) -> None :
        """
        点击元素
        
        Args:
            **kwargs: 可变关键字参数
                locating_method (str): 定位方式，如 "By.XPATH"
                expression (str): 定位表达式
        """
        self.find_element_clickable(**kwargs).click()

    def input_text(self, **kwargs: Any) -> None:
        """
        在元素中输入文本
        
        Args:
            **kwargs: 可变关键字参数
                locating_method (str): 定位方式，如 "By.XPATH"
                expression (str): 定位表达式
                text (str): 要输入的文本
        """
        self.find_element_visibility(**kwargs).send_keys(kwargs["text"])

    def get_screenshot(self, **kwargs: Any) -> None:
        """
        获取屏幕截图（待实现）
        
        Args:
            **kwargs: 截图相关参数
        """
        pass

    def quit(self):
        """
        关闭WebDriver会话
        """
        self.driver.quit()

    def ex_invoke(self, **kwargs: Any) -> None:
        """
        执行扩展方法
        
        从指定的扩展目录加载并执行自定义方法。
        
        Args:
            **kwargs: 可变关键字参数
                request_method (str): 方法名
                step_value (dict): 步骤参数字典
        """
        method = kwargs.get("request_method")
        # 检查是否配置了扩展目录
        if GlobalContext().get_context("key_dir") is not None:
            sys.path.append(GlobalContext().get_context("key_dir"))
            modul = __import__(method)
            # 根据方法名生成类名（下划线命名转为驼峰命名）
            class_name = ''.join(word.capitalize() for word in method.split('_'))
            class_ = getattr(modul, class_name)
            # 获取并执行方法
            request_method = class_(self.driver).__getattribute__(method)
            request_method(**kwargs["step_value"])
