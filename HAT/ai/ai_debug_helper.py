# -*- coding: utf-8 -*-
"""
HAT / ai / ai_debug_helper.py

接口测试失败时的自动排错助手。

三层结构：
    通信层 call_llm      —— 唯一一处大模型调用实现，OpenAI 兼容接口
    内容层 build_debug_prompt —— 组装诊断提示词
    门面层 ai_debug      —— 对外唯一入口，串联规则引擎与大模型

外加一个本地规则引擎：
    未配置 API Key 时整套代码必须仍能跑通。
    规则引擎按五类识别失败原因：
        环境类 —— 服务不可达、连接被拒、超时、依赖缺失
        语法类 —— Python 语法错误、缩进错误、导入失败
        框架类 —— pytest 夹具/标记/收集相关错误
        接口类 —— 4xx / 5xx 状态码、响应结构异常
        断言类 —— 断言失败、状态码与期望不符

兼容契约（函数名与参数顺序固定，新增参数一律带默认值追加在末尾）：
    call_llm(prompt)
    build_debug_prompt(exception, request_info, response_text, code_snippet, context)
    ai_debug(...)

依赖方向：ai_prompts ← ai_debug_helper ← ai_assert
"""

# 标准库：配置读取
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# 本项目的提示词模块
try:
    from HAT.ai.ai_prompts import (
        REPORT_TEMPLATE,
        render_assert_prompt,
        render_debug_prompt,
        render_rule_prompt,
    )
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    # 直接执行本文件时（python HAT/ai/ai_debug_helper.py），
    # sys.path[0] 是 HAT/ai 目录，框架根目录不在其中，包式导入会失败。
    # 这里把框架根目录补进 sys.path 再试一次。
    _hat_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if _hat_root not in sys.path:
        sys.path.insert(0, _hat_root)
    from HAT.ai.ai_prompts import (
        REPORT_TEMPLATE,
        render_assert_prompt,
        render_debug_prompt,
        render_rule_prompt,
    )


# ============================================================================
# 1. 配置读取
# ============================================================================

# 大模型配置的环境变量名
ENV_API_KEY = "LLM_API_KEY"
ENV_BASE_URL = "LLM_BASE_URL"
ENV_MODEL = "LLM_MODEL"

# 未配置时的默认模型名。OpenAI 兼容服务一般都能接受这个名字
DEFAULT_MODEL = "gpt-4o-mini"

# 调用大模型的默认超时时间，单位秒
DEFAULT_TIMEOUT = 60

# 调用大模型失败时的重试次数
DEFAULT_RETRIES = 2


def load_dotenv_config(env_file=None):
    """从 .env 文件读取大模型配置。

    优先用 python-dotenv；没装时退化为手工解析，
    保证这个模块在缺少可选依赖的环境下依然能导入。

    :param env_file: .env 文件路径，None 表示在 day12 目录与当前工作目录中查找
    :return: 解析出的配置字典，键为 api_key / base_url / model
    """
    # 候选路径：框架根目录/.env、当前工作目录/.env
    candidates = []
    if env_file:
        candidates.append(env_file)
    else:
        here = os.path.dirname(os.path.abspath(__file__))
        candidates.append(os.path.join(os.path.dirname(os.path.dirname(here)), ".env"))
        candidates.append(os.path.join(os.getcwd(), ".env"))

    # 收集 .env 中定义的键值对
    values = {}
    for candidate in candidates:
        if not candidate or not os.path.isfile(candidate):
            continue
        try:
            with open(candidate, "r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    # 跳过空行与注释行
                    if not line or line.startswith("#"):
                        continue
                    # 只处理 KEY=VALUE 形式
                    if "=" not in line:
                        continue
                    key, _, value = line.partition("=")
                    # 去掉可能存在的引号
                    value = value.strip().strip('"').strip("'")
                    values[key.strip()] = value
            # 找到第一个存在的 .env 就用它，不继续往下找
            break
        except OSError:
            continue

    # 环境变量优先级高于 .env 文件
    api_key = os.environ.get(ENV_API_KEY) or values.get(ENV_API_KEY, "")
    base_url = os.environ.get(ENV_BASE_URL) or values.get(ENV_BASE_URL, "")
    model = os.environ.get(ENV_MODEL) or values.get(ENV_MODEL, "") or DEFAULT_MODEL

    return {
        "api_key": api_key or "",
        "base_url": (base_url or "").rstrip("/"),
        "model": model,
    }


# 模块级配置。导入时读取一次，后续可通过 reload_config() 刷新
CONFIG = load_dotenv_config()


def reload_config(env_file=None):
    """重新读取大模型配置。

    场景：测试进程启动后用户才改了 .env 文件，需要刷新。

    :param env_file: .env 文件路径，None 表示自动查找
    :return: 新的配置字典
    """
    global CONFIG
    CONFIG = load_dotenv_config(env_file)
    return CONFIG


def has_api_key():
    """当前是否配置了大模型 API Key。

    :return: True 表示可以调用大模型
    """
    return bool(CONFIG.get("api_key"))


# ============================================================================
# 2. 通信层：call_llm
# ============================================================================

def call_llm(prompt, image_b64=None):
    """调用大模型，返回文本结果。

    这是整个项目里唯一一处大模型调用实现，
    ai_assert 通过它来工作，ai_debug 也通过它来生成诊断。

    未配置 API Key 时不发起请求，返回空字符串，
    由调用方决定降级策略。

    :param prompt: 提示词文本
    :param image_b64: 可选，base64 编码的 PNG 截图。
                      传入时按多模态消息发送（需要视觉模型），
                      用于 Web UI 的截图断言场景
    :return: 大模型返回的文本；调用失败或未配置 Key 时返回空字符串
    """
    # 没有 Key 直接返回，交给上层降级
    if not has_api_key():
        return ""

    # 组装 OpenAI 兼容的请求体
    api_key = CONFIG["api_key"]
    base_url = CONFIG["base_url"]
    model = CONFIG["model"]

    # base_url 为空说明没配地址，同样没法调用
    if not base_url:
        return ""

    # 组装消息体。带截图时按多模态格式发送（OpenAI 兼容协议）
    if image_b64:
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url",
             "image_url": {"url": "data:image/png;base64," + image_b64}},
        ]
    else:
        content = prompt

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0.2,
        # max_tokens 要留足。推理型模型（reasoning_content）会先消耗一部分
        # token 做思考，max_tokens 给小了会导致正式回答被截断、content 为空。
        # 这里给到 8192，足够覆盖思考 + 输出的开销。
        "max_tokens": 8192,
    }

    # 请求地址。base_url 通常已经带 /v1，这里补上 chat/completions
    url = base_url + "/chat/completions"

    # 重试机制。网络抖动或服务临时不可用时重试
    last_error = ""
    for attempt in range(DEFAULT_RETRIES + 1):
        try:
            request = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers={
                    "Content-Type": "application/json",
                    "Authorization": "Bearer " + api_key,
                },
            )
            # 发起请求。URL 由代码固定，Key 只在请求头里出现，不进日志
            with urllib.request.urlopen(request, timeout=DEFAULT_TIMEOUT) as response:
                body = json.loads(response.read().decode("utf-8"))
            # 取 choices[0].message.content
            choices = body.get("choices") or []
            if not choices:
                return ""
            return (choices[0].get("message") or {}).get("content", "")
        except urllib.error.HTTPError as error:
            # HTTP 4xx/5xx。4xx 多半是请求本身有问题，重试无意义
            last_error = "HTTP {} {}".format(error.code, error.reason)
            if 400 <= error.code < 500:
                break
        except Exception as error:
            # 网络异常、超时、JSON 解析失败等
            last_error = "{}: {}".format(type(error).__name__, error)

        # 最后一次失败就不再等了
        if attempt < DEFAULT_RETRIES:
            time.sleep(0.5 * (attempt + 1))

    # 调用失败时把原因记到标准错误，排查时能看到
    print("[ai_debug_helper] 大模型调用失败: {}".format(last_error), file=sys.stderr)
    return ""


# ============================================================================
# 3. 本地规则引擎
# ============================================================================

# 五类报错的定义。name 为类别名，desc 为说明，patterns 为命中特征
RULE_CATEGORIES = [
    {
        "name": "环境类",
        "desc": "服务不可达、连接被拒绝、请求超时或依赖缺失，属于运行环境的故障",
        "patterns": [
            (r"ConnectionError", "requests 抛出了 ConnectionError，说明连接建立失败"),
            (r"ConnectTimeout|ReadTimeout|Timeout", "请求超时，服务响应过慢或网络不通"),
            (r"Max retries exceeded", "重试次数用尽仍无法建立连接"),
            (r"Connection refused", "目标端口拒绝连接，服务没有启动"),
            (r"NameError", "变量或模块名不存在，可能是依赖未安装"),
            (r"ModuleNotFoundError|ImportError", "模块导入失败，依赖包缺失"),
            (r"OSError|FileNotFoundError", "文件或系统资源访问失败"),
        ],
    },
    {
        "name": "语法类",
        "desc": "Python 代码本身写错了，尚未进入业务逻辑",
        "patterns": [
            (r"SyntaxError", "Python 语法错误，代码无法被解析"),
            (r"IndentationError|TabError", "缩进错误，代码块结构不合法"),
            (r"invalid syntax", "代码中存在不合法的语法结构"),
        ],
    },
    {
        "name": "框架类",
        "desc": "pytest 框架层面的问题，如夹具缺失、标记未注册、收集失败",
        "patterns": [
            (r"fixture '[^']+' not found", "用到了不存在的夹具"),
            (r"fixture .* not found", "用到了不存在的夹具"),
            (r"PytestUnknownMarkWarning|Unknown mark", "使用了未注册的 pytest 标记"),
            (r"error collecting|ERROR collecting", "pytest 收集用例阶段失败"),
            (r"INTERNALERROR", "pytest 内部错误，通常是插件或配置问题"),
            (r"assertion rewrit", "断言重写被禁用，pytest 无法正常做断言重写"),
        ],
    },
    {
        "name": "接口类",
        "desc": "请求发出但服务端返回了异常状态码或异常响应结构",
        "patterns": [
            (r"\b500\b.*Internal Server Error", "服务端内部错误 500，需查看服务端日志"),
            (r"\b502\b|Bad Gateway", "网关错误 502"),
            (r"\b503\b|Service Unavailable", "服务不可用 503"),
            (r"\b404\b|Not Found", "接口路径不存在 404，核对接口地址与请求方法"),
            (r"\b405\b|Method Not Allowed", "请求方法不被允许 405，核对 GET/POST 等方法"),
            (r"\b401\b|Unauthorized", "未授权 401，缺少或无效的鉴权令牌"),
            (r"\b403\b|Forbidden", "权限不足 403"),
            (r"\b422\b", "参数校验失败 422，核对请求体字段"),
            (r"JSONDecodeError|Expecting value", "响应体不是合法 JSON"),
            (r"KeyError", "响应体中缺少预期的字段"),
            (r"IncompleteRead|RemoteDisconnected", "连接被服务端中断，响应体未收全"),
        ],
    },
    {
        "name": "断言类",
        "desc": "请求与响应都正常，但结果与断言的期望不一致",
        "patterns": [
            (r"AssertionError", "断言失败，实际结果与期望不符"),
            (r"assert \d+ == \d+", "状态码断言失败"),
            (r"assert .* is not None", "期望值不为 None 但实际为 None"),
            (r"^assert\b", "断言语句失败"),
        ],
    },
]


def match_rule(exception_text):
    """用本地规则引擎判断失败属于哪一类。

    :param exception_text: 异常文本
    :return: 命中的规则字典，包含 name / desc / rule_name / rule_desc；
             一条都没命中时返回默认的断言类规则
    """
    text = exception_text or ""

    # 依次匹配五类规则
    for category in RULE_CATEGORIES:
        for pattern, rule_desc in category["patterns"]:
            if re.search(pattern, text):
                return {
                    "name": category["name"],
                    "desc": category["desc"],
                    "rule_name": rule_desc,
                    "rule_desc": category["desc"],
                }

    # 全都没命中时按最常见的断言失败处理
    return {
        "name": "断言类",
        "desc": "未匹配到已知特征，按断言失败处理",
        "rule_name": "默认兜底规则",
        "rule_desc": "异常文本未匹配任何已知特征，默认按断言失败分析",
    }


# ============================================================================
# 4. 内容层：build_debug_prompt
# ============================================================================

def build_debug_prompt(exception, request_info, response_text, code_snippet, context=""):
    """组装失败诊断用的提示词。

    先用本地规则引擎做一次快速分类，
    命中规则时把结论一并给大模型，让它在此基础上做精确定位；
    没命中时用通用诊断提示词。

    :param exception: 异常对象或异常文本
    :param request_info: 请求信息文本
    :param response_text: 响应体文本
    :param code_snippet: 失败位置源码片段
    :param context: 额外上下文
    :return: 完整的提示词文本
    """
    # 把异常统一转成文本
    exception_text = format_exception(exception)

    # 跑一遍本地规则引擎
    rule = match_rule(exception_text)

    # 命中了具体规则就走规则版提示词，把结论喂给大模型
    if rule["rule_name"] != "默认兜底规则":
        return render_rule_prompt(
            category=rule["name"],
            rule_name=rule["rule_name"],
            rule_desc=rule["rule_desc"],
            exception=exception_text,
            request_info=request_info,
            response_text=response_text,
            code_snippet=code_snippet,
            context=context,
        )

    # 没命中则用通用诊断提示词
    return render_debug_prompt(
        exception=exception_text,
        request_info=request_info,
        response_text=response_text,
        code_snippet=code_snippet,
        context=context,
    )


def format_exception(exception):
    """把异常对象转成可读文本。

    :param exception: 异常对象、异常类型或字符串
    :return: 异常文本
    """
    # 已经是字符串时直接用
    if isinstance(exception, str):
        return exception
    # None 时给个占位
    if exception is None:
        return ""
    # 异常对象取类型名加消息
    return "{}: {}".format(type(exception).__name__, str(exception))


# ============================================================================
# 5. 门面层：ai_debug
# ============================================================================

def ai_debug(exception, request_info="", response_text="", code_snippet="",
             context="", case_name="", case_file="", stage="call",
             report_dir=None):
    """生成失败诊断并写入 Markdown 报告。

    这是对外唯一入口：
        1. 跑本地规则引擎拿初步结论；
        2. 有 API Key 就调大模型做深度分析，没有就用规则结论；
        3. 拼装 Markdown 报告写盘。

    :param exception: 异常对象或异常文本
    :param request_info: 请求信息文本
    :param response_text: 响应体文本
    :param code_snippet: 失败位置源码片段
    :param context: 额外上下文
    :param case_name: 用例名，用作报告文件名
    :param case_file: 用例所在文件
    :param stage: 失败阶段，call 表示用例执行阶段失败
    :param report_dir: 报告输出目录，None 表示项目根下的 ai_debug_reports
    :return: 生成的报告 Markdown 文本；连报告文件都没写成时返回空字符串
    """
    # 第 1 步：异常统一转文本，并跑一遍规则引擎
    exception_text = format_exception(exception)
    rule = match_rule(exception_text)

    # 第 2 步：组装诊断正文。有 Key 走大模型，没有就用规则结论
    diagnosis = ""
    source = "本地规则引擎"

    if has_api_key():
        # 组装提示词。与 build_debug_prompt 同源，保证两处口径一致
        prompt = build_debug_prompt(
            exception_text, request_info, response_text, code_snippet, context
        )
        # 调用大模型。内部已做重试与异常兜底，失败返回空串
        answer = call_llm(prompt)
        if answer.strip():
            diagnosis = answer.strip()
            source = "大模型（{}）".format(CONFIG.get("model", ""))
        else:
            # 有 Key 但调用失败，退回规则结论
            diagnosis = build_local_diagnosis(rule, exception_text,
                                              request_info, response_text)
    else:
        # 没有 Key，直接用本地规则结论
        diagnosis = build_local_diagnosis(rule, exception_text,
                                          request_info, response_text)

    # 第 3 步：拼装报告正文
    report = REPORT_TEMPLATE.format(
        case_name=case_name or "未知用例",
        case_file=case_file or "",
        stage=stage,
        generated_at=time.strftime("%Y-%m-%d %H:%M:%S"),
        source=source,
        exception=exception_text or "（无异常信息）",
        request_info=request_info or "（无请求信息）",
        response_text=response_text or "（无响应内容）",
        code_snippet=code_snippet or "（无源码片段）",
        diagnosis=diagnosis,
    )

    # 第 4 步：写入文件。目录不存在就创建
    if report_dir is None:
        # 默认写到框架根目录下的 ai_debug_reports
        here = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.dirname(os.path.dirname(here))
        report_dir = os.path.join(project_root, "ai_debug_reports")
    try:
        os.makedirs(report_dir, exist_ok=True)
        # 文件名用用例名，去掉路径分隔符等不适合做文件名的字符
        safe_name = re.sub(r'[\\/:*?"<>|]', "_", case_name or "unknown_case")
        file_path = os.path.join(report_dir, "{}_debug.md".format(safe_name))
        with open(file_path, "w", encoding="utf-8") as handle:
            handle.write(report)
        return report
    except OSError as error:
        # 写盘失败不能影响测试流程，打印提示即可
        print("[ai_debug_helper] 诊断报告写入失败: {}".format(error), file=sys.stderr)
        return report


def build_local_diagnosis(rule, exception_text, request_info, response_text):
    """没有大模型时，用规则引擎结论拼一份本地诊断。

    :param rule: 规则引擎命中的规则
    :param exception_text: 异常文本
    :param request_info: 请求信息文本
    :param response_text: 响应体文本
    :return: Markdown 格式的诊断正文
    """
    # 按类别给出针对性的排查建议
    suggestions = {
        "环境类": [
            "确认被测服务已启动：访问 {}/health 看是否返回 200".format(
                os.environ.get("BASE_URL", "http://localhost:8000")
            ),
            "确认服务端口与 base_url 配置一致",
            "确认没有网络代理或防火墙拦截本机端口",
            "确认 requests 等依赖已安装且版本兼容",
        ],
        "语法类": [
            "在 IDE 中检查报错行附近的括号、引号与缩进",
            "确认修改后的文件已保存",
            "用 python -m py_compile 文件名 做一次语法自检",
        ],
        "框架类": [
            "确认使用的夹具在 conftest.py 中确实存在且作用域匹配",
            "确认自定义标记已在 pytest.ini 的 markers 中注册",
            "确认测试文件命名与目录结构符合 pytest 的收集规则",
        ],
        "接口类": [
            "核对请求方法与接口文档是否一致（GET/POST/PUT/DELETE）",
            "核对接口路径是否正确，注意接口前缀与末尾斜杠",
            "核对鉴权信息是否已携带，令牌是否过期",
            "核对请求体字段名与类型是否符合接口定义",
            "查看服务端日志确认错误发生在哪一层",
        ],
        "断言类": [
            "确认期望值本身写对了，再确认实际响应是否真的不符",
            "打印实际响应体，逐字段与期望值比对",
            "确认断言执行前响应已被正确获取，没有拿到 None",
        ],
    }

    # 组装 Markdown 正文
    lines = [
        "## 一、失败现象",
        "",
        "本地规则引擎判定本次失败属于 **{}**。".format(rule["name"]),
        "",
        "```",
        exception_text or "（无异常信息）",
        "```",
        "",
        "## 二、根因分析",
        "",
        "- **类别**：{}".format(rule["name"]),
        "- **命中规则**：{}".format(rule["rule_name"]),
        "- **规则说明**：{}".format(rule["rule_desc"]),
        "",
        "## 三、修复建议",
        "",
    ]

    # 逐条追加该类别的建议
    for index, suggestion in enumerate(suggestions.get(rule["name"], []), 1):
        lines.append("{}. {}".format(index, suggestion))

    # 附上现场信息，方便人工继续排查
    lines.extend([
        "",
        "## 四、验证方式",
        "",
        "按上述建议调整后重新执行该用例，确认状态码与响应体符合断言。",
        "",
        "<details><summary>请求信息</summary>",
        "",
        "```",
        request_info or "（无请求信息）",
        "```",
        "",
        "</details>",
        "",
        "<details><summary>响应内容</summary>",
        "",
        "```",
        response_text or "（无响应内容）",
        "```",
        "",
        "</details>",
    ])

    return "\n".join(lines)


if __name__ == "__main__":
    # 自检：跑一遍规则引擎，确认五类都能命中
    samples = [
        ("ConnectionError: HTTPConnectionPool(host='localhost', port=8000): "
         "Max retries exceeded", "环境类"),
        ("  File \"x.py\", line 3\n    if True\nSyntaxError: invalid syntax", "语法类"),
        ("fixture 'no_such_fixture' not found", "框架类"),
        ("AssertionError: assert 500 == 200", "断言类"),
        ("requests.exceptions.HTTPError: 404 Client Error: Not Found", "接口类"),
    ]
    for text, expect in samples:
        result = match_rule(text)
        flag = "OK " if result["name"] == expect else "FAIL"
        print("[{}] 期望 {} -> 实际 {}".format(flag, expect, result["name"]))
