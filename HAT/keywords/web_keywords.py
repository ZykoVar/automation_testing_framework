# -*- coding: utf-8 -*-
"""
Web自动化测试关键字模块（Playwright 实现）

提供Web自动化测试所需的各种关键字方法，包括页面导航、元素交互、
数据提取、断言验证、数据库查询和 AI 视觉断言等。

定位表达式支持两种写法（都经 _resolve 统一解析）：

  1. 方言字符串（推荐，与 Playwright 语义定位对齐）：
       CSS 默认      ".cls" / "#id" / "input[name='x']"
       placeholder   "placeholder=手机号码"
       role+name     "role=button[name='登录']"
       role+exact    "role=button[name='登录',exact]"
       text          "text=评论" / "text=评论,exact"
       testid        "testid=xxx"
       xpath         "xpath=//input[@type='email']"
       tag 语法糖    "tag=button.submit"

  2. 旧版字典（向后兼容 Selenium 时代的用例配置）：
       {"locating_method": "By.XPATH", "expression": "//input[@type='email']"}
     支持的 locating_method：By.XPATH / By.CSS_SELECTOR / By.ID /
     By.NAME / By.CLASS_NAME / By.TAG_NAME / By.LINK_TEXT

timeout 参数单位为秒（与旧版 Selenium 实现的语义保持一致），内部换算成毫秒。
"""

import base64
import re
import sys
from typing import Any, Dict, Callable, Optional

import allure
import pymysql
from loguru import logger
from playwright.sync_api import Locator, Page
from pymysql import cursors

from HAT.ai.ai_assert import judge_by_local_rules, parse_verdict
from HAT.ai.ai_debug_helper import call_llm, has_api_key, render_assert_prompt
from HAT.core.global_context import GlobalContext

# 旧版 Selenium 定位方式 → 方言字符串前缀 的映射
_LEGACY_BY_MAP = {
    "XPATH": "xpath={expr}",
    "CSS_SELECTOR": "css={expr}",
    "ID": "css=#{expr}",
    "NAME": "css=[name='{expr}']",
    "CLASS_NAME": "css=.{expr}",
    "TAG_NAME": "css={expr}",
    "LINK_TEXT": "text={expr}",
}


class WebKeywords:
    """
    Web自动化关键字类

    提供Web自动化测试所需的各种关键字方法，包括页面导航、元素定位和交互等。

    Attributes:
        page: Playwright Page 对象
    """

    def __init__(self, page: Page) -> None:
        """
        初始化Web关键字对象

        Args:
            page: Playwright Page 实例
        """
        self.page = page

    # ==================== 定位解析 ====================

    def _resolve(self, selector: str) -> Locator:
        """
        把方言字符串解析成 Playwright Locator

        Args:
            selector: 方言定位字符串

        Returns:
            Locator: Playwright 定位器
        """
        s = str(selector).strip()
        if s.startswith("placeholder="):
            return self.page.get_by_placeholder(s[len("placeholder="):])
        if s.startswith("text="):
            body = s[len("text="):]
            if body.endswith(",exact"):
                return self.page.get_by_text(body[:-len(",exact")], exact=True)
            return self.page.get_by_text(body)
        if s.startswith("testid="):
            return self.page.get_by_test_id(s[len("testid="):])
        if s.startswith("tag="):
            return self.page.locator(s[len("tag="):])
        if s.startswith("role="):
            body = s[len("role="):]
            m = re.match(r"^([\w-]+)\[(.+)\]$", body)
            if m:
                role_name = m.group(1)
                kv_match = re.match(
                    r"^(\w+(?:-\w+)?)\s*=\s*['\"]?([^'\"]+)['\"]?\s*(?:,(exact))?\s*$",
                    m.group(2),
                )
                if kv_match and kv_match.group(1) == "name":
                    return self.page.get_by_role(
                        role_name,
                        name=kv_match.group(2),
                        exact=kv_match.group(3) == "exact",
                    )
                return self.page.get_by_role(role_name)
            return self.page.get_by_role(body)
        return self.page.locator(s)

    def _get_selector(self, **kwargs: Any) -> str:
        """
        从全局上下文 _all_web_elements 中取出定位表达式

        元素配置支持方言字符串或旧版字典两种写法。

        Args:
            **kwargs: element_position（页面分组键）、element（元素键）

        Returns:
            str: 方言定位字符串
        """
        all_web_elements = GlobalContext().get_context("_all_web_elements")
        if not isinstance(all_web_elements, dict):
            raise TypeError(
                f"_all_web_elements should be a dict, but got {type(all_web_elements)}"
            )

        position_key = kwargs["element_position"]
        position = all_web_elements.get(position_key)
        if position is None:
            raise KeyError(f"Element position '{position_key}' not found in _all_web_elements")

        element_key = kwargs["element"]
        element = position.get(element_key)
        if element is None:
            raise KeyError(f"Element '{element_key}' not found in position '{position_key}'")

        # 新格式：直接是方言字符串
        if isinstance(element, str):
            return element

        # 旧格式：{"locating_method": "By.XPATH", "expression": "..."}
        if isinstance(element, dict):
            method = str(element.get("locating_method", "By.CSS_SELECTOR"))
            by_name = method.split(".")[-1].upper()
            template = _LEGACY_BY_MAP.get(by_name)
            if template is None:
                raise ValueError(f"不支持的 locating_method: {method}")
            return template.format(expr=element.get("expression", ""))

        raise TypeError(f"元素配置应为字符串或字典，实际为 {type(element)}")

    def _find(self, **kwargs: Any) -> Locator:
        """按 element_position + element 定位元素。"""
        return self._resolve(self._get_selector(**kwargs))

    @staticmethod
    def _timeout_ms(kwargs: Dict[str, Any], default_seconds: float = 10) -> float:
        """把秒为单位的 timeout 参数换算成 Playwright 需要的毫秒。"""
        return float(kwargs.get("timeout", default_seconds)) * 1000

    # ==================== 页面导航 ====================

    @allure.step("open_url")
    def open_url(self, **kwargs: Any) -> None:
        """
        打开指定URL

        Args:
            **kwargs: request_url（要打开的URL地址）
        """
        self.page.goto(kwargs["request_url"], wait_until="load")
        self.show_log("open_url", kwargs["request_url"])
        self.get_screenshot()

    @allure.step("go_back")
    def go_back(self, **kwargs: Any) -> None:
        """浏览器后退。"""
        self.page.go_back()
        self.show_log("go_back")

    @allure.step("refresh_page")
    def refresh_page(self, **kwargs: Any) -> None:
        """刷新当前页面。"""
        self.page.reload()
        self.show_log("refresh_page")

    # ==================== 元素交互 ====================

    @allure.step("click_element")
    def click_element(self, **kwargs: Any) -> None:
        """
        点击元素（Playwright 自动等待元素可见可点）

        Args:
            **kwargs: element_position、element、timeout（秒，默认10）
        """
        self._find(**kwargs).click(timeout=self._timeout_ms(kwargs))
        self.show_log("click_element")
        self.get_screenshot()

    @allure.step("input_text")
    def input_text(self, **kwargs: Any) -> None:
        """
        在元素中输入文本（fill 语义，先清空再输入）

        Args:
            **kwargs: element_position、element、text、timeout（秒，默认10）
        """
        self._find(**kwargs).fill(str(kwargs["text"]), timeout=self._timeout_ms(kwargs))
        self.show_log("input_text", kwargs["text"])
        self.get_screenshot()

    @allure.step("hover_element")
    def hover_element(self, **kwargs: Any) -> None:
        """悬停在元素上（触发下拉菜单等悬浮交互）。"""
        self._find(**kwargs).hover(timeout=self._timeout_ms(kwargs))
        self.show_log("hover_element")
        self.get_screenshot()

    @allure.step("select_option")
    def select_option(self, **kwargs: Any) -> None:
        """
        下拉框选择

        Args:
            **kwargs: element_position、element、value（选项的 value 或可见文本）
        """
        self._find(**kwargs).select_option(kwargs["value"], timeout=self._timeout_ms(kwargs))
        self.show_log("select_option", kwargs["value"])

    @allure.step("execute_js")
    def execute_js(self, **kwargs: Any) -> None:
        """
        执行 JavaScript，返回值可存入上下文变量

        Args:
            **kwargs: script（JS 表达式）、variable_name（可选，存结果的变量名）
        """
        result = self.page.evaluate(kwargs["script"])
        if kwargs.get("variable_name"):
            GlobalContext().set_context(kwargs["variable_name"], result)
        self.show_log("execute_js", result)

    @allure.step("wait_for_text")
    def wait_for_text(self, **kwargs: Any) -> None:
        """
        等待页面出现指定文本（常用于等待异步加载完成）

        Args:
            **kwargs: text、timeout（秒，默认10）
        """
        self.page.get_by_text(str(kwargs["text"])).first.wait_for(
            state="visible", timeout=self._timeout_ms(kwargs)
        )
        self.show_log("wait_for_text", kwargs["text"])

    # ==================== 数据提取 ====================

    @allure.step("get_element_data")
    def get_element_data(self, **kwargs: Any) -> None:
        """
        获取元素文本并写入全局上下文

        Args:
            **kwargs: element_position、element、variable_name、timeout（秒，默认10）
        """
        element = self._find(**kwargs).first
        element.wait_for(state="visible", timeout=self._timeout_ms(kwargs))
        result = element.inner_text()
        if not result:
            raise Exception(
                f"No data found in element position: "
                f"{kwargs.get('element_position')} {kwargs.get('element')}"
            )
        self.show_log("get_element_data", result)
        GlobalContext().set_context(kwargs["variable_name"], result)

    @allure.step("get_screenshot")
    def get_screenshot(self) -> None:
        """截取当前页面并附加到 Allure 报告。"""
        allure.attach(
            self.page.screenshot(full_page=True),
            "screenshot",
            allure.attachment_type.PNG,
        )
        self.show_log("get_screenshot")

    @allure.step("quit")
    def quit(self):
        """
        关闭当前用例的浏览器上下文。

        正常情况下 WebCaseContext.release_driver 会统一释放，
        该关键字用于用例中途主动结束浏览器会话的场景。
        """
        self.page.context.close()
        self.show_log("quit")

    # ==================== AI 视觉断言 ====================

    def _collect_page_text(self) -> str:
        """收集页面的 URL + title + body 可见文本，作为文本模式的判断依据。"""
        try:
            body = self.page.evaluate("document.body ? document.body.innerText : ''")
        except Exception as e:
            logger.warning(f"收集页面文本失败: {e}")
            body = ""
        return f"[URL] {self.page.url}\n[TITLE] {self.page.title()}\n[BODY]\n{body}"

    @allure.step("ai_assert_screenshot")
    def ai_assert_screenshot(self, **kwargs: Any) -> None:
        """
        AI 视觉断言：截取当前页面，让大模型判断是否满足中文规则

        判断链路：
            有 Key：截图 → 视觉模型判断
                    → 视觉调用失败时降级为「页面文本 → 文本模型」
            无 Key：降级为「页面文本 → 本地正则规则」（与接口侧 ai_assert 同源）

        Args:
            **kwargs:
                rule: 中文断言规则，必填，如 "页面右上角显示用户名 admin"
                strict: "true"(默认) 不满足则让用例失败；"false" 只记录结论
                context: 可选，补充上下文说明
        """
        rule = kwargs.get("rule", "")
        if not rule:
            raise ValueError("ai_assert_screenshot 关键字缺少必填参数 rule")
        strict = str(kwargs.get("strict", "true")).strip().lower() not in ("false", "0", "no")
        context = kwargs.get("context", "")

        # 截图留证（无论走哪条判断链路，报告里都能看到当时页面长什么样）
        screenshot_bytes = self.page.screenshot(full_page=True)
        allure.attach(screenshot_bytes, "AI 断言截图", allure.attachment_type.PNG)

        satisfied: Optional[bool] = None
        reason = ""

        if has_api_key():
            # 视觉模式
            image_b64 = base64.b64encode(screenshot_bytes).decode()
            raw = call_llm(
                render_assert_prompt(rule, "（页面内容见所附截图，请基于截图判断）", context),
                image_b64=image_b64,
            )
            if raw.strip():
                satisfied = parse_verdict(raw)
                reason = raw
                if satisfied is None:
                    # 模型输出未带 VERDICT 标记，按保守原则视为不通过
                    satisfied = False
                    reason = "（模型输出缺少 VERDICT 标记，按不通过处理）\n" + raw
            if satisfied is None:
                # 视觉调用失败，降级为文本模式再试一次
                logger.warning("视觉模式调用失败，降级为页面文本模式")
                page_text = self._collect_page_text()
                raw = call_llm(render_assert_prompt(rule, page_text[:2000], context))
                if raw.strip():
                    satisfied = parse_verdict(raw)
                    reason = "（视觉模式不可用，已降级为页面文本判断）\n" + raw
                    if satisfied is None:
                        satisfied = False
                        reason = "（模型输出缺少 VERDICT 标记，按不通过处理）\n" + reason
            if satisfied is None:
                satisfied = False
                reason = "（大模型调用失败，按不通过处理）"
        else:
            # 无 Key：本地正则规则对页面文本做判断
            satisfied, reason = judge_by_local_rules(rule, {"text": self._collect_page_text()})
            reason = "（未配置 LLM_API_KEY，本地规则基于页面文本判断）" + reason

        allure.attach(
            f"RULE:\n{rule}\n\nRESULT: {satisfied}\n\nDETAIL:\n{reason}",
            name="AI 视觉断言详情",
            attachment_type=allure.attachment_type.TEXT,
        )
        print(f"[AI断言] {'通过' if satisfied else '不通过'} | 规则: {rule}")
        self.show_log("ai_assert_screenshot", {"rule": rule, "satisfied": satisfied})

        if not satisfied and strict:
            raise AssertionError(f"自然语言断言不满足\n规则: {rule}\n依据: {reason}")

    # ==================== 断言（与 API 侧保持一致） ====================

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
        """文本相等断言"""
        kwargs.update({"comparison_operator": "=="})
        self.assert_data(**kwargs)
        self.show_log("assert_text_equal", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_text_contain")
    def assert_text_contain(self, **kwargs: Any) -> None:
        """文本包含断言"""
        kwargs.update({"comparison_operator": "in"})
        self.assert_data(**kwargs)
        self.show_log("assert_text_contain", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_text_not_contain")
    def assert_text_not_contain(self, **kwargs: Any) -> None:
        """文本不包含断言"""
        kwargs.update({"comparison_operator": "not in"})
        self.assert_data(**kwargs)
        self.show_log("assert_text_not_contain", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_ge")
    def assert_number_ge(self, **kwargs: Any) -> None:
        """数字大于等于断言"""
        kwargs.update({"comparison_operator": ">=", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_ge", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_le")
    def assert_number_le(self, **kwargs: Any) -> None:
        """数字小于等于断言"""
        kwargs.update({"comparison_operator": "<=", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_le", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_equal")
    def assert_number_equal(self, **kwargs: Any) -> None:
        """数字相等断言"""
        kwargs.update({"comparison_operator": "==", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_equal", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_not_equal")
    def assert_number_not_equal(self, **kwargs: Any) -> None:
        """数字不相等断言"""
        kwargs.update({"comparison_operator": "!=", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_not_equal", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_gt")
    def assert_number_gt(self, **kwargs: Any) -> None:
        """数字大于断言"""
        kwargs.update({"comparison_operator": ">", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_gt", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    @allure.step("assert_number_lt")
    def assert_number_lt(self, **kwargs: Any) -> None:
        """数字小于断言"""
        kwargs.update({"comparison_operator": "<", "compare_type": "number"})
        self.assert_data(**kwargs)
        self.show_log("assert_number_lt", f"{kwargs['actual_value']} - {kwargs['expected_value']}")

    # ==================== 数据库与日志 ====================

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
            # 获取并执行方法。扩展类拿到的是 Playwright Page 对象
            request_method = class_(self.page).__getattribute__(method)
            request_method(**kwargs["step_value"])
