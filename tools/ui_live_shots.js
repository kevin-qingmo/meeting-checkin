// 线上实拍：登录页 / 活动列表 / 签到大屏 / 手机扫码页（公网实例）
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots';
const BASE = 'https://web-production-9fe1faa8.up.railway.app';
const USER = process.argv[2] || 'admin';
const PWD = process.argv[3] || 'nk2026';

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu']
  });

  const p1 = await browser.newPage();
  await p1.setViewport({ width: 1280, height: 860 });
  await p1.goto(BASE + '/login', { waitUntil: 'networkidle2' });
  await p1.screenshot({ path: OUT + '/live-1-login.png' });

  await p1.type('input[name=username]', USER);
  await p1.type('input[name=password]', PWD);
  await Promise.all([
    p1.waitForNavigation({ waitUntil: 'networkidle2' }),
    p1.click('button[type=submit]')
  ]);
  const afterLogin = p1.url();
  console.log('登录后地址:', afterLogin);

  await p1.goto(BASE + '/admin/', { waitUntil: 'networkidle2' });
  await p1.screenshot({ path: OUT + '/live-2-admin.png' });

  // 找第一个活动 id
  const ids = await p1.evaluate(() => Array.from(document.querySelectorAll('a[href*="/admin/activity/"]'))
    .map(a => (a.getAttribute('href').match(/activity\/(\d+)/) || [])[1]).filter(Boolean));
  const aid = ids[0];
  console.log('活动 id:', aid);

  if (aid) {
    const p2 = await browser.newPage();
    await p2.setViewport({ width: 1600, height: 1000 });
    await p2.goto(BASE + '/board/' + aid, { waitUntil: 'networkidle2' });
    await new Promise(r => setTimeout(r, 1800));
    await p2.screenshot({ path: OUT + '/live-3-board.png' });

    const p3 = await browser.newPage();
    await p3.setViewport({ width: 430, height: 860, isMobile: true, deviceScaleFactor: 2 });
    await p3.goto(BASE + '/scan/' + aid + '?t=demo&c=1&m=in', { waitUntil: 'networkidle2' });
    await p3.screenshot({ path: OUT + '/live-4-scan.png' });
  }

  console.log('live screenshots done');
  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
