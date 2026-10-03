// Prepared for centralized testing; not executed during M4 implementation.
import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

async function setup(page: Page) {
  const response = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:5174" },
    data: {
      username: "growth" + randomUUID().replaceAll("-", "").slice(0, 18),
      display_name: "成长研究者",
      password: "research-12345",
    },
  });
  expect(response.ok()).toBeTruthy();
  const auth = await response.json();
  async function write(path: string, data: unknown, method = "POST") {
    const r = await page.request.fetch("/api/v1" + path, {
      method,
      headers: {
        Origin: "http://127.0.0.1:5174",
        "X-CSRF-Token": auth.csrf_token,
      },
      data,
    });
    expect(r.ok(), await r.text()).toBeTruthy();
    return r.status() === 204 ? null : r.json();
  }
  const record = await write("/records", {
    request_id: randomUUID(),
    title: "未达预期的实验",
    body: "我补充了对照条件。结果仍未提升。",
    record_type: "experiment",
    outcome_status: "unsupported",
  });
  return { record, write };
}

async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
}

test("贡献、标签实例、理解变化与显式后续行动", async ({ page }, info) => {
  const { record } = await setup(page);
  await page.goto("/records/" + record.id);
  await page.getByRole("link", { name: "记录我的贡献", exact: true }).click();
  const dialog = page.getByRole("dialog");
  await dialog
    .getByLabel("我做了什么", { exact: true })
    .fill("我补充了对照条件");
  await dialog
    .getByLabel("我的具体参与（可选）", { exact: true })
    .fill("我比较了两组设置");
  await dialog.getByLabel("以上本人参与的描述由我确认").check();
  await dialog.getByRole("button", { name: "保存贡献", exact: true }).click();
  await expect(dialog).not.toBeVisible();
  await page
    .getByRole("link", { name: "我补充了对照条件", exact: true })
    .click();
  await expect(page.locator(".growth-detail")).toContainText("已附材料");
  await page.getByRole("button", { name: "修改历史", exact: true }).click();
  await expect(
    page.locator(".growth-detail summary").filter({ hasText: "第 1 版" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "能力档案", exact: true }).click();
  await page.getByRole("button", { name: "实验设计", exact: true }).click();
  await page.getByRole("button", { name: "记录能力实例", exact: true }).click();
  await dialog
    .getByLabel("一句话主题", { exact: true })
    .fill("在帮助下设计对照");
  await dialog.getByRole("checkbox", { name: "实验设计", exact: true }).check();
  await dialog.getByLabel("完成方式", { exact: true }).selectOption("assisted");
  await dialog
    .getByLabel("下一步想尝试什么（可选）", { exact: true })
    .fill("再检查随机种子");
  await dialog
    .getByRole("button", { name: "保存能力实例", exact: true })
    .click();
  await page
    .getByRole("link", { name: "在帮助下设计对照", exact: true })
    .click();
  await expect(page.locator(".growth-detail")).toContainText(
    "用户自述／待补依据",
  );
  await page.getByRole("button", { name: "据此创建行动", exact: true }).click();
  await dialog
    .getByLabel("行动标题", { exact: true })
    .fill("下一次检查随机种子");
  await dialog.getByRole("button", { name: "保存行动", exact: true }).click();
  await page
    .getByRole("link", { name: "下一次检查随机种子", exact: true })
    .click();
  await expect(
    page.getByText("发起这次行动的贡献／成长", { exact: true }),
  ).toBeVisible();
  await page.goto("/growth?tab=understanding");
  await page.getByRole("button", { name: "记录理解变化", exact: true }).click();
  await dialog.getByLabel("一句话主题", { exact: true }).fill("如何解释未提升");
  await dialog
    .getByLabel("之前如何理解（必填）", { exact: true })
    .fill("单次结果能判断方法");
  await dialog
    .getByLabel("现在如何理解（必填）", { exact: true })
    .fill("需要先排除评估设置差异");
  await dialog
    .getByRole("button", { name: "保存理解变化", exact: true })
    .click();
  await page.getByRole("link", { name: "如何解释未提升", exact: true }).click();
  await expect(page.locator(".growth-detail")).toContainText(
    "需要先排除评估设置差异",
  );
  await noOverflow(page);
  await page.screenshot({
    path: info.outputPath("m4-understanding.png"),
    fullPage: true,
  });
});

test("AI 贡献核对、失败保留输入及人工确认", async ({ page }, info) => {
  const { record, write } = await setup(page);
  await write(
    "/ai/config",
    {
      expected_version: 0,
      url: "http://127.0.0.1:8099/v1",
      model: "test-model",
      api_key: "e2e-fake-key",
    },
    "PUT",
  );
  await page.goto(
    "/records/ai/new?kind=contribution_candidates&record=" + record.id,
  );
  await page.getByRole("button", { name: "预览发送内容", exact: true }).click();
  await page.getByRole("button", { name: "开始整理", exact: true }).click();
  await page
    .getByRole("button", { name: "查看建议 1", exact: true })
    .click({ timeout: 15000 });
  await expect(
    page.getByRole("heading", { name: "核对贡献候选" }),
  ).toBeVisible();
  const accept = page.getByRole("button", {
    name: "采纳为个人贡献",
    exact: true,
  });
  await expect(accept).toBeDisabled();
  await page
    .getByLabel("我的具体参与", { exact: true })
    .fill("我比较了设置并作出选择");
  await page.getByLabel("以上本人参与的描述由我确认").check();
  await page.route("**/api/v1/ai/suggestions/*/accept", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "version_conflict",
          message: "材料再次变化，请保留输入",
          request_id: "growth-e2e",
        },
      }),
    }),
  );
  await accept.click();
  await expect(page.getByRole("alert")).toContainText("材料再次变化");
  await expect(page.getByLabel("我的具体参与", { exact: true })).toHaveValue(
    "我比较了设置并作出选择",
  );
  await page.unroute("**/api/v1/ai/suggestions/*/accept");
  await accept.click();
  await page.getByRole("link", { name: "查看正式贡献", exact: true }).click();
  await expect(page.locator(".growth-detail")).toContainText(
    "我比较了设置并作出选择",
  );
  await page.reload();
  await expect(page.locator(".growth-detail")).toContainText("已附材料");
  await noOverflow(page);
  await page.screenshot({
    path: info.outputPath("m4-ai-contribution.png"),
    fullPage: true,
  });
});
