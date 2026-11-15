"""导出签到表（Excel 三工作表）。"""
from datetime import datetime

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill

from .access import activity_stats

HEADER_FILL = PatternFill("solid", fgColor="265171")
HEADER_FONT = Font(color="FFFFFF", bold=True)


def _style_header(ws, headers):
    ws.append(headers)
    for cell in ws[1]:
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.alignment = Alignment(horizontal="center", vertical="center")
    ws.freeze_panes = "A2"


def _fmt(value):
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    return value


def build_workbook(activity):
    stats = activity_stats(activity)
    wb = Workbook()

    ws = wb.active
    ws.title = "签到明细"
    _style_header(ws, ["姓名", "校区", "手机号", "签到时间", "签离时间", "来源"])
    for r in sorted(stats["records"], key=lambda x: x.checked_in_at or datetime.min):
        ws.append([
            r.name,
            r.campus,
            r.phone or "",
            _fmt(r.checked_in_at),
            _fmt(r.checked_out_at) if r.checked_out_at else "",
            "补录" if r.source == "manual" else "扫码",
        ])
    for col, width in zip("ABCDEF", (16, 18, 16, 22, 22, 10)):
        ws.column_dimensions[col].width = width

    ws2 = wb.create_sheet("应到实到统计")
    _style_header(ws2, ["项目", "数值"])
    ws2.append(["活动名称", activity.title])
    ws2.append(["开始时间", _fmt(activity.start_at)])
    ws2.append(["结束时间", _fmt(activity.end_at)])
    ws2.append(["活动地点", activity.location or ""])
    ws2.append(["应到人数", stats["expected"]])
    ws2.append(["实到人数", stats["checked_in"]])
    ws2.append(["已签离人数", stats["checked_out"]])
    ws2.append(["缺席人数", len(stats["absent"])])
    ws2.column_dimensions["A"].width = 18
    ws2.column_dimensions["B"].width = 32

    ws3 = wb.create_sheet("缺席名单")
    _style_header(ws3, ["姓名", "校区", "手机号", "学段", "学科"])
    for row in stats["absent"]:
        ws3.append([row.name, row.campus, row.phone or "", row.stage, row.subject])
    for col, width in zip("ABCDE", (16, 18, 16, 12, 12)):
        ws3.column_dimensions[col].width = width

    return wb
