import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  api,
  ApiError,
  fieldLabels,
  time,
  type Project,
  type Revision as RecordRevision,
  type Source,
} from "./api";
import {
  ErrorNotice,
  Loading,
  Markdown,
  Options,
  useDirtyGuard,
} from "./common";
import {
  actionStates,
  detailLabels,
  detailValue,
  itemStates,
  kinds,
  relationTypes,
  type Evidence,
  type EvidenceInput,
  type GraphNodeData,
  type History,
  type Material,
  type Page,
} from "./m2";

export function ProjectField({
  value,
  onChange,
  projects,
}: {
  value: string;
  onChange: (v: string) => void;
  projects: Project[];
}) {
  return (
    <label>
      所属项目
      <select value={value} onChange={(e) => onChange(e.target.value)}>
        <option value="">未归类</option>
        {projects.map((p) => (
          <option key={p.id} value={p.id} disabled={p.archived}>
            {p.name}
            {p.archived ? "（已归档）" : ""}
          </option>
        ))}
      </select>
    </label>
  );
}
export function Pagination({
  page,
  total,
  size = 20,
  onChange,
}: {
  page: number;
  total: number;
  size?: number;
  onChange: (n: number) => void;
}) {
  return (
    <div className="m2-pagination">
      <span>
        共 {total} 项 · 第 {page} 页
      </span>
      <button
        disabled={page <= 1}
        onClick={() => onChange(page - 1)}
        type="button"
      >
        上一页
      </button>
      <button
        disabled={page * size >= total}
        onClick={() => onChange(page + 1)}
        type="button"
      >
        下一页
      </button>
    </div>
  );
}
export function ObjectPicker({
  onPick,
  kind,
  unlinked = false,
  label = "搜索对象",
}: {
  onPick: (n: GraphNodeData) => void;
  kind?: string;
  unlinked?: boolean;
  label?: string;
}) {
  const [q, setQ] = useState(""),
    [page, setPage] = useState(1),
    [type, setType] = useState(kind || "");
  const params = new URLSearchParams({
    q,
    page: String(page),
    page_size: "10",
  });
  if (type) params.set("kind", type);
  if (unlinked) params.set("unlinked", "true");
  const result = useQuery({
    queryKey: ["m2", "candidates", params.toString()],
    queryFn: () => api<Page<GraphNodeData>>("/graph/candidates?" + params),
  });
  return (
    <div className="object-picker">
      <div className="form-grid">
        <label>
          {label}
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="按标题搜索"
          />
        </label>
        {!kind && (
          <label>
            对象类型
            <select
              value={type}
              onChange={(e) => {
                setType(e.target.value);
                setPage(1);
              }}
            >
              <option value="">全部类型</option>
              <Options values={kinds} />
            </select>
          </label>
        )}
      </div>
      <ErrorNotice error={result.error} />
      {result.isPending ? (
        <Loading />
      ) : (
        <>
          <div className="picker-results">
            {result.data?.items.map((n) => (
              <button type="button" key={n.id} onClick={() => onPick(n)}>
                <span className={"kind-dot " + n.kind} />
                <span>
                  <strong>{n.title}</strong>
                  <small>
                    {kinds[n.kind]} · {n.project_name}
                  </small>
                </span>
                <span>选择</span>
              </button>
            ))}
            {result.data?.total === 0 && (
              <p className="muted">没有找到可选内容。</p>
            )}
          </div>
          <Pagination
            page={page}
            total={result.data?.total || 0}
            size={10}
            onChange={setPage}
          />
        </>
      )}
    </div>
  );
}
export function TextFields({
  labels,
  values,
  onChange,
}: {
  labels: Record<string, string>;
  values: Record<string, unknown>;
  onChange: (k: string, v: string) => void;
}) {
  return (
    <>
      {Object.entries(labels).map(([key, label]) => (
        <label key={key}>
          {label}
          <textarea
            rows={2}
            maxLength={20000}
            value={String(values[key] || "")}
            onChange={(e) => onChange(key, e.target.value)}
          />
        </label>
      ))}
    </>
  );
}
export function useEditor(onClose: () => void) {
  const [dirty, setDirty] = useState(false),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const client = useQueryClient();
  useDirtyGuard(dirty);
  function change(fn: () => void) {
    fn();
    setDirty(true);
    setError(null);
  }
  function close() {
    if (!dirty || window.confirm("放弃尚未保存的修改？")) {
      setDirty(false);
      onClose();
    }
  }
  async function save(fn: () => Promise<unknown>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setDirty(false);
      await client.invalidateQueries({ queryKey: ["m2"] });
      await client.invalidateQueries({ queryKey: ["records"] });
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return { dirty, error, busy, change, close, save, setError };
}
export function ConflictNotice({
  error,
  onReload,
}: {
  error: unknown;
  onReload: () => void;
}) {
  return (
    <>
      <ErrorNotice error={error} />
      {error instanceof ApiError && error.code === "version_conflict" && (
        <button
          type="button"
          onClick={() => {
            if (window.confirm("重新载入会放弃当前输入，确定继续？"))
              onReload();
          }}
        >
          重新载入最新版本
        </button>
      )}
    </>
  );
}
export function EvidenceCards({ evidence }: { evidence: Evidence[] }) {
  return (
    <div className="evidence-list">
      {evidence.length === 0 && (
        <p className="muted small">
          未附证据。表述由用户填写，系统未验证结论。
        </p>
      )}
      {evidence.map((e) => (
        <details className="evidence-card" key={e.id}>
          <summary>
            {e.record_title} · 记录 v{e.record_version}{" "}
            <span className="tag">
              {e.availability === "deleted"
                ? "来源已删除"
                : e.needs_review
                  ? "待复核"
                  : "固定版本"}
            </span>
          </summary>
          {e.availability === "available" && (
            <>
              <p className="small muted">
                {e.stance === "supporting"
                  ? "支持依据"
                  : e.stance === "opposing"
                    ? "反对依据"
                    : "背景依据"}{" "}
                · {e.source_version_id ? "原始材料" : "记录快照"}
              </p>
              {e.quote && <blockquote>{e.quote}</blockquote>}
              <pre>{e.content}</pre>
              <Link to={"/records/" + e.record_id}>查看当前记录</Link>
            </>
          )}
        </details>
      ))}
    </div>
  );
}
export function EvidenceEditor({
  values,
  onChange,
  existing = [],
}: {
  values: EvidenceInput[];
  onChange: (v: EvidenceInput[]) => void;
  existing?: Evidence[];
}) {
  const [adding, setAdding] = useState(false),
    [record, setRecord] = useState<GraphNodeData | null>(null),
    [revId, setRevId] = useState(""),
    [sourceId, setSourceId] = useState(""),
    [field, setField] = useState("body"),
    [quote, setQuote] = useState(""),
    [stance, setStance] = useState<EvidenceInput["stance"]>("context"),
    [error, setError] = useState("");
  const revisions = useQuery({
    queryKey: ["m2", "evidence-revisions", record?.object_id],
    queryFn: () =>
      api<RecordRevision[]>("/records/" + record!.object_id + "/revisions"),
    enabled: !!record,
  });
  const sources = useQuery({
    queryKey: ["m2", "evidence-sources", record?.object_id],
    queryFn: () => api<Source[]>("/records/" + record!.object_id + "/sources"),
    enabled: !!record,
  });
  const selected =
    revisions.data?.find((r) => r.id === revId) || revisions.data?.[0];
  const snapshot = selected?.snapshot as
    | {
        title?: string;
        body?: string;
        fields?: Record<string, string>;
        source_version_ids?: string[];
      }
    | undefined;
  const sourceVersions =
    sources.data
      ?.flatMap((s) => s.versions.map((v) => ({ ...v, name: s.name })))
      .filter((v) => snapshot?.source_version_ids?.includes(v.id)) || [];
  const text = sourceId
    ? sourceVersions.find((v) => v.id === sourceId)?.content || ""
    : field.startsWith("fields.")
      ? snapshot?.fields?.[field.slice(7)] || ""
      : field === "title"
        ? snapshot?.title || ""
        : snapshot?.body || "";
  function reset() {
    setRecord(null);
    setRevId("");
    setSourceId("");
    setQuote("");
    setError("");
    setAdding(false);
  }
  function add() {
    if (!selected) return;
    const idx = text.indexOf(quote);
    if (quote && idx < 0) {
      setError("引用片段未在当前原文中找到，请复制原文片段。");
      return;
    }
    const start = quote ? Array.from(text.slice(0, idx)).length : null;
    onChange([
      ...values,
      {
        record_revision_id: selected.id,
        source_version_id: sourceId || null,
        field_path: field,
        quote,
        start,
        end: start === null ? null : start + Array.from(quote).length,
        stance,
      },
    ]);
    reset();
  }
  return (
    <section className="evidence-editor">
      <h3>
        固定版本证据 <small>选填，可后补</small>
      </h3>
      {values.map((v, i) => {
        const old = existing.find(
          (e) =>
            e.record_revision_id === v.record_revision_id &&
            e.source_version_id === v.source_version_id,
        );
        return (
          <div className="selected-evidence" key={i}>
            <span>
              {old?.record_title || "已选择记录版本"}
              {v.quote ? " · " + v.quote.slice(0, 50) : " · 引用整个字段"}
            </span>
            <button
              type="button"
              onClick={() => onChange(values.filter((_, j) => i !== j))}
            >
              移除
            </button>
          </div>
        );
      })}
      {!adding ? (
        <button type="button" onClick={() => setAdding(true)}>
          添加证据
        </button>
      ) : (
        <div className="evidence-compose">
          {!record ? (
            <ObjectPicker
              kind="record"
              label="选择证据记录"
              onPick={(n) => {
                setRecord(n);
                setRevId("");
                setSourceId("");
              }}
            />
          ) : (
            <>
              <strong>{record.title}</strong>
              <ErrorNotice error={revisions.error || sources.error} />
              <label>
                记录版本
                <select
                  value={selected?.id || ""}
                  onChange={(e) => {
                    setRevId(e.target.value);
                    setSourceId("");
                    setQuote("");
                  }}
                >
                  {revisions.data?.map((r) => (
                    <option key={r.id} value={r.id}>
                      第 {r.version} 版 · {time(r.created_at)}
                    </option>
                  ))}
                </select>
              </label>
              <label>
                引用内容
                <select
                  value={sourceId || field}
                  onChange={(e) => {
                    const isSource = sourceVersions.some(
                      (v) => v.id === e.target.value,
                    );
                    setSourceId(isSource ? e.target.value : "");
                    if (!isSource) setField(e.target.value);
                    setQuote("");
                  }}
                >
                  <option value="body">记录正文</option>
                  <option value="title">记录标题</option>
                  {Object.entries(fieldLabels).map(([k, v]) => (
                    <option key={k} value={"fields." + k}>
                      {v}
                    </option>
                  ))}
                  {sourceVersions.map((v) => (
                    <option key={v.id} value={v.id}>
                      {v.name} · 来源 v{v.version}
                    </option>
                  ))}
                </select>
              </label>
              <pre className="evidence-preview">{text || "（此字段为空）"}</pre>
              <label>
                原文片段（选填，留空引用整个字段）
                <textarea
                  rows={2}
                  value={quote}
                  onChange={(e) => setQuote(e.target.value)}
                />
              </label>
              <label>
                依据用途
                <select
                  value={stance}
                  onChange={(e) => setStance(e.target.value as typeof stance)}
                >
                  <option value="context">背景依据</option>
                  <option value="supporting">支持依据</option>
                  <option value="opposing">反对依据</option>
                </select>
              </label>
              <ErrorNotice error={error} />
              <button type="button" disabled={!selected} onClick={add}>
                确认引用此版本
              </button>
            </>
          )}
          <button type="button" onClick={reset}>
            取消添加
          </button>
        </div>
      )}
    </section>
  );
}
export function SnapshotView({ value }: { value: Record<string, unknown> }) {
  const details = (value.details || value.fields || {}) as Record<
    string,
    unknown
  >;
  return (
    <div className="snapshot">
      <strong>{String(value.title || "")}</strong>
      {Boolean(value.status) && (
        <p className="muted">
          状态：
          {(
            {
              ...actionStates,
              ...itemStates.question,
              ...itemStates.finding,
              ...itemStates.direction,
            } as Record<string, string>
          )[String(value.status)] || String(value.status)}
        </p>
      )}
      {Boolean(value.relation_type) && (
        <p>
          关系：
          {
            relationTypes[value.relation_type as keyof typeof relationTypes]
          } · {String(value.reason || "未填写说明")}
          <br />
          <small>
            起点第 {String(value.source_version)} 版 → 终点第{" "}
            {String(value.target_version)} 版
          </small>
        </p>
      )}
      {Boolean(value.start_at) && (
        <p className="muted">
          {time(String(value.start_at))} — {time(String(value.end_at))} ·{" "}
          {String(value.timezone)}
        </p>
      )}
      {Boolean(details.decision) && (
        <p>
          选择：
          {
            (
              {
                continue: "继续",
                adjust: "调整",
                pause: "暂缓",
                finish: "结束",
              } as Record<string, string>
            )[String(details.decision)]
          }
        </p>
      )}
      {["description", "body", "result_summary", "reopen_reason"].map((k) =>
        value[k] ? (
          <section key={k}>
            <h4>{detailLabels[k] || k}</h4>
            <Markdown>{String(value[k])}</Markdown>
          </section>
        ) : null,
      )}
      {Object.entries(details)
        .filter(
          ([k, v]) =>
            v &&
            (detailLabels[k] || fieldLabels[k as keyof typeof fieldLabels]),
        )
        .map(([k, v]) => (
          <section key={k}>
            <h4>
              {detailLabels[k] || fieldLabels[k as keyof typeof fieldLabels]}
            </h4>
            <p className="preserve">{detailValue(k, v)}</p>
          </section>
        ))}
      {Array.isArray(value.evidence) && (
        <EvidenceCards evidence={value.evidence as Evidence[]} />
      )}
      {Array.isArray(value.results) &&
        value.results.map(
          (r: {
            record_revision_id: string;
            title: string;
            version: number;
            deleted: boolean;
            snapshot: Record<string, unknown> | null;
          }) => (
            <details key={r.record_revision_id}>
              <summary>
                结果记录：{r.title} · 第 {r.version} 版
              </summary>
              {!r.deleted && r.snapshot && <SnapshotView value={r.snapshot} />}
            </details>
          ),
        )}
      {Array.isArray(value.materials) &&
        (value.materials as Material[]).map((m) => (
          <details key={m.revision_id}>
            <summary>
              依据：{m.title} · 第 {m.version} 版
            </summary>
            {m.snapshot && <SnapshotView value={m.snapshot} />}
          </details>
        ))}
    </div>
  );
}
export function HistoryPanel({ path }: { path: string }) {
  const data = useQuery({
    queryKey: ["m2", "history", path],
    queryFn: () => api<History[]>(path + "/revisions"),
  });
  const ops: Record<string, string> = {
    create: "创建",
    edit: "编辑",
    delete: "删除",
    restore: "恢复",
    review: "复核",
    complete: "结项",
    reopen: "重新开启",
  };
  return (
    <section className="m2-history">
      <h3>修改历史</h3>
      <ErrorNotice error={data.error} />
      {data.isPending ? (
        <Loading />
      ) : (
        data.data?.map((r) => (
          <details key={r.id}>
            <summary>
              第 {r.version} 版 · {ops[r.operation] || r.operation} ·{" "}
              {time(r.created_at)}
            </summary>
            <SnapshotView value={r.snapshot} />
          </details>
        ))
      )}
    </section>
  );
}
export function DetailFields({ values }: { values: Record<string, unknown> }) {
  return (
    <div className="detail-fields">
      {Object.entries(values)
        .filter(([k, v]) => v && detailLabels[k])
        .map(([k, v]) => (
          <section key={k}>
            <h4>{detailLabels[k]}</h4>
            <p className="preserve">{detailValue(k, v)}</p>
          </section>
        ))}
    </div>
  );
}
