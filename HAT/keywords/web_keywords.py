import sys

from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as ec

from HAT.core.global_context import GlobalContext


class WebKeywords:
    def __init__(self, driver):
        self.driver = driver

    def wait(self, **kwargs):
        # return WebDriverWait(self.driver, timeout=10)
        timeout = kwargs.get("timeout", 10)
        return WebDriverWait(self.driver, timeout)

    def wait_for_all_elements_visibility(self, locator):
        try:
            elements = self.wait().until(
                ec.visibility_of_all_elements_located(locator)
            )
            return elements
        except Exception as e:
            print(e)

    def wait_for_element_clickable(self, locator):
        try:
            element = self.wait().until(
                ec.element_to_be_clickable(locator)
            )
            return element
        except Exception as e:
            print(e)

    def maximize_window(self):
        self.driver.maximize_window()

    def open_url(self, **kwargs):
        self.driver.get(kwargs["request_url"])
        self.maximize_window()

    def find_element_visibility(self, **kwargs):
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

    def find_element_clickable(self, **kwargs):
        locating_method = kwargs["locating_method"]
        if isinstance(locating_method, str):
            from selenium.webdriver.common.by import By
            locating_method = getattr(By, locating_method.split(".")[-1])
        locator = (locating_method, kwargs["expression"])
        return self.wait_for_element_clickable(locator)

    def click_element(self, **kwargs):
        self.find_element_clickable(**kwargs).click()

    def input_text(self, **kwargs):
        self.find_element_visibility(**kwargs).send_keys(kwargs["text"])

    def get_screenshot(self, **kwargs):
        pass

    def quit(self):
        self.driver.quit()

    def ex_invoke(self, **kwargs):
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
            request_method = class_(self.driver).__getattribute__(method)
            request_method(**kwargs["step_value"])
