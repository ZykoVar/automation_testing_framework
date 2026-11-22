# -*- coding: utf-8 -*-
"""
HAT / ai 包

AI 辅助能力（移植自 day12 框架）：

    ai_prompts        —— 全部提示词与报告模板，纯标准库
    ai_debug_helper   —— 大模型唯一调用点 call_llm + 本地规则引擎降级
    ai_assert         —— 自然语言断言（strict / 非 strict 双模式）
    ai_debug_plugin   —— pytest 钩子，用例失败时自动生成诊断报告

依赖方向：
    ai_prompts  ←  ai_debug_helper  ←  ai_assert
    ai_debug_plugin 只依赖 ai_debug_helper 与 GlobalContext

大模型调用只在 ai_debug_helper.call_llm 一处实现。
未配置 LLM_API_KEY 时整套能力降级为本地规则引擎，不影响用例执行。
"""
