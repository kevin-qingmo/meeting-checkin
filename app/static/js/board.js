/* 签到大屏：二维码 / 现场码 20 秒轮换 + 实时数据轮询 + 中奖名单轮询
 *
 * 关键点：
 *  - 倒计时锚定在「取到这轮码的时刻」（cycleStart），而不是服务器整点，
 *    这样切换签到/签离模式后倒计时会真正从 20 秒重新开始。
 *  - 码与现场码由服务端按 (活动, 周期, 模式) 派生，切换模式必然换新码。
 *
 * 弱网适配（服务器在境外节点，国内链路丢包严重时单次请求可能耗时几十秒）：
 *  - 所有请求带超时（AbortController），不让连接无限期挂住；
 *  - 请求在途不叠加，避免把浏览器的并发连接池打满（那会让整页「加载不出来」）；
 *  - 失败后指数退避重试（2s → 4s → 8s → 15s 封顶），成功即恢复原频率。
 */
(function () {
  const FETCH_TIMEOUT = 8000;   // 单次请求超时（毫秒）
  const BASE_LIVE = 2000;       // 实时数据正常轮询间隔
  const BASE_WINNERS = 5000;    // 中奖名单正常轮询间隔
  const BACKOFF_MAX = 15000;    // 退避上限

  let mode = INITIAL_MODE || 'in';
  let cycle = -1;
  let cycleSeconds = 20;
  let cycleStart = Date.now();
  let lastAttempt = 0;

  let liveFail = 0;
  let winnersFail = 0;
  let qrFail = 0;

  const qrImg = document.getElementById('qr-img');
  const siteCode = document.getElementById('site-code');
  const barFill = document.getElementById('bar-fill');
  const refreshTip = document.getElementById('refresh-tip');
  const badge = document.getElementById('mode-badge');
  const switchBtn = document.getElementById('switch-mode');

  function backoff(fail) {
    return Math.min(BACKOFF_MAX, 2000 * Math.pow(2, Math.min(fail, 3)));
  }

  // 带超时的 JSON 请求：超时或失败都抛错，由调用方统一退避处理
  async function getJSON(url) {
    const ctrl = new AbortController();
    const timer = setTimeout(function () { ctrl.abort(); }, FETCH_TIMEOUT);
    try {
      const r = await fetch(url, { signal: ctrl.signal, cache: 'no-store' });
      if (!r.ok) throw new Error('http ' + r.status);
      return await r.json();
    } finally {
      clearTimeout(timer);
    }
  }

  function setMode(m) {
    if (m === mode) return;
    mode = m;
    badge.textContent = m === 'out' ? '签离模式' : '签到模式';
    badge.classList.toggle('out', m === 'out');
    switchBtn.textContent = m === 'out' ? '切换为签到模式' : '切换为签离模式';
    cycle = -1;          // 强制换新码
    refreshQr(true);     // 取新码 + 重新计时
  }

  let qrLoading = false;

  async function refreshQr(force) {
    if (qrLoading) return;
    qrLoading = true;
    lastAttempt = Date.now();
    try {
      const d = await getJSON(`/api/board/${ACTIVITY_ID}/qr?mode=${mode}&_=${Date.now()}`);
      qrFail = 0;
      if (!force && d.cycle === cycle && d.mode === mode) return;
      cycle = d.cycle;
      cycleSeconds = d.cycle_seconds || 20;
      qrImg.src = d.qr_png + '&_=' + Date.now();
      siteCode.textContent = d.site_code;
      cycleStart = Date.now();   // 这一轮从此刻开始计时
      paintBar(0);
    } catch (e) {
      // 网络抖动 / 超时：保持当前码，下个周期再试
      qrFail++;
      if (refreshTip) {
        refreshTip.textContent = '网络较慢，正在重新获取二维码…';
      }
    } finally {
      qrLoading = false;
    }
  }

  function paintBar(elapsed) {
    // 倒计时：蓝色块贴左端，右边缘随剩余时间从右向左退缩
    const remain = Math.max(0, Math.min(1, (cycleSeconds - elapsed) / cycleSeconds));
    barFill.style.width = (remain * 100).toFixed(2) + '%';
    const left = Math.max(0, Math.ceil(cycleSeconds - elapsed));
    if (qrFail > 0) return;   // 网络异常时保留提示文案，不覆盖
    refreshTip.textContent = left > 0 ? `二维码 ${left} 秒后自动刷新` : '正在刷新二维码…';
  }

  function tick() {
    const elapsed = (Date.now() - cycleStart) / 1000;
    paintBar(elapsed);
    if (elapsed >= cycleSeconds && Date.now() - lastAttempt > 2000) {
      refreshQr(false);
    }
  }

  let liveLoading = false;

  async function loadLive() {
    if (liveLoading) return;   // 上一轮还没回来，本次跳过（防止请求堆积）
    liveLoading = true;
    try {
      const d = await getJSON(`/api/activity/${ACTIVITY_ID}/live?_=${Date.now()}`);
      liveFail = 0;
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
    } catch (e) {
      liveFail++;   // 网络异常：保持当前画面，退避后重试
    } finally {
      liveLoading = false;
    }
  }

  // 中奖名单：轮询公开抽签接口；同一轮不重复重绘，避免滚动动画被重置
  let lastWinnerRound = -1;
  let winnersLoading = false;   // in-flight 防抖：慢网络下不叠加请求

  async function loadWinners() {
    if (winnersLoading) return;   // 上一轮还没回来，本次跳过
    winnersLoading = true;
    let d;
    try {
      d = await getJSON(`/api/activity/${ACTIVITY_ID}/lottery?_=${Date.now()}`);
      winnersFail = 0;
    } catch (e) {
      winnersFail++;
      return;   // 网络抖动：保持当前画面，下个周期再试
    } finally {
      winnersLoading = false;
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
    if (latest.id === lastWinnerRound) return;   // 同一轮不重复重绘（含轮次文案）
    lastWinnerRound = latest.id;
    if (empty) empty.style.display = 'none';
    if (roundTag) roundTag.textContent = '最新一轮 · ' + (latest.created_at || '');
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

  // 自调度轮询：成功用基础间隔，失败按指数退避，避免弱网下请求堆积
  async function loop(fn, base, failCounter) {
    await fn();
    const delay = failCounter() > 0 ? backoff(failCounter()) : base;
    setTimeout(function () { loop(fn, base, failCounter); }, delay);
  }

  switchBtn.addEventListener('click', () => setMode(mode === 'in' ? 'out' : 'in'));

  refreshQr(true);
  tick();
  setInterval(tick, 250);
  loop(loadLive, BASE_LIVE, function () { return liveFail; });
  loop(loadWinners, BASE_WINNERS, function () { return winnersFail; });
})();
