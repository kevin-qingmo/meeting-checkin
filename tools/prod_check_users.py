"""排查生产库账号状态：列出用户，并校验 admin 密码是否仍为初始密码。"""
import os
import sys

import psycopg
from werkzeug.security import check_password_hash

url = os.environ.get("DATABASE_URL", "")
if url.startswith("postgres://"):
    url = url.replace("postgres://", "postgresql://", 1)

CANDIDATES = [
    "mc-80yn1w8bp1",
    "admin123456",
    "TmpVerify#2026",
]

with psycopg.connect(url) as c, c.cursor() as cur:
    cur.execute(
        "SELECT id, username, display_name, role, active, password_hash, created_at "
        "FROM users ORDER BY id"
    )
    for row in cur.fetchall():
        uid, username, display_name, role, active, pwd_hash, created = row
        print("id={} username={} display={} role={} active={} hash_len={} created={}".format(
            uid, username, display_name, role, active, len(pwd_hash or ""), created))
        for cand in CANDIDATES:
            try:
                ok = check_password_hash(pwd_hash or "", cand)
            except Exception:
                ok = False
            if ok:
                print("    -> 密码匹配：{}".format(cand))
    print("--- activities ---")
    cur.execute("SELECT count(*) FROM activities")
    print("活动数:", cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM checkins")
    print("签到记录数:", cur.fetchone()[0])
    cur.execute("SELECT count(*) FROM roster")
    print("名册数:", cur.fetchone()[0])
