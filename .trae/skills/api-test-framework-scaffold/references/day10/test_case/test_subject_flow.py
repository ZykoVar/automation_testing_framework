# -*- coding: utf-8 -*-
"""
day10 / test_case / test_subject_flow.py

学科管理业务流程测试，同时演示 Excel 数据驱动。

被测接口：
    POST   /api/v1/subjects/            新增学科
    GET    /api/v1/subjects/            学科列表
    PUT    /api/v1/subjects/{id}        修改学科
    DELETE /api/v1/subjects/{id}        删除/停用学科

用例分布：
    1. test_create_subject_from_excel   —— Excel 数据驱动：读取 create_subject.xlsx 批量执行
    2. test_subject_full_flow           —— 完整链路：创建 → 列表查询 → 修改 → 删除
    3. test_subject_create_failed       —— 创建学科失败：必填字段缺失
    4. test_subject_delete_failed       —— 删除学科失败：学科不存在
    5. test_subject_delete_without_token —— 删除学科失败：未携带令牌

Excel 数据驱动的价值：
    用例数据放在 Excel 里，业务同学可以直接编辑，新增场景不用改代码。
    Excel 的列名与 YAML 的字段一一对应，由 utils/excel_loader.py 解析成
    与 YAML 完全一致的 ApiCase 对象，所以两条驱动的测试函数可以互相替换。

Excel 文件由 utils/yaml_excel_generator.py 从 YAML 反向生成：
    python day10/utils/yaml_excel_generator.py data/yaml_data/create_subject.yaml \
        -o data/excel_data/create_subject.xlsx

实测结论（断言以此为准）：
    201 学科创建成功，message=学科创建成功，data 为学科详情
    422 必填字段缺失，code=VALIDATION_ERROR，message=数据验证失败
    200 修改成功，message=学科更新成功
    200 学科不存在，message=学科不存在
    401 未携带令牌，code=UNAUTHORIZED，message=请先登录

运行方式：
    cd d:/AI_API_AUTO2.0/day10
    python -m pytest test_case/test_subject_flow.py -v
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

# Excel 用例加载器
try:
    from utils.excel_loader import load_cases as load_excel_cases
    from utils.yaml_loader import jsonpath_get
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    from day10.utils.excel_loader import load_cases as load_excel_cases
    from day10.utils.yaml_loader import jsonpath_get

# 共享配置
try:
    from utils.config import (
        BASE_URL,
        SUBJECTS_PATH,
        generate_subject_no,
    )
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    from day10.utils.config import (
        BASE_URL,
        SUBJECTS_PATH,
        generate_subject_no,
    )


# ============================================================================
# 1. 加载 Excel 用例数据
# ============================================================================

# Excel 用例数据文件路径。全部基于本文件位置动态计算，不硬编码绝对路径
EXCEL_PATH = DAY10_DIR / "data" / "excel_data" / "create_subject.xlsx"


def _replace_subject_code(case):
    """把 Excel 用例里的 ${SUBJECT_CODE} 换成唯一编码。

    只替换「值恰好是占位符」的字段。
    异常用例（如「编码超过二十个字符」）故意写了固定的长字符串，
    那种值不能替换 —— 换成唯一编码后校验场景就没了，
    用例会从「期望 422」变成「实际 201」。

    :param case: ApiCase 对象
    :return: 替换后的 ApiCase 对象
    """
    # 生成唯一编码
    unique_code = generate_subject_no()

    # 请求体里替换占位符。
    # 判据是值等于占位符本身，而不是「存在 code 字段就替换」
    if isinstance(case.json_body, dict) and case.json_body.get("code") == "${SUBJECT_CODE}":
        case.json_body["code"] = unique_code

    # 期望字段里同样替换，否则断言会拿占位符去比对
    for expression, expected_value in list(case.expect_json.items()):
        if expected_value == "${SUBJECT_CODE}":
            case.expect_json[expression] = unique_code

    return case


# 加载 Excel 用例。
# 学科编码在库里唯一，Excel 里写的是 ${SUBJECT_CODE} 占位符，
# 这里统一替换成运行时生成的唯一编码，避免第二次执行就撞「编码已存在」
EXCEL_CASES = [
    _replace_subject_code(case) for case in load_excel_cases(EXCEL_PATH)
]


# ============================================================================
# 2. 用例一：Excel 数据驱动
# ============================================================================

@pytest.mark.crud
@pytest.mark.parametrize(
    "case",
    EXCEL_CASES,
    ids=lambda case: case.pytest_id,
)
@allure.feature("学科管理")
@allure.story("新增学科数据驱动")
@allure.title("SUBJ-EXCEL-{case.case_id} Excel 驱动：{case.case_name}")
@allure.description(
    "用例数据来自 data/excel_data/create_subject.xlsx，\n"
    "由 utils/excel_loader.py 解析成与 YAML 完全一致的 ApiCase 对象。\n\n"
    "断言点：\n"
    "    1. HTTP 状态码与 expect_status 一致；\n"
    "    2. 失败场景校验 message 包含期望关键字；\n"
    "    3. expect_json 中声明的字段逐个做 JSONPath 断言。"
)
def test_create_subject_from_excel(auth_http_client, case):
    """用例 SUBJ-EXCEL：新增学科，Excel 数据驱动。

    :param auth_http_client: 已登录的 HttpClient
    :param case: ApiCase 对象，由 @pytest.mark.parametrize 注入
    :raises AssertionError: 状态码、message 或字段值与用例数据不符
    """
    # story 在运行时动态设置，便于在报告里按场景分组
    allure.dynamic.story(case.story)

    with allure.step("发送 {} 请求：{}".format(case.method, case.path)):
        response = auth_http_client.request(
            case.method,
            case.path,
            json_body=case.json_body,
            headers=case.headers,
            expect_status=None,
        )

    body = response.json()

    with allure.step("断言状态码为 {}".format(case.expect_status)):
        assert response.status_code == case.expect_status, \
            "用例 {} ({}) 期望状态码 {}，实际 {}。\n请求体: {}\n实际响应: {}".format(
                case.case_id,
                case.case_name,
                case.expect_status,
                response.status_code,
                case.json_body,
                response.text[:500],
            )

    with allure.step("断言响应 message 包含「{}」".format(case.expect_message or "")):
        if case.expect_message:
            actual_message = body.get("message") or body.get("detail") or ""
            assert case.expect_message in str(actual_message), \
                "用例 {} ({}) 的 message 应包含 {}，实际为: {}\n实际响应: {}".format(
                    case.case_id,
                    case.case_name,
                    case.expect_message,
                    actual_message,
                    response.text[:500],
                )

    with allure.step("逐个断言 expect_json 声明的字段"):
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

    # 清理：只有创建成功的用例才真的落库了数据。
    # 异常用例服务端已回滚，这里删不到东西也不会报错。
    # 不清理的话每次跑都会在库里留下一条「自动化测试学科」，越积越多
    created_id = (body.get("data") or {}).get("id")
    if created_id:
        with allure.step("清理：删除本次创建的学科 id={}".format(created_id)):
            auth_http_client.delete(
                "{}{}".format(SUBJECTS_PATH, created_id),
                expect_status=None,
            )


# ============================================================================
# 3. 用例二：学科全生命周期
# ============================================================================

@pytest.mark.crud
@pytest.mark.smoke
@allure.feature("学科管理")
@allure.story("学科全生命周期")
@allure.title("SUBJ-FLOW-001 创建学科后查询、修改、删除，数据闭环无残留")
@allure.description(
    "一条用例走完学科的完整生命周期，每一步都用 step 在报告里标出来。\n\n"
    "清理由 subject_factory 夹具兜底，即使断言失败也会删除临时数据。"
)
def test_subject_full_flow(subject_factory):
    """用例 SUBJ-FLOW-001：学科全生命周期。

    :param subject_factory: 学科数据工厂夹具
    :raises AssertionError: 任一环节的响应不符合预期
    """
    # 生成唯一学科编码
    subject_code = generate_subject_no()

    # ------------------------------------------------------------------
    # 第 1 步：创建学科
    # ------------------------------------------------------------------
    with allure.step("步骤1 创建学科：编码 {}".format(subject_code)):
        subject = subject_factory.create(
            code=subject_code,
            name="全流程测试学科",
            full_score=150,
            pass_score=90,
            sort_order=50,
        )

        assert subject.get("id") is not None, \
            "创建学科应返回学科 id，实际: {}".format(subject)
        assert subject.get("code") == subject_code, \
            "学科编码应回显为 {}，实际 {}".format(subject_code, subject.get("code"))
        assert subject.get("is_active") is True, \
            "新建学科的启用状态应为 True，实际 {}".format(subject.get("is_active"))

        subject_id = subject["id"]
        print("创建成功，学科 id={} 编码={}".format(subject_id, subject_code))

    # ------------------------------------------------------------------
    # 第 2 步：查询学科列表并确认新学科在列表中
    # ------------------------------------------------------------------
    with allure.step("步骤2 查询学科列表：GET {}".format(SUBJECTS_PATH)):
        response = subject_factory.client.get(
            SUBJECTS_PATH, expect_status=None
        )

        body = response.json()
        assert response.status_code == 200, \
            "查询学科列表应返回 200，实际 {}".format(response.status_code)

        subject_list = body.get("data") or []
        assert any(item.get("code") == subject_code for item in subject_list), \
            "学科列表中应包含刚创建的学科，实际共 {} 条".format(len(subject_list))

    # ------------------------------------------------------------------
    # 第 3 步：修改学科名称
    # ------------------------------------------------------------------
    with allure.step("步骤3 修改学科名称：PUT /api/v1/subjects/{}".format(subject_id)):
        response = subject_factory.client.put(
            "{}{}".format(SUBJECTS_PATH, subject_id),
            json_body={"name": "更新后的学科名称"},
            expect_status=None,
        )

        body = response.json()
        assert response.status_code == 200, \
            "修改学科应返回 200，实际 {}".format(response.status_code)
        assert body.get("message") == "学科更新成功", \
            "message 应为「学科更新成功」，实际 {}".format(body.get("message"))

        updated = body.get("data") or {}
        assert updated.get("name") == "更新后的学科名称", \
            "更新后名称应为「更新后的学科名称」，实际 {}".format(updated.get("name"))

    # ------------------------------------------------------------------
    # 第 4 步：删除学科并确认已删除
    # ------------------------------------------------------------------
    with allure.step("步骤4 删除学科：DELETE /api/v1/subjects/{}".format(subject_id)):
        # 第一次删除：验证删除成功
        # 注意不能先调 cleanup() —— cleanup 是「兜底清理」，
        # 它会把学科删掉，之后再删就只会拿到「学科不存在」，
        # 永远验证不到「学科已删除」这条正常路径
        response = subject_factory.client.delete(
            "{}{}".format(SUBJECTS_PATH, subject_id),
            expect_status=None,
        )

        body = response.json()
        assert response.status_code == 200, \
            "删除学科应返回 200，实际 {}".format(response.status_code)
        assert body.get("message") == "学科已删除", \
            "message 应为「学科已删除」，实际 {}".format(body.get("message"))

        # 再删一次，服务端应提示学科不存在
        response = subject_factory.client.delete(
            "{}{}".format(SUBJECTS_PATH, subject_id),
            expect_status=None,
        )

        body = response.json()
        assert body.get("message") == "学科不存在", \
            "重复删除时 message 应为「学科不存在」，实际 {}".format(body.get("message"))


# ============================================================================
# 4. 异常场景：创建学科失败、删除学科失败
# ============================================================================

@pytest.mark.crud
@allure.feature("学科管理")
@allure.story("学科接口异常")
@allure.title("SUBJ-FAIL-001 创建学科失败：缺少必填字段 code")
@allure.description(
    "必填字段缺失时服务端返回 422，\n"
    "响应体带 code=VALIDATION_ERROR 与 detail 列表，detail 里给出字段位置与原因。"
)
def test_subject_create_failed(auth_http_client):
    """用例 SUBJ-FAIL-001：创建学科失败，缺少 code。

    :param auth_http_client: 已登录的 HttpClient
    :raises AssertionError: 状态码或错误响应结构不符合预期
    """
    with allure.step("提交缺少 code 的请求体"):
        response = auth_http_client.post(
            SUBJECTS_PATH,
            json_body={"name": "缺少编码的学科"},
            expect_status=None,
        )

    body = response.json()
    assert response.status_code == 422, \
        "期望状态码 422，实际 {}".format(response.status_code)
    assert body.get("code") == "VALIDATION_ERROR", \
        "code 应为 VALIDATION_ERROR，实际 {}".format(body.get("code"))
    assert body.get("message") == "数据验证失败", \
        "message 应为「数据验证失败」，实际 {}".format(body.get("message"))

    detail = body.get("detail") or []
    assert detail, "422 响应应带 detail 明细，实际: {}".format(body)
    assert detail[0].get("type") == "missing", \
        "detail[0].type 应为 missing，实际 {}".format(detail[0].get("type"))
    assert "code" in detail[0].get("loc", []), \
        "detail[0].loc 应指出 code 字段，实际 {}".format(detail[0].get("loc"))


@pytest.mark.crud
@allure.feature("学科管理")
@allure.story("学科接口异常")
@allure.title("SUBJ-FAIL-002 删除学科失败：学科不存在")
@allure.description(
    "删除不存在的学科时服务端不返回 404，\n"
    "而是返回 200 + message=「学科不存在」，这是被测服务的实际契约。"
)
def test_subject_delete_failed(auth_http_client):
    """用例 SUBJ-FAIL-002：删除不存在的学科。

    :param auth_http_client: 已登录的 HttpClient
    :raises AssertionError: 响应不符合「学科不存在」的约定
    """
    # 使用一个肯定不存在的 id。测试库自增 id 远小于该值
    not_exist_id = 99999999

    with allure.step("删除不存在的学科 id={}".format(not_exist_id)):
        response = auth_http_client.delete(
            "{}{}".format(SUBJECTS_PATH, not_exist_id),
            expect_status=None,
        )

    body = response.json()
    assert response.status_code == 200, \
        "期望状态码 200，实际 {}".format(response.status_code)
    assert body.get("message") == "学科不存在", \
        "message 应为「学科不存在」，实际 {}".format(body.get("message"))


@pytest.mark.auth
@allure.feature("学科管理")
@allure.story("学科接口鉴权异常")
@allure.title("SUBJ-FAIL-003 删除学科失败：未携带访问令牌")
@allure.description(
    "删除接口要求 Bearer 令牌。\n"
    "不带令牌删除时，服务端返回 401，且不会真的删掉数据。"
)
def test_subject_delete_without_token(session_http_client):
    """用例 SUBJ-FAIL-003：删除学科失败，未携带令牌。

    :param session_http_client: 未登录的会话级 HttpClient
    :raises AssertionError: 状态码或错误响应结构不符合预期
    """
    with allure.step("不带令牌删除学科"):
        response = session_http_client.delete(
            "{}{}".format(SUBJECTS_PATH, 1),
            expect_status=None,
        )

    body = response.json()
    assert response.status_code == 401, \
        "期望状态码 401，实际 {}".format(response.status_code)
    assert body.get("code") == "UNAUTHORIZED", \
        "code 应为 UNAUTHORIZED，实际 {}".format(body.get("code"))
    assert body.get("message") == "请先登录", \
        "message 应为「请先登录」，实际 {}".format(body.get("message"))


if __name__ == "__main__":
    # 直接运行本文件时，以 pytest 方式执行
    pytest.main(["-v", __file__])
