# -*- coding: utf-8 -*-
"""
day10 / conftest.py

day10 根目录的 conftest，提供全目录共享的 fixture 与失败诊断钩子。

pytest 的 conftest 分层机制：
    根目录 conftest.py     —— 对 day10 及其所有子目录生效
    test_case/conftest.py  —— 只对 test_case 目录生效

根 conftest 只负责「与被测系统打交道的公共设施」：
    1. session_http_client —— 全局共享的未登录 HttpClient，Session 复用连接池；
    2. auth_http_client   —— 已登录的 HttpClient，令牌由客户端自动管理。

这里用 yield 的原因：
    pytest 夹具在 yield 之前是「准备」，yield 之后是「清理」。
    把创建动作放在 yield 之前、释放动作放在 yield 之后，
    资源就既能提前交付给用例，又能在用例结束后自动回收。

此外还挂了一个失败诊断钩子：
    pytest_runtest_makereport —— 用例 call 阶段失败时，
    自动收集异常、请求信息、响应体与源码片段，调用 AI 生成诊断，
    并把报告写到 ai_debug_reports/用例名_debug.md。
    该钩子只做旁路增强，任何异常都不会影响 pytest 自身的判定流程。
"""

# 第三方库：pytest 测试框架
import pytest

# 第三方库：requests，仅用于探测服务是否可达
import requests

# 标准库：路径处理与模块搜索路径
import os
import sys

# 标准库：读取失败用例的源码片段
import inspect
import traceback

# ============================================================================
# 0. 路径引导
#    pytest 以「prepend」模式导入 conftest 时，会把本文件所在目录向上回溯，
#    找到第一个不含 __init__.py 的目录并插入 sys.path。
#    day10/ 与 day10/test_case/ 都有 __init__.py，所以回溯到项目根，
#    「from day10.utils import ...」在 pytest 下一定能解析。
#
#    但直接用 python 执行测试文件时，sys.path[0] 是测试文件所在目录，
#    项目根不在其中，包式导入就会失败。
#    这里显式把项目根加入 sys.path，保证各种调用方式都能跑。
# ============================================================================

# 定位项目根目录。本文件在 day10/ 下，上溯一级即为项目根
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# 项目根不在 sys.path 中时补进去。已存在则跳过，避免重复插入
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 本项目的 HTTP 客户端封装。
# 用包式导入 day10.utils 而非顶层导入 utils：
# day10 与它的子目录都有 __init__.py，属于一个包，
# 包式导入不依赖「当前工作目录恰好是 day10」这个前提
from day10.utils.AI_HttpClient import HttpClient

# 本项目的共享配置
from day10.utils.config import (
    BASE_URL,
    HEALTH_PATH,
    LOGIN_PATH,
    PASSWORD,
    TIMEOUT,
    USERNAME,
)

# AI 排错助手。该模块内部做了未配置 Key 的降级，导入它不会让测试跑不起来
from day10.utils.ai_debug_helper import ai_debug


# ============================================================================
# 1. 服务可用性探测
# ============================================================================

# 模块加载时探测一次服务是否可达。
# 服务不可达时整个 day10 目录的用例都会被跳过，
# 而不是让每条用例都去连接失败、报一堆无意义的错误
try:
    SERVICE_AVAILABLE = requests.get(
        BASE_URL + HEALTH_PATH, timeout=3
    ).status_code == 200
except requests.exceptions.RequestException:
    SERVICE_AVAILABLE = False


# ============================================================================
# 2. 共享 fixture
# ============================================================================

@pytest.fixture(scope="session")
def session_http_client():
    """会话级 HttpClient 夹具（未登录）。

    scope="session" 表示整个测试会话只创建一次，
    所有用例共用同一个 requests.Session，TCP 连接与 TLS 握手只付一次成本。

    该客户端始终保持「未登录」状态，专门用于鉴权失败类场景的验证
    （未带令牌时服务端应返回 401）。

    :return: 已配置好但未登录的 HttpClient 实例
    """
    # 创建客户端，配置基础地址、超时与重试策略
    client = HttpClient(
        base_url=BASE_URL,
        headers={"Accept": "application/json"},
        timeout=(3, TIMEOUT),
        retries=2,
        backoff=0.3,
    )
    # yield 之前是准备阶段，交给测试用例使用
    yield client
    # yield 之后是清理阶段，整个会话结束时释放连接池
    client.close()


@pytest.fixture(scope="session")
def auth_http_client():
    """会话级已登录 HttpClient 夹具。

    独立创建一个客户端并完成一次登录，
    令牌保存在该客户端内部，之后所有请求自动携带 Authorization 头，
    调用方无需手工传递。

    与 session_http_client 分开建实例，是为了让 session_http_client
    始终保持未登录状态 —— 鉴权失败类用例需要用它来构造「不带令牌」的请求。

    :return: 已完成登录的 HttpClient 实例
    """
    # 创建独立的客户端，避免污染未登录客户端的状态
    client = HttpClient(
        base_url=BASE_URL,
        headers={"Accept": "application/json"},
        timeout=(3, TIMEOUT),
        retries=2,
        backoff=0.3,
    )
    # 执行登录。login() 内部用 expect_status 断言登录返回 200
    client.login(
        LOGIN_PATH,
        {"username": USERNAME, "password": PASSWORD},
        expect_status=200,
    )
    # 断言登录确实拿到了令牌，避免后续用例因未鉴权而产生误判
    assert client.is_authenticated, "登录后应持有访问令牌"
    # 交出同一个实例，鉴权头会自动附加到每次请求
    yield client
    # 会话结束时释放连接池
    client.close()


# ============================================================================
# 3. 失败诊断钩子
#    用例 call 阶段失败时，自动调用 AI 生成排错诊断报告。
#
#    工作流程：
#        1. pytest_runtest_makereport 在每个阶段结束时被调用；
#        2. 只在 phase == "call" 且用例 failed 时动手，
#           setup 阶段失败是环境问题、teardown 阶段失败是清理问题，
#           都不属于「用例逻辑写错」，不生成诊断；
#        3. 收集四样东西：异常信息、请求信息、响应体、源码片段；
#        4. 调 ai_debug 生成 Markdown 报告写到 ai_debug_reports/。
#
#    健壮性要求（重要）：
#        诊断是旁路增强，不能反过来影响测试结果。
#        所以整个钩子体用 try/except 包住，
#        任何异常都不向上抛，只打印提示。
# ============================================================================

# 诊断报告输出目录。放在 day10 项目根下
AI_DEBUG_REPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                                   "ai_debug_reports")

# 收集失败现场时，源码片段保留的行数。太多看不清，太少定位不准
CODE_SNIPPET_LINES = 12


def _get_excinfo(item, call):
    """取到失败时的异常信息结构。

    pytest 9 里 report.excinfo 已被移除，异常信息要从 call.excinfo 拿，
    它是一个 ExceptionInfo 对象，带 .tb / .type / .value 等属性。
    旧版 pytest 的 report.excinfo 是三元组，这里一并兼容。

    :param item: pytest 的 item 对象
    :param call: pytest 的 call 对象
    :return: 异常信息对象，取不到时返回 None
    """
    # 新版：call.excinfo 是 ExceptionInfo 对象
    excinfo = getattr(call, "excinfo", None)
    if excinfo is not None:
        return excinfo

    # 旧版：report.excinfo 是三元组
    report = getattr(item, "rep_call", None)
    if report is not None:
        return getattr(report, "excinfo", None)

    return None


def _get_traceback(excinfo):
    """从异常信息里取出 traceback 对象。

    :param excinfo: 异常信息对象
    :return: traceback 对象；取不到时返回 None
    """
    if excinfo is None:
        return None

    # 新版：ExceptionInfo 有 tb 属性
    tb = getattr(excinfo, "tb", None)
    if tb is not None:
        return tb

    # 旧版：三元组的第三项
    try:
        return excinfo[2]
    except (IndexError, TypeError):
        return None


def _find_response(item, call):
    """从失败现场找出响应对象。

    响应对象通常是用例里的局部变量（response = requests.post(...)），
    不在 pytest 的 funcargs 里，所以要从 traceback 的栈帧局部变量中找。

    :param item: pytest 的 item 对象
    :param call: pytest 的 call 对象
    :return: requests.Response 对象；找不到时返回 None
    """
    # 先看用例参数。响应对象被做成夹具参数时走这条路
    funcargs = getattr(item, "funcargs", {}) or {}
    for name in ("response", "resp", "res", "r"):
        candidate = funcargs.get(name)
        if candidate is not None and hasattr(candidate, "status_code"):
            return candidate

    # 再看 traceback 栈帧的局部变量。
    # 从最内层帧往外找，用例自己那一帧里的 response 就是要找的
    tb = _get_traceback(_get_excinfo(item, call))
    frames = []
    while tb is not None:
        frames.append(tb.tb_frame)
        tb = tb.tb_next

    # 从最内层往外层找
    for frame in reversed(frames):
        local_vars = frame.f_locals or {}
        for name in ("response", "resp", "res", "r"):
            candidate = local_vars.get(name)
            if candidate is not None and hasattr(candidate, "status_code"):
                return candidate

    return None


def _extract_request_info(item, call):
    """从测试函数里提取请求信息。

    优先找用例里保存下来的响应对象与请求参数，
    找不到就退回成简略说明。

    :param item: pytest 的 item 对象
    :param call: pytest 的 call 对象
    :return: 请求信息文本
    """
    # 找响应对象
    response = _find_response(item, call)

    # 没找到响应对象时只给出用例名，说明现场信息有限
    if response is None:
        return "未在失败现场找到响应对象，无法提取请求信息"

    # 拼装请求信息
    lines = [
        "请求方法: {}".format(getattr(response.request, "method", "未知")),
        "请求地址: {}".format(getattr(response.request, "url", "未知")),
    ]

    # 请求头。只记录非敏感的，避免把令牌写进报告
    headers = getattr(response.request, "headers", {}) or {}
    safe_headers = {
        key: value for key, value in headers.items()
        if key.lower() not in ("authorization", "cookie")
    }
    lines.append("请求头: {}".format(safe_headers))

    # 请求体
    body = getattr(response.request, "body", None)
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


def _extract_response_text(item, call):
    """从测试函数里提取响应体文本。

    :param item: pytest 的 item 对象
    :param call: pytest 的 call 对象
    :return: 响应体文本
    """
    # 找响应对象
    response = _find_response(item, call)

    if response is None:
        return "未在失败现场找到响应对象，无法提取响应体"

    # 响应体可能很大，截断到 3000 字符，够诊断用了
    text = getattr(response, "text", "") or ""
    if len(text) > 3000:
        text = text[:3000] + "\n... (响应体过长已截断)"

    return "状态码: {}\n{}".format(
        getattr(response, "status_code", "未知"), text
    )


def _extract_code_snippet(item, call):
    """提取失败位置附近的源码片段。

    :param item: pytest 的 item 对象
    :param call: pytest 的 call 对象
    :return: 源码片段文本
    """
    # 拿到用例函数对象
    func = getattr(item, "function", None)
    if func is None:
        return "（无法定位用例函数源码）"

    try:
        # 取整个函数的源码
        source = inspect.getsource(func)
        lines = source.splitlines()

        # 默认截取整个函数
        start = 0
        end = len(lines)

        # 定位到具体行号，截取该行附近的代码。
        # 不同 pytest 版本的报告结构不同：
        #   旧版是 ReprExceptionInfo，有 tb 属性；
        #   新版是 ExceptionChainRepr，需要从 chain 里逐个取 tb。
        # 这里统一走 _get_traceback_lines() 拿行号列表。
        error_lines = _get_traceback_lines(item, call)
        if error_lines:
            # 取最后一处出错行
            lineno = error_lines[-1]
            offset = lineno - 1
            if 0 <= offset < len(lines):
                start = max(0, offset - CODE_SNIPPET_LINES // 2)
                end = min(len(lines), start + CODE_SNIPPET_LINES)

        # 拼接片段并标注行号，便于定位
        snippet = []
        for offset in range(start, end):
            snippet.append("{:>4} | {}".format(offset + 1, lines[offset]))
        return "\n".join(snippet)
    except (OSError, TypeError, IndexError):
        # 取不到源码时给出兜底说明
        return "（无法读取用例源码: {}）".format(
            getattr(item, "nodeid", "未知用例")
        )


def _get_traceback_lines(item, call):
    """从失败报告里取出 traceback 的行号列表。

    :param item: pytest 的 item 对象
    :param call: pytest 的 call 对象
    :return: 行号列表
    """
    lines = []

    # 优先用 excinfo 的 tb，最稳定
    tb = _get_traceback(_get_excinfo(item, call))
    while tb is not None:
        lines.append(tb.tb_lineno)
        tb = tb.tb_next

    if lines:
        return lines

    # 退回到解析 longrepr
    report = getattr(item, "rep_call", None)
    longrepr = getattr(report, "longrepr", None) if report else None
    if longrepr is None:
        return []

    # 新版结构：ExceptionChainRepr，chain 里每项是 (ReprTraceback, 位置, excinfo)
    chain = getattr(longrepr, "chain", None)
    if chain:
        for entry in chain:
            # entry[0] 是 ReprTraceback，其 reprentries 里每项有 lineno
            repr_traceback = entry[0] if isinstance(entry, (tuple, list)) else entry
            for repr_entry in getattr(repr_traceback, "repentries", []) or []:
                lineno = getattr(repr_entry, "lineno", None)
                if lineno:
                    lines.append(lineno)
        if lines:
            return lines

    # 旧版结构：直接有 tb 属性
    tb = getattr(longrepr, "tb", None)
    while tb is not None:
        lines.append(tb.tb_lineno)
        tb = tb.tb_next

    return lines


def _extract_exception(item, call):
    """从测试报告中提取异常信息。

    :param item: pytest 的 item 对象
    :param call: pytest 的 call 对象
    :return: 异常文本
    """
    report = getattr(item, "rep_call", None)
    if report is not None:
        try:
            # longreprtext 里带完整 traceback，最有用
            text = report.longreprtext
            if text:
                return text
        except Exception:
            pass

    # 退一步用 excinfo 拼
    excinfo = _get_excinfo(item, call)
    if excinfo is not None:
        # 新版：ExceptionInfo 有 .value
        value = getattr(excinfo, "value", None)
        if value is not None:
            tb = _get_traceback(excinfo)
            if tb is not None:
                return "".join(traceback.format_exception(type(value), value, tb))
            return "{}: {}".format(type(value).__name__, value)

        # 旧版：三元组
        try:
            return "".join(traceback.format_exception(*excinfo))
        except (TypeError, ValueError):
            pass

    return "（未找到异常信息）"


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    """用例失败时自动生成 AI 排错诊断报告。

    用 hookwrapper 拿到每个阶段的执行结果，
    在 call 阶段失败时收集现场信息并调用 AI 生成诊断。

    :param item: pytest 的 item 对象
    :param call: pytest 的 call 对象
    """
    # 执行钩子，拿到 outcome 后可以读取报告信息
    outcome = yield

    # 拿这次阶段的执行结果
    report = outcome.get_result()

    # 把报告挂到 item 上，后续 makereport 钩子可以复用
    setattr(item, "rep_" + report.when, report)

    # 只处理 call 阶段的失败。setup 失败是环境问题，teardown 失败是清理问题
    if report.when != "call" or not report.failed:
        return

    # 整个诊断流程用 try 包住。任何异常都不能影响 pytest 自身的判定
    try:
        # 第 1 步：收集现场信息
        exception_text = _extract_exception(item, call)
        request_info = _extract_request_info(item, call)
        response_text = _extract_response_text(item, call)
        code_snippet = _extract_code_snippet(item, call)

        # 第 2 步：拼上下文，告诉大模型这是哪个服务、哪个用例
        context = (
            "被测服务: {}\n"
            "用例: {}\n"
            "用例文件: {}\n"
            "运行命令: python -m pytest {} -v"
        ).format(
            BASE_URL,
            item.name,
            getattr(item, "location", ""),
            getattr(item, "nodeid", ""),
        )

        # 第 3 步：调用 AI 生成诊断并写盘
        ai_debug(
            exception=exception_text,
            request_info=request_info,
            response_text=response_text,
            code_snippet=code_snippet,
            context=context,
            case_name=item.name,
            case_file=getattr(item, "location", ""),
            stage="call",
            report_dir=AI_DEBUG_REPORT_DIR,
        )

        # 提示报告位置，方便直接打开
        print("\n[AI排错] 已生成诊断报告: {}/{}_debug.md".format(
            AI_DEBUG_REPORT_DIR, item.name))

    except Exception as error:
        # 诊断失败只打印提示，绝不影响测试结果
        print("[AI排错] 生成诊断报告时出错: {}".format(error))
