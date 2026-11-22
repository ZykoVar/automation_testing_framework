# -*- coding: utf-8 -*-
"""
day10 / test_case / test_demo_fail.py

故意失败的演示用例，用来展示 AI 自动排错诊断的完整效果。

这 2 条用例都是「故意写错」的，正常运行时必定失败，
这是本文件的设计目的 —— 失败才能触发根 conftest 里的 AI 排错钩子。

两条用例分别覆盖两类典型错误：
    1. test_demo_fail_status_code —— 写错了状态码期望值。
       请求本身完全正确，但断言写成了 201，
       属于「接口行为与预期不符」类问题。
    2. test_demo_fail_method      —— 用 GET 方法去调只接受 POST 的接口。
       属于「请求没发对」类问题，服务端会返回 405。

跑完之后到 ai_debug_reports/ 目录看生成的诊断报告。

两条用例都带 demo_fail 标记，需要时用下面这条命令排除它们，
让流水线恢复绿色：
    python -m pytest test_case -v -m "not demo_fail"

运行方式：
    cd d:/AI_API_AUTO2.0/day10
    python -m pytest test_case/test_demo_fail.py -v
"""

# 第三方库：pytest 测试框架
import pytest

# 第三方库：allure 测试报告框架
import allure

# 标准库：路径处理与模块搜索路径
import os
import sys
from pathlib import Path

# ============================================================================
# 0. 路径引导与导入兼容
# ============================================================================

# 本文件位于 day10/test_case/，上溯一级是 day10，上溯两级是项目根
DAY10_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = DAY10_DIR.parent

# 把 day10 目录与项目根补进 sys.path，保证包式导入能解析
for _path in (str(DAY10_DIR), str(PROJECT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# 共享配置
try:
    from utils.config import BASE_URL, LOGIN_PATH, PASSWORD, USERNAME
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    from day10.utils.config import BASE_URL, LOGIN_PATH, PASSWORD, USERNAME


# ============================================================================
# 1. 用例一：状态码断言写错
# ============================================================================

@pytest.mark.demo_fail
@allure.feature("AI排错演示")
@allure.story("故意失败用例")
@allure.title("DEMO-FAIL-001 故意写错状态码期望值，演示断言类排错")
@allure.description(
    "登录接口成功时返回 200，这里故意断言成 201。\n"
    "请求发得完全正确，错的是断言里的期望值 —— 这正是最常见也最容易误判的一类失败：\n"
    "到底是接口变了，还是测试写错了？"
)
def test_demo_fail_status_code(session_http_client):
    """用例 DEMO-FAIL-001：故意写错状态码期望值。

    :param session_http_client: 会话级 HttpClient
    :raises AssertionError: 状态码与故意写错的期望值不符
    """
    # 第 1 步：构造并发送请求。请求本身完全正确
    response = session_http_client.post(
        LOGIN_PATH,
        json_body={"username": USERNAME, "password": PASSWORD},
        expect_status=None,
    )

    # 第 2 步：打印实际状态码与响应体，方便对照
    print("实际状态码: {}".format(response.status_code))
    print("实际响应体: {}".format(response.text[:300]))

    # 第 3 步：故意写错的断言。期望值应该是 200，这里写成 201
    assert response.status_code == 201, \
        "期望状态码 201，实际 {}".format(response.status_code)


# ============================================================================
# 2. 用例二：用错请求方法
# ============================================================================

@pytest.mark.demo_fail
@allure.feature("AI排错演示")
@allure.story("故意失败用例")
@allure.title("DEMO-FAIL-002 故意用 GET 调只接受 POST 的接口")
@allure.description(
    "登录接口只支持 POST，用 GET 去调服务端会返回 405 Method Not Allowed。\n"
    "这类失败与上一条性质不同：上一条是「响应拿到了，但和预期不符」，\n"
    "这一条是「请求本身就没发对」。"
)
def test_demo_fail_method(session_http_client):
    """用例 DEMO-FAIL-002：故意用 GET 调只接受 POST 的接口。

    :param session_http_client: 会话级 HttpClient
    :raises AssertionError: 用 GET 调 POST 接口拿不到 200
    """
    # 第 1 步：故意用 GET 方法调登录接口
    response = session_http_client.get(LOGIN_PATH, expect_status=None)

    # 第 2 步：打印实际状态码与响应体
    print("实际状态码: {}".format(response.status_code))
    print("实际响应体: {}".format(response.text[:300]))

    # 第 3 步：断言期望 200，但 GET 方法拿不到
    assert response.status_code == 200, \
        "期望状态码 200，实际 {}".format(response.status_code)


if __name__ == "__main__":
    # 直接运行本文件时，以 pytest 方式执行
    pytest.main(["-v", __file__])
