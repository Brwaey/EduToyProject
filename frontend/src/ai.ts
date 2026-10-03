import type { components } from "./api.generated";
export type AIConfig = components["schemas"]["ConfigOut"];
export type AITask = components["schemas"]["TaskOut"];
export type AISuggestion = components["schemas"]["SuggestionOut"];
export type AIPreview = components["schemas"]["PreviewOut"];
export type AISelection = components["schemas"]["Selection"];
export type AIPick = components["schemas"]["MaterialPick"];
export type Citation = components["schemas"]["Citation"];
export type AIRelation = components["schemas"]["RelationCandidate"];
export type AIKind =
  "record_draft" | "relation_suggestions" | "contribution_candidates";
export type FieldName =
  | "title"
  | "record_type"
  | "context"
  | "actions"
  | "collaboration"
  | "observations"
  | "interpretation"
  | "next_steps";
export type Draft = {
  fields: Partial<Record<FieldName, { value: string; citations: Citation[] }>>;
  questions: string[];
};
export const taskStates: Record<string, string> = {
  queued: "排队中",
  running: "处理中",
  succeeded: "已完成",
  failed: "失败",
  cancelled: "已取消",
};
export const suggestionStates: Record<string, string> = {
  pending: "待确认",
  accepted: "已采纳",
  edited_accepted: "修改后采纳",
  rejected: "已拒绝",
};
export const taskKinds: Record<string, string> = {
  record_draft: "探索卡整理",
  relation_suggestions: "地图关系建议",
  connection_test: "连接测试",
  contribution_candidates: "贡献候选",
};
export function endpointPreview(url: string) {
  const s = url.trim().replace(/\/+$/, "");
  return s
    ? s.endsWith("/chat/completions")
      ? s
      : s + "/chat/completions"
    : "";
}
export function isActive(t?: AITask) {
  return t?.status === "queued" || t?.status === "running";
}
