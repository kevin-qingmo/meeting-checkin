"""量一下弱网优化前后的首屏体积对比（本地测量）。

用法：
    py -3 tools/measure_firstpaint.py
"""
import gzip
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import Activity, User  # noqa: E402

STATIC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "app", "static")


def kb(n):
    return "{:.1f} KB".format(n / 1024)


def main():
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SECRET_KEY": "test-secret",
    })
    with app.app_context():
        db.create_all()
        admin = User(username="admin", display_name="教务主任", role="super")
        admin.set_password("admin123456")
        db.session.add(admin)
        db.session.commit()
        now = datetime.now()
        act = Activity(
            title="小学语文骨干研修班研修活动",
            campus_ids='["敬慧路校区"]',
            stage_ids='["初中"]',
            subject_ids='["语文"]',
            start_at=now - timedelta(hours=1),
            end_at=now + timedelta(hours=3),
            location="和慧南路校区 报告厅",
            need_checkout=True,
            owner_id=admin.id,
        )
        db.session.add(act)
        db.session.commit()
        act_id = act.id

    client = app.test_client()
    with client.session_transaction() as sess:
        sess["_user_id"] = "1"

    print("【优化前】旧版首屏需要 4 个独立请求（每次都要一次 TCP+TLS 握手）：")
    old = 0
    for rel in ("css/app.css", "img_school_logo.png", "css/board.css", "js/board.js"):
        p = os.path.join(STATIC, rel.replace("/", os.sep))
        if os.path.exists(p):
            old += os.path.getsize(p)
            print("  - {}  {}".format(rel, kb(os.path.getsize(p))))
    print("  合计 {}（4 次握手）".format(kb(old)))

    print()
    print("【优化后】每个页面只有 1 个请求（HTML 本身，gzip 后传输）：")
    for path in ("/login", "/board/{}".format(act_id), "/scan/{}".format(act_id)):
        resp = client.get(path)
        raw = resp.get_data()
        gz = gzip.compress(raw, 6)
        print("  {:14s} 原始 {} -> gzip {}（压缩率 {:.0%}）".format(
            path, kb(len(raw)), kb(len(gz)),
            (1 - len(gz) / len(raw)) if raw else 0))


if __name__ == "__main__":
    main()
