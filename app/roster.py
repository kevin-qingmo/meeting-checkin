"""Excel 名册导入。必填：姓名、校区；可选：手机号、学段、学科。"""
from openpyxl import load_workbook

from .extensions import db
from .models import Roster


def import_roster(activity_id, file_storage):
    """返回 (导入条数, 错误行列表)。错误行格式：第一行视为表头被跳过。"""
    wb = load_workbook(file_storage, data_only=True)
    ws = wb.active
    errors = []
    added = 0
    header_seen = False
    for row in ws.iter_rows(values_only=True):
        if not row or not any(c is not None and str(c).strip() for c in row):
            continue
        cells = ["" if c is None else str(c).strip() for c in row]
        if not header_seen:
            header_seen = True
            first = cells[0]
            if first in ("姓名", "名字", "name", "Name", "NAME"):
                continue
        name = cells[0] if cells else ""
        campus = cells[1] if len(cells) > 1 else ""
        if not name or not campus:
            errors.append(" / ".join([c for c in cells[:2] if c]) or "(空行)")
            continue
        phone = cells[2] if len(cells) > 2 else ""
        stage = cells[3] if len(cells) > 3 else ""
        subject = cells[4] if len(cells) > 4 else ""
        db.session.add(
            Roster(
                activity_id=activity_id,
                name=name,
                campus=campus,
                phone=phone,
                stage=stage,
                subject=subject,
            )
        )
        added += 1
    db.session.commit()
    return added, errors
