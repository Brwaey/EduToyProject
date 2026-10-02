import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

async function register(page: Page, suffix = "") {
  const username = "u" + randomUUID().replaceAll("-", "").slice(0, 20) + suffix;
  await page.goto("/login");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("显示名称").fill("研究者小林");
  await page.getByLabel("密码", { exact: true }).fill("research-12345");
  await page.getByRole("button", { name: "创建账号", exact: true }).click();
  await expect(page.getByRole("heading", { name: "科研记录" })).toBeVisible();
  return username;
}

async function openProjectManager(page: Page) {
  await page
    .getByRole("button", { name: "管理项目", exact: true })
    .filter({ visible: true })
    .click();
}

test("记录闭环、来源修订、账号隔离和会话持久化", async ({
  page,
  browser,
}, testInfo) => {
  const username = await register(page);
  await openProjectManager(page);
  await page.getByLabel("项目名称").fill("视觉模型评估");
  await page.getByLabel("项目说明").fill("统一评估口径，保留实验判断");
  await page.getByRole("button", { name: "保存项目" }).click();
  await expect(page.locator(".project-row")).toContainText("视觉模型评估");
  await page.getByRole("button", { name: "关闭", exact: true }).click();

  await page.getByRole("button", { name: "导入文本" }).click();
  await page.locator("input[type=file]").setInputFiles({
    name: "实验日志.md",
    mimeType: "text/markdown",
    buffer: Buffer.from(
      "\ufeff# 评估口径复查\n原始实验中，两组评估口径不一致。\n<script>window.hacked=true</script>",
    ),
  });
  await page.getByLabel("所属项目").selectOption({ label: "视觉模型评估" });
  await page
    .getByRole("combobox", { name: "记录类型", exact: true })
    .selectOption("experiment");
  await page.getByRole("button", { name: "确认导入" }).click();
  await expect(
    page.getByRole("heading", { name: "评估口径复查", level: 2 }),
  ).toBeVisible();
  const recordUrl = page.url();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page
    .getByLabel("我的判断", { exact: true })
    .fill("目前不能下结论，应先统一评估配置。");
  await page
    .getByRole("combobox", { name: "工作状态", exact: true })
    .selectOption("finished");
  await page
    .getByRole("combobox", { name: "结果判断", exact: true })
    .selectOption("inconclusive");
  await page.getByRole("button", { name: "保存记录", exact: true }).click();
  await expect(page.locator(".thought-interpretation")).toContainText(
    "应先统一评估配置",
  );
  await page.getByRole("tab", { name: "原始材料" }).click();
  await expect(page.locator(".source-card pre").first()).toContainText(
    "两组评估口径不一致",
  );
  await page.getByRole("button", { name: "修订", exact: true }).click();
  await page.getByLabel("材料内容").fill("修订材料：检查到两套不同配置。");
  await page.getByRole("button", { name: "保存新版本" }).click();
  await expect(page.locator(".source-card pre").first()).toContainText(
    "修订材料",
  );
  await page.getByRole("tab", { name: "修改历史" }).click();
  await expect(page.locator(".history>details")).toHaveCount(3);
  await page
    .locator(".history>details")
    .last()
    .locator("summary")
    .first()
    .click();
  await expect(page.locator(".history-body").last()).toContainText(
    "原始实验中",
  );
  await page.getByRole("tab", { name: "探索记录" }).click();
  await page.getByLabel("搜索记录").fill("统一评估");
  await expect(page.locator(".record-list .record-item")).toHaveCount(1);
  await page.reload();
  await expect(
    page.getByRole("heading", { name: "评估口径复查", level: 2 }),
  ).toBeVisible();
  expect(
    await page.evaluate(() => (window as Window & { hacked?: boolean }).hacked),
  ).toBeUndefined();
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([]);
  await page.screenshot({
    path: testInfo.outputPath("record-detail.png"),
    fullPage: true,
  });

  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByLabel("查看已删除记录")).toBeChecked();
  await page.locator(".record-list .record-item").first().click();
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "恢复记录", exact: true }).click();
  await expect(page.getByLabel("查看已删除记录")).not.toBeChecked();
  await expect(page.locator(".record-list .record-item")).toHaveCount(1);

  const other = await browser.newContext({ baseURL: "http://127.0.0.1:5174" });
  const b = await other.newPage();
  await register(b, "b");
  await expect(b.locator(".record-list .record-item")).toHaveCount(0);
  const me = await b.request.get("/api/v1/auth/me");
  expect(me.status()).toBe(200);
  const id = new URL(recordUrl).pathname.split("/").at(-1);
  expect((await b.request.get("/api/v1/records/" + id)).status()).toBe(404);
  await other.close();

  await page.getByRole("button", { name: "退出登录" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.getByLabel("用户名", { exact: true }).fill(username);
  await page.getByLabel("密码", { exact: true }).fill("research-12345");
  await page.getByRole("button", { name: "进入研迹" }).click();
  await expect(page.locator(".record-list .record-item")).toHaveCount(1);
});

test("保存失败保留输入、未保存导航提示和项目归档恢复", async ({ page }) => {
  await register(page);
  await page.getByRole("link", { name: "新建记录" }).click();
  await page.getByLabel("标题", { exact: true }).fill("一句话也值得保留");
  await page.getByLabel("记录正文").fill("我的草稿");
  await page.route("**/api/v1/records", (route) =>
    route.request().method() === "POST" ? route.abort() : route.continue(),
  );
  await page.getByRole("button", { name: "保存记录", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("连接失败");
  await expect(page.getByLabel("记录正文")).toHaveValue("我的草稿");
  page.once("dialog", (dialog) => dialog.dismiss());
  await page.getByRole("link", { name: "研究地图" }).click();
  await expect(page.getByLabel("记录正文")).toHaveValue("我的草稿");
  await page.unroute("**/api/v1/records");
  await page.getByRole("button", { name: "保存记录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "一句话也值得保留", level: 2 }),
  ).toBeVisible();

  await openProjectManager(page);
  await page.getByLabel("项目名称").fill("归档测试项目");
  await page.getByRole("button", { name: "保存项目" }).click();
  await page
    .getByRole("button", { name: "归档项目 归档测试项目", exact: true })
    .click();
  await expect(page.locator(".project-row")).toContainText("已归档");
  await page
    .getByRole("button", { name: "恢复项目 归档测试项目", exact: true })
    .click();
  await expect(page.locator(".project-row")).not.toContainText("已归档");
  await page.getByRole("button", { name: "关闭", exact: true }).click();
});

test("空状态、导入错误、安全 Markdown、页面不横向溢出", async ({
  page,
}, testInfo) => {
  await register(page);
  await expect(page.getByRole("heading", { name: /值得留下的/ })).toBeVisible();
  await page.getByRole("button", { name: "导入文本" }).click();
  await page.locator("input[type=file]").setInputFiles({
    name: "bad.txt",
    mimeType: "text/plain",
    buffer: Buffer.from([255, 254, 0, 2]),
  });
  await expect(page.getByRole("alert")).toContainText("UTF-8");
  await expect(page.getByRole("button", { name: "确认导入" })).toBeDisabled();
  await page.getByRole("button", { name: "关闭", exact: true }).click();
  await page.getByRole("link", { name: "新建记录" }).click();
  await page.getByLabel("标题", { exact: true }).fill("安全展示");
  await page
    .getByLabel("记录正文")
    .fill(
      "<script>window.hacked=true</script>\n[危险链接](javascript:alert(1))\n![远程图片](https://example.com/private.png)",
    );
  await page.getByRole("button", { name: "保存记录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "安全展示", level: 2 }),
  ).toBeVisible();
  await expect(page.locator(".markdown script")).toHaveCount(0);
  await expect(page.locator('.markdown a[href^="javascript"]')).toHaveCount(0);
  await expect(page.locator(".markdown img")).toHaveCount(0);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: testInfo.outputPath("layout.png"),
    fullPage: true,
  });
});

test("会话过期重新登录保留草稿，多窗口冲突不覆盖", async ({
  page,
  context,
}) => {
  await register(page);
  await page.getByRole("link", { name: "新建记录" }).click();
  await page.getByLabel("标题", { exact: true }).fill("会话恢复测试");
  await page.getByLabel("记录正文").fill("过期之后仍应保留的草稿");
  await context.clearCookies();
  await page.getByRole("button", { name: "保存记录", exact: true }).click();
  const login = page.getByRole("dialog");
  await expect(
    login.getByRole("heading", { name: "登录已过期" }),
  ).toBeVisible();
  await login.getByLabel("密码", { exact: true }).fill("research-12345");
  await login.getByRole("button", { name: "重新登录", exact: true }).click();
  await expect(login).toHaveCount(0);
  await expect(page.getByLabel("记录正文")).toHaveValue(
    "过期之后仍应保留的草稿",
  );
  await page.getByRole("button", { name: "保存记录", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "会话恢复测试", level: 2 }),
  ).toBeVisible();

  const other = await context.newPage();
  await other.goto(page.url());
  await other.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.getByLabel("记录正文").fill("窗口 A 尚未保存的判断");
  await other.getByLabel("记录正文").fill("窗口 B 已保存的判断");
  await other.getByRole("button", { name: "保存记录", exact: true }).click();
  await expect(other.locator(".detail > .markdown")).toContainText(
    "窗口 B 已保存的判断",
  );
  await page.getByRole("button", { name: "保存记录", exact: true }).click();
  await expect(page.getByRole("alert")).toContainText("其他页面更新");
  await expect(page.getByLabel("记录正文")).toHaveValue(
    "窗口 A 尚未保存的判断",
  );
  page.once("dialog", (dialog) => dialog.accept());
  await page.getByRole("button", { name: "重新载入最新版本" }).click();
  await expect(page.locator(".detail > .markdown")).toContainText(
    "窗口 B 已保存的判断",
  );
  await other.close();
});
