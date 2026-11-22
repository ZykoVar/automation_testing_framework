# -*- coding: utf-8 -*-
"""
day10 / __init__.py

把 day10 目录声明为一个 Python 包。

作用：
    1. pytest 以「prepend」模式收集时，会向上回溯到第一个不含 __init__.py 的目录。
       day10 与 day10/test_case 都带 __init__.py 时，
       回溯停在项目根，「from day10.utils import ...」这类包式导入才成立；
    2. 目录被打包成 wheel / sdist 时，本文件是包的入口标记。

包内的模块分层：
    utils/      工具层，HTTP 客户端、配置、用例加载、AI 辅助
    test_case/  测试脚本层，用例只写业务，不写基础设施
    conftest.py 根 conftest，提供 session 级 fixture 与 AI 排错钩子
"""
