# -*- coding: utf-8 -*-
"""Generate an interface test case workbook from a JSON spec.

Usage:
    python generate_xlsx.py <cases.json> -o <output.xlsx>

Writes three sheets: 用例清单表, P0P1用例详情卡, 待确认项清单.
The JSON structure is documented in ../references/spec.md.
"""
import argparse
import json
import sys

from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

HEADERS = ["用例编号", "所属模块", "用例标题", "优先级", "前置条件",
           "请求方式", "请求参数", "执行步骤", "预期结果"]

DETAIL_FIELDS = ["用例编号", "所属模块", "用例标题", "优先级", "前置条件",
                 "请求方式", "请求参数", "执行步骤", "预期结果", "备注"]

THIN = Side(style="thin", color="D9DEE7")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)
FT = "Arial"
HDR_FILL = PatternFill("solid", start_color="1F3864")
HDR_FONT = Font(name=FT, bold=True, color="FFFFFF", size=10)
Z1 = PatternFill("solid", start_color="FFFFFF")
Z2 = PatternFill("solid", start_color="F7F9FC")
P0_FILL = PatternFill("solid", start_color="EAF2FF")
PRI_FONT = {
    "P0": Font(name=FT, bold=True, color="C00000", size=10),
    "P1": Font(name=FT, bold=True, color="1F3864", size=10),
    "P2": Font(name=FT, color="404040", size=10),
    "P3": Font(name=FT, color="808080", size=10),
}


def build_expected(case):
    return ("1. 接口返回：" + case["expected_return"] + "\n"
            "2. 数据落库：" + case["expected_db"] + "\n"
            "3. 安全与日志：" + case["expected_security"])


def style_header(ws, ncols, height=26):
    for c in range(1, ncols + 1):
        cell = ws.cell(1, c)
        cell.fill = HDR_FILL
        cell.font = HDR_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
        cell.border = BORDER
    ws.row_dimensions[1].height = height


def build_list_sheet(wb, meta, cases):
    ws = wb.active
    ws.title = "用例清单表"
    ws.append(HEADERS)
    for case in cases:
        ws.append([
            case["id"], meta["module"], case["title"], case["priority"],
            case["precondition"], case.get("method", meta["api"]),
            case["params"], "\n".join(case["steps"]), build_expected(case),
        ])
    style_header(ws, len(HEADERS))

    for r in range(2, ws.max_row + 1):
        for c in range(1, len(HEADERS) + 1):
            cell = ws.cell(r, c)
            cell.font = Font(name=FT, size=10)
            cell.alignment = Alignment(vertical="top", wrap_text=True,
                                       horizontal="center" if c in (1, 2, 4, 6) else "left")
            cell.border = BORDER
            cell.fill = Z1 if r % 2 == 0 else Z2
        pc = ws.cell(r, 4)
        pc.font = PRI_FONT.get(pc.value, Font(name=FT, size=10))
        pc.alignment = Alignment(horizontal="center", vertical="center")
        if pc.value == "P0":
            pc.fill = P0_FILL
        ws.row_dimensions[r].height = 150

    for col, w in zip("ABCDEFGHI", [18, 11, 30, 8, 34, 20, 40, 60, 76]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "C2"
    ws.auto_filter.ref = "A1:I%d" % ws.max_row
    return ws


def build_detail_sheet(wb, meta, cases):
    ws = wb.create_sheet("P0P1用例详情卡")
    ws.append(["字段"] + DETAIL_FIELDS)
    style_header(ws, len(DETAIL_FIELDS) + 1)

    targets = [c for c in cases if c["priority"] in ("P0", "P1")]
    row = 2
    for idx, case in enumerate(targets):
        block_start = row
        values = {
            "用例编号": case["id"],
            "所属模块": meta["module"],
            "用例标题": case["title"],
            "优先级": case["priority"],
            "前置条件": case["precondition"],
            "请求方式": case.get("method", meta["api"]),
            "请求参数": case["params"],
            "执行步骤": "\n".join(case["steps"]),
            "预期结果": build_expected(case),
            "备注": case.get("note", "—"),
        }
        for i, key in enumerate(DETAIL_FIELDS):
            ws.cell(row, i + 2, values[key])
        row += 11

        for r in range(block_start, block_start + 10):
            for c in range(1, len(DETAIL_FIELDS) + 2):
                cell = ws.cell(r, c)
                cell.border = BORDER
                cell.font = Font(name=FT, size=10)
                cell.alignment = Alignment(vertical="top", wrap_text=True)
                if c == 1:
                    cell.fill = PatternFill("solid", start_color="EDF1F8")
                    cell.font = Font(name=FT, bold=True, size=10, color="1F3864")
                    cell.alignment = Alignment(horizontal="center", vertical="center")
                else:
                    cell.fill = Z1 if idx % 2 == 0 else Z2
            if r not in (block_start, block_start + 3):
                ws.row_dimensions[r].height = 118
        ws.row_dimensions[block_start].height = 20

        pc = ws.cell(block_start + 3, 5)
        pc.font = PRI_FONT.get(pc.value, Font(name=FT, size=10))
        pc.alignment = Alignment(horizontal="center", vertical="center")

        ws.cell(block_start + 10, 2,
                "用例详情卡 %d / %d：%s" % (idx + 1, len(targets), case["id"]))
        ws.cell(block_start + 10, 2).font = Font(name=FT, italic=True, size=9, color="7F7F7F")

    ws.column_dimensions["A"].width = 13
    for col, w in zip("BCDEFGHIJK", [12, 30, 8, 34, 20, 40, 60, 76, 44]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "B2"
    return ws


def build_pending_sheet(wb, pending):
    if not pending:
        return None
    ws = wb.create_sheet("待确认项清单")
    ws.append(["序号", "所属用例编号", "类别", "需确认内容", "说明与影响"])
    for i, item in enumerate(pending, 1):
        ws.append([i, item.get("case_id", ""), item.get("category", ""),
                   item["item"], item.get("impact", "")])
    style_header(ws, 5)

    for r in range(2, ws.max_row + 1):
        for c in range(1, 6):
            cell = ws.cell(r, c)
            cell.font = Font(name=FT, size=10)
            cell.alignment = Alignment(vertical="top", wrap_text=True,
                                       horizontal="center" if c == 1 else "left")
            cell.border = BORDER
            cell.fill = Z1 if r % 2 == 0 else Z2
        ws.cell(r, 4).font = Font(name=FT, bold=True, size=10, color="C00000")
        ws.row_dimensions[r].height = 34

    for col, w in zip("ABCDE", [6, 18, 12, 40, 58]):
        ws.column_dimensions[col].width = w
    ws.freeze_panes = "A2"
    return ws


def validate(meta, cases):
    errors = []
    if not meta.get("module"):
        errors.append("meta.module is required")
    if not meta.get("api"):
        errors.append("meta.api is required")
    seen = set()
    for i, case in enumerate(cases):
        cid = case.get("id", "<missing id at index %d>" % i)
        if not cid:
            errors.append("case at index %d has no id" % i)
        if cid in seen:
            errors.append("duplicate case id: %s" % cid)
        seen.add(cid)
        if case.get("priority") not in ("P0", "P1", "P2", "P3"):
            errors.append("%s has invalid priority: %r" % (cid, case.get("priority")))
        for key in ("title", "precondition", "params", "steps",
                    "expected_return", "expected_db", "expected_security"):
            if not case.get(key):
                errors.append("%s is missing %s" % (cid, key))
    return errors


def main():
    ap = argparse.ArgumentParser(description="Generate interface test case workbook")
    ap.add_argument("spec", help="path to the JSON spec file")
    ap.add_argument("-o", "--output", required=True, help="output xlsx path")
    args = ap.parse_args()

    with open(args.spec, encoding="utf-8") as f:
        data = json.load(f)

    meta = data.get("meta", {})
    cases = data.get("cases", [])
    if not cases:
        print("error: spec contains no cases", file=sys.stderr)
        return 1

    errors = validate(meta, cases)
    if errors:
        print("spec validation failed:", file=sys.stderr)
        for e in errors:
            print("  - " + e, file=sys.stderr)
        return 1

    wb = Workbook()
    build_list_sheet(wb, meta, cases)
    build_detail_sheet(wb, meta, cases)
    build_pending_sheet(wb, data.get("pending", []))
    wb.save(args.output)

    p0 = sum(1 for c in cases if c["priority"] == "P0")
    p1 = sum(1 for c in cases if c["priority"] == "P1")
    print("saved: %s" % args.output)
    print("cases: %d  P0: %d  P1: %d  detail_cards: %d  pending: %d"
          % (len(cases), p0, p1, p0 + p1, len(data.get("pending", []))))
    return 0


if __name__ == "__main__":
    sys.exit(main())