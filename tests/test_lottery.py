"""随机抽签与账号删除的测试。"""
import json
from datetime import datetime, timedelta

from app.extensions import db
from app.models import Activity, CheckIn, LotteryRound, Roster, User
from conftest import login


def _signed_in(app, aid, name, phone, campus="敬慧路校区", source="scan"):
    with app.app_context():
        db.session.add(CheckIn(
            activity_id=aid, name=name, phone=phone, campus=campus,
            code_used="1234", mode="in", source=source,
            checked_in_at=datetime.now(),
        ))
        db.session.commit()


def test_lottery_round_model_roundtrip(app):
    with app.app_context():
        act = db.session.get(Activity, app.config["TEST_ACTIVITY_ID"])
        rnd = LotteryRound(
            activity_id=act.id, draw_count=2,
            winners_json=json.dumps([{"name": "张三", "campus": "敬慧路校区", "phone": "13800000000"}],
                                     ensure_ascii=False),
            excluded=True, operator_id=1,
        )
        db.session.add(rnd)
        db.session.commit()
        assert rnd.id is not None
        assert rnd.winners[0]["name"] == "张三"
        assert rnd.excluded is True
        assert len(act.lottery_rounds) == 1
