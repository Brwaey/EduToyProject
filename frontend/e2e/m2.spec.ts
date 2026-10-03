import { expect, test, type Page } from "@playwright/test";
import { randomUUID } from "node:crypto";

async function setup(page: Page) {
  const username = "m2" + randomUUID().replaceAll("-", "").slice(0, 20);
  const response = await page.request.post("/api/v1/auth/register", {
    headers: { Origin: "http://127.0.0.1:5174" },
    data: { username, display_name: "探索者", password: "research-12345" },
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
    return r.json();
  }
  const a = await write("/projects", { name: "模型评估 A" });
  const b = await write("/projects", { name: "教学反馈 B" });
  const record = await write("/records", {
    request_id: randomUUID(),
    title: "未达预期的评估实验",
    body: "两组评估口径不一致，当前条件下未见提升。",
    project_id: a.id,
    record_type: "experiment",
    work_status: "finished",
    outcome_status: "unsupported",
  });
  return { a, b, record, write };
}
async function choose(page: Page, title: string) {
  await page
    .getByRole("dialog")
    .locator(".picker-results button")
    .filter({ hasText: title })
    .click();
}
async function listMap(page: Page) {
  await page.getByRole("button", { name: "列表", exact: true }).click();
}
async function noOverflow(page: Page) {
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBeTruthy();
}

test("研究地图到跨项目行动与复盘的完整闭环", async ({ page }, info) => {
  test.setTimeout(90000);
  page.setDefaultTimeout(10000);
  const { a, b, record, write } = await setup(page);
  await page.goto("/map");
  await expect(
    page.getByRole("heading", { name: "研究地图", exact: true }),
  ).toBeVisible();
  await expect(page.locator(".react-flow__node")).toHaveCount(0);
  await page.getByRole("button", { name: "新建研究问题", exact: true }).click();
  await page.getByLabel("标题", { exact: true }).fill("评估口径会影响结论吗？");
  await page.getByLabel("所属项目").selectOption(a.id);
  await page.getByRole("button", { name: "保存研究问题" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.goto("/records/" + record.id);
  await page.getByRole("link", { name: "建立地图关联" }).click();
  await expect(page.getByRole("dialog", { name: "建立关联" })).toBeVisible();
  await choose(page, "评估口径会影响结论吗？");
  await page.getByLabel("关系类型").selectOption("tests");
  await page.getByLabel("关系理由").fill("实验试图检验统一口径能否改善结果");
  await page.getByRole("button", { name: "保存关系" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await listMap(page);
  await expect(page.locator(".node-list .node-row")).toHaveCount(2);

  await page.getByRole("button", { name: "记录发现" }).click();
  await page.getByLabel("发现表述").fill("差异可能来自评估配置");
  await page.getByLabel("所属项目").selectOption(a.id);
  await page.getByLabel("表述类型").selectOption("interpretation");
  await page.getByText("进一步整理（选填）", { exact: true }).click();
  await page.getByLabel("适用条件").fill("当前两组样本与参数设置");
  await page.getByRole("button", { name: "添加证据" }).click();
  await choose(page, "未达预期的评估实验");
  await page.getByLabel("引用内容").selectOption({ index: 8 });
  await page.getByLabel("原文片段", { exact: false }).fill("评估口径不一致");
  await page.getByRole("button", { name: "确认引用此版本" }).click();
  await page.getByRole("button", { name: "保存发现" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .locator(".node-row")
    .filter({ hasText: "差异可能来自评估配置" })
    .click();
  await page.getByRole("button", { name: "建立关联", exact: true }).click();
  await choose(page, "未达预期的评估实验");
  await page.getByLabel("关系类型").selectOption("derived_from");
  await page.getByLabel("关系理由").fill("来自这次实验的条件差异");
  await page.getByRole("button", { name: "保存关系" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "提出后续方向" }).click();
  await page.getByLabel("标题", { exact: true }).fill("统一口径后验证教学反馈");
  await page.getByLabel("所属项目").selectOption(b.id);
  await page
    .getByRole("combobox", { name: "状态", exact: true })
    .selectOption("focus");
  await page
    .getByRole("combobox", { name: "优先级", exact: true })
    .selectOption("high");
  await page.getByRole("button", { name: "保存候选方向" }).click();
  await expect(page.getByRole("dialog", { name: "建立关联" })).toBeVisible();
  await page.getByLabel("关系类型").selectOption("derived_from");
  await page.getByLabel("关系理由").fill("将评估配置的经验迁移到教学反馈项目");
  await page.getByRole("button", { name: "保存关系" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByLabel("地图范围").selectOption(a.id);
  await expect(
    page.locator(".node-row").filter({ hasText: "统一口径后验证教学反馈" }),
  ).toContainText("跨项目");
  await noOverflow(page);
  await page.screenshot({
    path: info.outputPath("map-list.png"),
    fullPage: true,
  });
  await page
    .locator(".node-row")
    .filter({ hasText: "统一口径后验证教学反馈" })
    .click();
  await page.getByRole("link", { name: "从方向创建行动" }).click();
  await expect(page.getByLabel("所属项目")).toHaveValue(b.id);
  await page.getByLabel("行动标题").fill("统一配置复测十个样本");
  await page.getByRole("button", { name: "保存行动" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .locator(".planning-card")
    .filter({ hasText: "统一配置复测十个样本" })
    .click();
  await page.getByRole("button", { name: "完成行动", exact: true }).click();
  await page
    .getByLabel("结果说明", { exact: true })
    .fill("统一口径后仍无明显提升，需要扩大样本。");
  await page.getByLabel("同时新建一条结果记录").check();
  await page.getByLabel("记录标题").fill("统一口径复测结果");
  await page.getByLabel("记录正文").fill("十个样本不足以支持原假设。");
  await page.getByLabel("同时关联到方向", { exact: false }).check();
  await page.getByRole("button", { name: "确认完成行动" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".result-summary")).toContainText("仍无明显提升");
  await page.getByRole("link", { name: "复盘这次行动" }).click();
  await page
    .getByLabel("实际发生了什么")
    .fill("统一后差异缩小，但样本量不足。");
  await page.getByLabel("接下来的选择").selectOption("adjust");
  await page.getByRole("button", { name: "保存复盘" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.locator(".planning-card").first().click();
  await expect(
    page.getByRole("heading", { name: "当时选择的依据" }),
  ).toBeVisible();
  await page.getByRole("link", { name: "据此创建行动" }).click();
  await page.getByLabel("行动标题").fill("扩大样本再核对");
  await page.getByRole("button", { name: "保存行动" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "复盘", exact: true }).click();
  await page.getByRole("button", { name: "开始周复盘" }).click();
  await page.getByLabel("本周推进").fill("梳理两个项目的共同评估问题。");
  await page.getByLabel("搜索复盘材料").fill("统一配置复测十个样本");
  await page.locator(".material-options input[type=checkbox]").check();
  await page.getByRole("button", { name: "保存复盘" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page
    .locator(".planning-card")
    .filter({ hasText: "本周科研复盘" })
    .click();
  await noOverflow(page);
  await page.screenshot({
    path: info.outputPath("weekly-reflection.png"),
    fullPage: true,
  });

  const sources = await (
    await page.request.get(`/api/v1/records/${record.id}/sources`)
  ).json();
  await write(`/sources/${sources[0].id}/versions`, {
    expected_version: 1,
    content: "修订材料：重新统一配置",
  });
  await page.goto("/map");
  await listMap(page);
  await page
    .locator(".node-row")
    .filter({ hasText: "差异可能来自评估配置" })
    .click();
  await expect(page.locator(".research-detail .notice")).toContainText(
    "来源已更新",
  );
  await page.locator(".research-detail .evidence-card summary").first().click();
  await expect(
    page.locator(".research-detail .evidence-card pre"),
  ).toContainText("两组评估口径不一致");
  await page
    .getByRole("button", { name: "确认现有依据仍适用", exact: true })
    .click();
  await expect(page.locator(".research-detail .notice")).toHaveCount(0);
  await write("/records/" + record.id, { expected_version: 2 }, "DELETE");
  await page.reload();
  await listMap(page);
  await expect(
    page.locator(".node-row").filter({ hasText: "未达预期的评估实验" }),
  ).toHaveCount(0);
  await write(`/records/${record.id}/restore`, { expected_version: 3 });
  await page.reload();
  await listMap(page);
  await expect(
    page.locator(".node-row").filter({ hasText: "未达预期的评估实验" }),
  ).toHaveCount(1);
  await expect(page.getByRole("alert")).toHaveCount(0);
});

test("布局保存、键盘选择与表单错误恢复", async ({ page }, info) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));

  const { a, write } = await setup(page);
  const item = await write("/research-items", {
    request_id: randomUUID(),
    kind: "question",
    title: "保留自己的判断",
    project_id: a.id,
    details: { kind: "question" },
  });
  await page.goto("/map");
  await page.getByRole("button", { name: "画布", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(1);
  await page.getByRole("button", { name: "自动整理" }).click();
  await page.getByRole("button", { name: "保存布局" }).click();
  await expect(page.getByRole("button", { name: "保存布局" })).toBeDisabled();
  const saved = await (await page.request.get("/api/v1/graph/layout")).json();
  expect(Object.keys(saved.positions)).toHaveLength(1);
  await page.reload();
  await page.getByRole("button", { name: "画布", exact: true }).click();
  await expect(page.locator(".react-flow__node")).toHaveCount(1);
  const node = page.locator(".react-flow__node").first();
  await node.focus();
  await node.press("Enter");
  await expect(page.getByRole("heading", { name: item.title })).toBeVisible();
  await node.press("ArrowRight");
  await expect(page.getByRole("button", { name: "保存布局" })).toBeEnabled();
  page.once("dialog", (d) => d.dismiss());
  await page.getByRole("button", { name: "列表", exact: true }).click();
  await expect(page.locator(".map-canvas")).toBeVisible();
  page.once("dialog", (d) => d.dismiss());
  await page.getByLabel("搜索研究内容").fill("切换筛选");
  await expect(page.getByLabel("搜索研究内容")).toHaveValue("");
  await page.getByRole("button", { name: "保存布局" }).click();
  await expect(page.getByRole("button", { name: "保存布局" })).toBeDisabled();
  const moved = await (await page.request.get("/api/v1/graph/layout")).json();
  expect(moved.positions).not.toEqual(saved.positions);
  await page.screenshot({
    path: info.outputPath("map-canvas.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "编辑研究问题" }).click();
  await page.getByLabel("标题", { exact: true }).fill("不应丢失的输入");
  await page.route("**/api/v1/research-items/" + item.id, (route) => {
    if (route.request().method() === "PATCH") return route.abort();
    return route.continue();
  });
  await page.getByRole("button", { name: "保存研究问题" }).click();
  await expect(page.getByRole("alert")).toContainText("连接失败");
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(
    "不应丢失的输入",
  );
  page.once("dialog", (d) => d.dismiss());
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "关闭", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toBeVisible();
  await page.unroute("**/api/v1/research-items/" + item.id);
  await write(
    "/research-items/" + item.id,
    {
      kind: "question",
      title: "另一个页面保存的内容",
      details: { kind: "question" },
      expected_version: 1,
    },
    "PATCH",
  );
  await page.getByRole("button", { name: "保存研究问题" }).click();
  await expect(page.getByRole("alert")).toContainText("其他页面更新");
  await expect(page.getByLabel("标题", { exact: true })).toHaveValue(
    "不应丢失的输入",
  );
  await noOverflow(page);
  expect(errors).toEqual([]);
});

test("关系删除恢复不丢记录、行动重新开启保留结项历史", async ({
  page,
}, info) => {
  const { a, record, write } = await setup(page);
  const q = await write("/research-items", {
    request_id: randomUUID(),
    kind: "question",
    title: "一个可以继续探索的问题",
    project_id: a.id,
    details: { kind: "question" },
  });
  await write("/relations", {
    request_id: randomUUID(),
    source: { kind: "record", id: record.id },
    target: { kind: "research_item", id: q.id },
  });
  await page.goto("/map");
  await listMap(page);
  await expect(page.locator(".node-list .node-row")).toHaveCount(2);
  await page.locator(".relation-card > summary").click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "删除关系", exact: true }).click();
  await expect(page.locator(".node-list .node-row")).toHaveCount(1);
  await page.getByLabel("查看已删除关系").check();
  await page.locator(".relation-card > summary").click();
  await page.getByRole("button", { name: "恢复关系", exact: true }).click();
  await expect(page.locator(".node-list .node-row")).toHaveCount(2);
  await page
    .locator(".node-list .node-row")
    .filter({ hasText: q.title })
    .click();
  page.once("dialog", (d) => d.accept());
  await page.getByRole("button", { name: "删除研究问题" }).click();
  await expect(page.locator(".node-list .node-row")).toHaveCount(0);
  await page.getByRole("button", { name: "恢复研究问题" }).click();
  await expect(page.locator(".node-list .node-row")).toHaveCount(2);
  await page.goto("/records/" + record.id);
  await expect(
    page.getByRole("heading", { name: record.title, level: 2 }),
  ).toBeVisible();
  const action = await write("/actions", {
    request_id: randomUUID(),
    title: "一句说明即可结项",
  });
  await page.goto("/next?tab=actions&item=" + action.id);
  await page.getByRole("button", { name: "完成行动", exact: true }).click();
  await page
    .getByLabel("结果说明", { exact: true })
    .fill("已核对口径，尚不能判断支持与否。");
  await noOverflow(page);
  await page.getByRole("button", { name: "确认完成行动" }).click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await page.getByRole("button", { name: "重新开启", exact: true }).click();
  await page.getByLabel("重新开启的原因").fill("需要加入新的样本");
  await page
    .getByRole("dialog")
    .getByRole("button", { name: "确认重新开启", exact: true })
    .click();
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(page.locator(".planning-details .kind-tag")).toContainText(
    "进行中",
  );
  await expect(page.locator(".result-summary")).toContainText("已核对口径");
  await page.getByRole("button", { name: "修改历史", exact: true }).click();
  await expect(page.locator(".m2-history > details")).toHaveCount(3);
  await page
    .locator(".m2-history > details")
    .first()
    .locator("summary")
    .click();
  await expect(page.locator(".m2-history")).toContainText("需要加入新的样本");
  await noOverflow(page);
  await page.screenshot({
    path: info.outputPath("action-history.png"),
    fullPage: true,
  });
});
