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
