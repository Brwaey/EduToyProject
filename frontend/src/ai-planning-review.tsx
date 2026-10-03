import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { api, json, time, type Project } from "./api";
import type { components } from "./api.generated";
import type { AISuggestion } from "./ai";
import { suggestionStates } from "./ai";
import { ErrorNotice, useDirtyGuard } from "./common";
import { ProjectField } from "./m2-shared";
import { reflectionLabels } from "./ai-planning-create";

type ActionDraft = components["schemas"]["ActionAcceptance"];
type FieldEdit = components["schemas"]["ReflectionFieldAcceptance"];
export default function AIPlanningReview({
  s,
  refresh,
  materials,
}: {
  s: AISuggestion;
  refresh: () => unknown;
  materials: ReactNode;
}) {
  const candidate = s.planning && "title" in s.planning ? s.planning : null;
  const reflection = s.planning && "fields" in s.planning ? s.planning : null;
  const client = useQueryClient();
  const target = s.task.inputs.objects.find(
    (o) => o.id === s.task.target_reflection_id,
  );
  const current = (target?.current?.details || {}) as Record<string, string>;
  const [action, setAction] = useState<ActionDraft>(() => ({
    title: candidate?.title || "",
    project_id: s.task.inputs.objects[0]?.project_id,
    direction_id: null,
    origin_reflection_id: null,
    details: {
      research_goal: candidate?.research_goal || "",
      learning_goal: candidate?.learning_goal || "",
      completion_criteria: candidate?.completion_criteria || "",
      effort: candidate?.effort || "",
      expected_date: null,
      pause_reason: "",
      restart_condition: "",
    },
  }));
  const [texts, setTexts] = useState<Record<string, string>>(() =>
    Object.fromEntries(
      Object.entries(reflection?.fields || {}).map(([k, v]) => [k, v.value]),
    ),
  );
  const [modes, setModes] = useState<
    Record<string, "omit" | "append" | "replace">
  >(() =>
    Object.fromEntries(
      Object.entries(reflection?.fields || {}).map(([k, v]) => [
        k,
        current[k] || !v.value ? "omit" : "replace",
      ]),
    ),
  );
  const [reviewed, setReviewed] = useState(false),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  const versions = JSON.stringify(
    s.task.inputs.objects.map((o) => o.current_version),
  );
  useEffect(() => setReviewed(false), [versions]);
  useDirtyGuard(dirty);
  const blocked =
    s.task.unavailable || s.task.inputs.objects.some((o) => o.archived);
  function change(fn: () => void) {
    fn();
    setDirty(true);
  }
  function finalText(k: string) {
    const prior = current[k] || "",
      text = texts[k] || "";
    return modes[k] === "append" && prior && text
      ? prior + "\n\n" + text
      : modes[k] === "append"
        ? prior || text
        : text;
  }
  async function decide(accept: boolean) {
    setBusy(true);
    setError(null);
    try {
      const fields: Record<string, FieldEdit> = {};
      for (const [k, mode] of Object.entries(modes))
        if (mode !== "omit")
          fields[k] = { mode, text: texts[k], final_text: finalText(k) };
      const body: components["schemas"]["AcceptInput"] = {
        expected_version: s.version,
        reviewed,
        current_versions: Object.fromEntries(
          s.task.inputs.objects.map((o) => [o.key, o.current_version]),
        ),
        ...(s.kind === "action_candidates"
          ? { action }
          : {
              reflection: { expected_version: target!.current_version, fields },
            }),
      };
      await api(
        "/ai/suggestions/" + s.id + (accept ? "/accept" : "/reject"),
        json("POST", accept ? body : { expected_version: s.version }),
      );
      setDirty(false);
      await Promise.all([
        client.invalidateQueries({ queryKey: ["ai"] }),
        client.invalidateQueries({ queryKey: ["m2"] }),
      ]);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const directions = s.task.inputs.objects.filter(
    (o) =>
      o.kind === "research_item" &&
      (o.current?.details as Record<string, unknown> | undefined)?.kind ===
        "direction",
  );
  return (
    <article className="ai-card" data-dirty={dirty}>
      <div className="ai-row">
        <h2>{candidate ? "核对行动建议" : "核对周复盘草稿"}</h2>
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
        {s.task.model} · {time(s.created_at)}
      </p>
      {materials}
      {blocked && (
        <p className="notice">来源或目标已删除或归档，请恢复后采纳。</p>
      )}
      {s.status === "pending" && !blocked ? (
        <>
          {candidate && (
            <>
              <p className="notice">
                以下是未来建议，采纳后只创建待开始行动。资源与投入属于估计。
              </p>
              <label>
                行动标题
                <input
                  aria-label="建议行动标题"
                  maxLength={200}
                  value={action.title}
                  onChange={(e) =>
                    change(() =>
                      setAction({ ...action, title: e.target.value }),
                    )
                  }
                />
              </label>
              <ProjectField
                value={action.project_id || ""}
                projects={projects.data || []}
                onChange={(v) =>
                  change(() => setAction({ ...action, project_id: v || null }))
                }
              />
              <div className="form-grid">
                <label>
                  关联方向
                  <select
                    value={action.direction_id || ""}
                    onChange={(e) =>
                      change(() =>
                        setAction({
                          ...action,
                          direction_id: e.target.value || null,
                        }),
                      )
                    }
                  >
                    <option value="">不关联</option>
                    {directions.map((o) => (
                      <option value={o.id} key={o.id}>
                        {o.title}
                      </option>
                    ))}
                  </select>
                </label>
                <label>
                  来源复盘
                  <select
                    value={action.origin_reflection_id || ""}
                    onChange={(e) =>
                      change(() =>
                        setAction({
                          ...action,
                          origin_reflection_id: e.target.value || null,
                        }),
                      )
                    }
                  >
                    <option value="">不关联</option>
                    {s.task.inputs.objects
                      .filter((o) => o.kind === "reflection")
                      .map((o) => (
                        <option value={o.id} key={o.id}>
                          {o.title}
                        </option>
                      ))}
                  </select>
                </label>
              </div>
              {(
                [
                  "research_goal",
                  "learning_goal",
                  "completion_criteria",
                  "effort",
                ] as const
              ).map((k) => (
                <label key={k}>
                  {
                    {
                      research_goal: "研究目标",
                      learning_goal: "学习目标",
                      completion_criteria: "建议做法与完成标准",
                      effort: "资源／预计投入（估计）",
                    }[k]
                  }
                  <textarea
                    value={action.details?.[k] || ""}
                    maxLength={20000}
                    onChange={(e) =>
                      change(() =>
                        setAction({
                          ...action,
                          details: { ...action.details, [k]: e.target.value },
                        }),
                      )
                    }
                  />
                </label>
              ))}
              <label>
                预计日期（由你安排，可不填）
                <input
                  type="date"
                  value={action.details?.expected_date || ""}
                  onChange={(e) =>
                    change(() =>
                      setAction({
                        ...action,
                        details: {
                          ...action.details,
                          expected_date: e.target.value || null,
                        },
                      }),
                    )
                  }
                />
              </label>
              <h3>提出理由</h3>
              <p>{candidate.reason}</p>
              <h3>风险与不确定性</h3>
              <p>{candidate.uncertainty || "未补充"}</p>
              {candidate.citations.map((c, i) => (
                <blockquote key={i}>
                  {c.material}：{c.quote}
                </blockquote>
              ))}
            </>
          )}
          {reflection && (
            <>
              <p>只写入明确选择的字段；部分采纳后该建议结束。追加预览如下。</p>
              {Object.entries(reflection.fields).map(([k, f]) => (
                <section className="ai-field" key={k}>
                  <h3>{reflectionLabels[k]}</h3>
                  <label>
                    处理方式
                    <select
                      aria-label={reflectionLabels[k] + "处理方式"}
                      value={modes[k]}
                      onChange={(e) =>
                        change(() =>
                          setModes({
                            ...modes,
                            [k]: e.target.value as (typeof modes)[string],
                          }),
                        )
                      }
                    >
                      <option value="omit">不采用</option>
                      <option value="append">追加</option>
                      <option value="replace">替换</option>
                    </select>
                  </label>
                  <div className="ai-compare">
                    <div>
                      <small>当前文字</small>
                      <pre>{current[k] || "（空）"}</pre>
                    </div>
                    <label>
                      AI 草稿／你的修改
                      <textarea
                        aria-label={"建议" + reflectionLabels[k]}
                        maxLength={20000}
                        value={texts[k]}
                        onChange={(e) =>
                          change(() =>
                            setTexts({ ...texts, [k]: e.target.value }),
                          )
                        }
                      />
                    </label>
                  </div>
                  {(f.citations || []).map((c, i) => (
                    <blockquote key={i}>
                      {c.material}：{c.quote}
                    </blockquote>
                  ))}
                  {modes[k] !== "omit" && (
                    <div>
                      <h4>保存后的完整文本</h4>
                      <pre>{finalText(k)}</pre>
                    </div>
                  )}
                </section>
              ))}
              {reflection.questions?.map((q, i) => (
                <p key={i}>待补充：{q}</p>
              ))}
            </>
          )}
          {s.task.needs_review && (
            <label className="notice ai-check">
              <input
                type="checkbox"
                checked={reviewed}
                onChange={(e) => change(() => setReviewed(e.target.checked))}
              />
              我已对照旧材料与当前文字，确认旧依据仍适用
            </label>
          )}
          <p className="ai-muted">
            引用可定位不代表已证实；你的补充与修改会单独保留。
          </p>
          <div className="inline-actions">
            <button
              className="primary"
              disabled={
                busy ||
                (s.task.needs_review && !reviewed) ||
                (!!reflection &&
                  Object.values(modes).every((m) => m === "omit"))
              }
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
        s.status !== "pending" && (
          <details>
            <summary>查看处理内容</summary>
            <pre>{JSON.stringify(s.accepted || s.original, null, 2)}</pre>
          </details>
        )
      )}
      {s.action_id && (
        <Link to={"/next?tab=actions&item=" + s.action_id}>查看正式行动</Link>
      )}
      {s.reflection_id && (
        <div className="inline-actions">
          <Link to={"/next?tab=reflections&item=" + s.reflection_id}>
            查看正式复盘
          </Link>
          <Link
            to={
              "/records/ai/new?kind=action_candidates&object_kind=reflection&object=" +
              s.reflection_id
            }
          >
            据此建议行动
          </Link>
        </div>
      )}
      <ErrorNotice error={error || projects.error} />
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
