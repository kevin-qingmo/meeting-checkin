// 验证「切换签到/签离模式 → 二维码刷新 + 倒计时重新计时」
// 断言：切换后 qr-src 变化、现场码变化、倒计时条回到接近满格、随后重新收缩
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots';
const BASE = 'http://localhost:5055';

const sleep = (ms) => new Promise(r => setTimeout(r, ms));

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });
  await page.goto(BASE + '/login', { waitUntil: 'networkidle2' });
  await page.type('input[name=username]', 'admin');
  await page.type('input[name=password]', 'admin123456');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2' }),
    page.click('button[type=submit]')
  ]);
  await page.goto(BASE + '/board/1', { waitUntil: 'networkidle2' });
  await sleep(1500);

  const snap = async () => await page.evaluate(() => {
    const bar = document.querySelector('.bar');
    const fill = document.getElementById('bar-fill');
    const bb = bar.getBoundingClientRect();
    const fb = fill.getBoundingClientRect();
    return {
      qrSrc: document.getElementById('qr-img').getAttribute('src'),
      siteCode: document.getElementById('site-code').textContent.trim(),
      badge: document.getElementById('mode-badge').textContent.trim(),
      btn: document.getElementById('switch-mode').textContent.trim(),
      tip: document.getElementById('refresh-tip').textContent.trim(),
      fillPct: +(fb.width / bb.width * 100).toFixed(1)
    };
  });

  const before = await snap();
  await (await page.$('.qr-card')).screenshot({ path: OUT + '/10-mode-before.png' });

  // 点击切换模式
  await page.click('#switch-mode');
  await sleep(1200);
  const after = await snap();
  await (await page.$('.qr-card')).screenshot({ path: OUT + '/11-mode-after.png' });

  // 再等 4 秒，倒计时应重新收缩（说明是重新计时，而不是卡住或跳回旧刻度）
  await sleep(4000);
  const later = await snap();

  const checks = {
    qr_changed: before.qrSrc !== after.qrSrc,
    site_code_changed: before.siteCode !== after.siteCode,
    badge_switched: before.badge !== after.badge && after.badge === '签离模式',
    bar_restarted: after.fillPct > 90,
    bar_shrinking_again: later.fillPct < after.fillPct - 5,
    tip_countdown_reset: /秒后自动刷新/.test(after.tip)
  };
  const pass = Object.values(checks).every(Boolean);
  console.log(JSON.stringify({ before, after, later, checks, pass }, null, 2));
  await browser.close();
  process.exit(pass ? 0 : 1);
})().catch(e => { console.error('FAIL', e); process.exit(1); });
