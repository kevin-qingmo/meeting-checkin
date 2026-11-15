// 本地界面验收：登录 → 抓取大屏 / 后台 / 手机端截图
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const fs = require('fs');

const OUT = 'D:/MiniMax工作站/签到系统/_screenshots';
const BASE = 'http://localhost:5055';

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000, deviceScaleFactor: 1 });

  const errors = [];
  page.on('pageerror', e => errors.push('pageerror: ' + e.message));
  page.on('console', m => { if (m.type() === 'error') errors.push('console: ' + m.text()); });

  // 1. 登录页
  await page.goto(BASE + '/login', { waitUntil: 'networkidle2' });
  await page.screenshot({ path: OUT + '/1-login.png' });

  // 2. 登录
  await page.type('input[name=username]', 'admin');
  await page.type('input[name=password]', 'admin123456');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2' }),
    page.click('button[type=submit]')
  ]);

  // 3. 活动列表
  await page.goto(BASE + '/admin/', { waitUntil: 'networkidle2' });
  await page.screenshot({ path: OUT + '/2-activities.png' });

  // 4. 签到大屏
  await page.goto(BASE + '/board/1', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2500));
  await page.screenshot({ path: OUT + '/3-board.png' });

  // 5. 核对大屏二维码与现场码是否与接口一致
  const board = await page.evaluate(async () => {
    const r = await fetch('/api/board/1/qr');
    const d = await r.json();
    return {
      api_site_code: d.site_code,
      dom_site_code: document.getElementById('site-code').textContent.trim(),
      stat_in: document.getElementById('stat-in').textContent.trim(),
      stat_out: document.getElementById('stat-out').textContent.trim(),
      feed_rows: document.querySelectorAll('#feed-list .feed-row').length,
      qr_img_loaded: (() => { const i = document.getElementById('qr-img'); return i.complete && i.naturalWidth > 0; })()
    };
  });

  // 6. 后台面板
  await page.goto(BASE + '/admin/activity/1/dashboard', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2500));
  await page.screenshot({ path: OUT + '/4-dashboard.png' });

  // 7. 手机端扫码页（独立无 cookie 会话）
  const phone = await browser.newPage();
  await phone.setViewport({ width: 414, height: 860, deviceScaleFactor: 2, isMobile: true });
  const qr = await page.evaluate(async () => {
    const r = await fetch('/api/board/1/qr');
    const d = await r.json();
    return { t: d.token, c: d.cycle, code: d.site_code };
  });
  await phone.goto(`${BASE}/scan/1?t=${qr.t}&c=${qr.c}&m=in`, { waitUntil: 'networkidle2' });
  await phone.screenshot({ path: OUT + '/5-scan-mobile.png' });

  // 8. 真机提交一次签到（手机端页面）——现场码每 20 秒刷新，提交前现取
  const qr2 = await page.evaluate(async () => {
    const r = await fetch('/api/board/1/qr');
    const d = await r.json();
    return { t: d.token, c: d.cycle, code: d.site_code };
  });
  await phone.goto(`${BASE}/scan/1?t=${qr2.t}&c=${qr2.c}&m=in`, { waitUntil: 'networkidle2' });
  const phoneNo = '135' + String(Math.floor(Math.random() * 100000000)).padStart(8, '0');
  await phone.type('input[name=name]', '测试老师');
  await phone.type('input[name=phone]', phoneNo);
  await phone.select('select[name=campus]', '敬慧路校区');
  await phone.type('input[name=site_code]', qr2.code);
  await phone.click('button[type=submit]');
  await phone.waitForFunction(() => {
    const el = document.getElementById('result');
    return el && el.className.indexOf('result') === 0 && el.className.length > 6;
  }, { timeout: 10000 });
  const resultText = await phone.$eval('#result', e => e.textContent.trim());
  const resultClass = await phone.$eval('#result', e => e.className);
  await phone.screenshot({ path: OUT + '/6-scan-success.png' });

  // 9. 回到大屏确认数字 +1
  await page.goto(BASE + '/board/1', { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 2500));
  const after = await page.evaluate(() => ({
    url: location.href,
    stat_in: (document.getElementById('stat-in') || {}).textContent,
    stat_out: (document.getElementById('stat-out') || {}).textContent,
    has_board: !!document.getElementById('feed-list')
  }));
  await page.screenshot({ path: OUT + '/7-board-after.png' });

  console.log(JSON.stringify({ board, after, resultText, errors }, null, 2));
  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
