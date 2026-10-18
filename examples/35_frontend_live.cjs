/** 新工作台真实链路：上传 → 提问 → 最终回答 → 文件下载。会调用真实模型。 */
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

(async () => {
  const browser = await chromium.launch({ headless: true,
    ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : {}) });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, acceptDownloads: true });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.LEARNING_BASE_URL || 'http://127.0.0.1:8001');
    await page.getByText('实时连接', { exact: true }).waitFor();
    const contents = '界面验收代号：晨光竹林。';
    await page.locator('#uploadFile').setInputFiles({
      name: 'learning-ui-check.txt', mimeType: 'text/plain', buffer: Buffer.from(contents),
    });
    await page.locator('.upload-chip').filter({ hasText: 'learning-ui-check.txt' }).waitFor();
    await page.getByRole('textbox', { name: '研究问题', exact: true }).fill(
      '请用 read_file_content 读取 learning-ui-check.txt，仅复述其中的验收代号；不要生成额外文件，也不要联网。'
    );
    const receipt = page.waitForResponse(response => new URL(response.url()).pathname === '/api/task' && response.request().method() === 'POST');
    await page.getByRole('textbox', { name: '研究问题', exact: true }).press('Enter');
    const accepted = await (await receipt).json();
    await page.locator('#status').filter({ hasText: '研究已完成' }).waitFor({ timeout: 180000 });
    assert((await page.locator('.message.assistant').innerText()).includes('晨光竹林'));
    assert((await page.locator('#events').innerText()).includes('read_file_content'));
    const taskResponse = await context.request.get(new URL('/api/tasks/' + accepted.task_id + '?' + new URLSearchParams({thread_id:accepted.thread_id}), page.url()).href);
    assert(taskResponse.ok());
    const record = await taskResponse.json();
    assert.equal(record.status, 'succeeded');
    assert(record.result.includes('晨光竹林') && record.sources.some(source => source.kind === 'file' && source.filename === 'learning-ui-check.txt'));
    assert((await page.locator('#sources').innerText()).includes('[F1]'));
    const link = page.getByRole('link', { name: '下载 learning-ui-check.txt', exact: true });
    await link.waitFor();
    const downloadPromise = page.waitForEvent('download');
    await link.click();
    const downloaded = await downloadPromise;
    assert.equal(await fs.readFile(await downloaded.path(), 'utf8'), contents);
    await page.reload();
    await page.locator('#status').filter({ hasText: '研究已完成' }).waitFor();
    assert((await page.locator('.message.assistant').innerText()).includes('晨光竹林'));
    assert.deepEqual(errors, []);
    const directory = path.resolve(__dirname, '../output/ui-preview');
    await fs.mkdir(directory, { recursive: true });
    await page.screenshot({ path: path.join(directory, 'live-desktop.png'), fullPage: true, animations: 'disabled' });
    console.log('真实浏览器通过：资料上传、读取事件、正确回答、文件列表、下载正文核对、任务账本查询、真实文件来源与范围、刷新恢复；无脚本异常');
    console.log('预览：', path.join(directory, 'live-desktop.png'));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
