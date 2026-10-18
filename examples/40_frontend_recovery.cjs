/** 配合40_reliability_check.py --serve：真实HTTP/SQLite，屏蔽WS通知，模型与搜索为模拟。 */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1080 } });
    // 刻意不把任何完成事件传给网页；答案必须通过HTTP查回。
    const sockets = [];
    await context.routeWebSocket('**/ws/*', socket => { sockets.push(socket); });
    const page = await context.newPage();
    const errors = [], submitted = [];
    page.on('pageerror', error => errors.push(error.message));
    page.on('request', request => {
      if (request.method() === 'POST' && new URL(request.url()).pathname === '/api/task') submitted.push(request.postDataJSON());
    });
    const base = process.env.LEARNING_BASE_URL || 'http://127.0.0.1:8012';
    await page.goto(base);
    await page.getByText('实时连接', { exact: true }).waitFor();
    await page.locator('#uploadFile').setInputFiles({ name: '恢复验收.txt', mimeType: 'text/plain', buffer: Buffer.from('开始\n' + '甲'.repeat(13000)) });
    await page.locator('.upload-chip').filter({ hasText: '恢复验收.txt' }).waitFor();
    await page.locator('#query').fill('恢复验收：请分析文件，生成带来源的报告');
    const receipt = page.waitForResponse(response => new URL(response.url()).pathname === '/api/task' && response.request().method() === 'POST');
    await page.locator('#query').press('Enter');
    const response = await receipt;
    assert.equal(response.status(), 202);
    const accepted = await response.json();
    assert(accepted.task_id && accepted.thread_id && accepted.task_id !== accepted.thread_id);
    await page.reload();
    await page.locator('#status').filter({ hasText: '研究已完成' }).waitFor({ timeout: 15000 });
    assert.equal(submitted.length, 1, '刷新不能再次提交任务');
    assert.equal(await page.locator('.message.assistant').count(), 1);
    assert((await page.locator('.message.assistant').innerText()).includes('本次工具来源'));
    assert((await page.locator('#sources').innerText()).includes('正文已截断'));
    assert((await page.locator('#sources').innerText()).includes('[F1]'));
    assert.equal(await page.locator('#sources a[href="https://example.org/reliability"]').count(), 1);
    for (let index = 0; index < 3; index++) {
      const checked = page.waitForResponse(response => new URL(response.url()).pathname === '/api/tasks');
      await page.locator('#recoverTask').click(); await checked;
    }
    assert.equal(await page.locator('.message.assistant').count(), 1, '反复查回不能追加重复答案');
    sockets.at(-1).send(JSON.stringify({ type: 'monitor_event', task_id: '00000000-0000-4000-8000-000000000001', event: 'error', data: { detail: '晚到的其他任务错误' } }));
    assert.equal(await page.locator('#status').innerText(), '研究已完成');
    const download = await context.request.get(new URL('/api/download?' + new URLSearchParams({ thread_id: accepted.thread_id, filename: '验收报告.md' }), base).href);
    assert(download.ok() && (await download.text()).includes('https://example.org/reliability'));
    const directory = path.resolve(__dirname, '../output/ui-preview');
    await fs.mkdir(directory, { recursive: true });
    await page.locator('.toast').last().waitFor({state:'hidden',timeout:7000});
    await page.screenshot({ path: path.join(directory, 'recovery-desktop.png'), fullPage: true, animations: 'disabled' });
    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(directory, 'recovery-mobile.png'), fullPage: true, animations: 'disabled' });
    assert.deepEqual(errors, []);
    console.log('通过：屏蔽WS通知后刷新由真实HTTP找回答案、只提交一次、重复核对不重复展示、来源与截断说明、报告下载、桌面/手机布局；模型和搜索为模拟');
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
