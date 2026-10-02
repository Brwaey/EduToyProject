import {
  useEffect,
  useRef,
  useState,
  type FormEvent,
  type ReactNode,
} from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Link,
  Navigate,
  NavLink,
  useBlocker,
  useLocation,
  useNavigate,
  useSearchParams,
} from "react-router-dom";
import {
  BookOpen,
  ArrowUpRight,
  GitBranch,
  Sprout,
  Compass,
  Plus,
  Upload,
  LogOut,
  Folder,
  Search,
  X,
  ArrowLeft,
  Check,
  FileText,
  Clock,
  Trash2,
  RotateCcw,
  Pencil,
  Archive,
  ChevronRight,
  LoaderCircle,
} from "lucide-react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";
import {
  api,
  json,
  setCsrf,
  ApiError,
  emptyFields,
  fieldLabels,
  outcomes,
  recordTypes,
  time,
  workStates,
  type Auth,
  type Fields,
  type Project,
  type RecordData,
  type RecordPage,
  type Revision,
  type Source,
  type RecordCreate,
  type RecordPatch,
} from "./api";

function ErrorNotice({ error }: { error: unknown }) {
  return error ? (
    <div className="error" role="alert">
      {error instanceof Error ? error.message : String(error)}
    </div>
  ) : null;
}
function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={18} />
      正在载入…
    </div>
  );
}
function Markdown({ children }: { children: string }) {
  return (
    <div className="markdown">
      <ReactMarkdown
        skipHtml
        urlTransform={(url) =>
          /^https?:\/\//i.test(url) ? defaultUrlTransform(url) : ""
        }
        components={{
          a: ({ children, href }) =>
            href ? (
              <a href={href} target="_blank" rel="noreferrer">
                {children}
              </a>
            ) : (
              <span>{children}</span>
            ),
          img: ({ alt }) => <span>[图片：{alt}]</span>,
        }}
      >
        {children}
      </ReactMarkdown>
    </div>
  );
}
function Options({ values }: { values: Record<string, string> }) {
  return Object.entries(values).map(([v, label]) => (
    <option key={v} value={v}>
      {label}
    </option>
  ));
}
function useDirtyGuard(dirty: boolean) {
  useBlocker(() => dirty && !window.confirm("还有未保存的修改，确定离开吗？"));
  useEffect(() => {
    const guard = (event: BeforeUnloadEvent) => {
      if (dirty) {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", guard);
    return () => window.removeEventListener("beforeunload", guard);
  }, [dirty]);
}
function Dialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header>
        <h2>{title}</h2>
        <button className="icon-button" onClick={onClose} aria-label="关闭">
          <X size={20} />
        </button>
      </header>
      {children}
    </dialog>
  );
}

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

export function App() {
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
            研究地图<span className="nav-soon">待开发</span>
          </NavLink>
          <NavLink to="/records" className={onRecords ? "active" : ""}>
            <BookOpen size={19} />
            科研记录
          </NavLink>
          <NavLink to="/growth">
            <Sprout size={19} />
            我的成长<span className="nav-soon">待开发</span>
          </NavLink>
          <NavLink to="/next">
            <Compass size={19} />
            下一步<span className="nav-soon">待开发</span>
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
          <p>每一次认真思考，都有迹可循。</p>
        </div>
      </aside>
      <main className="main-content">
        {onRecords ? (
          <RecordsPage projects={projects.data || []} />
        ) : (
          <section className="future-page">
            <span className="eyebrow">{other[2]}</span>
            <h1>{other[0]}</h1>
            <p>{other[1]}</p>
            <div className="future-state">
              <Compass size={40} />
              <h2>这一页正在准备中</h2>
              <p>
                当前版本已开放科研记录。你现在保存的材料和判断，将成为后续研究脉络的基础。
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

function Reauthenticate({
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

function ProjectManager({
  projects,
  onClose,
}: {
  projects: Project[];
  onClose: () => void;
}) {
  const client = useQueryClient();
  const [selected, setSelected] = useState<Project | null>(null),
    [name, setName] = useState(""),
    [description, setDescription] = useState("");
  const [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false);
  const close = () => {
    if (!dirty || window.confirm("放弃尚未保存的项目修改？")) onClose();
  };
  const choose = (p: Project | null) => {
    if (dirty && !window.confirm("放弃尚未保存的项目修改？")) return;
    setSelected(p);
    setName(p?.name || "");
    setDescription(p?.description || "");
    setDirty(false);
    setError(null);
  };
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await api(
        selected ? "/projects/" + selected.id : "/projects",
        json(selected ? "PATCH" : "POST", { name, description }),
      );
      setDirty(false);
      setSelected(null);
      setName("");
      setDescription("");
      await client.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  async function archive(p: Project) {
    setBusy(true);
    setError(null);
    try {
      await api("/projects/" + p.id, json("PATCH", { archived: !p.archived }));
      await client.invalidateQueries({ queryKey: ["projects"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="管理研究项目" onClose={close}>
      <div className="project-manager">
        <section>
          <button className="subtle" onClick={() => choose(null)}>
            <Plus size={16} />
            新建项目
          </button>
          {projects.map((p) => (
            <div className="project-row" key={p.id}>
              <button className="text-button" onClick={() => choose(p)}>
                {p.name}
                {p.archived && <small>已归档</small>}
              </button>
              <button
                className="icon-button"
                disabled={busy}
                aria-label={(p.archived ? "恢复项目 " : "归档项目 ") + p.name}
                onClick={() => archive(p)}
              >
                {p.archived ? <RotateCcw size={16} /> : <Archive size={16} />}
              </button>
            </div>
          ))}
        </section>
        <form onSubmit={save}>
          <h3>{selected ? "编辑项目" : "新建项目"}</h3>
          <label>
            项目名称
            <input
              value={name}
              onChange={(e) => {
                setName(e.target.value);
                setDirty(true);
              }}
              required
              maxLength={120}
            />
          </label>
          <label>
            项目说明
            <textarea
              value={description}
              onChange={(e) => {
                setDescription(e.target.value);
                setDirty(true);
              }}
              rows={4}
              maxLength={10000}
            />
          </label>
          <ErrorNotice error={error} />
          <button className="primary" disabled={busy}>
            保存项目
          </button>
          <p className="muted small">
            归档保留已有记录。恢复项目后可继续编辑。
          </p>
        </form>
      </div>
    </Dialog>
  );
}

function RecordsPage({ projects }: { projects: Project[] }) {
  const location = useLocation(),
    [params, setParams] = useSearchParams();
  const [importing, setImporting] = useState(false);
  const projectFilter = params.get("project") || "",
    selectedId = location.pathname.split("/")[2];
  const selectedProject = projects.find((p) => p.id === projectFilter);
  const query = new URLSearchParams();
  for (const key of [
    "q",
    "record_type",
    "work_status",
    "outcome_status",
    "page",
    "deleted",
  ])
    if (params.get(key)) query.set(key, params.get(key)!);
  if (projectFilter === "unassigned") query.set("unassigned", "true");
  else if (projectFilter) query.set("project_id", projectFilter);
  query.set("page_size", "12");
  const list = useQuery({
    queryKey: ["records", query.toString()],
    queryFn: () => api<RecordPage>("/records?" + query),
  });
  function filter(key: string, value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value);
    else next.delete(key);
    if (key !== "page") next.delete("page");
    setParams(next);
  }
  const newPath =
    "/records/new" +
    (projectFilter && projectFilter !== "unassigned"
      ? "?project=" + projectFilter
      : "");
  return (
    <>
      <header className="page-header">
        <div>
          <div className="eyebrow">RESEARCH JOURNAL</div>
          <h1>
            科研记录<span className="edition">M1</span>
          </h1>
          <p>记录做过的尝试，也留住当时的判断。</p>
        </div>
        <div className="header-actions">
          <button onClick={() => setImporting(true)}>
            <Upload size={16} />
            导入文本
          </button>
          <Link className="primary" to={newPath}>
            <Plus size={17} />
            新建记录
          </Link>
        </div>
      </header>
      <section className="record-workspace">
        <div className="record-browser">
          <div className="browser-top">
            <label className="search-field">
              <Search size={17} />
              <input
                aria-label="搜索记录"
                placeholder="搜索标题、内容或判断"
                value={params.get("q") || ""}
                onChange={(e) => filter("q", e.target.value)}
              />
            </label>
            <div className="filters">
              <select
                aria-label="筛选项目"
                value={projectFilter}
                onChange={(e) => filter("project", e.target.value)}
              >
                <option value="">全部项目</option>
                <option value="unassigned">未归类记录</option>
                {projects.map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                    {p.archived ? "（已归档）" : ""}
                  </option>
                ))}
              </select>
              <select
                aria-label="筛选记录类型"
                value={params.get("record_type") || ""}
                onChange={(e) => filter("record_type", e.target.value)}
              >
                <option value="">全部类型</option>
                <Options values={recordTypes} />
              </select>
              <select
                aria-label="筛选工作状态"
                value={params.get("work_status") || ""}
                onChange={(e) => filter("work_status", e.target.value)}
              >
                <option value="">全部工作状态</option>
                <Options values={workStates} />
              </select>
              <select
                aria-label="筛选结果判断"
                value={params.get("outcome_status") || ""}
                onChange={(e) => filter("outcome_status", e.target.value)}
              >
                <option value="">全部结果判断</option>
                <Options values={outcomes} />
              </select>
            </div>
            <label className="checkbox">
              <input
                type="checkbox"
                checked={params.get("deleted") === "true"}
                onChange={(e) =>
                  filter("deleted", e.target.checked ? "true" : "")
                }
              />
              查看已删除记录
            </label>
            <div className="list-caption">
              <span>{selectedProject?.name || "探索记录"}</span>
              <span>{list.data?.total ?? "—"} 条</span>
            </div>
          </div>
          <ErrorNotice error={list.error} />
          {list.error && (
            <button onClick={() => list.refetch()}>重新加载</button>
          )}
          {list.isPending ? (
            <Loading />
          ) : list.data?.items.length ? (
            <div className="record-list">
              {list.data.items.map((item) => (
                <Link
                  className={
                    "record-item " + (selectedId === item.id ? "selected" : "")
                  }
                  key={item.id}
                  to={"/records/" + item.id + "?" + params.toString()}
                >
                  <div className="record-item-top">
                    <span className={"type-label type-" + item.record_type}>
                      {recordTypes[item.record_type]}
                    </span>
                    <span>{time(item.updated_at)}</span>
                  </div>
                  <h3>{item.title}</h3>
                  <p>
                    {item.fields.interpretation ||
                      item.body ||
                      "还没有补充正文"}
                  </p>
                  <div className="record-item-bottom">
                    <span>
                      {projects.find((p) => p.id === item.project_id)?.name ||
                        "未归类"}
                    </span>
                    <span>
                      {item.deleted_at
                        ? "已删除"
                        : workStates[item.work_status]}
                    </span>
                    <span>{outcomes[item.outcome_status]}</span>
                  </div>
                </Link>
              ))}
            </div>
          ) : (
            <div className="list-empty">
              <FileText size={24} />
              <p>这里还没有记录</p>
              <small>写下一句话，或调整筛选条件。</small>
            </div>
          )}
          {list.data && list.data.total > 12 && (
            <div className="pagination">
              <button
                disabled={list.data.page === 1}
                onClick={() => filter("page", String(list.data!.page - 1))}
              >
                上一页
              </button>
              <span>
                {list.data.page} / {Math.ceil(list.data.total / 12)}
              </span>
              <button
                disabled={list.data.page * 12 >= list.data.total}
                onClick={() => filter("page", String(list.data!.page + 1))}
              >
                下一页
              </button>
            </div>
          )}
        </div>
        <div className="record-content">
          {selectedId === "new" ? (
            <RecordEditor
              key={"new-" + projectFilter}
              projects={projects}
              initialProject={
                selectedProject && !selectedProject.archived
                  ? selectedProject.id
                  : null
              }
            />
          ) : selectedId ? (
            <RecordDetail
              key={selectedId}
              id={selectedId}
              projects={projects}
            />
          ) : (
            <div className="journal-welcome">
              <div className="welcome-mark">
                <BookOpen size={34} />
              </div>
              <span className="eyebrow">从一次探索开始</span>
              <h2>
                值得留下的，
                <br />
                不只有成功的结果。
              </h2>
              <p>
                一个尚未解开的疑问，一次改变方向的判断，
                <br />
                一段未达预期的尝试，都可以从这里记下。
              </p>
              <Link className="primary" to={newPath}>
                <Plus size={17} />
                写一条记录
              </Link>
              <div className="welcome-types">
                <span>论文阅读</span>
                <span>实验尝试</span>
                <span>AI 协作</span>
                <span>灵感疑问</span>
              </div>
            </div>
          )}
        </div>
      </section>
      {importing && (
        <ImportDialog
          projects={projects}
          initialProject={
            selectedProject && !selectedProject.archived
              ? selectedProject.id
              : ""
          }
          onClose={() => setImporting(false)}
        />
      )}
    </>
  );
}

function RecordEditor({
  projects,
  initialProject,
  record,
  onDone,
}: {
  projects: Project[];
  initialProject?: string | null;
  record?: RecordData;
  onDone?: () => void;
}) {
  const navigate = useNavigate(),
    client = useQueryClient();
  const [title, setTitle] = useState(record?.title || ""),
    [body, setBody] = useState(record?.body || "");
  const [project, setProject] = useState(
      record?.project_id || initialProject || "",
    ),
    [type, setType] = useState<RecordData["record_type"]>(
      record?.record_type || "note",
    );
  const [work, setWork] = useState<RecordData["work_status"]>(
      record?.work_status || "in_progress",
    ),
    [outcome, setOutcome] = useState<RecordData["outcome_status"]>(
      record?.outcome_status || "none",
    );
  const [fields, setFields] = useState<Fields>({
      ...emptyFields,
      ...record?.fields,
    }),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null);
  const request = useRef({ signature: "", id: crypto.randomUUID() });
  const [baseVersion] = useState(record?.version);
  useDirtyGuard(dirty);
  function change(action: () => void) {
    action();
    setDirty(true);
    setError(null);
  }
  async function save(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const payload = {
      title,
      body,
      project_id: project || null,
      record_type: type,
      work_status: work,
      outcome_status: outcome,
      fields,
    };
    const signature = JSON.stringify(payload);
    if (request.current.signature !== signature)
      request.current = { signature, id: crypto.randomUUID() };
    try {
      const value: RecordPatch | RecordCreate = record
        ? { ...payload, expected_version: baseVersion! }
        : { ...payload, request_id: request.current.id };
      const result = await api<RecordData>(
        record ? "/records/" + record.id : "/records",
        json(record ? "PATCH" : "POST", value),
      );
      setDirty(false);
      client.setQueryData(["record", result.id], result);
      await client.invalidateQueries({ queryKey: ["records"] });
      await client.invalidateQueries({ queryKey: ["revisions", result.id] });
      if (onDone) onDone();
      else setTimeout(() => navigate("/records/" + result.id), 0);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  const cancel = () => {
    if (dirty && !window.confirm("放弃未保存的修改？")) return;
    setDirty(false);
    if (onDone) onDone();
    else setTimeout(() => navigate("/records"), 0);
  };
  return (
    <form className="editor" onSubmit={save} data-dirty={dirty}>
      <div className="detail-heading">
        <span className="eyebrow">
          {record ? "继续整理这次探索" : "新的一次记录"}
        </span>
        <button type="button" className="text-button" onClick={cancel}>
          <ArrowLeft size={15} />
          返回
        </button>
      </div>
      <label>
        标题
        <input
          className="title-input"
          value={title}
          onChange={(e) => change(() => setTitle(e.target.value))}
          placeholder="这次想留下什么？"
          maxLength={200}
        />
      </label>
      <div className="form-grid">
        <label>
          记录类型
          <select
            value={type}
            onChange={(e) =>
              change(() => setType(e.target.value as typeof type))
            }
          >
            <Options values={recordTypes} />
          </select>
        </label>
        <label>
          所属项目
          <select
            value={project}
            onChange={(e) => change(() => setProject(e.target.value))}
          >
            <option value="">暂未归类</option>
            {projects
              .filter((p) => !p.archived)
              .map((p) => (
                <option key={p.id} value={p.id}>
                  {p.name}
                </option>
              ))}
          </select>
        </label>
      </div>
      <label>
        记录正文
        <textarea
          value={body}
          onChange={(e) => change(() => setBody(e.target.value))}
          rows={7}
          placeholder="可以先写一句话，之后再慢慢整理。支持 Markdown。"
          maxLength={1048576}
        />
      </label>
      <div className="form-grid">
        <label>
          工作状态
          <select
            value={work}
            onChange={(e) =>
              change(() => setWork(e.target.value as typeof work))
            }
          >
            <Options values={workStates} />
          </select>
        </label>
        <label>
          结果判断
          <select
            value={outcome}
            onChange={(e) =>
              change(() => setOutcome(e.target.value as typeof outcome))
            }
          >
            <Options values={outcomes} />
          </select>
        </label>
      </div>
      <div className="section-divider">
        <span>进一步整理</span>
        <small>选填，保留当时的想法</small>
      </div>
      {Object.entries(fieldLabels).map(([key, label]) => (
        <label key={key}>
          {label}
          <textarea
            value={fields[key as keyof Fields] || ""}
            onChange={(e) =>
              change(() => setFields({ ...fields, [key]: e.target.value }))
            }
            rows={2}
            maxLength={20000}
          />
        </label>
      ))}
      <ErrorNotice error={error} />
      {error instanceof ApiError && error.code === "version_conflict" && (
        <button
          type="button"
          onClick={() => {
            if (window.confirm("重新载入会放弃当前未保存输入，确定继续？")) {
              setDirty(false);
              client.invalidateQueries({ queryKey: ["record", record!.id] });
              onDone?.();
            }
          }}
        >
          重新载入最新版本
        </button>
      )}
      <footer className="editor-footer">
        <span>{dirty ? "有未保存的修改" : "至少填写标题或正文"}</span>
        <button
          className="primary"
          disabled={busy || !(title.trim() || body.trim())}
        >
          <Check size={16} />
          {busy ? "保存中…" : "保存记录"}
        </button>
      </footer>
    </form>
  );
}

function RecordDetail({ id, projects }: { id: string; projects: Project[] }) {
  const client = useQueryClient(),
    navigate = useNavigate();
  const record = useQuery({
    queryKey: ["record", id],
    queryFn: () => api<RecordData>("/records/" + id + "?include_deleted=true"),
  });
  const [editing, setEditing] = useState(false),
    [tab, setTab] = useState("record"),
    [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  if (record.isPending) return <Loading />;
  if (record.error || !record.data)
    return (
      <div className="detail">
        <ErrorNotice error={record.error} />
        <button onClick={() => record.refetch()}>重新载入</button>
      </div>
    );
  const r = record.data,
    archived = projects.find((p) => p.id === r.project_id)?.archived;
  if (editing)
    return (
      <RecordEditor
        record={r}
        projects={projects}
        onDone={() => {
          setEditing(false);
          record.refetch();
        }}
      />
    );
  async function removeOrRestore() {
    if (
      !window.confirm(
        r.deleted_at ? "恢复这条记录？" : "将记录移入已删除？之后可以恢复。",
      )
    )
      return;
    setBusy(true);
    setError(null);
    try {
      const next = await api<RecordData>(
        "/records/" + id + (r.deleted_at ? "/restore" : ""),
        json(r.deleted_at ? "POST" : "DELETE", { expected_version: r.version }),
      );
      client.setQueryData(["record", id], next);
      await client.invalidateQueries({ queryKey: ["records"] });
      navigate("/records" + (r.deleted_at ? "" : "?deleted=true"));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <article className="detail">
      <div className="detail-heading">
        <span className={"type-label type-" + r.record_type}>
          {recordTypes[r.record_type]}
        </span>
        <div className="inline-actions">
          {!r.deleted_at && (
            <button
              className="text-button"
              disabled={archived}
              onClick={() => {
                if (
                  document.querySelector('[data-dirty="true"]') &&
                  !window.confirm("放弃未保存的材料修改？")
                )
                  return;
                setEditing(true);
              }}
            >
              <Pencil size={15} />
              编辑
            </button>
          )}
          <button
            className="text-button"
            disabled={busy || archived}
            onClick={removeOrRestore}
          >
            {r.deleted_at ? <RotateCcw size={15} /> : <Trash2 size={15} />}{" "}
            {r.deleted_at ? "恢复记录" : "删除"}
          </button>
        </div>
      </div>
      <h2 className="record-title">{r.title}</h2>
      <div className="metadata">
        <span>
          <Folder size={14} />
          {projects.find((p) => p.id === r.project_id)?.name || "未归类"}
        </span>
        <span>
          <Clock size={14} />
          {time(r.updated_at)}
        </span>
        <span>第 {r.version} 版</span>
      </div>
      {archived && (
        <div className="notice">
          项目已归档。可在“管理项目与归档”中恢复后继续编辑。
        </div>
      )}
      {r.deleted_at && (
        <div className="notice">记录已删除，可恢复后继续查看来源和编辑。</div>
      )}
      <ErrorNotice error={error} />
      <div className="tabs" role="tablist" aria-label="记录详情">
        {[
          ["record", "探索记录"],
          ["sources", "原始材料"],
          ["history", "修改历史"],
        ].map(([key, label]) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            className={tab === key ? "active" : ""}
            disabled={key === "sources" && !!r.deleted_at}
            onClick={() => {
              if (
                document.querySelector('[data-dirty="true"]') &&
                !window.confirm("放弃未保存的材料修改？")
              )
                return;
              setTab(key);
            }}
          >
            {label}
          </button>
        ))}
      </div>
      {tab === "record" ? (
        <>
          <div className="state-pair">
            <div>
              <small>工作状态</small>
              <span>{workStates[r.work_status]}</span>
            </div>
            <div>
              <small>结果判断</small>
              <span>{outcomes[r.outcome_status]}</span>
            </div>
          </div>
          {r.body ? (
            <Markdown>{r.body}</Markdown>
          ) : (
            <p className="muted">还没有补充正文。</p>
          )}
          {Object.entries(fieldLabels).map(([key, label]) =>
            r.fields[key as keyof Fields] ? (
              <section className={"thought thought-" + key} key={key}>
                <h3>{label}</h3>
                <Markdown>{r.fields[key as keyof Fields]!}</Markdown>
              </section>
            ) : null,
          )}
        </>
      ) : tab === "sources" ? (
        <Sources record={r} readonly={!!archived} />
      ) : (
        <History id={id} />
      )}
    </article>
  );
}

function History({ id }: { id: string }) {
  const history = useQuery({
    queryKey: ["revisions", id],
    queryFn: () => api<Revision[]>("/records/" + id + "/revisions"),
  });
  if (history.isPending) return <Loading />;
  const labels: Record<string, string> = {
    create: "创建记录",
    edit: "编辑记录",
    delete: "删除记录",
    restore: "恢复记录",
    source_add: "追加来源",
    source_revise: "修订来源",
  };
  return (
    <div className="history">
      <ErrorNotice error={history.error} />
      {history.data?.map((revision) => {
        const snap = revision.snapshot as unknown as RecordData & {
          source_version_ids: string[];
        };
        return (
          <details key={revision.id}>
            <summary>
              <span className="version-dot">{revision.version}</span>
              <strong>
                {labels[revision.operation] || revision.operation}
              </strong>
              <time>{time(revision.created_at)}</time>
            </summary>
            <div className="history-body">
              <h3>{snap.title}</h3>
              <p className="small muted">
                {recordTypes[snap.record_type]} · {workStates[snap.work_status]}{" "}
                · {outcomes[snap.outcome_status]} ·{" "}
                {snap.deleted_at ? "已删除" : "正常"} · 项目{" "}
                {snap.project_id || "未归类"}
              </p>
              <Markdown>{snap.body}</Markdown>
              {Object.entries(fieldLabels).map(([key, label]) =>
                snap.fields[key as keyof Fields] ? (
                  <section key={key}>
                    <h4>{label}</h4>
                    <p className="preserve">
                      {snap.fields[key as keyof Fields]}
                    </p>
                  </section>
                ) : null,
              )}
              <details>
                <summary>
                  当时引用的来源版本（{snap.source_version_ids.length}）
                </summary>
                {snap.source_version_ids.map((v) => (
                  <code className="source-id" key={v}>
                    {v}
                  </code>
                ))}
              </details>
            </div>
          </details>
        );
      })}
    </div>
  );
}

function Sources({
  record,
  readonly,
}: {
  record: RecordData;
  readonly: boolean;
}) {
  const client = useQueryClient();
  const sources = useQuery({
    queryKey: ["sources", record.id, record.version],
    queryFn: () => api<Source[]>("/records/" + record.id + "/sources"),
  });
  const [mode, setMode] = useState<"text" | "link">("text"),
    [name, setName] = useState(""),
    [content, setContent] = useState(""),
    [revising, setRevising] = useState<Source | null>(null);
  const [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false),
    [dirty, setDirty] = useState(false);
  const baseVersion = useRef(record.version);
  useEffect(() => {
    if (!dirty && !revising) baseVersion.current = record.version;
  }, [record.version, dirty, revising]);
  useDirtyGuard(dirty);
  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const result = await api<RecordData>(
        revising
          ? "/sources/" + revising.id + "/versions"
          : "/records/" + record.id + "/sources",
        json(
          "POST",
          revising
            ? { expected_version: baseVersion.current, content }
            : {
                expected_version: baseVersion.current,
                kind: mode,
                name: name || (mode === "link" ? "参考链接" : "补充材料"),
                content,
              },
        ),
      );
      setDirty(false);
      setContent("");
      setName("");
      setRevising(null);
      client.setQueryData(["record", record.id], result);
      await client.invalidateQueries({ queryKey: ["revisions", record.id] });
      await client.invalidateQueries({ queryKey: ["records"] });
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  function revise(source: Source) {
    if (dirty && !window.confirm("放弃当前材料输入？")) return;
    setRevising(source);
    baseVersion.current = record.version;
    setContent(source.versions[0].content);
    setName(source.name);
    setMode(source.kind === "link" ? "link" : "text");
    setDirty(false);
  }
  return (
    <div className="sources">
      <p className="muted small">
        原始材料独立保存。修订会产生新版本，旧内容仍可回溯。
      </p>
      <ErrorNotice error={sources.error} />
      {sources.isPending ? (
        <Loading />
      ) : (
        sources.data?.map((source) => (
          <section className="source-card" key={source.id}>
            <header>
              <div>
                <FileText size={17} />
                <strong>{source.name}</strong>
                <small>v{source.current_version}</small>
              </div>
              {!readonly && (
                <button className="text-button" onClick={() => revise(source)}>
                  修订
                </button>
              )}
            </header>
            <details open>
              <summary>
                当前版本 · {time(source.versions[0].created_at)}
              </summary>
              {source.kind === "link" ? (
                <a
                  href={source.versions[0].content}
                  target="_blank"
                  rel="noreferrer"
                >
                  {source.versions[0].content}
                </a>
              ) : (
                <pre>{source.versions[0].content}</pre>
              )}
              <code className="source-id">{source.versions[0].id}</code>
            </details>
            {source.versions.slice(1).map((v) => (
              <details key={v.id}>
                <summary>
                  历史版本 {v.version} · {time(v.created_at)}
                </summary>
                <pre>{v.content}</pre>
                <code className="source-id">{v.id}</code>
              </details>
            ))}
          </section>
        ))
      )}
      {!readonly && (
        <form className="source-form" onSubmit={submit} data-dirty={dirty}>
          <h3>{revising ? "修订：" + revising.name : "追加来源材料"}</h3>
          {!revising && (
            <div className="form-grid">
              <label>
                材料类型
                <select
                  value={mode}
                  onChange={(e) => {
                    setMode(e.target.value as typeof mode);
                    setDirty(true);
                  }}
                >
                  <option value="text">文本材料</option>
                  <option value="link">参考链接</option>
                </select>
              </label>
              <label>
                名称
                <input
                  value={name}
                  maxLength={200}
                  onChange={(e) => {
                    setName(e.target.value);
                    setDirty(true);
                  }}
                  placeholder="可选"
                />
              </label>
            </div>
          )}
          <label>
            {mode === "link" ? "链接地址" : "材料内容"}
            <textarea
              value={content}
              rows={4}
              maxLength={1048576}
              required
              onChange={(e) => {
                setContent(e.target.value);
                setDirty(true);
              }}
            />
          </label>
          <ErrorNotice error={error} />
          <div className="inline-actions">
            <button className="primary" disabled={busy || !content.trim()}>
              {busy ? "保存中…" : revising ? "保存新版本" : "添加材料"}
            </button>
            {revising && (
              <button
                type="button"
                onClick={() => {
                  if (!dirty || window.confirm("放弃当前修订？")) {
                    setRevising(null);
                    setContent("");
                    setName("");
                    setDirty(false);
                  }
                }}
              >
                取消修订
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}

function ImportDialog({
  projects,
  initialProject,
  onClose,
}: {
  projects: Project[];
  initialProject: string;
  onClose: () => void;
}) {
  const [file, setFile] = useState<File | null>(null),
    [preview, setPreview] = useState(""),
    [project, setProject] = useState(initialProject),
    [type, setType] = useState("note");
  const [error, setError] = useState<unknown>(null),
    [busy, setBusy] = useState(false);
  const request = useRef({ signature: "", id: crypto.randomUUID() });
  const client = useQueryClient(),
    navigate = useNavigate();
  const close = () => {
    if (!file || window.confirm("关闭导入窗口？尚未导入的内容不会保存。"))
      onClose();
  };
  async function choose(value: File | undefined) {
    setFile(null);
    setPreview("");
    setError(null);
    if (!value) return;
    try {
      if (!/\.(md|txt)$/i.test(value.name))
        throw new Error("仅支持 .md 和 .txt 文件");
      if (value.size > 1048576) throw new Error("文件不能超过 1 MiB");
      const text = new TextDecoder("utf-8", { fatal: true }).decode(
        await value.arrayBuffer(),
      );
      if (!text.trim() || text.includes("\0"))
        throw new Error("文件为空或包含非文本内容");
      setPreview(text);
      setFile(value);
    } catch (e) {
      setError(
        e instanceof TypeError ? new Error("请使用 UTF-8 编码的文本文件") : e,
      );
    }
  }
  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    const signature = JSON.stringify([file.name, preview, project, type]);
    if (request.current.signature !== signature)
      request.current = { signature, id: crypto.randomUUID() };
    const data = new FormData();
    data.set("file", file);
    data.set("request_id", request.current.id);
    data.set("record_type", type);
    if (project) data.set("project_id", project);
    try {
      const r = await api<RecordData>("/records/import", {
        method: "POST",
        body: data,
      });
      await client.invalidateQueries({ queryKey: ["records"] });
      onClose();
      navigate("/records/" + r.id);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  return (
    <Dialog title="导入科研记录" onClose={close}>
      <form onSubmit={submit}>
        <p className="muted">一份文件对应一条记录，原始文本会单独保留。</p>
        <label className="file-input">
          选择 Markdown 或文本文件
          <input
            type="file"
            accept=".md,.txt"
            onChange={(e) => choose(e.target.files?.[0])}
          />
          <small>UTF-8 编码 · 最大 1 MiB</small>
        </label>
        <div className="form-grid">
          <label>
            记录类型
            <select value={type} onChange={(e) => setType(e.target.value)}>
              <Options values={recordTypes} />
            </select>
          </label>
          <label>
            所属项目
            <select
              value={project}
              onChange={(e) => setProject(e.target.value)}
            >
              <option value="">暂未归类</option>
              {projects
                .filter((p) => !p.archived)
                .map((p) => (
                  <option key={p.id} value={p.id}>
                    {p.name}
                  </option>
                ))}
            </select>
          </label>
        </div>
        {file && (
          <div className="import-preview">
            <strong>{file.name}</strong>
            <pre>{preview}</pre>
          </div>
        )}
        <ErrorNotice error={error} />
        <button className="primary" disabled={!file || busy}>
          <Upload size={16} />
          {busy ? "导入中…" : "确认导入"}
        </button>
      </form>
    </Dialog>
  );
}
