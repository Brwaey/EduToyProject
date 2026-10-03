// M5-A: written for later centralized execution. Uses only the local model fixture.
import { test, expect, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";
import { readFile } from "node:fs/promises";

async function setup(page: Page) {
  const registered = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:5174" },
    data: {
      username: "m5_" + randomUUID().replaceAll("-", "").slice(0, 20),
      display_name: "规划测试",
      password: "research-12345",
    },
  });
  expect(registered.ok()).toBeTruthy();
  const auth = await registered.json();
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
    return r.json();
  }
  const record = await write("/records", {
    request_id: randomUUID(),
    title: "规划实验",
    body: "我补充了对照条件，结果仍未改善。",
  });
  await write(
    "/ai/config",
    {
      expected_version: 0,
      url: "http://127.0.0.1:8099/v1",
      model: "test-model",
      api_key: "fake-m5-key",
    },
    "PUT",
  );
  page.on("dialog", (d) => d.accept());
  return { record, write };
}

test("行动材料明确选择、冲突保留输入、采纳与正式依据", async ({ page }) => {
  const { record } = await setup(page);
  await page.goto(
    "/records/ai/new?kind=action_candidates&object_kind=record&object=" +
      record.id,
  );
  await page.getByLabel("这次希望解决什么").fill("检查对照条件");
  await expect(page.getByRole("checkbox", { name: /^正文/ })).not.toBeChecked();
  await page.getByRole("checkbox", { name: /^正文/ }).check();
  await page.getByRole("button", { name: "预览发送内容", exact: true }).click();
  await page.getByRole("button", { name: "生成行动建议", exact: true }).click();
  await page
    .getByRole("button", { name: "查看建议 1", exact: true })
    .click({ timeout: 15000 });
  await page.getByLabel("建议行动标题").fill("我的下一次验证");
  await page.route("**/api/v1/ai/suggestions/*/accept", (route) =>
    route.fulfill({
      status: 409,
      contentType: "application/json",
      body: JSON.stringify({
        error: {
          code: "version_conflict",
          message: "模拟材料变化，输入保留",
          request_id: "test",
        },
      }),
    }),
  );
  await page.getByRole("button", { name: "采纳选定内容", exact: true }).click();
  await expect(page.getByLabel("建议行动标题")).toHaveValue("我的下一次验证");
  await expect(page.getByRole("alert")).toContainText("输入保留");
  await page.unroute("**/api/v1/ai/suggestions/*/accept");
  await page.getByRole("button", { name: "采纳选定内容", exact: true }).click();
  await page.getByRole("link", { name: "查看正式行动", exact: true }).click();
  await expect(page.locator(".research-detail")).toContainText("待开始");
  await expect(
    page.getByRole("heading", { name: "AI 采纳时的内容与固定依据" }),
  ).toBeVisible();
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
});

test("周复盘追加替换预览与范围导出", async ({ page }) => {
  const { record, write } = await setup(page);
  const rev = (
    await (
      await page.request.get(`/api/v1/records/${record.id}/revisions`)
    ).json()
  )[0];
  const reflection = await write("/reflections", {
    request_id: randomUUID(),
    kind: "period",
    title: "本周复盘",
    start_at: "2026-09-27T16:00:00Z",
    end_at: "2026-10-04T16:00:00Z",
    timezone: "Asia/Shanghai",
    details: { progress: "我自己的推进判断", understanding: "我自己的认识" },
    materials: [{ kind: "record", id: record.id, revision_id: rev.id }],
  });
  await page.goto(
    "/records/ai/new?kind=reflection_draft&object_kind=reflection&object=" +
      reflection.id,
  );
  await page.getByRole("checkbox", { name: /^本周推进/ }).check();
  await page.getByRole("button", { name: "预览发送内容", exact: true }).click();
  await page.getByRole("button", { name: "开始辅助整理", exact: true }).click();
  await page
    .getByRole("button", { name: "查看建议 1", exact: true })
    .click({ timeout: 15000 });
  await expect(page.getByLabel("本周推进处理方式")).toHaveValue("omit");
  await page.getByLabel("本周推进处理方式").selectOption("append");
  await page.getByLabel("建议本周推进").fill("另补充核对步骤");
  await page.getByLabel("受阻事项处理方式").selectOption("replace");
  await expect(
    page.getByText("我自己的推进判断\n\n另补充核对步骤", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "采纳选定内容", exact: true }).click();
  await page.getByRole("link", { name: "查看正式复盘", exact: true }).click();
  await expect(page.locator(".research-detail")).toContainText("我自己的认识");
  await page.getByRole("link", { name: "导出此复盘", exact: true }).click();
  await page.getByRole("button", { name: "生成导出预览", exact: true }).click();
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "下载 JSON", exact: true }).click();
  const downloaded = await downloadPromise;
  const data = JSON.parse(await readFile((await downloaded.path())!, "utf8"));
  expect(data.format_version).toBe("yanji.business.v1");
  expect(data.objects[0].details.progress).toContain("另补充核对步骤");
  expect(JSON.stringify(data)).not.toContain("fake-m5-key");
  await page.getByLabel("文件格式").selectOption("markdown");
  await page.getByRole("button", { name: "生成导出预览", exact: true }).click();
  const mdPromise = page.waitForEvent("download");
  await page
    .getByRole("button", { name: "下载 Markdown", exact: true })
    .click();
  expect((await mdPromise).suggestedFilename()).toBe("yanji-export.md");
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= innerWidth + 1,
    ),
  ).toBeTruthy();
});
