# -*- coding: utf-8 -*-
"""
day10 / test_case / test_student_flow.py

学生管理业务流程测试，用 Allure 装饰器 + step 组织报告层级。

被测接口：
    POST   /api/v1/students/            新增学生
    GET    /api/v1/students/{id}        学生详情
    GET    /api/v1/students/?search=xxx 学生列表（按学号搜索）
    PUT    /api/v1/students/{id}        更新学生
    DELETE /api/v1/students/{id}        删除学生

用例分布：
    1. test_student_full_flow               —— 完整链路：创建 → 查询 → 更新 → 删除
    2. test_student_create_failed           —— 创建学生失败：必填字段缺失
    3. test_student_create_duplicated_no    —— 创建学生失败：学号重复
    4. test_student_query_without_token     —— 查询学生失败：未携带令牌
    5. test_student_delete_without_token    —— 删除学生失败：未携带令牌
    6. test_student_not_exist               —— 学生不存在：查询与删除的兜底行为

Allure 的使用要点：
    @allure.feature  —— 一级目录，对应「学生管理」这个模块
    @allure.story    —— 二级目录，对应一条业务链路
    @allure.title    —— 用例标题，报告列表里显示的就是它
    @allure.step     —— 用例内的步骤，在报告里展开成可折叠的树
    step 装饰的是函数，用 with step("..."): 包住代码块，
    块内抛出的异常会连带整个 step 标记为失败，报告里一眼能看出断在哪一步。

实测结论（断言以此为准）：
    201 新增成功，message=学生创建成功，data 为学生详情
    422 必填字段缺失，code=VALIDATION_ERROR，message=数据验证失败
    201 学号重复，message=「学号 xxx 已存在」，data 为 null
    200 学生详情，message=获取学生详情成功
    200 学生不存在，message=学生不存在，data 为 null
    200 删除成功，message=学生已删除
    401 未携带令牌，code=UNAUTHORIZED，message=请先登录

运行方式：
    cd d:/AI_API_AUTO2.0/day10
    python -m pytest test_case/test_student_flow.py -v
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

# 共享配置。接口路径与业务常量统一从配置层取
try:
    from utils.config import (
        CLASS_ID,
        GENDER_MALE,
        STATUS_ENROLLED,
        STUDENT_DETAIL_PATH,
        STUDENTS_PATH,
        generate_student_no,
    )
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    from day10.utils.config import (
        CLASS_ID,
        GENDER_MALE,
        STATUS_ENROLLED,
        STUDENT_DETAIL_PATH,
        STUDENTS_PATH,
        generate_student_no,
    )


# ============================================================================
# 1. 完整链路：创建 → 查询 → 更新 → 删除
# ============================================================================

@pytest.mark.crud
@pytest.mark.smoke
@allure.feature("学生管理")
@allure.story("学生全生命周期")
@allure.title("STU-FLOW-001 创建学生后查询、更新、删除，数据闭环无残留")
@allure.description(
    "一条用例走完学生的完整生命周期，每一步都用 step 在报告里标出来。\n\n"
    "覆盖接口：\n"
    "    POST   /api/v1/students/\n"
    "    GET    /api/v1/students/{id}\n"
    "    GET    /api/v1/students/?search=学号\n"
    "    PUT    /api/v1/students/{id}\n"
    "    DELETE /api/v1/students/{id}\n\n"
    "清理由 student_factory 夹具兜底，即使断言失败也会删除临时数据。"
)
def test_student_full_flow(student_factory):
    """用例 STU-FLOW-001：学生全生命周期。

    :param student_factory: 学生数据工厂夹具
    :raises AssertionError: 任一环节的响应不符合预期
    """
    # 生成唯一学号。第二次执行不会撞「学号已存在」
    student_no = generate_student_no()

    # ------------------------------------------------------------------
    # 第 1 步：创建学生
    # ------------------------------------------------------------------
    with allure.step("步骤1 创建学生：学号 {}".format(student_no)):
        student = student_factory.create(
            student_no=student_no,
            name="全流程测试学生",
            class_id=CLASS_ID,
            gender=GENDER_MALE,
            status=STATUS_ENROLLED,
        )

        # 断言学生详情已返回，且携带 id 与学号
        assert student.get("id") is not None, \
            "创建学生应返回学生 id，实际: {}".format(student)
        assert student.get("student_no") == student_no, \
            "学号应回显为 {}，实际 {}".format(student_no, student.get("student_no"))
        assert student.get("class_name"), \
            "学生详情应包含班级名称，实际: {}".format(student.get("class_name"))

        student_id = student["id"]
        print("创建成功，学生 id={} 学号={}".format(student_id, student_no))

    # ------------------------------------------------------------------
    # 第 2 步：按 id 查询学生详情
    # ------------------------------------------------------------------
    with allure.step("步骤2 查询学生详情：GET {}".format(
            STUDENT_DETAIL_PATH.format(student_id=student_id))):
        response = student_factory_get(student_factory, student_id)

        body = response.json()
        assert body.get("message") == "获取学生详情成功", \
            "message 应为「获取学生详情成功」，实际 {}".format(body.get("message"))

        detail = body.get("data") or {}
        assert detail.get("id") == student_id, \
            "查询到的学生 id 应为 {}".format(student_id)
        assert detail.get("student_no") == student_no, \
            "查询到的学号应为 {}".format(student_no)
        assert detail.get("name") == "全流程测试学生", \
            "查询到的姓名应为「全流程测试学生」，实际 {}".format(detail.get("name"))

    # ------------------------------------------------------------------
    # 第 3 步：按学号搜索学生列表
    # ------------------------------------------------------------------
    with allure.step("步骤3 按学号搜索学生列表：GET {}?search={}".format(
            STUDENTS_PATH, student_no)):
        response = student_factory_get(student_factory, student_id,
                                       search=student_no)

        body = response.json()
        matched = body.get("data") or []
        assert any(item.get("student_no") == student_no for item in matched), \
            "按学号搜索应能查到该学生，实际查到: {}".format(matched)

    # ------------------------------------------------------------------
    # 第 4 步：更新学生姓名
    # ------------------------------------------------------------------
    with allure.step("步骤4 更新学生姓名：PUT {}".format(
            STUDENT_DETAIL_PATH.format(student_id=student_id))):
        updated = student_factory.update(student_id, name="更新后的学生姓名")

        assert updated.get("name") == "更新后的学生姓名", \
            "更新后姓名应为「更新后的学生姓名」，实际 {}".format(updated.get("name"))

    # ------------------------------------------------------------------
    # 第 5 步：删除学生并确认已删除
    # ------------------------------------------------------------------
    with allure.step("步骤5 删除学生：DELETE {}".format(
            STUDENT_DETAIL_PATH.format(student_id=student_id))):
        # 第一次删除：验证删除成功
        # 不能先调 cleanup() —— cleanup 是「兜底清理」，
        # 它会把学生删掉，之后再删就只会拿到「学生不存在」，
        # 永远验证不到「学生已删除」这条正常路径
        response = student_factory.client.delete(
            STUDENT_DETAIL_PATH.format(student_id=student_id),
            expect_status=None,
        )

        body = response.json()
        assert response.status_code == 200, \
            "删除学生应返回 200，实际 {}".format(response.status_code)
        assert body.get("message") == "学生已删除", \
            "message 应为「学生已删除」，实际 {}".format(body.get("message"))

        # 再查一次，服务端应提示学生不存在
        response = student_factory_get(student_factory, student_id)
        body = response.json()
        assert body.get("message") == "学生不存在", \
            "删除后查询应提示「学生不存在」，实际 {}".format(body.get("message"))
        assert body.get("data") is None, \
            "删除后查询 data 应为 null，实际 {}".format(body.get("data"))


# ============================================================================
# 2. 异常场景：创建学生失败
# ============================================================================

@pytest.mark.crud
@allure.feature("学生管理")
@allure.story("学生新增异常")
@allure.title("STU-FAIL-001 创建学生失败：缺少必填字段 student_no")
@allure.description(
    "必填字段缺失时服务端返回 422，\n"
    "响应体带 code=VALIDATION_ERROR 与 detail 列表，detail 里给出字段位置与原因。"
)
def test_student_create_failed(auth_http_client):
    """用例 STU-FAIL-001：创建学生失败，缺少 student_no。

    :param auth_http_client: 已登录的 HttpClient
    :raises AssertionError: 状态码或错误响应结构不符合预期
    """
    with allure.step("提交缺少 student_no 的请求体"):
        response = auth_http_client.post(
            STUDENTS_PATH,
            json_body={"name": "缺少学号的学生", "class_id": CLASS_ID},
            expect_status=None,
        )

    body = response.json()
    assert response.status_code == 422, \
        "期望状态码 422，实际 {}".format(response.status_code)
    assert body.get("code") == "VALIDATION_ERROR", \
        "code 应为 VALIDATION_ERROR，实际 {}".format(body.get("code"))
    assert body.get("message") == "数据验证失败", \
        "message 应为「数据验证失败」，实际 {}".format(body.get("message"))

    # detail 是列表，第一项给出出错的字段位置
    detail = body.get("detail") or []
    assert detail, "422 响应应带 detail 明细，实际: {}".format(body)
    assert detail[0].get("type") == "missing", \
        "detail[0].type 应为 missing，实际 {}".format(detail[0].get("type"))
    assert "student_no" in detail[0].get("loc", []), \
        "detail[0].loc 应指出 student_no 字段，实际 {}".format(detail[0].get("loc"))


@pytest.mark.crud
@allure.feature("学生管理")
@allure.story("学生新增异常")
@allure.title("STU-FAIL-002 创建学生失败：学号已存在")
@allure.description(
    "学号在库中唯一。重复提交时服务端返回 201，\n"
    "但 message 提示「学号 xxx 已存在」且 data 为 null —— "
    "这是被测服务的实际契约，断言按实测结果写。"
)
def test_student_create_duplicated_no(student_factory):
    """用例 STU-FAIL-002：创建学生失败，学号重复。

    :param student_factory: 学生数据工厂夹具
    :raises AssertionError: 重复学号的响应不符合预期
    """
    # 先建一个学生占住这个学号
    student_no = generate_student_no()
    student_factory.create(student_no=student_no, name="占位学生")

    with allure.step("用相同的学号再次创建学生"):
        response = student_factory.client.post(
            STUDENTS_PATH,
            json_body={
                "student_no": student_no,
                "name": "重复学号学生",
                "class_id": CLASS_ID,
            },
            expect_status=None,
        )

    body = response.json()
    assert "已存在" in str(body.get("message")), \
        "message 应提示学号已存在，实际 {}".format(body.get("message"))
    assert body.get("data") is None, \
        "学号重复时 data 应为 null，实际 {}".format(body.get("data"))


# ============================================================================
# 3. 异常场景：查询学生失败、删除学生失败
# ============================================================================

@pytest.mark.auth
@allure.feature("学生管理")
@allure.story("学生接口鉴权异常")
@allure.title("STU-FAIL-003 查询学生失败：未携带访问令牌")
@allure.description(
    "除健康检查与登录外，其余接口都要求 Bearer 令牌。\n"
    "不带令牌查询学生详情时，服务端返回 401。"
)
def test_student_query_without_token(session_http_client):
    """用例 STU-FAIL-003：查询学生失败，未携带令牌。

    :param session_http_client: 未登录的会话级 HttpClient
    :raises AssertionError: 状态码或错误响应结构不符合预期
    """
    with allure.step("不带令牌查询学生详情"):
        response = session_http_client.get(
            STUDENT_DETAIL_PATH.format(student_id=1),
            expect_status=None,
        )

    body = response.json()
    assert response.status_code == 401, \
        "期望状态码 401，实际 {}".format(response.status_code)
    assert body.get("code") == "UNAUTHORIZED", \
        "code 应为 UNAUTHORIZED，实际 {}".format(body.get("code"))
    assert body.get("message") == "请先登录", \
        "message 应为「请先登录」，实际 {}".format(body.get("message"))


@pytest.mark.auth
@allure.feature("学生管理")
@allure.story("学生接口鉴权异常")
@allure.title("STU-FAIL-004 删除学生失败：未携带访问令牌")
@allure.description(
    "删除接口同样要求 Bearer 令牌。\n"
    "不带令牌删除时，服务端返回 401，且不会真的删掉数据。"
)
def test_student_delete_without_token(session_http_client):
    """用例 STU-FAIL-004：删除学生失败，未携带令牌。

    :param session_http_client: 未登录的会话级 HttpClient
    :raises AssertionError: 状态码或错误响应结构不符合预期
    """
    with allure.step("不带令牌删除学生"):
        response = session_http_client.delete(
            STUDENT_DETAIL_PATH.format(student_id=1),
            expect_status=None,
        )

    body = response.json()
    assert response.status_code == 401, \
        "期望状态码 401，实际 {}".format(response.status_code)
    assert body.get("code") == "UNAUTHORIZED", \
        "code 应为 UNAUTHORIZED，实际 {}".format(body.get("code"))
    assert body.get("message") == "请先登录", \
        "message 应为「请先登录」，实际 {}".format(body.get("message"))


# ============================================================================
# 4. 异常场景：学生不存在
# ============================================================================

@pytest.mark.crud
@allure.feature("学生管理")
@allure.story("学生不存在")
@allure.title("STU-NOTFOUND-001 查询不存在的学生返回「学生不存在」且 data 为 null")
@allure.description(
    "被测服务的学生详情接口在学生不存在时不返回 404，\n"
    "而是返回 200 + message=「学生不存在」+ data=null。\n"
    "用例按实测契约断言，避免把业务兜底误判成接口缺陷。"
)
def test_student_not_exist(auth_http_client):
    """用例 STU-NOTFOUND-001：查询不存在的学生。

    :param auth_http_client: 已登录的 HttpClient
    :raises AssertionError: 响应不符合「学生不存在」的约定
    """
    # 使用一个肯定不存在的 id。测试库自增 id 远小于该值
    not_exist_id = 99999999

    with allure.step("查询不存在的学生 id={}".format(not_exist_id)):
        response = auth_http_client.get(
            STUDENT_DETAIL_PATH.format(student_id=not_exist_id),
            expect_status=None,
        )

    body = response.json()
    assert response.status_code == 200, \
        "期望状态码 200，实际 {}".format(response.status_code)
    assert body.get("message") == "学生不存在", \
        "message 应为「学生不存在」，实际 {}".format(body.get("message"))
    assert body.get("data") is None, \
        "学生不存在时 data 应为 null，实际 {}".format(body.get("data"))

    with allure.step("删除同一个不存在的学生"):
        response = auth_http_client.delete(
            STUDENT_DETAIL_PATH.format(student_id=not_exist_id),
            expect_status=None,
        )

    body = response.json()
    assert body.get("message") == "学生不存在", \
        "删除不存在的学生时 message 应为「学生不存在」，实际 {}".format(
            body.get("message"))


# ============================================================================
# 5. 内部辅助
#    数据工厂除 create/update/cleanup 外还暴露了 client，
#    查询类请求直接用这个客户端发，保持用例的数据来源单一。
# ============================================================================

def student_factory_get(factory, student_id, search=None):
    """查询学生详情或按学号搜索。

    :param factory: student_factory 夹具对象
    :param student_id: 学生 id
    :param search: 搜索关键字，传 None 表示按 id 查详情
    :return: requests.Response 对象
    """
    # 传了搜索关键字就查列表，否则查详情
    if search:
        return factory.client.get(
            STUDENTS_PATH,
            params={"search": search},
            expect_status=None,
        )

    return factory.client.get(
        STUDENT_DETAIL_PATH.format(student_id=student_id),
        expect_status=None,
    )


if __name__ == "__main__":
    # 直接运行本文件时，以 pytest 方式执行
    pytest.main(["-v", __file__])
