/* 签到大屏：二维码 / 现场码 20 秒轮换 + 实时数据 2 秒轮询 */
(function () {
  let mode = INITIAL_MODE || 'in';
  let cycle = -1;
  let cycleSeconds = 20;
  let tickTimer = null;

  const qrImg = document.getElementById('qr-img');
  const siteCode = document.getElementById('site-code');
  const barFill = document.getElementById('bar-fill');
  const refreshTip = document.getElementById('refresh-tip');
  const badge = document.getElementById('mode-badge');
  const switchBtn = document.getElementById('switch-mode');

  function setMode(m) {
    mode = m;
    badge.textContent = m === 'out' ? '签离模式' : '签到模式';
    badge.classList.toggle('out', m === 'out');
    switchBtn.textContent = m === 'out' ? '切换为签到模式' : '切换为签离模式';
    refreshQr(true);
  }

  async function refreshQr(force) {
    const r = await fetch(`/api/board/${ACTIVITY_ID}/qr?mode=${mode}&_=${Date.now()}`);
    if (!r.ok) return;
    const d = await r.json();
    if (!force && d.cycle === cycle) return;
    cycle = d.cycle;
    cycleSeconds = d.cycle_seconds || 20;
    qrImg.src = d.qr_png + '&_=' + Date.now();
    siteCode.textContent = d.site_code;
    paintBar(0);
  }

  function paintBar(elapsed) {
    // 倒计时：蓝色块贴左端，右边缘随剩余时间从右向左退缩
    const remain = Math.max(0, Math.min(1, (cycleSeconds - elapsed) / cycleSeconds));
    barFill.style.width = (remain * 100).toFixed(2) + '%';
    const left = Math.max(0, Math.ceil(cycleSeconds - elapsed));
    refreshTip.textContent = `二维码 ${left} 秒后自动刷新`;
  }

  function tick() {
    const elapsed = (Date.now() / 1000) % cycleSeconds;
    paintBar(elapsed);
    const curCycle = Math.floor(Date.now() / 1000 / cycleSeconds);
    if (curCycle !== cycle) refreshQr(false);
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
        <span class="tag ${x.checked_out_at ? 'y' : 'g'}">${x.checked_out_at ? '已签离' : '已签到'}</span>
      </div>`).join('') || '<div class="feed-row"><span class="campus">暂无签到记录</span></div>';
    list.innerHTML = html;
  }

  function esc(s) {
    return (s === null || s === undefined ? '' : String(s)).replace(/[&<>"]/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]));
  }

  switchBtn.addEventListener('click', () => setMode(mode === 'in' ? 'out' : 'in'));

  refreshQr(true);
  tick();
  tickTimer = setInterval(tick, 250);
  loadLive();
  setInterval(loadLive, 2000);
})();
