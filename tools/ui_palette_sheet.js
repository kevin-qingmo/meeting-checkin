// 拼接指定配色的对比图：node tools/ui_palette_sheet.js key1 key2 ...
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const fs = require('fs');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots/palette';
const keys = process.argv.slice(2);
const META = {
  'ql-warm': ['青莲紫 × 暖米白', '主色不变，纸底换成暖米白，柔和耐看'],
  'ql-cool': ['青莲紫 × 冷静灰蓝', '海鸥蓝降为辅色，理性稳重'],
  'ql-magenta': ['青莲紫 × 品红', '同色系更鲜艳，喜庆、辨识度高'],
  'ql-teal': ['青莲紫 × 松石绿', '紫绿对比色，沉稳有层次'],
  'qinglian-purple': ['青莲紫 · 基准', '浅紫纸底 + 深紫大屏']
};

(async () => {
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new', args: ['--no-sandbox', '--disable-gpu']
  });
  const p = await browser.newPage();
  await p.setViewport({ width: 1700, height: 1200 });
  const html = `<html><head><meta charset="utf-8"><style>
    body{margin:0;background:#f2f2f2;font-family:"Microsoft YaHei",sans-serif}
    .row{display:flex;gap:14px;padding:14px 16px;align-items:flex-start}
    .meta{width:200px;padding-top:6px}
    .meta h3{margin:0 0 6px;font-size:21px;color:#222}
    .meta p{margin:0;font-size:13px;color:#666;line-height:1.5}
    img{width:440px;border:1px solid #ddd;border-radius:8px;background:#fff}
    img.b{width:540px}img.s{width:300px}
  </style></head><body>
  ${keys.map(k => `<div class="row">
    <div class="meta"><h3>${META[k][0]}</h3><p>${META[k][1]}</p></div>
    <img class="b" src="${k}-board.png">
    <img src="${k}-dashboard.png">
    <img class="s" src="${k}-scan.png">
  </div>`).join('')}
  </body></html>`;
  const f = `${OUT}/_sheet2.html`;
  fs.writeFileSync(f, html, 'utf8');
  await p.goto('file:///' + f.replace(/\\/g, '/'), { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 800));
  await p.screenshot({ path: `${OUT}/_variants-sheet.png`, fullPage: true });
  await browser.close();
  console.log('ok:', `${OUT}/_variants-sheet.png`);
})().catch(e => { console.error('FAIL', e); process.exit(1); });
