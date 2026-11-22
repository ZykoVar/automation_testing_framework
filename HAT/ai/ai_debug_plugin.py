# -*- coding: utf-8 -*-
"""
HAT / ai / ai_debug_plugin.py

用例失败时的自动诊断 pytest 插件（移植自 day12 根 conftest 的诊断钩子）。

工作流程：
    1. pytest_runtest_makereport 在每个阶段结束时被调用；
    2. 只在 call 阶段且用例 failed 时动手，
       setup 失败是环境问题、teardown 失败是清理问题，都不生成诊断；
    3. 收集四样东西：异常信息、请求信息、响应体、用例内容；
    4. 调 ai_debug 生成 Markdown 报告写到 ai_debug_reports/。

与 day12 版本的差异（适配 HAT 的关键字驱动模型）：
    - day12 从 traceback 栈帧局部变量里找 response 对象；
      HAT 的响应由关键字统一写入 GlobalContext，直接从上下文取；
    - day12 的「源码片段」是测试函数的 Python 源码；
      HAT 的用例是 YAML 数据，这里把 case_info 原样 dump 成 YAML 作为现场。

健壮性要求（重要）：
    诊断是旁路增强，不能反过来影响测试结果。
    整个钩子体用 try/except 包住，任何异常都不向上抛，只打印提示。
"""

import os
import re

import pytest
import yaml

from HAT.ai.ai_debug_helper import ai_debug
from HAT.core.global_context import GlobalContext

# 诊断报告输出目录。放在框架根目录下
AI_DEBUG_REPORT_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "ai_debug_reports",
)

# 响应体截断长度。太长会把提示词刷爆，够诊断用即可
RESPONSE_TEXT_MAX_LENGTH = 3000


def _extract_exception(report):
    """从测试报告中提取异常文本。

    :param report: pytest 的测试报告对象
    :return: 异常文本
    """
    try:
        text = report.longreprtext
        if text:
            return text
    except Exception:
        pass
    longrepr = getattr(report, "longrepr", None)
    return str(longrepr) if longrepr else "（未找到异常信息）"


def _get_response():
    """从全局上下文取出最后一个响应对象。

    HAT 的请求关键字（send_request / post_request / get_request）
    会把响应写入 GlobalContext 的 "response" 键。

    :return: requests.Response 对象；找不到时返回 None
    """
    try:
        response = GlobalContext().get_context("response")
    except Exception:
        return None
    if response is not None and hasattr(response, "status_code"):
        return response
    return None


def _extract_request_info(response):
    """从响应对象反推请求信息。

    :param response: requests.Response 对象，可能为 None
    :return: 请求信息文本
    """
    if response is None:
        return "未在全局上下文中找到响应对象，无法提取请求信息"

    request = getattr(response, "request", None)
    if request is None:
        return "响应对象未携带请求信息"

    lines = [
        "请求方法: {}".format(getattr(request, "method", "未知")),
        "请求地址: {}".format(getattr(request, "url", "未知")),
    ]

    # 请求头。只记录非敏感的，避免把令牌写进报告
    headers = getattr(request, "headers", {}) or {}
    safe_headers = {
        key: value for key, value in headers.items()
        if key.lower() not in ("authorization", "cookie")
    }
    lines.append("请求头: {}".format(safe_headers))

    # 请求体
    body = getattr(request, "body", None)
    if body:
        if isinstance(body, bytes):
            # requests 把 JSON 请求体编码成了 bytes，这里尝试解回文本。
            # 解不出来（比如上传的文件）就只记长度
            try:
                lines.append("请求体: {}".format(body.decode("utf-8")))
            except UnicodeDecodeError:
                lines.append("请求体: <二进制数据，长度 {}>".format(len(body)))
        else:
            lines.append("请求体: {}".format(body))

    return "\n".join(lines)


def _extract_response_text(response):
    """提取响应体文本，过长时截断。

    :param response: requests.Response 对象，可能为 None
    :return: 响应体文本
    """
    if response is None:
        return "未在全局上下文中找到响应对象，无法提取响应体"

    text = getattr(response, "text", "") or ""
    if len(text) > RESPONSE_TEXT_MAX_LENGTH:
        text = text[:RESPONSE_TEXT_MAX_LENGTH] + "\n... (响应体过长已截断)"

    return "状态码: {}\n{}".format(getattr(response, "status_code", "未知"), text)


def _extract_case_content(item):
    """把失败用例的 case_info 原样转成 YAML 文本，作为「用例现场」。

    HAT 的用例是 YAML 数据而不是 Python 函数，
    等价于 day12 版本里的「失败位置源码片段」。

    :param item: pytest 的 item 对象
    :return: 用例内容文本
    """
    callspec = getattr(item, "callspec", None)
    params = getattr(callspec, "params", None) or {}
    case_info = params.get("case_info")
    if case_info is None:
        return "（未能从用例参数中取得 case_info）"
    try:
        return yaml.safe_dump(case_info, allow_unicode=True, sort_keys=False)
    except Exception:
        return str(case_info)


def _capture_web_screenshot(item):
    """Web 用例失败时截取当前页面，保存到诊断报告目录。

    WebCaseContext 初始化时会把当前 page 写入 GlobalContext 的 "page" 键，
    这里直接取用。API 用例没有 page，返回 None。

    :param item: pytest 的 item 对象
    :return: 截图文件路径；取不到 page 或截图失败时返回 None
    """
    try:
        from HAT.context.web_case_context import (
            get_current_page,
            get_failure_screenshot,
        )
    except Exception:
        return None

    # 优先用 test_runner 在异常路径上截取的失败现场（上下文释放前截取）
    failure_shot = get_failure_screenshot()
    if failure_shot and os.path.isfile(failure_shot):
        return failure_shot

    # 兜底：page 还活着时当场截一张
    try:
        page = get_current_page()
    except Exception:
        return None
    if page is None or not hasattr(page, "screenshot"):
        return None
    try:
        safe_name = re.sub(r'[\\/:*?"<>|\[\]]', "_", item.name or "unknown_case")
        file_path = os.path.join(AI_DEBUG_REPORT_DIR, "{}_fail.png".format(safe_name))
        page.screenshot(path=file_path, full_page=True)
        return file_path
    except Exception as error:
        print("[AI排错] Web 失败截图失败: {}".format(error))
        return None


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item, call):
    """用例失败时自动生成 AI 排错诊断报告。

    使用新版 wrapper 钩子（pytest 7.4+ 支持），
    旧版 hookwrapper 在 pytest 9 中已被移除。

    :param item: pytest 的 item 对象
    :param call: pytest 的 call 对象
    """
    # 执行钩子，拿到返回的报告对象。
    # 注意：wrapper 钩子的返回值会替换钩子结果，结尾必须 return report，
    # 否则下游钩子拿到 None 会直接崩掉
    report = yield

    # 把报告挂到 item 上，保持与 day12 版本一致的习惯
    setattr(item, "rep_" + report.when, report)

    # 只处理 call 阶段的失败
    if report.when != "call" or not report.failed:
        return report

    # 整个诊断流程用 try 包住。任何异常都不能影响 pytest 自身的判定
    try:
        response = _get_response()

        exception_text = _extract_exception(report)
        request_info = _extract_request_info(response)
        response_text = _extract_response_text(response)
        case_content = _extract_case_content(item)

        # Web 用例失败时额外截取页面现场。
        # 注意：REPORT_TEMPLATE 不渲染 context，截图路径必须并进 response_text
        # 才能落到报告里（Web 用例本来就没有接口响应体，刚好放在这一节）
        screenshot_path = _capture_web_screenshot(item)
        if screenshot_path:
            response_text = "失败时页面截图: {}\n{}".format(screenshot_path, response_text)

        context = (
            "测试框架: HAT（关键字驱动，用例为 YAML 数据）\n"
            "用例: {}\n"
            "用例节点: {}\n"
            "{}"
            "说明: 「失败位置源码」一节是该用例的 YAML 内容，不是 Python 代码"
        ).format(
            item.name,
            getattr(item, "nodeid", ""),
            "失败时页面截图: {}\n".format(screenshot_path) if screenshot_path else "",
        )

        ai_debug(
            exception=exception_text,
            request_info=request_info,
            response_text=response_text,
            code_snippet=case_content,
            context=context,
            case_name=item.name,
            case_file=getattr(item, "nodeid", ""),
            stage="call",
            report_dir=AI_DEBUG_REPORT_DIR,
        )

        print("\n[AI排错] 已生成诊断报告: {}/{}_debug.md".format(
            AI_DEBUG_REPORT_DIR, item.name))

    except Exception as error:
        # 诊断失败只打印提示，绝不影响测试结果
        print("[AI排错] 生成诊断报告时出错: {}".format(error))

    # wrapper 钩子的返回值就是钩子结果，必须原样交还
    return report
