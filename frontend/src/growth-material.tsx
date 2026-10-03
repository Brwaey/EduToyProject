import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, fieldLabels, recordTypes, workStates, outcomes } from "./api";
import { actionStates, itemStates, detailLabels } from "./m2";
import { ErrorNotice, Loading, Markdown } from "./common";
import { bases, growthLabels, modes, type GrowthMaterial } from "./growth";

export function GrowthText({ value }: { value: Record<string, unknown> }) {
  return (
    <div className="growth-text">
      {Object.entries(value)
        .filter(([k, v]) => k !== "kind" && typeof v === "string" && v)
        .map(([k, v]) => (
          <section key={k}>
            <h4>
              {growthLabels[k] ||
                detailLabels[k] ||
                (fieldLabels as Record<string, string>)[k] ||
                k}
            </h4>
            <Markdown>
              {String(
                ({ ...modes, ...bases } as Record<string, string>)[String(v)] ||
                  v,
              )}
            </Markdown>
          </section>
        ))}
    </div>
  );
}
export function FixedMaterial({ material }: { material: GrowthMaterial }) {
  const [open, setOpen] = useState(false);
  const query = useQuery({
    queryKey: [
      "growth",
      "material",
      material.kind,
      material.id,
      material.revision_id,
    ],
    queryFn: () =>
      api<GrowthMaterial>(
        "/growth/material?" +
          new URLSearchParams({
            kind: material.kind,
            id: material.id,
            revision_id: material.revision_id,
          }),
      ),
    enabled: open,
  });
  const m = query.data || material;
  const currentLink =
    m.kind === "record"
      ? "/records/" + m.id
      : m.kind === "action" || m.kind === "reflection"
        ? "/next?tab=" +
          (m.kind === "action" ? "actions" : "reflections") +
          "&item=" +
          m.id
        : m.kind === "research_item"
          ? "/map?item=" + m.id
          : "/growth?object=" +
            m.kind +
            "&id=" +
            m.id +
            "&tab=" +
            (m.kind === "contribution"
              ? "contributions"
              : m.snapshot?.kind === "understanding_change"
                ? "understanding"
                : "abilities");
  return (
    <details
      className="evidence-card"
      open={open}
      onToggle={(e) => setOpen(e.currentTarget.open)}
    >
      <summary>
        {m.title} · 固定 v{m.version}
        {m.deleted ? " · 已删除" : m.needs_review ? " · 当前内容有变化" : ""}
      </summary>
      {open && (
        <>
          <Link to={currentLink}>打开当前内容，核对版本变化</Link>
          <ErrorNotice error={query.error} />
          {query.isPending ? (
            <Loading />
          ) : m.snapshot ? (
            <MaterialContent value={m.snapshot} />
          ) : (
            <p className="notice">来源已删除，恢复后可查看。</p>
          )}
        </>
      )}
    </details>
  );
}
export function MaterialContent({ value }: { value: Record<string, unknown> }) {
  return (
    <div className="growth-snapshot">
      <h4>{String(value.title || "当时内容")}</h4>
      {typeof value.occurred_on === "string" && (
        <p>发生于 {value.occurred_on}</p>
      )}
      {typeof value.status === "string" && (
        <p>
          当时状态：
          {(
            {
              ...actionStates,
              ...itemStates.question,
              ...itemStates.finding,
              ...itemStates.direction,
            } as Record<string, string>
          )[value.status] || value.status}
        </p>
      )}
      {typeof value.work_status === "string" && (
        <p>
          {(recordTypes as Record<string, string>)[String(value.record_type)]} ·{" "}
          {(workStates as Record<string, string>)[value.work_status]} ·{" "}
          {(outcomes as Record<string, string>)[String(value.outcome_status)]}
        </p>
      )}
      {typeof value.start_at === "string" && (
        <p>
          复盘范围：{value.start_at} — {String(value.end_at)} ·{" "}
          {String(value.timezone)}
        </p>
      )}
      {typeof value.body === "string" && <Markdown>{value.body}</Markdown>}
      {typeof value.result_summary === "string" && (
        <Markdown>{value.result_summary}</Markdown>
      )}
      {Boolean(value.fields) && (
        <GrowthText value={value.fields as Record<string, unknown>} />
      )}
      {Boolean(value.details) && (
        <GrowthText value={value.details as Record<string, unknown>} />
      )}
      {Array.isArray(value.tags) && (
        <p>
          当时标签：
          {(value.tags as { name: string }[]).map((t) => t.name).join("、")}
        </p>
      )}
      {Array.isArray(value.references) &&
        (value.references as GrowthMaterial[]).map((r, i) => (
          <FixedMaterial key={r.revision_id + ":" + i} material={r} />
        ))}
      {typeof value.ai_suggestion_id === "string" && (
        <Link to={"/records/ai?suggestion=" + value.ai_suggestion_id}>
          查看生成时的 AI 建议
        </Link>
      )}
      {Array.isArray(value.user_supplement_fields) &&
        value.user_supplement_fields.length > 0 && (
          <p className="notice">
            用户补充或修改：
            {(value.user_supplement_fields as string[])
              .map((k) => growthLabels[k] || "贡献表述")
              .join("、")}
            。原引用不代表已验证补充内容。
          </p>
        )}
    </div>
  );
}
