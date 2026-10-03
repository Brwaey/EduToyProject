import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams, useNavigate } from "react-router-dom";
import { api, json, fieldLabels, recordTypes, time, type Project } from "./api";
import { ErrorNotice, Loading, Options, useDirtyGuard } from "./common";
import { Pagination } from "./m2-shared";
import { relationTypes, type Page } from "./m2";
import {
  isActive,
  taskKinds,
  taskStates,
  suggestionStates,
  type AIConfig,
  type AITask,
  type AISuggestion,
  type Draft,
  type FieldName,
  type AIRelation,
  type Citation,
} from "./ai";

export default function AIInbox({ projects }: { projects: Project[] }) {
  const [params, setParams] = useSearchParams();
  const [tab, setTab] = useState<"suggestions" | "tasks">("suggestions"),
    [status, setStatus] = useState("pending"),
    [kind, setKind] = useState(""),
    [project, setProject] = useState(""),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState<Record<string, number>>({}),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const client = useQueryClient();
  const query = new URLSearchParams({ page: String(page), page_size: "10" });
  if (status) query.set("status", status);
  if (kind) query.set("kind", kind);
  if (project) query.set("project_id", project);
  const list = useQuery({
    queryKey: ["ai", tab, query.toString()],
    queryFn: () => api<Page<AISuggestion | AITask>>("/ai/" + tab + "?" + query),
    refetchInterval: (q) =>
      tab === "tasks" && q.state.data?.items.some((t) => isActive(t as AITask))
        ? 2000
        : false,
  });
  const taskId = params.get("task"),
    suggestionId = params.get("suggestion");
  async function rejectSelected() {
    setBusy(true);
    setError(null);
    try {
      await api(
        "/ai/suggestions/reject-batch",
        json("POST", { suggestions: selected }),
      );
      setSelected({});
      await client.invalidateQueries({ queryKey: ["ai"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="ai-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">AI INBOX</div>
          <h1>AI 收件箱</h1>
          <p>整理是草稿，关联是建议。核对依据后再写入你的研究内容。</p>
        </div>
        <div className="inline-actions">
          <Link to="/settings/model">模型设置</Link>
          <Link to="/records/ai/new?kind=record_draft">整理探索卡</Link>
          <Link
            className="primary"
            to="/records/ai/new?kind=relation_suggestions"
          >
            建议关联
          </Link>
        </div>
      </header>
      <nav className="tabs" aria-label="科研记录页签">
        <Link to="/records">全部记录</Link>
        <span className="active">AI 收件箱</span>
      </nav>
      <div className="tabs">
        <button
          className={tab === "suggestions" ? "active" : ""}
          onClick={() => {
            setTab("suggestions");
            setStatus("pending");
            setPage(1);
          }}
        >
          候选建议
        </button>
        <button
          className={tab === "tasks" ? "active" : ""}
          onClick={() => {
            setTab("tasks");
            setStatus("");
            setPage(1);
          }}
        >
          生成任务
        </button>
      </div>
      <div className="filters">
        <select
          aria-label="AI 状态筛选"
          value={status}
          onChange={(e) => {
            setStatus(e.target.value);
            setPage(1);
          }}
        >
          <option value="">全部状态</option>
          <Options
            values={tab === "suggestions" ? suggestionStates : taskStates}
          />
        </select>
        <select
          aria-label="AI 类型筛选"
          value={kind}
          onChange={(e) => {
            setKind(e.target.value);
            setPage(1);
          }}
        >
          <option value="">全部类型</option>
          <Options values={taskKinds} />
        </select>
        <select
          aria-label="AI 项目筛选"
          value={project}
          onChange={(e) => {
            setProject(e.target.value);
            setPage(1);
          }}
        >
          <option value="">全部项目</option>
          {projects.map((p) => (
            <option value={p.id} key={p.id}>
              {p.name}
            </option>
          ))}
        </select>
        <button onClick={() => list.refetch()}>刷新列表</button>
      </div>
      <ErrorNotice error={list.error} />
      <ErrorNotice error={error} />
      {list.isPending && <Loading />}
      {tab === "suggestions" && Object.keys(selected).length > 0 && (
        <button disabled={busy} onClick={rejectSelected}>
          拒绝选中建议（{Object.keys(selected).length}）
        </button>
      )}
      <div className="ai-list">
        {list.data?.items.map((row) => (
          <div className="ai-row ai-card" key={row.id}>
            {tab === "suggestions" && row.status === "pending" && (
              <input
                aria-label={"选择建议 " + row.id}
                type="checkbox"
                checked={row.id in selected}
                onChange={(e) =>
                  setSelected((old) => {
                    const next = { ...old };
                    if (e.target.checked)
                      next[row.id] = (row as AISuggestion).version;
                    else delete next[row.id];
                    return next;
                  })
                }
              />
            )}
            <button
              className="text-button"
              onClick={() =>
                setParams({ [tab === "tasks" ? "task" : "suggestion"]: row.id })
              }
            >
              {taskKinds[row.kind]} ·{" "}
              {tab === "tasks"
                ? taskStates[row.status]
                : suggestionStates[row.status]}
            </button>
            <span>{time(row.created_at)}</span>
            {tab === "suggestions" &&
              (row as AISuggestion).task.needs_review && (
                <span className="notice">待复核</span>
              )}
          </div>
        ))}
        {list.data?.total === 0 && (
          <div className="ai-card">
            <p>这里还没有符合条件的{tab === "tasks" ? "任务" : "建议"}。</p>
            <p className="ai-muted">
              从一条记录开始整理，或选择已有研究内容寻找关联。
            </p>
          </div>
        )}
      </div>
      {list.data && (
        <Pagination
          page={page}
          total={list.data.total}
          size={10}
          onChange={setPage}
        />
      )}
      {taskId && (
        <TaskDetail
          id={taskId}
          onSuggestion={(id) => setParams({ suggestion: id })}
        />
      )}{" "}
      {suggestionId && (
        <SuggestionDetail key={suggestionId} id={suggestionId} />
      )}
    </section>
  );
}
function Materials({ task }: { task: AITask }) {
  return (
    <details className="ai-materials">
      <summary>查看当时发送的材料与版本</summary>
      {task.inputs.objects.map((o) => (
        <p key={o.key}>
          {o.key} · {o.title} · 当时 v{o.version}／当前 v{o.current_version}
          {o.archived ? " · 已归档" : ""}
        </p>
      ))}
      {task.inputs.materials.map((m) => (
        <details key={m.key}>
          <summary>
            {m.key} · {m.object_key} · {m.field_path}
          </summary>
          <pre>{m.unavailable ? "来源已删除，恢复后可查看。" : m.text}</pre>
          {task.needs_review && !m.unavailable && (
            <>
              <small>当前材料（完整字段）</small>
              <pre>{m.current_text}</pre>
            </>
          )}
        </details>
      ))}
    </details>
  );
}
function TaskDetail({
  id,
  onSuggestion,
}: {
  id: string;
  onSuggestion: (id: string) => void;
}) {
  const navigate = useNavigate();
  const client = useQueryClient(),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const task = useQuery({
    queryKey: ["ai", "task", id],
    queryFn: () => api<AITask>("/ai/tasks/" + id),
    refetchInterval: (q) =>
      !q.state.data || isActive(q.state.data) ? 2000 : false,
  });
  useEffect(() => {
    if (task.data && !isActive(task.data)) {
      void client.invalidateQueries({ queryKey: ["ai", "suggestions"] });
      void client.invalidateQueries({ queryKey: ["ai", "tasks"] });
    }
  }, [task.data?.status, id, client]);
  const request = useRef({ id: "", uuid: crypto.randomUUID() });
  async function command(action: "cancel" | "retry") {
    setBusy(true);
    setError(null);
    try {
      let body: object = {};
      if (action === "retry") {
        const config = await api<AIConfig>("/ai/config");
        const fingerprint = id + ":" + config.version;
        if (request.current.id !== fingerprint)
          request.current = { id: fingerprint, uuid: crypto.randomUUID() };
        body = {
          request_id: request.current.uuid,
          config_version: config.version,
        };
      }
      const t = await api<AITask>(
        "/ai/tasks/" + id + "/" + action,
        json("POST", body),
      );
      await client.invalidateQueries({ queryKey: ["ai"] });
      if (t.id !== id) navigate("/records/ai?task=" + t.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  if (!task.data)
    return (
      <>
        <Loading />
        <ErrorNotice error={task.error} />
      </>
    );
  const t = task.data;
  return (
    <article className="ai-card">
      <h2>
        {taskKinds[t.kind]} · {taskStates[t.status]}
      </h2>
      <p className="ai-wrap">
        {t.model} · {t.endpoint}
      </p>
      <p>
        创建于 {time(t.created_at)} · 用量：
        {t.usage ? JSON.stringify(t.usage) : "未知"}
      </p>
      {t.error_message && (
        <div className="error" role="alert">
          {t.error_message}
        </div>
      )}
      {t.needs_review && <p className="notice">材料已更新，候选需要复核。</p>}
      <Materials task={t} />
      <div className="inline-actions">
        {t.suggestion_ids.map((id, i) => (
          <button key={id} onClick={() => onSuggestion(id)}>
            查看建议 {i + 1}
          </button>
        ))}
        {isActive(t) && (
          <button disabled={busy} onClick={() => command("cancel")}>
            取消任务
          </button>
        )}
        {["failed", "cancelled"].includes(t.status) && (
          <button disabled={busy} onClick={() => command("retry")}>
            使用当前配置重试
          </button>
        )}
        {t.kind !== "connection_test" && (
          <Link to={"/records/ai/new?kind=" + t.kind}>重新选择材料</Link>
        )}
      </div>
      {t.status === "succeeded" &&
        t.kind === "relation_suggestions" &&
        !t.suggestion_ids.length && <p>未找到有充分依据的关系建议。</p>}
      <ErrorNotice error={error} />
    </article>
  );
}
function SuggestionDetail({ id }: { id: string }) {
  const query = useQuery({
    queryKey: ["ai", "suggestion", id],
    queryFn: () => api<AISuggestion>("/ai/suggestions/" + id),
  });
  return (
    <>
      <ErrorNotice error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        query.data && (
          <SuggestionReview s={query.data} refresh={() => query.refetch()} />
        )
      )}
    </>
  );
}
const labels: Record<FieldName, string> = {
  title: "标题",
  record_type: "记录类型",
  ...fieldLabels,
} as Record<FieldName, string>;
function SuggestionReview({
  s,
  refresh,
}: {
  s: AISuggestion;
  refresh: () => unknown;
}) {
  const client = useQueryClient();
  const draft = s.kind === "record_draft" ? (s.original as Draft | null) : null;
  const original =
    s.kind === "relation_suggestions"
      ? (s.original as unknown as AIRelation | null)
      : null;
  const current = s.task.inputs.objects[0]?.current as {
    title: string;
    record_type: string;
    fields: Record<string, string>;
  } | null;
  function currentValue(key: string) {
    return key === "title"
      ? current?.title
      : key === "record_type"
        ? current?.record_type
        : current?.fields[key];
  }
  const [fields, setFields] = useState<Partial<Record<FieldName, string>>>(() =>
      Object.fromEntries(
        Object.entries(draft?.fields || {}).map(([k, v]) => [k, v!.value]),
      ),
    ),
    [checked, setChecked] = useState<Record<string, boolean>>(() =>
      Object.fromEntries(
        Object.entries(draft?.fields || {}).map(([k, v]) => [
          k,
          !currentValue(k) && !!v!.value,
        ]),
      ),
    ),
    [relation, setRelation] = useState<AIRelation | null>(() =>
      original
        ? {
            source: original.source,
            target: original.target,
            relation_type: original.relation_type,
            reason: original.reason,
            uncertainty: original.uncertainty || "",
            citations: original.citations,
          }
        : null,
    ),
    [reviewed, setReviewed] = useState(false),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const versionFingerprint = JSON.stringify(
    s.task.inputs.objects.map((o) => o.current_version),
  );
  useEffect(() => setReviewed(false), [versionFingerprint]);
  useDirtyGuard(dirty);
  async function decide(accept: boolean) {
    setBusy(true);
    setError(null);
    try {
      const body = accept
        ? {
            expected_version: s.version,
            current_versions: Object.fromEntries(
              s.task.inputs.objects.map((o) => [o.key, o.current_version]),
            ),
            reviewed,
            ...(draft
              ? {
                  fields: Object.fromEntries(
                    Object.entries(fields).filter(([k]) => checked[k]),
                  ),
                }
              : { relation }),
          }
        : { expected_version: s.version };
      await api(
        "/ai/suggestions/" + s.id + (accept ? "/accept" : "/reject"),
        json("POST", body),
      );
      setDirty(false);
      await client.invalidateQueries({ queryKey: ["ai"] });
      await client.invalidateQueries({ queryKey: ["records"] });
      await client.invalidateQueries({ queryKey: ["record"] });
      await client.invalidateQueries({ queryKey: ["m2"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const blocked =
    s.task.unavailable || s.task.inputs.objects.some((o) => o.archived);
  return (
    <article className="ai-card ai-review" data-dirty={dirty}>
      <div className="ai-row">
        <h2>核对建议</h2>
        <span>{suggestionStates[s.status]}</span>
        <button
          onClick={() => {
            setReviewed(false);
            refresh();
          }}
        >
          重新载入当前版本（保留输入）
        </button>
      </div>
      <p>
        模型：{s.task.model} · 生成时间：{time(s.created_at)}
      </p>
      <Materials task={s.task} />
      {blocked ? (
        <div className="notice">来源或目标已删除或归档，请恢复后处理。</div>
      ) : s.status === "pending" ? (
        <>
          {draft && (
            <>
              <h3>选择需要写入的字段</h3>
              {Object.entries(draft.fields).map(([key, f]) => {
                const k = key as FieldName;
                return (
                  <div className="ai-field" key={k}>
                    <label className="ai-check">
                      <input
                        type="checkbox"
                        checked={!!checked[k]}
                        onChange={(e) => {
                          setChecked({ ...checked, [k]: e.target.checked });
                          setDirty(true);
                        }}
                      />
                      采用{labels[k]}
                    </label>
                    <div className="ai-compare">
                      <div>
                        <small>当前内容</small>
                        <pre>{currentValue(k) || "（空）"}</pre>
                      </div>
                      <label>
                        AI 草稿／你的修改
                        {k === "record_type" ? (
                          <select
                            aria-label={"建议" + labels[k]}
                            value={fields[k] || ""}
                            onChange={(e) => {
                              setFields({ ...fields, [k]: e.target.value });
                              setDirty(true);
                            }}
                          >
                            <Options values={recordTypes} />
                          </select>
                        ) : (
                          <textarea
                            aria-label={"建议" + labels[k]}
                            rows={3}
                            value={fields[k] || ""}
                            onChange={(e) => {
                              setFields({ ...fields, [k]: e.target.value });
                              setDirty(true);
                            }}
                          />
                        )}
                      </label>
                    </div>
                    <Citations citations={f!.citations} />
                  </div>
                );
              })}
              {draft.questions?.length > 0 && (
                <div>
                  <h3>待补充的问题</h3>
                  <ul>
                    {draft.questions.map((q, i) => (
                      <li key={i}>{q}</li>
                    ))}
                  </ul>
                </div>
              )}
            </>
          )}
          {relation && (
            <>
              <div className="form-grid">
                <label>
                  起点
                  <select
                    value={relation.source}
                    onChange={(e) => {
                      setRelation({ ...relation, source: e.target.value });
                      setDirty(true);
                    }}
                  >
                    {s.task.inputs.objects.map((o) => (
                      <option key={o.key} value={o.key}>
                        {o.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  关系类型
                  <select
                    value={relation.relation_type}
                    onChange={(e) => {
                      setRelation({
                        ...relation,
                        relation_type: e.target
                          .value as AIRelation["relation_type"],
                      });
                      setDirty(true);
                    }}
                  >
                    <Options values={relationTypes} />
                  </select>
                </label>
                <label>
                  终点
                  <select
                    value={relation.target}
                    onChange={(e) => {
                      setRelation({ ...relation, target: e.target.value });
                      setDirty(true);
                    }}
                  >
                    {s.task.inputs.objects.map((o) => (
                      <option key={o.key} value={o.key}>
                        {o.title}
                      </option>
                    ))}
                  </select>
                </label>
              </div>
              <label>
                关系理由
                <textarea
                  aria-label="关系理由"
                  value={relation.reason}
                  onChange={(e) => {
                    setRelation({ ...relation, reason: e.target.value });
                    setDirty(true);
                  }}
                />
              </label>
              <label>
                仍不确定的部分
                <textarea
                  aria-label="仍不确定的部分"
                  value={relation.uncertainty}
                  onChange={(e) => {
                    setRelation({ ...relation, uncertainty: e.target.value });
                    setDirty(true);
                  }}
                />
              </label>
              <h3>引用依据</h3>
              {relation.citations.map((c, i) => (
                <div className="ai-material" key={i}>
                  <label>
                    材料
                    <select
                      value={c.material}
                      onChange={(e) => {
                        setRelation({
                          ...relation,
                          citations: relation.citations.map((v, j) =>
                            i === j ? { ...v, material: e.target.value } : v,
                          ),
                        });
                        setDirty(true);
                      }}
                    >
                      {s.task.inputs.materials
                        .filter(
                          (m) =>
                            s.task.inputs.objects.find(
                              (o) => o.key === m.object_key,
                            )?.kind === "record",
                        )
                        .map((m) => (
                          <option key={m.key} value={m.key}>
                            {m.key} · {m.field_path}
                          </option>
                        ))}
                    </select>
                  </label>
                  <label>
                    原文片段
                    <textarea
                      value={c.quote || ""}
                      onChange={(e) => {
                        setRelation({
                          ...relation,
                          citations: relation.citations.map((v, j) =>
                            i === j ? { ...v, quote: e.target.value } : v,
                          ),
                        });
                        setDirty(true);
                      }}
                    />
                  </label>
                  <label>
                    第几次出现
                    <input
                      type="number"
                      min="1"
                      value={c.occurrence || 1}
                      onChange={(e) => {
                        setRelation({
                          ...relation,
                          citations: relation.citations.map((v, j) =>
                            i === j
                              ? { ...v, occurrence: Number(e.target.value) }
                              : v,
                          ),
                        });
                        setDirty(true);
                      }}
                    />
                  </label>
                  <button
                    onClick={() => {
                      setRelation({
                        ...relation,
                        citations: relation.citations.filter((_, j) => j !== i),
                      });
                      setDirty(true);
                    }}
                  >
                    移除此引用
                  </button>
                </div>
              ))}
              <button
                onClick={() => {
                  const m = s.task.inputs.materials.find(
                    (m) =>
                      s.task.inputs.objects.find((o) => o.key === m.object_key)
                        ?.kind === "record",
                  );
                  if (m) {
                    setRelation({
                      ...relation,
                      citations: [
                        ...relation.citations,
                        { material: m.key, quote: "", occurrence: 1 },
                      ],
                    });
                    setDirty(true);
                  }
                }}
              >
                添加引用
              </button>
            </>
          )}
          {s.task.needs_review && (
            <div className="notice">
              <p>材料已更新，请对照当时材料和当前内容。</p>
              {s.task.inputs.objects.map((o) => (
                <details key={o.key}>
                  <summary>
                    当前：{o.title} · v{o.current_version}
                  </summary>
                  <pre>{JSON.stringify(o.current, null, 2)}</pre>
                </details>
              ))}
              <label className="ai-check">
                <input
                  type="checkbox"
                  checked={reviewed}
                  onChange={(e) => {
                    setReviewed(e.target.checked);
                    setDirty(true);
                  }}
                />
                我已核对，旧依据仍适用于本次采纳
              </label>
            </div>
          )}
          <p className="ai-muted">
            引用已通过原文位置校验；是否支持表述仍需你核对。只写入选中的字段或此条关系。
          </p>
          <div className="inline-actions">
            <button
              className="primary"
              disabled={busy || (s.task.needs_review && !reviewed)}
              onClick={() => decide(true)}
            >
              采纳选定内容
            </button>
            <button disabled={busy} onClick={() => decide(false)}>
              拒绝建议
            </button>
          </div>
        </>
      ) : (
        <>
          <p>该建议已处理，生成时的依据与处理结果保留。</p>
          <details>
            <summary>查看处理内容</summary>
            <pre>{JSON.stringify(s.accepted || s.original, null, 2)}</pre>
          </details>
        </>
      )}
      {s.record_id && <Link to={"/records/" + s.record_id}>查看正式记录</Link>}
      {s.relation_id && (
        <Link to={"/map?relation=" + s.relation_id}>查看正式关系</Link>
      )}
      <ErrorNotice error={error} />
      {s.events.length > 0 && (
        <details>
          <summary>处理历史</summary>
          {s.events.map((e, i) => (
            <p key={i}>
              {String(e.operation)} · {time(String(e.created_at))}
            </p>
          ))}
        </details>
      )}
    </article>
  );
}
function Citations({ citations }: { citations: Citation[] }) {
  return (
    <div className="ai-citations">
      {citations.map((c, i) => (
        <p key={i}>
          依据 {c.material}：{c.quote || "整份选中材料"}
          {(c.occurrence || 1) > 1 ? "（第 " + c.occurrence + " 次）" : ""}
        </p>
      ))}
    </div>
  );
}
