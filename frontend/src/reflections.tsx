import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, json, type Project, type Revision } from "./api";
import { Dialog, ErrorNotice, Loading } from "./common";
import {
  dateInput,
  detailLabels,
  localWeek,
  requestIdentity,
  type History,
  type Material,
  type MaterialRef,
  type Page,
  type Reflection,
  type ReflectionInput,
} from "./m2";
import {
  ConflictNotice,
  DetailFields,
  HistoryPanel,
  Pagination,
  ProjectField,
  SnapshotView,
  TextFields,
  useEditor,
} from "./m2-shared";
const attemptFields = [
  "expectations",
  "actual",
  "known",
  "unknown",
  "explanations",
  "reusable",
  "reason",
  "restart_condition",
  "next_steps",
];
const periodFields = ["progress", "understanding", "blockers", "next_steps"];
function dates(start: string, end: string) {
  const a = new Date(start + "T00:00:00"),
    b = new Date(end + "T00:00:00");
  b.setDate(b.getDate() + 1);
  return {
    start_at: isNaN(a.valueOf()) ? "" : a.toISOString(),
    end_at: isNaN(b.valueOf()) ? "" : b.toISOString(),
  };
}
export function ReflectionEditor({
  initial,
  kind,
  projects,
  onClose,
  recordId,
  actionId,
}: {
  initial?: Reflection;
  kind: "attempt" | "period";
  projects: Project[];
  onClose: () => void;
  recordId?: string;
  actionId?: string;
}) {
  const editor = useEditor(onClose),
    client = useQueryClient(),
    week = localWeek();
  const sunday = new Date(week.end);
  sunday.setDate(sunday.getDate() - 1);
  const [title, setTitle] = useState(
      initial?.title || (kind === "period" ? "本周科研复盘" : ""),
    ),
    [project, setProject] = useState(initial?.project_id || ""),
    [start, setStart] = useState(
      dateInput(initial?.start_at ? new Date(initial.start_at) : week.start),
    ),
    [end, setEnd] = useState(
      dateInput(
        initial?.end_at
          ? new Date(new Date(initial.end_at).getTime() - 1)
          : sunday,
      ),
    ),
    [details, setDetails] = useState<NonNullable<ReflectionInput["details"]>>(
      initial?.details || {
        expectations: "",
        actual: "",
        known: "",
        unknown: "",
        explanations: "",
        reusable: "",
        progress: "",
        understanding: "",
        blockers: "",
        next_steps: "",
        decision: "continue",
        reason: "",
        restart_condition: "",
      },
    ),
    [selected, setSelected] = useState<MaterialRef[]>(
      initial?.materials.map((m) => ({
        kind: m.kind as MaterialRef["kind"],
        id: m.id,
        revision_id: m.revision_id,
      })) || [],
    ),
    [labels, setLabels] = useState<Record<string, string>>(
      Object.fromEntries(
        initial?.materials.map((m) => [m.revision_id, m.title]) || [],
      ),
    ),
    [q, setQ] = useState(""),
    [page, setPage] = useState(1);
  const identity = useRef({ signature: "", id: crypto.randomUUID() });
  const range =
    kind === "period"
      ? dates(start, end)
      : {
          start_at: "1970-01-01T00:00:00Z",
          end_at: new Date(Date.now() + 86400000).toISOString(),
        };
  const queryParams = new URLSearchParams({
    ...range,
    q,
    page: String(page),
    page_size: "10",
  });
  if (project) queryParams.set("project_id", project);
  const materials = useQuery({
    queryKey: ["m2", "materials", kind, start, end, project, q, page],
    queryFn: () => api<Page<Material>>("/reflections/materials?" + queryParams),
    enabled: !!range.start_at && !!range.end_at,
  });
  useEffect(() => {
    if (initial || (!recordId && !actionId)) return;
    let ignore = false;
    const objectId = recordId || actionId!,
      objectKind = recordId ? "record" : "action";
    api<(Revision | History)[]>(
      "/" + (recordId ? "records" : "actions") + "/" + objectId + "/revisions",
    )
      .then((values) => {
        if (ignore || !values[0]) return;
        const r = values[0];
        setSelected([{ kind: objectKind, id: objectId, revision_id: r.id }]);
        setLabels({ [r.id]: String(r.snapshot.title || "相关尝试") });
        setTitle(String(r.snapshot.title || "一次尝试") + " · 复盘");
      })
      .catch(editor.setError);
    return () => {
      ignore = true;
    };
  }, [recordId, actionId]);
  function toggle(m: Material) {
    editor.change(() => {
      setSelected(
        selected.some((r) => r.revision_id === m.revision_id)
          ? selected.filter((r) => r.revision_id !== m.revision_id)
          : [
              ...selected.filter((r) => r.id !== m.id || r.kind !== m.kind),
              {
                kind: m.kind as MaterialRef["kind"],
                id: m.id,
                revision_id: m.revision_id,
              },
            ],
      );
      setLabels({ ...labels, [m.revision_id]: m.title });
    });
  }
  function submit(e: FormEvent) {
    e.preventDefault();
    const payload: ReflectionInput = {
      kind,
      title,
      project_id: project || null,
      ...(kind === "period" ? range : { start_at: null, end_at: null }),
      timezone: Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
      details,
      materials: selected,
    };
    editor.save(() =>
      api(
        initial ? "/reflections/" + initial.id : "/reflections",
        json(
          initial ? "PATCH" : "POST",
          initial
            ? { ...payload, expected_version: initial.version }
            : { ...payload, request_id: requestIdentity(identity, payload) },
        ),
      ),
    );
  }
  return (
    <Dialog
      title={
        initial ? "编辑复盘" : kind === "period" ? "手动周复盘" : "尝试复盘"
      }
      onClose={editor.close}
    >
      <form data-dirty={editor.dirty} onSubmit={submit}>
        <label>
          复盘标题
          <input
            value={title}
            required
            maxLength={200}
            onChange={(e) => editor.change(() => setTitle(e.target.value))}
          />
        </label>
        <ProjectField
          value={project}
          projects={projects}
          onChange={(v) =>
            editor.change(() => {
              setProject(v);
              setPage(1);
            })
          }
        />
        {kind === "period" && (
          <div className="form-grid">
            <label>
              开始日期
              <input
                type="date"
                required
                value={start}
                onChange={(e) =>
                  editor.change(() => {
                    setStart(e.target.value);
                    setPage(1);
                  })
                }
              />
            </label>
            <label>
              结束日期（包含当天）
              <input
                type="date"
                required
                value={end}
                onChange={(e) =>
                  editor.change(() => {
                    setEnd(e.target.value);
                    setPage(1);
                  })
                }
              />
            </label>
          </div>
        )}
        <details open>
          <summary>选择本次依据（已选 {selected.length} 项）</summary>
          <p className="muted small">
            保存后固定这些版本；日期范围变化不会自动替换已经选择的依据。
          </p>
          {selected.map((r) => (
            <div className="selection-row" key={r.revision_id}>
              <span>{labels[r.revision_id] || "已有材料"}</span>
              <button
                type="button"
                onClick={() =>
                  editor.change(() =>
                    setSelected(
                      selected.filter((v) => v.revision_id !== r.revision_id),
                    ),
                  )
                }
              >
                移除材料
              </button>
            </div>
          ))}
          <label>
            搜索复盘材料
            <input
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </label>
          <ErrorNotice error={materials.error} />
          {materials.isPending ? (
            <Loading />
          ) : (
            <div className="material-options">
              {materials.data?.items.map((m) => (
                <label className="check-row" key={m.revision_id}>
                  <input
                    type="checkbox"
                    checked={selected.some(
                      (r) => r.revision_id === m.revision_id,
                    )}
                    onChange={() => toggle(m)}
                  />
                  <span>
                    {m.title}
                    <small>
                      {m.kind === "record"
                        ? "科研记录"
                        : m.kind === "action"
                          ? "行动"
                          : "研究内容"}{" "}
                      · 第 {m.version} 版
                    </small>
                  </span>
                </label>
              ))}
            </div>
          )}
          <Pagination
            page={page}
            total={materials.data?.total || 0}
            size={10}
            onChange={setPage}
          />
        </details>
        <TextFields
          labels={Object.fromEntries(
            (kind === "attempt" ? attemptFields : periodFields).map((k) => [
              k,
              detailLabels[k],
            ]),
          )}
          values={details}
          onChange={(k, v) =>
            editor.change(() => setDetails({ ...details, [k]: v }))
          }
        />
        {kind === "attempt" && (
          <label>
            接下来的选择
            <select
              value={details.decision || "continue"}
              onChange={(e) =>
                editor.change(() =>
                  setDetails({
                    ...details,
                    decision: e.target.value as typeof details.decision,
                  }),
                )
              }
            >
              <option value="continue">继续</option>
              <option value="adjust">调整方法</option>
              <option value="pause">暂缓</option>
              <option value="finish">结束</option>
            </select>
          </label>
        )}
        <p className="notice">
          本次只保存你的复盘与所选依据。创建行动和调整方向将在保存后由你明确执行。
        </p>
        <ConflictNotice
          error={editor.error}
          onReload={() => {
            client.invalidateQueries({ queryKey: ["m2"] });
            onClose();
          }}
        />
        <button className="primary" disabled={editor.busy || !title.trim()}>
          保存复盘
        </button>
      </form>
    </Dialog>
  );
}
export function ReflectionDetail({
  id,
  projects,
  onClose,
}: {
  id: string;
  projects: Project[];
  onClose: () => void;
}) {
  const client = useQueryClient(),
    [editing, setEditing] = useState(false),
    [history, setHistory] = useState(false),
    [error, setError] = useState<unknown>(null);
  const query = useQuery({
    queryKey: ["m2", "reflection", id],
    queryFn: () =>
      api<Reflection>("/reflections/" + id + "?include_deleted=true"),
  });
  if (query.isPending) return <Loading />;
  if (!query.data) return <ErrorNotice error={query.error} />;
  const r = query.data;
  async function remove() {
    if (
      !r.deleted_at &&
      !window.confirm("删除此复盘？相关记录、行动与方向会保留。")
    )
      return;
    try {
      await api(
        "/reflections/" + id + (r.deleted_at ? "/restore" : ""),
        json(r.deleted_at ? "POST" : "DELETE", { expected_version: r.version }),
      );
      await client.invalidateQueries({ queryKey: ["m2"] });
    } catch (e) {
      setError(e);
    }
  }
  return (
    <article className="research-detail">
      <div className="detail-heading">
        <span className="kind-tag finding">
          {r.kind === "period" ? "周期复盘" : "尝试复盘"}
        </span>
        <button onClick={onClose}>关闭详情</button>
      </div>
      <h2>{r.title}</h2>
      <div className="metadata">
        <span>第 {r.version} 版</span>
        <span>
          {projects.find((p) => p.id === r.project_id)?.name || "未归类"}
        </span>
      </div>
      {r.start_at && (
        <p className="muted small">
          {new Date(r.start_at).toLocaleDateString("zh-CN", {
            timeZone: r.timezone,
          })}{" "}
          —{" "}
          {new Date(new Date(r.end_at!).getTime() - 1).toLocaleDateString(
            "zh-CN",
            { timeZone: r.timezone },
          )}{" "}
          · {r.timezone}
        </p>
      )}
      {(r.archived || r.deleted_at) && (
        <p className="notice">
          {r.deleted_at
            ? "复盘已删除，可恢复后继续。"
            : "项目已归档，内容只读。"}
        </p>
      )}
      <DetailFields values={r.details} />
      {r.kind === "attempt" && (
        <p>
          选择：
          {
            {
              continue: "继续",
              adjust: "调整方法",
              pause: "暂缓",
              finish: "结束",
            }[r.details.decision || "continue"]
          }
        </p>
      )}
      <h3>当时选择的依据</h3>
      {r.materials.length === 0 && (
        <p className="muted">本次未选择依据材料。</p>
      )}
      {r.materials.map((m) => (
        <details className="evidence-card" key={m.revision_id}>
          <summary>
            {m.title} · 第 {m.version} 版
          </summary>
          {m.snapshot && <SnapshotView value={m.snapshot} />}
        </details>
      ))}
      <ErrorNotice error={error} />
      <div className="inline-actions">
        {!r.deleted_at && (
          <>
            <button disabled={r.archived} onClick={() => setEditing(true)}>
              编辑复盘
            </button>
            <Link
              className="primary"
              to={"/next?tab=actions&new=1&reflection=" + id}
            >
              据此创建行动
            </Link>
            <Link to="/next?tab=directions">去调整方向</Link>
          </>
        )}
        <button disabled={r.archived} onClick={remove}>
          {r.deleted_at ? "恢复复盘" : "删除复盘"}
        </button>
        <button onClick={() => setHistory(!history)}>修改历史</button>
      </div>
      {history && <HistoryPanel path={"/reflections/" + id} />}{" "}
      {editing && (
        <ReflectionEditor
          initial={r}
          kind={r.kind}
          projects={projects}
          onClose={() => setEditing(false)}
        />
      )}
    </article>
  );
}
