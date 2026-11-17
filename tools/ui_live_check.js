// 线上验收：海岸铁道绿配色 + 「全校活动」联动
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots';
const BASE = 'https://web-production-9fe1faa8.up.railway.app';
const USER = process.argv[2] || 'tmp_palette_2026';
const PWD = process.argv[3] || 'Tmp#2026palette';

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
  await p.screenshot({ path: OUT + '/L1-login.png' });
  await p.type('input[name=username]', USER);
  await p.type('input[name=password]', PWD);
  await Promise.all([p.waitForNavigation({ waitUntil: 'networkidle2' }), p.click('button[type=submit]')]);
  ok(/\/admin/.test(p.url()), '线上登录成功');

  // 新建活动页 + 全校活动联动
  await p.goto(BASE + '/admin/activity/new', { waitUntil: 'networkidle2' });
  await sleep(300);
  await p.screenshot({ path: OUT + '/L2-form-normal.png' });
  await p.click('#school_wide');
  await sleep(400);
  const st = await p.evaluate(() => ({
    stage: Array.from(document.querySelectorAll('input[name=stage_ids]')).filter(i => i.disabled).length,
    subject: Array.from(document.querySelectorAll('input[name=subject_ids]')).filter(i => i.disabled).length,
    campus: Array.from(document.querySelectorAll('input[name=campus_ids]')).filter(i => i.disabled).length,
    off: document.querySelectorAll('.check.off').length,
  }));
  ok(st.stage > 0 && st.subject > 0, '线上：勾选全校活动后学段/学科置灰不可选');
  ok(st.campus > 0, '线上：单个校区同时置灰');
  await p.screenshot({ path: OUT + '/L3-form-schoolwide.png' });

  // 提交一个全校活动（仅用于取景，随后删除）
  await p.evaluate(() => {
    const set = (sel, v) => { const el = document.querySelector(sel); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); };
    set('input[name=title]', '全校教师大会');
    set('input[name=start_at]', '2026-11-20T08:30');
    set('input[name=end_at]', '2026-11-20T11:30');
  });
  await Promise.all([p.waitForNavigation({ waitUntil: 'networkidle2' }), p.click('button[type=submit]')]);
  const body = await p.evaluate(() => document.body.innerText);
  ok(body.includes('全校教师大会'), '线上：全校活动创建成功');
  ok(body.includes('全校活动'), '线上：看板显示「全校活动」标记');
  const aid = (p.url().match(/activity\/(\d+)/) || [])[1];
  console.log('  活动 id =', aid);

  // 补录几条，页面有内容
  for (const [name, phone, campus] of [
    ['王老师', '13900000001', '和慧南路校区'],
    ['李老师', '13900000002', '雅馨路校区'],
    ['张老师', '13900000003', '敬慧路校区']
  ]) {
    await p.evaluate(async (aid, n, ph, c) => {
      const res = await fetch(`/api/activity/${aid}/manual`, {
        method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: new URLSearchParams({ name: n, phone: ph, campus: c })
      });
      return res.json();
    }, aid, name, phone, campus);
  }
  await p.goto(BASE + '/admin/activity/' + aid + '/dashboard', { waitUntil: 'networkidle2' });
  await sleep(1200);
  await p.screenshot({ path: OUT + '/L4-dashboard.png' });

  // 大屏
  const p2 = await browser.newPage();
  await p2.setViewport({ width: 1600, height: 1000 });
  await p2.goto(BASE + '/board/' + aid, { waitUntil: 'networkidle2' });
  await sleep(2500);
  await p2.screenshot({ path: OUT + '/L5-board.png' });

  // 手机扫码页
  const qr = await p.evaluate(async aid => (await fetch(`/api/board/${aid}/qr?mode=in`)).json(), aid);
  const p3 = await browser.newPage();
  await p3.setViewport({ width: 430, height: 880, isMobile: true, deviceScaleFactor: 2 });
  await p3.goto(`${BASE}/scan/${aid}?t=${encodeURIComponent(qr.token)}&c=${encodeURIComponent(qr.cycle)}&m=in`,
    { waitUntil: 'networkidle2' });
  await sleep(700);
  await p3.screenshot({ path: OUT + '/L6-scan.png' });

  // 清理：删除临时活动
  const del = await p.evaluate(async aid => {
    const res = await fetch(`/admin/activity/${aid}/delete`, { method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' } });
    return res.status;
  }, aid);
  console.log('  删除临时活动状态码:', del);

  await browser.close();
  console.log('done');
})().catch(e => { console.error('FAIL', e); process.exit(1); });
