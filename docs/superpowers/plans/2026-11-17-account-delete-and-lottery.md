# 管理员账号删除 + 活动随机抽签 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为会议扫码签到系统增加两项能力——创建者可删除管理员账号（其名下活动一并删除），以及活动后台可设置人数从已签到人员中随机抽签、结果落库、签到大屏滚动展示、并进入 Excel 导出。

**Architecture:** 新增 `app/lottery.py` 承载抽签领域逻辑（候选池构建、历史中奖人集合、随机抽取、轮次序列化），`app/models.py` 新增 `LotteryRound` 表。新增两个 HTTP 接口：`POST /admin/activity/<id>/lottery`（登录 + 活动归属）与 `GET /api/activity/<id>/lottery`（**公开只读**，供大屏投屏）。账号删除复用已有的 `POST /admin/users` 路由的 `action` 分支（同属创建者专属守卫）。

**Tech Stack:** Python 3.14 / Flask / Flask-Login / SQLAlchemy / PostgreSQL（本地 SQLite）/ Jinja2 / 原生 CSS+JS（无前端构建）/ openpyxl / pytest / puppeteer-core + Edge headless

## Global Constraints

- 项目根：`D:\MiniMax工作站\签到系统`；虚拟环境：`.venv\Scripts\python.exe`
- 运行测试：`& '.\.venv\Scripts\python.exe' -m pytest tests -q`（当前基线 40 passed）
- 配色（不要改动）：日式黑金——墨黑 `#2C2A26`、沙金 `#D4B48C`、陶土金 `#B89274`、深金 `#8A6B52`、纸底 `#F5F1EC`；大屏已签到=沙金、已签离=绿 `#A8C4B4`
- 页面文案全部中文；数据库字段用英文；时间格式 `YYYY-MM-DD HH:MM:SS`
- 角色语义：`role=super` 在界面上叫「创建者」，普通管理员叫「管理员」；**不要**在界面文案里再出现「超级管理员」
- 用户已决定：不新增任何公开的密码重置/自助恢复接口
- 部署用 `railway up --service web --detach --yes`（直传，不依赖 GitHub）
- 改动后本地 Flask 服务需要重启才能看到模板变化（`--no-reload`）
- 线上验收用的临时账号与一次性 SSH 密钥**用完立即注销**

---

### Task 1: 数据模型 LotteryRound

**Files:**
- Modify: `app/models.py`（在 `CheckIn` 之后、`Setting` 之前新增模型）
- Test: `tests/test_lottery.py`（新建）

**Interfaces:**
- Consumes: 既有 `Activity`（`app/models.py`）、`User`（`app/models.py`）
- Produces:
  - `class LotteryRound(db.Model)`，表名 `lottery_rounds`
  - 字段：`id`、`activity_id`、`draw_count`、`winners_json`(Text)、`excluded`(Boolean)、`operator_id`、`created_at`
  - `LotteryRound.activity` → 关系 `Activity`，反向名 `lottery_rounds`
  - `LotteryRound.operator` → 关系 `User`（`foreign_keys=[operator_id]`）
  - `LotteryRound.winners` → property，返回 `list[dict]`（由 `winners_json` 解析）

- [ ] **Step 1: 写失败的测试**

新建 `tests/test_lottery.py`：

```python
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
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py -q`
Expected: FAIL —— `ImportError: cannot import name 'LotteryRound'`

- [ ] **Step 3: 实现模型**

在 `app/models.py` 的 `CheckIn` 类之后（`Setting` 类之前）插入：

```python
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
```

（`app/models.py` 顶部已有 `import json` 与 `from datetime import datetime`，无需新增导入。）

- [ ] **Step 4: 运行测试确认通过**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/models.py tests/test_lottery.py
git commit -m "feat: 新增 LotteryRound 模型记录抽签轮次"
```

---

### Task 2: 抽签领域逻辑 app/lottery.py

**Files:**
- Create: `app/lottery.py`
- Test: `tests/test_lottery.py`（追加用例）

**Interfaces:**
- Consumes: `CheckIn`、`LotteryRound`（Task 1 产出）
- Produces（后续任务全部依赖这些名字，签名必须一致）：
  - `person_key(name, campus, phone) -> str`：去重键，手机号优先 `p:<phone>`，否则 `n:<name>|<campus>`
  - `candidate_pool(activity) -> list[CheckIn]`：该活动已签到人员（`checked_in_at` 非空），按去重键去重
  - `past_winner_keys(activity) -> set[str]`：该活动所有历史轮次中奖人的去重键集合
  - `draw(activity, count, exclude_winners=True) -> tuple[list[dict], int]`：返回 `(winners, available_count)`；`winners` 每项 `{"name","campus","phone"}`
  - `save_round(activity, winners, draw_count, excluded, operator_id) -> LotteryRound`
  - `serialize_round(round_row, operator_name="") -> dict`：`{"id","draw_count","winners","excluded","created_at","operator"}`
  - `recent_rounds(activity, limit=5) -> list[dict]`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_lottery.py` 末尾追加：

```python
def test_candidate_pool_only_contains_signed_in(app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    with app.app_context():
        act = db.session.get(Activity, aid)
        pool = app_lottery.candidate_pool(act)
        assert [r.name for r in pool] == ["张三"]


def test_draw_only_from_signed_in(app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    with app.app_context():
        act = db.session.get(Activity, aid)
        winners, available = app_lottery.draw(act, 5)
        assert available == 2
        assert len(winners) == 2
        assert {w["name"] for w in winners} == {"张三", "李四"}


def test_draw_excludes_previous_winners_when_flag_on(app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    with app.app_context():
        act = db.session.get(Activity, aid)
        winners, _ = app_lottery.draw(act, 1)
        app_lottery.save_round(act, winners, 1, True, None)
        second, available = app_lottery.draw(act, 1, exclude_winners=True)
        assert available == 1
        assert second[0]["name"] != winners[0]["name"]
        third, available3 = app_lottery.draw(act, 1, exclude_winners=False)
        assert available3 == 2


def test_person_key_prefers_phone():
    assert app_lottery.person_key("张三", "校区A", "13800000000") == "p:13800000000"
    assert app_lottery.person_key("张三", "校区A", "") == "n:张三|校区A"
```

同时在文件顶部加导入：

```python
from app import lottery as app_lottery
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py -q`
Expected: FAIL —— `ModuleNotFoundError: No module named 'app.lottery'`

- [ ] **Step 3: 实现 app/lottery.py**

创建 `app/lottery.py`：

```python
"""随机抽签领域逻辑：候选池、历史中奖人、随机抽取与轮次留痕。"""
import json
import secrets

from .extensions import db
from .models import CheckIn, LotteryRound


def person_key(name, campus, phone):
    """去重键：优先手机号，其次姓名+校区。"""
    phone = (phone or "").strip()
    if phone:
        return "p:" + phone
    return "n:" + (name or "").strip() + "|" + (campus or "").strip()


def candidate_pool(activity):
    """候选池 = 该活动已签到人员（扫码与补录都算），按去重键去重。"""
    rows = CheckIn.query.filter_by(activity_id=activity.id).all()
    pool, seen = [], set()
    for row in rows:
        if row.checked_in_at is None:
            continue
        key = person_key(row.name, row.campus, row.phone)
        if key in seen:
            continue
        seen.add(key)
        pool.append(row)
    return pool


def past_winner_keys(activity):
    """该活动所有历史轮次中奖人的去重键集合。"""
    keys = set()
    for row in LotteryRound.query.filter_by(activity_id=activity.id).all():
        for w in row.winners:
            keys.add(person_key(w.get("name"), w.get("campus"), w.get("phone")))
    return keys


def draw(activity, count, exclude_winners=True):
    """随机抽取。返回 (winners, available_count)。"""
    pool = candidate_pool(activity)
    blocked = past_winner_keys(activity) if exclude_winners else set()
    available = [r for r in pool
                 if person_key(r.name, r.campus, r.phone) not in blocked]
    try:
        k = int(count)
    except (TypeError, ValueError):
        k = 1
    k = max(1, k)
    picked = secrets.SystemRandom().sample(available, min(k, len(available)))
    winners = [{"name": r.name, "campus": r.campus or "", "phone": r.phone or ""} for r in picked]
    return winners, len(available)


def save_round(activity, winners, draw_count, excluded, operator_id):
    """写入一轮抽签记录。"""
    row = LotteryRound(
        activity_id=activity.id,
        draw_count=draw_count,
        winners_json=json.dumps(winners, ensure_ascii=False),
        excluded=bool(excluded),
        operator_id=operator_id,
    )
    db.session.add(row)
    db.session.commit()
    return row


def serialize_round(row, operator_name=""):
    return {
        "id": row.id,
        "draw_count": row.draw_count,
        "winners": row.winners,
        "excluded": bool(row.excluded),
        "created_at": row.created_at.strftime("%Y-%m-%d %H:%M:%S") if row.created_at else "",
        "operator": operator_name or "",
    }


def recent_rounds(activity, limit=5):
    rows = (LotteryRound.query.filter_by(activity_id=activity.id)
            .order_by(LotteryRound.id.desc()).limit(limit).all())
    out = []
    for row in rows:
        name = row.operator.display_name if row.operator else ""
        out.append(serialize_round(row, name))
    return out
```

- [ ] **Step 4: 运行测试确认通过**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py -q`
Expected: PASS

- [ ] **Step 5: 提交**

```bash
git add app/lottery.py tests/test_lottery.py
git commit -m "feat: 抽签领域逻辑（候选池 / 排除已中奖 / 随机抽取 / 轮次留痕）"
```

---

### Task 3: 抽签 HTTP 接口

**Files:**
- Modify: `app/routes/admin.py`（新增 `activity_lottery` 路由 + 导入）
- Modify: `app/routes/api.py`（新增公开只读接口 + 导入）
- Test: `tests/test_lottery.py`（追加用例）

**Interfaces:**
- Consumes: Task 2 的 `candidate_pool` / `draw` / `save_round` / `serialize_round` / `recent_rounds`
- Produces:
  - `POST /admin/activity/<int:activity_id>/lottery`（登录 + 活动归属）→ JSON `{ok, message, round, rounds}`；失败时 `ok=false` 且 HTTP 400
  - `GET /api/activity/<int:activity_id>/lottery`（**公开只读**）→ JSON `{ok, rounds, latest}`；活动不存在 → 404

- [ ] **Step 1: 写失败的测试**

在 `tests/test_lottery.py` 末尾追加：

```python
def test_lottery_endpoint_draws_and_records(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    _signed_in(app, aid, "李四", "13800000002")
    login(client)
    r = client.post("/admin/activity/%d/lottery" % aid,
                    data={"count": "1", "exclude_winners": "on"})
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert len(d["round"]["winners"]) == 1
    assert d["round"]["excluded"] is True
    with app.app_context():
        assert LotteryRound.query.filter_by(activity_id=aid).count() == 1


def test_lottery_endpoint_requires_login(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    r = client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    assert r.status_code in (302, 401, 403)


def test_lottery_endpoint_without_candidates_fails(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    login(client)
    r = client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    assert r.status_code == 400
    assert r.get_json()["ok"] is False


def test_lottery_read_endpoint_is_public(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    login(client)
    client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    client.get("/logout")
    r = client.get("/api/activity/%d/lottery" % aid)
    assert r.status_code == 200
    d = r.get_json()
    assert d["ok"] is True
    assert d["latest"]["winners"][0]["name"] == "张三"
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py -q`
Expected: FAIL —— 404（路由不存在）

- [ ] **Step 3: 实现后台抽签路由**

在 `app/routes/admin.py` 的导入区把 models 导入改为：

```python
from ..models import ALL_CAMPUS, Activity, CheckIn, LotteryRound, Roster, Setting, User
```

并新增导入：

```python
from ..lottery import candidate_pool, draw, recent_rounds, save_round, serialize_round
```

在 `activity_delete` 路由之后插入：

```python
@bp.route("/activity/<int:activity_id>/lottery", methods=["POST"])
@login_required
def activity_lottery(activity_id):
    """从已签到人员中随机抽签并留痕。"""
    act = get_managed_activity(activity_id)
    try:
        count = int(request.form.get("count") or 1)
    except (TypeError, ValueError):
        count = 1
    count = max(1, count)
    exclude = request.form.get("exclude_winners") in ("on", "1", "true", "yes")
    if not candidate_pool(act):
        return jsonify({"ok": False, "message": "暂无可抽取人员，请先完成签到"}), 400
    winners, available = draw(act, count, exclude)
    if not winners:
        return jsonify({"ok": False, "message": "可抽取人员不足（可抽 {} 人）".format(available)}), 400
    row = save_round(act, winners, count, exclude, current_user.id)
    return jsonify({
        "ok": True,
        "message": "已抽出 {} 人".format(len(winners)),
        "round": serialize_round(row, current_user.display_name),
        "rounds": recent_rounds(act, 5),
    })
```

- [ ] **Step 4: 实现公开只读接口**

在 `app/routes/api.py` 的导入区补上 `from ..lottery import recent_rounds`，并在 `from ..models import Activity, CheckIn` 处补 `LotteryRound`（若用到）。在文件末尾追加：

```python
@bp.route("/api/activity/<int:activity_id>/lottery")
def activity_lottery(activity_id):
    """抽签记录（公开只读，供大屏投屏使用）。"""
    activity = db.session.get(Activity, activity_id)
    if activity is None:
        return jsonify({"ok": False, "message": "活动不存在"}), 404
    rounds = recent_rounds(activity, 5)
    return jsonify({"ok": True, "rounds": rounds, "latest": rounds[0] if rounds else None})
```

- [ ] **Step 5: 运行测试确认通过**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py -q`
Expected: PASS

- [ ] **Step 6: 跑全量回归**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add app/routes/admin.py app/routes/api.py tests/test_lottery.py
git commit -m "feat: 抽签接口（后台抽取 + 公开只读查询）"
```

---

### Task 4: 活动后台抽签界面

**Files:**
- Modify: `app/templates/admin/dashboard.html`（新增「随机抽签」卡片、遮罩弹层、历史记录表、JS）
- Modify: `app/static/css/app.css`（新增 `.lottery-*` 与遮罩层样式）
- Test: `tests/test_lottery.py`（追加页面结构断言）+ 浏览器脚本 `tools/ui_check_lottery.js`

**Interfaces:**
- Consumes: Task 3 的 `POST /admin/activity/<id>/lottery` 返回 `{ok, message, round, rounds}`
- Produces: 页面元素 id：`lottery-count`、`lottery-exclude`、`lottery-btn`、`lottery-msg`、`lottery-history`、`lottery-overlay`、`lottery-winners`、`lottery-close`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_lottery.py` 末尾追加：

```python
def test_dashboard_has_lottery_card(client):
    login(client)
    body = client.get("/admin/activity/%d/dashboard" % app_id(client)).get_data(as_text=True) \
        if False else client.get("/admin/").get_data(as_text=True)
    assert "随机抽签" in body
```

（简化写法，避免依赖 fixture 顺序：在测试里用 `app.config["TEST_ACTIVITY_ID"]`，写成

```python
def test_dashboard_has_lottery_card(client, app):
    login(client)
    body = client.get("/admin/activity/%d/dashboard" % app.config["TEST_ACTIVITY_ID"]).get_data(as_text=True)
    assert "随机抽签" in body
    assert 'id="lottery-count"' in body
    assert 'id="lottery-exclude"' in body
    assert 'id="lottery-history"' in body
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py::test_dashboard_has_lottery_card -q`
Expected: FAIL —— 页面里没有「随机抽签」

- [ ] **Step 3: 在 dashboard.html 加抽签卡片**

在「手动补录」卡片所在 `grid grid-2` 之后、`签到明细` 卡片之前插入：

```html
<div class="card" style="margin-top:16px">
  <h2>随机抽签</h2>
  <div class="sub">从本场<strong>已签到</strong>人员中随机抽取；结果会记录并在大屏展示</div>
  <div class="row" style="align-items:flex-end">
    <div class="field" style="flex:0 0 180px">
      <label>抽取人数</label>
      <input type="number" id="lottery-count" min="1" value="1" step="1">
    </div>
    <div class="field" style="flex:0 0 auto">
      <label class="switch">
        <input type="checkbox" id="lottery-exclude" checked>
        <span>排除已中奖的人</span>
      </label>
    </div>
    <div style="flex:0">
      <button class="btn" id="lottery-btn" type="button">开始抽奖</button>
    </div>
  </div>
  <div id="lottery-msg" class="muted small" style="margin-top:8px"></div>

  <div style="margin-top:16px">
    <div class="muted small" style="margin-bottom:6px">历史抽奖记录</div>
    <table id="lottery-history">
      <thead><tr><th>轮次</th><th>抽取时间</th><th>人数</th><th>中奖名单</th><th>操作人</th><th>排除已中奖</th></tr></thead>
      <tbody id="lottery-history-body">
        <tr><td colspan="6" class="muted">暂无抽奖记录</td></tr>
      </tbody>
    </table>
  </div>
</div>

<div class="lottery-overlay" id="lottery-overlay">
  <div class="lottery-overlay-box">
    <div class="lottery-overlay-title">恭喜中奖</div>
    <div class="lottery-winners" id="lottery-winners"></div>
    <button class="btn btn-ghost" id="lottery-close" type="button">关闭</button>
  </div>
</div>
```

在该模板的 `{% block scripts %}` 脚本末尾追加：

```javascript
async function loadLotteryHistory(){
  const r = await fetch(`/api/activity/${ACTIVITY_ID}/lottery`);
  if(!r.ok) return;
  const d = await r.json();
  const body = document.getElementById('lottery-history-body');
  const rows = (d.rounds||[]).slice().reverse();
  body.innerHTML = rows.map((x, i) => `<tr>
      <td>第 ${rows.length - i} 轮</td>
      <td class="small">${esc(x.created_at)}</td>
      <td>${x.draw_count}</td>
      <td>${esc((x.winners||[]).map(w => w.name).join('、')) || '—'}</td>
      <td>${esc(x.operator)}</td>
      <td>${x.excluded ? '是' : '否'}</td>
    </tr>`).join('') || '<tr><td colspan="6" class="muted">暂无抽奖记录</td></tr>';
}
document.getElementById('lottery-btn').addEventListener('click', async () => {
  const btn = document.getElementById('lottery-btn');
  const msg = document.getElementById('lottery-msg');
  btn.disabled = true;
  msg.textContent = '抽取中…';
  const fd = new FormData();
  fd.append('count', document.getElementById('lottery-count').value || '1');
  if (document.getElementById('lottery-exclude').checked) fd.append('exclude_winners', 'on');
  const r = await fetch(`/admin/activity/${ACTIVITY_ID}/lottery`, {method:'POST', body: fd});
  const d = await r.json();
  btn.disabled = false;
  msg.textContent = d.message || '';
  if(d.ok){
    document.getElementById('lottery-winners').innerHTML =
      d.round.winners.map(w => `<div class="lottery-winner">${esc(w.name)}<span>${esc(w.campus)}</span></div>`).join('');
    document.getElementById('lottery-overlay').classList.add('show');
  }
  loadLotteryHistory();
});
document.getElementById('lottery-close').addEventListener('click', () => {
  document.getElementById('lottery-overlay').classList.remove('show');
});
loadLotteryHistory();
```

- [ ] **Step 4: 在 app.css 加样式**

在文件末尾追加：

```css
/* ---------- 随机抽签 ---------- */
.lottery-overlay{position:fixed;inset:0;background:rgba(28,25,23,.72);display:none;place-items:center;z-index:80;padding:24px}
.lottery-overlay.show{display:grid}
.lottery-overlay-box{background:#2C2A26;border:1px solid rgba(212,180,140,.5);border-radius:20px;
  padding:36px 44px;min-width:min(520px,92vw);text-align:center;box-shadow:0 24px 60px rgba(0,0,0,.5)}
.lottery-overlay-title{font-size:26px;color:#D4B48C;letter-spacing:6px;margin-bottom:20px}
.lottery-winners{display:flex;flex-direction:column;gap:12px;margin-bottom:22px}
.lottery-winner{font-size:34px;font-weight:800;color:#F5F1EC;letter-spacing:4px}
.lottery-winner span{display:block;font-size:14px;font-weight:400;color:#B3A894;letter-spacing:2px}
```

- [ ] **Step 5: 运行测试确认通过**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py -q`
Expected: PASS

- [ ] **Step 6: 提交**

```bash
git add app/templates/admin/dashboard.html app/static/css/app.css tests/test_lottery.py
git commit -m "feat: 活动后台新增随机抽签卡片与中奖弹层"
```

---

### Task 5: 签到大屏展示中奖名单

**Files:**
- Modify: `app/templates/board.html`（新增「中奖名单」卡片）
- Modify: `app/static/js/board.js`（5 秒轮询抽签接口 + 滚动渲染）
- Modify: `app/static/css/board.css`（中奖名单卡片样式）
- Test: `tools/ui_check_lottery.js`（新建，浏览器端到端）

**Interfaces:**
- Consumes: Task 3 的 `GET /api/activity/<id>/lottery` → `{ok, rounds, latest}`
- Produces: 页面元素 id：`winner-list`、`winner-empty`、`winner-round`

- [ ] **Step 1: 写浏览器端到端脚本**

新建 `tools/ui_check_lottery.js`：

```javascript
// 端到端：后台抽奖 → 大屏出现中奖名单
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const BASE = 'http://localhost:5055';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const ok = (c, m) => console.log((c ? '  PASS  ' : '! FAIL  ') + m);

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new', args: ['--no-sandbox', '--disable-gpu']
  });
  const p = await browser.newPage();
  await p.setViewport({ width: 1360, height: 950 });
  await p.goto(BASE + '/login', { waitUntil: 'networkidle2' });
  await p.type('input[name=username]', 'admin');
  await p.type('input[name=password]', 'admin123456');
  await Promise.all([p.waitForNavigation({ waitUntil: 'networkidle2' }), p.click('button[type=submit]')]);

  // 找到活动 id
  await p.goto(BASE + '/admin/', { waitUntil: 'networkidle2' });
  const ids = await p.evaluate(() => Array.from(document.querySelectorAll('a[href*="/admin/activity/"]'))
    .map(a => (a.getAttribute('href').match(/activity\/(\d+)/) || [])[1]).filter(Boolean));
  const aid = ids[0];
  ok(!!aid, '找到活动 id: ' + aid);

  // 先补录两个人并签到
  await p.evaluate(async (aid) => {
    for (const [n, ph, c] of [['抽奖甲', '13900000001', '和慧南路校区'], ['抽奖乙', '13900000002', '雅馨路校区']]) {
      await fetch(`/api/activity/${aid}/manual`, {
        method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: new URLSearchParams({ name: n, phone: ph, campus: c })
      });
    }
  }, aid);

  // 打开后台抽签
  await p.goto(BASE + '/admin/activity/' + aid + '/dashboard', { waitUntil: 'networkidle2' });
  await sleep(500);
  await p.click('#lottery-btn');
  await sleep(1200);
  const overlayShown = await p.evaluate(() => document.getElementById('lottery-overlay').classList.contains('show'));
  ok(overlayShown, '抽奖后弹层出现');
  const winners = await p.evaluate(() => document.getElementById('lottery-winners').innerText.trim());
  ok(winners.length > 0, '弹层内显示中奖名单: ' + winners.replace(/\n/g, ' '));
  await p.screenshot({ path: 'D:/MiniMax工作站/签到系统/_screenshots/lottery-overlay.png' });
  await p.click('#lottery-close');

  // 历史记录表格有一行
  const historyRows = await p.evaluate(() => document.querySelectorAll('#lottery-history-body tr').length);
  ok(historyRows >= 1, '历史抽奖记录已写入表格');

  // 大屏展示
  const p2 = await browser.newPage();
  await p2.setViewport({ width: 1600, height: 1000 });
  await p2.goto(BASE + '/board/' + aid, { waitUntil: 'networkidle2' });
  await sleep(3000);
  const boardText = await p2.evaluate(() => document.getElementById('winner-list') ? document.getElementById('winner-list').innerText : '');
  ok(boardText.trim().length > 0, '大屏显示中奖名单: ' + boardText.replace(/\n/g, ' '));
  await p2.screenshot({ path: 'D:/MiniMax工作站/签到系统/_screenshots/lottery-board.png' });

  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
```

- [ ] **Step 2: 运行脚本确认失败**

前置：本地服务在 5055 运行，且本地库有活动与已签到人员（`tools/demo_data.py` 可生成演示数据）。

Run: `node tools\ui_check_lottery.js`
Expected: FAIL —— `#lottery-btn` 不存在 / `winner-list` 不存在

- [ ] **Step 3: 在 board.html 加中奖名单卡片**

在 `board.html` 的 `<section class="board-side">` 内、`</section>` 之前（最新动态 `.feed` 之后）插入：

```html
      <div class="feed winner-feed">
        <div class="feed-head">中奖名单 <span class="winner-round" id="winner-round"></span></div>
        <div class="feed-list winner-list" id="winner-list">
          <div class="winner-empty" id="winner-empty">本次暂无抽奖</div>
        </div>
      </div>
```

- [ ] **Step 4: 在 board.js 加轮询与渲染**

在 `board.js` 的 `loadLive` 函数之后、`esc` 函数之前插入：

```javascript
  let lastWinnerRound = -1;

  async function loadWinners() {
    const r = await fetch(`/api/activity/${ACTIVITY_ID}/lottery?_=${Date.now()}`);
    if (!r.ok) return;
    const d = await r.json();
    const list = document.getElementById('winner-list');
    const empty = document.getElementById('winner-empty');
    const roundTag = document.getElementById('winner-round');
    const latest = d.latest;
    if (!latest || !(latest.winners || []).length) {
      if (empty) empty.style.display = '';
      if (roundTag) roundTag.textContent = '';
      return;
    }
    if (empty) empty.style.display = 'none';
    if (roundTag) roundTag.textContent = '（最新一轮 · ' + latest.created_at + '）';
    if (latest.id === lastWinnerRound) return;   // 同一轮不重复重绘
    lastWinnerRound = latest.id;
    const names = latest.winners.map(w => w.name).join('、');
    list.innerHTML = `<div class="winner-marquee"><div class="winner-marquee-inner">${esc(names)}</div></div>`;
  }
```

并在文件末尾的 `setInterval(loadLive, 2000);` 后面加：

```javascript
  loadWinners();
  setInterval(loadWinners, 5000);
```

- [ ] **Step 5: 在 board.css 加样式**

在 `board.css` 末尾追加：

```css
/* ---------- 中奖名单 ---------- */
.winner-feed{min-height:0}
.winner-round{font-size:13px;font-weight:400;color:#B3A894;margin-left:8px}
.winner-list{display:flex;align-items:center;justify-content:center;min-height:150px;overflow:hidden}
.winner-empty{color:#8A8175;font-size:16px}
.winner-marquee{width:100%;overflow:hidden}
.winner-marquee-inner{display:inline-block;white-space:nowrap;font-size:40px;font-weight:800;color:#D4B48C;
  letter-spacing:6px;padding-left:100%;animation:winner-scroll 18s linear infinite}
@keyframes winner-scroll{from{transform:translateX(0)}to{transform:translateX(-100%)}}
```

- [ ] **Step 6: 重启本地服务并运行脚本确认通过**

```bash
$pid = (Get-NetTCPConnection -LocalPort 5055 -State Listen).OwningProcess; Stop-Process -Id $pid -Force
& '.\.venv\Scripts\python.exe' -m flask --app wsgi run --port 5055 --no-reload
```

（第二条放后台运行。）

Run: `node tools\ui_check_lottery.js`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add app/templates/board.html app/static/js/board.js app/static/css/board.css tools/ui_check_lottery.js
git commit -m "feat: 签到大屏新增滚动中奖名单"
```

---

### Task 6: 管理员账号删除

**Files:**
- Modify: `app/routes/admin.py`（`users()` 路由新增 `action == "delete"` 分支）
- Modify: `app/templates/admin/users.html`（每行加删除按钮 + 确认文案）
- Test: `tests/test_lottery.py`（追加用例）

**Interfaces:**
- Consumes: `LotteryRound`（Task 1）、`Activity`/`CheckIn`/`Roster`（既有）
- Produces: `POST /admin/users`，表单字段 `action=delete`、`uid=<账号 id>`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_lottery.py` 末尾追加：

```python
def test_creator_can_delete_admin_account(client, app):
    login(client)
    with app.app_context():
        other = User.query.filter_by(username="teacher2").one()
        uid = other.id
    r = client.post("/admin/users", data={"action": "delete", "uid": str(uid)},
                    follow_redirects=True)
    assert "已删除账号" in r.get_data(as_text=True)
    with app.app_context():
        assert User.query.get(uid) is None


def test_delete_account_cascades_its_activities(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    login(client)
    with app.app_context():
        other = User.query.filter_by(username="teacher2").one()
        other_id = other.id
        act = Activity(title="待删除活动", owner_id=other_id,
                       start_at=datetime.now(), end_at=datetime.now() + timedelta(hours=1))
        db.session.add(act)
        db.session.commit()
        act_id = act.id
        db.session.add(LotteryRound(activity_id=act_id, draw_count=1,
                                    winners_json="[]", excluded=True, operator_id=other_id))
        db.session.commit()
    client.post("/admin/users", data={"action": "delete", "uid": str(other_id)})
    with app.app_context():
        assert db.session.get(Activity, act_id) is None
        assert CheckIn.query.filter_by(activity_id=act_id).count() == 0
        assert LotteryRound.query.filter_by(activity_id=act_id).count() == 0


def test_cannot_delete_current_account(client, app):
    login(client)
    with app.app_context():
        uid = User.query.filter_by(username="admin").one().id
    client.post("/admin/users", data={"action": "delete", "uid": str(uid)})
    with app.app_context():
        assert User.query.get(uid) is not None


def test_normal_admin_cannot_delete_accounts(client, app):
    login(client, "teacher2", "teacher123456")
    with app.app_context():
        uid = User.query.filter_by(username="admin").one().id
    r = client.post("/admin/users", data={"action": "delete", "uid": str(uid)})
    assert r.status_code == 403
    with app.app_context():
        assert User.query.get(uid) is not None
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py -q`
Expected: FAIL —— 账号未被删除

- [ ] **Step 3: 实现删除分支**

在 `app/routes/admin.py` 的 `users()` 路由里，`elif action == "rename":` 分支之后追加：

```python
        elif action == "delete":
            uid = (request.form.get("uid") or "").strip()
            u = db.session.get(User, int(uid)) if uid.isdigit() else None
            if u is None:
                flash("账号不存在", "error")
            elif u.id == current_user.id:
                flash("不能删除当前登录的账号", "error")
            else:
                name = u.display_name
                act_ids = [a.id for a in Activity.query.filter_by(owner_id=u.id).all()]
                if act_ids:
                    LotteryRound.query.filter(LotteryRound.activity_id.in_(act_ids)).delete(synchronize_session=False)
                    CheckIn.query.filter(CheckIn.activity_id.in_(act_ids)).delete(synchronize_session=False)
                    Roster.query.filter(Roster.activity_id.in_(act_ids)).delete(synchronize_session=False)
                    Activity.query.filter(Activity.id.in_(act_ids)).delete(synchronize_session=False)
                db.session.delete(u)
                db.session.commit()
                flash("已删除账号「{}」及其 {} 个活动".format(name, len(act_ids)), "success")
```

- [ ] **Step 4: 界面加删除按钮**

在 `app/templates/admin/users.html` 的「操作」列中，把当前账号的改名表单改成「改名 + 删除」两行，并在非当前账号行加删除按钮：

```html
          <td class="right small">
            {% if u.id != current_user.id %}
            <form method="post" style="display:inline"><input type="hidden" name="action" value="role"><input type="hidden" name="uid" value="{{ u.id }}"><button class="btn btn-sm btn-ghost">改角色</button></form>
            <form method="post" style="display:inline"><input type="hidden" name="action" value="toggle"><input type="hidden" name="uid" value="{{ u.id }}"><button class="btn btn-sm btn-ghost">{{ '停用' if u.active else '启用' }}</button></form>
            <form method="post" style="display:inline"
                  onsubmit="return confirm('确定删除账号「{{ u.display_name }}」吗？\n\n该账号名下的活动、名册与签到记录会一并删除，且无法恢复。');">
              <input type="hidden" name="action" value="delete">
              <input type="hidden" name="uid" value="{{ u.id }}">
              <button class="btn btn-sm btn-red" type="submit">删除</button>
            </form>
            {% else %}
            <form method="post" style="display:inline-flex;gap:6px;align-items:center">
              <input type="hidden" name="action" value="rename">
              <input type="hidden" name="uid" value="{{ u.id }}">
              <input type="text" name="display_name" value="{{ u.display_name }}" style="width:110px;padding:4px 8px;font-size:13px">
              <button class="btn btn-sm btn-ghost">改姓名</button>
            </form>
            {% endif %}
          </td>
```

- [ ] **Step 5: 运行测试确认通过**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py -q`
Expected: PASS

- [ ] **Step 6: 跑全量回归**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 7: 提交**

```bash
git add app/routes/admin.py app/templates/admin/users.html tests/test_lottery.py
git commit -m "feat: 创建者可删除管理员账号（级联删除其名下活动）"
```

---

### Task 7: Excel 导出新增「抽奖记录」表

**Files:**
- Modify: `app/exporter.py`
- Test: `tests/test_lottery.py`（追加用例）+ 修正既有 `tests/test_flow.py::test_export_excel_has_three_sheets`

**Interfaces:**
- Consumes: `LotteryRound`（Task 1）、`recent_rounds` 不用于导出（导出需要全部轮次，直接查库）
- Produces: 导出 workbook 的第 4 张表 `抽奖记录`，列为 `["轮次", "抽取时间", "抽取人数", "中奖名单", "操作人", "排除已中奖者"]`

- [ ] **Step 1: 写失败的测试**

在 `tests/test_lottery.py` 末尾追加：

```python
def test_export_contains_lottery_sheet(client, app):
    import io
    from openpyxl import load_workbook
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    login(client)
    client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    r = client.get("/admin/activity/%d/export" % aid)
    wb = load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames == ["签到明细", "应到实到统计", "缺席名单", "抽奖记录"]
    ws = wb["抽奖记录"]
    assert [c.value for c in ws[1]] == ["轮次", "抽取时间", "抽取人数", "中奖名单", "操作人", "排除已中奖者"]
    assert ws.max_row == 2
```

同时把 `tests/test_flow.py` 里那条旧断言改成：

```python
def test_export_excel_has_four_sheets(client, app):
    login(client)
    _scan(client, app)
    r = client.get("/admin/activity/%d/export" % app.config["TEST_ACTIVITY_ID"])
    assert r.status_code == 200
    import io
    from openpyxl import load_workbook
    wb = load_workbook(io.BytesIO(r.data))
    assert wb.sheetnames == ["签到明细", "应到实到统计", "缺席名单", "抽奖记录"]
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py::test_export_contains_lottery_sheet -q`
Expected: FAIL —— 只有 3 张表

- [ ] **Step 3: 实现导出**

在 `app/exporter.py` 的导入区加：

```python
from .models import LotteryRound
```

并在 `build_workbook()` 中 `ws3` 段落之后、`return wb` 之前插入：

```python
    ws4 = wb.create_sheet("抽奖记录")
    _style_header(ws4, ["轮次", "抽取时间", "抽取人数", "中奖名单", "操作人", "排除已中奖者"])
    rounds = (LotteryRound.query.filter_by(activity_id=activity.id)
              .order_by(LotteryRound.id).all())
    for idx, row in enumerate(rounds, 1):
        names = "、".join(w.get("name", "") for w in row.winners)
        ws4.append([
            idx,
            _fmt(row.created_at),
            row.draw_count,
            names,
            row.operator.display_name if row.operator else "",
            "是" if row.excluded else "否",
        ])
    for col, width in zip("ABCDEF", (8, 22, 12, 40, 16, 16)):
        ws4.column_dimensions[col].width = width
```

- [ ] **Step 4: 运行测试确认通过**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests -q`
Expected: 全部 PASS

- [ ] **Step 5: 提交**

```bash
git add app/exporter.py tests/test_lottery.py tests/test_flow.py
git commit -m "feat: Excel 导出新增「抽奖记录」工作表"
```

---

### Task 8: 活动删除同步清理抽签记录 + 全量验收上线

**Files:**
- Modify: `app/routes/admin.py`（`activity_delete` 增加 `LotteryRound` 清理）
- Test: `tests/test_lottery.py`（追加用例）
- Modify: `AGENTS.md`（记录抽签与账号删除机制）

**Interfaces:**
- Consumes: 全部前置任务
- Produces: 无新接口

- [ ] **Step 1: 写失败的测试**

在 `tests/test_lottery.py` 末尾追加：

```python
def test_delete_activity_also_removes_lottery_rounds(client, app):
    aid = app.config["TEST_ACTIVITY_ID"]
    _signed_in(app, aid, "张三", "13800000001")
    login(client)
    client.post("/admin/activity/%d/lottery" % aid, data={"count": "1"})
    with app.app_context():
        assert LotteryRound.query.filter_by(activity_id=aid).count() == 1
    client.post("/admin/activity/%d/delete" % aid)
    with app.app_context():
        assert LotteryRound.query.filter_by(activity_id=aid).count() == 0
```

- [ ] **Step 2: 运行测试确认失败**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests/test_lottery.py::test_delete_activity_also_removes_lottery_rounds -q`
Expected: FAIL —— 抽签记录仍在

- [ ] **Step 3: 实现清理**

在 `app/routes/admin.py` 的 `activity_delete` 中，把

```python
    CheckIn.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
    Roster.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
```

改为

```python
    LotteryRound.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
    CheckIn.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
    Roster.query.filter_by(activity_id=act.id).delete(synchronize_session=False)
```

- [ ] **Step 4: 全量回归 + 浏览器端到端**

Run: `& '.\.venv\Scripts\python.exe' -m pytest tests -q`
Expected: 全部 PASS（基线 40 + 新增用例）

Run: `node tools\ui_check_lottery.js`
Expected: 全部 PASS

- [ ] **Step 5: 更新 AGENTS.md**

在 `AGENTS.md` 的「目录速查」之前新增小节：

```markdown
## 随机抽签机制（2026-11-17 新增）

- 数据表 `lottery_rounds`：每次抽取落一条（人数 / 中奖名单 JSON / 是否排除已中奖 / 操作人 / 时间）。
- 领域逻辑集中在 `app/lottery.py`：`candidate_pool`（只取已签到）、`past_winner_keys`（历史中奖人）、
  `draw`（`secrets.SystemRandom().sample`）、`save_round`、`recent_rounds`。
- 去重键：手机号优先 `p:<phone>`，否则 `n:<姓名>|<校区>`。
- 接口：`POST /admin/activity/<id>/lottery`（登录+活动归属）、`GET /api/activity/<id>/lottery`（**公开只读**，大屏用）。
- 大屏 `board.js` 每 5 秒轮询抽签接口，`winner-marquee` CSS 动画滚动展示最新一轮名单。
- Excel 导出第 4 张表「抽奖记录」。
- 活动删除、账号删除都会级联清理 `lottery_rounds`。
```

- [ ] **Step 6: 提交**

```bash
git add app/routes/admin.py tests/test_lottery.py AGENTS.md
git commit -m "feat: 删除活动同步清理抽签记录；补充机制文档"
```

- [ ] **Step 7: 部署上线**

```bash
railway up --service web --detach --yes
```

等待约 60 秒后确认：

```powershell
(Invoke-WebRequest -Uri 'https://web-production-9fe1faa8.up.railway.app/api/health' -UseBasicParsing).Content
```

Expected: `{"ok":true,...}`

- [ ] **Step 8: 线上验收（用完即清理）**

按既有流程：生成无口令 SSH 密钥 → `railway ssh keys add` → `railway connect Postgres --tunnel-only --port 15432` → 建临时账号 → 跑 `tools/ui_live_check.js`（扩展断言：抽签接口可用、大屏能读到中奖名单）→ 删除临时账号与临时活动 → `railway ssh keys remove` → 停隧道 → 删本地私钥。

- [ ] **Step 9: 推送 GitHub（网络允许时）**

```bash
git -c http.curloptResolve="github.com:443:140.82.112.4" push origin main
```

若失败换 `140.82.114.4` / `140.82.113.4` 重试；GitHub 不通不影响线上（部署走 Railway 直传）。
