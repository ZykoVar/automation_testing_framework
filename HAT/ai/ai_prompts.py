# -*- coding: utf-8 -*-
"""
HAT / ai / ai_prompts.py

全部提示词与公共片段的集中存放处。

设计约束：
    1. 纯标准库，不依赖 openai / pytest / requests。
       这样任何一层想换通信方式或换断言框架，都不会牵连到这里。
    2. 提示词与业务代码分离。改提示词只改本文件，不动任何业务代码。
    3. 提示词以「片段 + 占位符」的方式组织，用 format() 渲染。
       占位符名字显式出现在代码里，渲染失败会立刻抛 KeyError，
       不会出现「提示词里少写一个 {} 却悄悄发出去」的情况。

三层结构：
    公共片段（COMMON_*）  —— 各场景共用的身份设定与输出约束
    场景提示词（*_PROMPT）—— 每个具体场景一段
    渲染函数（render_*）  —— 把公共片段与场景提示词拼成最终 prompt

对外暴露：
    render_debug_prompt(...)  —— 渲染失败诊断用的提示词
    render_assert_prompt(...) —— 渲染自然语言断言用的提示词
    render_rule_prompt(...)   —— 渲染本地规则引擎补充说明用的提示词
    所有常量                   —— 便于测试与二次封装
"""

# ============================================================================
# 1. 公共片段
# ============================================================================

# 身份设定。所有场景共用的一段，让大模型始终站在「资深测试工程师」的角色上
ROLE_TEST_ENGINEER = (
    "你是一名资深接口测试工程师，精通 pytest、requests、HTTP 协议与 RESTful 接口设计，"
    "拥有多年接口自动化与线上问题排查经验。"
)

# 分析时必须遵循的思维步骤。放在提示词前部，让模型先建立分析框架再下结论
ANALYSIS_STEPS = (
    "分析时按以下顺序思考：\n"
    "1. 先复述客观事实：异常类型、异常消息、状态码、响应体中的关键字段；\n"
    "2. 再定位问题边界：是测试代码写错、接口行为不符预期，还是环境/依赖故障；\n"
    "3. 最后给出可执行的修复建议，按优先级排序。\n"
    "严禁编造未在上下文中出现的信息，无法判断的部分明确写「信息不足，无法判断」。"
)

# 输出格式约束。规定严格输出 Markdown 章节，便于程序解析与人工阅读
OUTPUT_FORMAT = (
    "输出必须使用 Markdown，按以下章节组织，不要有多余的前言和客套话：\n"
    "## 一、失败现象\n"
    "客观描述发生了什么，包含关键错误信息原文。\n"
    "## 二、根因分析\n"
    "分条列出，每条标注「测试代码问题 / 接口行为问题 / 环境或依赖问题 / 信息不足」四类之一。\n"
    "## 三、修复建议\n"
    "给出可直接落地的修改，每条说明改哪个文件、改成什么、为什么。\n"
    "## 四、验证方式\n"
    "说明修复后如何确认问题已消除。"
)

# 排错场景的身份设定：比断言场景更强调定位问题
ROLE_DEBUGGER = ROLE_TEST_ENGINEER + (
    "你的当前任务是分析一条自动化测试用例的失败原因，"
    "定位失败点并给出准确的修复方案。"
)

# 断言场景的身份设定：只判断规则是否满足，不做无关推测
ROLE_JUDGE = ROLE_TEST_ENGINEER + (
    "你的当前任务是判断一条测试响应是否满足用户用中文描述的断言规则，"
    "只依据给定的响应内容做判断，不推测未提供的信息。"
)


# ============================================================================
# 2. 场景提示词
# ============================================================================

# 失败诊断提示词。四个占位符分别对应异常、请求信息、响应体、源码片段
DEBUG_PROMPT = """{role}

{context}

{analysis_steps}

{output_format}

---

## 一、待分析的失败现场

### 1. 异常信息
```
{exception}
```

### 2. 失败用例的请求信息
```
{request_info}
```

### 3. 服务端响应内容
```
{response_text}
```

### 4. 失败位置的源码片段
```python
{code_snippet}
```

请基于以上全部信息完成分析。

补充要求：
1. 如果响应内容为空或明显不是接口返回的内容（例如是连接错误页），要在根因分析中明确指出；
2. 如果异常来自断言而不是请求本身，要区分「请求没发对」与「响应不符合预期」；
3. 修复建议必须针对具体文件与具体代码，不要写「检查接口是否正常」这类无法执行的建议；
4. 本次分析不要修改任何文件，只输出分析与建议。
"""

# 自然语言断言提示词。占位符 rule 是中文规则，payload 是实际响应内容
ASSERT_PROMPT = """{role}

{analysis_steps}

{output_format}

---

## 一、待判断的断言

### 断言规则（用户用中文描述）
```
{rule}
```

### 实际响应
```
{payload}
```

请判断实际响应是否满足上述断言规则。

---

## 输出要求（必须严格遵守）

回答的**第一行**必须是下面两行之一，且只能有一行，不加任何前缀、后缀或标点：

VERDICT: PASS
VERDICT: FAIL

第一行给出结论之后，再输出下列 Markdown 章节：

## 一、失败现象
用一句话复述你判断的结论（满足或不满足），并说明依据。

## 二、根因分析
说明为什么得出这个结论，引用响应中的具体字段与值。

## 三、修复建议
规则不满足时给出处理方式；满足时说明已验证的内容。

补充要求：
1. 严格按规则字面含义判断，不要替用户放宽或收紧标准；
2. 只依据「实际响应」中的内容判断，不推测未出现的信息；
3. 规则中若出现「包含」「等于」「大于」「小于」「为空」「非空」等词，按其常规含义严格比对；
4. 除第一行的 VERDICT 外，正文中不要出现 VERDICT 字样，避免干扰解析。
"""

# 规则引擎补充提示词。当地规则引擎已经定位到问题类别时，
# 把这个结论交给大模型做精确定位与修复建议
RULE_PROMPT = """{role}

本地规则引擎已经对该失败做出初步判断，请在此基础上精确定位并给出修复方案。

## 一、规则引擎的初步结论
- 命中类别：{category}
- 命中规则：{rule_name}
- 规则说明：{rule_desc}

## 二、失败现场
### 异常信息
```
{exception}
```

### 请求信息
```
{request_info}
```

### 响应内容
```
{response_text}
```

### 源码片段
```python
{code_snippet}
```

{analysis_steps}

{output_format}

补充要求：
1. 结论必须与规则引擎给出的类别一致，不要推翻；
2. 在此基础上补充规则引擎没能定位到的具体信息（如具体是哪个断言、哪个字段不对）；
3. 修复建议要落到具体文件与具体代码。
"""


# ============================================================================
# 3. 渲染函数
# ============================================================================

def render_debug_prompt(exception, request_info, response_text, code_snippet, context=""):
    """渲染失败诊断用的提示词。

    :param exception: 异常对象或异常文本
    :param request_info: 请求信息文本，方法、URL、请求头、请求体
    :param response_text: 服务端响应体文本
    :param code_snippet: 失败位置的源码片段
    :param context: 额外上下文，例如被测服务地址、用例名
    :return: 渲染完成的提示词字符串
    """
    # 上下文为空时给一句默认说明，避免提示词里出现空白段落
    extra_context = context.strip() if context and context.strip() else "无额外上下文。"
    return DEBUG_PROMPT.format(
        role=ROLE_DEBUGGER,
        context=extra_context,
        analysis_steps=ANALYSIS_STEPS,
        output_format=OUTPUT_FORMAT,
        exception=exception if exception else "（无异常信息）",
        request_info=request_info if request_info else "（无请求信息）",
        response_text=response_text if response_text else "（无响应内容）",
        code_snippet=code_snippet if code_snippet else "（无源码片段）",
    )


def render_assert_prompt(rule, payload, context=""):
    """渲染自然语言断言用的提示词。

    :param rule: 中文描述的断言规则
    :param payload: 实际响应的文本内容
    :param context: 额外上下文，例如被测接口地址
    :return: 渲染完成的提示词字符串
    """
    # 上下文为空时给一句默认说明
    extra_context = context.strip() if context and context.strip() else "无额外上下文。"
    # 把上下文拼到规则后面，让模型知道这条规则针对的是哪个接口
    full_rule = "{}\n（规则适用范围：{}）".format(rule, extra_context)
    return ASSERT_PROMPT.format(
        role=ROLE_JUDGE,
        analysis_steps=ANALYSIS_STEPS,
        output_format=OUTPUT_FORMAT,
        rule=full_rule,
        payload=payload if payload else "（空响应）",
    )


def render_rule_prompt(category, rule_name, rule_desc,
                       exception, request_info, response_text, code_snippet,
                       context=""):
    """渲染本地规则引擎命中后的补充分析提示词。

    :param category: 规则命中的类别
    :param rule_name: 命中的规则名
    :param rule_desc: 规则说明
    :param exception: 异常对象或文本
    :param request_info: 请求信息文本
    :param response_text: 响应体文本
    :param code_snippet: 源码片段
    :param context: 额外上下文
    :return: 渲染完成的提示词字符串
    """
    extra_context = context.strip() if context and context.strip() else "无额外上下文。"
    return RULE_PROMPT.format(
        role=ROLE_DEBUGGER,
        category=category,
        rule_name=rule_name,
        rule_desc=rule_desc,
        exception=exception if exception else "（无异常信息）",
        request_info=request_info if request_info else "（无请求信息）",
        response_text=response_text if response_text else "（无响应内容）",
        code_snippet=code_snippet if code_snippet else "（无源码片段）",
        analysis_steps=ANALYSIS_STEPS,
        output_format=OUTPUT_FORMAT,
    )


# ============================================================================
# 4. 对外常量
# ============================================================================

# 报告模板。诊断报告的 Markdown 骨架，由 ai_debug_helper 填充内容
REPORT_TEMPLATE = """# 用例失败诊断报告

## 基本信息

| 项 | 值 |
| --- | --- |
| 用例 | `{case_name}` |
| 用例文件 | `{case_file}` |
| 失败阶段 | `{stage}` |
| 生成时间 | `{generated_at}` |
| 诊断来源 | `{source}` |

---

## 失败现场

### 异常信息
```
{exception}
```

### 请求信息
```
{request_info}
```

### 响应内容
```
{response_text}
```

### 失败位置源码
```python
{code_snippet}
```

---

## 诊断结论

{diagnosis}
"""


if __name__ == "__main__":
    # 自检：渲染一遍提示词，确认没有占位符缺失
    print(render_debug_prompt(
        exception="AssertionError: assert 200 == 401",
        request_info="POST http://localhost:8000/api/v1/auth/login",
        response_text='{"detail":"Not Found"}',
        code_snippet="response = requests.post(url, json=payload)",
        context="被测服务 http://localhost:8000",
    )[:600])
    print("...")
    print(render_assert_prompt(
        rule="状态码等于 200",
        payload='{"access_token": "xxx"}',
    )[:400])
    print("...")
    print(render_rule_prompt(
        category="断言类",
        rule_name="状态码断言失败",
        rule_desc="响应状态码与期望值不一致",
        exception="AssertionError",
        request_info="POST /api/v1/auth/login",
        response_text="{}",
        code_snippet="assert response.status_code == 200",
    )[:400])
