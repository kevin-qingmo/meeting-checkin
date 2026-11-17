// 端到端：后台抽奖 → 弹层 → 大屏出现中奖名单
// 注意：脚本必须可重复运行——每次运行用唯一手机号/姓名补录人员，
// 否则第二次运行时这批人已进入「已中奖」集合（去重键 p:<手机号>），
// 而「排除已中奖」默认勾选 → 候选池为空 → 服务端 400 → 弹层不出现 → 假失败。
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const BASE = process.env.LOTTERY_BASE || 'http://localhost:5055';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SHOT = 'D:/MiniMax工作站/签到系统/_screenshots';

// 每次运行唯一标识：用于生成不重复的手机号与姓名
const RUN = String(Date.now());
const SUFFIX = RUN.slice(-8);            // 8 位数字
const PHONE_A = '139' + SUFFIX;           // 11 位手机号
const PHONE_B = '138' + SUFFIX;
const PHONE_C = '137' + SUFFIX;
const NAME_A = '抽奖甲' + SUFFIX.slice(-4);
const NAME_B = '抽奖乙' + SUFFIX.slice(-4);
const NAME_C = '抽奖丙' + SUFFIX.slice(-4);

// 断言失败时打印的上下文
const ctx = { run: RUN, aid: null, people: [], lotteryMsg: '', latest: null, winnersText: '', historyRows: 0 };
let failures = 0;
const ok = (c, m) => {
  if (!c) failures++;
  console.log((c ? '  PASS  ' : '! FAIL  ') + m);
  if (!c) console.log('        失败上下文: ' + JSON.stringify(ctx, null, 2));
};

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
  ctx.aid = aid;
  ok(!!aid, '找到活动 id: ' + aid);
  if (!aid) { await browser.close(); process.exit(1); }

  // 先补录三个人并签到（手机号/姓名本次运行唯一，保证脚本可重复运行）
  const people = [[NAME_A, PHONE_A], [NAME_B, PHONE_B], [NAME_C, PHONE_C]];
  ctx.people = people.map(x => x[0] + '/' + x[1]);
  const added = await p.evaluate(async (aid, people) => {
    const out = [];
    for (const [n, ph] of people) {
      const r = await fetch(`/api/activity/${aid}/manual`, {
        method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: new URLSearchParams({ name: n, phone: ph, campus: '和慧南路校区' })
      });
      out.push({ name: n, phone: ph, status: r.status });
    }
    return out;
  }, aid, people);
  ctx.added = added;
  ok(added.every(x => x.status === 200), '补录三名可抽奖人员: ' + JSON.stringify(added));

  // 打开后台抽签
  await p.goto(BASE + '/admin/activity/' + aid + '/dashboard', { waitUntil: 'networkidle2' });
  await sleep(500);

  // 抽取人数非法时前端应拦截并给出中文提示（不发请求）
  await p.evaluate(() => { document.getElementById('lottery-count').value = '0'; });
  await p.click('#lottery-btn');
  await sleep(400);
  const badCountMsg = await p.evaluate(() => document.getElementById('lottery-msg').textContent.trim());
  ok(badCountMsg.includes('大于 0 的整数'), '抽取人数非法时前端拦截并提示: ' + badCountMsg);

  // 正常抽取
  await p.evaluate(() => { document.getElementById('lottery-count').value = '1'; });
  await p.click('#lottery-btn');
  await sleep(1500);
  ctx.lotteryMsg = await p.evaluate(() => document.getElementById('lottery-msg').textContent.trim());
  ctx.latest = await p.evaluate(async (aid) => {
    const r = await fetch(`/api/activity/${aid}/lottery`);
    const d = await r.json();
    return d.latest ? { id: d.latest.id, draw_count: d.latest.draw_count, winners: d.latest.winners, operator: d.latest.operator } : null;
  }, aid);
  const overlayShown = await p.evaluate(() => document.getElementById('lottery-overlay').classList.contains('show'));
  ok(overlayShown, '抽奖后弹层出现（接口 message: ' + ctx.lotteryMsg + '）');
  ctx.winnersText = await p.evaluate(() => document.getElementById('lottery-winners').innerText.trim());
  ok(ctx.winnersText.length > 0, '弹层内显示中奖名单: ' + ctx.winnersText.replace(/\n/g, ' '));
  await p.screenshot({ path: SHOT + '/lottery-overlay.png' });

  // ESC 键关闭弹层
  await p.keyboard.press('Escape');
  await sleep(300);
  const overlayClosedByEsc = await p.evaluate(() => !document.getElementById('lottery-overlay').classList.contains('show'));
  ok(overlayClosedByEsc, 'ESC 键可关闭弹层');

  // 再抽一次，验证点击遮罩空白处可关闭（点击中奖名单本体不关闭）
  await p.click('#lottery-btn');
  await sleep(1500);
  const clickInsideKeepsOpen = await p.evaluate(() => {
    const box = document.querySelector('.lottery-overlay-box');
    if (!box) return false;
    box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    return document.getElementById('lottery-overlay').classList.contains('show');
  });
  ok(clickInsideKeepsOpen, '点击中奖名单本体不关闭弹层');
  await p.mouse.click(10, 10);   // 遮罩空白处
  await sleep(300);
  const overlayClosedByBackdrop = await p.evaluate(() => !document.getElementById('lottery-overlay').classList.contains('show'));
  ok(overlayClosedByBackdrop, '点击遮罩空白处可关闭弹层');

  // 历史记录表格有记录
  ctx.historyRows = await p.evaluate(() => document.querySelectorAll('#lottery-history-body tr').length);
  ok(ctx.historyRows >= 1, '历史抽奖记录已写入表格（行数 ' + ctx.historyRows + '）');

  // 大屏展示
  const p2 = await browser.newPage();
  await p2.setViewport({ width: 1600, height: 1000 });
  await p2.goto(BASE + '/board/' + aid, { waitUntil: 'networkidle2' });
  await sleep(3000);
  const boardText = await p2.evaluate(() => document.getElementById('winner-list') ? document.getElementById('winner-list').innerText : '');
  ok(boardText.trim().length > 0, '大屏显示中奖名单: ' + boardText.replace(/\n/g, ' '));
  await p2.screenshot({ path: SHOT + '/lottery-board.png' });

  await browser.close();
  if (failures) { console.log('\n共 ' + failures + ' 条断言失败'); process.exit(1); }
  console.log('\n全部断言通过');
})().catch(e => { console.error('FAIL', e); console.log('失败上下文: ' + JSON.stringify(ctx, null, 2)); process.exit(1); });
