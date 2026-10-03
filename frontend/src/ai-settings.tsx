import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, json } from "./api";
import { ErrorNotice, Loading, useDirtyGuard } from "./common";
import {
  endpointPreview,
  isActive,
  taskStates,
  type AIConfig,
  type AITask,
} from "./ai";

export default function AISettings() {
  const config = useQuery({
    queryKey: ["ai", "config"],
    queryFn: () => api<AIConfig>("/ai/config"),
  });
  return (
    <section className="ai-page">
      <header className="page-header">
        <div>
          <div className="eyebrow">MODEL SETTINGS</div>
          <h1>模型设置</h1>
          <p>使用你自己的 OpenAI 兼容接口，配置按账号保存。</p>
        </div>
        <Link to="/records/ai">AI 收件箱</Link>
      </header>
      <ErrorNotice error={config.error} />
      {config.isPending ? (
        <Loading />
      ) : (
        config.data && <ConfigForm initial={config.data} />
      )}
    </section>
  );
}
function ConfigForm({ initial }: { initial: AIConfig }) {
  const client = useQueryClient();
  const [url, setUrl] = useState(initial.endpoint),
    [model, setModel] = useState(initial.model),
    [key, setKey] = useState(""),
    [version, setVersion] = useState(initial.version),
    [saved, setSaved] = useState(initial),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [message, setMessage] = useState(""),
    [taskId, setTaskId] = useState("");
  const dirty = url !== saved.endpoint || model !== saved.model || !!key;
  useDirtyGuard(dirty);
  const task = useQuery({
    queryKey: ["ai", "task", taskId],
    queryFn: () => api<AITask>("/ai/tasks/" + taskId),
    enabled: !!taskId,
    refetchInterval: (q) =>
      !q.state.data || isActive(q.state.data) ? 2000 : false,
  });
  async function save(test: boolean) {
    setBusy(true);
    setError(null);
    setMessage("");
    try {
      const c = await api<AIConfig>(
        "/ai/config",
        json("PUT", {
          expected_version: version,
          url,
          model,
          ...(key ? { api_key: key } : {}),
        }),
      );
      setKey("");
      setVersion(c.version);
      setSaved(c);
      setUrl(c.endpoint);
      setMessage("配置已保存。");
      client.setQueryData(["ai", "config"], c);
      if (test) {
        const t = await api<AITask>(
          "/ai/config/test",
          json("POST", {
            request_id: crypto.randomUUID(),
            config_version: c.version,
          }),
        );
        setTaskId(t.id);
      }
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function clear() {
    if (!window.confirm("清除模型配置并取消尚未完成的 AI 任务？")) return;
    setBusy(true);
    try {
      await api("/ai/config", json("DELETE", { expected_version: version }));
      const c = await api<AIConfig>("/ai/config");
      setSaved(c);
      setVersion(c.version);
      setUrl("");
      setModel("");
      setKey("");
      setTaskId("");
      await client.invalidateQueries({ queryKey: ["ai"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="ai-card ai-config" data-dirty={dirty}>
      <p className="ai-muted">
        上次连接测试：
        {taskStates[task.data?.status || initial.test_status] || "尚未测试"}
      </p>
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          try {
            const c = await api<AIConfig>("/ai/config");
            setVersion(c.version);
            setSaved(c);
            setMessage("已更新配置版本，当前输入仍保留，请核对后保存。");
          } catch (e) {
            setError(e);
          }
        }}
      >
        重新载入配置版本（保留输入）
      </button>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          void save(false);
        }}
      >
        <label>
          API URL
          <input
            required
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            placeholder="https://example.com/v1"
            autoComplete="off"
          />
        </label>
        <p className="ai-muted ai-wrap">
          实际请求地址：{endpointPreview(url) || "填写后显示"}
        </p>
        <label>
          模型名
          <input
            required
            value={model}
            onChange={(e) => setModel(e.target.value)}
            placeholder="填写服务提供的模型名"
            autoComplete="off"
          />
        </label>
        <label>
          API Key
          <input
            type="password"
            autoComplete="new-password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder={
              saved.has_key
                ? "已配置；留空保留，修改地址需重新输入"
                : "填写 API Key"
            }
          />
        </label>
        <p className="ai-muted">
          密钥加密保存在本机后端，保存后不能查看明文。HTTP
          仅支持本机回环地址；其他地址使用 HTTPS。
        </p>
        {saved.has_key && !saved.key_available && (
          <div className="notice">
            主密钥不可用，请恢复原密钥文件。手动记录仍可使用。
          </div>
        )}
        <div className="inline-actions">
          <button className="primary" disabled={busy} type="submit">
            保存配置
          </button>
          <button disabled={busy} type="button" onClick={() => void save(true)}>
            保存并测试
          </button>
          {saved.has_key && (
            <button disabled={busy} type="button" onClick={clear}>
              清除配置
            </button>
          )}
        </div>
        <ErrorNotice error={error} />
        {message && <p role="status">{message}</p>}
      </form>
      {task.data && (
        <div className="notice" role="status">
          连接测试：{taskStates[task.data.status]}。
          {task.data.error_message ||
            (task.data.status === "succeeded"
              ? "基本请求成功，可以选择科研材料开始整理。"
              : "")}
          <Link to={"/records/ai?task=" + task.data.id}>查看任务</Link>
        </div>
      )}
      <ErrorNotice error={task.error} />
    </div>
  );
}
