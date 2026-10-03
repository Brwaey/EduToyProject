import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, json, fieldLabels, type Project } from "./api";
import type { components } from "./api.generated";
import type { AIConfig, AIPreview, AISelection, AITask } from "./ai";
import { ErrorNotice, Loading, Options, useDirtyGuard } from "./common";
import { Pagination } from "./m2-shared";
import { growthLabels } from "./growth";

type Detail = components["schemas"]["AIMaterialDetail"];
type MaterialPage = components["schemas"]["AIMaterialPage"];
type Choice = { detail: Detail; selection: AISelection };
export const materialKinds = {
  record: "科研记录",
  research_item: "问题／发现／方向",
  action: "行动",
  reflection: "复盘",
  contribution: "贡献",
  growth_entry: "成长条目",
};
export const reflectionLabels: Record<string, string> = {
  progress: "本周推进",
  understanding: "认识变化",
  blockers: "受阻事项",
  next_steps: "下一步选择",
};
const fieldNames: Record<string, string> = {
  ...fieldLabels,
  ...growthLabels,
  ...reflectionLabels,
  title: "标题",
  body: "正文",
  description: "说明",
  research_goal: "研究目标",
  learning_goal: "学习目标",
  completion_criteria: "完成标准",
  effort: "预计投入",
  result_summary: "结项说明",
  motivation: "问题缘由",
  hypothesis: "假设",
  conditions: "适用条件",
  rationale: "方向缘由",
  question: "研究问题",
  supporting: "支持依据",
  opposing: "反对依据",
  resources: "资源",
  minimal_action: "最小验证行动",
  uncertainty: "不确定性",
};
const label = (path: string) =>
  fieldNames[path.replace(/^(fields|details)\./, "")] || path;

export default function AIPlanningCreate({
  kind,
}: {
  kind: "action_candidates" | "reflection_draft";
}) {
  const [params] = useSearchParams(),
    navigate = useNavigate();
  const target = kind === "reflection_draft" ? params.get("object") || "" : "";
  const [choices, setChoices] = useState<Choice[]>([]),
    [goal, setGoal] = useState(""),
    [constraints, setConstraints] = useState(""),
    [query, setQuery] = useState(""),
    [filter, setFilter] = useState(""),
    [project, setProject] = useState(""),
    [page, setPage] = useState(1),
    [preview, setPreview] = useState<AIPreview | null>(null),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [done, setDone] = useState("");
  const loaded = useRef(""),
    request = useRef({ digest: "", id: crypto.randomUUID() });
  const dirty = !!(choices.length || goal || constraints) && !done;
  useDirtyGuard(dirty);
  useEffect(() => {
    if (done) navigate("/records/ai?task=" + done);
  }, [done, navigate]);
  const config = useQuery({
    queryKey: ["ai", "config"],
    queryFn: () => api<AIConfig>("/ai/config"),
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
  });
  const search = new URLSearchParams({
    task_kind: kind,
    q: query,
    page: String(page),
  });
  if (filter) search.set("kind", filter);
  if (project) search.set("project_id", project);
  const list = useQuery({
    queryKey: ["ai", "materials", search.toString()],
    queryFn: () => api<MaterialPage>("/ai/materials?" + search),
    enabled: kind === "action_candidates",
  });
  async function pick(k: string, id: string, revision?: string) {
    if (choices.some((c) => c.selection.id === id)) return;
    if (choices.length >= 20) {
      setError(new Error("最多选择 20 个对象，请先移除一项。"));
      return;
    }
    setBusy(true);
    setError(null);
    setPreview(null);
    try {
      const d = await api<Detail>(
        `/ai/materials/${k}/${id}` +
          (revision ? "?revision_id=" + revision : ""),
      );
      if (kind === "reflection_draft" && id === target)
        d.options = d.options.filter(
          (o) =>
            o.pick.field_path?.startsWith("details.") &&
            reflectionLabels[o.pick.field_path.slice(8)],
        );
      setChoices((old) =>
        old.some((c) => c.selection.id === id)
          ? old
          : [
              ...old,
              {
                detail: d,
                selection: {
                  kind: k as AISelection["kind"],
                  id,
                  version: d.version,
                  current_version: d.current_version,
                  revision_id: d.revision_id,
                  materials: [],
                },
              },
            ],
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    const id = params.get("object"),
      type = params.get("object_kind");
    const key = kind + ":" + id;
    if (id && type && loaded.current !== key) {
      loaded.current = key;
      void pick(type, id);
    }
  }, [params, kind]);
  const payload = {
    kind,
    objects: choices.map((c) => c.selection),
    parameters: { goal, constraints },
    target_reflection_id: target || null,
  };
  async function submit(start: boolean) {
    setBusy(true);
    setError(null);
    try {
      if (!start) {
        setPreview(await api<AIPreview>("/ai/preview", json("POST", payload)));
        return;
      }
      const body = { ...payload, config_version: config.data!.version };
      const digest = JSON.stringify(body);
      if (request.current.digest !== digest)
        request.current = { digest, id: crypto.randomUUID() };
      const t = await api<AITask>(
        "/ai/tasks",
        json("POST", { ...body, request_id: request.current.id }),
      );
      setDone(t.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const related =
    choices.find((c) => c.detail.id === target)?.detail.related || [];
  async function reload(c: Choice) {
    setBusy(true);
    setError(null);
    setPreview(null);
    try {
      const d = await api<Detail>(
        `/ai/materials/${c.selection.kind}/${c.selection.id}` +
          (c.selection.id === target
            ? ""
            : "?revision_id=" + c.detail.revision_id),
      );
      if (d.id === target)
        d.options = d.options.filter(
          (o) =>
            o.pick.field_path?.startsWith("details.") &&
            reflectionLabels[o.pick.field_path.slice(8)],
        );
      setChoices((old) =>
        old.map((v) =>
          v.detail.id === d.id
            ? {
                detail: d,
                selection: {
                  ...v.selection,
                  version: d.version,
                  current_version: d.current_version,
                  revision_id: d.revision_id,
                },
              }
            : v,
        ),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="ai-page" data-dirty={dirty}>
      <header className="page-header">
        <div>
          <div className="eyebrow">AI · 下一次探索</div>
          <h1>
            {kind === "action_candidates" ? "AI 建议行动" : "AI 辅助整理周复盘"}
          </h1>
          <p>勾选实际发送的字段。关联证据、历史和其他对象不会自动发送。</p>
        </div>
        <Link to="/records/ai">AI 收件箱</Link>
      </header>
      <ErrorNotice error={config.error || projects.error} />
      {!config.data?.key_available && (
        <p className="notice">
          请先<Link to="/settings/model">配置模型接口</Link>。可以先选择材料。
        </p>
      )}
      {kind === "action_candidates" ? (
        <>
          <div className="ai-card">
            <label>
              这次希望解决什么
              <textarea
                aria-label="这次希望解决什么"
                maxLength={4000}
                value={goal}
                onChange={(e) => {
                  setGoal(e.target.value);
                  setPreview(null);
                }}
              />
            </label>
            <label>
              时间、资源与限制（可选）
              <textarea
                value={constraints}
                maxLength={4000}
                onChange={(e) => {
                  setConstraints(e.target.value);
                  setPreview(null);
                }}
              />
            </label>
          </div>
          <div className="ai-card">
            <h2>添加分析对象</h2>
            <div className="filters">
              <input
                aria-label="搜索分析对象"
                placeholder="搜索标题"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(1);
                }}
              />
              <select
                aria-label="分析对象类型"
                value={filter}
                onChange={(e) => {
                  setFilter(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">所有类型</option>
                <Options values={materialKinds} />
              </select>
              <select
                aria-label="分析项目"
                value={project}
                onChange={(e) => {
                  setProject(e.target.value);
                  setPage(1);
                }}
              >
                <option value="">全部项目</option>
                {projects.data
                  ?.filter((p) => !p.archived)
                  .map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
              </select>
            </div>
            <ErrorNotice error={list.error} />
            {list.isPending && <Loading />}
            {list.data?.items.map((o) => (
              <button
                key={String(o.id)}
                disabled={busy || choices.some((c) => c.selection.id === o.id)}
                onClick={() => pick(String(o.kind), String(o.id))}
              >
                {String(o.title)} ·{" "}
                {materialKinds[o.kind as keyof typeof materialKinds]}
              </button>
            ))}
            {list.data?.total === 0 && <p>没有可用材料，请先保存科研内容。</p>}
            <Pagination
              page={page}
              total={list.data?.total || 0}
              onChange={setPage}
            />
          </div>
        </>
      ) : (
        <div className="ai-card">
          <p>
            请先保存自己的周判断，再选择已关联材料的固定版本。需要添加新材料时，先回到复盘编辑并保存。
          </p>
          {target ? (
            <Link to={"/next?tab=reflections&item=" + target}>
              返回目标复盘
            </Link>
          ) : (
            <p>请从已保存的周期复盘详情进入。</p>
          )}
          <h2>可选参考材料</h2>
          {related.length === 0 && (
            <p>该复盘尚未关联其他材料，可以只整理你自己的文字。</p>
          )}
          {related.map((r) => (
            <button
              key={String(r.revision_id)}
              disabled={
                busy ||
                !!r.deleted ||
                !!r.archived ||
                choices.some((c) => c.selection.id === r.id)
              }
              onClick={() =>
                pick(String(r.kind), String(r.id), String(r.revision_id))
              }
            >
              选择 {String(r.title)} · 固定 v{String(r.version)}
              {r.deleted ? "（已删除）" : r.archived ? "（已归档）" : ""}
            </button>
          ))}
        </div>
      )}
      {choices.map((c, index) => (
        <div className="ai-card" key={c.detail.id}>
          <div className="ai-row">
            <h2>{c.detail.title}</h2>
            <span>
              材料 v{c.detail.version} · 当前 v{c.detail.current_version}
            </span>
            <button disabled={busy} onClick={() => reload(c)}>
              重新核对当前版本
            </button>
            {c.detail.id !== target && (
              <button
                onClick={() => {
                  setChoices(choices.filter((_, i) => i !== index));
                  setPreview(null);
                }}
              >
                移除对象
              </button>
            )}
          </div>
          {c.detail.evidence_label && (
            <p className="notice">{c.detail.evidence_label}</p>
          )}
          {!c.detail.options.length && (
            <p className="notice">没有可发送的文字，请先编辑并保存。</p>
          )}
          {c.detail.options.map((o, i) => {
            const selected = c.selection.materials.find(
              (p) =>
                p.field_path === o.pick.field_path &&
                p.source_version_id === o.pick.source_version_id,
            );
            function update(materials: AISelection["materials"]) {
              setChoices((old) =>
                old.map((v, j) =>
                  j === index
                    ? { ...v, selection: { ...v.selection, materials } }
                    : v,
                ),
              );
              setPreview(null);
            }
            return (
              <div className="ai-material" key={i}>
                <label className="ai-check">
                  <input
                    type="checkbox"
                    checked={!!selected}
                    onChange={(e) =>
                      update(
                        e.target.checked
                          ? [...c.selection.materials, o.pick]
                          : c.selection.materials.filter((p) => p !== selected),
                      )
                    }
                  />
                  {label(o.label)} · {Array.from(o.text).length} 字符
                </label>
                <details>
                  <summary>查看文字／选择片段</summary>
                  <pre>{o.text}</pre>
                  {selected && (
                    <div className="form-grid">
                      {(["start", "end"] as const).map((k) => (
                        <label key={k}>
                          {k === "start"
                            ? "起始位置（0 起，留空为全文）"
                            : "结束位置（不含）"}
                          <input
                            type="number"
                            min="0"
                            value={selected[k] ?? ""}
                            onChange={(e) =>
                              update(
                                c.selection.materials.map((p) =>
                                  p === selected
                                    ? {
                                        ...p,
                                        [k]:
                                          e.target.value === ""
                                            ? null
                                            : Number(e.target.value),
                                      }
                                    : p,
                                ),
                              )
                            }
                          />
                        </label>
                      ))}
                    </div>
                  )}
                </details>
              </div>
            );
          })}
        </div>
      ))}
      <ErrorNotice error={error} />
      <button
        disabled={
          busy ||
          !choices.length ||
          (kind === "action_candidates" && !goal.trim())
        }
        onClick={() => submit(false)}
      >
        预览发送内容
      </button>
      {preview && (
        <div className="ai-card">
          <h2>发送前预览</h2>
          <p className="ai-wrap">
            模型：{config.data?.model} · {config.data?.endpoint}
          </p>
          <p>
            {preview.objects.length} 个对象 · {preview.characters}／32,000 字符
          </p>
          {kind === "action_candidates" && (
            <pre>
              {goal}
              {constraints ? "\n限制：" + constraints : ""}
            </pre>
          )}
          {preview.materials.map((m) => (
            <details key={m.key}>
              <summary>
                {m.key} · {label(m.field_path)}
              </summary>
              <pre>{m.text}</pre>
            </details>
          ))}
          <button
            className="primary"
            disabled={busy || !config.data?.key_available}
            onClick={() => submit(true)}
          >
            {kind === "action_candidates" ? "生成行动建议" : "开始辅助整理"}
          </button>
        </div>
      )}
    </section>
  );
}
