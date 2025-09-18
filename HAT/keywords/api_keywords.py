"""
API关键字模块

该模块提供了用于API测试的关键字方法，包括HTTP请求发送、响应数据提取、
断言验证和数据库查询等功能。
"""

import json
import sys
from typing import Any, Dict, Callable

import allure
import jsonpath
import pymysql
from loguru import logger
from pymysql import cursors

from HAT.core.global_context import GlobalContext


class ApiKeywords:
    """
    API关键字类
    
    提供各种用于API测试的关键字方法，包括HTTP请求、数据提取、断言验证等。
    
    Attributes:
        request: HTTP请求会话对象
    """

    def __init__(self, request: Any) -> None:
        """
        初始化API关键字对象
        
        Args:
            request: HTTP请求会话对象
        """
        self.request = request

    @allure.step("send_request")
    def send_request(self, **kwargs: Any) -> None:
        """
        发送HTTP请求
        
        Args:
            **kwargs: 请求参数
        """
        self.show_log("send_request", kwargs)
        # 移除请求方法参数，避免传递给requests库
        kwargs.pop("request_method", None)
        response = self.request.request(**kwargs)
        GlobalContext().set_context("response", response)

        # 检查响应内容是否为空，避免JSON解析错误
        if response.text and response.text.strip():
            try:
                self.show_log("response_data", response.json())
            except json.JSONDecodeError:
                self.show_log("response_text", response.text)
        else:
            self.show_log("response_data", "Empty response body")

    @allure.step("post_request")
    def post_request(self, **kwargs: Any) -> None:
        """
        发送POST请求
        
        Args:
            **kwargs: POST请求参数，包括URL、请求头、请求体等
        """
        self.show_log("post_request", kwargs)
        # 构建请求数据
        request_data = {
            "url": kwargs.get("request_url", None),
            "params": kwargs.get("request_parameters", None),
            "files": kwargs.get("file_path", None),
            "headers": kwargs.get("request_headers", None)
        }
        # 根据内容类型设置请求体
        content_type = kwargs.get("content_type", "data").lower()
        if content_type == "json":
            request_data["json"] = kwargs.get("request_payload", None)
        elif content_type == "data":
            request_data["data"] = kwargs.get("request_payload", None)
        else:
            raise Exception("Content type error")

        response = self.request.request("post", **request_data)
        GlobalContext().set_context("response", response)

        # 检查响应内容是否为空，避免JSON解析错误
        if response.text and response.text.strip():
            try:
                self.show_log("response_data", response.json())
            except json.JSONDecodeError:
                self.show_log("response_text", response.text)
        else:
            self.show_log("response_data", "Empty response body")

    @allure.step("get_request")
    def get_request(self, **kwargs: Any) -> None:
        """
        发送GET请求
        
        Args:
            **kwargs: GET请求参数，包括URL、请求头、查询参数等
        """
        self.show_log("get_request", kwargs)
        # 构建请求数据
        request_data = {
            "url": kwargs.get("request_url", None),
            "params": kwargs.get("request_parameters", None),
            "headers": kwargs.get("request_headers", None),
            "data": kwargs.get("request_payload", None),
        }
        response = self.request.request("get", **request_data)
        GlobalContext().set_context("response", response)

        # 检查响应内容是否为空，避免JSON解析错误
        if response.text and response.text.strip():
            try:
                self.show_log("response_data", response.json())
            except json.JSONDecodeError:
                self.show_log("response_text", response.text)
        else:
            self.show_log("response_data", "Empty response body")

    @allure.step("get_json_data")
    def get_json_data(self, **kwargs: Any) -> None:
        """
        从JSON响应中提取数据
        
        使用jsonpath表达式从响应中提取数据并保存到全局上下文
        
        Args:
            **kwargs: 包含expression(表达式)、index(索引)、variable_name(变量名)等参数
        """
        expression = kwargs.get("expression", None)
        index = kwargs.get("index", 0)
        # 处理索引参数
        if index is None:
            index = 0
        if isinstance(index, str):
            index = int(index)
        response = GlobalContext().get_context("response")

        # 检查响应是否存在
        if response is None:
            raise Exception("No response found in context")

        try:
            result = jsonpath.jsonpath(response.json(), expression)
            if result is False:
                raise Exception(f"No data found for expression: {expression}")
            result = result[index]
            self.show_log("get_json_data", result)
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

    def ex_invoke(self, **kwargs: Any) -> None:
        """
        执行扩展方法
        
        Args:
            **kwargs: 包含request_method(方法名)、step_value(步骤值)等参数
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
            request_method = class_(self.request).__getattribute__(method)
            request_method(**kwargs["step_value"])
