import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowUpRight,
  BookOpen,
  ChevronRight,
  Compass,
  Folder,
  GitBranch,
  LogOut,
  Plus,
  Sprout,
} from "lucide-react";
import { lazy, Suspense, useEffect, useState } from "react";
import {
  Link,
  Navigate,
  NavLink,
  useBlocker,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { api, ApiError, setCsrf, type Auth, type Project } from "./api";

import { Reauthenticate } from "./auth";
import { ErrorNotice, Loading } from "./common";
import { ProjectManager } from "./projects";
const AISettings = lazy(() => import("./ai-settings"));
const ExportPage = lazy(() => import("./export-page"));
const AIInbox = lazy(() => import("./ai-inbox"));
const AICreate = lazy(() => import("./ai-create"));
const RecordsPage = lazy(() =>
  import("./records").then((module) => ({ default: module.RecordsPage })),
);
const MapPage = lazy(() => import("./map"));
const NextPage = lazy(() => import("./planning"));
const GrowthPage = lazy(() => import("./growth-page"));

export function App() {
  useBlocker(
    () =>
      !!document.querySelector('[data-dirty="true"]') &&
      !window.confirm("还有未保存的修改，确定离开吗？"),
  );
  const client = useQueryClient(),
    navigate = useNavigate(),
    location = useLocation();
  const me = useQuery({
    queryKey: ["me"],
    queryFn: async () => {
      const value = await api<Auth>("/auth/me");
      setCsrf(value.csrf_token);
      return value;
    },
    staleTime: Infinity,
  });
  const projects = useQuery({
    queryKey: ["projects"],
    queryFn: () => api<Project[]>("/projects"),
    enabled: !!me.data,
  });
  const [manager, setManager] = useState(false),
    [sessionExpired, setSessionExpired] = useState(false),
    [logoutError, setLogoutError] = useState<unknown>(null);
  useEffect(() => {
    const expired = () => {
      setCsrf("");
      setSessionExpired(true);
    };
    window.addEventListener("session-expired", expired);
    return () => window.removeEventListener("session-expired", expired);
  }, [client, navigate]);
  if (me.isPending) return <Loading />;
  if (me.error instanceof ApiError && me.error.status === 401)
    return <Navigate to="/login" replace />;
  if (me.error || !me.data)
    return (
      <main className="fatal">
        <ErrorNotice error={me.error} />
        <button onClick={() => me.refetch()}>重新连接</button>
      </main>
    );
  async function logout() {
    if (
      document.querySelector('[data-dirty="true"]') &&
      !window.confirm("还有未保存的修改，确定退出吗？")
    )
      return;
    try {
      await api("/auth/logout", { method: "POST" });
      setCsrf("");
      client.clear();
      navigate("/login");
    } catch (e) {
      setLogoutError(e);
    }
  }
  const onRecords =
    location.pathname === "/" || location.pathname.startsWith("/records");
  const other =
    location.pathname === "/map"
      ? ["研究地图", "把研究问题、尝试与证据连接起来。", "M2 · 研究脉络与关系"]
      : location.pathname === "/growth"
        ? [
            "我的成长",
            "用具体的判断与实例，回看理解的变化。",
            "M4 · 贡献与能力成长",
          ]
        : ["下一步", "从已有证据出发，选择下一次探索。", "M2 · 方向与行动"];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <Link className="brand" to="/records">
          <Sprout size={26} />
          <strong>研迹</strong>
          <span>YANJI</span>
        </Link>
        <div className="workspace-label">个人科研空间</div>
        <nav aria-label="主导航">
          <NavLink to="/map">
            <GitBranch size={19} />
            研究地图
          </NavLink>
          <NavLink to="/records" className={onRecords ? "active" : ""}>
            <BookOpen size={19} />
            科研记录
          </NavLink>
          <NavLink to="/growth">
            <Sprout size={19} />
            我的成长
          </NavLink>
          <NavLink to="/next">
            <Compass size={19} />
            下一步
          </NavLink>
        </nav>
        <div className="sidebar-projects">
          <div className="section-label">
            研究项目
            <button
              className="icon-button"
              onClick={() => setManager(true)}
              aria-label="管理项目"
            >
              <Plus size={16} />
            </button>
          </div>
          <ErrorNotice error={projects.error} />
          {projects.data
            ?.filter((p) => !p.archived)
            .slice(0, 6)
            .map((p) => (
              <Link key={p.id} to={"/records?project=" + p.id}>
                <Folder size={15} />
                <span>{p.name}</span>
              </Link>
            ))}
          <button className="text-button" onClick={() => setManager(true)}>
            管理项目与归档 <ChevronRight size={14} />
          </button>
        </div>
        <div className="sidebar-bottom">
          <div className="user">
            <span className="avatar">
              {me.data.user.display_name.slice(0, 1)}
            </span>
            <div>
              <strong>{me.data.user.display_name}</strong>
              <small>个人账号</small>
            </div>
            <button
              className="icon-button mobile-projects"
              onClick={() => setManager(true)}
              aria-label="管理项目"
            >
              <Folder size={17} />
            </button>
            <button
              className="icon-button"
              onClick={logout}
              aria-label="退出登录"
            >
              <LogOut size={17} />
            </button>
          </div>
          <ErrorNotice error={logoutError} />
          <Link to="/settings/model">模型设置</Link>
          <Link to="/settings/export">数据导出</Link>
          <p>每一次认真思考，都有迹可循。</p>
        </div>
      </aside>
      <main className="main-content">
        {location.pathname === "/settings/export" ? (
          <Suspense fallback={<Loading />}>
            <ExportPage key={location.search} projects={projects.data || []} />
          </Suspense>
        ) : location.pathname === "/settings/model" ? (
          <Suspense fallback={<Loading />}>
            <AISettings />
          </Suspense>
        ) : location.pathname === "/records/ai/new" ? (
          <Suspense fallback={<Loading />}>
            <AICreate />
          </Suspense>
        ) : location.pathname === "/records/ai" ? (
          <Suspense fallback={<Loading />}>
            <AIInbox projects={projects.data || []} />
          </Suspense>
        ) : onRecords ? (
          <Suspense fallback={<Loading />}>
            <RecordsPage projects={projects.data || []} />
          </Suspense>
        ) : location.pathname === "/map" ? (
          <Suspense fallback={<Loading />}>
            <MapPage projects={projects.data || []} />
          </Suspense>
        ) : location.pathname === "/growth" ? (
          <Suspense fallback={<Loading />}>
            <GrowthPage projects={projects.data || []} />
          </Suspense>
        ) : location.pathname === "/next" ? (
          <Suspense fallback={<Loading />}>
            <NextPage projects={projects.data || []} />
          </Suspense>
        ) : (
          <section className="future-page">
            <span className="eyebrow">{other[2]}</span>
            <h1>{other[0]}</h1>
            <p>{other[1]}</p>
            <div className="future-state">
              <Compass size={40} />
              <h2>这一页正在准备中</h2>
              <p>
                当前已开放科研记录、研究地图和下一步。成长模块将在后续连接你的具体判断、贡献与学习实例。
              </p>
              <Link className="primary" to="/records">
                去记录一次探索 <ArrowUpRight size={17} />
              </Link>
            </div>
          </section>
        )}
      </main>
      {manager && (
        <ProjectManager
          projects={projects.data || []}
          onClose={() => setManager(false)}
        />
      )}
      {sessionExpired && (
        <Reauthenticate
          username={me.data.user.username}
          onClose={() => setSessionExpired(false)}
        />
      )}
    </div>
  );
}
