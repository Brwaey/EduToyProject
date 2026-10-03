import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

async function setup(page: Page) {
  const r = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:5174" },
    data: {
      username: "ai" + randomUUID().replaceAll("-", "").slice(0, 20),
      display_name: "AI 研究者",
      password: "research-12345",
    },
  });
  expect(r.ok()).toBeTruthy();
  const auth = await r.json();
  async function write(path: string, data: unknown, method = "POST") {
    const res = await page.request.fetch("/api/v1" + path, {
      method,
      headers: {
        Origin: "http://127.0.0.1:5174",
        "X-CSRF-Token": auth.csrf_token,
      },
      data,
    });
    expect(res.ok(), await res.text()).toBeTruthy();
    return res.status() === 204 ? null : res.json();
  }
  const record = await write("/records", {
    request_id: randomUUID(),
    title: "需要整理的中文实验",
    body: "中文实验结果：两次尝试均未见提升。",
    record_type: "experiment",
  });
  return { record, write };
}
async function configure(page: Page) {
  await page.goto("/settings/model");
  await page
    .getByLabel("API URL", { exact: true })
    .fill("http://127.0.0.1:8099/v1");
  await page.getByLabel("模型名", { exact: true }).fill("test-model");
  await page.getByLabel("API Key", { exact: true }).fill("e2e-test-secret");
  await page.getByRole("button", { name: "保存并测试", exact: true }).click();
  await expect(
    page.getByText("基本请求成功，可以选择科研材料开始整理。", {
      exact: false,
    }),
  ).toBeVisible({ timeout: 10000 });
  await expect(page.getByLabel("API Key", { exact: true })).toHaveValue("");
  await page.reload();
  await expect(page.getByLabel("模型名", { exact: true })).toHaveValue(
    "test-model",
  );
}
async function generate(page: Page, recordId: string) {
  await page.goto("/records/" + recordId);
  await page.getByRole("link", { name: "AI 整理", exact: true }).click();
  await page.getByRole("button", { name: "预览发送内容", exact: true }).click();
  await expect(page.getByRole("heading", { name: "发送前预览" })).toBeVisible();
  await page.getByRole("button", { name: "开始整理", exact: true }).click();
  await page
    .getByRole("button", { name: "查看建议 1", exact: true })
    .click({ timeout: 15000 });
  await expect(
    page.getByRole("heading", { name: "核对建议", exact: true }),
  ).toBeVisible();
}

test("模型设置、整理采纳、来源复核与地图关系", async ({ page }, info) => {
  test.setTimeout(90000);
  const { record, write } = await setup(page);
  await configure(page);
  await page.screenshot({
    path: info.outputPath("m3-settings.png"),
    fullPage: true,
  });
  await generate(page, record.id);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: info.outputPath("m3-review.png"),
    fullPage: true,
  });
  await expect(page.getByLabel("采用标题", { exact: true })).not.toBeChecked();
  await expect(
    page.getByLabel("采用观察与结果", { exact: true }),
  ).toBeChecked();
  await page
    .getByLabel("建议观察与结果", { exact: true })
    .fill("两次尝试均未见提升，需复核设置。");
  await page.getByRole("button", { name: "采纳选定内容", exact: true }).click();
  await expect(
    page.getByText("该建议已处理，生成时的依据与处理结果保留。"),
  ).toBeVisible();
  await page.getByRole("link", { name: "查看正式记录" }).click();
  await expect(
    page.getByRole("heading", { name: record.title, exact: true, level: 2 }),
  ).toBeVisible();
  await expect(
    page.getByText("两次尝试均未见提升，需复核设置。", { exact: true }),
  ).toBeVisible();
  await generate(page, record.id);
  const current = await (
    await page.request.get("/api/v1/records/" + record.id)
  ).json();
  await write(
    "/records/" + record.id,
    { expected_version: current.version, body: "补充：已统一设置，仍待复测。" },
    "PATCH",
  );
  await page
    .getByRole("button", { name: "重新载入当前版本（保留输入）" })
    .click();
  await expect(
    page.getByLabel("我已核对，旧依据仍适用于本次采纳"),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "采纳选定内容" }),
  ).toBeDisabled();
  await page.getByLabel("采用观察与结果", { exact: true }).check();
  await page.getByLabel("我已核对，旧依据仍适用于本次采纳").check();
  await page.getByRole("button", { name: "采纳选定内容" }).click();
  await expect(page.getByRole("link", { name: "查看正式记录" })).toBeVisible();
  const q = await write("/research-items", {
    request_id: randomUUID(),
    kind: "question",
    title: "设置差异会影响实验吗",
    details: { kind: "question" },
  });
  await page.goto(
    "/records/ai/new?kind=relation_suggestions&record=" + record.id,
  );
  await page
    .locator(".picker-results button")
    .filter({ hasText: q.title })
    .click();
  await page.getByRole("button", { name: "预览发送内容" }).click();
  await page.getByRole("button", { name: "开始整理" }).click();
  await page
    .getByRole("button", { name: "查看建议 1" })
    .click({ timeout: 15000 });
  await expect(page.getByLabel("关系理由", { exact: true })).toHaveValue(
    "选定实验与研究问题相关",
  );
  await page.getByRole("button", { name: "采纳选定内容" }).click();
  await page.getByRole("link", { name: "查看正式关系" }).click();
  await expect(page.locator(".relation-card")).toHaveCount(1);
  await expect(
    page.getByText("选定实验与研究问题相关", { exact: true }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: info.outputPath("m3-map.png"),
    fullPage: true,
  });
});

test("失败与冲突保留输入、批量拒绝及取消", async ({ page }, info) => {
  test.setTimeout(90000);
  const { record, write } = await setup(page);
  await configure(page);
  await generate(page, record.id);
  await page.getByLabel("建议观察与结果").fill("保留这段人工核对文字");
  await page.route("**/api/v1/ai/suggestions/*/accept", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "version_conflict",
          message: "材料再次变化，请重新核对",
          request_id: "e2e",
        },
      }),
    }),
  );
  await page.getByRole("button", { name: "采纳选定内容" }).click();
  await expect(page.getByRole("alert")).toContainText("材料再次变化");
  await expect(page.getByLabel("建议观察与结果")).toHaveValue(
    "保留这段人工核对文字",
  );
  await page.unroute("**/api/v1/ai/suggestions/*/accept");
  await page.getByRole("button", { name: "拒绝建议", exact: true }).click();
  await expect(
    page.getByText("该建议已处理，生成时的依据与处理结果保留。"),
  ).toBeVisible();
  await generate(page, record.id);
  await page.goto("/records/ai");
  await page.getByRole("checkbox", { name: /^选择建议 / }).check();
  await page.getByRole("button", { name: "拒绝选中建议（1）" }).click();
  await expect(page.getByRole("checkbox", { name: /^选择建议 / })).toHaveCount(
    0,
  );
  expect(
    await page.evaluate(() =>
      JSON.stringify({
        local: { ...localStorage },
        session: { ...sessionStorage },
      }),
    ),
  ).not.toContain("e2e-test-secret");
  const cfg = await (await page.request.get("/api/v1/ai/config")).json();
  await write(
    "/ai/config",
    { expected_version: cfg.version, url: cfg.endpoint, model: "slow" },
    "PUT",
  );
  const updated = await (await page.request.get("/api/v1/ai/config")).json();
  const t = await write("/ai/config/test", {
    request_id: randomUUID(),
    config_version: updated.version,
  });
  await page.goto("/records/ai?task=" + t.id);
  await page.getByRole("button", { name: "取消任务", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "连接测试 · 已取消", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "使用当前配置重试" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
  await page.screenshot({
    path: info.outputPath("m3-inbox.png"),
    fullPage: true,
  });
});
