import type { components } from "./api.generated";
export type Item = components["schemas"]["ItemOut"];
export type ItemInput = Omit<components["schemas"]["ItemCreate"], "request_id">;
export type ItemCreate = components["schemas"]["ItemCreate"];
export type ItemEdit = components["schemas"]["ItemEdit"];
export type ItemKind = Item["kind"];
export type ItemDetails = Item["details"];
export type GraphNodeData = components["schemas"]["NodeOut"];
export type Relation = components["schemas"]["RelationOut"];
export type RelationInput = Omit<
  components["schemas"]["RelationCreate"],
  "request_id"
>;
export type Evidence = components["schemas"]["EvidenceOut"];
export type EvidenceInput = components["schemas"]["EvidenceInput"];
export type Action = components["schemas"]["ActionOut"];
export type ActionInput = Omit<
  components["schemas"]["ActionCreate"],
  "request_id"
>;
export type ResultRef = components["schemas"]["ResultRef"];
export type Reflection = components["schemas"]["ReflectionOut"];
export type ReflectionInput = Omit<
  components["schemas"]["ReflectionCreate"],
  "request_id"
>;
export type Material = components["schemas"]["MaterialOut"];
export type MaterialRef = components["schemas"]["MaterialRef"];
export type History = components["schemas"]["HistoryOut"];
export type Graph = components["schemas"]["GraphOut"];
export type Layout = components["schemas"]["LayoutOut"];
export type ObjectRef = components["schemas"]["ObjectRef"];
export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};
export const kinds = {
  question: "研究问题",
  record: "探索记录",
  finding: "发现",
  direction: "候选方向",
};
export const relationTypes = {
  related: "关联",
  subquestion: "子问题",
  derived_from: "源于",
  tests: "验证",
  supports: "支持",
  challenges: "质疑",
  extends: "延伸",
  reuses: "复用",
};
export const itemStates = {
  question: { exploring: "探索中", paused: "暂缓", answered: "已有回答" },
  finding: { tentative: "暂定", reviewed: "已核对", withdrawn: "已撤回" },
  direction: {
    candidate: "候选",
    focus: "当前重点",
    paused: "暂缓",
    closed: "已关闭",
  },
};
export const actionStates = {
  planned: "待开始",
  in_progress: "进行中",
  blocked: "受阻",
  paused: "暂缓",
  completed: "已完成",
  cancelled: "已取消",
};
export const priorities = { high: "高", normal: "普通", low: "低" };
export const detailLabels: Record<string, string> = {
  statement_type: "表述类型",
  priority: "优先级",
  motivation: "提出问题的原因",
  hypothesis: "当前假设",
  uncertainty: "仍不确定的部分",
  conditions: "适用条件",
  question: "想研究的问题",
  rationale: "产生这一方向的原因",
  supporting: "支持依据",
  opposing: "反对依据",
  resources: "所需资源",
  effort: "预计投入",
  minimal_action: "最小验证行动",
  pause_reason: "暂缓或受阻原因",
  restart_condition: "重新考虑的条件",
  research_goal: "研究目标",
  learning_goal: "学习目标（选填）",
  completion_criteria: "完成标准",
  expected_date: "预计日期",
  expectations: "原先期待",
  actual: "实际发生了什么",
  known: "已经知道的",
  unknown: "仍不知道的",
  explanations: "可能的解释",
  reusable: "可复用材料",
  progress: "本周推进",
  understanding: "认识变化",
  blockers: "仍然受阻的事项",
  next_steps: "下一步选择",
  reason: "选择的理由",
  reopen_reason: "重新开启原因",
  result_summary: "结果说明",
  description: "补充说明",
  body: "记录正文",
};
export function objectRef(n: GraphNodeData): ObjectRef {
  return { kind: n.object_kind, id: n.object_id };
}
export function evidenceInput(e: Evidence): EvidenceInput {
  return {
    record_revision_id: e.record_revision_id,
    source_version_id: e.source_version_id,
    field_path: e.field_path,
    start: e.start,
    end: e.end,
    quote: e.quote,
    stance: e.stance as EvidenceInput["stance"],
  };
}
export function localWeek() {
  const start = new Date();
  start.setHours(0, 0, 0, 0);
  start.setDate(start.getDate() - ((start.getDay() + 6) % 7));
  const end = new Date(start);
  end.setDate(end.getDate() + 7);
  return { start, end };
}
export function dateInput(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
}
export function requestIdentity(
  ref: { current: { signature: string; id: string } },
  value: unknown,
) {
  const signature = JSON.stringify(value);
  if (signature !== ref.current.signature)
    ref.current = { signature, id: crypto.randomUUID() };
  return ref.current.id;
}

export function detailValue(key: string, value: unknown) {
  if (key === "statement_type")
    return (
      (
        {
          observation: "观察事实",
          interpretation: "解释判断",
          hypothesis: "待验证假设",
        } as Record<string, string>
      )[String(value)] || String(value)
    );
  if (key === "priority")
    return priorities[value as keyof typeof priorities] || String(value);
  return String(value);
}
