"""
Web自动化测试关键字模块

该模块提供了Web自动化测试的核心关键字实现，
包括元素定位、等待、操作等常用功能。
"""

import sys
from base64 import b64decode
from typing import Any, Optional, List, Dict, Callable

import allure
import pymysql
from loguru import logger
from pymysql import cursors
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

    def get_locator(self, **kwargs: Any) -> tuple[str, str]:
        """
        获取元素定位器

        从全局上下文中获取Web元素配置信息，并根据传入的参数构建元素定位器。

        Args:
            **kwargs: 可变关键字参数
                element_position (str): 元素位置键名，用于在全局上下文中查找元素位置配置
                element (str): 元素键名，用于在元素位置配置中查找具体元素信息

        Returns:
            tuple: Selenium定位器元组 (定位方式, 定位表达式)

        Raises:
            TypeError: 当_global_web_elements不是字典类型或element_position/
                      element_position_key不是字符串类型时
            KeyError: 当在全局上下文中找不到指定的元素位置或元素时

        Example:
            >>> element_locator = self.get_locator(
            ...     element_position="login_page",
            ...     element="username_input"
            ... )
            >>> print(element_locator)
            (By.ID, "username")
        """
        all_web_elements = GlobalContext().get_context("_all_web_elements")
        if not isinstance(all_web_elements, dict):
            raise TypeError(f"_all_web_elements should be a dict, but got {type(all_web_elements)}")

        element_position_key = kwargs["element_position"]
        if not isinstance(element_position_key, str):
            raise TypeError(f"element_position should be a string, but got {type(element_position_key)}")

        element_position = all_web_elements.get(element_position_key)
        if element_position is None:
            raise KeyError(f"Element position '{element_position_key}' not found in _all_web_elements")

        if not isinstance(element_position, dict):
            raise TypeError(f"Element position should be a dict, but got {type(element_position)}")

        element_key = kwargs["element"]
        if not isinstance(element_key, str):
            raise TypeError(f"element should be a string, but got {type(element_key)}")

        element = element_position.get(element_key)
        if element is None:
            raise KeyError(f"Element '{element_key}' not found in element position '{element_position_key}'")

        locating_method = element["locating_method"]
        if isinstance(locating_method, str):
            from selenium.webdriver.common.by import By
            locating_method = getattr(By, locating_method.split(".")[-1])
        locator = (locating_method, element["expression"])
        self.show_log("get_locator", locator)
        return locator

    @allure.step("maximize_window")
    def maximize_window(self) -> None:
        """
        最大化浏览器窗口
        """
        self.driver.maximize_window()
        self.show_log("maximize_window")

    @allure.step("open_url")
    def open_url(self, **kwargs: Any) -> None:
        """
        打开指定URL
        
        Args:
            **kwargs: 可变关键字参数
                request_url (str): 要打开的URL地址
        """
        self.driver.get(kwargs["request_url"])
        self.show_log("open_url", kwargs["request_url"])
        self.maximize_window()
        self.get_screenshot()

    def find_element_visibility(self, **kwargs: Any) -> WebElement:
        """
        查找可见元素
        
        Args:
            **kwargs: 可变关键字参数
                element_position (str): 元素位置键名
                element (str): 元素键名
                index (int): 元素索引，默认为0
                
        Returns:
            WebElement: 找到的元素对象
        """
        locator = self.get_locator(**kwargs)

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
                element_position (str): 元素位置键名
                element (str): 元素键名
                
        Returns:
            WebElement: 可点击的元素对象
        """
        locator = self.get_locator(**kwargs)
        return self.wait_for_element_clickable(locator)

    @allure.step("click_element")
    def click_element(self, **kwargs: Any) -> None:
        """
        点击元素
        
        Args:
            **kwargs: 可变关键字参数
                locating_method (str): 定位方式，如 "By.XPATH"
                expression (str): 定位表达式
        """
        self.find_element_clickable(**kwargs).click()
        self.show_log("click_element")
        self.get_screenshot()

    @allure.step("input_text")
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
        self.show_log("input_text", kwargs["text"])
        self.get_screenshot()

    @allure.step("get_screenshot")
    def get_screenshot(self) -> None:
        """
        获取屏幕截图
        """
        img_base64 = self.driver.get_screenshot_as_base64()
        allure.attach(b64decode(img_base64.encode("ascii")), "screenshot", allure.attachment_type.PNG)
        self.show_log("get_screenshot")

    @allure.step("quit")
    def quit(self):
        """
        关闭WebDriver会话
        """
        self.driver.quit()
        self.show_log("quit")

    @allure.step("get_element_data")
    def get_element_data(self, **kwargs: Any) -> None:
        """
        获取数据

        Args:
            **kwargs: 获取数据相关参数
        """
        try:
            result = self.find_element_visibility(**kwargs).text
            if not result:
                raise Exception(
                    f"No data found in element position: "
                    f"{kwargs.get('element_position')} {kwargs.get('element')}"
                )
            self.show_log("get_element_data", result)
            GlobalContext().set_context(kwargs["variable_name"], result)
        except Exception as e:
            raise Exception(f"Failed to extract JSON data: {str(e)}")

    @allure.step("assert_data")
    def assert_data(self, **kwargs: Any) -> None:
        """
        数据断言

        支持多种比较操作符的数据断言方法

        Args:
            **kwargs: 包含actual_value(实际值)、expected_value(期望值)、
                     comparison_operator(比较操作符)等参数
        """
        # 定义比较操作符字典
        comparators: Dict[str, Callable[[Any, Any], bool]] = {
            ">": lambda x, y: x > y,
            "<": lambda x, y: x < y,
            "==": lambda x, y: x == y,
            ">=": lambda x, y: x >= y,
            "<=": lambda x, y: x <= y,
            "!=": lambda x, y: x != y,
            "in": lambda x, y: y in x,
            "not in": lambda x, y: y not in x,
        }
        error_msg = kwargs.get("error_message", None)
        compare_type = kwargs.get("compare_type", "text")
        comparison_operator = kwargs.get("comparison_operator", "==")

        # 检查比较操作符是否有效
        if comparison_operator not in comparators:
            raise ValueError(f"Invalid comparison operator: {comparison_operator}")

        # 根据比较类型转换期望值
        expected_value = kwargs.get("expected_value")
        if compare_type == "number":
            try:
                expected_value = float(expected_value)
            except (ValueError, TypeError):
                raise ValueError(f"Cannot convert '{expected_value}' to number for comparison")
        else:
            expected_value = str(expected_value) if expected_value is not None else ""

        actual_value = kwargs.get("actual_value", "")

        # 执行断言
        if not comparators[comparison_operator](actual_value, expected_value):
            if error_msg:
                raise AssertionError(error_msg)
            else:
                raise AssertionError(
                    f"Assertion failed: {actual_value} {comparison_operator} {expected_value} is False")

    @allure.step("assert_text_equal")
    def assert_text_equal(self, **kwargs: Any) -> None:
        """
        文本相等断言

        Args:
            **kwargs: 断言参数
        """
        # 设置比较操作符为相等
        kwargs.update({"comparison_operator": "=="})
        self.assert_data(**kwargs)
        self.show_log("assert_text_equal", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_text_contain")
    def assert_text_contain(self, **kwargs: Any) -> None:
        """
        文本包含断言

        Args:
            **kwargs: 断言参数
        """
        # 设置比较操作符为包含
        kwargs.update({"comparison_operator": "in"})
        self.assert_data(**kwargs)
        self.show_log("assert_text_contain", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_text_not_contain")
    def assert_text_not_contain(self, **kwargs: Any) -> None:
        """
        文本不包含断言

        Args:
            **kwargs: 断言参数
        """
        # 设置比较操作符为不包含
        kwargs.update({"comparison_operator": "not in"})
        self.assert_data(**kwargs)
        self.show_log("assert_text_not_contain", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_ge")
    def assert_number_ge(self, **kwargs: Any) -> None:
        """
        数字大于等于断言

        Args:
            **kwargs: 断言参数
        """
        # 设置比较操作符为大于等于，并指定比较类型为数字
        kwargs.update({"comparison_operator": ">=", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_ge", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_le")
    def assert_number_le(self, **kwargs: Any) -> None:
        """
        数字小于等于断言

        Args:
            **kwargs: 断言参数
        """
        # 设置比较操作符为小于等于，并指定比较类型为数字
        kwargs.update({"comparison_operator": "<=", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_le", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_equal")
    def assert_number_equal(self, **kwargs: Any) -> None:
        """
        数字相等断言

        Args:
            **kwargs: 断言参数
        """
        # 设置比较操作符为相等，并指定比较类型为数字
        kwargs.update({"comparison_operator": "==", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_equal", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_not_equal")
    def assert_number_not_equal(self, **kwargs: Any) -> None:
        """
        数字不相等断言

        Args:
            **kwargs: 断言参数
        """
        # 设置比较操作符为不相等，并指定比较类型为数字
        kwargs.update({"comparison_operator": "!=", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_not_equal", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_gt")
    def assert_number_gt(self, **kwargs: Any) -> None:
        """
        数字大于断言

        Args:
            **kwargs: 断言参数
        """
        # 设置比较操作符为大于，并指定比较类型为数字
        kwargs.update({"comparison_operator": ">", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_gt", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_lt")
    def assert_number_lt(self, **kwargs: Any) -> None:
        """
        数字小于断言

        Args:
            **kwargs: 断言参数
        """
        # 设置比较操作符为小于，并指定比较类型为数字
        kwargs.update({"comparison_operator": "<", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_lt", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("fetch_database_data")
    def fetch_database_data(self, **kwargs: Any) -> None:
        """
        从数据库获取数据

        Args:
            **kwargs: 包含database(数据库配置名)、sql(SQL语句)、variable_name(变量名列表)等参数
        """
        # 获取数据库配置并建立连接
        db_config = GlobalContext().get_context("_database")[kwargs["database"]]
        config = {"cursorclass": cursors.DictCursor}
        config.update(db_config)
        database_connection = pymysql.connect(**config)
        cursor = database_connection.cursor()
        # 执行SQL查询
        cursor.execute(kwargs["sql"])
        query_result = cursor.fetchall()
        cursor.close()
        database_connection.close()

        # 处理查询结果
        result_dict = {}
        var_names = kwargs.get("variable_name", [])
        if not var_names:
            # 如果没有指定变量名，则使用默认命名方式
            for index, item in enumerate(query_result, start=1):
                if isinstance(item, dict):
                    for key, value in item.items():
                        result_dict[f"{key}_{index}"] = value
                else:
                    result_dict[f"{index}"] = item
        else:
            # 如果指定了变量名，则使用指定的命名方式
            field_length = len(query_result[0]) if query_result else 0
            if len(var_names) != field_length:
                raise Exception(
                    f"The number of variable names [{var_names}] does not match the number of fields [{field_length}]")
            for index, item in enumerate(query_result, start=1):
                for col_index, key in enumerate(item):
                    result_dict[f"{var_names[col_index]}_{index}"] = item[key]
        GlobalContext().set_by_dict(result_dict)
        self.show_log("fetch_database_data", result_dict)

    @allure.step("show_log")
    def show_log(self, data_name: str, data: Any = None) -> None:
        """
        记录日志信息

        Args:
            data_name: 数据名称
            data: 要记录的数据
        """
        logger.debug(f"----------Log:{data_name}----------")
        logger.debug(f"{data_name}:{data}")
        logger.debug(f"----------End log:{data_name}------")

    @allure.step("ex_invoke")
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
