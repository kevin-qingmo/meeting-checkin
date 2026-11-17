"""生成演示数据：活动 + 名册 + 若干签到记录，便于本地预览大屏效果。

用法：python tools/demo_data.py
"""
import os
import random
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Activity, CheckIn, Roster, User  # noqa: E402

PEOPLE = [
    ("费敏尧", "八里台实验小学"), ("朱呈怡", "咸水沽三小"), ("王辰晨", "高庄子小学"),
    ("王云", "小站实验小学"), ("宋倩", "南开学校瑞明路"), ("张俊", "咸水沽五小"),
    ("田洪宇", "双港小学"), ("曹磊", "津南实验小学"), ("于洋", "紫港实验小学"),
    ("李想", "咸水沽实验小学"),
]


def run():
    app = create_app()
    with app.app_context():
        db.create_all()
        owner = User.query.filter_by(username="admin").first()
        if owner is None:
            owner = User(username="admin", display_name="创建者", role="super")
            owner.set_password("admin123456")
            db.session.add(owner)
            db.session.commit()

        now = datetime.now()
        act = Activity(
            title="小学语文骨干研修班研修活动",
            campus_ids='["敬慧路校区", "雅馨路校区", "和慧南路校区"]',
            stage_ids='["初中"]',
            subject_ids='["语文"]',
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=3),
            location="和慧南路校区 报告厅",
            need_checkout=True,
            owner_id=owner.id,
        )
        db.session.add(act)
        db.session.commit()

        for name, campus in PEOPLE:
            db.session.add(Roster(activity_id=act.id, name=name, campus=campus,
                                  phone="138{:08d}".format(random.randint(0, 99999999)),
                                  stage="初中", subject="语文"))

        for i, (name, campus) in enumerate(PEOPLE):
            checked_in = now - timedelta(minutes=40 - i * 2)
            rec = CheckIn(activity_id=act.id, name=name,
                          phone="138{:08d}".format(13800000000 + i),
                          campus=campus, code_used="{:04d}".format(random.randint(0, 9999)),
                          mode="in", source="scan", checked_in_at=checked_in)
            if i % 3 == 0:
                rec.checked_out_at = checked_in + timedelta(minutes=5)
            db.session.add(rec)

        db.session.commit()
        print("[demo] 活动 ID = {}，可访问 /board/{}".format(act.id, act.id))


if __name__ == "__main__":
    run()
