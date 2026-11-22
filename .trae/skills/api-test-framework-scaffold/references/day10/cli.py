# -*- coding: utf-8 -*-
# @Author: QX
# @File: cli.py
"""
day10 / cli.py

一键执行 day10 的测试用例并生成 Allure 报告。

产物统一输出到 day10/report 目录：
    day10/report/allure-results —— allure 原始结果数据（JSON）
    day10/report/allure-report  —— allure 生成的 HTML 报告

路径基于本文件位置计算，因此无论从哪个工作目录执行，
产物都落在 day10/report 下，不会散落到项目根目录。

用法：
    python day10/cli.py
    python day10/cli.py -m smoke        # 追加参数会透传给 pytest
    python day10/cli.py -k "登录"        # 按用例名过滤
    python day10/cli.py -m "not demo_fail"  # 排除故意失败的演示用例
"""
import os
import sys

import pytest


# ============================================================================
# 1. 路径准备
# ============================================================================

# day10 目录。本文件在 day10/ 下，上溯一级即为 day10
DAY10_DIR = os.path.dirname(os.path.abspath(__file__))

# 报告输出根目录。所有 Allure 产物都放在这里
REPORT_DIR = os.path.join(DAY10_DIR, "report")

# allure 原始结果目录。pytest 执行时把结果写到这里
ALLURE_RESULTS_DIR = os.path.join(REPORT_DIR, "allure-results")

# allure HTML 报告目录。allure generate 时把报告输出到这里
ALLURE_REPORT_DIR = os.path.join(REPORT_DIR, "allure-report")

# AI 排错报告目录。用例失败时自动生成诊断报告
AI_DEBUG_REPORT_DIR = os.path.join(DAY10_DIR, "ai_debug_reports")

# 被测用例目录
TEST_CASE_DIR = os.path.join(DAY10_DIR, "test_case")

# 确保报告目录存在。不存在时 allure 会直接报错退出
os.makedirs(ALLURE_RESULTS_DIR, exist_ok=True)

# 确保 AI 排错报告目录存在
os.makedirs(AI_DEBUG_REPORT_DIR, exist_ok=True)


# ============================================================================
# 2. 参数说明
# ============================================================================
'''
"-v"：显示更详细的信息，提高输出的 verbosity（详细程度）。
"-s"：关闭输出捕获，测试中的 print 与日志实时显示在控制台。
"--capture=sys"：只捕获 sys.stdout / sys.stderr，第三方库的输出不被拦截。
"--clean-alluredir"：执行前清空 allure-results 目录，避免残留旧结果混入本次报告。
"--alluredir=<目录>"：指定 allure 原始结果的输出目录。
"-n=3"：xdist 并发执行，3 个 worker。默认注释掉，需要时打开。
'''

# pytest 参数。末尾追加命令行传入的额外参数
pytest_args = [
    '-v',
    '-s',
    '--capture=sys',
    '--clean-alluredir',
    '--alluredir={}'.format(ALLURE_RESULTS_DIR),
    TEST_CASE_DIR,
    # r'D:\AI_API_AUTO2.0\day10\test_case\test_login.py'

    # '-n=3'
]


# ============================================================================
# 3. 执行测试并生成报告
# ============================================================================

# 执行 pytest。extra_args 为用户在命令行追加的参数
extra_args = sys.argv[1:]

# 运行测试用例，结果写入 allure-results
pytest.main(pytest_args + extra_args)

# 生成 HTML 报告到 allure-report。
# -c 表示先清空输出目录，避免旧报告残留
os.system('allure generate -c -o "{}" "{}"'.format(ALLURE_REPORT_DIR, ALLURE_RESULTS_DIR))

# 提示报告位置，方便直接打开
print("Allure 报告已生成: {}".format(ALLURE_REPORT_DIR))

# 如果没有报告加下面的语句
# from allure_combine import combine_allure
#  combine_allure(测试报告的路径)
# combine_allure("./allure-report")
