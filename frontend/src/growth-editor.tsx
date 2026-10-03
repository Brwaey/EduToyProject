import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState, type FormEvent } from "react";
import { api, json, type Project } from "./api";
import { Dialog, ErrorNotice, Options, useDirtyGuard } from "./common";
import { ObjectPicker, ProjectField } from "./m2-shared";
import { requestIdentity } from "./m2";
import {
  bases,
  contributionTypes,
  evidencePick,
  growthKinds,
  growthLabels,
  growthPath,
  localDate,
  modes,
  type AbilityTag,
  type EvidencePick,
  type GrowthKind,
  type GrowthObject,
} from "./growth";
import { MaterialContent } from "./growth-material";
import { GrowthEvidencePicker } from "./growth-shared";

export type GrowthSeed = {
  title?: string;
  project_id?: string | null;
  question_id?: string | null;
  question_title?: string | null;
  evidence?: EvidencePick[];
};
export function GrowthEditor({
  kind,
  initial,
  seed,
  projects,
  onClose,
}: {
  kind: GrowthKind;
  initial?: GrowthObject;
  seed?: GrowthSeed;
  projects: Project[];
  onClose: () => void;
}) {
  const client = useQueryClient(),
    identity = useRef({ signature: "", id: crypto.randomUUID() });
  const [title, setTitle] = useState(initial?.title || seed?.title || ""),
    [occurred, setOccurred] = useState(initial?.occurred_on || localDate()),
    [project, setProject] = useState(
      initial?.project_id || seed?.project_id || "",
    ),
    [question, setQuestion] = useState(
      initial?.question_id || seed?.question_id || "",
    ),
    [questionTitle, setQuestionTitle] = useState(
      initial?.question_title || seed?.question_title || "",
    ),
    [picking, setPicking] = useState(false),
    [type, setType] = useState(initial?.contribution_type || "choice"),
    [details, setDetails] = useState<Record<string, string>>(
      (initial?.details as Record<string, string>) || {},
    ),
    [tags, setTags] = useState<string[]>(
      (initial?.tags || []).map((t) => String(t.id)),
    ),
    [evidence, setEvidence] = useState<EvidencePick[]>(
      initial?.evidence.map(evidencePick) || seed?.evidence || [],
    ),
    [confirmed, setConfirmed] = useState(false),
    [dirty, setDirty] = useState(false),
    [version, setVersion] = useState(initial?.version),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  useDirtyGuard(dirty);
  const [comparison, setComparison] = useState<GrowthObject | null>(null);
  const tagQuery = useQuery({
    queryKey: ["growth", "tags", "editor"],
    queryFn: () =>
      api<AbilityTag[]>("/ability-tags?archived=true&include_archived=true"),
    enabled: kind === "ability_instance",
  });
  function change(fn: () => void) {
    fn();
    setDirty(true);
    if (kind === "contribution") setConfirmed(false);
  }
  function close() {
    if (!dirty || window.confirm("还有未保存的修改，确定关闭吗？")) onClose();
  }
  async function submit(e: FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const payload = {
        title,
        occurred_on: occurred,
        project_id: project || null,
        question_id: question || null,
        evidence,
        ...(kind === "contribution"
          ? { contribution_type: type, details, confirmed }
          : {
              kind,
              tag_ids: kind === "ability_instance" ? tags : [],
              details: {
                ...details,
                kind,
                ...(kind === "ability_instance"
                  ? {
                      basis_type: details.basis_type || "self_report",
                      completion_mode: details.completion_mode || "unspecified",
                    }
                  : {
                      before: details.before || "",
                      after: details.after || "",
                    }),
              },
            }),
      };
      await api(
        growthPath(kind) + (initial ? "/" + initial.id : ""),
        json(
          initial ? "PATCH" : "POST",
          initial
            ? { ...payload, expected_version: version }
            : { ...payload, request_id: requestIdentity(identity, payload) },
        ),
      );
      setDirty(false);
      await client.invalidateQueries({ queryKey: ["growth"] });
      await client.invalidateQueries({ queryKey: ["m2"] });
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const keys =
    kind === "contribution"
      ? [
          "personal_role",
          "reason",
          "ai_help",
          "others_help",
          "impact",
          "next_steps",
        ]
      : kind === "ability_instance"
        ? ["situation", "attempts", "learned", "difficulties", "next_steps"]
        : ["before", "after", "trigger", "uncertainty", "next_steps"];
  return (
    <Dialog
      title={(initial ? "编辑" : "记录") + growthKinds[kind]}
      onClose={close}
    >
      <form onSubmit={submit} data-dirty={dirty}>
        <label>
          {kind === "contribution" ? "我做了什么" : "一句话主题"}
          <input
            required
            maxLength={200}
            value={title}
            onChange={(e) => change(() => setTitle(e.target.value))}
          />
        </label>
        <div className="form-grid">
          <label>
            发生日期
            <input
              type="date"
              required
              value={occurred}
              onChange={(e) => change(() => setOccurred(e.target.value))}
            />
          </label>
          <ProjectField
            projects={projects}
            value={project}
            onChange={(v) => change(() => setProject(v))}
          />
        </div>
        {kind === "contribution" && (
          <label>
            贡献类型
            <select
              value={type}
              onChange={(e) => change(() => setType(e.target.value))}
            >
              <Options values={contributionTypes} />
            </select>
          </label>
        )}
        <div className="inline-actions">
          <span>关联问题：{questionTitle || "未选择"}</span>
          <button type="button" onClick={() => setPicking(!picking)}>
            选择问题
          </button>
          {question && (
            <button
              type="button"
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
                if (!initial && !project) setProject(n.project_id || "");
              });
              setPicking(false);
            }}
          />
        )}
        {kind === "ability_instance" && (
          <>
            <fieldset>
              <legend>能力标签（至少一个）</legend>
              <ErrorNotice error={tagQuery.error} />
              {tagQuery.data?.map((t) => (
                <label className="check-row" key={t.id}>
                  <input
                    type="checkbox"
                    checked={tags.includes(t.id)}
                    disabled={t.archived && !tags.includes(t.id)}
                    onChange={(e) =>
                      change(() =>
                        setTags(
                          e.target.checked
                            ? [...tags, t.id]
                            : tags.filter((id) => id !== t.id),
                        ),
                      )
                    }
                  />
                  {t.name}
                  {t.archived ? "（已归档）" : ""}
                </label>
              ))}
              {tagQuery.data?.length === 0 && (
                <p>请先在能力档案添加一个标签，再记录实例。</p>
              )}
            </fieldset>
            <div className="form-grid">
              <label>
                完成方式
                <select
                  value={details.completion_mode || "unspecified"}
                  onChange={(e) =>
                    change(() =>
                      setDetails({
                        ...details,
                        completion_mode: e.target.value,
                      }),
                    )
                  }
                >
                  <Options values={modes} />
                </select>
              </label>
              <label>
                依据类型
                <select
                  value={details.basis_type || "self_report"}
                  onChange={(e) =>
                    change(() =>
                      setDetails({ ...details, basis_type: e.target.value }),
                    )
                  }
                >
                  <Options values={bases} />
                </select>
              </label>
            </div>
          </>
        )}
        {keys.map((k) => (
          <label key={k}>
            {growthLabels[k]}
            {["before", "after"].includes(k) ? "（必填）" : "（可选）"}
            <textarea
              rows={3}
              maxLength={20000}
              required={["before", "after"].includes(k)}
              value={details[k] || ""}
              onChange={(e) =>
                change(() => setDetails({ ...details, [k]: e.target.value }))
              }
            />
          </label>
        ))}
        <GrowthEvidencePicker
          values={evidence}
          existing={initial?.evidence}
          understanding={kind === "understanding_change"}
          allowContributions={kind !== "contribution"}
          onChange={(v) => change(() => setEvidence(v))}
        />
        {kind === "contribution" && (
          <label className="check-row">
            <input
              type="checkbox"
              required
              checked={confirmed}
              onChange={(e) => {
                setConfirmed(e.target.checked);
                setDirty(true);
              }}
            />
            以上本人参与的描述由我确认
          </label>
        )}
        <ErrorNotice error={error} />
        {initial && (
          <button
            type="button"
            onClick={async () => {
              try {
                const current = await api<GrowthObject>(
                  growthPath(kind) + "/" + initial.id,
                );
                setComparison(current);
                setConfirmed(false);
                setError(null);
              } catch (e) {
                setError(e);
              }
            }}
          >
            冲突后重新载入版本（保留输入）
          </button>
        )}
        {comparison && (
          <section className="notice">
            <h3>当前服务器版本 v{comparison.version}</h3>
            <p>
              你的输入仍在表单中。请核对最新内容后确认；保存会使用表单中的内容。
            </p>
            <MaterialContent
              value={comparison as unknown as Record<string, unknown>}
            />
            <p>
              发生日期：{comparison.occurred_on}；项目：
              {projects.find((p) => p.id === comparison.project_id)?.name ||
                "未归类"}
              ；问题：{comparison.question_title || "未选择"}
            </p>
            <button
              type="button"
              onClick={() => {
                setVersion(comparison.version);
                setComparison(null);
                setConfirmed(false);
              }}
            >
              已对照最新内容，使用我的表单继续编辑
            </button>
          </section>
        )}
        <div className="inline-actions">
          <button
            type="submit"
            className="primary"
            disabled={
              busy || !!comparison || (kind === "contribution" && !confirmed)
            }
          >
            保存{growthKinds[kind]}
          </button>
          <button type="button" onClick={close}>
            取消
          </button>
        </div>
      </form>
    </Dialog>
  );
}
