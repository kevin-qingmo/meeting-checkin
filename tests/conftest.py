import os
import sys
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402
from app.extensions import db  # noqa: E402
from app.models import CAMPUSES, STAGES, SUBJECTS, Activity, Setting, User  # noqa: E402


@pytest.fixture()
def app():
    application = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SECRET_KEY": "test-secret",
        "BASE_URL": "http://localhost:5000",
        "CYCLE_SECONDS": 20,
    })
    with application.app_context():
        db.create_all()
        Setting.set_list("campuses", CAMPUSES)
        Setting.set_list("stages", STAGES)
        Setting.set_list("subjects", SUBJECTS)

        admin = User(username="admin", display_name="教务主任", role="super")
        admin.set_password("admin123456")
        other = User(username="teacher2", display_name="张老师", role="admin")
        other.set_password("teacher123456")
        db.session.add_all([admin, other])
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
        application.config["TEST_ACTIVITY_ID"] = act.id

    yield application


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def activity(app):
    with app.app_context():
        return db.session.get(Activity, app.config["TEST_ACTIVITY_ID"])


def login(client, username="admin", password="admin123456"):
    return client.post("/login", data={"username": username, "password": password},
                       follow_redirects=True)
