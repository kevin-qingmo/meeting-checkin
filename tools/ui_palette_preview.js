// 配色改版预览：登录页 / 后台活动列表 / 活动后台 / 签到大屏 / 手机扫码页
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots';
const BASE = 'http://localhost:5055';

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu']
  });

  // 1. 登录页
  const p1 = await browser.newPage();
  await p1.setViewport({ width: 1280, height: 860 });
  await p1.goto(BASE + '/login', { waitUntil: 'networkidle2' });
  await p1.screenshot({ path: OUT + '/p1-login.png' });

  // 登录
  await p1.type('input[name=username]', 'admin');
  await p1.type('input[name=password]', 'admin123456');
  await Promise.all([
    p1.waitForNavigation({ waitUntil: 'networkidle2' }),
    p1.click('button[type=submit]')
  ]);

  // 2. 活动列表
  await p1.goto(BASE + '/admin/', { waitUntil: 'networkidle2' });
  await p1.screenshot({ path: OUT + '/p2-activities.png' });

  // 3. 活动后台
  await p1.goto(BASE + '/admin/activity/1/dashboard', { waitUntil: 'networkidle2' });
  await p1.screenshot({ path: OUT + '/p3-dashboard.png' });

  // 4. 签到大屏
  const p2 = await browser.newPage();
  await p2.setViewport({ width: 1600, height: 1000 });
  await p2.goto(BASE + '/board/1', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 1500));
  await p2.screenshot({ path: OUT + '/p4-board.png' });

  // 5. 手机扫码页
  const p3 = await browser.newPage();
  await p3.setViewport({ width: 430, height: 860, isMobile: true, deviceScaleFactor: 2 });
  await p3.goto(BASE + '/scan/1?t=demo&c=1&m=in', { waitUntil: 'networkidle2' });
  await p3.screenshot({ path: OUT + '/p5-scan.png' });

  console.log('screenshots done');
  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
