import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useSearchParams } from "react-router-dom";
import { api, apiBlob, json, type Project } from "./api";
import type { components } from "./api.generated";
import { ErrorNotice, Loading, Options } from "./common";
import { Pagination } from "./m2-shared";

type Selection = components["schemas"]["ExportSelection"];
type Preview = components["schemas"]["ExportPreview"];
type Kind = components["schemas"]["ExportRef"]["kind"];
type Ref = components["schemas"]["ExportRef"];
const kinds: Record<Kind, string> = {
  project: "项目",
  record: "科研记录与来源",
  research_item: "问题／发现／方向",
  relation: "地图关系",
  action: "行动",
  reflection: "复盘",
  contribution: "贡献",
  growth_entry: "成长条目",
  ability_tag: "能力标签",
};

export default function ExportPage({ projects }: { projects: Project[] }) {
  const [params] = useSearchParams();
  const initialKind = params.get("kind") as Kind,
    initialId = params.get("object");
  const [selection, setSelection] = useState<Selection>(() => ({
    format: "json",
    scope: initialId && kinds[initialKind] ? "selected" : "all",
    types: [],
    project_ids: [],
    objects:
      initialId && kinds[initialKind]
        ? [{ kind: initialKind, id: initialId }]
        : [],
    include_archived: false,
  }));
  const [kind, setKind] = useState<Kind>(
      kinds[initialKind] ? initialKind : "record",
    ),
    [q, setQ] = useState(""),
    [page, setPage] = useState(1),
    [preview, setPreview] = useState<Preview | null>(null),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [message, setMessage] = useState("");
  const types =
    selection.format === "markdown"
      ? { record: kinds.record, reflection: kinds.reflection }
      : kinds;
  const query = new URLSearchParams({
    kind,
    q,
    page: String(page),
    include_archived: String(selection.include_archived),
  });
  const candidates = useQuery({
    queryKey: ["exports", query.toString()],
    queryFn: () =>
      api<components["schemas"]["ExportCandidates"]>(
        "/exports/candidates?" + query,
      ),
    enabled: selection.scope === "selected",
  });
  function change(patch: Partial<Selection>) {
    setSelection({ ...selection, ...patch });
    setPreview(null);
    setMessage("");
  }
  async function run(download: boolean) {
    setBusy(true);
    setError(null);
    setMessage("");
    try {
      if (!download) {
        setPreview(
          await api<Preview>("/exports/preview", json("POST", selection)),
        );
        return;
      }
      const blob = await apiBlob(
        "/exports/download",
        json("POST", { ...selection, fingerprint: preview!.fingerprint }),
      );
      const url = URL.createObjectURL(blob),
        a = document.createElement("a");
      a.href = url;
      a.download = preview!.filename;
      document.body.append(a);
      a.click();
      a.remove();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
      setMessage("下载已发起。分享前请核对文件内容与范围。");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const selected = selection.objects || [];
  function toggle(ref: Ref) {
    const exists = selected.some((r) => r.kind === ref.kind && r.id === ref.id);
    change({
      objects: exists
        ? selected.filter((r) => r.kind !== ref.kind || r.id !== ref.id)
        : [...selected, ref],
    });
  }
  return (
    <section className="ai-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">DATA EXPORT</div>
          <h1>数据导出</h1>
          <p>下载当前正式内容及实际引用的固定版本，保留来源与判断的区别。</p>
        </div>
      </header>
      <fieldset className="ai-card export-fields" disabled={busy}>
        <legend>选择格式与范围</legend>
        <label>
          文件格式
          <select
            value={selection.format}
            onChange={(e) => {
              const format = e.target.value as Selection["format"];
              change({
                format,
                types: selection.types?.filter(
                  (k) =>
                    format === "json" || ["record", "reflection"].includes(k),
                ),
                objects: selected.filter(
                  (r) =>
                    format === "json" ||
                    ["record", "reflection"].includes(r.kind),
                ),
              });
              if (
                format === "markdown" &&
                selected.some((r) => !["record", "reflection"].includes(r.kind))
              )
                setMessage(
                  "Markdown 只支持记录和复盘，其他类型已从选择中移除。请重新核对范围后预览。",
                );
              setKind("record");
              setPage(1);
            }}
          >
            <option value="json">JSON · 完整业务数据</option>
            <option value="markdown">Markdown · 记录与复盘</option>
          </select>
        </label>
        <label>
          导出范围
          <select
            value={selection.scope}
            onChange={(e) =>
              change({
                scope: e.target.value as Selection["scope"],
                project_ids: [],
                objects: [],
              })
            }
          >
            <option value="all">全部项目</option>
            <option value="projects">选定项目</option>
            <option value="unassigned">未归类内容</option>
            <option value="selected">手动选择对象</option>
          </select>
        </label>
        <label className="ai-check">
          <input
            type="checkbox"
            checked={!!selection.include_archived}
            onChange={(e) => change({ include_archived: e.target.checked })}
          />
          包含归档项目与标签（未勾选时排除）
        </label>
        {selection.scope === "projects" && (
          <div>
            <h2>选择项目</h2>
            {projects
              .filter((p) => selection.include_archived || !p.archived)
              .map((p) => (
                <label className="ai-check" key={p.id}>
                  <input
                    type="checkbox"
                    checked={selection.project_ids?.includes(p.id)}
                    onChange={(e) =>
                      change({
                        project_ids: e.target.checked
                          ? [...(selection.project_ids || []), p.id]
                          : selection.project_ids?.filter((id) => id !== p.id),
                      })
                    }
                  />
                  {p.name}
                  {p.archived ? "（归档）" : ""}
                </label>
              ))}
          </div>
        )}
        {selection.scope !== "selected" && (
          <div>
            <h2>对象类型</h2>
            <p>全部不勾选表示导出此格式支持的全部类型。</p>
            {Object.entries(types).map(([k, title]) => (
              <label className="ai-check" key={k}>
                <input
                  type="checkbox"
                  checked={selection.types?.includes(k as Kind)}
                  onChange={(e) =>
                    change({
                      types: e.target.checked
                        ? [...(selection.types || []), k as Kind]
                        : selection.types?.filter((t) => t !== k),
                    })
                  }
                />
                {title}
              </label>
            ))}
          </div>
        )}
        {selection.scope === "selected" && (
          <div>
            <h2>选择对象 · 已选 {selected.length}</h2>
            <div className="filters">
              <select
                aria-label="导出对象类型"
                value={kind}
                onChange={(e) => {
                  setKind(e.target.value as Kind);
                  setPage(1);
                }}
              >
                <Options values={types} />
              </select>
              <input
                aria-label="搜索导出对象"
                placeholder="搜索标题"
                value={q}
                onChange={(e) => {
                  setQ(e.target.value);
                  setPage(1);
                }}
              />
            </div>
            <ErrorNotice error={candidates.error} />
            {candidates.isPending && <Loading />}
            {candidates.data?.items.map((o) => (
              <label className="ai-check" key={String(o.id)}>
                <input
                  type="checkbox"
                  checked={selected.some(
                    (r) => r.kind === kind && r.id === o.id,
                  )}
                  onChange={() => toggle({ kind, id: String(o.id) })}
                />
                {String(o.title) || "无说明关系"}
              </label>
            ))}
            <Pagination
              page={page}
              total={candidates.data?.total || 0}
              onChange={setPage}
            />
            <details>
              <summary>已选对象</summary>
              {selected.map((r) => (
                <p key={r.id}>
                  {kinds[r.kind]} · {r.id}
                  <button onClick={() => toggle(r)}>移除</button>
                </p>
              ))}
            </details>
          </div>
        )}
        <p className="notice">
          删除内容不会导出。跨项目的固定依据会列入附录，普通链接仅保留摘要。文件可能含你的科研材料，请在分享前核对。
        </p>
        <button className="primary" onClick={() => run(false)}>
          生成导出预览
        </button>
      </fieldset>
      <ErrorNotice error={error} />
      {busy && <Loading />}
      {message && <p role="status">{message}</p>}
      {preview && (
        <article className="ai-card">
          <h2>下载前预览</h2>
          <ul>
            {Object.entries(preview.counts).map(([k, n]) => (
              <li key={k}>
                {kinds[k as Kind]}：{n}
              </li>
            ))}
          </ul>
          <p>
            固定版本（含来源）：{preview.fixed_versions} · 总条目：
            {preview.entries} · 约 {(preview.bytes / 1024).toFixed(1)} KiB
          </p>
          {(
            [
              ["跨项目固定依据", preview.cross_project_evidence],
              ["归档内容", preview.archived_content],
              ["来源删除占位", preview.unavailable],
            ] as const
          ).map(([title, values]) => (
            <details key={title}>
              <summary>
                {title} · {values.length}
              </summary>
              {values.map((v, i) => (
                <p key={i}>
                  {String(v.title || v.id)}
                  {v.revision_id ? " · " + String(v.revision_id) : ""}
                </p>
              ))}
            </details>
          ))}
          <p>下载将再次核对正文、版本和引用状态；内容变化时需要重新预览。</p>
          <button className="primary" disabled={busy} onClick={() => run(true)}>
            下载 {selection.format === "json" ? "JSON" : "Markdown"}
          </button>
        </article>
      )}
    </section>
  );
}
