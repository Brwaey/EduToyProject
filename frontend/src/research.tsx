import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api, json, type Project } from "./api";
import { Dialog, ErrorNotice, Loading, Markdown, Options } from "./common";
import {
  detailLabels,
  evidenceInput,
  itemStates,
  kinds,
  objectRef,
  priorities,
  relationTypes,
  requestIdentity,
  type EvidenceInput,
  type GraphNodeData,
  type Item,
  type ItemInput,
  type ItemKind,
  type Page,
  type Relation,
} from "./m2";
import {
  ConflictNotice,
  DetailFields,
  EvidenceCards,
  EvidenceEditor,
  HistoryPanel,
  ObjectPicker,
  Pagination,
  ProjectField,
  TextFields,
  useEditor,
} from "./m2-shared";

const fields: Record<ItemKind, string[]> = {
  question: ["motivation", "hypothesis", "uncertainty"],
  finding: ["conditions", "uncertainty"],
  direction: [
    "question",
    "rationale",
    "supporting",
    "opposing",
    "uncertainty",
    "resources",
    "effort",
    "minimal_action",
    "pause_reason",
    "restart_condition",
  ],
};
export function ItemEditor({
  kind,
  initial,
  projects,
  onClose,
  onSaved,
  initialProject = "",
}: {
  kind: ItemKind;
  initial?: Item;
  projects: Project[];
  onClose: () => void;
  onSaved?: (i: Item) => void;
  initialProject?: string;
}) {
  const editor = useEditor(onClose),
    client = useQueryClient();
  const [title, setTitle] = useState(initial?.title || ""),
    [description, setDescription] = useState(initial?.description || ""),
    [project, setProject] = useState(initial?.project_id || initialProject),
    [status, setStatus] = useState(
      initial?.status || Object.keys(itemStates[kind])[0],
    ),
    [details, setDetails] = useState<Record<string, unknown>>(
      initial?.details || {
        kind,
        ...(kind === "finding"
          ? { statement_type: "observation" }
          : kind === "direction"
            ? { priority: "normal" }
            : {}),
      },
    ),
    [confirmed, setConfirmed] = useState(false),
    [evidence, setEvidence] = useState<EvidenceInput[]>(
      initial?.evidence.map(evidenceInput) || [],
    );
  const identity = useRef({ signature: "", id: crypto.randomUUID() });
  function submit(e: FormEvent) {
    e.preventDefault();
    const payload: ItemInput = {
      kind,
      title,
      description,
      project_id: project || null,
      status,
      details: details as ItemInput["details"],
      evidence,
    };
    editor.save(async () => {
      const result = await api<Item>(
        initial ? "/research-items/" + initial.id : "/research-items",
        json(
          initial ? "PATCH" : "POST",
          initial
            ? { ...payload, expected_version: initial.version }
            : { ...payload, request_id: requestIdentity(identity, payload) },
        ),
      );
      onSaved?.(result);
    });
  }
  return (
    <Dialog
      title={(initial ? "编辑" : "新建") + kinds[kind]}
      onClose={editor.close}
    >
      <form onSubmit={submit} data-dirty={editor.dirty}>
        <label>
          {kind === "finding" ? "发现表述" : "标题"}
          <input
            required
            maxLength={200}
            value={title}
            onChange={(e) => editor.change(() => setTitle(e.target.value))}
            placeholder={
              kind === "question"
                ? "例如：不同评估口径会影响结论吗？"
                : kind === "finding"
                  ? "例如：当前差异可能来自评估配置"
                  : "例如：在统一条件下重新验证"
            }
          />
        </label>
        <div className="form-grid">
          <ProjectField
            value={project}
            onChange={(v) => editor.change(() => setProject(v))}
            projects={projects}
          />
          <label>
            状态
            <select
              value={status}
              onChange={(e) => editor.change(() => setStatus(e.target.value))}
            >
              <Options values={itemStates[kind]} />
            </select>
          </label>
        </div>
        <label>
          补充说明
          <textarea
            rows={3}
            value={description}
            onChange={(e) =>
              editor.change(() => setDescription(e.target.value))
            }
          />
        </label>
        {kind === "finding" && (
          <>
            <label>
              表述类型
              <select
                value={String(details.statement_type)}
                onChange={(e) =>
                  editor.change(() =>
                    setDetails({ ...details, statement_type: e.target.value }),
                  )
                }
              >
                <option value="observation">观察事实</option>
                <option value="interpretation">解释判断</option>
                <option value="hypothesis">待验证假设</option>
              </select>
            </label>
            {status === "reviewed" && initial?.status !== "reviewed" && (
              <label className="check-row">
                <input
                  type="checkbox"
                  required
                  checked={confirmed}
                  onChange={(e) =>
                    editor.change(() => setConfirmed(e.target.checked))
                  }
                />
                我已核对所选依据与这条发现的适用条件
              </label>
            )}
            <p className="muted small">
              “已核对”表示你核对过依据，不表示系统证明了结论；需要至少一项证据。
            </p>
          </>
        )}
        {kind === "direction" && (
          <label>
            优先级
            <select
              value={String(details.priority)}
              onChange={(e) =>
                editor.change(() =>
                  setDetails({ ...details, priority: e.target.value }),
                )
              }
            >
              <Options values={priorities} />
            </select>
          </label>
        )}
        <details className="optional-fields" open={!!initial}>
          <summary>进一步整理（选填）</summary>
          <TextFields
            labels={Object.fromEntries(
              fields[kind].map((k) => [k, detailLabels[k]]),
            )}
            values={details}
            onChange={(k, v) =>
              editor.change(() => setDetails({ ...details, [k]: v }))
            }
          />
        </details>
        <EvidenceEditor
          values={evidence}
          existing={initial?.evidence}
          onChange={(v) => editor.change(() => setEvidence(v))}
        />
        <ConflictNotice
          error={editor.error}
          onReload={() => {
            client.invalidateQueries({ queryKey: ["m2"] });
            onClose();
          }}
        />
        <footer className="editor-footer">
          <span>{editor.dirty ? "有未保存的修改" : "一句话也可以开始"}</span>
          <button className="primary" disabled={editor.busy || !title.trim()}>
            {editor.busy ? "保存中…" : "保存" + kinds[kind]}
          </button>
        </footer>
      </form>
    </Dialog>
  );
}
export function RelationEditor({
  initial,
  source: initialSource,
  target: initialTarget,
  onClose,
}: {
  initial?: Relation;
  source?: GraphNodeData;
  target?: GraphNodeData;
  onClose: () => void;
}) {
  const editor = useEditor(onClose),
    client = useQueryClient();
  const [source, setSource] = useState(
      initial?.source || initialSource || null,
    ),
    [target, setTarget] = useState(initial?.target || initialTarget || null),
    [picking, setPicking] = useState<"source" | "target" | null>(
      initialSource ? "target" : null,
    ),
    [type, setType] = useState<Relation["relation_type"]>(
      initial?.relation_type || "related",
    ),
    [reason, setReason] = useState(initial?.reason || ""),
    [evidence, setEvidence] = useState<EvidenceInput[]>(
      initial?.evidence.map(evidenceInput) || [],
    );
  const identity = useRef({ signature: "", id: crypto.randomUUID() });
  function submit(e: FormEvent) {
    e.preventDefault();
    if (!source || !target) return;
    const payload = {
      source: objectRef(source),
      target: objectRef(target),
      relation_type: type,
      reason,
      evidence,
    };
    editor.save(() =>
      api(
        initial ? "/relations/" + initial.id : "/relations",
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
    <Dialog title={initial ? "编辑关系" : "建立关联"} onClose={editor.close}>
      <form onSubmit={submit} data-dirty={editor.dirty}>
        <div className="relation-endpoints">
          {(["source", "target"] as const).map((k, i) => (
            <div key={k}>
              <small>{i === 0 ? "起点 A" : "终点 B"}</small>
              <strong>
                {(k === "source" ? source : target)?.title || "尚未选择"}
              </strong>
              <button type="button" onClick={() => setPicking(k)}>
                选择{i === 0 ? "起点" : "终点"}
              </button>
            </div>
          ))}
          <button
            type="button"
            onClick={() =>
              editor.change(() => {
                setSource(target);
                setTarget(source);
              })
            }
          >
            交换方向
          </button>
        </div>
        {picking && (
          <ObjectPicker
            label={picking === "source" ? "选择关系起点" : "选择关系终点"}
            onPick={(n) =>
              editor.change(() => {
                (picking === "source" ? setSource : setTarget)(n);
                setPicking(null);
              })
            }
          />
        )}
        <label>
          关系类型
          <select
            value={type}
            onChange={(e) =>
              editor.change(() => setType(e.target.value as typeof type))
            }
          >
            <Options values={relationTypes} />
          </select>
        </label>
        <p className="relation-sentence">
          {source?.title || "A"} <b>{relationTypes[type]}</b>{" "}
          {target?.title || "B"}
        </p>
        <label>
          关系理由{type === "related" ? "（选填）" : ""}
          <textarea
            required={type !== "related"}
            rows={3}
            value={reason}
            onChange={(e) => editor.change(() => setReason(e.target.value))}
          />
        </label>
        <EvidenceEditor
          values={evidence}
          existing={initial?.evidence}
          onChange={(v) => editor.change(() => setEvidence(v))}
        />
        <ConflictNotice
          error={editor.error}
          onReload={() => {
            client.invalidateQueries({ queryKey: ["m2"] });
            onClose();
          }}
        />
        <footer className="editor-footer">
          <span>确认后才加入地图</span>
          <button
            className="primary"
            disabled={editor.busy || !source || !target}
          >
            {editor.busy ? "保存中…" : "保存关系"}
          </button>
        </footer>
      </form>
    </Dialog>
  );
}
export function RelationsPanel({
  relationId,
  node,
  onCreate,
}: {
  node?: GraphNodeData;
  relationId?: string;
  onCreate?: () => void;
}) {
  const client = useQueryClient(),
    [deleted, setDeleted] = useState(false),
    [page, setPage] = useState(1),
    [editing, setEditing] = useState<Relation | null>(null),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const params = new URLSearchParams({
    deleted: String(deleted),
    page: String(page),
  });
  if (node) params.set("node_id", node.id);
  const query = useQuery({
    queryKey: ["m2", "relations", params.toString(), relationId],
    queryFn: async () =>
      relationId
        ? {
            items: [
              await api<Relation>(
                "/relations/" + relationId + "?include_deleted=true",
              ),
            ],
            total: 1,
            page: 1,
            page_size: 20,
          }
        : api<Page<Relation>>("/relations?" + params),
  });
  async function mutate(
    r: Relation,
    operation: "delete" | "restore" | "review",
  ) {
    if (
      operation === "delete" &&
      !window.confirm("删除这条关系？两端内容会保留。")
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await api(
        "/relations/" + r.id + (operation === "delete" ? "" : "/" + operation),
        json(operation === "delete" ? "DELETE" : "POST", {
          expected_version: r.version,
        }),
      );
      await client.invalidateQueries({ queryKey: ["m2"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="relations-panel">
      <div className="section-heading">
        <h3>研究关系</h3>
        {onCreate && <button onClick={onCreate}>建立关联</button>}
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
        查看已删除关系
      </label>
      <ErrorNotice error={query.error || error} />
      {query.isPending ? (
        <Loading />
      ) : (
        query.data?.items.map((r) => (
          <details
            className="relation-card"
            key={r.id}
            open={relationId ? true : undefined}
          >
            <summary>
              {r.source?.title || "起点已删除"}{" "}
              <b>{relationTypes[r.relation_type]}</b>{" "}
              {r.target?.title || "终点已删除"}{" "}
              {r.needs_review && <span className="tag attention">待复核</span>}
            </summary>
            <p className="preserve">
              {r.reason || "普通关联，未填写额外说明。"}
            </p>
            <EvidenceCards evidence={r.evidence} />
            <div className="inline-actions">
              {deleted ? (
                <button
                  disabled={busy || r.archived || !r.available}
                  onClick={() => mutate(r, "restore")}
                >
                  恢复关系
                </button>
              ) : (
                <>
                  <button
                    disabled={r.archived || !r.available}
                    onClick={() => setEditing(r)}
                  >
                    编辑关系
                  </button>
                  <button
                    disabled={busy || r.archived || !r.available}
                    onClick={() => mutate(r, "review")}
                  >
                    确认现有依据仍适用
                  </button>
                  <button
                    disabled={busy || r.archived}
                    onClick={() => mutate(r, "delete")}
                  >
                    删除关系
                  </button>
                </>
              )}
            </div>
            <HistoryPanel path={"/relations/" + r.id} />
          </details>
        ))
      )}
      {query.data?.total === 0 && (
        <p className="muted">还没有{deleted ? "已删除的" : "建立"}关系。</p>
      )}
      <Pagination
        page={page}
        total={query.data?.total || 0}
        onChange={setPage}
      />
      {editing && (
        <RelationEditor initial={editing} onClose={() => setEditing(null)} />
      )}
    </section>
  );
}
export function ItemDetail({
  id,
  projects,
  onClose,
  onDirection,
}: {
  id: string;
  projects: Project[];
  onClose?: () => void;
  onDirection?: (i: Item) => void;
}) {
  const client = useQueryClient(),
    [editing, setEditing] = useState(false),
    [history, setHistory] = useState(false),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const query = useQuery({
    queryKey: ["m2", "item", id],
    queryFn: () => api<Item>("/research-items/" + id + "?include_deleted=true"),
  });
  if (query.isPending) return <Loading />;
  if (!query.data) return <ErrorNotice error={query.error} />;
  const i = query.data;
  async function mutate(operation: "delete" | "restore" | "review") {
    if (
      operation === "delete" &&
      !window.confirm(
        "删除此" + kinds[i.kind] + "？相关连线会隐藏，其他内容会保留。",
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      await api(
        "/research-items/" +
          id +
          (operation === "delete" ? "" : "/" + operation),
        json(operation === "delete" ? "DELETE" : "POST", {
          expected_version: i.version,
        }),
      );
      await client.invalidateQueries({ queryKey: ["m2"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="research-detail">
      <div className="detail-heading">
        <span className={"kind-tag " + i.kind}>{kinds[i.kind]}</span>
        {onClose && <button onClick={onClose}>关闭详情</button>}
      </div>
      <h2>{i.title}</h2>
      <div className="metadata">
        <span>
          {projects.find((p) => p.id === i.project_id)?.name || "未归类"}
        </span>
        <span>{(itemStates[i.kind] as Record<string, string>)[i.status]}</span>
        <span>第 {i.version} 版</span>
      </div>
      {i.deleted_at && (
        <p className="notice">
          内容已删除。恢复后关联会重新出现，单独删除的关系仍保持删除状态。
        </p>
      )}
      {i.archived && <p className="notice">项目已归档，内容只读。</p>}
      {i.needs_review && (
        <p className="notice">
          来源已更新或不可用。旧依据仍保留，请核对后确认。
        </p>
      )}
      <Markdown>{i.description}</Markdown>
      <DetailFields values={i.details} />
      <EvidenceCards evidence={i.evidence} />
      <ErrorNotice error={error} />
      <div className="inline-actions">
        {i.deleted_at ? (
          <button
            disabled={busy || i.archived}
            onClick={() => mutate("restore")}
          >
            恢复{kinds[i.kind]}
          </button>
        ) : (
          <>
            <button disabled={i.archived} onClick={() => setEditing(true)}>
              编辑{kinds[i.kind]}
            </button>
            <button
              disabled={busy || i.archived}
              onClick={() => mutate("review")}
            >
              确认现有依据仍适用
            </button>
            <button
              disabled={busy || i.archived}
              onClick={() => mutate("delete")}
            >
              删除{kinds[i.kind]}
            </button>
          </>
        )}
        <button onClick={() => setHistory(!history)}>修改历史</button>
      </div>
      {!i.deleted_at && (
        <div className="next-links">
          {i.kind === "direction" ? (
            <Link
              className="primary"
              to={"/next?tab=actions&new=1&direction=" + id}
            >
              从方向创建行动
            </Link>
          ) : (
            <button disabled={i.archived} onClick={() => onDirection?.(i)}>
              提出后续方向
            </button>
          )}
          {i.kind === "direction" && (
            <Link to={"/next?tab=actions&direction=" + id}>
              查看该方向的行动
            </Link>
          )}
        </div>
      )}
      {history && <HistoryPanel path={"/research-items/" + id} />}{" "}
      {editing && (
        <ItemEditor
          kind={i.kind}
          initial={i}
          projects={projects}
          onClose={() => setEditing(false)}
        />
      )}
    </article>
  );
}
