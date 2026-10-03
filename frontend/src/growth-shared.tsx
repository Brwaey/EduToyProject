import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api } from "./api";
import type { components } from "./api.generated";
import { ErrorNotice, Loading, Options } from "./common";
import { EvidenceEditor, Pagination } from "./m2-shared";
import type { Page, EvidenceInput } from "./m2";
import {
  evidencePick,
  growthLink,
  materialKinds,
  materialPick,
  purposes,
  type EvidencePick,
  type GrowthEvidence,
  type GrowthMaterial,
} from "./growth";

export { GrowthText, FixedMaterial, MaterialContent } from "./growth-material";
import { FixedMaterial } from "./growth-material";
export function GrowthEvidenceCards({ values }: { values: GrowthEvidence[] }) {
  return (
    <div>
      {values.length === 0 && (
        <p className="muted">用户自述／待补依据。可以先留下自己的经历。</p>
      )}
      {values.map((e) => (
        <section key={e.id} className="growth-evidence">
          <small>
            {purposes[e.purpose || "context"]}
            {e.needs_review ? " · 依据待复核" : ""}
          </small>
          {e.availability === "deleted" && (
            <p className="notice">部分或全部依据已删除，恢复后可继续核对。</p>
          )}
          <FixedMaterial material={e.source} />
          {e.content !== null && (
            <details>
              <summary>
                查看引用原文{e.source_version_id ? "（来源版本）" : ""}
              </summary>
              {e.quote && <blockquote>{e.quote}</blockquote>}
              <pre className="growth-original">{e.content}</pre>
            </details>
          )}
        </section>
      ))}
    </div>
  );
}
export function GrowthEvidencePicker({
  values,
  onChange,
  understanding = false,
  allowContributions = false,
  existing = [],
}: {
  values: EvidencePick[];
  onChange: (v: EvidencePick[]) => void;
  understanding?: boolean;
  allowContributions?: boolean;
  existing?: GrowthEvidence[];
}) {
  const [q, setQ] = useState(""),
    [kind, setKind] = useState("record"),
    [page, setPage] = useState(1),
    [purpose, setPurpose] = useState<EvidencePick["purpose"]>(
      understanding ? "trigger" : "context",
    ),
    [labels, setLabels] = useState<Record<string, string>>({});
  const query = useQuery({
    queryKey: ["growth", "materials", q, kind, page],
    queryFn: () =>
      api<Page<GrowthMaterial>>(
        "/growth/materials?" +
          new URLSearchParams({ q, kind, page: String(page), page_size: "5" }),
      ),
  });
  function add(v: EvidencePick, title?: string) {
    const normalized = evidencePick(v);
    if (
      !values.some(
        (e) => JSON.stringify(evidencePick(e)) === JSON.stringify(normalized),
      )
    )
      onChange([...values, normalized]);
    if (title)
      setLabels((old) => ({ ...old, [JSON.stringify(normalized)]: title }));
  }
  function snippets(refs: EvidenceInput[]) {
    const all = [...values];
    for (const e of refs) {
      const v = evidencePick({ ...e, purpose });
      if (
        !all.some((x) => JSON.stringify(evidencePick(x)) === JSON.stringify(v))
      )
        all.push(v);
    }
    onChange(all);
  }
  return (
    <fieldset className="growth-material-picker">
      <legend>选择固定版本依据（可暂不添加）</legend>
      {understanding && (
        <label>
          依据用于
          <select
            value={purpose}
            onChange={(e) =>
              setPurpose(e.target.value as EvidencePick["purpose"])
            }
          >
            <Options
              values={{
                before: purposes.before,
                trigger: purposes.trigger,
                after: purposes.after,
              }}
            />
          </select>
        </label>
      )}
      {values.map((e, i) => (
        <div className="evidence-card" key={i}>
          <p>
            {purposes[e.purpose || "context"]} ·{" "}
            {labels[JSON.stringify(evidencePick(e))] ||
              existing.find(
                (x) =>
                  JSON.stringify(evidencePick(x)) ===
                  JSON.stringify(evidencePick(e)),
              )?.source.title ||
              e.quote ||
              "已选择固定版本材料"}
          </p>
          <button
            type="button"
            onClick={() => onChange(values.filter((_, j) => j !== i))}
          >
            移除依据
          </button>
        </div>
      ))}
      <div className="form-grid">
        <label>
          材料类型
          <select
            value={kind}
            onChange={(e) => {
              setKind(e.target.value);
              setPage(1);
            }}
          >
            <Options
              values={
                allowContributions
                  ? materialKinds
                  : {
                      record: materialKinds.record,
                      action: materialKinds.action,
                      reflection: materialKinds.reflection,
                    }
              }
            />
          </select>
        </label>
        <label>
          搜索材料
          <input
            value={q}
            onChange={(e) => {
              setQ(e.target.value);
              setPage(1);
            }}
          />
        </label>
      </div>
      <ErrorNotice error={query.error} />
      {query.isPending ? (
        <Loading />
      ) : (
        query.data?.items.map((m) => (
          <div key={m.revision_id} className="growth-material-row">
            <span>
              {m.title} · v{m.version}
            </span>
            <button
              type="button"
              onClick={() => add(materialPick(m, purpose), m.title)}
            >
              添加依据
            </button>
          </div>
        ))
      )}
      {query.data && (
        <Pagination
          page={page}
          total={query.data.total}
          size={5}
          onChange={setPage}
        />
      )}
      <details>
        <summary>引用记录中的具体原文或来源片段</summary>
        <EvidenceEditor values={[]} onChange={snippets} />
      </details>
    </fieldset>
  );
}
export function GrowthContext({
  kind,
  id,
  readonly = false,
}: {
  kind: "record" | "action" | "reflection" | "research_item";
  id: string;
  readonly?: boolean;
}) {
  const query = useQuery({
    queryKey: ["growth", "context", kind, id],
    queryFn: () =>
      api<components["schemas"]["GrowthContextOut"]>(
        "/growth/context?" + new URLSearchParams({ kind, id }),
      ),
  });
  const link = (target: string) =>
    "/growth?" +
    new URLSearchParams({ new: target, source_kind: kind, source_id: id });
  return (
    <section className="growth-context">
      <h3>我的贡献与成长</h3>
      {!readonly && (
        <div className="inline-actions">
          <Link to={link("contribution")}>记录我的贡献</Link>
          <Link to={link("ability_instance")}>记录能力实例</Link>
          <Link to={link("understanding_change")}>记录理解变化</Link>
        </div>
      )}
      <ErrorNotice error={query.error} />
      {query.data &&
        [...query.data.contributions, ...query.data.entries].map((o) => (
          <p key={o.id}>
            <Link to={growthLink(o)}>{o.title}</Link>
          </p>
        ))}
      {query.data &&
        !query.data.contributions.length &&
        !query.data.entries.length && (
          <p className="muted">还没有关联条目，可以先留下一句自述。</p>
        )}
    </section>
  );
}
