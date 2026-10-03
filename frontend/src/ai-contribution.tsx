import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, json, time, type Project } from "./api";
import { ErrorNotice, Options, useDirtyGuard } from "./common";
import { ObjectPicker, ProjectField } from "./m2-shared";
import {
  contributionTypes,
  evidencePick,
  growthLabels,
  localDate,
  type EvidencePick,
} from "./growth";
import type { AISuggestion, Citation } from "./ai";
import { suggestionStates } from "./ai";

type Candidate = {
  contribution_type: keyof typeof contributionTypes;
  fields: Record<string, { value: string; citations: Citation[] }>;
  uncertainty: string;
  questions: string[];
  evidence: EvidencePick[];
};
export default function AIContributionReview({
  s,
  refresh,
  materials,
}: {
  s: AISuggestion;
  refresh: () => unknown;
  materials: React.ReactNode;
}) {
  const original = s.original as Candidate | null,
    client = useQueryClient();
  const [fields, setFields] = useState<Record<string, string>>(() =>
      Object.fromEntries(
        Object.entries(original?.fields || {}).map(([k, v]) => [k, v.value]),
      ),
    ),
    [type, setType] = useState(original?.contribution_type || "choice"),
    [occurred, setOccurred] = useState(localDate()),
    [project, setProject] = useState(() => {
      const ids = new Set(s.task.inputs.objects.map((o) => o.project_id));
      return ids.size === 1 ? s.task.inputs.objects[0]?.project_id || "" : "";
    }),
    [question, setQuestion] = useState(""),
    [questionTitle, setQuestionTitle] = useState(""),
    [picking, setPicking] = useState(false),
    [selected, setSelected] = useState<number[]>(
      () => original?.evidence.map((_, i) => i) || [],
    ),
    [confirmed, setConfirmed] = useState(false),
    [reviewed, setReviewed] = useState(false),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  const fingerprint = JSON.stringify(
    s.task.inputs.objects.map((o) => o.current_version),
  );
  useEffect(() => {
    setReviewed(false);
    setConfirmed(false);
  }, [fingerprint]);
  useDirtyGuard(dirty);
  const blocked =
      s.task.unavailable || s.task.inputs.objects.some((o) => o.archived),
    keys = [
      "title",
      "personal_role",
      "reason",
      "ai_help",
      "others_help",
      "impact",
    ];
  function change(fn: () => void) {
    fn();
    setConfirmed(false);
    setDirty(true);
  }
  async function decide(accept: boolean) {
    setBusy(true);
    setError(null);
    try {
      const details = Object.fromEntries(
        keys.filter((k) => k !== "title").map((k) => [k, fields[k] || ""]),
      );
      await api(
        "/ai/suggestions/" + s.id + (accept ? "/accept" : "/reject"),
        json(
          "POST",
          accept
            ? {
                expected_version: s.version,
                current_versions: Object.fromEntries(
                  s.task.inputs.objects.map((o) => [o.key, o.current_version]),
                ),
                reviewed,
                contribution: {
                  title: fields.title || "",
                  contribution_type: type,
                  occurred_on: occurred,
                  project_id: project || null,
                  question_id: question || null,
                  details,
                  evidence: (original?.evidence || [])
                    .filter((_, i) => selected.includes(i))
                    .map(evidencePick),
                  confirmed,
                },
              }
            : { expected_version: s.version },
        ),
      );
      setDirty(false);
      await client.invalidateQueries({ queryKey: ["ai"] });
      await client.invalidateQueries({ queryKey: ["growth"] });
      refresh();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="ai-card ai-review" data-dirty={dirty}>
      <div className="ai-row">
        <h2>核对贡献候选</h2>
        <span>{suggestionStates[s.status]}</span>
        <button
          onClick={() => {
            setReviewed(false);
            setConfirmed(false);
            refresh();
          }}
        >
          重新载入当前版本（保留输入）
        </button>
      </div>
      <p>
        模型：{s.task.model} · {time(s.created_at)}
      </p>
      {materials}
      {blocked ? (
        <p className="notice">所选材料已删除或归档，请恢复后处理。</p>
      ) : s.status === "pending" && original ? (
        <>
          <p className="notice">
            模型不能替你认定本人贡献。请核对自己的参与；你增补或修改的事实会另标为用户补充。
          </p>
          <div className="form-grid">
            <label>
              贡献类型
              <select
                value={type}
                onChange={(e) =>
                  change(() => setType(e.target.value as typeof type))
                }
              >
                <Options values={contributionTypes} />
              </select>
            </label>
            <label>
              发生日期
              <input
                type="date"
                value={occurred}
                required
                onChange={(e) => change(() => setOccurred(e.target.value))}
              />
            </label>
            <ProjectField
              projects={projects.data || []}
              value={project}
              onChange={(v) => change(() => setProject(v))}
            />
          </div>
          <div className="inline-actions">
            <span>关联问题：{questionTitle || "未选择"}</span>
            <button onClick={() => setPicking(!picking)}>选择问题</button>
            {question && (
              <button
                onClick={() =>
                  change(() => {
                    setQuestion("");
                    setQuestionTitle("");
                  })
                }
              >
                移除问题
              </button>
            )}
          </div>
          {picking && (
            <ObjectPicker
              kind="question"
              onPick={(n) => {
                change(() => {
                  setQuestion(n.object_id);
                  setQuestionTitle(n.title);
                });
                setPicking(false);
              }}
            />
          )}
          {keys.map((k) => (
            <div className="ai-field" key={k}>
              <label>
                {k === "title" ? "我做了什么" : growthLabels[k]}
                <textarea
                  rows={3}
                  maxLength={k === "title" ? 200 : 20000}
                  value={fields[k] || ""}
                  onChange={(e) =>
                    change(() => setFields({ ...fields, [k]: e.target.value }))
                  }
                />
              </label>
              {fields[k] !== original.fields[k]?.value && fields[k] && (
                <small>用户补充／修改；原引用不代表已证明该补充。</small>
              )}
              {original.fields[k]?.citations.map((c, i) => (
                <blockquote key={i}>
                  {c.material}：{c.quote}
                </blockquote>
              ))}
            </div>
          ))}
          <p>{original.uncertainty}</p>
          {original.questions.length > 0 && (
            <ul>
              {original.questions.map((q, i) => (
                <li key={i}>{q}</li>
              ))}
            </ul>
          )}
          <h3>保留的固定依据（至少一项）</h3>
          {original.evidence.map((e, i) => (
            <label key={i} className="check-row">
              <input
                type="checkbox"
                checked={selected.includes(i)}
                onChange={(event) =>
                  change(() =>
                    setSelected(
                      event.target.checked
                        ? [...selected, i]
                        : selected.filter((j) => j !== i),
                    ),
                  )
                }
              />
              {e.quote || "已定位原文片段"}
            </label>
          ))}
          {s.task.needs_review && (
            <div className="notice">
              <p>材料已更新，请对照当时内容与当前内容。</p>
              <label className="check-row">
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
          <label className="check-row">
            <input
              type="checkbox"
              checked={confirmed}
              onChange={(e) => {
                setConfirmed(e.target.checked);
                setDirty(true);
              }}
            />
            以上本人参与的描述由我确认
          </label>
          <div className="inline-actions">
            <button
              className="primary"
              disabled={
                busy ||
                !confirmed ||
                !fields.title?.trim() ||
                !occurred ||
                !selected.length ||
                (s.task.needs_review && !reviewed)
              }
              onClick={() => decide(true)}
            >
              采纳为个人贡献
            </button>
            <button disabled={busy} onClick={() => decide(false)}>
              拒绝建议
            </button>
          </div>
        </>
      ) : (
        <>
          <p>该候选已处理，原候选与用户修改分别保留。</p>
          <details>
            <summary>查看处理结果</summary>
            <pre>{JSON.stringify(s.accepted || s.original, null, 2)}</pre>
          </details>
        </>
      )}
      {s.contribution_id && (
        <Link
          to={
            "/growth?tab=contributions&object=contribution&id=" +
            s.contribution_id
          }
        >
          查看正式贡献
        </Link>
      )}
      <ErrorNotice error={error} />
      <ErrorNotice error={projects.error} />
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
