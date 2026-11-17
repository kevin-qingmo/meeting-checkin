import os
import psycopg

c = psycopg.connect(os.environ["DATABASE_URL"])
cur = c.cursor()
cur.execute("select id, title, created_at, owner_id from activities order by id")
print("activities:", cur.fetchall())
cur.execute("select id, activity_id, name, campus, source from checkins order by id")
print("checkins:", cur.fetchall())
