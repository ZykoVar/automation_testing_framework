# -*- coding: utf-8 -*-
"""
day10 / utils / yaml_loader.py
pip install pyyaml    安装pyyaml库

YAML 驱动的接口用例数据加载工具。

解决什么问题：
    接口用例数据写在 YAML 文件里，测试代码只负责「怎么执行、怎么断言」，
    新增场景只需往 YAML 追加一条记录，不用改测试函数。

核心能力：
    1. load_yaml_file(path)             —— 读取单个 YAML 文件，异常信息带文件名；
    2. render_vars(obj, variables)      —— 递归替换 ${VAR} 占位符；
    3. parse_file(path)                 —— 把 YAML 解析成 List[ApiCase]；
    4. load_cases(path, case_ids=None)  —— 按 case_id 过滤后返回用例列表；
    5. ApiCase                          —— 用例数据类，带 to_request_kwargs() 与 pytest_id；
    6. jsonpath_get(data, expression)   —— 迷你 JSONPath，取值用于 expect_json 断言。

设计约定：
    - 文件级 method / path / headers 会下沉到每一条用例；
    - 用例级字段覆盖文件级字段，用例级优先；
    - 加载期就做完整校验（重复 case_id、必填缺失、method 非法、expect_status 缺失），
      错误信息统一带上文件名与用例位置，避免跑到一半才发现数据写错；
    - 本文件不依赖项目内其它模块，可独立使用。
"""

# 标准库：数据类，用于描述一条接口用例
from dataclasses import dataclass, field

# 标准库：类型注解
from typing import Any, Dict, List, Optional

# 标准库：环境变量，变量占位符优先从这里取
import os

# 标准库：路径处理
from pathlib import Path

# 标准库：正则，占位符替换与 JSONPath 取值都要用
import re

# 第三方库：PyYAML，读取用例数据文件
import yaml


# ============================================================================
# 1. 常量
# ============================================================================

# 允许出现在用例里的 HTTP 方法。出现其它值说明 YAML 写错了
ALLOWED_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")

# 占位符匹配规则：${VAR}，VAR 允许字母、数字、下划线，且不以数字开头
PLACEHOLDER_PATTERN = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}")

# 默认变量表。环境变量中同名变量优先于此表
DEFAULT_VARIABLES: Dict[str, str] = {
    "BASE_URL": "http://localhost:8000",
}


# ============================================================================
# 2. 异常
# ============================================================================

class YamlCaseError(Exception):
    """YAML 用例数据相关的异常。

    所有错误信息都带上文件名与用例位置，
    例如「用例数据错误: login.yaml -> cases[2] (login003): expect_status 缺失」。
    """


# ============================================================================
# 3. JSONPath 取值
# ============================================================================

def jsonpath_get(data: Any, expression: str) -> Any:
    """按 JSONPath 表达式从数据中取值。

    支持的表达式写法（本项目够用即可，不追求完整的 JSONPath 规范）：
        $.user.username      取字典里的字段
        $.data[0].id        先取列表第 0 项，再取字段
        $.data[0]           直接取列表第 0 项

    :param data: 被取值的原始数据，通常是解析后的响应体
    :param expression: JSONPath 表达式，必须以 $ 开头
    :return: 取到的值；路径不存在时返回 None
    :raises ValueError: 表达式格式非法时抛出
    """
    # 表达式必须以 $ 开头，否则视为非法
    if not isinstance(expression, str) or not expression.startswith("$"):
        raise ValueError("JSONPath 表达式必须以 $ 开头，实际为: {}".format(expression))

    # 拆出路径片段：.字段 或 [下标]
    tokens = re.findall(r"\.([^.\[\]]+)|\[(\d+)\]", expression[1:])

    # 从原始数据开始逐层往下走
    current = data
    # 逐个片段下钻
    for field_name, index in tokens:
        # 当前节点不是容器时无法继续，直接返回 None
        if current is None:
            return None
        # 下标片段：按列表下标取值
        if index:
            # 不是列表或下标越界时返回 None
            if not isinstance(current, list) or int(index) >= len(current):
                return None
            current = current[int(index)]
        # 字段片段：按键取值
        else:
            # 不是字典时返回 None
            if not isinstance(current, dict):
                return None
            current = current.get(field_name)

    # 返回最终取到的值
    return current


# ============================================================================
# 4. 变量渲染
# ============================================================================

def render_vars(obj: Any, variables: Optional[Dict[str, str]] = None) -> Any:
    """递归替换字符串中的 ${VAR} 占位符。

    变量来源：传入的 variables 优先，其次环境变量，最后内置默认表。
    未找到对应变量时保留占位符原文，便于排查是哪里少配了变量。

    :param obj: 待处理的对象，支持 dict / list / str / 标量
    :param variables: 变量表，形如 {"BASE_URL": "http://localhost:8000"}
    :return: 替换后的新对象，原对象不被修改
    """
    # 合并变量来源：内置默认 < 环境变量 < 显式传入
    merged: Dict[str, str] = dict(DEFAULT_VARIABLES)
    # 环境变量覆盖默认值
    merged.update({key: value for key, value in os.environ.items()})
    # 显式传入的变量优先级最高
    if variables:
        merged.update(variables)

    # 递归处理
    return _render_value(obj, merged)


def _render_value(value: Any, variables: Dict[str, str]) -> Any:
    """render_vars 的递归实现。

    :param value: 当前节点的值
    :param variables: 已合并好的变量表
    :return: 替换后的值
    """
    # 字典：逐个键值递归
    if isinstance(value, dict):
        return {key: _render_value(item, variables) for key, item in value.items()}
    # 列表：逐个元素递归
    if isinstance(value, list):
        return [_render_value(item, variables) for item in value]
    # 字符串：做占位符替换
    if isinstance(value, str):
        return PLACEHOLDER_PATTERN.sub(
            lambda match: variables.get(match.group(1), match.group(0)),
            value,
        )
    # 其余类型（数字、布尔、None）原样返回
    return value


# ============================================================================
# 5. 用例数据类
# ============================================================================

@dataclass
class ApiCase:
    """一条接口用例。

    文件级配置在解析时下沉到每条用例，
    因此用例对象是自包含的，执行时不需要再回头找文件级配置。
    """

    # 用例编号，全文件唯一
    case_id: str = ""
    # 用例名称，用于报告展示
    case_name: str = ""
    # 所属业务场景，用于分组
    story: str = ""
    # HTTP 方法
    method: str = "GET"
    # 接口路径
    path: str = ""
    # 服务基础地址，空表示路径本身就是完整地址
    base_url: str = ""
    # 请求头
    headers: Dict[str, Any] = field(default_factory=dict)
    # JSON 请求体
    json_body: Optional[Any] = None
    # 原始请求体。与 json_body 互斥，用于构造非 JSON 的请求体
    raw_body: Optional[str] = None
    # 期望的 HTTP 状态码
    expect_status: int = 0
    # 期望的响应 message 关键字
    expect_message: Optional[str] = None
    # 期望的响应字段，形如 {"$.user.role": "admin"}
    expect_json: Dict[str, Any] = field(default_factory=dict)
    # 是否跳过
    skip: bool = False
    # 跳过原因
    skip_reason: str = ""
    # 重复执行次数，默认 1
    repeat: int = 1
    # 所属模块与接口标识，来自文件级配置
    module: str = ""
    interface: str = ""
    # 接口名称，来自文件级配置
    name: str = ""

    @property
    def url(self) -> str:
        """拼接后的完整请求地址。

        :return: 可直接交给 requests 的 URL
        """
        # 路径本身是完整地址时直接返回
        if self.path.startswith("http://") or self.path.startswith("https://"):
            return self.path
        # 没有配置基础地址时原样返回
        if not self.base_url:
            return self.path
        # 拼接基础地址与路径，避免双斜杠
        return "{}/{}".format(self.base_url.rstrip("/"), self.path.lstrip("/"))

    @property
    def pytest_id(self) -> str:
        """pytest 参数化时的用例标识。

        格式为「编号-用例名」，例如 login002-登录失败-账号不存在。

        :return: 用例标识字符串
        """
        return "{}-{}".format(self.case_id, self.case_name)

    def to_request_kwargs(self) -> Dict[str, Any]:
        """转成 requests.request() 的关键字参数。

        返回值可直接展开使用：
            requests.request(**case.to_request_kwargs())

        :return: 包含 method、url、headers 与请求体的字典
        """
        # 基础参数
        kwargs: Dict[str, Any] = {
            "method": self.method,
            "url": self.url,
            "headers": dict(self.headers),
        }
        # 有原始请求体时按原始内容发送
        if self.raw_body is not None:
            kwargs["data"] = self.raw_body
        # 否则有 JSON 请求体时按 JSON 发送。
        # 用 is not None 判断而不是真值判断，json_body 为空字典 {} 时也要发送
        elif self.json_body is not None:
            kwargs["json"] = self.json_body
        # 返回参数
        return kwargs


# ============================================================================
# 6. 读取与解析
# ============================================================================

def load_yaml_file(path: Any) -> Dict[str, Any]:
    """读取单个 YAML 文件并返回解析后的字典。

    :param path: YAML 文件路径，str 或 Path 均可
    :return: 解析后的字典
    :raises YamlCaseError: 文件不存在、语法错误、顶层结构不是字典
    """
    # 统一转成 Path，后续拼接与报错展示更方便
    file_path = Path(path)
    # 文件不存在时给出带文件名的清晰提示
    if not file_path.is_file():
        raise YamlCaseError("YAML 用例文件不存在: {}".format(file_path))

    # 读取并解析。encoding 固定 utf-8，保证中文用例名不乱码
    try:
        with file_path.open("r", encoding="utf-8") as handle:
            # safe_load 不会构造任意 Python 对象，安全性更高
            content = yaml.safe_load(handle)
    except yaml.YAMLError as error:
        # 语法错误时把文件名与原始原因一起抛出
        raise YamlCaseError("YAML 语法错误: {}: {}".format(file_path, error)) from error
    except OSError as error:
        # 读文件失败（权限、编码等）
        raise YamlCaseError("YAML 文件读取失败: {}: {}".format(file_path, error)) from error

    # 顶层不是字典说明文件结构不对
    if not isinstance(content, dict):
        raise YamlCaseError(
            "YAML 顶层结构必须是字典: {}: 实际为 {}".format(
                file_path, type(content).__name__
            )
        )

    # 返回解析结果
    return content


def _require(value: Any, field_name: str, location: str, file_path: Path) -> Any:
    """校验必填字段是否缺失，缺失时抛出带位置的异常。

    :param value: 字段值
    :param field_name: 字段名，用于报错信息
    :param location: 用例位置，例如 cases[2] (login003)
    :param file_path: 文件路径，用于报错信息
    :return: 非空的字段值
    :raises YamlCaseError: 字段缺失或为空
    """
    # 值为 None 或空字符串都视为缺失
    if value is None or (isinstance(value, str) and not value.strip()):
        raise YamlCaseError(
            "用例数据错误: {} -> {}: {} 缺失".format(file_path, location, field_name)
        )
    # 返回校验通过的值
    return value


def parse_file(path: Any, variables: Optional[Dict[str, str]] = None) -> List[ApiCase]:
    """解析 YAML 文件，返回用例列表。

    处理步骤：
        1. 读取文件并做变量替换；
        2. 校验文件级配置（method、path 必填，method 合法）；
        3. 逐条解析用例，把文件级配置下沉，用例级配置覆盖；
        4. 校验 case_id 唯一、必填字段齐全、expect_status 存在。

    :param path: YAML 文件路径
    :param variables: 变量表，用于 ${VAR} 替换
    :return: 用例列表
    :raises YamlCaseError: 文件级或用例级配置有误
    """
    # 文件路径
    file_path = Path(path)
    # 读取并渲染变量
    content = render_vars(load_yaml_file(file_path), variables)

    # 文件级位置标识，用于报错
    file_level = "文件级配置"

    # 文件级必填项校验
    file_method = _require(content.get("method"), "method", file_level, file_path)
    file_path_value = _require(content.get("path"), "path", file_level, file_path)

    # method 合法性校验
    if str(file_method).upper() not in ALLOWED_METHODS:
        raise YamlCaseError(
            "用例数据错误: {} -> {}: method 非法，实际为 {}".format(
                file_path, file_level, file_method
            )
        )

    # 文件级可选配置
    file_base_url = content.get("base_url") or ""
    file_headers = content.get("headers") or {}
    file_module = content.get("module") or ""
    file_interface = content.get("interface") or ""
    file_name = content.get("name") or ""

    # 用例列表
    raw_cases = content.get("cases")
    # cases 缺失或不是列表都算配置错误
    if not isinstance(raw_cases, list) or not raw_cases:
        raise YamlCaseError(
            "用例数据错误: {} -> cases 必须是非空列表".format(file_path)
        )

    # 解析结果
    cases: List[ApiCase] = []
    # 已出现过的 case_id，用于查重
    seen_ids: Dict[str, int] = {}

    # 逐条解析
    for index, raw_case in enumerate(raw_cases):
        # 用例位置标识，报错时能直接定位到第几条
        location = "cases[{}]".format(index)

        # 用例本身必须是字典
        if not isinstance(raw_case, dict):
            raise YamlCaseError(
                "用例数据错误: {} -> {}: 用例必须是字典，实际为 {}".format(
                    file_path, location, type(raw_case).__name__
                )
            )

        # 取编号，用于拼位置信息
        case_id = raw_case.get("case_id") or ""
        # 编号已经出现在位置标识里，方便直接看出是哪条用例
        location = "cases[{}]{}".format(
            index, " ({})".format(case_id) if case_id else ""
        )

        # 编号查重
        if case_id in seen_ids:
            raise YamlCaseError(
                "用例数据错误: {} -> {}: case_id 重复，与 cases[{}] 冲突".format(
                    file_path, location, seen_ids[case_id]
                )
            )

        # 必填字段校验
        _require(case_id, "case_id", location, file_path)
        _require(raw_case.get("case_name"), "case_name", location, file_path)
        _require(raw_case.get("story"), "story", location, file_path)

        # expect_status 必填，且必须是整数
        expect_status = raw_case.get("expect_status")
        if expect_status is None:
            raise YamlCaseError(
                "用例数据错误: {} -> {}: expect_status 缺失".format(file_path, location)
            )
        if not isinstance(expect_status, int) or isinstance(expect_status, bool):
            raise YamlCaseError(
                "用例数据错误: {} -> {}: expect_status 必须是整数，实际为 {}".format(
                    file_path, location, expect_status
                )
            )

        # 用例级 method 覆盖文件级，未配置时沿用文件级
        case_method = raw_case.get("method") or file_method
        # method 合法性校验
        if str(case_method).upper() not in ALLOWED_METHODS:
            raise YamlCaseError(
                "用例数据错误: {} -> {}: method 非法，实际为 {}".format(
                    file_path, location, case_method
                )
            )

        # 用例级 path 覆盖文件级
        case_path = raw_case.get("path") or file_path_value

        # 用例级 headers 覆盖文件级 headers（整体替换，不做深合并）
        case_headers = raw_case.get("headers")
        if case_headers is None:
            case_headers = file_headers

        # 组装用例对象
        case = ApiCase(
            case_id=case_id,
            case_name=raw_case.get("case_name"),
            story=raw_case.get("story"),
            method=str(case_method).upper(),
            path=case_path,
            base_url=raw_case.get("base_url") or file_base_url,
            headers=dict(case_headers),
            json_body=raw_case.get("json_body"),
            raw_body=raw_case.get("raw_body"),
            expect_status=expect_status,
            expect_message=raw_case.get("expect_message"),
            expect_json=dict(raw_case.get("expect_json") or {}),
            skip=bool(raw_case.get("skip")),
            skip_reason=raw_case.get("skip_reason") or "",
            repeat=int(raw_case.get("repeat") or 1),
            module=file_module,
            interface=file_interface,
            name=file_name,
        )

        # 记录编号，供后续查重
        seen_ids[case_id] = index
        # 加入结果
        cases.append(case)

    # 返回解析后的用例列表
    return cases


def load_cases(
    path: Any,
    case_ids: Optional[List[str]] = None,
    variables: Optional[Dict[str, str]] = None,
) -> List[ApiCase]:
    """加载用例，支持按 case_id 过滤。

    :param path: YAML 文件路径
    :param case_ids: 需要保留的 case_id 列表，传 None 表示全部保留
    :param variables: 变量表，用于 ${VAR} 替换
    :return: 用例列表
    :raises YamlCaseError: 文件解析失败，或指定的 case_id 不存在
    """
    # 先解析全部用例
    cases = parse_file(path, variables)

    # 不需要过滤时直接返回
    if case_ids is None:
        return cases

    # 需要保留的编号集合
    wanted = set(case_ids)
    # 实际存在的编号集合
    existing = {case.case_id for case in cases}
    # 指定的编号里有不存在的，直接报错，避免用例被静默跳过
    missing = wanted - existing
    if missing:
        raise YamlCaseError(
            "用例数据错误: {}: 指定的 case_id 不存在: {}".format(
                Path(path), ", ".join(sorted(missing))
            )
        )

    # 按指定编号过滤，顺序保持与文件中一致
    return [case for case in cases if case.case_id in wanted]
