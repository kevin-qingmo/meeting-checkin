// 线上实拍（配色改版）：登录页 → 活动列表 → 新建临时活动 → 后台看板 → 签到大屏 → 手机扫码页
// 结束后自动删除临时活动，恢复干净的生产库
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots';
const BASE = process.argv[2] || 'https://web-production-9fe1faa8.up.railway.app';
const USER = process.argv[3] || 'admin';
const PWD = process.argv[4] || 'nk2026';

const sleep = ms => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu']
  });
  const p = await browser.newPage();
  await p.setViewport({ width: 1360, height: 900 });

  // 1) 登录页
  await p.goto(BASE + '/login', { waitUntil: 'networkidle2' });
  await sleep(400);
  await p.screenshot({ path: OUT + '/live-1-login.png' });
  console.log('[1] 登录页已截图');

  // 2) 登录
  await p.type('input[name=username]', USER);
  await p.type('input[name=password]', PWD);
  await Promise.all([
    p.waitForNavigation({ waitUntil: 'networkidle2' }),
    p.click('button[type=submit]')
  ]);
  console.log('[2] 登录后地址:', p.url());
  if (!/\/admin/.test(p.url())) {
    const flash = await p.evaluate(() => {
      const el = document.querySelector('.flash');
      return el ? el.textContent.trim() : '(无提示)';
    });
    console.log('!! 登录未成功，页面提示：', flash);
    await p.screenshot({ path: OUT + '/live-x-login-failed.png' });
    await browser.close();
    process.exit(2);
  }

  // 3) 活动列表
  await p.goto(BASE + '/admin/', { waitUntil: 'networkidle2' });
  await sleep(400);
  await p.screenshot({ path: OUT + '/live-2-admin.png' });
  console.log('[3] 活动列表已截图');

  // 4) 新建临时活动
  await p.goto(BASE + '/admin/activity/new', { waitUntil: 'networkidle2' });
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const fmt = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  const start = new Date(now.getTime() - 30 * 60000);
  const end = new Date(now.getTime() + 3 * 3600000);
  await p.evaluate((s, e) => {
    const set = (sel, v) => {
      const el = document.querySelector(sel);
      el.value = v;
      el.dispatchEvent(new Event('input', { bubbles: true }));
      el.dispatchEvent(new Event('change', { bubbles: true }));
    };
    set('input[name=title]', '配色验收·临时活动');
    set('input[name=start_at]', s);
    set('input[name=end_at]', e);
    set('input[name=location]', '和慧南路校区 报告厅');
    const cb = document.querySelector('input[name=campus_ids]');
    if (cb && !cb.checked) cb.click();
  }, fmt(start), fmt(end));
  await Promise.all([
    p.waitForNavigation({ waitUntil: 'networkidle2' }),
    p.click('button[type=submit]')
  ]);
  const m = (p.url().match(/activity\/(\d+)/) || [])[1];
  console.log('[4] 临时活动 id:', m, '地址:', p.url());
  if (!m) {
    await p.screenshot({ path: OUT + '/live-x-activity-failed.png' });
    await browser.close();
    process.exit(3);
  }

  // 5) 后台看板 + 补录几条，页面才有内容
  const demo = [
    ['王老师', '13900000001', '和慧南路校区'],
    ['李老师', '13900000002', '雅馨路校区'],
    ['张老师', '13900000003', '敬慧路校区'],
    ['刘老师', '13900000004', '和慧南路校区']
  ];
  for (const [name, phone, campus] of demo) {
    const r = await p.evaluate(async (aid, n, ph, c) => {
      const body = new URLSearchParams({ name: n, phone: ph, campus: c });
      const res = await fetch(`/api/activity/${aid}/manual`, { method: 'POST', body });
      return (await res.json()).ok;
    }, m, name, phone, campus);
    console.log('   补录', name, r);
  }
  await p.goto(BASE + '/admin/activity/' + m + '/dashboard', { waitUntil: 'networkidle2' });
  await sleep(1200);
  await p.screenshot({ path: OUT + '/live-3-dashboard.png' });
  console.log('[5] 后台看板已截图');

  // 6) 签到大屏
  const p2 = await browser.newPage();
  await p2.setViewport({ width: 1600, height: 1000 });
  await p2.goto(BASE + '/board/' + m, { waitUntil: 'networkidle2' });
  await sleep(2500);
  await p2.screenshot({ path: OUT + '/live-4-board.png' });
  console.log('[6] 签到大屏已截图');

  // 7) 手机扫码页（取真实 token/cycle）
  const qr = await p.evaluate(async aid => {
    const res = await fetch(`/api/board/${aid}/qr?mode=in`);
    return await res.json();
  }, m);
  const p3 = await browser.newPage();
  await p3.setViewport({ width: 430, height: 880, isMobile: true, deviceScaleFactor: 2 });
  await p3.goto(`${BASE}/scan/${m}?t=${encodeURIComponent(qr.token)}&c=${encodeURIComponent(qr.cycle)}&m=in`,
    { waitUntil: 'networkidle2' });
  await sleep(700);
  await p3.screenshot({ path: OUT + '/live-5-scan.png' });
  console.log('[7] 手机扫码页已截图');

  // 8) 删除临时活动，恢复生产库干净
  const del = await p.evaluate(async aid => {
    const res = await fetch(`/admin/activity/${aid}/delete`, {
      method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' }
    });
    return res.status;
  }, m);
  console.log('[8] 删除临时活动状态码:', del);

  await browser.close();
  console.log('done');
})().catch(e => { console.error('FAIL', e); process.exit(1); });
