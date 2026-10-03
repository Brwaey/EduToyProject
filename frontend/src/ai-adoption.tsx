import { Link } from "react-router-dom";
import { time } from "./api";

export function PlanningLink({ kind, id }: { kind: string; id: string }) {
  return (
    <Link
      to={
        "/records/ai/new?kind=action_candidates&object_kind=" +
        kind +
        "&object=" +
        id
      }
    >
      基于这些材料建议行动
    </Link>
  );
}
export function ExportLink({
  kind,
  id,
}: {
  kind: "record" | "reflection";
  id: string;
}) {
  return (
    <Link to={"/settings/export?kind=" + kind + "&object=" + id}>
      导出此{kind === "record" ? "记录" : "复盘"}
    </Link>
  );
}
export function AdoptionPanel({
  values,
}: {
  values: Record<string, unknown>[];
}) {
  if (!values.length) return null;
  return (
    <section>
      <h3>AI 采纳时的内容与固定依据</h3>
      <p className="muted">
        仅对应所列修订；后续手动编辑不代表仍由这些依据支持。
      </p>
      {values.map((a) => (
        <details key={String(a.id)} className="evidence-card">
          <summary>
            {time(String(a.created_at))} · 修订{" "}
            {String(a.revision_id).slice(0, 8)}
          </summary>
          <Link to={"/records/ai?suggestion=" + a.suggestion_id}>
            查看建议与采纳记录
          </Link>
          <pre>{JSON.stringify(a.final_content, null, 2)}</pre>
          {((a.citations as Record<string, unknown>[]) || []).map((c, i) => (
            <div key={i}>
              <p>
                {String(c.title)} · 固定 v{String(c.version)}
                {c.needs_review ? " · 来源已更新，待复核" : ""}
              </p>
              <blockquote>
                {c.deleted ? "来源已删除，正文不可用" : String(c.quote)}
              </blockquote>
            </div>
          ))}
        </details>
      ))}
    </section>
  );
}
