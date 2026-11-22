# -*- coding: utf-8 -*-
"""
day10 / test_case / test_login.py

登录接口的 YAML 数据驱动测试。

用例数据全部来自 day10/data/yaml_data/login.yaml，
本文件只负责「怎么执行、怎么断言」：
    - 数据解析：utils/yaml_loader.py 的 load_cases；
    - 请求发送：直接用 requests，保持用例数据驱动与 HTTP 客户端解耦；
    - 断言口径：HTTP 状态码、响应 message、expect_json 字段级断言。

断言失败时的报错信息必须包含 case_id、case_name、请求参数与实际响应，
否则 28 条用例一起失败时无法定位到具体是哪一条、发了什么、收到了什么。

导入兼容：
    项目既有风格是 from utils.xxx import ...，
    但 pytest 以包模式收集（day10/ 与 day10/test_case/ 都有 __init__.py）时，
    顶层导入可能失败。这里先尝试顶层导入，失败再退回包式导入，
    并把 day10 目录补进 sys.path，保证各种运行方式都能跑通。

运行方式：
    cd d:/AI_API_AUTO2.0/day10
    python -m pytest test_case/test_login.py -v
"""

# 第三方库：pytest 测试框架
import pytest

# 第三方库：requests，用于发送请求
import requests

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

# 用例数据文件路径。全部基于本文件位置动态计算，不硬编码任何绝对路径
YAML_PATH = DAY10_DIR / "data" / "yaml_data" / "login.yaml"

# day10 目录不在 sys.path 中时补进去。
# 补进去之后 from utils.xxx import ... 才能解析，
# 否则顶层导入会因找不到 utils 包而失败
for _path in (str(DAY10_DIR), str(PROJECT_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)

# 导入 YAML 加载工具。
# 先试顶层导入（项目既有风格），失败再退回包式导入，两种运行方式都能工作
try:
    from utils.yaml_loader import load_cases, jsonpath_get
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    from day10.utils.yaml_loader import load_cases, jsonpath_get

# 导入共享配置。地址、账号、接口路径都从配置层拿，代码里不出现硬编码
try:
    from utils.config import BASE_URL, LOGIN_PATH, TIMEOUT
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    from day10.utils.config import BASE_URL, LOGIN_PATH, TIMEOUT


# ============================================================================
# 1. 加载用例数据
# ============================================================================

# 变量表。显式传入的变量优先级最高，
# 保证 YAML 里的 ${BASE_URL} 一定渲染成本文件里的 BASE_URL
VARIABLES = {"BASE_URL": BASE_URL}

# 加载用例数据。
# 数据文件写错时（编号重复、必填缺失、状态码缺失），
# 加载阶段就会抛出带文件名与用例位置的异常，收集阶段直接报错，不会静默跳过
CASES = load_cases(YAML_PATH, variables=VARIABLES)


# ============================================================================
# 2. 用例执行
# ============================================================================

@pytest.mark.auth
@pytest.mark.parametrize(
    "case",
    CASES,
    ids=lambda case: case.pytest_id,
)
@allure.feature("登录模块")
@allure.story("{case.story}")
@allure.title("{case.case_name}")
@allure.description(
    "登录接口的 YAML 数据驱动校验。\n\n"
    "断言点：\n"
    "    1. HTTP 状态码与用例数据中的 expect_status 一致；\n"
    "    2. 失败场景校验 message 包含期望的关键字；\n"
    "    3. expect_json 中声明的字段逐个做 JSONPath 断言。"
)
def test_login_from_yaml(case):
    """登录接口数据驱动用例。

    :param case: ApiCase 对象，由 @pytest.mark.parametrize 注入
    """
    # story 在运行时动态设置。
    # @allure.story 是静态装饰器，写死在函数上，
    # 所有参数化用例都会落到同一个 story 分组里；
    # 而 feature/story 这类 label 在 Allure 内部不支持 {param} 变量替换，
    # 所以想在报告里按场景分组，只能在用例体内用 allure.dynamic.story 追加。
    allure.dynamic.story(case.story)

    # 第 1 步：跳过标记的用例。skip_reason 作为跳过原因
    if case.skip:
        pytest.skip(case.skip_reason or "用例被标记为跳过")

    # 第 2 步：拼出完整请求地址
    url = case.url

    # 第 3 步：组装请求参数。
    # raw_body 优先（用于构造非 JSON 请求体），其次是 json_body
    request_kwargs = {"headers": case.headers, "timeout": TIMEOUT}
    if case.raw_body is not None:
        request_kwargs["data"] = case.raw_body
    elif case.json_body is not None:
        request_kwargs["json"] = case.json_body

    # 第 4 步：按 repeat 次数重复执行。重复执行的场景用于验证幂等性
    for index in range(case.repeat):
        response = requests.request(case.method, url, **request_kwargs)

        # 第 5 步：断言状态码。失败信息带完整上下文，便于批量失败时定位
        assert case.expect_status == response.status_code, \
            "用例 {} ({}) 期望状态码 {}，实际 {}。\n请求参数: {}\n实际响应: {}".format(
                case.case_id,
                case.case_name,
                case.expect_status,
                response.status_code,
                request_kwargs.get("json", request_kwargs.get("data")),
                response.text[:500],
            )

        # 第 6 步：解析响应体。响应不是合法 JSON 时跳过后续的字段断言
        try:
            body = response.json()
        except ValueError:
            body = None

        # 第 7 步：失败场景校验 message 包含期望关键字
        if case.expect_message and body is not None:
            actual_message = body.get("message") or body.get("detail") or ""
            assert case.expect_message in str(actual_message), \
                "用例 {} ({}) 的 message 应包含 {}，实际为: {}\n实际响应: {}".format(
                    case.case_id,
                    case.case_name,
                    case.expect_message,
                    actual_message,
                    response.text[:500],
                )

        # 第 8 步：逐个断言 expect_json 里声明的字段。
        # 用 JSONPath 取值，取不到或值不等都算失败
        for expression, expected_value in case.expect_json.items():
            actual_value = jsonpath_get(body, expression)
            assert actual_value == expected_value, \
                "用例 {} ({}) 断言失败：{} 期望值 {!r}，实际 {!r}\n实际响应: {}".format(
                    case.case_id,
                    case.case_name,
                    expression,
                    expected_value,
                    actual_value,
                    response.text[:500],
                )


if __name__ == "__main__":
    # 直接运行本文件时，以 pytest 方式执行
    pytest.main(["-v", __file__])
