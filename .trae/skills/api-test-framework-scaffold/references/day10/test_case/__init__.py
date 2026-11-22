# -*- coding: utf-8 -*-
"""
day10 / test_case / __init__.py

测试脚本层。

目录内的文件分工：
    conftest.py           数据工厂夹具（学生、学科）
    test_login.py         登录接口，YAML 数据驱动
    test_login_demo.py    传统断言与 AI 自然语言断言的对照演示
    test_demo_fail.py     故意失败的用例，用于演示 AI 自动排错
    test_student_flow.py  学生业务流程，Allure 装饰器 + step
    test_subject_flow.py  学科业务流程与 Excel 数据驱动
"""
