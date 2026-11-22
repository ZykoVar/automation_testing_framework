# -*- coding: utf-8 -*-
"""
day10 / utils / excel_loader.py
pip install openpyxl    安装openpyxl库

Excel 驱动的接口用例数据加载器。

与 yaml_loader 的分工：
    yaml_loader  —— 加载 YAML 格式的用例数据，返回 List[ApiCase]
    excel_loader —— 加载 Excel 格式的用例数据，同样返回 List[ApiCase]
    两者产出的对象结构完全一致，测试函数可以无缝切换数据源。

Excel 的列名与 YAML 的字段一一对应：
    case_id        用例编号
    case_name      用例名称
    story          所属场景
    method         HTTP 方法
    path           接口路径
    base_url       服务基础地址
    headers        请求头（JSON 字符串）
    json_body      请求体（JSON 字符串）
    raw_body       原始请求体
    expect_status  期望状态码
    expect_message 期望 message 关键字
    expect_json    期望字段（JSON 字符串）
    skip           是否跳过
    skip_reason    跳过原因
    repeat         重复次数

用法：
    python day10/utils/excel_loader.py
"""

# 标准库：类型注解
from typing import Any, Dict, List, Optional

# 标准库：路径处理
from pathlib import Path

# 标准库：JSON 解析
import json

# 标准库：模块搜索路径
import sys

# 第三方库：openpyxl，读取 Excel
from openpyxl import load_workbook

# 本项目的 YAML 加载器。直接复用它的 ApiCase 数据类与校验逻辑
try:
    from utils.yaml_loader import ApiCase, YamlCaseError, jsonpath_get
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    # 直接执行本文件时（python utils/excel_loader.py），
    # sys.path[0] 是 utils 目录，父级的 day10 不在其中，顶层导入会失败。
    # 这里把 day10 目录补进 sys.path 再试一次
    _day10_dir = str(Path(__file__).resolve().parent.parent)
    if _day10_dir not in sys.path:
        sys.path.insert(0, _day10_dir)
    from utils.yaml_loader import ApiCase, YamlCaseError, jsonpath_get


# ============================================================================
# 1. 常量
# ============================================================================

# Excel 的表头行。缺任意一列都会在加载期报错
HEADERS = [
    "case_id",
    "case_name",
    "story",
    "method",
    "path",
    "base_url",
    "headers",
    "json_body",
    "raw_body",
    "expect_status",
    "expect_message",
    "expect_json",
    "skip",
    "skip_reason",
    "repeat",
]

# 允许出现在用例里的 HTTP 方法
ALLOWED_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")


# ============================================================================
# 2. 单元格取值
# ============================================================================

def _cell_text(value: Any) -> str:
    """把单元格值转成去除首尾空白的字符串。

    :param value: 单元格原始值
    :return: 字符串，空值返回空串
    """
    if value is None:
        return ""
    return str(value).strip()


def _parse_json_cell(value: str, field_name: str, location: str, file_path: Path) -> Any:
    """解析 JSON 格式的单元格。

    :param value: 单元格文本
    :param field_name: 字段名，用于报错信息
    :param location: 用例位置
    :param file_path: 文件路径
    :return: 解析后的对象；单元格为空时返回 None
    """
    # 空单元格直接返回 None
    if not value:
        return None
    try:
        return json.loads(value)
    except ValueError as error:
        raise YamlCaseError(
            "用例数据错误: {} -> {}: {} 不是合法 JSON: {}".format(
                file_path, location, field_name, error
            )
        ) from error


def _parse_bool_cell(value: str) -> bool:
    """把单元格值转成布尔值。

    兼容 true/True/1/yes 等写法。

    :param value: 单元格文本
    :return: 布尔值
    """
    return value.lower() in ("true", "1", "yes", "y", "是")


def _parse_int_cell(value: str, field_name: str, location: str, file_path: Path) -> Optional[int]:
    """把单元格值转成整数。

    :param value: 单元格文本
    :param field_name: 字段名
    :param location: 用例位置
    :param file_path: 文件路径
    :return: 整数；单元格为空时返回 None
    :raises YamlCaseError: 不是合法整数
    """
    # 空单元格返回 None
    if not value:
        return None
    try:
        return int(value)
    except ValueError as error:
        raise YamlCaseError(
            "用例数据错误: {} -> {}: {} 必须是整数，实际为 {}".format(
                file_path, location, field_name, value
            )
        ) from error


# ============================================================================
# 3. 加载与解析
# ============================================================================

def load_excel_file(path: Any) -> List[Dict[str, Any]]:
    """读取 Excel 文件，返回以字典表示的原始行。

    :param path: Excel 文件路径
    :return: 行字典列表，每行是一个用例的原始字段
    :raises YamlCaseError: 文件不存在、工作表缺失或表头不完整
    """
    # 统一转成 Path
    file_path = Path(path)
    # 文件不存在时给出带文件名的清晰提示
    if not file_path.is_file():
        raise YamlCaseError("Excel 用例文件不存在: {}".format(file_path))

    try:
        # 只读模式打开，避免大文件占用过多内存
        workbook = load_workbook(file_path, read_only=True, data_only=True)
    except Exception as error:
        raise YamlCaseError(
            "Excel 文件读取失败: {}: {}".format(file_path, error)
        ) from error

    try:
        # 取第一个工作表
        sheet = workbook.active
        if sheet is None:
            raise YamlCaseError("Excel 文件没有工作表: {}".format(file_path))

        # 读表头。openpyxl 的 iter_rows 从 1 开始
        rows = sheet.iter_rows(values_only=True)
        try:
            header_row = next(rows)
        except StopIteration:
            raise YamlCaseError("Excel 文件为空: {}".format(file_path))

        # 表头转成小写去空白，匹配时更宽松
        header_names = [
            str(name).strip().lower() if name is not None else ""
            for name in header_row
        ]

        # 校验必需的列是否齐全
        missing = [name for name in ("case_id", "case_name", "expect_status") if name not in header_names]
        if missing:
            raise YamlCaseError(
                "Excel 文件缺少必需的列: {}: {}".format(file_path, ", ".join(missing))
            )

        # 逐行组装字典。空行直接跳过
        result = []
        for row_index, row in enumerate(rows, start=2):
            # 全空行跳过
            if not any(_cell_text(cell) for cell in row):
                continue
            # 按表头位置组装字典
            item = {}
            for column_index, name in enumerate(header_names):
                if not name:
                    continue
                cell_value = row[column_index] if column_index < len(row) else None
                item[name] = cell_value
            item["__row__"] = row_index
            result.append(item)

        return result
    finally:
        # 只读模式也要显式关闭，释放文件句柄
        workbook.close()


def parse_excel_file(path: Any) -> List[ApiCase]:
    """解析 Excel 文件，返回用例列表。

    :param path: Excel 文件路径
    :return: ApiCase 列表
    :raises YamlCaseError: 文件解析失败或数据有误
    """
    # 文件路径
    file_path = Path(path)
    # 读取原始行
    raw_rows = load_excel_file(file_path)

    # 结果列表
    cases: List[ApiCase] = []
    # 已出现过的 case_id，用于查重
    seen_ids: Dict[str, int] = {}

    for index, row in enumerate(raw_rows):
        # 用例位置标识，报错时能直接定位到第几条
        location = "rows[{}] (行{})".format(index, row.get("__row__", "?"))

        # 取编号
        case_id = _cell_text(row.get("case_id"))
        # 编号为空说明这行没有有效数据
        if not case_id:
            continue
        # 编号查重
        if case_id in seen_ids:
            raise YamlCaseError(
                "用例数据错误: {} -> {}: case_id 重复，与 rows[{}] 冲突".format(
                    file_path, location, seen_ids[case_id]
                )
            )

        # 取必填字段
        case_name = _cell_text(row.get("case_name"))
        if not case_name:
            raise YamlCaseError(
                "用例数据错误: {} -> {}: case_name 缺失".format(file_path, location)
            )

        story = _cell_text(row.get("story")) or "未分类"

        # method 合法性校验
        method = (_cell_text(row.get("method")) or "GET").upper()
        if method not in ALLOWED_METHODS:
            raise YamlCaseError(
                "用例数据错误: {} -> {}: method 非法，实际为 {}".format(
                    file_path, location, method
                )
            )

        # path 必填
        path_value = _cell_text(row.get("path"))
        if not path_value:
            raise YamlCaseError(
                "用例数据错误: {} -> {}: path 缺失".format(file_path, location)
            )

        # expect_status 必填且必须是整数
        expect_status = _parse_int_cell(
            _cell_text(row.get("expect_status")), "expect_status", location, file_path
        )
        if expect_status is None:
            raise YamlCaseError(
                "用例数据错误: {} -> {}: expect_status 缺失".format(file_path, location)
            )

        # 组装用例对象
        case = ApiCase(
            case_id=case_id,
            case_name=case_name,
            story=story,
            method=method,
            path=path_value,
            base_url=_cell_text(row.get("base_url")),
            headers=_parse_json_cell(
                _cell_text(row.get("headers")), "headers", location, file_path
            ) or {},
            json_body=_parse_json_cell(
                _cell_text(row.get("json_body")), "json_body", location, file_path
            ),
            raw_body=_cell_text(row.get("raw_body")) or None,
            expect_status=expect_status,
            expect_message=_cell_text(row.get("expect_message")) or None,
            expect_json=_parse_json_cell(
                _cell_text(row.get("expect_json")), "expect_json", location, file_path
            ) or {},
            skip=_parse_bool_cell(_cell_text(row.get("skip"))),
            skip_reason=_cell_text(row.get("skip_reason")),
            repeat=_parse_int_cell(
                _cell_text(row.get("repeat")), "repeat", location, file_path
            ) or 1,
        )

        # 记录编号，供后续查重
        seen_ids[case_id] = index
        # 加入结果
        cases.append(case)

    return cases


def load_cases(
    path: Any,
    case_ids: Optional[List[str]] = None,
) -> List[ApiCase]:
    """加载 Excel 用例，支持按 case_id 过滤。

    :param path: Excel 文件路径
    :param case_ids: 需要保留的 case_id 列表，传 None 表示全部保留
    :return: 用例列表
    :raises YamlCaseError: 文件解析失败，或指定的 case_id 不存在
    """
    # 先解析全部用例
    cases = parse_excel_file(path)

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


if __name__ == "__main__":
    # 自检：默认加载 create_subject.xlsx 并打印用例列表
    import sys
    _day10_dir = str(Path(__file__).resolve().parent.parent)
    if _day10_dir not in sys.path:
        sys.path.insert(0, _day10_dir)
    _excel = Path(_day10_dir) / "data" / "excel_data" / "create_subject.xlsx"
    _cases = load_cases(_excel)
    print("共 {} 条用例".format(len(_cases)))
    for _case in _cases:
        print("  {} | {} | {}".format(_case.case_id, _case.case_name, _case.expect_status))
