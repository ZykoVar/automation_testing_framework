# -*- coding: utf-8 -*-
"""
day10 / utils / __init__.py

企业级接口自动化测试框架的工具层。

模块清单与依赖方向：

    AI_HttpClient.py       HTTP 客户端。零依赖，可独立运行
        无

    config.py               共享配置与业务常量
        无

    yaml_loader.py          YAML 用例加载器，含 ApiCase 数据类
        无

    excel_loader.py         Excel 用例加载器
        -> yaml_loader（复用 ApiCase 数据类）

    yaml_excel_generator.py YAML 反向生成 Excel
        -> yaml_loader（复用解析逻辑）

    ai_prompts.py           提示词与公共片段，纯标准库
        无

    ai_debug_helper.py      排错助手，含 call_llm 与 ai_debug
        -> ai_prompts

    ai_assert.py            自然语言断言，含 ai_assert
        -> ai_debug_helper

依赖方向严格单向，不可逆：
    ai_prompts  <-  ai_debug_helper  <-  ai_assert

    大模型调用只实现一次，在 ai_debug_helper.call_llm。
    其余模块通过它访问模型，不直接发起网络请求。

用法示例：

    from utils.ai_assert import ai_assert
    from utils.ai_debug_helper import ai_debug
    from utils.AI_HttpClient import HttpClient

    # 自然语言断言
    ai_assert(response, "状态码等于 200", strict=False)

    # 手动触发一次诊断
    report = ai_debug(exception, request_info, response_text, code_snippet)
"""

# 包标识。用于日志与报告中标记工具来源
__version__ = "1.0.0"

# 工具名称。会出现在诊断报告的标题里
__tool_name__ = "day10 企业级接口自动化测试框架"
