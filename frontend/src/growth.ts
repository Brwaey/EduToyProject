import type { components } from "./api.generated";
export type GrowthObject = components["schemas"]["GrowthObjectOut"];
export type GrowthEvidence = components["schemas"]["GrowthEvidenceOut"];
export type EvidencePick = components["schemas"]["GrowthEvidenceInput"];
export type GrowthMaterial = components["schemas"]["GrowthMaterialOut"];
export type AbilityTag = components["schemas"]["AbilityTagOut"];
export type GrowthHistory = components["schemas"]["GrowthHistoryOut"];
export type ContributionInput = components["schemas"]["ContributionInput"];
export type GrowthInput = Omit<
  components["schemas"]["GrowthCreate"],
  "request_id"
>;
export type GrowthKind =
  "contribution" | "ability_instance" | "understanding_change";
export const contributionTypes = {
  question: "提出问题",
  choice: "作出选择",
  correction: "修正建议",
  validation: "设计验证",
  understanding: "形成理解",
  connection: "建立联系",
};
export const growthKinds = {
  contribution: "贡献",
  ability_instance: "能力实例",
  understanding_change: "理解变化",
};
export const evidenceStates = {
  self_report: "用户自述／待补依据",
  attached: "已附材料",
  needs_review: "依据待复核",
  unavailable: "部分或全部依据不可用",
};
export const growthLabels: Record<string, string> = {
  personal_role: "我的具体参与",
  reason: "为什么这样做",
  ai_help: "AI 提供的帮助",
  others_help: "他人提供的帮助",
  impact: "产生的影响",
  next_steps: "下一步想尝试什么",
  situation: "当时的任务与情境",
  attempts: "我尝试了什么",
  learned: "我学到了什么",
  difficulties: "仍有困难的部分",
  before: "之前如何理解",
  after: "现在如何理解",
  trigger: "什么促使我改变",
  uncertainty: "仍不确定的部分",
  completion_mode: "完成方式",
  basis_type: "依据类型",
};
export const modes = {
  unspecified: "未注明",
  assisted: "在帮助下完成",
  independent: "独立完成",
  transferred: "迁移到新情境",
};
export const bases = {
  self_report: "用户自述",
  material: "材料记录",
  task_practice: "任务实践",
};
export const purposes = {
  context: "相关依据",
  before: "之前依据",
  trigger: "触发材料",
  after: "现在依据",
};
export const materialKinds = {
  record: "科研记录",
  action: "行动",
  reflection: "复盘",
  contribution: "贡献",
};
export function localDate() {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function growthPath(kind: string) {
  return kind === "contribution" ? "/contributions" : "/growth-entries";
}
export function growthLink(obj: { id: string; kind: string }) {
  return `/growth?tab=${obj.kind === "contribution" ? "contributions" : obj.kind === "understanding_change" ? "understanding" : "abilities"}&id=${obj.id}&object=${obj.kind === "contribution" ? "contribution" : "growth_entry"}`;
}
export function evidencePick(e: EvidencePick): EvidencePick {
  return {
    record_revision_id: e.record_revision_id ?? null,
    m2_revision_id: e.m2_revision_id ?? null,
    contribution_revision_id: e.contribution_revision_id ?? null,
    source_version_id: e.source_version_id ?? null,
    field_path: e.field_path ?? "body",
    start: e.start ?? null,
    end: e.end ?? null,
    quote: e.quote ?? "",
    purpose: e.purpose ?? "context",
  };
}
export function materialPick(
  m: GrowthMaterial,
  purpose: EvidencePick["purpose"] = "context",
): EvidencePick {
  return evidencePick({
    field_path: "body",
    quote: "",
    [m.kind === "record"
      ? "record_revision_id"
      : m.kind === "contribution"
        ? "contribution_revision_id"
        : "m2_revision_id"]: m.revision_id,
    purpose,
  });
}
