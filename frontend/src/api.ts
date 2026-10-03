import type { components } from "./api.generated";

export type RecordData = components["schemas"]["RecordOut"];
export type Project = components["schemas"]["ProjectOut"];
export type Source = components["schemas"]["SourceOut"];
export type Revision = components["schemas"]["RevisionOut"];
export type Auth = components["schemas"]["AuthOut"];
export type Fields = components["schemas"]["ExplorationFields"];
export type RecordPage = components["schemas"]["RecordList"];
export type RecordCreate = components["schemas"]["RecordCreate"];
export type RecordPatch = components["schemas"]["RecordPatch"];

let csrf = "";
export function setCsrf(value: string) {
  csrf = value;
}
export class ApiError extends Error {
  constructor(
    public status: number,
    public code: string,
    message: string,
  ) {
    super(message);
  }
}
async function request(
  path: string,
  options: RequestInit = {},
): Promise<Response> {
  const headers = new Headers(options.headers);
  if (options.body && !(options.body instanceof FormData))
    headers.set("Content-Type", "application/json");
  if (csrf) headers.set("X-CSRF-Token", csrf);
  let response: Response;
  try {
    response = await fetch("/api/v1" + path, {
      ...options,
      credentials: "same-origin",
      headers,
    });
  } catch {
    throw new Error("连接失败，请检查后端是否运行。当前输入仍然保留。");
  }
  if (!response.ok) {
    const result = await response.json().catch(() => ({}));
    if (response.status === 401 && !path.startsWith("/auth/"))
      window.dispatchEvent(new Event("session-expired"));
    throw new ApiError(
      response.status,
      result.error?.code || "request_failed",
      result.error?.message || "请求失败，请稍后重试",
    );
  }
  return response;
}
export async function api<T>(
  path: string,
  options: RequestInit = {},
): Promise<T> {
  const response = await request(path, options);
  return response.status === 204 ? (undefined as T) : response.json();
}
export async function apiBlob(
  path: string,
  options: RequestInit,
): Promise<Blob> {
  return (await request(path, options)).blob();
}
export function json(method: string, body: unknown): RequestInit {
  return { method, body: JSON.stringify(body) };
}
export const recordTypes = {
  note: "随手记",
  paper: "论文阅读",
  experiment: "实验尝试",
  ai: "AI 协作",
  idea: "灵感疑问",
};
export const workStates = {
  planned: "待开始",
  in_progress: "进行中",
  blocked: "受阻",
  paused: "暂缓",
  finished: "已结束",
};
export const outcomes = {
  none: "尚无结果",
  inconclusive: "证据不足",
  unsupported: "当前条件下未支持",
  preliminary: "初步支持",
  not_applicable: "不适用",
};
export const fieldLabels: Record<keyof Fields, string> = {
  context: "背景与目标",
  actions: "我的行动",
  collaboration: "AI 与他人的帮助",
  observations: "观察与结果",
  interpretation: "我的判断",
  next_steps: "后续想法",
};
export const emptyFields: Fields = {
  context: "",
  actions: "",
  collaboration: "",
  observations: "",
  interpretation: "",
  next_steps: "",
};
export function time(value: string) {
  return new Date(value).toLocaleString("zh-CN", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}
