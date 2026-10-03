import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { ActionDetail, ActionEditor } from "./actions";
import { api, type Project } from "./api";
import { ErrorNotice, Loading, Options } from "./common";
import {
  actionStates,
  itemStates,
  priorities,
  type Action,
  type Item,
  type Page,
  type Reflection,
} from "./m2";
import { Pagination } from "./m2-shared";
import { ReflectionDetail, ReflectionEditor } from "./reflections";
import { ItemDetail, ItemEditor } from "./research";
export default function NextPage({ projects }: { projects: Project[] }) {
  const [params, setParams] = useSearchParams(),
    tab = params.get("tab") || "directions",
    selected = params.get("item") || "",
    directionId = params.get("direction") || "";
  const [project, setProject] = useState(""),
    [q, setQ] = useState(""),
    [status, setStatus] = useState(""),
    [priority, setPriority] = useState(""),
    [deleted, setDeleted] = useState(false),
    [page, setPage] = useState(1),
    [creating, setCreating] = useState(false),
    [reflectionKind, setReflectionKind] = useState<"attempt" | "period">(
      "period",
    );
  useEffect(() => {
    if (params.get("new")) {
      setReflectionKind(params.get("new") === "attempt" ? "attempt" : "period");
      setCreating(true);
    }
  }, [params.toString()]);
  function close() {
    setCreating(false);
    const next = new URLSearchParams(params);
    next.delete("new");
    next.delete("record");
    next.delete("action");
    next.delete("reflection");
    setParams(next, { replace: true });
  }
  function switchTab(t: string) {
    setStatus("");
    setPage(1);
    setParams({ tab: t });
  }
  const path =
      tab === "directions"
        ? "/research-items"
        : tab === "actions"
          ? "/actions"
          : "/reflections",
    queryParams = new URLSearchParams({
      q,
      page: String(page),
      deleted: String(deleted),
    });
  if (project === "unassigned") queryParams.set("unassigned", "true");
  else if (project) queryParams.set("project_id", project);
  if (tab === "directions") {
    queryParams.set("kind", "direction");
    if (priority) queryParams.set("priority", priority);
  }
  if (tab !== "reflections" && status) queryParams.set("status", status);
  if (tab === "actions" && directionId)
    queryParams.set("direction_id", directionId);
  const data = useQuery({
    queryKey: ["m2", "planning", path, queryParams.toString()],
    queryFn: () =>
      api<Page<Item | Action | Reflection>>(path + "?" + queryParams),
  });
  const direction = useQuery({
    queryKey: ["m2", "item", directionId],
    queryFn: () => api<Item>("/research-items/" + directionId),
    enabled: !!directionId,
  });
  const rows = data.data?.items || [],
    groups =
      tab === "directions"
        ? Object.entries(itemStates.direction).map(([key, label]) => ({
            key,
            label,
            rows: rows.filter((r) => "status" in r && r.status === key),
          }))
        : [
            {
              key: "all",
              label: tab === "actions" ? "行动列表" : "复盘记录",
              rows,
            },
          ];
  function choose(id: string) {
    const next = new URLSearchParams(params);
    next.set("item", id);
    setParams(next);
  }
  function closeDetail() {
    const next = new URLSearchParams(params);
    next.delete("item");
    setParams(next);
  }
  return (
    <section className="workspace-page">
      <header className="workspace-header">
        <div>
          <span className="eyebrow">从已有证据，走向下一次探索</span>
          <h1>下一步</h1>
          <p>保留选择的理由，把想法变成一次具体行动。</p>
        </div>
        <div className="inline-actions">
          {tab === "reflections" && (
            <button
              onClick={() => {
                setReflectionKind("attempt");
                setCreating(true);
              }}
            >
              新建尝试复盘
            </button>
          )}
          <button
            className="primary"
            onClick={() => {
              setReflectionKind("period");
              setCreating(true);
            }}
          >
            {tab === "directions"
              ? "新建候选方向"
              : tab === "actions"
                ? "创建行动"
                : "开始周复盘"}
          </button>
        </div>
      </header>
      <nav className="planning-tabs" aria-label="下一步分类">
        {[
          ["directions", "方向池"],
          ["actions", "行动"],
          ["reflections", "复盘"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            onClick={() => switchTab(key)}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="workspace-filters">
        <label>
          项目筛选
          <select
            value={project}
            onChange={(e) => {
              setProject(e.target.value);
              setPage(1);
            }}
          >
            <option value="">全部项目</option>
            <option value="unassigned">未归类</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.archived ? "（已归档）" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          搜索
          {tab === "directions" ? "方向" : tab === "actions" ? "行动" : "复盘"}
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </label>
        {tab !== "reflections" && (
          <label>
            状态筛选
            <select
              value={status}
              onChange={(e) => {
                setStatus(e.target.value);
                setPage(1);
              }}
            >
              <option value="">全部状态</option>
              <Options
                values={
                  tab === "directions" ? itemStates.direction : actionStates
                }
              />
            </select>
          </label>
        )}
        {tab === "directions" && (
          <label>
            优先级筛选
            <select
              value={priority}
              onChange={(e) => {
                setPriority(e.target.value);
                setPage(1);
              }}
            >
              <option value="">全部优先级</option>
              <Options values={priorities} />
            </select>
          </label>
        )}
      </div>
      <label className="check-row">
        <input
          type="checkbox"
          checked={deleted}
          onChange={(e) => {
            setDeleted(e.target.checked);
            setPage(1);
          }}
        />
        查看已删除内容
      </label>
      {directionId && (
        <p className="notice">
          当前方向：{direction.data?.title || "载入中"}{" "}
          <button
            onClick={() => {
              const next = new URLSearchParams(params);
              next.delete("direction");
              setParams(next);
            }}
          >
            查看全部行动
          </button>
        </p>
      )}
      <ErrorNotice error={data.error || direction.error} />
      <div className={"planning-workspace" + (selected ? " with-detail" : "")}>
        <div>
          {data.isPending ? (
            <Loading />
          ) : data.data?.total === 0 ? (
            <div className="m2-empty">
              <span className="empty-orbit">↗</span>
              <h2>
                {deleted
                  ? "没有已删除内容"
                  : q || status
                    ? "没有符合条件的内容"
                    : tab === "directions"
                      ? "先留下一个值得尝试的方向"
                      : tab === "actions"
                        ? "选择一次可以推进的小行动"
                        : "给自己的判断留一点空间"}
              </h2>
              <p>
                {tab === "directions"
                  ? "从问题、发现或不确定性出发，不必急着作出结论。"
                  : tab === "actions"
                    ? "明确想做什么、怎样算完成，其余内容可以后补。"
                    : "回看真实材料，写下自己的认识和下一步选择。"}
              </p>
            </div>
          ) : (
            <div
              className={
                tab === "directions" ? "direction-board" : "planning-list"
              }
            >
              {groups.map((g) => (
                <section className="direction-column" key={g.key}>
                  <h3>
                    {g.label}
                    <small>{g.rows.length}</small>
                  </h3>
                  {g.rows.map((r) => (
                    <button
                      key={r.id}
                      className={
                        "planning-card" + (selected === r.id ? " selected" : "")
                      }
                      onClick={() => choose(r.id)}
                    >
                      <strong>{r.title}</strong>
                      <small>
                        {projects.find((p) => p.id === r.project_id)?.name ||
                          "未归类"}
                        {r.archived ? " · 已归档" : ""}
                      </small>
                      {"status" in r && (
                        <span className="tag">
                          {tab === "actions"
                            ? (actionStates as Record<string, string>)[r.status]
                            : (itemStates.direction as Record<string, string>)[
                                r.status
                              ]}
                        </span>
                      )}
                      {tab === "directions" &&
                        "kind" in r &&
                        r.kind === "direction" &&
                        "priority" in r.details && (
                          <span className="small">
                            优先级：
                            {
                              priorities[
                                r.details.priority as keyof typeof priorities
                              ]
                            }
                          </span>
                        )}
                      {"result_summary" in r && r.result_summary && (
                        <p>{r.result_summary.slice(0, 80)}</p>
                      )}
                    </button>
                  ))}
                </section>
              ))}
            </div>
          )}
          <Pagination
            page={page}
            total={data.data?.total || 0}
            onChange={setPage}
          />
        </div>
        {selected && (
          <aside className="planning-details">
            {tab === "directions" ? (
              <ItemDetail
                key={selected}
                id={selected}
                projects={projects}
                onClose={closeDetail}
                onDirection={() => setCreating(true)}
              />
            ) : tab === "actions" ? (
              <ActionDetail
                key={selected}
                id={selected}
                projects={projects}
                onClose={closeDetail}
              />
            ) : (
              <ReflectionDetail
                key={selected}
                id={selected}
                projects={projects}
                onClose={closeDetail}
              />
            )}
          </aside>
        )}
      </div>
      {creating &&
        (tab === "directions" ? (
          <ItemEditor
            kind="direction"
            projects={projects}
            initialProject={project === "unassigned" ? "" : project}
            onClose={close}
          />
        ) : tab === "actions" ? (
          (!directionId || direction.data) && (
            <ActionEditor
              projects={projects}
              direction={direction.data}
              originReflection={params.get("reflection") || undefined}
              onClose={close}
            />
          )
        ) : (
          <ReflectionEditor
            kind={reflectionKind}
            projects={projects}
            recordId={params.get("record") || undefined}
            actionId={params.get("action") || undefined}
            onClose={close}
          />
        ))}
    </section>
  );
}
