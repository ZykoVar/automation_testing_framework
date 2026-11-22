# -*- coding: utf-8 -*-
"""
Web测试用例上下文模块（Playwright 实现）

该模块提供了Web测试用例的上下文管理功能，
包括浏览器生命周期管理和Web关键字初始化。

与 Selenium 时代的差异：
    - 浏览器引擎换成 Playwright，自动等待替代手写 WebDriverWait；
    - 隔离单位从「整个浏览器」改为「browser context」：
      浏览器进程可按 driver_reuse 复用，每个用例拿独立的 context + page，
      cookie / 登录态互不影响；
    - 配置项见用例目录 context.yaml 的 _browser_config：
          browser_name: chromium / firefox / webkit（默认 chromium）
          headless:     true / false（默认 true）
          viewport:     {width: 1920, height: 1080}
          args:         额外的浏览器启动参数列表
    - 当前 page 记录在模块级变量中（通过 get_current_page() 取用），
      供失败诊断钩子（ai_debug_plugin）在失败时截图留证。
      注意：不能放进 GlobalContext —— test_runner 会对全局上下文做
      deepcopy，而 Playwright 的 Page 对象不可序列化，会直接导致用例崩溃。
"""

import atexit
from typing import Optional

from playwright.sync_api import Browser, BrowserContext, Page, sync_playwright

from HAT.core.global_context import GlobalContext
from HAT.keywords.web_keywords import WebKeywords

# 全局 Playwright 实例与浏览器进程，用于跨用例复用
_global_playwright = None
_global_browser: Optional[Browser] = None

# 当前用例的 page（模块级登记，不入 GlobalContext，原因见模块 docstring）
_current_page: Optional[Page] = None

# 最近一次失败截图的路径，由 capture_failure_screenshot 写入、
# ai_debug_plugin 读取后清空
_failure_screenshot: Optional[str] = None


def get_current_page() -> Optional[Page]:
    """取当前用例的 Page 对象，供失败诊断钩子等旁路能力使用。"""
    return _current_page


def get_failure_screenshot() -> Optional[str]:
    """取最近一次失败截图的路径（不消费，由读取方自行决定是否清空）。"""
    return _failure_screenshot


def _ensure_playwright():
    """确保全局 Playwright 实例已启动（只启动一次）。"""
    global _global_playwright
    if _global_playwright is None:
        _global_playwright = sync_playwright().start()
    return _global_playwright


def _launch_browser() -> Browser:
    """按 _browser_config 启动一个浏览器进程（不记录到全局变量）。"""
    browser_config = GlobalContext().get_context("_browser_config") or {}
    browser_name = str(browser_config.get("browser_name", "chromium")).lower()
    headless = bool(browser_config.get("headless", True))
    args = list(browser_config.get("args") or [])

    launcher = getattr(_ensure_playwright(), browser_name, None)
    if launcher is None:
        raise ValueError(
            f"不支持的浏览器类型: {browser_name}，可选 chromium / firefox / webkit"
        )
    return launcher.launch(headless=headless, args=args)


def _start_browser() -> Browser:
    """启动（或复用）全局共享的浏览器进程。"""
    global _global_browser
    if _global_browser is None:
        _global_browser = _launch_browser()
    return _global_browser


def cleanup_shared_browser():
    """进程退出前关闭复用的浏览器与 Playwright。"""
    global _global_playwright, _global_browser
    try:
        if _global_browser is not None:
            _global_browser.close()
    except Exception as e:
        print(e)
    try:
        if _global_playwright is not None:
            _global_playwright.stop()
    except Exception as e:
        print(e)
    _global_browser = None
    _global_playwright = None


atexit.register(cleanup_shared_browser)


class WebCaseContext:
    """
    Web测试用例上下文类

    该类负责管理Web测试用例的上下文信息，
    包括浏览器、浏览器上下文（browser context）和Web关键字对象的初始化。

    Attributes:
        keywords: Web关键字对象
        context: 当前用例的 BrowserContext
        page: 当前用例的 Page
    """

    def __init__(self) -> None:
        """
        初始化Web测试用例上下文
        """
        self.keywords: Optional[WebKeywords] = None
        self.browser: Optional[Browser] = None
        self.context: Optional[BrowserContext] = None
        self.page: Optional[Page] = None
        # 记录浏览器是否为本用例独占（不复用时每个用例独立启动）
        self._browser_owned: bool = False

    def init_keywords(self) -> WebKeywords:
        """
        初始化Web关键字对象

        根据全局上下文中的 driver_reuse 配置决定是否复用浏览器进程；
        无论复用与否，每个用例都创建独立的 browser context 和 page，
        保证用例间 cookie、登录态互不影响。

        Returns:
            WebKeywords: 初始化后的Web关键字对象
        """
        driver_reuse = GlobalContext().get_context("driver_reuse")
        browser_config = GlobalContext().get_context("_browser_config") or {}
        viewport = browser_config.get("viewport") or {"width": 1920, "height": 1080}

        if driver_reuse:
            # 复用全局浏览器进程，未启动则启动
            self.browser = _start_browser()
            self._browser_owned = False
        else:
            # 每个用例独立浏览器进程，用例结束即关闭
            self.browser = _launch_browser()
            self._browser_owned = True

        # 每个用例独立 context，天然隔离 cookie 与登录态
        self.context = self.browser.new_context(viewport=viewport)
        self.page = self.context.new_page()
        self.page.set_default_timeout(10000)

        # 登记到模块级变量，供失败诊断钩子截图留证
        global _current_page
        _current_page = self.page

        self.keywords = WebKeywords(self.page)
        return self.keywords

    def capture_failure_screenshot(self) -> Optional[str]:
        """
        用例失败时截取当前页面现场。

        必须在浏览器上下文释放之前调用（test_runner 在抛异常的路径上、
        release_driver 之前调用本方法），否则 page 已关闭无法再截图。

        Returns:
            截图文件路径；截图失败时返回 None
        """
        global _failure_screenshot
        if self.page is None:
            return None
        try:
            import os
            import time

            report_dir = os.path.join(
                os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
                "ai_debug_reports",
            )
            os.makedirs(report_dir, exist_ok=True)
            file_path = os.path.join(report_dir, f"web_fail_{int(time.time() * 1000)}.png")
            self.page.screenshot(path=file_path, full_page=True)
            _failure_screenshot = file_path
            return file_path
        except Exception as e:
            print(f"[Web] 失败截图失败: {e}")
            return None

    def release_driver(self) -> None:
        """
        释放当前用例的资源

        复用模式：只关本用例的 context，浏览器进程留给后续用例；
        独占模式：context 和浏览器进程一起关。
        方法名保持 release_driver 不变，是为了兼容 test_runner 的既有调用。
        """
        try:
            if self.context is not None:
                self.context.close()
        except Exception as e:
            print(e)
        try:
            if self._browser_owned and self.browser is not None:
                self.browser.close()
        except Exception as e:
            print(e)
        # 清掉当前 page 的登记，避免下一个用例误用已关闭的页面
        global _current_page
        if _current_page is self.page:
            _current_page = None
