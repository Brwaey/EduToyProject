import { PlanningLink, AdoptionPanel } from "./ai-adoption";
import { FixedMaterial, GrowthContext } from "./growth-shared";
import { growthPath, type GrowthObject, type GrowthMaterial } from "./growth";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import {
  api,
  emptyFields,
  fieldLabels,
  json,
  outcomes,
  recordTypes,
  workStates,
  type Project,
  type RecordCreate,
  type Revision,
} from "./api";
import { Dialog, ErrorNotice, Loading, Options } from "./common";
import {
  actionStates,
  detailLabels,
  requestIdentity,
  type Action,
  type ActionInput,
  type Item,
  type ResultRef,
} from "./m2";
import {
  ConflictNotice,
  DetailFields,
  HistoryPanel,
  ObjectPicker,
  ProjectField,
  SnapshotView,
  TextFields,
  useEditor,
} from "./m2-shared";

export function ActionEditor({
  initial,
  projects,
  direction,
  originReflection,
  growthOrigin,
  onClose,
}: {
  initial?: Action;
  projects: Project[];
  direction?: Item;
  originReflection?: string;
  growthOrigin?: GrowthObject;
  onClose: () => void;
}) {
  const editor = useEditor(onClose),
    client = useQueryClient(),
    identity = useRef({ signature: "", id: crypto.randomUUID() });
  const [title, setTitle] = useState(
      initial?.title ||
        (growthOrigin
          ? String(
              growthOrigin.details.next_steps ||
                "围绕“" + growthOrigin.title + "”继续探索",
            ).slice(0, 200)
          : ""),
    ),
    [project, setProject] = useState(
      initial?.project_id ||
        direction?.project_id ||
        growthOrigin?.project_id ||
        "",
    ),
    [directionId, setDirectionId] = useState(
      initial?.direction_id || direction?.id || "",
    ),
    [directionTitle, setDirectionTitle] = useState(
      initial?.direction_title || direction?.title || "",
    ),
    [picking, setPicking] = useState(false),
    [status, setStatus] = useState<Action["status"]>(
      initial?.status || "planned",
    ),
    [details, setDetails] = useState<Action["details"]>(
      initial?.details || {
        research_goal: "",
        learning_goal: growthOrigin
          ? String(growthOrigin.details.next_steps || "")
          : "",
        completion_criteria: "",
        expected_date: null,
        effort: "",
        pause_reason: "",
        restart_condition: "",
      },
    ),
    [results, setResults] = useState<ResultRef[]>(
      initial?.results.map((r) => ({
        record_id: r.record_id,
        record_revision_id: r.record_revision_id,
      })) || [],
    ),
    [resultTitles, setResultTitles] = useState<Record<string, string>>(
      Object.fromEntries(
        initial?.results.map((r) => [r.record_id, r.title]) || [],
      ),
    );
  function submit(e: FormEvent) {
    e.preventDefault();
    const payload: ActionInput = {
      title,
      project_id: project || null,
      direction_id: directionId || null,
      origin_reflection_id:
        initial?.origin_reflection_id || originReflection || null,
      status,
      details,
      results,
    };
    if (growthOrigin && !initial) {
      const action = {
        ...payload,
        request_id: requestIdentity(identity, payload),
      };
      editor.save(async () => {
        await api(
          growthPath(growthOrigin.kind) + "/" + growthOrigin.id + "/actions",
          json("POST", {
            expected_version: growthOrigin.version,
            revision_id: growthOrigin.revision_id,
            request_id: action.request_id,
            action,
          }),
        );
        await client.invalidateQueries({ queryKey: ["growth"] });
      });
      return;
    }
    editor.save(() =>
      api(
        initial ? "/actions/" + initial.id : "/actions",
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
    <Dialog title={initial ? "编辑行动" : "创建行动"} onClose={editor.close}>
      <form onSubmit={submit} data-dirty={editor.dirty}>
        <label>
          行动标题
          <input
            value={title}
            required
            maxLength={200}
            onChange={(e) => editor.change(() => setTitle(e.target.value))}
            placeholder="一次可以完成的具体探索"
          />
        </label>
        <ProjectField
          projects={projects}
          value={project}
          onChange={(v) => editor.change(() => setProject(v))}
        />
        <div className="selection-row">
          <span>关联方向：{directionTitle || "暂不关联"}</span>
          <button type="button" onClick={() => setPicking(!picking)}>
            选择方向
          </button>
          {directionId && (
            <button
              type="button"
              onClick={() =>
                editor.change(() => {
                  setDirectionId("");
                  setDirectionTitle("");
                })
              }
            >
              取消关联方向
            </button>
          )}
        </div>
        {picking && (
          <ObjectPicker
            kind="direction"
            onPick={(n) =>
              editor.change(() => {
                setDirectionId(n.object_id);
                setDirectionTitle(n.title);
                setPicking(false);
                if (!initial && !project) setProject(n.project_id || "");
              })
            }
          />
        )}
        <label>
          行动状态
          <select
            value={status}
            disabled={
              initial?.status === "completed" || initial?.status === "cancelled"
            }
            onChange={(e) =>
              editor.change(() => setStatus(e.target.value as Action["status"]))
            }
          >
            {Object.entries(actionStates)
              .filter(
                ([k]) => k !== "completed" || initial?.status === "completed",
              )
              .map(([k, v]) => (
                <option key={k} value={k}>
                  {v}
                </option>
              ))}
          </select>
        </label>
        <TextFields
          labels={Object.fromEntries(
            [
              "research_goal",
              "learning_goal",
              "completion_criteria",
              "effort",
              "pause_reason",
              "restart_condition",
            ].map((k) => [k, detailLabels[k]]),
          )}
          values={details}
          onChange={(k, v) =>
            editor.change(() => setDetails({ ...details, [k]: v }))
          }
        />
        <label>
          预计日期（选填）
          <input
            type="date"
            value={details.expected_date || ""}
            onChange={(e) =>
              editor.change(() =>
                setDetails({
                  ...details,
                  expected_date: e.target.value || null,
                }),
              )
            }
          />
        </label>
        <details>
          <summary>关联已有结果记录（{results.length}）</summary>
          {results.map((r) => (
            <div className="selection-row" key={r.record_id}>
              <span>{resultTitles[r.record_id] || "记录版本"}</span>
              <button
                type="button"
                onClick={() =>
                  editor.change(() =>
                    setResults(
                      results.filter((x) => x.record_id !== r.record_id),
                    ),
                  )
                }
              >
                移除结果关联
              </button>
            </div>
          ))}
          <ObjectPicker
            kind="record"
            onPick={async (n) => {
              try {
                const revisions = await api<Revision[]>(
                  "/records/" + n.object_id + "/revisions",
                );
                editor.change(() => {
                  setResults([
                    ...results.filter((r) => r.record_id !== n.object_id),
                    {
                      record_id: n.object_id,
                      record_revision_id: revisions[0].id,
                    },
                  ]);
                  setResultTitles({ ...resultTitles, [n.object_id]: n.title });
                });
              } catch (e) {
                editor.setError(e);
              }
            }}
          />
        </details>
        <ConflictNotice
          error={editor.error}
          onReload={() => {
            client.invalidateQueries({ queryKey: ["m2"] });
            onClose();
          }}
        />
        <footer className="editor-footer">
          <span>结果说明在结项时填写</span>
          <button className="primary" disabled={editor.busy || !title.trim()}>
            保存行动
          </button>
        </footer>
      </form>
    </Dialog>
  );
}
export function CompleteDialog({
  action,
  projects,
  onClose,
}: {
  action: Action;
  projects: Project[];
  onClose: () => void;
}) {
  const editor = useEditor(onClose),
    client = useQueryClient(),
    identity = useRef({ signature: "", id: crypto.randomUUID() }),
    recordIdentity = useRef({ signature: "", id: crypto.randomUUID() });
  const [summary, setSummary] = useState(""),
    [newRecord, setNewRecord] = useState(false),
    [link, setLink] = useState(false),
    [results, setResults] = useState<ResultRef[]>([]),
    [titles, setTitles] = useState<Record<string, string>>({});
  const [draft, setDraft] = useState<Omit<RecordCreate, "request_id">>({
    title: "",
    body: "",
    project_id: action.project_id,
    record_type: "note",
    work_status: "in_progress",
    outcome_status: "none",
    fields: { ...emptyFields },
  });
  function submit(e: FormEvent) {
    e.preventDefault();
    const payload = {
      expected_version: action.version,
      result_summary: summary,
      records: results,
      new_record: newRecord
        ? { ...draft, request_id: requestIdentity(recordIdentity, draft) }
        : null,
      link_direction: newRecord && link,
    };
    editor.save(() =>
      api(
        "/actions/" + action.id + "/complete",
        json("POST", {
          ...payload,
          request_id: requestIdentity(identity, payload),
        }),
      ),
    );
  }
  return (
    <Dialog title="完成行动" onClose={editor.close}>
      <form onSubmit={submit} data-dirty={editor.dirty}>
        <h3>{action.title}</h3>
        <label>
          结果说明
          <textarea
            required
            rows={3}
            value={summary}
            onChange={(e) => editor.change(() => setSummary(e.target.value))}
            placeholder="一句话说明做到了什么、发现什么，或为什么尚不能下结论。"
          />
        </label>
        <details>
          <summary>关联已有记录（选填，已选 {results.length} 条）</summary>
          {results.map((r) => (
            <div className="selection-row" key={r.record_id}>
              <span>{titles[r.record_id]}</span>
              <button
                type="button"
                onClick={() =>
                  editor.change(() =>
                    setResults(
                      results.filter((x) => x.record_id !== r.record_id),
                    ),
                  )
                }
              >
                移除
              </button>
            </div>
          ))}
          <ObjectPicker
            kind="record"
            onPick={async (n) => {
              try {
                const versions = await api<Revision[]>(
                  "/records/" + n.object_id + "/revisions",
                );
                editor.change(() => {
                  setResults([
                    ...results.filter((r) => r.record_id !== n.object_id),
                    {
                      record_id: n.object_id,
                      record_revision_id: versions[0].id,
                    },
                  ]);
                  setTitles({ ...titles, [n.object_id]: n.title });
                });
              } catch (e) {
                editor.setError(e);
              }
            }}
          />
        </details>
        <label className="check-row">
          <input
            type="checkbox"
            checked={newRecord}
            onChange={(e) =>
              editor.change(() => setNewRecord(e.target.checked))
            }
          />
          同时新建一条结果记录
        </label>
        {newRecord && (
          <div className="record-draft">
            <label>
              结果记录标题
              <input
                value={draft.title}
                onChange={(e) =>
                  editor.change(() =>
                    setDraft({ ...draft, title: e.target.value }),
                  )
                }
              />
            </label>
            <label>
              结果记录正文
              <textarea
                rows={4}
                value={draft.body}
                onChange={(e) =>
                  editor.change(() =>
                    setDraft({ ...draft, body: e.target.value }),
                  )
                }
              />
            </label>
            <ProjectField
              projects={projects}
              value={draft.project_id || ""}
              onChange={(v) =>
                editor.change(() =>
                  setDraft({ ...draft, project_id: v || null }),
                )
              }
            />
            <div className="form-grid">
              <label>
                记录类型
                <select
                  value={draft.record_type}
                  onChange={(e) =>
                    editor.change(() =>
                      setDraft({
                        ...draft,
                        record_type: e.target
                          .value as RecordCreate["record_type"],
                      }),
                    )
                  }
                >
                  <Options values={recordTypes} />
                </select>
              </label>
              <label>
                工作状态
                <select
                  value={draft.work_status}
                  onChange={(e) =>
                    editor.change(() =>
                      setDraft({
                        ...draft,
                        work_status: e.target
                          .value as RecordCreate["work_status"],
                      }),
                    )
                  }
                >
                  <Options values={workStates} />
                </select>
              </label>
              <label>
                结果判断
                <select
                  value={draft.outcome_status}
                  onChange={(e) =>
                    editor.change(() =>
                      setDraft({
                        ...draft,
                        outcome_status: e.target
                          .value as RecordCreate["outcome_status"],
                      }),
                    )
                  }
                >
                  <Options values={outcomes} />
                </select>
              </label>
            </div>
            <details>
              <summary>整理背景、行动与个人判断（选填）</summary>
              <TextFields
                labels={fieldLabels}
                values={draft.fields || {}}
                onChange={(k, v) =>
                  editor.change(() =>
                    setDraft({
                      ...draft,
                      fields: { ...emptyFields, ...draft.fields, [k]: v },
                    }),
                  )
                }
              />
            </details>
            {action.direction_id && !action.direction_deleted && (
              <label className="check-row">
                <input
                  type="checkbox"
                  checked={link}
                  onChange={(e) =>
                    editor.change(() => setLink(e.target.checked))
                  }
                />
                同时关联到方向「{action.direction_title}」
              </label>
            )}
          </div>
        )}
        <p className="notice">
          将保存结项说明{newRecord ? "、一条科研记录" : ""}
          {newRecord && link ? "和一条方向关联" : ""}
          。方向状态与研究结论由你另行决定。
        </p>
        <ConflictNotice
          error={editor.error}
          onReload={() => {
            client.invalidateQueries({ queryKey: ["m2"] });
            onClose();
          }}
        />
        <button
          className="primary"
          disabled={
            editor.busy ||
            !summary.trim() ||
            (newRecord && !draft.title?.trim() && !draft.body?.trim())
          }
        >
          确认完成行动
        </button>
      </form>
    </Dialog>
  );
}
function ReopenDialog({
  action,
  onClose,
}: {
  action: Action;
  onClose: () => void;
}) {
  const editor = useEditor(onClose),
    client = useQueryClient(),
    [reason, setReason] = useState(""),
    identity = useRef({ signature: "", id: crypto.randomUUID() });
  return (
    <Dialog title="重新开启行动" onClose={editor.close}>
      <form
        data-dirty={editor.dirty}
        onSubmit={(e) => {
          e.preventDefault();
          const value = { expected_version: action.version, reason };
          editor.save(() =>
            api(
              "/actions/" + action.id + "/reopen",
              json("POST", {
                ...value,
                request_id: requestIdentity(identity, value),
              }),
            ),
          );
        }}
      >
        <label>
          重新开启的原因
          <textarea
            required
            value={reason}
            onChange={(e) => editor.change(() => setReason(e.target.value))}
          />
        </label>
        <ConflictNotice
          error={editor.error}
          onReload={() => {
            client.invalidateQueries({ queryKey: ["m2"] });
            onClose();
          }}
        />
        <button className="primary" disabled={editor.busy || !reason.trim()}>
          确认重新开启
        </button>
      </form>
    </Dialog>
  );
}
export function ActionDetail({
  id,
  projects,
  onClose,
}: {
  id: string;
  projects: Project[];
  onClose: () => void;
}) {
  const query = useQuery({
      queryKey: ["m2", "action", id],
      queryFn: () => api<Action>("/actions/" + id + "?include_deleted=true"),
    }),
    client = useQueryClient();
  const [editing, setEditing] = useState(false),
    [complete, setComplete] = useState(false),
    [reopen, setReopen] = useState(false),
    [history, setHistory] = useState(false),
    [error, setError] = useState<unknown>(null);
  if (query.isPending) return <Loading />;
  if (!query.data) return <ErrorNotice error={query.error} />;
  const a = query.data;
  async function remove() {
    if (!a.deleted_at && !window.confirm("删除行动？关联记录会保留。")) return;
    try {
      await api(
        "/actions/" + id + (a.deleted_at ? "/restore" : ""),
        json(a.deleted_at ? "POST" : "DELETE", { expected_version: a.version }),
      );
      await client.invalidateQueries({ queryKey: ["m2"] });
    } catch (e) {
      setError(e);
    }
  }
  return (
    <article className="research-detail">
      <div className="detail-heading">
        <span className="kind-tag direction">
          行动 · {actionStates[a.status]}
        </span>
        <button onClick={onClose}>关闭详情</button>
      </div>
      <h2>{a.title}</h2>
      {!a.deleted_at && !a.archived && <PlanningLink kind="action" id={a.id} />}
      <AdoptionPanel values={a.ai_adoptions || []} />
      {a.growth_origin && (
        <section>
          <h3>发起这次行动的贡献／成长</h3>
          <FixedMaterial material={a.growth_origin as GrowthMaterial} />
        </section>
      )}
      {!a.deleted_at && (
        <GrowthContext kind="action" id={a.id} readonly={a.archived} />
      )}
      <div className="metadata">
        <span>
          {projects.find((p) => p.id === a.project_id)?.name || "未归类"}
        </span>
        <span>第 {a.version} 版</span>
      </div>
      {a.direction_id && (
        <p>
          关联方向：{a.direction_title}{" "}
          {!a.direction_deleted && (
            <Link to={"/next?tab=directions&item=" + a.direction_id}>
              查看方向
            </Link>
          )}
        </p>
      )}
      {a.origin_reflection_id && (
        <Link to={"/next?tab=reflections&item=" + a.origin_reflection_id}>
          查看产生此行动的复盘
        </Link>
      )}
      {a.archived && <p className="notice">项目已归档，内容只读。</p>}
      {a.deleted_at && <p className="notice">行动已删除，可恢复后继续。</p>}
      <DetailFields values={a.details} />
      {a.result_summary && (
        <section className="result-summary">
          <h3>最近的结项说明</h3>
          <p className="preserve">{a.result_summary}</p>
        </section>
      )}
      <h3>结果记录</h3>
      {a.results.length === 0 && (
        <p className="muted">尚未关联结果记录；行动可以仅用一句说明结项。</p>
      )}
      {a.results.map((r) => (
        <details className="evidence-card" key={r.record_id}>
          <summary>
            {r.title} · v{r.version}
          </summary>
          {r.snapshot && (
            <>
              <SnapshotView value={r.snapshot} />
              <Link to={"/records/" + r.record_id}>查看当前记录</Link>
            </>
          )}
        </details>
      ))}
      <ErrorNotice error={error} />
      <div className="inline-actions">
        {!a.deleted_at && (
          <>
            <button disabled={a.archived} onClick={() => setEditing(true)}>
              编辑行动
            </button>
            {a.status === "completed" || a.status === "cancelled" ? (
              <button disabled={a.archived} onClick={() => setReopen(true)}>
                重新开启
              </button>
            ) : (
              <button
                className="primary"
                disabled={a.archived}
                onClick={() => setComplete(true)}
              >
                完成行动
              </button>
            )}
            <Link to={"/next?tab=reflections&new=attempt&action=" + id}>
              复盘这次行动
            </Link>
          </>
        )}
        <button disabled={a.archived} onClick={remove}>
          {a.deleted_at ? "恢复行动" : "删除行动"}
        </button>
        <button onClick={() => setHistory(!history)}>修改历史</button>
      </div>
      {history && <HistoryPanel path={"/actions/" + id} />}{" "}
      {editing && (
        <ActionEditor
          initial={a}
          projects={projects}
          onClose={() => setEditing(false)}
        />
      )}{" "}
      {complete && (
        <CompleteDialog
          action={a}
          projects={projects}
          onClose={() => setComplete(false)}
        />
      )}{" "}
      {reopen && <ReopenDialog action={a} onClose={() => setReopen(false)} />}
    </article>
  );
}
