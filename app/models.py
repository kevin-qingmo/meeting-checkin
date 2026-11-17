import json
from datetime import datetime

from flask_login import UserMixin
from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

CAMPUSES = [
    {"id": "c1", "name": "敬慧路校区"},
    {"id": "c2", "name": "雅馨路校区"},
    {"id": "c3", "name": "和慧南路校区"},
]

STAGES = [
    {"id": "s1", "name": "小学"},
    {"id": "s2", "name": "初中"},
    {"id": "s3", "name": "高中"},
]

SUBJECTS = [
    {"id": "j1", "name": "语文"},
    {"id": "j2", "name": "数学"},
    {"id": "j3", "name": "英语"},
    {"id": "j4", "name": "物理"},
    {"id": "j5", "name": "化学"},
    {"id": "j6", "name": "道法"},
    {"id": "j7", "name": "历史"},
    {"id": "j8", "name": "生物"},
    {"id": "j9", "name": "地理"},
    {"id": "j10", "name": "体育"},
    {"id": "j11", "name": "音乐"},
    {"id": "j12", "name": "美术"},
    {"id": "j13", "name": "信息"},
    {"id": "j14", "name": "科学"},
    {"id": "j15", "name": "心理"},
]

# 「全校活动」：跨全部校区的活动，用特殊值存进 campus_ids（无需改表结构）
ALL_CAMPUS = "全校活动"


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    display_name = db.Column(db.String(64), nullable=False)
    role = db.Column(db.String(16), default="admin")
    active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    def set_password(self, raw):
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw):
        return check_password_hash(self.password_hash, raw)

    @property
    def is_super(self):
        return self.role == "super"


class Activity(db.Model):
    __tablename__ = "activities"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    campus_ids = db.Column(db.Text, default="[]")
    stage_ids = db.Column(db.Text, default="[]")
    subject_ids = db.Column(db.Text, default="[]")
    start_at = db.Column(db.DateTime, nullable=False)
    end_at = db.Column(db.DateTime, nullable=False)
    location = db.Column(db.String(200), default="")
    need_checkout = db.Column(db.Boolean, default=False)
    status = db.Column(db.String(16), default="active")
    owner_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now)

    owner = db.relationship("User", backref="activities")

    # ---- JSON 字段便捷访问 ----
    @property
    def campuses(self):
        return json.loads(self.campus_ids or "[]")

    @property
    def stages(self):
        return json.loads(self.stage_ids or "[]")

    @property
    def subjects(self):
        return json.loads(self.subject_ids or "[]")

    @property
    def is_archived(self):
        return self.status == "archived"

    @property
    def is_school_wide(self):
        """是否为「全校活动」（跨全部校区，学段/学科不参与筛选）。"""
        return ALL_CAMPUS in self.campuses


class Roster(db.Model):
    __tablename__ = "roster"

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    campus = db.Column(db.String(64), nullable=False)
    phone = db.Column(db.String(32), default="")
    stage = db.Column(db.String(32), default="")
    subject = db.Column(db.String(32), default="")

    activity = db.relationship("Activity", backref="roster")


class CheckIn(db.Model):
    __tablename__ = "checkins"

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False)
    name = db.Column(db.String(64), nullable=False)
    phone = db.Column(db.String(32), default="")
    campus = db.Column(db.String(64), default="")
    code_used = db.Column(db.String(8), default="")
    mode = db.Column(db.String(8), default="in")  # in | out
    source = db.Column(db.String(16), default="scan")  # scan | manual
    checked_in_at = db.Column(db.DateTime, default=datetime.utcnow)
    checked_out_at = db.Column(db.DateTime, nullable=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    activity = db.relationship("Activity", backref="checkins")
    operator = db.relationship("User", foreign_keys=[operator_id])


class LotteryRound(db.Model):
    """一次随机抽签的结果留痕。"""

    __tablename__ = "lottery_rounds"

    id = db.Column(db.Integer, primary_key=True)
    activity_id = db.Column(db.Integer, db.ForeignKey("activities.id"), nullable=False)
    draw_count = db.Column(db.Integer, default=1)
    winners_json = db.Column(db.Text, default="[]")
    excluded = db.Column(db.Boolean, default=True)
    operator_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.now)

    activity = db.relationship("Activity", backref="lottery_rounds")
    operator = db.relationship("User", foreign_keys=[operator_id])

    @property
    def winners(self):
        try:
            return json.loads(self.winners_json or "[]")
        except (ValueError, TypeError):
            return []


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(32), primary_key=True)
    value = db.Column(db.Text, default="[]")

    @staticmethod
    def list_of(key):
        raw = db.session.get(Setting, key)
        if not raw:
            return []
        try:
            return json.loads(raw.value)
        except (ValueError, TypeError):
            return []

    @staticmethod
    def set_list(key, items):
        raw = db.session.get(Setting, key)
        if raw is None:
            raw = Setting(key=key)
            db.session.add(raw)
        raw.value = json.dumps(items, ensure_ascii=False)
