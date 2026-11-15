// 截取后台活动列表页，验证「删除」按钮与二次确认提示已就位
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
  await page.goto('http://localhost:5055/admin/', { waitUntil: 'networkidle2' });

  const info = await page.evaluate(() => {
    const btns = Array.from(document.querySelectorAll('button.btn-red')).map(b => ({
      text: b.textContent.trim(),
      confirmText: (b.closest('form')?.getAttribute('onsubmit') || '').slice(0, 60),
      action: b.closest('form')?.getAttribute('action')
    }));
    return { count: btns.length, sample: btns.slice(0, 2) };
  });
  console.log(JSON.stringify(info, null, 2));
  await page.screenshot({ path: OUT + '/12-admin-delete.png', fullPage: true });
  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
