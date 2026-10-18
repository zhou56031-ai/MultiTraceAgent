/**
 * 工作台交互回归：模拟 HTTP/WebSocket，不调用真实模型。
 * 需要本机可用的 Playwright；通过 PLAYWRIGHT_MODULE 指定模块或安装路径。
 * LEARNING_BASE_URL 默认 http://127.0.0.1:8001。
 */
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs/promises');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');

const waitUntil = async (predicate, timeout = 10000) => {
  const end = Date.now() + timeout;
  while (Date.now() < end) {
    if (await predicate()) return;
    await new Promise(resolve => setTimeout(resolve, 40));
  }
  throw new Error('等待验证条件超时');
};

(async () => {
  const browser = await chromium.launch({
    headless: true,
    ...(process.env.BROWSER_PATH ? { executablePath: process.env.BROWSER_PATH } : {}),
  });
  try {
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    const sockets = new Map();
    const files = new Map();
    const submissions = [];
    let uploads = 0;
    let connections = 0;
    await page.routeWebSocket('**/ws/*', socket => {
      const id = new URL(socket.url()).pathname.split('/').pop();
      sockets.set(id, socket); connections++;
      socket.onMessage(message => { if (message === 'ping') socket.send(JSON.stringify({ type: 'pong' })); });
    });
    await page.route('**/api/files?*', route => {
      const id = new URL(route.request().url()).searchParams.get('thread_id');
      return route.fulfill({ json: { files: files.get(id) || [] } });
    });
    await page.route('**/api/upload', route => {
      const body = route.request().postDataBuffer().toString('utf8');
      assert(body.includes('name="thread_id"') && body.includes('name="file"'));
      uploads++;
      return route.fulfill({ json: { status: 'uploaded' } });
    });
    await page.route('**/api/tasks?*', route => route.fulfill({ json: { tasks: [] } }));
    await page.route('**/api/tasks/*?*', route => route.fulfill({ status: 404, json: { detail: '模拟任务未持久化' } }));
    await page.route('**/api/task', async route => {
      const body = route.request().postDataJSON();
      if (body.query === '触发提交错误') {
        await route.fulfill({ status: 503, json: { detail: '模拟提交失败' } }); return;
      }
      if (body.query === '回执异常但任务完成') {
        emit(body.thread_id, 'task_result', { result: '执行结果已经确认' });
        await new Promise(resolve => setTimeout(resolve, 150));
        await route.fulfill({ contentType: 'application/json', body: 'invalid-json' }); return;
      }
      submissions.push(body);
      await route.fulfill({ status: 202, json: { status: 'started', thread_id: body.thread_id, task_id: body.task_id } });
    });
    const emit = (id, event, data = {}) => sockets.get(id).send(JSON.stringify({
      type: 'monitor_event', event, message: event, data, timestamp: new Date().toISOString(),
    }));
    const base = process.env.LEARNING_BASE_URL || 'http://127.0.0.1:8001';
    await page.goto(base);
    await page.getByText('实时连接', { exact: true }).waitFor();
    assert(await page.getByRole('button', { name: '开始研究', exact: true }).isDisabled());
    const previewDir = path.resolve(__dirname, '../output/ui-preview');
    await fs.mkdir(previewDir, { recursive: true });
    await page.screenshot({ path: path.join(previewDir, 'desktop.png'), fullPage: true, animations: 'disabled' });

    await page.getByRole('button', { name: '试试数字助手 分工计算 · 观察协作过程', exact: true }).click();
    await page.getByRole('textbox', { name: '研究问题', exact: true }).press('Enter');
    await waitUntil(() => submissions.length === 1);
    const first = submissions[0].thread_id;
    assert(await page.getByRole('textbox', { name: '研究问题', exact: true }).isDisabled());
    files.set(first, [{ name: '报告.md', size: 128 }]);
    emit(first, 'assistant_call', { assistant_name: '数字统计助手', description: '统计三个整数' });
    emit(first, 'tool_start', { tool_name: 'sum_numbers', args: { item_count_hint: 3 } });
    emit(first, 'task_result', { result: '# 计算结果\n\n**合计：60**\n\n|项目|值|\n|---|---|\n|数量|3|\n\n<img src=x onerror="alert(1)">' });
    await page.getByText('研究已完成', { exact: true }).first().waitFor();
    await page.locator('.message.assistant table').waitFor();
    assert.equal(await page.locator('.message.assistant img').count(), 0);
    assert((await page.locator('.message.assistant').innerText()).includes('<img src=x'));
    await page.getByRole('link', { name: '下载 报告.md', exact: true }).waitFor();
    const downloadUrl = new URL(await page.getByRole('link', { name: '下载 报告.md', exact: true }).getAttribute('href'), base);
    assert.equal(downloadUrl.searchParams.get('thread_id'), first);
    assert.equal(downloadUrl.searchParams.get('filename'), '报告.md');

    await page.getByRole('button', { name: '新建研究 ↗', exact: true }).click();
    const secondSession = await page.locator('.session-select[aria-pressed="true"]').getAttribute('title');
    const second = secondSession.split(' · ').pop();
    await page.locator('#uploadFile').setInputFiles([
      { name: '练习.txt', mimeType: 'text/plain', buffer: Buffer.from('蓝色海豚') },
      { name: '说明.md', mimeType: 'text/markdown', buffer: Buffer.from('# 说明') },
    ]);
    await waitUntil(() => uploads === 2);
    await page.locator('.upload-chip').filter({ hasText: '说明.md' }).waitFor();
    await page.getByRole('textbox', { name: '研究问题', exact: true }).fill('第二会话的草稿');
    emit(first, 'tool_start', { tool_name: 'background_only', args: {} });
    await page.locator('.session-select').filter({ hasText: '请委派数字统计助手' }).click();
    await page.getByText('工具 · background_only', { exact: true }).waitFor();
    await page.locator('.session-select').filter({ hasText: '新的研究' }).click();
    assert.equal(await page.getByRole('textbox', { name: '研究问题', exact: true }).inputValue(), '第二会话的草稿');
    assert(!(await page.locator('#events').innerText()).includes('background_only'));
    await page.waitForFunction(() => localStorage.getItem('multiagent-search.workbench.v1')?.includes('第二会话的草稿'));
    await page.reload();
    await page.getByText('实时连接', { exact: true }).waitFor();
    assert.equal(await page.getByRole('textbox', { name: '研究问题', exact: true }).inputValue(), '第二会话的草稿');
    assert.equal(await page.locator('.session-select').count(), 2);

    sockets.get(second).send('not-json'); sockets.get(second).send('null');
    await page.getByRole('textbox', { name: '研究问题', exact: true }).press('Enter');
    await waitUntil(() => submissions.length === 2);
    const previousConnections = connections;
    sockets.get(second).close({ code: 1011, reason: 'simulated disconnect' });
    await page.getByRole('status').filter({ hasText: '状态待确认' }).waitFor();
    await waitUntil(() => connections > previousConnections);
    await page.getByText('实时连接', { exact: true }).waitFor();
    assert(await page.getByRole('textbox', { name: '研究问题', exact: true }).isDisabled());
    await page.locator('.session-row.active .session-close').click();
    assert.equal(await page.locator('.session-select').count(), 1);

    await page.getByRole('button', { name: '新建研究 ↗', exact: true }).click();
    await page.getByRole('textbox', { name: '研究问题', exact: true }).fill('触发提交错误');
    await page.getByRole('textbox', { name: '研究问题', exact: true }).press('Enter');
    await page.getByRole('status').filter({ hasText: '任务失败' }).waitFor();
    assert((await page.locator('#events').innerText()).includes('模拟提交失败'));
    await page.getByRole('button', { name: '新建研究 ↗', exact: true }).click();
    await page.getByRole('textbox', { name: '研究问题', exact: true }).fill('回执异常但任务完成');
    await page.getByRole('textbox', { name: '研究问题', exact: true }).press('Enter');
    await page.getByText('提交回执异常，已保留执行结果', { exact: true }).waitFor();
    assert.equal(await page.locator('#status').innerText(), '研究已完成');
    await page.getByRole('button', { name: '清理已结束的会话', exact: true }).click();
    assert.equal(await page.locator('.session-select').count(), 1);

    await page.getByText('实时连接', { exact: true }).waitFor();
    const idleId = (await page.locator('.session-select[aria-pressed="true"]').getAttribute('title')).split(' · ').pop();
    const beforeClose = connections;
    sockets.get(idleId).close({ code: 1000, reason: 'new tab takes over' });
    await page.getByRole('button', { name: '重新连接', exact: true }).waitFor();
    await new Promise(resolve => setTimeout(resolve, 1250));
    assert.equal(connections, beforeClose, '正常关闭不应自动争抢连接');
    await page.getByRole('button', { name: '重新连接', exact: true }).click();
    await page.getByText('实时连接', { exact: true }).waitFor();

    await page.setViewportSize({ width: 390, height: 844 });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    await page.screenshot({ path: path.join(previewDir, 'mobile.png'), fullPage: true, animations: 'disabled' });
    await page.getByRole('button', { name: '打开会话侧栏', exact: true }).click();
    assert((await page.locator('#sidebar').getAttribute('class')).includes('open'));
    await page.getByRole('button', { name: '新建研究 ↗', exact: true }).click();
    assert.equal(await page.locator('#sidebar').getAttribute('class'), 'sidebar');
    assert.deepEqual(errors, []);
    console.log('通过：提交状态、Markdown安全排版、文件链接、多文件上传、会话隔离与草稿恢复、坏消息、断线重连、连接接管、回执竞态、失败提示、清理会话、手机布局');
    console.log('截图：', previewDir);
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
