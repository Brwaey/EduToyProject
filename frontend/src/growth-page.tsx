import { PlanningLink } from "./ai-adoption";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, json, time, type Project } from "./api";
import { Dialog, ErrorNotice, Loading, Options, useDirtyGuard } from "./common";
import { Pagination } from "./m2-shared";
import { requestIdentity, type Page } from "./m2";
import { ActionEditor } from "./actions";
import { GrowthEditor, type GrowthSeed } from "./growth-editor";
import {
  GrowthEvidenceCards,
  GrowthText,
  MaterialContent,
} from "./growth-shared";
import {
  contributionTypes,
  evidenceStates,
  growthKinds,
  growthLink,
  growthPath,
  materialPick,
  type AbilityTag,
  type GrowthHistory,
  type GrowthKind,
  type GrowthMaterial,
  type GrowthObject,
} from "./growth";

export default function GrowthPage({ projects }: { projects: Project[] }) {
  const [params, setParams] = useSearchParams(),
    client = useQueryClient();
  const tab = params.get("tab") || "contributions",
    kind: GrowthKind =
      tab === "abilities"
        ? "ability_instance"
        : tab === "understanding"
          ? "understanding_change"
          : "contribution";
  const [q, setQ] = useState(""),
    [project, setProject] = useState(""),
    [from, setFrom] = useState(""),
    [to, setTo] = useState(""),
    [deleted, setDeleted] = useState(false),
    [archived, setArchived] = useState(false),
    [status, setStatus] = useState(""),
    [type, setType] = useState(""),
    [tag, setTag] = useState(""),
    [page, setPage] = useState(1),
    [editor, setEditor] = useState<{
      kind: GrowthKind;
      initial?: GrowthObject;
      seed?: GrowthSeed;
    } | null>(null),
    [tagEditor, setTagEditor] = useState<AbilityTag | null | undefined>(),
    [error, setError] = useState<unknown>(null);
  const query = new URLSearchParams({
    q,
    page: String(page),
    deleted: String(deleted),
    include_archived: String(archived),
  });
  if (project === "unassigned") query.set("unassigned", "true");
  else if (project) query.set("project_id", project);
  if (from) query.set("date_from", from);
  if (to) query.set("date_to", to);
  if (status) query.set("evidence_status", status);
  if (kind !== "contribution") query.set("kind", kind);
  else if (type) query.set("contribution_type", type);
  if (kind === "ability_instance" && tag) query.set("tag_id", tag);
  const list = useQuery({
    queryKey: ["growth", "list", kind, query.toString()],
    queryFn: () => api<Page<GrowthObject>>(growthPath(kind) + "?" + query),
  });
  const tagParams = new URLSearchParams(query);
  tagParams.delete("page");
  tagParams.delete("kind");
  tagParams.delete("tag_id");
  tagParams.delete("contribution_type");
  tagParams.set("archived", "true");
  const tags = useQuery({
    queryKey: ["growth", "tags", "page", tagParams.toString()],
    queryFn: () => api<AbilityTag[]>("/ability-tags?" + tagParams),
    enabled: kind === "ability_instance",
  });
  const id = params.get("id"),
    objectKind =
      params.get("object") === "contribution" ? "contribution" : "growth_entry";
  const detail = useQuery({
    queryKey: ["growth", "detail", objectKind, id],
    queryFn: () =>
      api<GrowthObject>(
        growthPath(objectKind) + "/" + id + "?include_deleted=true",
      ),
    enabled: !!id,
  });
  const seedKey = [
      params.get("new"),
      params.get("source_kind"),
      params.get("source_id"),
    ].join(":"),
    loaded = useRef("");
  useEffect(() => {
    if (!params.get("new") || loaded.current === seedKey) return;
    loaded.current = seedKey;
    let ignore = false;
    const target = params.get("new") as GrowthKind,
      sourceKind = params.get("source_kind"),
      sourceId = params.get("source_id");
    if (!Object.keys(growthKinds).includes(target)) return;
    (async () => {
      try {
        let seed: GrowthSeed = {};
        if (sourceKind && sourceId) {
          const path = (
            {
              record: "records",
              action: "actions",
              reflection: "reflections",
              research_item: "research-items",
            } as Record<string, string>
          )[sourceKind];
          if (!path) throw Error("不支持的来源类型");
          const [source, revs] = await Promise.all([
            api<{ title: string; project_id: string | null }>(
              "/" + path + "/" + sourceId,
            ),
            api<{ id: string; version: number }[]>(
              "/" + path + "/" + sourceId + "/revisions",
            ),
          ]);
          seed = {
            title: source.title + " · " + growthKinds[target],
            project_id: source.project_id,
          };
          if (sourceKind === "research_item") {
            seed.question_id = sourceId;
            seed.question_title = source.title;
          } else if (revs[0]) {
            const m = await api<GrowthMaterial>(
              "/growth/material?" +
                new URLSearchParams({
                  kind: sourceKind,
                  id: sourceId,
                  revision_id: revs[0].id,
                }),
            );
            seed.evidence = [
              materialPick(
                m,
                target === "understanding_change" ? "trigger" : "context",
              ),
            ];
          }
        }
        if (!ignore) setEditor({ kind: target, seed });
      } catch (e) {
        if (!ignore) setError(e);
      }
    })();
    return () => {
      ignore = true;
      loaded.current = "";
    };
  }, [seedKey, params]);
  function closeEditor() {
    setEditor(null);
    if (params.has("new")) {
      const next = new URLSearchParams(params);
      next.delete("new");
      next.delete("source_kind");
      next.delete("source_id");
      setParams(next, { replace: true });
    }
  }
  async function addSuggested(name: string) {
    try {
      await api(
        "/ability-tags",
        json("POST", { name, request_id: crypto.randomUUID() }),
      );
      await client.invalidateQueries({ queryKey: ["growth"] });
    } catch (e) {
      setError(e);
    }
  }
  function filter(fn: () => void) {
    fn();
    setPage(1);
  }
  return (
    <section className="growth-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">MY GROWTH</div>
          <h1>我的成长</h1>
          <p>用具体的判断与经历，回看自己的参与和理解变化。</p>
        </div>
        <div className="inline-actions">
          <Link to="/records/ai/new?kind=contribution_candidates">
            AI 寻找贡献候选
          </Link>
          <button className="primary" onClick={() => setEditor({ kind })}>
            记录{growthKinds[kind]}
          </button>
        </div>
      </header>
      <nav className="tabs" aria-label="成长页签">
        {[
          ["contributions", "贡献时间线"],
          ["abilities", "能力档案"],
          ["understanding", "理解变化"],
        ].map(([key, label]) => (
          <button
            key={key}
            className={tab === key ? "active" : ""}
            onClick={() => {
              setPage(1);
              setParams({ tab: key });
            }}
          >
            {label}
          </button>
        ))}
      </nav>
      <div className="filters">
        <label>
          搜索
          <input
            value={q}
            placeholder="贡献、经历或理解"
            onChange={(e) => filter(() => setQ(e.target.value))}
          />
        </label>
        <label>
          项目
          <select
            value={project}
            onChange={(e) => filter(() => setProject(e.target.value))}
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
          发生日期从
          <input
            type="date"
            value={from}
            onChange={(e) => filter(() => setFrom(e.target.value))}
          />
        </label>
        <label>
          至
          <input
            type="date"
            value={to}
            onChange={(e) => filter(() => setTo(e.target.value))}
          />
        </label>
        <label>
          依据状态
          <select
            value={status}
            onChange={(e) => filter(() => setStatus(e.target.value))}
          >
            <option value="">全部</option>
            <Options values={evidenceStates} />
          </select>
        </label>
        {kind === "contribution" && (
          <label>
            贡献类型
            <select
              value={type}
              onChange={(e) => filter(() => setType(e.target.value))}
            >
              <option value="">全部</option>
              <Options values={contributionTypes} />
            </select>
          </label>
        )}
      </div>
      <div className="inline-actions">
        <label className="check-row">
          <input
            type="checkbox"
            checked={archived}
            onChange={(e) => filter(() => setArchived(e.target.checked))}
          />
          包含归档项目
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={deleted}
            onChange={(e) => filter(() => setDeleted(e.target.checked))}
          />
          已删除内容
        </label>
        <button
          onClick={() => client.invalidateQueries({ queryKey: ["growth"] })}
        >
          刷新
        </button>
      </div>
      {kind === "ability_instance" && (
        <section className="growth-tags">
          <div className="inline-actions">
            <h2>能力标签</h2>
            <button onClick={() => setTagEditor(null)}>添加能力标签</button>
            <button onClick={() => filter(() => setTag(""))}>全部实例</button>
          </div>
          <p className="muted">
            数量表示当前筛选范围内的经历，不代表能力等级。
          </p>
          <ErrorNotice error={tags.error} />
          <div className="growth-tag-grid">
            {tags.data?.map((t) => (
              <article
                key={t.id}
                className={"growth-card " + (tag === t.id ? "selected" : "")}
              >
                <button
                  className="text-button"
                  onClick={() => filter(() => setTag(t.id))}
                >
                  {t.name}
                  {t.archived ? " · 已归档" : ""}
                </button>
                <p>{t.description || "用具体实例留下自己的学习过程。"}</p>
                <p>
                  {t.instance_count} 条实例
                  {t.latest_instance
                    ? " · 最近：" + String(t.latest_instance.title)
                    : ""}
                </p>
                <button onClick={() => setTagEditor(t)}>管理标签</button>
              </article>
            ))}
          </div>
          {tags.data?.length === 0 && (
            <div className="empty-state">
              <p>可以先选择一个标签，再记录经历。</p>
              <div className="inline-actions">
                {[
                  "论文判断",
                  "实验设计",
                  "结果分析",
                  "问题提出",
                  "AI 协作",
                ].map((n) => (
                  <button key={n} onClick={() => addSuggested(n)}>
                    {n}
                  </button>
                ))}
              </div>
            </div>
          )}
        </section>
      )}
      <ErrorNotice error={error} />
      <ErrorNotice error={list.error} />
      <div className={"growth-workspace " + (id ? "has-detail" : "")}>
        <div>
          {list.isPending ? (
            <Loading />
          ) : (
            list.data?.items.map((o) => (
              <article
                key={o.id}
                className={"growth-card " + (id === o.id ? "selected" : "")}
              >
                <small>
                  {o.occurred_on} ·{" "}
                  {projects.find((p) => p.id === o.project_id)?.name ||
                    "未归类"}
                </small>
                <h3>
                  <Link to={growthLink(o)}>{o.title}</Link>
                </h3>
                <p>
                  {evidenceStates[o.evidence_status]}
                  {o.archived ? " · 项目已归档" : ""}
                </p>
                {o.contribution_type && (
                  <span>
                    {
                      contributionTypes[
                        o.contribution_type as keyof typeof contributionTypes
                      ]
                    }
                  </span>
                )}
              </article>
            ))
          )}
          {list.data?.total === 0 && (
            <div className="empty-state">
              <h2>还没有符合条件的{growthKinds[kind]}</h2>
              <p>可以先留下自己的自述，再逐步补充依据。</p>
              <button onClick={() => setEditor({ kind })}>
                记录{growthKinds[kind]}
              </button>
            </div>
          )}
          {list.data && (
            <Pagination
              page={page}
              total={list.data.total}
              onChange={setPage}
            />
          )}
        </div>
        {id && (
          <div>
            <ErrorNotice error={detail.error} />
            {detail.isPending ? (
              <Loading />
            ) : (
              detail.data && (
                <GrowthDetail
                  object={detail.data}
                  projects={projects}
                  onEdit={() =>
                    setEditor({
                      kind: detail.data!.kind as GrowthKind,
                      initial: detail.data,
                    })
                  }
                  onClose={() => setParams({ tab })}
                />
              )
            )}
          </div>
        )}
      </div>
      {editor && (
        <GrowthEditor
          key={editor.initial?.id || seedKey + editor.kind}
          {...editor}
          projects={projects}
          onClose={closeEditor}
        />
      )}
      {tagEditor !== undefined && (
        <TagEditor
          initial={tagEditor || undefined}
          onClose={() => setTagEditor(undefined)}
        />
      )}
    </section>
  );
}
function GrowthDetail({
  object: o,
  projects,
  onEdit,
  onClose,
}: {
  object: GrowthObject;
  projects: Project[];
  onEdit: () => void;
  onClose: () => void;
}) {
  const client = useQueryClient(),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [showHistory, setShowHistory] = useState(false),
    [action, setAction] = useState(false);
  const history = useQuery({
    queryKey: ["growth", "history", o.id, o.version],
    queryFn: () =>
      api<GrowthHistory[]>(growthPath(o.kind) + "/" + o.id + "/revisions"),
    enabled: showHistory,
  });
  async function command(name: string) {
    if (
      !window.confirm(
        name === "review"
          ? "已对照固定依据与当前内容，确认这些依据仍适用？"
          : o.deleted_at
            ? "恢复这条内容？"
            : "删除后可在已删除内容中恢复，继续？",
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await api(
        growthPath(o.kind) + "/" + o.id + (name ? "/" + name : ""),
        json(name ? "POST" : "DELETE", {
          expected_version: o.version,
          ...(name === "review"
            ? { current_versions: o.current_versions }
            : {}),
        }),
      );
      await client.invalidateQueries({ queryKey: ["growth"] });
      await client.invalidateQueries({ queryKey: ["m2"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="growth-card growth-detail">
      <div className="inline-actions">
        <span>
          {growthKinds[o.kind as GrowthKind]} · v{o.version}
        </span>
        <button onClick={onClose}>关闭详情</button>
      </div>
      <h2>{o.title}</h2>
      {!o.deleted_at && !o.archived && (
        <PlanningLink
          kind={o.kind === "contribution" ? "contribution" : "growth_entry"}
          id={o.id}
        />
      )}
      <p>
        {o.occurred_on} ·{" "}
        {projects.find((p) => p.id === o.project_id)?.name || "未归类"}
      </p>
      <p className="notice">
        {evidenceStates[o.evidence_status]}。材料引用需结合情境由你判断。
      </p>
      {o.confirmed_at && (
        <p className="muted">本人参与已由用户确认 · {time(o.confirmed_at)}</p>
      )}
      {o.question_id && (
        <p>
          关联问题：
          <Link to={"/map?item=" + o.question_id}>{o.question_title}</Link>
        </p>
      )}
      {(o.tags || []).length > 0 && (
        <p>能力标签：{(o.tags || []).map((t) => String(t.name)).join("、")}</p>
      )}
      <GrowthText value={o.details} />
      <h3>固定版本依据</h3>
      <GrowthEvidenceCards values={o.evidence} />
      {o.needs_review && (
        <p className="notice">
          请对照旧依据与当前内容。嵌套依据变化可在来源详情核对，必要时编辑并选择新的来源版本。
        </p>
      )}
      <ErrorNotice error={error} />
      {o.archived && <p className="notice">项目已归档，恢复项目后可编辑。</p>}
      <div className="inline-actions">
        {!o.deleted_at && (
          <>
            <button disabled={o.archived || busy} onClick={onEdit}>
              编辑内容
            </button>
            <button
              disabled={o.archived || busy}
              onClick={() => setAction(true)}
            >
              据此创建行动
            </button>
            {o.evidence.length > 0 && (
              <button
                disabled={o.archived || busy}
                onClick={() => command("review")}
              >
                确认旧依据仍适用
              </button>
            )}
          </>
        )}
        <button
          disabled={o.archived || busy}
          onClick={() => command(o.deleted_at ? "restore" : "")}
        >
          {o.deleted_at ? "恢复内容" : "删除内容"}
        </button>
        <button onClick={() => setShowHistory(!showHistory)}>修改历史</button>
      </div>
      {(o.actions || []).length > 0 && (
        <section>
          <h3>后续行动</h3>
          {(o.actions || []).map((a) => (
            <p key={String(a.id)}>
              <Link to={"/next?tab=actions&item=" + a.id}>
                {String(a.title)}
              </Link>
            </p>
          ))}
        </section>
      )}
      {showHistory && (
        <section>
          <h3>修改历史</h3>
          <ErrorNotice error={history.error} />
          {history.data?.map((h) => (
            <details key={h.id}>
              <summary>
                第 {h.version} 版 · {h.operation} · {time(h.created_at)}
              </summary>
              <MaterialContent value={h.snapshot} />
              {Array.isArray(h.snapshot.evidence) && (
                <GrowthEvidenceCards
                  values={h.snapshot.evidence as GrowthObject["evidence"]}
                />
              )}
            </details>
          ))}
        </section>
      )}
      {action && (
        <ActionEditor
          projects={projects}
          growthOrigin={o}
          onClose={() => setAction(false)}
        />
      )}
    </article>
  );
}
function TagEditor({
  initial,
  onClose,
}: {
  initial?: AbilityTag;
  onClose: () => void;
}) {
  const client = useQueryClient(),
    identity = useRef({ signature: "", id: crypto.randomUUID() }),
    [name, setName] = useState(initial?.name || ""),
    [description, setDescription] = useState(initial?.description || ""),
    [archived, setArchived] = useState(initial?.archived || false),
    [version, setVersion] = useState(initial?.version),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [showHistory, setShowHistory] = useState(false);
  const [comparison, setComparison] = useState<AbilityTag | null>(null);
  useDirtyGuard(dirty);
  const history = useQuery({
    queryKey: ["growth", "tag-history", initial?.id],
    queryFn: () =>
      api<GrowthHistory[]>("/ability-tags/" + initial!.id + "/revisions"),
    enabled: !!initial && showHistory,
  });
  function close() {
    if (!dirty || window.confirm("还有未保存的修改，确定关闭吗？")) onClose();
  }
  async function save(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const p = { name, description, archived };
      await api(
        "/ability-tags" + (initial ? "/" + initial.id : ""),
        json(
          initial ? "PATCH" : "POST",
          initial
            ? { ...p, expected_version: version }
            : { ...p, request_id: requestIdentity(identity, p) },
        ),
      );
      setDirty(false);
      await client.invalidateQueries({ queryKey: ["growth"] });
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title={initial ? "管理能力标签" : "添加能力标签"} onClose={close}>
      <form onSubmit={save} data-dirty={dirty}>
        <label>
          标签名称
          <input
            required
            maxLength={60}
            value={name}
            onChange={(e) => {
              setName(e.target.value);
              setDirty(true);
            }}
          />
        </label>
        <label>
          说明
          <textarea
            maxLength={2000}
            value={description}
            onChange={(e) => {
              setDescription(e.target.value);
              setDirty(true);
            }}
          />
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={archived}
            onChange={(e) => {
              setArchived(e.target.checked);
              setDirty(true);
            }}
          />
          归档标签（保留历史和已关联实例）
        </label>
        <ErrorNotice error={error} />
        {initial && (
          <button
            type="button"
            onClick={async () => {
              try {
                const tags = await api<AbilityTag[]>(
                  "/ability-tags?archived=true&include_archived=true",
                );
                const tag = tags.find((t) => t.id === initial.id);
                if (tag) setComparison(tag);
                setError(null);
              } catch (e) {
                setError(e);
              }
            }}
          >
            重新载入版本（保留输入）
          </button>
        )}
        {comparison && (
          <section className="notice">
            <p>
              当前 v{comparison.version}：{comparison.name} ·{" "}
              {comparison.description} ·{" "}
              {comparison.archived ? "已归档" : "使用中"}
            </p>
            <button
              type="button"
              onClick={() => {
                setVersion(comparison.version);
                setComparison(null);
              }}
            >
              已对照，使用我的输入继续编辑
            </button>
          </section>
        )}
        <button
          type="submit"
          className="primary"
          disabled={busy || !!comparison}
        >
          保存标签
        </button>
        {initial && (
          <button type="button" onClick={() => setShowHistory(!showHistory)}>
            标签历史
          </button>
        )}
        {showHistory && (
          <>
            <ErrorNotice error={history.error} />
            {history.data?.map((h) => (
              <p key={h.id}>
                v{h.version} · {String(h.snapshot.name)} ·{" "}
                {String(h.snapshot.description || "")} · {time(h.created_at)}
              </p>
            ))}
          </>
        )}
      </form>
    </Dialog>
  );
}
