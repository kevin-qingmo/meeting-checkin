// 配色候选预览：把真实界面按不同配色方案渲染并拼图对比
// 用法：node tools/ui_palette_candidates.js <活动ID>
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const fs = require('fs');
const OUT = 'D:/MiniMax工作站/签到系统/_screenshots/palette';
const BASE = 'http://localhost:5055';
const ACT = process.argv[2] || '3';
const ONLY = (process.argv[3] || '').split(',').filter(Boolean);

const PALETTES = [
  {
    key: 'ql-warm',
    name: '青莲紫 × 暖米白',
    tag: '主色不变，纸底换成暖米白，柔和耐看',
    bg: ['#FBF7F2', '#F3EBE4', '#EBE0D8'], card: '#FFFFFF', card2: '#FBF6F1', line: '#E8DCD2',
    text: '#3A2E33', muted: '#8A6E75', faint: '#A9969C', primary: '#7E0C6E', primaryD: '#5A0750',
    light: '#E0B4DC', green: '#6B8E7F', orange: '#BA9A6D', red: '#C96A6A',
    board: ['#8E1E7C', '#5E0A52', '#3B0836'], boardSub: '#EBD3E8', boardBlue: '#E0B4DC', boardGreen: '#8FC7AE',
    accent: '#C489C1', headBg: '#F7F0EA', hover: '#FBF6F1', line2: '#EFE4DA'
  },
  {
    key: 'ql-cool',
    name: '青莲紫 × 冷静灰蓝',
    tag: '海鸥蓝降为辅色，理性稳重',
    bg: ['#F4F5F9', '#EAEDF4', '#E0E5EF'], card: '#FFFFFF', card2: '#F7F8FC', line: '#DEE2EC',
    text: '#2F3340', muted: '#5A7286', faint: '#93A3B3', primary: '#7E0C6E', primaryD: '#5A0750',
    light: '#AFD8EE', green: '#6B8E7F', orange: '#BA9A6D', red: '#C96A6A',
    board: ['#7A2C8E', '#4A1568', '#2A0B44'], boardSub: '#DCD3E9', boardBlue: '#AFD8EE', boardGreen: '#8FC7AE',
    accent: '#B98FD4', headBg: '#EFF1F7', hover: '#F7F8FC', line2: '#E6E9F1'
  },
  {
    key: 'ql-magenta',
    name: '青莲紫 × 品红',
    tag: '同色系更鲜艳，喜庆、辨识度高',
    bg: ['#FCF2F8', '#F6E6F1', '#EFDAE9'], card: '#FFFFFF', card2: '#FDF5FA', line: '#F0D8E9',
    text: '#3B1335', muted: '#8A507F', faint: '#AE83A3', primary: '#7E0C6E', primaryD: '#5A0750',
    light: '#F0A8D8', green: '#6B8E7F', orange: '#BA9A6D', red: '#C96A6A',
    board: ['#B02A93', '#7E0C6E', '#4A0750'], boardSub: '#F3D5EC', boardBlue: '#F0A8D8', boardGreen: '#8FC7AE',
    accent: '#E0459B', headBg: '#FAEDF5', hover: '#FDF5FA', line2: '#F2DEEC'
  },
  {
    key: 'ql-teal',
    name: '青莲紫 × 松石绿',
    tag: '紫绿对比色，沉稳有层次',
    bg: ['#F3F6F4', '#E7EEEB', '#DBE4E1'], card: '#FFFFFF', card2: '#F6F9F8', line: '#D8E3DF',
    text: '#26302D', muted: '#3F6B60', faint: '#84A099', primary: '#7E0C6E', primaryD: '#5A0750',
    light: '#7FC3B4', green: '#4F8C7A', orange: '#BA9A6D', red: '#C96A6A',
    board: ['#7A2A8E', '#4A1568', '#2A0B44'], boardSub: '#D6E9E4', boardBlue: '#D9A8D6', boardGreen: '#9FD6C7',
    accent: '#7FC3B4', headBg: '#EDF3F1', hover: '#F6F9F8', line2: '#E1E9E6'
  },
  {
    key: 'qinglian-purple',
    name: '青莲紫 · 南开校色',
    tag: '基准 RGB(126,12,110)，浅紫纸底 + 深紫大屏',
    bg: ['#F8F3F9', '#F0E7F2', '#E7DBEA'], card: '#FFFFFF', card2: '#FBF7FC', line: '#E6D9E7',
    text: '#3A1A35', muted: '#7A5676', faint: '#A28CA2', primary: '#7E0C6E', primaryD: '#5A0750',
    light: '#D9A8D6', green: '#6B8E7F', orange: '#BA9A6D', red: '#C96A6A',
    board: ['#A2338F', '#7E0C6E', '#520649'], boardSub: '#EBD6E9', boardBlue: '#D9A8D6', boardGreen: '#8FC7AE',
    accent: '#C489C1', headBg: '#F6EFF6', hover: '#FBF7FC', line2: '#EDE2EE'
  },
  {
    key: 'rail-green',
    name: '海岸铁道绿',
    tag: '复古低饱和，适合长时间阅读',
    bg: ['#F7F6EE', '#EFEFDF', '#E7E7D6'], card: '#FFFFFF', card2: '#F6F6EC', line: '#DFE3D2',
    text: '#343635', muted: '#4E6B55', faint: '#8A9484', primary: '#3B5645', primaryD: '#2C4234',
    light: '#ADCEDF', green: '#5E8C6E', orange: '#BA9A6D', red: '#C96A6A',
    board: ['#4E6B55', '#3B5645', '#2A3D31'], boardSub: '#CFE0D2', boardBlue: '#ADCEDF', boardGreen: '#9FCBB0',
    accent: '#BA9A6D', headBg: '#F0F2E6', hover: '#F6F6EC', line2: '#E4E7D8'
  },
  {
    key: 'nordic-warm',
    name: '日式北欧暖调',
    tag: '暖纸底 + 沙金陶土，安静高级',
    bg: ['#F5F1EC', '#EBE5DC', '#E2DACF'], card: '#FFFAF3', card2: '#FBF6EE', line: '#F0E8D8',
    text: '#2C2A26', muted: '#6B5D4F', faint: '#8A7C6E', primary: '#8A6B52', primaryD: '#6B5340',
    light: '#D4B48C', green: '#6B8E7F', orange: '#BA9A6D', red: '#C96A6A',
    board: ['#4A4439', '#2C2A26', '#1F1E1B'], boardSub: '#DED5C7', boardBlue: '#E0C79C', boardGreen: '#A8C4B4',
    accent: '#D4B48C', headBg: '#F7F1E7', hover: '#FBF6EE', line2: '#EFE6D6'
  },
  {
    key: 'harbor-lime',
    name: '港湾青柠',
    tag: '清新明快，适合学生与年轻教师',
    bg: ['#F2F7F8', '#E2EAEE', '#D8E4EA'], card: '#FFFFFF', card2: '#F4F9FA', line: '#D3E1E6',
    text: '#2F4A52', muted: '#6EA89C', faint: '#AAAfA8', primary: '#5F9FB8', primaryD: '#3E7E98',
    light: '#89BEE0', green: '#A5C174', orange: '#BA9A6D', red: '#C96A6A',
    board: ['#6FA8BE', '#4C8298', '#37677C'], boardSub: '#DDF0F5', boardBlue: '#A9DCF5', boardGreen: '#C3DDA0',
    accent: '#A5C174', headBg: '#ECF4F6', hover: '#F4F9FA', line2: '#DFEAED'
  },
  {
    key: 'seagull',
    name: '海鸥蓝（当前）',
    tag: '现行方案，仅作对照',
    bg: ['#EDF5F9', '#E4EFF7', '#DCEAF4'], card: '#FFFFFF', card2: '#F7FBFD', line: '#D8E8F0',
    text: '#265171', muted: '#548490', faint: '#8AA8B3', primary: '#265171', primaryD: '#1B4359',
    light: '#AFD8EE', green: '#6B8E7F', orange: '#BA9A6D', red: '#C96A6A',
    board: ['#2E6183', '#265171', '#1B4359'], boardSub: '#BFDCEC', boardBlue: '#7CC0E8', boardGreen: '#8FC7AE',
    accent: '#4E93B8', headBg: '#F2F8FC', hover: '#F7FBFD', line2: '#E4EFF6'
  }
];

function css(p) {
  const rgba = (hex, a) => {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255},${(n >> 8) & 255},${n & 255},${a})`;
  };
  return `
body{background:linear-gradient(160deg,${p.bg[0]} 0%,${p.bg[1]} 55%,${p.bg[2]} 100%) !important;color:${p.text} !important}
.topbar{background:${rgba(p.card, .88)} !important;border-bottom-color:${p.line} !important}
.brand{color:${p.primary} !important}
.logo{background:linear-gradient(135deg,${p.primary},${p.muted}) !important}
.topnav a{color:${p.muted} !important}
.topnav a:hover{background:${p.card2} !important;color:${p.primary} !important}
.topnav a.on{background:${rgba(p.light, .4)} !important;color:${p.primaryD} !important}
.who{color:${p.muted} !important}
.card{background:${p.card} !important;border-color:${p.line} !important;box-shadow:0 10px 28px rgba(0,0,0,.05) !important}
.card h2{color:${p.primary} !important}
.card .sub{color:${p.muted} !important}
.stat{background:${p.card} !important;border-color:${p.line} !important;box-shadow:0 10px 28px rgba(0,0,0,.05) !important}
.stat .num{color:${p.primary} !important}
.stat .num.green{color:${p.green} !important}
.stat .num.orange{color:${p.orange} !important}
.stat .lbl{color:${p.muted} !important}
th{color:${p.muted} !important;background:${p.headBg} !important}
td{border-bottom-color:${p.line2} !important}
tbody tr:hover{background:${p.hover} !important}
.tag{background:${rgba(p.light, .42)} !important;color:${p.primaryD} !important;border-color:${rgba(p.primary, .18)} !important}
.tag.g{background:${rgba(p.green, .16)} !important;color:${p.green} !important;border-color:${rgba(p.green, .35)} !important}
.tag.y{background:${rgba(p.orange, .18)} !important;color:${p.orange} !important;border-color:${rgba(p.orange, .38)} !important}
.tag.r{background:${rgba(p.red, .14)} !important;color:${p.red} !important;border-color:${rgba(p.red, .32)} !important}
.muted{color:${p.muted} !important}
.kpi{color:${p.primary} !important}.kpi.g{color:${p.green} !important}
.act-title{color:${p.primary} !important}.act-meta{color:${p.muted} !important}
.btn{background:${p.primary} !important;color:#fff !important}
.btn:hover{background:${p.primaryD} !important}
.btn-ghost{background:${p.card2} !important;border-color:${p.line} !important;color:${p.primary} !important}
.btn-green{background:${p.green} !important}.btn-red{background:${p.red} !important}
input[type=text],input[type=password],input[type=datetime-local],input[type=number],input[type=tel],select,textarea{
  background:${p.card2} !important;color:${p.text} !important;border-color:${p.line} !important}
input:focus,select:focus,textarea:focus{border-color:${p.primary} !important;box-shadow:0 0 0 3px ${rgba(p.light, .45)} !important}
.flash-success{background:${rgba(p.green, .13)} !important;border-color:${rgba(p.green, .38)} !important;color:${p.green} !important}
.flash-error{background:${rgba(p.red, .12)} !important;border-color:${rgba(p.red, .36)} !important;color:${p.red} !important}
.flash-warning{background:${rgba(p.orange, .16)} !important;border-color:${rgba(p.orange, .42)} !important;color:${p.orange} !important}
.empty{color:${p.faint} !important}
.login-card{background:${p.card} !important;border-color:${p.line} !important;box-shadow:0 18px 44px rgba(0,0,0,.08) !important}
.login-card h1{color:${p.primary} !important}.login-card .sub{color:${p.muted} !important}
.check{background:${p.card2} !important;border-color:${p.line} !important;color:${p.text} !important}
.check.on{border-color:${p.primary} !important;background:${rgba(p.light, .34)} !important}
.modal{background:${rgba(p.primary, .34)} !important}
.modal-box{background:${p.card} !important;border-color:${p.line} !important}
.modal-box h3{color:${p.primary} !important}
.empty,.small{color:${p.faint} !important}
.small{color:${p.muted} !important}

/* 大屏 */
.board-page{background:radial-gradient(1200px 700px at 50% -10%, ${p.board[0]} 0%, ${p.board[1]} 58%, ${p.board[2]} 100%) !important}
.board-head h1{color:#fff !important}
.board-sub{color:${p.boardSub} !important}
.mode-badge{background:${rgba(p.green, .2)} !important;color:${p.boardGreen} !important;border-color:${rgba(p.green, .45)} !important}
.qr-card{background:#fff !important;color:${p.primary} !important;box-shadow:0 22px 50px rgba(0,0,0,.4) !important}
.qr-frame{border-color:${p.light} !important}
.qr-tip{color:${p.primary} !important}.qr-hint{color:${p.faint} !important}
.site-code-label{color:${p.muted} !important}.site-code{color:${p.primary} !important}
.bar{background:${p.card2} !important}
.bar-fill{background:linear-gradient(90deg,${p.primary},${p.accent}) !important}
.refresh-tip{color:${p.faint} !important}
.stat-card{background:rgba(255,255,255,.08) !important;border-color:rgba(255,255,255,.16) !important}
.stat-card .num{color:#fff !important}
.stat-card.blue .num{color:${p.boardBlue} !important}
.stat-card.green .num{color:${p.boardGreen} !important}
.stat-card .lbl{color:${p.boardSub} !important}
.feed{background:rgba(255,255,255,.06) !important;border-color:rgba(255,255,255,.14) !important}
.feed-head{color:#F2F7F7 !important}
.feed-row .who{color:#fff !important}.feed-row .campus{color:${p.boardSub} !important}
.board-page .feed-row .tag{background:${rgba(p.boardBlue, .2)} !important;color:${p.boardBlue} !important;border-color:${rgba(p.boardBlue, .42)} !important}
.board-page .feed-row .tag.g{background:${rgba(p.boardGreen, .2)} !important;color:${p.boardGreen} !important;border-color:${rgba(p.boardGreen, .45)} !important}
.switch-mode{background:${p.accent} !important;color:#fff !important}
.switch-mode:hover{background:${p.primaryD} !important}

/* 手机扫码页（模板内联样式，需 !important 覆盖） */
.scan-head h1{color:${p.primary} !important}
.scan-head .meta{color:${p.muted} !important}
.scan-card{background:${p.card} !important;border-color:${p.line} !important;color:${p.primary} !important;box-shadow:0 12px 32px rgba(0,0,0,.08) !important}
.scan-card label{color:${p.muted} !important}
.scan-card input,.scan-card select{background:${p.card2} !important;color:${p.text} !important;border-color:${p.line} !important}
.hint{color:${p.faint} !important}
`;
}

(async () => {
  if (!fs.existsSync(OUT)) fs.mkdirSync(OUT, { recursive: true });
  const browser = await puppeteer.launch({
    executablePath: 'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',
    headless: 'new',
    args: ['--no-sandbox', '--disable-gpu']
  });

  // 登录
  const p1 = await browser.newPage();
  await p1.setViewport({ width: 1360, height: 900 });
  await p1.goto(BASE + '/login', { waitUntil: 'networkidle2' });
  await p1.type('input[name=username]', 'admin');
  await p1.type('input[name=password]', 'admin123456');
  await Promise.all([
    p1.waitForNavigation({ waitUntil: 'networkidle2' }),
    p1.click('button[type=submit]')
  ]);
  console.log('登录:', p1.url());

  const p2 = await browser.newPage();
  await p2.setViewport({ width: 1600, height: 1000 });
  const p3 = await browser.newPage();
  await p3.setViewport({ width: 430, height: 880, isMobile: true, deviceScaleFactor: 2 });

  const shots = [];
  for (const pal of PALETTES) {
    if (ONLY.length && !ONLY.includes(pal.key)) continue;
    const style = css(pal);
    // 后台看板
    await p1.goto(BASE + '/admin/activity/' + ACT + '/dashboard', { waitUntil: 'networkidle2' });
    await p1.addStyleTag({ content: style });
    await new Promise(r => setTimeout(r, 900));
    const f1 = `${OUT}/${pal.key}-dashboard.png`;
    await p1.screenshot({ path: f1 });

    // 大屏
    await p2.goto(BASE + '/board/' + ACT, { waitUntil: 'networkidle2' });
    await p2.addStyleTag({ content: style });
    await new Promise(r => setTimeout(r, 2200));
    const f2 = `${OUT}/${pal.key}-board.png`;
    await p2.screenshot({ path: f2 });

    // 手机扫码页
    await p3.goto(`${BASE}/scan/${ACT}?t=demo&c=1&m=in`, { waitUntil: 'networkidle2' });
    await p3.addStyleTag({ content: style });
    await new Promise(r => setTimeout(r, 700));
    const f3 = `${OUT}/${pal.key}-scan.png`;
    await p3.screenshot({ path: f3 });

    shots.push({ pal, f1, f2, f3 });
    console.log('已渲染:', pal.name);
  }

  // 拼图：每套一行三图（写成本地 HTML 再用 file:// 打开，图片才能正常加载）
  const comp = await browser.newPage();
  await comp.setViewport({ width: 1700, height: 1400 });
  const html = `<html><head><meta charset="utf-8"><style>
    body{margin:0;background:#f2f2f2;font-family:"Microsoft YaHei",sans-serif}
    .row{display:flex;gap:14px;padding:16px;align-items:flex-start}
    .meta{width:190px;padding-top:8px}
    .meta h3{margin:0 0 6px;font-size:22px;color:#222}
    .meta p{margin:0 0 10px;font-size:13px;color:#666;line-height:1.5}
    .sw{display:flex;gap:6px;margin-top:8px}
    .sw i{width:26px;height:26px;border-radius:6px;display:block;border:1px solid rgba(0,0,0,.12)}
    img{width:430px;border:1px solid #ddd;border-radius:8px;background:#fff}
    img.b{width:520px}
    img.s{width:300px}
  </style></head><body>
  ${shots.map(s => `<div class="row">
    <div class="meta"><h3>${s.pal.name}</h3><p>${s.pal.tag}</p>
      <div class="sw">${[s.pal.primary, s.pal.light, s.pal.card2, s.pal.green, s.pal.orange].map(c => `<i style="background:${c}"></i>`).join('')}</div>
    </div>
    <img class="b" src="${s.pal.key}-board.png">
    <img src="${s.pal.key}-dashboard.png">
    <img class="s" src="${s.pal.key}-scan.png">
  </div>`).join('')}
  </body></html>`;
  const sheetPath = `${OUT}/_sheet.html`;
  fs.writeFileSync(sheetPath, html, 'utf8');
  await comp.goto('file:///' + sheetPath.replace(/\\/g, '/'), { waitUntil: 'networkidle2' });
  await new Promise(r => setTimeout(r, 900));
  await comp.screenshot({ path: `${OUT}/_contact-sheet.png`, fullPage: true });
  console.log('拼图完成:', `${OUT}/_contact-sheet.png`);

  await browser.close();
})().catch(e => { console.error('FAIL', e); process.exit(1); });
