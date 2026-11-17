// 线上登录页补拍（等待图片解码完成）
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots';
const BASE = 'https://web-production-9fe1faa8.up.railway.app';

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new', args: ['--no-sandbox', '--disable-gpu']
  });
  const p = await browser.newPage();
  await p.setViewport({ width: 1280, height: 860 });
  await p.goto(BASE + '/login', { waitUntil: 'networkidle2' });
  await p.waitForFunction(() => {
    const img = document.querySelector('.school-logo');
    return img && img.complete && img.naturalWidth > 0;
  }, { timeout: 15000 });
  await new Promise(r => setTimeout(r, 500));
  const info = await p.evaluate(() => {
    const img = document.querySelector('.school-logo');
    const r = img.getBoundingClientRect();
    return { natural: img.naturalWidth + 'x' + img.naturalHeight, shown: Math.round(r.width) + 'x' + Math.round(r.height) };
  });
  console.log('校徽加载:', JSON.stringify(info));
  await p.screenshot({ path: OUT + '/L1-login.png' });
  await browser.close();
  console.log('ok');
})().catch(e => { console.error('FAIL', e); process.exit(1); });
