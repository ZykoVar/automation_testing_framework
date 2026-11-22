# -*- coding: utf-8 -*-
"""
day10 / test_case / conftest.py

只对 test_case 目录生效的 conftest，提供测试数据工厂。

与根 conftest 的分工：
    根 conftest     —— 提供 HTTP 客户端等「怎么发请求」的基础设施
    本目录 conftest —— 提供学生数据工厂等「造什么数据」的业务设施

核心是 yield 的用法：
    创建学生放在 yield 之前，用例直接拿到创建好的学生详情；
    删除学生放在 yield 之后，无论用例是否走到结尾、是否断言失败，
    数据都会被清理，环境不残留脏数据。
"""

# 第三方库：pytest 测试框架
import pytest

# 第三方库：loguru 日志库
from loguru import logger

# 标准库：轻量命名空间，用于把多个方法打包成对象交给用例
from types import SimpleNamespace

# 标准库：路径处理与模块搜索路径
import os
import sys

# ============================================================================
# 0. 路径引导
#    与根 conftest 同样的处理：把项目根加入 sys.path，
#    保证直接用 python 执行测试文件时包式导入也能解析
# ============================================================================

# 定位项目根目录。本文件在 day10/test_case/ 下，上溯三级即为项目根
PROJECT_ROOT = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)

# 项目根不在 sys.path 中时补进去。已存在则跳过，避免重复插入
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

# 本项目的共享配置。
# 用包式导入 day10.utils 而非顶层导入 utils：
# day10 与它的子目录都有 __init__.py，属于一个包，
# 包式导入不依赖「当前工作目录恰好是 day10」这个前提
from day10.utils.config import (
    CLASS_ID,
    GENDER_FEMALE,
    GENDER_MALE,
    STATUS_ENROLLED,
    STATUS_SUSPENDED,
    SUBJECTS_PATH,
    generate_student_no,
    generate_subject_no,
)


# ============================================================================
# 1. 学生数据工厂
# ============================================================================

@pytest.fixture()
def student_factory(auth_http_client):
    """学生数据工厂夹具。

    提供四个成员：
        create(**overrides) —— 新建学生，返回学生详情字典
        update(student_id, **fields) —— 修改学生，返回修改后的详情
        cleanup()           —— 清理本工厂创建的全部学生
        client              —— 工厂内部使用的已登录 HttpClient

    典型用法：

        def test_xxx(student_factory):
            student = student_factory.create(name="张三")
            student_factory.update(student["id"], name="李四")
            ...
            student_factory.cleanup()

    用例若不显式调用 cleanup()，夹具的 yield 之后会兜底清理，
    保证即使断言失败也不会在库里留下脏数据。

    :param auth_http_client: 已登录的 HttpClient
    :yield: 包含 create、update、cleanup 三个方法的工厂对象
    """
    # 记录本工厂创建的学生 id，清理时按 id 逐个删除
    created_ids = []

    def create(**overrides):
        """新建一名学生。

        默认值取自业务常量，调用方只需覆盖关心的字段。
        student_no 默认用时间戳生成，保证唯一。

        :param overrides: 覆盖的字段，如 student_no、name、class_id、gender、status
        :return: 新建学生的详情字典
        """
        # 构造请求体。未覆盖的字段走接口默认值
        payload = {
            "student_no": generate_student_no(),
            "name": "自动化测试学生",
            "class_id": CLASS_ID,
            "gender": GENDER_MALE,
            "status": STATUS_ENROLLED,
        }
        # 用调用方传入的值覆盖默认值
        payload.update(overrides)

        # 发起新增请求。新增成功应返回 201
        response = auth_http_client.post(
            "/api/v1/students/",
            json_body=payload,
            expect_status=201,
        )
        # 取出学生详情
        student = response.json().get("data") or {}
        # 记录 id，供清理使用
        if student.get("id") is not None:
            created_ids.append(student["id"])
        # 返回详情供用例断言
        return student

    def update(student_id, **fields):
        """修改一名学生。

        :param student_id: 学生 id
        :param fields: 要修改的字段，如 name、gender、status、class_id
        :return: 修改后的学生详情字典
        """
        # 发起修改请求
        response = auth_http_client.put(
            "/api/v1/students/{}".format(student_id),
            json_body=fields,
            expect_status=200,
        )
        # 返回修改后的详情
        return response.json().get("data") or {}

    def cleanup():
        """清理本工厂创建的全部学生。

        逐个按 id 删除，失败的记录打日志但不中断，
        保证一次清理不会因为个别数据异常而卡住。
        """
        # 倒序清理，先建的后删，避免依赖关系导致删不掉
        for student_id in reversed(created_ids):
            try:
                auth_http_client.delete(
                    "/api/v1/students/{}".format(student_id),
                    expect_status=200,
                )
                logger.info("已清理临时学生 id={}", student_id)
            except Exception as error:
                # 清理失败只记日志，不影响用例结论
                logger.warning("清理临时学生 id={} 失败: {}", student_id, error)
        # 清空记录，避免重复清理
        created_ids.clear()

    # 把四个成员打包成一个对象交给用例。
    # client 一并暴露，用例需要发查询类请求时直接复用，不必再依赖根夹具
    factory = SimpleNamespace(
        create=create, update=update, cleanup=cleanup, client=auth_http_client
    )

    # 交出工厂对象
    yield factory

    # yield 之后是清理阶段。无论用例是否走到结尾都会执行，
    # 保证环境不残留脏数据
    cleanup()


# ============================================================================
# 2. 学科数据工厂
# ============================================================================

@pytest.fixture()
def subject_factory(auth_http_client):
    """学科数据工厂夹具。

    提供三个成员：
        create(**overrides) —— 新建学科，返回学科详情字典
        cleanup()           —— 清理本工厂创建的全部学科
        client              —— 工厂内部使用的已登录 HttpClient

    :param auth_http_client: 已登录的 HttpClient
    :yield: 包含 create、cleanup、client 三个成员的工厂对象
    """
    # 记录本工厂创建的学科 id，清理时按 id 逐个删除
    created_ids = []

    def create(**overrides):
        """新建一个学科。

        :param overrides: 覆盖的字段，如 code、name、full_score、pass_score
        :return: 新建学科的详情字典
        """
        # 构造请求体。code 用时间戳生成，保证唯一
        payload = {
            "code": generate_subject_no(),
            "name": "自动化测试学科",
            "full_score": 150,
            "pass_score": 90,
            "sort_order": 50,
        }
        # 用调用方传入的值覆盖默认值
        payload.update(overrides)

        # 发起新增请求。新增成功应返回 201
        response = auth_http_client.post(
            SUBJECTS_PATH,
            json_body=payload,
            expect_status=201,
        )
        # 取出学科详情
        subject = response.json().get("data") or {}
        # 记录 id，供清理使用
        if subject.get("id") is not None:
            created_ids.append(subject["id"])
        # 返回详情供用例断言
        return subject

    def cleanup():
        """清理本工厂创建的全部学科。"""
        # 倒序清理，先建的后删
        for subject_id in reversed(created_ids):
            try:
                auth_http_client.delete(
                    "{}{}".format(SUBJECTS_PATH, subject_id),
                    expect_status=200,
                )
                logger.info("已清理临时学科 id={}", subject_id)
            except Exception as error:
                # 清理失败只记日志，不影响用例结论
                logger.warning("清理临时学科 id={} 失败: {}", subject_id, error)
        # 清空记录，避免重复清理
        created_ids.clear()

    # 把三个成员打包成一个对象交给用例。
    # client 一并暴露，用例需要发查询类请求时直接复用，不必再依赖根夹具
    factory = SimpleNamespace(
        create=create, cleanup=cleanup, client=auth_http_client
    )

    # 交出工厂对象
    yield factory

    # yield 之后是清理阶段，保证环境不残留脏数据
    cleanup()
