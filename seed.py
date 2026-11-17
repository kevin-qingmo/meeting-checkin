"""初始化数据库：创建「创建者」账号与预置字典。"""
import os

from app import create_app
from app.extensions import db
from app.models import CAMPUSES, STAGES, SUBJECTS, Setting, User


def run():
    app = create_app()
    with app.app_context():
        db.create_all()

        if not User.query.filter_by(username="admin").first():
            password = os.environ.get("ADMIN_PASSWORD", "admin123456")
            u = User(username="admin", display_name="吴洪凯", role="super")
            u.set_password(password)
            db.session.add(u)
            db.session.commit()
            print("[seed] 已创建创建者账号 admin（吴洪凯）/ {}".format(password))
        else:
            print("[seed] 创建者账号已存在，跳过")

        for key, items in (("campuses", CAMPUSES), ("stages", STAGES), ("subjects", SUBJECTS)):
            if not Setting.list_of(key):
                Setting.set_list(key, items)
                db.session.commit()
                print("[seed] 已写入{}字典（{} 项）".format(key, len(items)))
    print("[seed] 完成")


if __name__ == "__main__":
    run()
