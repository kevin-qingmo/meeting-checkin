// 验收：海岸铁道绿配色 + 「全校活动」联动置灰
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots';
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

  // ---- 新建活动页：全校活动联动 ----
  await p.goto(BASE + '/admin/activity/new', { waitUntil: 'networkidle2' });
  await p.screenshot({ path: OUT + '/g1-form-normal.png' });

  const before = await p.evaluate(() => ({
    stageDisabled: Array.from(document.querySelectorAll('input[name=stage_ids]')).filter(i => i.disabled).length,
    subjectDisabled: Array.from(document.querySelectorAll('input[name=subject_ids]')).filter(i => i.disabled).length,
    campusDisabled: Array.from(document.querySelectorAll('input[name=campus_ids]')).filter(i => i.disabled).length,
  }));
  ok(before.stageDisabled === 0 && before.subjectDisabled === 0, '未勾选时学段/学科可点');

  // 勾选「全校活动」
  await p.click('#school_wide');
  await sleep(400);
  const after = await p.evaluate(() => ({
    stageDisabled: Array.from(document.querySelectorAll('input[name=stage_ids]')).filter(i => i.disabled).length,
    subjectDisabled: Array.from(document.querySelectorAll('input[name=subject_ids]')).filter(i => i.disabled).length,
    campusDisabled: Array.from(document.querySelectorAll('input[name=campus_ids]')).filter(i => i.disabled).length,
    offLabels: document.querySelectorAll('.check.off').length,
    tipVisible: getComputedStyle(document.getElementById('schoolWideTip')).display !== 'none',
    stageFieldOff: document.getElementById('stageField').classList.contains('off'),
    subjectFieldOff: document.getElementById('subjectField').classList.contains('off'),
  }));
  ok(after.stageDisabled > 0, '勾选后学段全部禁用 (' + after.stageDisabled + ')');
  ok(after.subjectDisabled > 0, '勾选后学科全部禁用 (' + after.subjectDisabled + ')');
  ok(after.campusDisabled > 0, '勾选后单个校区禁用 (' + after.campusDisabled + ')');
  ok(after.offLabels > 0, '禁用项已置灰 (.check.off = ' + after.offLabels + ')');
  ok(after.tipVisible, '提示语已显示');
  ok(after.stageFieldOff && after.subjectFieldOff, '学段/学科区块变灰');
  await p.screenshot({ path: OUT + '/g2-form-schoolwide.png' });

  // 取消勾选 → 恢复可选
  await p.click('#school_wide');
  await sleep(300);
  const restored = await p.evaluate(() => ({
    stageDisabled: Array.from(document.querySelectorAll('input[name=stage_ids]')).filter(i => i.disabled).length,
    offLabels: document.querySelectorAll('.check.off').length,
  }));
  ok(restored.stageDisabled === 0 && restored.offLabels === 0, '取消勾选后恢复可选');

  // ---- 真正提交全校活动 ----
  await p.click('#school_wide');
  await sleep(200);
  await p.evaluate(() => {
    const set = (sel, v) => { const el = document.querySelector(sel); el.value = v; el.dispatchEvent(new Event('change', { bubbles: true })); };
    set('input[name=title]', '全校教师大会');
    set('input[name=start_at]', '2026-11-20T08:30');
    set('input[name=end_at]', '2026-11-20T11:30');
  });
  await Promise.all([p.waitForNavigation({ waitUntil: 'networkidle2' }), p.click('button[type=submit]')]);
  const body = await p.evaluate(() => document.body.innerText);
  ok(body.includes('全校教师大会'), '全校活动已创建并跳转看板');
  ok(body.includes('全校活动'), '看板显示「全校活动」标记');
  await p.screenshot({ path: OUT + '/g3-dashboard-schoolwide.png' });

  // 活动列表
  await p.goto(BASE + '/admin/', { waitUntil: 'networkidle2' });
  await p.screenshot({ path: OUT + '/g4-activities.png' });

  // ---- 配色核验 ----
  const colors = await p.evaluate(() => {
    const cs = getComputedStyle(document.body);
    return { bg: cs.backgroundImage.slice(0, 90), text: cs.color };
  });
  console.log('  body 背景:', colors.bg);
  console.log('  body 文字:', colors.text);
  const appCss = await (await fetch(BASE + '/static/css/app.css')).text();
  ok(appCss.includes('#3B5645'), 'app.css 主色为海岸铁道绿 #3B5645');
  const boardCss = await (await fetch(BASE + '/static/css/board.css')).text();
  ok(boardCss.includes('#4E6B55') && boardCss.includes('#3B5645'), 'board.css 为深墨绿变体');

  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
