"""更新某个账号的显示名（本地 SQLite 或生产 Postgres 均可）。

用法：
    python tools/set_display_name.py <用户名> <显示名>
生产库需先设置 DATABASE_URL（SSH 隧道）再执行。
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import User  # noqa: E402


def run(username, display_name):
    app = create_app()
    with app.app_context():
        u = User.query.filter_by(username=username).first()
        if u is None:
            print("[err] 账号不存在:", username)
            return
        u.display_name = display_name
        db.session.commit()
        print("[ok] 已更新 {} → {}".format(username, display_name))
        for row in User.query.order_by(User.id).all():
            print("   ", row.id, row.username, row.display_name, row.role, row.active)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    run(sys.argv[1], sys.argv[2])
