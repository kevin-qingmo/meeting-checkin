/* 签到大屏：二维码 / 现场码 20 秒轮换 + 实时数据 2 秒轮询 + 中奖名单 5 秒轮询
 *
 * 关键点：
 *  - 倒计时锚定在「取到这轮码的时刻」（cycleStart），而不是服务器整点，
 *    这样切换签到/签离模式后倒计时会真正从 20 秒重新开始。
 *  - 码与现场码由服务端按 (活动, 周期, 模式) 派生，切换模式必然换新码。
 */
(function () {
  let mode = INITIAL_MODE || 'in';
  let cycle = -1;
  let cycleSeconds = 20;
  let cycleStart = Date.now();
  let refreshing = false;
  let lastAttempt = 0;

  const qrImg = document.getElementById('qr-img');
  const siteCode = document.getElementById('site-code');
  const barFill = document.getElementById('bar-fill');
  const refreshTip = document.getElementById('refresh-tip');
  const badge = document.getElementById('mode-badge');
  const switchBtn = document.getElementById('switch-mode');

  function setMode(m) {
    if (m === mode) return;
    mode = m;
    badge.textContent = m === 'out' ? '签离模式' : '签到模式';
    badge.classList.toggle('out', m === 'out');
    switchBtn.textContent = m === 'out' ? '切换为签到模式' : '切换为签离模式';
    cycle = -1;          // 强制换新码
    refreshQr(true);     // 取新码 + 重新计时
  }

  async function refreshQr(force) {
    if (refreshing) return;
    refreshing = true;
    lastAttempt = Date.now();
    try {
      const r = await fetch(`/api/board/${ACTIVITY_ID}/qr?mode=${mode}&_=${Date.now()}`);
      if (!r.ok) return;
      const d = await r.json();
      if (!force && d.cycle === cycle && d.mode === mode) return;
      cycle = d.cycle;
      cycleSeconds = d.cycle_seconds || 20;
      qrImg.src = d.qr_png + '&_=' + Date.now();
      siteCode.textContent = d.site_code;
      cycleStart = Date.now();   // 这一轮从此刻开始计时
      paintBar(0);
    } catch (e) {
      /* 网络抖动：保持当前码，下个周期再试 */
    } finally {
      refreshing = false;
    }
  }

  function paintBar(elapsed) {
    // 倒计时：蓝色块贴左端，右边缘随剩余时间从右向左退缩
    const remain = Math.max(0, Math.min(1, (cycleSeconds - elapsed) / cycleSeconds));
    barFill.style.width = (remain * 100).toFixed(2) + '%';
    const left = Math.max(0, Math.ceil(cycleSeconds - elapsed));
    refreshTip.textContent = left > 0 ? `二维码 ${left} 秒后自动刷新` : '正在刷新二维码…';
  }

  function tick() {
    const elapsed = (Date.now() - cycleStart) / 1000;
    paintBar(elapsed);
    if (elapsed >= cycleSeconds && Date.now() - lastAttempt > 2000) {
      refreshQr(false);
    }
  }

  async function loadLive() {
    const r = await fetch(`/api/activity/${ACTIVITY_ID}/live?_=${Date.now()}`);
    if (!r.ok) return;
    const d = await r.json();
    document.getElementById('stat-in').textContent = d.checked_in;
    document.getElementById('stat-out').textContent = d.checked_out;
    const list = document.getElementById('feed-list');
    const html = d.records.map(x => `
      <div class="feed-row">
        <span class="who">${esc(x.name)}</span>
        <span class="campus">${esc(x.campus)}</span>
        <span class="time">${esc(x.checked_in_at)}</span>
        <span class="tag ${x.checked_out_at ? 'g' : ''}">${x.checked_out_at ? '已签离' : '已签到'}</span>
      </div>`).join('') || '<div class="feed-row"><span class="campus">暂无签到记录</span></div>';
    list.innerHTML = html;
  }

  // 中奖名单：5 秒轮询公开抽签接口；同一轮不重复重绘，避免滚动动画被重置
  let lastWinnerRound = -1;

  async function loadWinners() {
    let d;
    try {
      const r = await fetch(`/api/activity/${ACTIVITY_ID}/lottery?_=${Date.now()}`);
      if (!r.ok) return;
      d = await r.json();
    } catch (e) {
      return;   // 网络抖动：保持当前画面，下个周期再试
    }
    const list = document.getElementById('winner-list');
    const empty = document.getElementById('winner-empty');
    const roundTag = document.getElementById('winner-round');
    const marquee = document.getElementById('winner-marquee');
    if (!list) return;
    const latest = (d && d.latest) || null;
    const winners = (latest && Array.isArray(latest.winners)) ? latest.winners : [];
    if (!winners.length) {
      lastWinnerRound = -1;
      if (empty) empty.style.display = '';
      if (roundTag) roundTag.textContent = '';
      if (marquee) marquee.innerHTML = '';
      return;
    }
    if (empty) empty.style.display = 'none';
    if (roundTag) roundTag.textContent = '最新一轮 · ' + (latest.created_at || '');
    if (latest.id === lastWinnerRound) return;   // 同一轮不重复重绘
    lastWinnerRound = latest.id;
    const items = winners.map(w => {
      const name = esc((w && w.name) || '');
      const campus = esc((w && w.campus) || '');
      return `<span class="winner-item"><span class="winner-name">${name}</span>` +
        (campus ? `<span class="winner-campus">${campus}</span>` : '') + '</span>';
    }).join('');
    if (marquee) {
      marquee.innerHTML = `<div class="winner-marquee-inner">${items}</div>`;
    }
  }

  function esc(s) {
    return (s === null || s === undefined ? '' : String(s)).replace(/[&<>"]/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  switchBtn.addEventListener('click', () => setMode(mode === 'in' ? 'out' : 'in'));

  refreshQr(true);
  tick();
  setInterval(tick, 250);
  loadLive();
  setInterval(loadLive, 2000);
  loadWinners();
  setInterval(loadWinners, 5000);
})();
