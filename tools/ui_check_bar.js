// 验证倒计时条：蓝色块应从右端向左收缩
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots';

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu']
  });
  const page = await browser.newPage();
  await page.setViewport({ width: 1600, height: 1000 });
  await page.goto('http://localhost:5055/login', { waitUntil: 'networkidle2' });
  await page.type('input[name=username]', 'admin');
  await page.type('input[name=password]', 'admin123456');
  await Promise.all([
    page.waitForNavigation({ waitUntil: 'networkidle2' }),
    page.click('button[type=submit]')
  ]);
  await page.goto('http://localhost:5055/board/1', { waitUntil: 'networkidle2' });

  const snap = async () => await page.evaluate(() => {
    const bar = document.querySelector('.bar');
    const fill = document.getElementById('bar-fill');
    const bb = bar.getBoundingClientRect();
    const fb = fill.getBoundingClientRect();
    return {
      tip: document.getElementById('refresh-tip').textContent.trim(),
      fillWidthPct: +(fb.width / bb.width * 100).toFixed(1),
      fillLeftGapPct: +((fb.left - bb.left) / bb.width * 100).toFixed(1),
      fillRightGapPct: +((bb.right - fb.right) / bb.width * 100).toFixed(1)
    };
  });

  await new Promise(r => setTimeout(r, 1200));
  const a = await snap();
  await (await page.$('.qr-card')).screenshot({ path: OUT + '/8-bar-t1.png' });

  await new Promise(r => setTimeout(r, 7000));
  const b = await snap();
  await (await page.$('.qr-card')).screenshot({ path: OUT + '/9-bar-t2.png' });

  console.log(JSON.stringify({ a, b }, null, 2));
  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
