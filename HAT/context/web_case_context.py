"""
Web测试用例上下文模块

该模块提供了Web测试用例的上下文管理功能，
包括WebDriver会话管理和Web关键字初始化。
"""
import atexit
from typing import Optional

from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver import DesiredCapabilities
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.chrome.service import Service as Chrome_Service
from selenium.webdriver.firefox.options import Options as FirefoxOptions, Options
from selenium.webdriver.firefox.service import Service as Firefox_Service
from selenium.webdriver.ie.options import Options as IeOptions
from selenium.webdriver.ie.service import Service as Ie_Service
from selenium.webdriver.chrome.options import Options

from HAT.core.global_context import GlobalContext
from HAT.keywords.api_keywords import ApiKeywords
from HAT.keywords.web_keywords import WebKeywords

# 全局WebDriver对象，用于会话复用
_global_driver_object = None


def cleanup_shared_driver():
    global _global_driver_object
    if _global_driver_object is not None:
        try:
            # 方法1：温和关闭
            try:
                _global_driver_object.quit()
            except:
                try:
                    # 方法2： close
                    _global_driver_object.close()
                except:
                    # 方法3：关闭进程
                    import os
                    import signal
                    if hasattr(_global_driver_object, 'service') and _global_driver_object.service.process:
                        try:
                            os.kill(_global_driver_object.service.process.pid, signal.SIGTERM)
                        except:
                            pass
        except Exception as e:
            print(e)
        finally:
            _global_driver_object = None


atexit.register(cleanup_shared_driver)


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
        self.driver: Optional[WebDriver] = None

    def init_driver(self):
        driver_class = {
            "remote": {"driver": webdriver.Remote},  # 支持远程连接
            "chrome": {"driver": webdriver.Chrome,  # 浏览器
                       "service": Chrome_Service,  # 浏览器驱动
                       "options": ChromeOptions,  # 浏览器配置 窗口 模式
                       "capabilities": DesiredCapabilities.CHROME},  # 浏览器能力 版本 操作系统
            "firefox": {"driver": webdriver.Firefox,
                        "service": Firefox_Service,
                        "options": FirefoxOptions,
                        "capabilities": DesiredCapabilities.FIREFOX},
            "ie": {"driver": webdriver.Ie,
                   "service": Ie_Service,
                   "options": IeOptions,
                   "capabilities": DesiredCapabilities.INTERNETEXPLORER},
        }

        _browser_config = GlobalContext().get_context("_browser_config")
        grid_url = _browser_config.get("grid_url", None)
        options = _browser_config.get("options", None)
        capability = _browser_config.get("capability", None)

        browser_name = capability.get("browser_name", "chrome")
        capabilities = driver_class[browser_name.lower()]["capabilities"].copy()

        service = None
        driver_path = _browser_config.get("driver_path", None)
        if driver_path is not None:
            service = driver_class[browser_name.lower()]["service"](driver_path)

            for key in capability.keys():
                capabilities.update({key: capability[key]})

            browser_options = Options()
            if options is not None and len(options) > 0:
                browser_options = driver_class[browser_name.lower()]["options"]()
                args = options.get("args", [])
                for arg in args:
                    browser_options.add_argument(arg)

            if grid_url is not None and len(grid_url) != 0:
                driver = webdriver.Remote(
                    command_executor=_browser_config["grid_url"],
                    options=browser_options
                )
            else:
                driver = driver_class[browser_name.lower()]["driver"](
                    service=service,
                    options=browser_options
                )
            return driver

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
        if driver_reuse is not None and driver_reuse == True:
            global _global_driver_object
            # 如果全局WebDriver对象不存在，则创建新的WebDriver
            if _global_driver_object is None:
                _global_driver_object = self.init_driver()
            self.driver = _global_driver_object
        else:
            # 创建新的独立WebDriver对象
            self.driver = self.init_driver()

        # 初始化Web关键字对象
        self.keywords = WebKeywords(self.driver)
        return self.keywords

    def release_driver(self):
        """
        释放WebDriver对象

        根据全局上下文中的WebDriver复用配置决定是否释放WebDriver对象。
        如果启用了会话复用且全局WebDriver对象存在，则释放WebDriver对象。

        Example:
            >>> context = WebCaseContext()
            >>> context.release_driver()
        """
        try:
            # 从全局上下文中获取WebDriver复用配置
            driver_reuse = GlobalContext().get_context("driver_reuse")

            # 根据配置决定是否释放WebDriver
            if (driver_reuse is None or driver_reuse == False) and self.driver is not None:
                self.driver.quit()
        except Exception as e:
            print(e)
