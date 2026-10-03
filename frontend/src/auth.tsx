import { useQueryClient } from "@tanstack/react-query";
import { ArrowUpRight, GitBranch, Sprout } from "lucide-react";
import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { api, json, setCsrf, type Auth } from "./api";

import { Dialog, ErrorNotice } from "./common";
export function Login() {
  const [register, setRegister] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const client = useQueryClient(),
    navigate = useNavigate();
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setBusy(true);
    const form = new FormData(event.currentTarget);
    try {
      const body = {
        username: form.get("username"),
        password: form.get("password"),
        ...(register ? { display_name: form.get("display_name") } : {}),
      };
      const auth = await api<Auth>(
        register ? "/auth/register" : "/auth/login",
        json("POST", body),
      );
      client.clear();
      setCsrf(auth.csrf_token);
      client.setQueryData(["me"], auth);
      navigate("/records");
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <main className="auth-page">
      <section className="auth-intro">
        <div className="brand">
          <Sprout />
          <strong>研迹</strong>
          <span>YANJI</span>
        </div>
        <div>
          <p className="eyebrow">留住探索中的每一步</p>
          <h1>
            让思考有迹可循，
            <br />
            让成长被自己看见。
          </h1>
          <p>
            记录一次尝试，保留一个判断。
            <br />
            从零散的研究日常，慢慢长出自己的脉络。
          </p>
        </div>
        <div className="auth-foot">
          <span>记录 · 理解 · 成长</span>
          <GitBranch size={38} />
        </div>
      </section>
      <section className="auth-form">
        <span className="small-label">你的个人科研空间</span>
        <h2>{register ? "开始记录你的研迹" : "欢迎回来"}</h2>
        <p className="muted">
          {register
            ? "创建独立账号，保存自己的研究记录。"
            : "从上一次的思考，继续向前。"}
        </p>
        <form onSubmit={submit}>
          <label>
            用户名
            <input
              name="username"
              required
              pattern="[a-zA-Z0-9_]{3,32}"
              minLength={3}
              maxLength={32}
              autoComplete="username"
              placeholder="3–32 位字母、数字或下划线"
            />
          </label>
          {register && (
            <label>
              显示名称
              <input
                name="display_name"
                required
                maxLength={80}
                placeholder="希望怎样称呼你"
              />
            </label>
          )}
          <label>
            密码
            <input
              name="password"
              type="password"
              required
              minLength={8}
              maxLength={128}
              autoComplete={register ? "new-password" : "current-password"}
              placeholder="至少 8 位"
            />
          </label>
          <ErrorNotice error={error} />
          <button className="primary full" disabled={busy}>
            {busy ? "请稍候…" : register ? "创建账号" : "进入研迹"}
            <ArrowUpRight size={18} />
          </button>
        </form>
        <p className="auth-switch">
          {register ? "已有账号？" : "还没有账号？"}
          <button
            className="text-button"
            onClick={() => {
              setRegister(!register);
              setError(null);
            }}
          >
            {register ? "登录" : "创建账号"}
          </button>
        </p>
        <p className="privacy-note">
          记录保存在当前服务的本地数据库中，仅对你的账号可见。
        </p>
      </section>
    </main>
  );
}

export function Reauthenticate({
  username,
  onClose,
}: {
  username: string;
  onClose: () => void;
}) {
  const client = useQueryClient();
  const [password, setPassword] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const auth = await api<Auth>(
        "/auth/login",
        json("POST", { username, password }),
      );
      setCsrf(auth.csrf_token);
      client.setQueryData(["me"], auth);
      onClose();
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="登录已过期" onClose={onClose}>
      <form onSubmit={submit}>
        <p className="muted">当前输入已保留。重新登录后，请再次点击保存。</p>
        <label>
          用户名
          <input value={username} readOnly autoComplete="username" />
        </label>
        <label>
          密码
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            required
            autoComplete="current-password"
          />
        </label>
        <ErrorNotice error={error} />
        <button className="primary" disabled={busy}>
          {busy ? "登录中…" : "重新登录"}
        </button>
      </form>
    </Dialog>
  );
}
