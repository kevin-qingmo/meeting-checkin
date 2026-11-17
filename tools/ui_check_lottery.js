// 端到端：后台抽奖 → 弹层 → 大屏出现中奖名单
// 注意：脚本必须可重复运行——每次运行用唯一手机号/姓名补录人员，
// 否则第二次运行时这批人已进入「已中奖」集合（去重键 p:<手机号>），
// 而「排除已中奖」默认勾选 → 候选池为空 → 服务端 400 → 弹层不出现 → 假失败。
const puppeteer = require('D:/软件/MiniMax/.minimax/skills/house-plan-designer/scripts/node_modules/puppeteer-core');
const BASE = process.env.LOTTERY_BASE || 'http://localhost:5055';
const sleep = ms => new Promise(r => setTimeout(r, ms));
const SHOT = 'D:/MiniMax工作站/签到系统/_screenshots';

// 每次运行唯一标识：用于生成不重复的手机号与姓名
const RUN = String(Date.now());
const SUFFIX = RUN.slice(-8);            // 8 位数字
const PHONE_A = '139' + SUFFIX;           // 11 位手机号
const PHONE_B = '138' + SUFFIX;
const PHONE_C = '137' + SUFFIX;
const NAME_A = '抽奖甲' + SUFFIX.slice(-4);
const NAME_B = '抽奖乙' + SUFFIX.slice(-4);
const NAME_C = '抽奖丙' + SUFFIX.slice(-4);

// 断言失败时打印的上下文
const ctx = { run: RUN, aid: null, people: [], lotteryMsg: '', latest: null, winnersText: '', historyRows: 0 };
let failures = 0;
const ok = (c, m) => {
  if (!c) failures++;
  console.log((c ? '  PASS  ' : '! FAIL  ') + m);
  if (!c) console.log('        失败上下文: ' + JSON.stringify(ctx, null, 2));
};

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

  // 用一个「抽签端到端校验」专用活动：候选池里只有本脚本补录的三个人，
  // 因此「中奖人必然出自这三人之一」成立，大屏断言才有意义。
  // 专用活动只增不减（app/routes/admin.py 的活动删除在有抽奖轮次时会 500，属既有缺陷，不在本任务范围），
  // 每次运行前先清空它的签到人员，保证候选池干净。
  const MARK = '抽签端到端校验';
  const now = new Date();
  const pad = n => String(n).padStart(2, '0');
  const fmt = d => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
  await p.goto(BASE + '/admin/', { waitUntil: 'networkidle2' });
  let aid = await p.evaluate((mark) => {
    for (const tr of Array.from(document.querySelectorAll('table tbody tr'))) {
      const t = tr.querySelector('.act-title');
      if (!t || t.textContent.trim() !== mark) continue;
      const a = tr.querySelector('a[href*="/admin/activity/"]');
      const m = a && (a.getAttribute('href').match(/activity\/(\d+)/) || []);
      if (m) return m[1];
    }
    return null;
  }, MARK);
  if (!aid) {
    const created = await p.evaluate(async (title, startAt, endAt) => {
      const body = new URLSearchParams({
        title, start_at: startAt, end_at: endAt,
        location: '端到端校验', campus_ids: '和慧南路校区',
      });
      const r = await fetch('/admin/activity/new', {
        method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' }, body,
      });
      return { url: r.url, status: r.status };
    }, MARK, fmt(new Date(now.getTime() - 3600e3)), fmt(new Date(now.getTime() + 7200e3)));
    aid = (created.url.match(/activity\/(\d+)/) || [])[1];
    ok(!!aid, '创建专用活动「' + MARK + '」→ id ' + aid);
  } else {
    ok(true, '复用专用活动「' + MARK + '」→ id ' + aid);
  }
  ctx.aid = aid;
  if (!aid) { await browser.close(); process.exit(1); }

  // 清空专用活动里可能残留的签到人员（只影响本脚本自己的专用活动）
  const purge = async () => p.evaluate(async (aid) => {
    let n = 0;
    for (let i = 0; i < 20; i++) {
      const r = await fetch(`/api/activity/${aid}/live?_=${Date.now()}`);
      if (!r.ok) break;
      const d = await r.json();
      const ids = (d.records || []).map(x => x.id).filter(Boolean);
      if (!ids.length) break;
      for (const id of ids) {
        await fetch(`/api/checkin/${id}/delete`, {
          method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' },
        });
        n++;
      }
    }
    return n;
  }, aid);
  const purged = await purge();
  ok(true, '清空专用活动残留签到人员: ' + purged + ' 条');

  // 先补录三个人并签到（手机号/姓名本次运行唯一，保证脚本可重复运行）
  const people = [[NAME_A, PHONE_A], [NAME_B, PHONE_B], [NAME_C, PHONE_C]];
  ctx.people = people.map(x => x[0] + '/' + x[1]);
  const added = await p.evaluate(async (aid, people) => {
    const out = [];
    for (const [n, ph] of people) {
      const r = await fetch(`/api/activity/${aid}/manual`, {
        method: 'POST', headers: { 'X-Requested-With': 'XMLHttpRequest' },
        body: new URLSearchParams({ name: n, phone: ph, campus: '和慧南路校区' })
      });
      out.push({ name: n, phone: ph, status: r.status });
    }
    return out;
  }, aid, people);
  ctx.added = added;
  ok(added.every(x => x.status === 200), '补录三名可抽奖人员: ' + JSON.stringify(added));

  // 打开后台抽签
  await p.goto(BASE + '/admin/activity/' + aid + '/dashboard', { waitUntil: 'networkidle2' });
  await sleep(500);

  // 抽取人数非法时前端应拦截并给出中文提示（不发请求）
  await p.evaluate(() => { document.getElementById('lottery-count').value = '0'; });
  await p.click('#lottery-btn');
  await sleep(400);
  const badCountMsg = await p.evaluate(() => document.getElementById('lottery-msg').textContent.trim());
  ok(badCountMsg.includes('大于 0 的整数'), '抽取人数非法时前端拦截并提示: ' + badCountMsg);

  // 正常抽取
  await p.evaluate(() => { document.getElementById('lottery-count').value = '1'; });
  await p.click('#lottery-btn');
  await sleep(1500);
  ctx.lotteryMsg = await p.evaluate(() => document.getElementById('lottery-msg').textContent.trim());
  ctx.latest = await p.evaluate(async (aid) => {
    const r = await fetch(`/api/activity/${aid}/lottery`);
    const d = await r.json();
    return d.latest ? { id: d.latest.id, draw_count: d.latest.draw_count, winners: d.latest.winners, operator: d.latest.operator } : null;
  }, aid);
  const overlayShown = await p.evaluate(() => document.getElementById('lottery-overlay').classList.contains('show'));
  ok(overlayShown, '抽奖后弹层出现（接口 message: ' + ctx.lotteryMsg + '）');
  ctx.winnersText = await p.evaluate(() => document.getElementById('lottery-winners').innerText.trim());
  ok(ctx.winnersText.length > 0, '弹层内显示中奖名单: ' + ctx.winnersText.replace(/\n/g, ' '));
  await p.screenshot({ path: SHOT + '/lottery-overlay.png' });

  // ESC 键关闭弹层
  await p.keyboard.press('Escape');
  await sleep(300);
  const overlayClosedByEsc = await p.evaluate(() => !document.getElementById('lottery-overlay').classList.contains('show'));
  ok(overlayClosedByEsc, 'ESC 键可关闭弹层');

  // 再抽一次，验证点击遮罩空白处可关闭（点击中奖名单本体不关闭）
  await p.click('#lottery-btn');
  await sleep(1500);
  const clickInsideKeepsOpen = await p.evaluate(() => {
    const box = document.querySelector('.lottery-overlay-box');
    if (!box) return false;
    box.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    return document.getElementById('lottery-overlay').classList.contains('show');
  });
  ok(clickInsideKeepsOpen, '点击中奖名单本体不关闭弹层');
  await p.mouse.click(10, 10);   // 遮罩空白处
  await sleep(300);
  const overlayClosedByBackdrop = await p.evaluate(() => !document.getElementById('lottery-overlay').classList.contains('show'));
  ok(overlayClosedByBackdrop, '点击遮罩空白处可关闭弹层');

  // 历史记录表格有记录
  ctx.historyRows = await p.evaluate(() => document.querySelectorAll('#lottery-history-body tr').length);
  ok(ctx.historyRows >= 1, '历史抽奖记录已写入表格（行数 ' + ctx.historyRows + '）');

  // 大屏展示：断言必须能区分「真的渲染出中奖人」与「只显示静态占位文字」
  const latest = await p.evaluate(async (aid) => {
    const r = await fetch(`/api/activity/${aid}/lottery?_=${Date.now()}`);
    const d = await r.json();
    return d.latest ? { id: d.latest.id, winners: d.latest.winners } : null;
  }, aid);
  ctx.latest = latest;
  const latestNames = ((latest && latest.winners) || []).map(w => (w && w.name) || '').filter(Boolean);

  const p2 = await browser.newPage();
  await p2.setViewport({ width: 1600, height: 1000 });
  await p2.goto(BASE + '/board/' + aid, { waitUntil: 'networkidle2' });
  await sleep(3000);
  const board = await p2.evaluate(() => {
    const list = document.getElementById('winner-list');
    const empty = document.getElementById('winner-empty');
    return {
      text: list ? list.innerText.trim() : '',
      emptyDisplay: empty ? getComputedStyle(empty).display : '(缺失)',
      emptyVisible: empty ? !!(empty.offsetParent || empty.getClientRects().length) : null,
    };
  });
  ctx.board = board;
  const boardText = board.text.replace(/\n/g, ' ');
  // 1) 空状态占位必须已隐藏（否则说明没渲染中奖名单，只是留着静态文案）
  ok(board.emptyDisplay === 'none' || board.emptyVisible === false,
    '大屏空状态占位已隐藏（#winner-empty 不可见）: display=' + board.emptyDisplay + ', visible=' + board.emptyVisible);
  // 2) 必须出现本轮中奖人姓名（本活动候选池只有本脚本补录的三人）
  const hit = [NAME_A, NAME_B, NAME_C].find(n => board.text.includes(n));
  ok(!!hit, '大屏显示中奖人姓名（应为 ' + [NAME_A, NAME_B, NAME_C].join(' / ') + ' 之一）: 实际文本="' + boardText + '"');
  // 3) 必须与公开接口的最新一轮完全一致
  ok(latestNames.length > 0 && latestNames.every(n => board.text.includes(n)),
    '大屏文本与最新一轮中奖人一致: 接口=' + latestNames.join('、') + ' / 大屏="' + boardText + '"');
  await p2.screenshot({ path: SHOT + '/lottery-board.png' });

  // 清理：清空专用活动的签到人员（活动本身复用，不删除）
  const cleaned = await purge();
  ok(true, '清理专用活动的签到人员: ' + cleaned + ' 条');

  await browser.close();
  if (failures) { console.log('\n共 ' + failures + ' 条断言失败'); process.exit(1); }
  console.log('\n全部断言通过');
})().catch(e => { console.error('FAIL', e); console.log('失败上下文: ' + JSON.stringify(ctx, null, 2)); process.exit(1); });
