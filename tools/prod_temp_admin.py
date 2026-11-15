"""直连生产数据库创建/删除临时验收账号（不改动用户自己的管理员密码）。

用法（需在带 DATABASE_URL 的环境下执行，例如 `railway run --service web ...`）：
    python tools/prod_temp_admin.py create <用户名> <密码>
    python tools/prod_temp_admin.py delete <用户名>
"""
import os
import sys

import psycopg
from werkzeug.security import generate_password_hash


def conn():
    url = os.environ.get("DATABASE_URL", "")
    if url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql://", 1)
    if not url:
        raise SystemExit("缺少 DATABASE_URL 环境变量")
    return psycopg.connect(url)


def create(user, pwd):
    with conn() as c, c.cursor() as cur:
        cur.execute("SELECT id FROM users WHERE username=%s", (user,))
        if cur.fetchone():
            cur.execute("UPDATE users SET password_hash=%s WHERE username=%s",
                        (generate_password_hash(pwd), user))
            print("[ok] 已重置临时账号密码:", user)
            return
        cur.execute(
            "INSERT INTO users (username, password_hash, display_name, role, active, created_at) "
            "VALUES (%s,%s,%s,'super',true,now())",
            (user, generate_password_hash(pwd), "临时验收账号"),
        )
        print("[ok] 已创建临时账号:", user)


def delete(user):
    with conn() as c, c.cursor() as cur:
        cur.execute("DELETE FROM users WHERE username=%s", (user,))
        print("[ok] 已删除临时账号:", user, "影响行数", cur.rowcount)


if __name__ == "__main__":
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action == "create" and len(sys.argv) >= 4:
        create(sys.argv[2], sys.argv[3])
    elif action == "delete" and len(sys.argv) >= 3:
        delete(sys.argv[2])
    else:
        raise SystemExit(__doc__)
