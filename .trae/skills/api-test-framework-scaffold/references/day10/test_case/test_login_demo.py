# -*- coding: utf-8 -*-
"""
day10 / test_case / test_login_demo.py

登录接口的演示用例，展示传统断言与 AI 自然语言断言的两种写法。

被测接口：POST /api/v1/auth/login
测试账号：admin / admin123（从 utils/config.py 读取，不在用例里写死）

4 条用例的分工：
    1. test_login_success            —— 传统断言：校验状态码与响应结构
    2. test_login_token_field        —— 传统断言：校验令牌字段存在且非空
    3. test_login_ai_assert_soft     —— AI 断言 strict=False：不满足只打印，不让用例失败
    4. test_login_ai_assert_strict   —— AI 断言 strict=True：不满足抛 AssertionError

AI 断言的两种模式对比：
    strict=False —— 「观察型」断言。规则写错了也不会让用例失败，
                    适合探索阶段，或把 AI 断言当作传统断言的补充验证。
    strict=True  —— 「把关型」断言。不满足直接抛 AssertionError，
                    pytest 判定用例失败，并自动触发根 conftest 里的 AI 排错钩子。

与传统断言的分工：
    传统断言  —— 口径明确、失败信息可读、可执行性强，是主体写法；
    AI 断言   —— 用中文描述复杂条件（如「状态码 200 且 data 非空且 user.role 为 admin」），
                 写起来比一串 if/assert 省事，作为补充手段使用。

运行方式：
    cd d:/AI_API_AUTO2.0/day10
    python -m pytest test_case/test_login_demo.py -v
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

# 把 day10 目录与项目根补进 sys.path，
# 保证「from utils.xxx import ...」与「from day10.utils.xxx import ...」都能解析
for _path in (str(DAY10_DIR), str(PROJECT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# AI 自然语言断言
try:
    from utils.ai_assert import ai_assert
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    from day10.utils.ai_assert import ai_assert

# 共享配置。地址、账号、接口路径统一从配置层取
try:
    from utils.config import BASE_URL, LOGIN_PATH, PASSWORD, USERNAME
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    from day10.utils.config import BASE_URL, LOGIN_PATH, PASSWORD, USERNAME


# ============================================================================
# 1. 用例一：传统断言 —— 校验状态码与响应结构
# ============================================================================

@pytest.mark.auth
@allure.feature("登录模块")
@allure.story("登录断言演示")
@allure.title("DEMO-LOGIN-001 传统断言：登录成功并返回完整响应结构")
@allure.description(
    "传统写法：明确断言状态码与响应体顶层字段。\n\n"
    "这类断言可执行性强、失败信息明确，是接口测试的主体写法。"
)
def test_login_success(session_http_client):
    """用例 DEMO-LOGIN-001：正确账号密码登录成功。

    使用 session_http_client 夹具发请求。
    该夹具是会话级的未登录客户端，正好用于登录接口本身。

    :param session_http_client: 会话级 HttpClient
    :raises AssertionError: 状态码或响应结构不符合预期
    """
    # 第 1 步：构造请求体
    payload = {"username": USERNAME, "password": PASSWORD}

    # 第 2 步：发送请求。expect_status=None 时不做状态码断言，
    # 留给下面用传统断言写清楚失败信息
    response = session_http_client.post(
        LOGIN_PATH, json_body=payload, expect_status=None
    )

    # 第 3 步：断言状态码
    assert response.status_code == 200, \
        "期望状态码 200，实际 {}".format(response.status_code)

    # 第 4 步：断言响应体结构
    data = response.json()
    assert isinstance(data, dict), "响应体应为 JSON 对象"
    assert "access_token" in data, \
        "响应体应包含 access_token 字段，实际字段: {}".format(list(data.keys()))
    assert data.get("token_type"), "token_type 不应为空"
    assert data.get("user"), "user 字段不应为空"

    print("登录成功，令牌前缀: {}".format(str(data.get("access_token"))[:20]))


# ============================================================================
# 2. 用例二：传统断言 —— 校验令牌字段存在且非空
# ============================================================================

@pytest.mark.auth
@allure.feature("登录模块")
@allure.story("登录断言演示")
@allure.title("DEMO-LOGIN-002 传统断言：令牌非空且用户信息正确")
@allure.description(
    "演示嵌套字段的取值方式：登录接口把角色放在 user 对象里，\n"
    "所以要取 data['user']['role'] 而不是 data['role']。"
)
def test_login_token_field(session_http_client):
    """用例 DEMO-LOGIN-002：响应中包含非空的访问令牌。

    :param session_http_client: 会话级 HttpClient
    :raises AssertionError: 令牌缺失、为空或用户信息不完整
    """
    # 第 1 步：发送登录请求
    response = session_http_client.post(
        LOGIN_PATH,
        json_body={"username": USERNAME, "password": PASSWORD},
        expect_status=None,
    )

    # 第 2 步：断言状态码
    assert response.status_code == 200, \
        "期望状态码 200，实际 {}".format(response.status_code)

    # 第 3 步：取出响应体
    data = response.json()

    # 第 4 步：断言令牌非空
    access_token = data.get("access_token")
    assert access_token, "access_token 不应为空"
    assert isinstance(access_token, str), "access_token 应为字符串"

    # 第 5 步：断言嵌套的用户信息
    user = data.get("user") or {}
    assert user.get("username") == USERNAME, \
        "user.username 应为 {}，实际 {}".format(USERNAME, user.get("username"))
    assert user.get("role"), "user.role 不应为空"

    print("令牌类型: {}，用户角色: {}".format(data.get("token_type"), user.get("role")))


# ============================================================================
# 3. 用例三：AI 断言 —— strict=False，不满足也不让用例失败
# ============================================================================

@pytest.mark.ai
@allure.feature("登录模块")
@allure.story("登录断言演示")
@allure.title("DEMO-LOGIN-003 AI 断言（观察型）：strict=False 不满足只打印")
@allure.description(
    "strict=False 时，即使规则不满足也只打印结论，不抛异常，用例依然判定为通过。\n\n"
    "适用场景：\n"
    "    1. 规则还在调整中，先观察大模型的判断对不对，不急着卡住流水线；\n"
    "    2. 作为传统断言的补充，对传统断言覆盖不到的地方做额外验证；\n"
    "    3. 探索阶段快速摸底。"
)
def test_login_ai_assert_soft(session_http_client):
    """用例 DEMO-LOGIN-003：AI 自然语言断言，观察型用法。

    :param session_http_client: 会话级 HttpClient
    """
    # 第 1 步：发送登录请求
    response = session_http_client.post(
        LOGIN_PATH,
        json_body={"username": USERNAME, "password": PASSWORD},
        expect_status=None,
    )

    # 第 2 步：用中文描述规则，交给 AI 判断
    # strict=False，不满足时只打印结论
    satisfied = ai_assert(
        response,
        "状态码等于 200，响应体包含 access_token 字段且值非空",
        strict=False,
        context="POST {}{}".format(BASE_URL, LOGIN_PATH),
    )

    # 第 3 步：打印判断结果。strict=False 时这里不会失败
    print("AI 断言判断结果: {}".format("满足" if satisfied else "不满足"))


# ============================================================================
# 4. 用例四：AI 断言 —— strict=True，不满足抛 AssertionError
# ============================================================================

@pytest.mark.ai
@allure.feature("登录模块")
@allure.story("登录断言演示")
@allure.title("DEMO-LOGIN-004 AI 断言（把关型）：strict=True 不满足则用例失败")
@allure.description(
    "strict=True 时，规则不满足会抛 AssertionError，pytest 判定用例失败，\n"
    "并自动触发根 conftest 里的 AI 排错钩子，在 ai_debug_reports/ 下生成诊断报告。\n\n"
    "适用场景：\n"
    "    1. 规则已经稳定，把它当作真正的断言来把关；\n"
    "    2. 复杂条件用自然语言描述比写一堆 if/assert 更直观。"
)
def test_login_ai_assert_strict(session_http_client):
    """用例 DEMO-LOGIN-004：AI 自然语言断言，把关型用法。

    :param session_http_client: 会话级 HttpClient
    :raises AssertionError: AI 判断规则不满足
    """
    # 第 1 步：发送登录请求
    response = session_http_client.post(
        LOGIN_PATH,
        json_body={"username": USERNAME, "password": PASSWORD},
        expect_status=None,
    )

    # 第 2 步：用中文描述规则，交给 AI 判断
    # strict=True，不满足时抛 AssertionError
    ai_assert(
        response,
        "状态码等于 200，响应体包含 access_token 字段，"
        "user 对象里的 username 等于 admin，role 等于 admin",
        strict=True,
        context="POST {}{}".format(BASE_URL, LOGIN_PATH),
    )

    print("AI 断言通过")


if __name__ == "__main__":
    # 直接运行本文件时，以 pytest 方式执行
    pytest.main(["-v", __file__])
