import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { api, json, fieldLabels, type RecordData, type Source } from "./api";
import { ErrorNotice, Loading, useDirtyGuard } from "./common";
import { ObjectPicker } from "./m2-shared";
import type { GraphNodeData, Item } from "./m2";
import {
  type AIConfig,
  type AIKind,
  type AIPick,
  type AIPreview,
  type AISelection,
  type AITask,
} from "./ai";

type Choice = {
  selection: AISelection;
  title: string;
  options: { key: string; label: string; pick: AIPick; text: string }[];
};
export default function AICreate() {
  const [params] = useSearchParams(),
    navigate = useNavigate();
  const kind: AIKind =
    params.get("kind") === "contribution_candidates"
      ? "contribution_candidates"
      : params.get("kind") === "relation_suggestions"
        ? "relation_suggestions"
        : "record_draft";
  const [choices, setChoices] = useState<Choice[]>([]),
    [preview, setPreview] = useState<AIPreview | null>(null),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [done, setDone] = useState("");
  const ids = useRef({ fingerprint: "", id: crypto.randomUUID() });
  const loaded = useRef("");
  useEffect(() => {
    if (done) navigate("/records/ai?task=" + done);
  }, [done, navigate]);
  useDirtyGuard(choices.length > 0 && !done);
  const config = useQuery({
    queryKey: ["ai", "config"],
    queryFn: () => api<AIConfig>("/ai/config"),
  });
  async function pick(node: Pick<GraphNodeData, "object_kind" | "object_id">) {
    if (choices.some((c) => c.selection.id === node.object_id)) return;
    setBusy(true);
    setError(null);
    setPreview(null);
    try {
      if (kind !== "relation_suggestions" && node.object_kind !== "record")
        return;
      let choice: Choice;
      if (node.object_kind === "record") {
        const [r, sources] = await Promise.all([
          api<RecordData>("/records/" + node.object_id),
          api<Source[]>("/records/" + node.object_id + "/sources"),
        ]);
        const options = [
          {
            key: "title",
            label: "标题",
            pick: { field_path: "title" },
            text: r.title,
          },
          {
            key: "body",
            label: "正文",
            pick: { field_path: "body" },
            text: r.body,
          },
          ...Object.entries(fieldLabels).map(([k, label]) => ({
            key: "fields." + k,
            label,
            pick: { field_path: "fields." + k },
            text: r.fields[k as keyof typeof r.fields],
          })),
          ...sources.map((s) => {
            const v = s.versions.find((v) => v.version === s.current_version)!;
            return {
              key: s.id,
              label: "来源：" + s.name,
              pick: { field_path: "content", source_version_id: v.id },
              text: v.content,
            };
          }),
        ].filter((o) => o.text.trim());
        choice = {
          title: r.title,
          selection: {
            kind: "record",
            id: r.id,
            version: r.version,
            materials: options
              .filter((o) => o.key === "body")
              .map((o) => o.pick),
          },
          options,
        };
      } else {
        const r = await api<Item>("/research-items/" + node.object_id);
        const options = [
          {
            key: "title",
            label: "标题",
            pick: { field_path: "title" },
            text: r.title,
          },
          {
            key: "description",
            label: "说明",
            pick: { field_path: "description" },
            text: r.description,
          },
          ...Object.entries(r.details)
            .filter(([k, v]) => k !== "kind" && typeof v === "string" && v)
            .map(([k, v]) => ({
              key: "details." + k,
              label: k,
              pick: { field_path: "details." + k },
              text: String(v),
            })),
        ].filter((o) => o.text.trim());
        choice = {
          title: r.title,
          selection: {
            kind: "research_item",
            id: r.id,
            version: r.version,
            materials: options.map((o) => o.pick),
          },
          options,
        };
      }
      setChoices((old) =>
        kind === "record_draft" ? [choice] : [...old, choice].slice(0, 20),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    const id = params.get("record");
    if (id && loaded.current !== id) {
      loaded.current = id;
      void pick({ object_kind: "record", object_id: id });
    }
  }, [params]);
  function change(index: number, materials: AIPick[]) {
    setPreview(null);
    setChoices((old) =>
      old.map((c, i) =>
        i === index ? { ...c, selection: { ...c.selection, materials } } : c,
      ),
    );
  }
  async function check() {
    setBusy(true);
    setError(null);
    try {
      setPreview(
        await api<AIPreview>(
          "/ai/preview",
          json("POST", { kind, objects: choices.map((c) => c.selection) }),
        ),
      );
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function start() {
    if (!config.data || !preview) return;
    setBusy(true);
    setError(null);
    const value = {
      kind,
      objects: choices.map((c) => c.selection),
      config_version: config.data.version,
    };
    const fingerprint = JSON.stringify(value);
    if (ids.current.fingerprint !== fingerprint)
      ids.current = { fingerprint, id: crypto.randomUUID() };
    try {
      const t = await api<AITask>(
        "/ai/tasks",
        json("POST", { ...value, request_id: ids.current.id }),
      );
      setDone(t.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="ai-page" data-dirty={choices.length > 0 && !done}>
      <header className="page-header">
        <div>
          <div className="eyebrow">AI · SELECT MATERIALS</div>
          <h1>
            {kind === "record_draft"
              ? "AI 整理探索卡"
              : kind === "contribution_candidates"
                ? "AI 寻找贡献候选"
                : "AI 建议关联"}
          </h1>
          <p>仅发送本次勾选的材料；生成后由你决定是否采纳。</p>
        </div>
        <Link to="/records/ai">返回收件箱</Link>
      </header>
      <ErrorNotice error={config.error} />
      {!config.data?.has_key && (
        <div className="notice">
          请先<Link to="/settings/model">配置模型接口</Link>。材料可先选择。
        </div>
      )}
      <div className="ai-card">
        <ObjectPicker
          kind={kind !== "relation_suggestions" ? "record" : undefined}
          label="选择科研材料"
          onPick={(n) => void pick(n)}
        />
      </div>
      {choices.map((c, index) => (
        <div className="ai-card" key={c.selection.id}>
          <div className="ai-row">
            <h2>{c.title}</h2>
            <span>第 {c.selection.version} 版</span>
            <button
              onClick={() => {
                setChoices(choices.filter((_, i) => i !== index));
                setPreview(null);
              }}
            >
              移除对象
            </button>
          </div>
          {c.options.map((o) => {
            const selected = c.selection.materials.find(
              (p) =>
                p.field_path === o.pick.field_path &&
                p.source_version_id === o.pick.source_version_id,
            );
            return (
              <div className="ai-material" key={o.key}>
                <label className="ai-check">
                  <input
                    type="checkbox"
                    checked={!!selected}
                    onChange={(e) =>
                      change(
                        index,
                        e.target.checked
                          ? [...c.selection.materials, o.pick]
                          : c.selection.materials.filter((p) => p !== selected),
                      )
                    }
                  />
                  {o.label} · {Array.from(o.text).length} 字符
                </label>
                <details>
                  <summary>查看材料与片段范围</summary>
                  <pre>{o.text}</pre>
                  {selected && (
                    <div className="form-grid">
                      <label>
                        起始位置（从 0，留空为全文）
                        <input
                          type="number"
                          min="0"
                          value={selected.start ?? ""}
                          onChange={(e) =>
                            change(
                              index,
                              c.selection.materials.map((p) =>
                                p === selected
                                  ? {
                                      ...p,
                                      start:
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
                      <label>
                        结束位置（不包含）
                        <input
                          type="number"
                          min="1"
                          value={selected.end ?? ""}
                          onChange={(e) =>
                            change(
                              index,
                              c.selection.materials.map((p) =>
                                p === selected
                                  ? {
                                      ...p,
                                      end:
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
                    </div>
                  )}
                </details>
              </div>
            );
          })}
        </div>
      ))}
      <ErrorNotice error={error} />
      <button disabled={busy || !choices.length} onClick={check}>
        预览发送内容
      </button>
      {busy && <Loading />}
      {preview && (
        <div className="ai-card">
          <h2>发送前预览</h2>
          <p className="ai-wrap">
            模型：{config.data?.model || "未配置"} · 地址：
            {config.data?.endpoint || "未配置"}
          </p>
          <p>
            {preview.objects.length} 个对象，{preview.characters} 个字符／上限
            32,000
          </p>
          {preview.materials.map((m) => (
            <details key={m.key}>
              <summary>
                {m.key} · {m.object_key} · {m.field_path}
              </summary>
              <pre>{m.text}</pre>
            </details>
          ))}
          <button
            className="primary"
            disabled={busy || !config.data?.key_available}
            onClick={start}
          >
            开始整理
          </button>
        </div>
      )}
    </section>
  );
}
