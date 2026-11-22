# -*- coding: utf-8 -*-
"""
day10 / utils / yaml_excel_generator.py
pip install openpyxl    安装openpyxl库

YAML 反向生成 Excel：把 YAML 用例数据导出成 Excel 表格。

用途：
    1. 团队里不写 YAML 的人也能维护用例数据；
    2. 用 Excel 做用例评审，评审完再导回 YAML；
    3. 对外交付用例清单。

用法：
    python day10/utils/yaml_excel_generator.py
    python day10/utils/yaml_excel_generator.py data/yaml_data/login.yaml
    python day10/utils/yaml_excel_generator.py data/yaml_data/login.yaml -o output.xlsx
"""

# 标准库：类型注解
from typing import Any, Dict, List, Optional

# 标准库：路径处理
from pathlib import Path

# 标准库：JSON 序列化
import json

# 标准库：命令行参数
import argparse

# 标准库：模块搜索路径
import sys

# 第三方库：openpyxl，写 Excel
from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# 本项目的 YAML 加载器。直接复用它的解析逻辑
try:
    from utils.yaml_loader import parse_file
except ImportError:  # pragma: no cover - 依赖运行环境，走兜底分支
    # 直接执行本文件时（python utils/yaml_excel_generator.py），
    # sys.path[0] 是 utils 目录，父级的 day10 不在其中，顶层导入会失败。
    # 这里把 day10 目录补进 sys.path 再试一次
    _day10_dir = str(Path(__file__).resolve().parent.parent)
    if _day10_dir not in sys.path:
        sys.path.insert(0, _day10_dir)
    from utils.yaml_loader import parse_file


# ============================================================================
# 1. 样式常量
# ============================================================================

# 表头填色
HEADER_FILL = PatternFill("solid", start_color="1F3864")
# 表头字体
HEADER_FONT = Font(name="Arial", bold=True, color="FFFFFF", size=10)
# 数据行字体
BODY_FONT = Font(name="Arial", size=10)
# 隔行填色
ZEBRA_FILL = PatternFill("solid", start_color="F7F9FC")
# 边框
THIN = Side(style="thin", color="D9DEE7")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)

# Excel 的列顺序。与 excel_loader.HEADERS 保持一致
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

# 各列的显示宽度
COLUMN_WIDTHS = [16, 30, 18, 10, 34, 26, 30, 40, 24, 14, 22, 30, 8, 20, 8]


# ============================================================================
# 2. 数据转换
# ============================================================================

def _to_json_text(value: Any) -> str:
    """把对象转成 Excel 单元格里的 JSON 文本。

    :param value: 任意对象
    :return: JSON 字符串；值为 None 时返回空串
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False)


def case_to_row(case) -> List[Any]:
    """把一条 ApiCase 转成 Excel 的一行。

    :param case: ApiCase 对象
    :return: 与 HEADERS 顺序一致的列表
    """
    return [
        case.case_id,
        case.case_name,
        case.story,
        case.method,
        case.path,
        case.base_url,
        _to_json_text(case.headers) if case.headers else "",
        _to_json_text(case.json_body) if case.json_body is not None else "",
        case.raw_body or "",
        case.expect_status,
        case.expect_message or "",
        _to_json_text(case.expect_json) if case.expect_json else "",
        "true" if case.skip else "false",
        case.skip_reason,
        case.repeat,
    ]


# ============================================================================
# 3. 生成 Excel
# ============================================================================

def generate_xlsx(yaml_path: Any, output_path: Any) -> str:
    """把 YAML 用例数据导出成 Excel。

    :param yaml_path: YAML 文件路径
    :param output_path: 输出的 Excel 文件路径
    :return: 输出文件路径
    """
    # 解析 YAML。复用 yaml_loader 的解析逻辑，保证字段口径一致
    cases = parse_file(yaml_path)

    # 创建工作簿
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "用例数据"

    # 写表头
    sheet.append(HEADERS)

    # 写数据行
    for case in cases:
        sheet.append(case_to_row(case))

    # 表头样式
    for column_index in range(1, len(HEADERS) + 1):
        cell = sheet.cell(1, column_index)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
        cell.border = BORDER
    sheet.row_dimensions[1].height = 24

    # 数据行样式。隔行填色提升可读性
    for row_index in range(2, sheet.max_row + 1):
        for column_index in range(1, len(HEADERS) + 1):
            cell = sheet.cell(row_index, column_index)
            cell.font = BODY_FONT
            cell.alignment = Alignment(vertical="top", wrap_text=True)
            cell.border = BORDER
            if row_index % 2 == 0:
                cell.fill = ZEBRA_FILL
        sheet.row_dimensions[row_index].height = 40

    # 设置列宽
    for column_index, width in enumerate(COLUMN_WIDTHS, start=1):
        sheet.column_dimensions[get_column_letter(column_index)].width = width

    # 冻结表头并开启筛选，方便查阅
    sheet.freeze_panes = "A2"
    sheet.auto_filter.ref = "A1:{}".format(
        get_column_letter(len(HEADERS))
    ) + str(sheet.max_row)

    # 确保输出目录存在
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    # 写盘
    workbook.save(output)

    return str(output)


def main() -> int:
    """命令行入口。

    :return: 退出码，0 表示成功
    """
    # 解析命令行参数
    parser = argparse.ArgumentParser(description="把 YAML 用例数据导出成 Excel")
    parser.add_argument(
        "yaml", nargs="?", default=None,
        help="YAML 用例数据文件路径，默认取 data/yaml_data/login.yaml",
    )
    parser.add_argument(
        "-o", "--output", default=None,
        help="输出 Excel 路径，默认与 YAML 同名但扩展名为 .xlsx",
    )
    args = parser.parse_args()

    # 确定 day10 目录。本文件在 day10/utils/ 下，上溯一级即为 day10
    day10_dir = Path(__file__).resolve().parent.parent

    # YAML 路径。命令行没给就用默认的 login.yaml
    yaml_path = Path(args.yaml) if args.yaml else day10_dir / "data" / "yaml_data" / "login.yaml"

    # 输出路径。命令行没给就与 YAML 同名
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = yaml_path.with_suffix(".xlsx")

    # 生成
    try:
        saved = generate_xlsx(yaml_path, output_path)
    except Exception as error:
        print("生成失败: {}".format(error))
        return 1

    print("已生成: {}".format(saved))
    return 0


if __name__ == "__main__":
    sys.exit(main())
