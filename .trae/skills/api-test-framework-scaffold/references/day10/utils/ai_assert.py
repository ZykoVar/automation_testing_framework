# -*- coding: utf-8 -*-
"""
day10 / utils / ai_assert.py

自然语言断言：用中文描述规则，交给大模型判断响应是否满足。

典型用法：
    from utils.ai_assert import ai_assert

    # 不满足也不抛异常，只打印结论
    ai_assert(response, "状态码等于 200", strict=False)

    # 不满足时抛 AssertionError，让 pytest 判定用例失败
    ai_assert(response, "响应体包含 access_token 字段且值非空", strict=True)

两种模式：
    有 API Key  —— 把规则与响应一起发给大模型，由模型判断
    无 API Key  —— 降级为本地正则规则判断，覆盖常见断言表述

依赖方向：ai_prompts ← ai_debug_helper ← ai_assert
本模块不直接调用大模型，只通过 ai_debug_helper.call_llm，
保证整个项目里大模型调用只有一处实现。
"""

# 标准库：正则、文本处理
import json
import re

# 通信层复用 ai_debug_helper，本模块不直接发起网络请求
try:
    from utils.ai_debug_helper import (
        CONFIG,
        call_llm,
        has_api_key,
        render_assert_prompt,
    )
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    import sys as _sys
    import os as _os
    _day10_dir = _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))
    if _day10_dir not in _sys.path:
        _sys.path.insert(0, _day10_dir)
    from utils.ai_debug_helper import (
        CONFIG,
        call_llm,
        has_api_key,
        render_assert_prompt,
    )


# ============================================================================
# 1. 降级用的本地规则
# ============================================================================

# 本地正则规则。key 为规则关键词，value 为 (匹配函数, 说明)。
# 每条规则处理一类常见的中文断言表述。
LOCAL_RULES = [
    # 状态码相关
    (r"状态码\s*(?:等于|是|为|=)\s*(\d{3})",
     "status_code", "状态码等于 {0}"),
    (r"返回\s*(\d{3})\s*(?:状态码|的)?",
     "status_code", "状态码等于 {0}"),
    # 字段存在性
    (r"(?:包含|含有|存在|有)\s*[「\"']?([A-Za-z_][A-Za-z0-9_]*)\s*[」\"']?\s*(?:字段|键|key|field)",
     "contains_key", "响应体包含 {0}"),
    (r"字段\s*[「\"']?([A-Za-z_][A-Za-z0-9_]*)\s*[」\"']?\s*(?:存在|存在且非空|非空)",
     "contains_key_nonempty", "响应体包含非空字段 {0}"),
    # 字段值相等。值可以带引号也可以不带，引号只是书写习惯不是硬要求
    (r"[「\"']?([A-Za-z_][A-Za-z0-9_]*)\s*[」\"']?\s*(?:的)?\s*(?:值)?\s*(?:等于|是|为)\s*[「\"']?([^\s」\"',，。]+)[」\"']?",
     "field_equals", "字段 {0} 的值等于 {1}"),
    # 包含字符串。同样允许不带引号
    (r"(?:包含|含有)\s*(?:字符串)?\s*[「\"']?([^\s」\"',，。]+)[」\"']?",
     "contains_text", "响应体包含 {0}"),
    # 空与非空
    (r"(?:响应体|返回值)\s*(?:为空|是空)",
     "is_empty", "响应体为空"),
    (r"(?:响应体|返回值)\s*(?:非空|不为空)",
     "not_empty", "响应体非空"),
]


# ============================================================================
# 2. 响应内容提取
# ============================================================================

def extract_payload(response):
    """把响应对象转成用于判断的文本。

    优先取 JSON 后的原文；取不到就用 response.text；
    都没有就退回 repr。

    :param response: requests.Response 对象、字典或已经是字符串
    :return: 响应文本
    """
    # 传进来就是字符串时直接用
    if isinstance(response, str):
        return response
    # 不是响应对象时用 str 兜底
    if response is None:
        return ""

    # 字典形式。优先用 text 键，其次把整个字典转成 JSON
    if isinstance(response, dict):
        if response.get("text"):
            return str(response.get("text"))
        try:
            return json.dumps(response, ensure_ascii=False, indent=2)
        except (TypeError, ValueError):
            return str(response)

    if not hasattr(response, "text"):
        return str(response)

    # 优先用 json() 得到的格式化文本，字段名更清晰
    try:
        data = response.json()
        if isinstance(data, (dict, list)):
            return json.dumps(data, ensure_ascii=False, indent=2)
    except Exception:
        # 不是合法 JSON 就走 text
        pass
    return response.text or ""


def get_status_code(response):
    """从响应对象中取出状态码。

    兼容两种传入形式：
        - requests.Response 对象，取 .status_code；
        - 字典（如 {"status_code": 200, "text": "..."}），取对应键。

    :param response: requests.Response 对象或字典
    :return: 状态码整数，取不到时返回 None
    """
    # 字典形式
    if isinstance(response, dict):
        value = response.get("status_code")
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    # 响应对象形式
    if hasattr(response, "status_code"):
        try:
            return int(response.status_code)
        except (TypeError, ValueError):
            return None

    return None


def find_field_value(data, key):
    """在响应数据中查找某个字段的值，支持嵌套结构。

    先在顶层找，顶层没有再递归到嵌套的字典与列表里找。
    登录接口的 user.role 这类字段就属于这种情况。

    :param data: 解析后的 JSON 数据
    :param key: 字段名
    :return: 找到时返回 (True, 值)，找不到返回 (False, None)
    """
    # 顶层直接命中
    if isinstance(data, dict) and key in data:
        return True, data.get(key)
    if isinstance(data, list):
        # 列表里逐个元素找
        for item in data:
            found, value = find_field_value(item, key)
            if found:
                return True, value
        return False, None

    # 顶层没有，递归到嵌套字典
    if isinstance(data, dict):
        for value in data.values():
            found, found_value = find_field_value(value, key)
            if found:
                return True, found_value

    return False, None


def get_json(response):
    """从响应对象中取出 JSON 数据。

    :param response: requests.Response 对象或字典
    :return: 解析后的字典或列表；解析失败时返回 None
    """
    # 字典形式。优先用 json 键，其次把 text 键当 JSON 解析
    if isinstance(response, dict):
        if isinstance(response.get("json"), (dict, list)):
            return response.get("json")
        text = response.get("text")
        if text:
            try:
                data = json.loads(text)
                if isinstance(data, (dict, list)):
                    return data
            except (ValueError, TypeError):
                return None
        return None

    if hasattr(response, "json"):
        try:
            data = response.json()
            if isinstance(data, (dict, list)):
                return data
        except Exception:
            return None
    return None


# ============================================================================
# 3. 本地正则降级判断
# ============================================================================

def judge_by_local_rules(rule, response):
    """没有大模型时，用正则规则判断响应是否满足中文规则。

    :param rule: 中文描述的断言规则
    :param response: requests.Response 对象或响应文本
    :return: (是否满足, 判断依据说明)
    """
    text = rule or ""
    payload = extract_payload(response)
    status_code = get_status_code(response)
    data = get_json(response)

    # 逐条尝试匹配规则中出现的表述
    for pattern, kind, template in LOCAL_RULES:
        matched = re.search(pattern, text, re.IGNORECASE)
        if not matched:
            continue

        # 状态码类
        if kind == "status_code":
            expect = int(matched.group(1))
            if status_code is None:
                return False, "无法取得响应状态码，无法判断「状态码等于 {}」".format(expect)
            if status_code == expect:
                return True, "本地规则：实际状态码 {} 等于期望 {}".format(status_code, expect)
            return False, "本地规则：实际状态码 {} 不等于期望 {}".format(status_code, expect)

        # 响应体包含某个字段
        if kind in ("contains_key", "contains_key_nonempty"):
            key = matched.group(1)
            if data is None:
                return False, "本地规则：响应体不是合法 JSON，无法确认字段 {}".format(key)
            found, value = find_field_value(data, key)
            if not found:
                return False, "本地规则：响应体中不存在字段 {}".format(key)
            if kind == "contains_key_nonempty":
                if value in (None, "", [], {}):
                    return False, "本地规则：字段 {} 存在但值为空".format(key)
                return True, "本地规则：字段 {} 存在且非空".format(key)
            return True, "本地规则：响应体中存在字段 {}".format(key)

        # 字段值相等
        if kind == "field_equals":
            key, expect = matched.group(1), matched.group(2)
            if data is None:
                return False, "本地规则：响应体不是合法 JSON，无法确认字段 {}".format(key)
            found, actual = find_field_value(data, key)
            if not found:
                return False, "本地规则：响应体中不存在字段 {}".format(key)
            if str(actual) == str(expect):
                return True, "本地规则：字段 {} 的值为 {}".format(key, expect)
            return False, "本地规则：字段 {} 的实际值为 {}，期望 {}".format(
                key, actual, expect)

        # 包含某段文本
        if kind == "contains_text":
            expect = matched.group(1)
            if expect in payload:
                return True, "本地规则：响应体中包含 {}".format(expect)
            return False, "本地规则：响应体中不包含 {}".format(expect)

        # 空与非空
        if kind == "is_empty":
            if not payload.strip():
                return True, "本地规则：响应体为空"
            return False, "本地规则：响应体非空，内容长度 {}".format(len(payload))

        if kind == "not_empty":
            if payload.strip():
                return True, "本地规则：响应体非空"
            return False, "本地规则：响应体为空"

    # 一条规则都没匹配上。无法判断时保守处理为不满足，
    # 并说明原因，避免把没验证的东西当成通过了
    return False, "本地规则无法解析该断言表述，建议配置 LLM_API_KEY 后重试"


# ============================================================================
# 4. 大模型判断
# ============================================================================

def judge_by_llm(rule, response, context=""):
    """把规则与响应交给大模型判断。

    :param rule: 中文描述的断言规则
    :param response: requests.Response 对象或响应文本
    :param context: 额外上下文，例如接口地址
    :return: (是否满足, 判断依据说明)
    """
    # 组装提示词。状态码单独拼一段，避免模型看不到状态码
    status_code = get_status_code(response)
    status_line = "HTTP 状态码: {}\n".format(status_code) if status_code is not None else ""

    prompt = render_assert_prompt(
        rule=rule,
        payload=status_line + extract_payload(response),
        context=context,
    )

    # 调用大模型
    answer = call_llm(prompt)
    if not answer.strip():
        # 调用失败，交给调用方决定降级
        return None, "大模型调用失败"

    # 解析模型输出。
    # 提示词要求首行固定输出 VERDICT: PASS 或 VERDICT: FAIL，
    # 这里优先按标记解析，标记缺失时才退回关键词匹配
    text = answer.strip()
    verdict = parse_verdict(text)

    # 标记明确时直接用
    if verdict is not None:
        return verdict, text

    # 标记缺失时退回关键词匹配。
    # 否定词优先，因为「不满足」里也含有「满足」
    negative_markers = ["不满足", "未满足", "不成立", "不符合", "断言失败", "not satisfied"]
    positive_markers = ["满足", "成立", "符合", "断言通过", "satisfied"]

    lowered = text.lower()
    if any(marker in lowered for marker in negative_markers):
        return False, text
    if any(marker in lowered for marker in positive_markers):
        return True, text

    # 结论不明确时，把模型原文交回去，让调用方看到真实输出
    return None, text


def parse_verdict(text):
    """从模型输出中解析 VERDICT 标记。

    提示词要求首行输出 VERDICT: PASS 或 VERDICT: FAIL，
    这里做宽松一点的匹配：忽略大小写，允许冒号前后有空格，
    并扫描前若干行而不只看第一行，容忍模型偶尔加的寒暄。

    :param text: 模型返回的文本
    :return: True 表示 PASS，False 表示 FAIL，None 表示没找到标记
    """
    if not text:
        return None

    # 只扫前 10 行，避免正文里偶然出现的 VERDICT 干扰
    for line in text.splitlines()[:10]:
        # 去掉可能存在的 markdown 强调符号与首尾空白
        cleaned = line.strip().strip("*").strip()
        # 匹配 VERDICT: PASS / VERDICT: FAIL
        matched = re.match(r"VERDICT\s*[:：]\s*(PASS|FAIL)", cleaned, re.IGNORECASE)
        if matched:
            return matched.group(1).upper() == "PASS"

    return None


# ============================================================================
# 5. 对外入口：ai_assert
# ============================================================================

def ai_assert(response, rule, strict=True, context=""):
    """用中文规则断言响应是否满足预期。

    :param response: requests.Response 对象，或已是文本的响应内容
    :param rule: 中文描述的断言规则，例如「状态码等于 200」
    :param strict: True 时不满足抛 AssertionError；False 时只打印结论
    :param context: 额外上下文，例如接口地址
    :return: 满足返回 True，不满足返回 False
    :raises AssertionError: strict=True 且不满足时抛出
    """
    # 先用大模型判断，有 Key 时优先
    if has_api_key():
        satisfied, reason = judge_by_llm(rule, response, context)
        if satisfied is None:
            # 大模型调用失败，降级到本地规则
            satisfied, reason = judge_by_local_rules(rule, response)
            reason = "（大模型不可用，已降级为本地规则判断）" + reason
    else:
        # 没有 Key，直接用本地规则
        satisfied, reason = judge_by_local_rules(rule, response)

    # 打印结论。无论是否抛异常都打印，方便在 pytest -s 下直接看到
    status = "通过" if satisfied else "不通过"
    print("[AI断言] {} | 规则: {}".format(status, rule))
    print("[AI断言] 依据: {}".format(reason))

    # strict 模式下不满足要抛异常，让 pytest 判定用例失败
    if not satisfied and strict:
        raise AssertionError("自然语言断言不满足\n规则: {}\n依据: {}".format(rule, reason))

    return satisfied


def ai_assert_many(response, rules, strict=True, context=""):
    """一次执行多条自然语言断言。

    :param response: requests.Response 对象
    :param rules: 中文规则列表
    :param strict: True 时任一条不满足即抛 AssertionError
    :param context: 额外上下文
    :return: 所有规则的判断结果列表，每项为 (规则, 是否满足, 依据)
    :raises AssertionError: strict=True 且存在不满足的规则时抛出
    """
    results = []
    for rule in rules:
        satisfied, reason = judge_by_local_rules(rule, response)
        results.append((rule, satisfied, reason))

    # 打印每条规则的结论
    for rule, satisfied, reason in results:
        print("[AI断言] {} | 规则: {}".format("通过" if satisfied else "不通过", rule))
        print("[AI断言] 依据: {}".format(reason))

    # 汇总不满足的规则
    failed = [rule for rule, satisfied, _ in results if not satisfied]

    # strict 模式下有失败就抛异常
    if failed and strict:
        raise AssertionError("以下自然语言断言不满足:\n- " + "\n- ".join(failed))

    return results


if __name__ == "__main__":
    # 自检：用一段假响应验证本地规则的判断结果
    class FakeResponse(object):
        """极简的响应替身，仅用于本文件自检。"""

        def __init__(self, status_code, text):
            self.status_code = status_code
            self.text = text

        def json(self):
            return json.loads(self.text)

    response = FakeResponse(200, json.dumps({
        "access_token": "abc.def.ghi",
        "token_type": "bearer",
        "user": {"id": 1, "username": "admin", "role": "admin"},
    }, ensure_ascii=False))

    checks = [
        ("状态码等于 200", True),
        ("状态码等于 401", False),
        ("响应体包含 access_token 字段", True),
        ("响应体包含 captcha 字段", False),
        ("字段 role 的值等于 admin", True),
        ("字段 role 的值等于 student", False),
        ("响应体包含 bearer", True),
        ("响应体非空", True),
    ]

    print("=== 本地规则自检 ===")
    for rule, expect in checks:
        satisfied, reason = judge_by_local_rules(rule, response)
        flag = "OK " if satisfied == expect else "FAIL"
        print("[{}] {} -> {}".format(flag, rule, reason))
