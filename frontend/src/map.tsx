import dagre from "@dagrejs/dagre";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Background,
  Controls,
  Handle,
  MarkerType,
  MiniMap,
  Position,
  ReactFlow,
  applyNodeChanges,
  type Node,
  type NodeChange,
  type NodeProps,
  type ReactFlowInstance,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { api, json, workStates, type Project } from "./api";
import { Dialog, ErrorNotice, Loading, Options, useDirtyGuard } from "./common";
import {
  itemStates,
  kinds,
  relationTypes,
  type Graph,
  type GraphNodeData,
  type Item,
  type ItemKind,
  type Layout,
  type Page,
} from "./m2";
import { ConflictNotice, ObjectPicker, Pagination } from "./m2-shared";
import {
  ItemDetail,
  ItemEditor,
  RelationEditor,
  RelationsPanel,
} from "./research";

function ResearchNode({ data }: NodeProps<Node<{ node: GraphNodeData }>>) {
  const n = data.node;
  return (
    <div
      className={"research-node " + n.kind + (n.external ? " external" : "")}
    >
      <Handle type="target" position={Position.Left} />
      <span className="node-kind">
        {kinds[n.kind]}
        {n.external ? " · 跨项目" : ""}
      </span>
      <strong>{n.title}</strong>
      <small>
        {n.project_name}
        {n.archived ? " · 已归档" : ""}
      </small>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}
const nodeTypes = { research: ResearchNode };
function arrange(graph: Graph) {
  const g = new dagre.graphlib.Graph();
  g.setGraph({ rankdir: "LR", nodesep: 32, ranksep: 80 });
  g.setDefaultEdgeLabel(() => ({}));
  for (const n of graph.nodes) g.setNode(n.id, { width: 228, height: 112 });
  for (const e of graph.edges) g.setEdge(e.source_id, e.target_id);
  dagre.layout(g);
  return Object.fromEntries(
    graph.nodes.map((n) => {
      const p = g.node(n.id);
      return [n.id, { x: p.x - 114, y: p.y - 56 }];
    }),
  );
}
function Canvas({
  graph,
  layout,
  scope,
  project,
  onSelect,
  onConnect,
  detailOpen,
}: {
  graph: Graph;
  layout: Layout;
  scope: string;
  project: string;
  detailOpen: boolean;
  onSelect: (n: GraphNodeData) => void;
  onConnect: (source: GraphNodeData, target: GraphNodeData) => void;
}) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [flow, setFlow] = useState<ReactFlowInstance<
    Node<{ node: GraphNodeData }>
  > | null>(null);
  const client = useQueryClient(),
    [nodes, setNodes] = useState<Node<{ node: GraphNodeData }>[]>([]),
    [dirty, setDirty] = useState(false),
    [busy, setBusy] = useState(false),
    [error, setError] = useState<unknown>(null),
    [baseVersion, setBaseVersion] = useState(layout.version);
  const selectionChanged = useCallback(
    ({ nodes }: { nodes: Node<{ node: GraphNodeData }>[] }) => {
      if (nodes[0]) onSelect(nodes[0].data.node);
    },
    [onSelect],
  );
  useEffect(() => {
    if (!flow) return;
    let frame = 0;
    const fit = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(() => {
        if (
          canvasRef.current?.isConnected &&
          canvasRef.current.clientWidth &&
          canvasRef.current.clientHeight
        )
          flow.fitView({ maxZoom: 1, padding: 0.2 });
      });
    };
    fit();
    window.addEventListener("resize", fit);
    return () => {
      window.removeEventListener("resize", fit);
      cancelAnimationFrame(frame);
    };
  }, [flow, detailOpen]);
  useDirtyGuard(dirty);
  useEffect(() => {
    const initial = arrange(graph);
    setNodes((current) =>
      graph.nodes.map((n) => ({
        id: n.id,
        type: "research",
        data: { node: n },
        position:
          current.find((old) => old.id === n.id)?.position ||
          layout.positions[n.id] ||
          initial[n.id],
      })),
    );
  }, [graph]);
  useEffect(() => {
    if (!dirty) {
      setBaseVersion(layout.version);
      setNodes((current) =>
        current.map((n) => ({
          ...n,
          position: layout.positions[n.id] || n.position,
        })),
      );
    }
  }, [layout, dirty]);
  const edges = useMemo(
    () =>
      graph.edges.map((e) => ({
        id: e.id,
        source: e.source_id,
        target: e.target_id,
        label:
          relationTypes[e.relation_type] + (e.needs_review ? " · 待复核" : ""),
        markerEnd: { type: MarkerType.ArrowClosed },
        style: { stroke: e.needs_review ? "#bc833b" : "#78978c" },
        data: { relation: e },
      })),
    [graph.edges],
  );
  async function save() {
    setBusy(true);
    setError(null);
    try {
      const result = await api<Layout>(
        "/graph/layout",
        json("PUT", {
          scope,
          project_id: project || null,
          expected_version: baseVersion,
          positions: Object.fromEntries(nodes.map((n) => [n.id, n.position])),
        }),
      );
      setBaseVersion(result.version);
      setDirty(false);
      client.setQueryData(["m2", "layout", scope, project], result);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }
  function changes(changes: NodeChange<Node<{ node: GraphNodeData }>>[]) {
    setNodes((n) => applyNodeChanges(changes, n));
    if (changes.some((c) => c.type === "position" && c.position))
      setDirty(true);
  }
  return (
    <div className="map-canvas-wrap" data-dirty={dirty}>
      <div className="canvas-toolbar">
        <span>{dirty ? "布局有未保存修改" : "拖动节点可调整布局"}</span>
        <button
          type="button"
          onClick={() => {
            const positions = arrange(graph);
            setNodes((n) =>
              n.map((v) => ({ ...v, position: positions[v.id] })),
            );
            setDirty(true);
          }}
        >
          自动整理
        </button>
        <button type="button" disabled={busy || !dirty} onClick={save}>
          保存布局
        </button>
      </div>
      <ConflictNotice
        error={error}
        onReload={() => {
          setDirty(false);
          setError(null);
          client.invalidateQueries({ queryKey: ["m2", "layout"] });
        }}
      />
      <div className="map-canvas" ref={canvasRef}>
        <ReactFlow
          onInit={setFlow}
          fitViewOptions={{ maxZoom: 1, padding: 0.2 }}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={changes}
          onNodeClick={(_, n) => onSelect(n.data.node)}
          onSelectionChange={selectionChanged}
          onConnect={(c) => {
            const a = graph.nodes.find((n) => n.id === c.source),
              b = graph.nodes.find((n) => n.id === c.target);
            if (a && b) onConnect(a, b);
          }}
          deleteKeyCode={null}
          fitView
          minZoom={0.15}
          maxZoom={2}
          ariaLabelConfig={{
            "controls.zoomIn.ariaLabel": "放大",
            "controls.zoomOut.ariaLabel": "缩小",
            "controls.fitView.ariaLabel": "适应视图",
            "node.a11yDescription.default": "按 Enter 选中节点，方向键移动。",
          }}
        >
          <Background color="#d9e2da" gap={24} />
          <Controls showInteractive={false} />
          <MiniMap pannable zoomable nodeColor="#9ab5a4" />
        </ReactFlow>
      </div>
    </div>
  );
}
export default function MapPage({ projects }: { projects: Project[] }) {
  const [params, setParams] = useSearchParams(),
    client = useQueryClient();
  const selectedProject = params.get("project") || "",
    scope =
      selectedProject === "unassigned"
        ? "unassigned"
        : selectedProject
          ? "project"
          : "all",
    project = scope === "project" ? selectedProject : "";
  const [q, setQ] = useState(""),
    [kind, setKind] = useState(""),
    [status, setStatus] = useState(""),
    [review, setReview] = useState(false),
    [archived, setArchived] = useState(false),
    [view, setView] = useState(() =>
      window.innerWidth < 900 ? "list" : "canvas",
    ),
    [page, setPage] = useState(1),
    [selected, setSelected] = useState<GraphNodeData | null>(null),
    [createKind, setCreateKind] = useState<ItemKind | null>(null),
    [relation, setRelation] = useState<{
      source?: GraphNodeData;
      target?: GraphNodeData;
    } | null>(null),
    [picker, setPicker] = useState(false),
    [catalog, setCatalog] = useState(false),
    [catalogPage, setCatalogPage] = useState(1),
    [linkError, setLinkError] = useState<unknown>(null),
    [deletedItem, setDeletedItem] = useState<string | null>(null),
    [origin, setOrigin] = useState<GraphNodeData | null>(null);
  const query = new URLSearchParams({
    scope,
    q,
    include_archived: String(archived),
  });
  if (project) query.set("project_id", project);
  if (kind) query.set("kind", kind);
  if (status) query.set("status", status);
  if (review) query.set("needs_review", "true");
  if (params.get("focus")) query.set("focus_node_id", params.get("focus")!);
  if (params.get("depth")) query.set("depth", params.get("depth")!);
  const graph = useQuery({
    queryKey: ["m2", "graph", query.toString()],
    queryFn: () => api<Graph>("/graph?" + query),
  });
  const layoutQuery = new URLSearchParams({ scope });
  if (project) layoutQuery.set("project_id", project);
  const layout = useQuery({
    queryKey: ["m2", "layout", scope, project],
    queryFn: () => api<Layout>("/graph/layout?" + layoutQuery),
  });
  const catalogQuery = useQuery({
    queryKey: ["m2", "deleted-items", catalogPage],
    queryFn: () =>
      api<Page<Item>>("/research-items?deleted=true&page=" + catalogPage),
    enabled: catalog,
  });
  useEffect(() => {
    const id = params.get("item");
    if (!id) return;
    api<Item>("/research-items/" + id)
      .then((i) =>
        setSelected({
          id: "research_item:" + i.id,
          object_id: i.id,
          object_kind: "research_item",
          kind: i.kind,
          title: i.title,
          project_id: i.project_id,
          project_name:
            projects.find((p) => p.id === i.project_id)?.name || "未归类",
          status: i.status,
          version: i.version,
          archived: i.archived,
          external: false,
        }),
      )
      .catch(setLinkError);
    const next = new URLSearchParams(params);
    next.delete("item");
    setParams(next, { replace: true });
  }, [params]);
  // Deep links from the record screen open a preselected relation without adding a node.
  useEffect(() => {
    const record = params.get("record");
    if (record) {
      api<{
        id: string;
        title: string;
        project_id: string | null;
        version: number;
        work_status: string;
      }>("/records/" + record)
        .then((r) =>
          setRelation({
            source: {
              id: "record:" + r.id,
              object_id: r.id,
              object_kind: "record",
              kind: "record",
              title: r.title,
              project_id: r.project_id,
              project_name:
                projects.find((p) => p.id === r.project_id)?.name || "未归类",
              status: r.work_status,
              version: r.version,
              archived: false,
              external: false,
            },
          }),
        )
        .catch(setLinkError);
      const next = new URLSearchParams(params);
      next.delete("record");
      setParams(next, { replace: true });
    }
  }, [params]);
  const selectedNow =
    graph.data?.nodes.find((n) => n.id === selected?.id) || selected;
  function mayChangeView() {
    return (
      !document.querySelector('.map-canvas-wrap[data-dirty="true"]') ||
      window.confirm("布局有未保存修改，确定切换吗？")
    );
  }
  function changeView(next: string) {
    if (view !== next && mayChangeView()) setView(next);
  }
  const select = useCallback((n: GraphNodeData) => {
    setSelected(n);
    setDeletedItem(null);
  }, []);
  function scopeChange(v: string) {
    setSelected(null);
    setPage(1);
    setParams(v ? { project: v } : {});
  }
  function focus(n: GraphNodeData) {
    const next = new URLSearchParams(params);
    next.set("focus", n.id);
    next.set(
      "depth",
      String(Math.min(3, Number(params.get("depth") || "0") + 1)),
    );
    setParams(next);
  }
  function afterItem(i: Item) {
    if (origin) {
      const node: GraphNodeData = {
        id: "research_item:" + i.id,
        object_id: i.id,
        object_kind: "research_item",
        kind: i.kind,
        title: i.title,
        project_id: i.project_id,
        project_name:
          projects.find((p) => p.id === i.project_id)?.name || "未归类",
        status: i.status,
        version: i.version,
        archived: i.archived,
        external: false,
      };
      setRelation({ source: node, target: origin });
      setOrigin(null);
    }
  }
  return (
    <section className="workspace-page">
      <ErrorNotice error={linkError} />
      <header className="workspace-header">
        <div>
          <span className="eyebrow">连接问题、尝试与下一次探索</span>
          <h1>研究地图</h1>
          <p>让分散的记录，逐渐形成自己的研究脉络。</p>
        </div>
        <div className="inline-actions">
          <Link to="/records/ai/new?kind=relation_suggestions">
            AI 建议关联
          </Link>
          <Link to="/records/ai">AI 收件箱</Link>
          <button onClick={() => setPicker(true)}>关联已有记录</button>
          <button className="primary" onClick={() => setCreateKind("question")}>
            新建研究问题
          </button>
        </div>
      </header>
      <div className="workspace-filters">
        <label>
          地图范围
          <select
            value={selectedProject}
            onChange={(e) => scopeChange(e.target.value)}
          >
            <option value="">个人总览</option>
            <option value="unassigned">未归类内容</option>
            {projects.map((p) => (
              <option key={p.id} value={p.id}>
                {p.name}
                {p.archived ? "（已归档）" : ""}
              </option>
            ))}
          </select>
        </label>
        <label>
          搜索研究内容
          <input
            value={q}
            onChange={(e) => {
              if (!mayChangeView()) return;
              setQ(e.target.value);
              setPage(1);
            }}
            placeholder="问题、发现、方向或记录"
          />
        </label>
        <label>
          节点类型
          <select
            value={kind}
            onChange={(e) => {
              if (!mayChangeView()) return;
              setKind(e.target.value);
              setStatus("");
              setPage(1);
            }}
          >
            <option value="">全部类型</option>
            <Options values={kinds} />
          </select>
        </label>
        <label>
          节点状态
          <select
            value={status}
            onChange={(e) => {
              if (mayChangeView()) {
                setStatus(e.target.value);
                setPage(1);
              }
            }}
          >
            <option value="">全部状态</option>
            <Options
              values={
                kind === "question" ||
                kind === "finding" ||
                kind === "direction"
                  ? itemStates[kind]
                  : kind === "record"
                    ? workStates
                    : {
                        ...workStates,
                        ...itemStates.question,
                        ...itemStates.finding,
                        ...itemStates.direction,
                      }
              }
            />
          </select>
        </label>
      </div>
      <div className="map-options">
        <div className="segmented">
          <button
            className={view === "canvas" ? "active" : ""}
            onClick={() => changeView("canvas")}
          >
            画布
          </button>
          <button
            className={view === "list" ? "active" : ""}
            onClick={() => changeView("list")}
          >
            列表
          </button>
        </div>
        <label className="check-row">
          <input
            type="checkbox"
            checked={review}
            onChange={(e) => {
              if (mayChangeView()) {
                setReview(e.target.checked);
                setPage(1);
              }
            }}
          />
          仅待复核关系
        </label>
        <label className="check-row">
          <input
            type="checkbox"
            checked={archived}
            onChange={(e) => {
              if (mayChangeView()) {
                setArchived(e.target.checked);
                setPage(1);
              }
            }}
          />
          包含归档项目
        </label>
        <button onClick={() => setCreateKind("finding")}>记录发现</button>
        <button onClick={() => setCreateKind("direction")}>提出方向</button>
        <button onClick={() => setCatalog(true)}>已删除内容</button>
      </div>
      {params.has("focus") && (
        <div className="notice">
          正在查看局部脉络{" "}
          <button
            onClick={() => {
              const next = new URLSearchParams(params);
              next.delete("focus");
              next.delete("depth");
              setParams(next);
            }}
          >
            返回完整视图
          </button>
        </div>
      )}
      <ErrorNotice error={graph.error || layout.error} />
      {graph.isPending || layout.isPending ? (
        <Loading />
      ) : (
        graph.data &&
        layout.data && (
          <>
            {graph.data.truncated && (
              <p className="notice">
                当前仅展示 {graph.data.nodes.length} / {graph.data.total_nodes}{" "}
                个节点。请缩小范围、搜索或聚焦邻居；全部内容可通过“浏览全部对象”分页查找。
              </p>
            )}
            <div
              className={
                "map-workspace" +
                (selectedNow || deletedItem ? " with-detail" : "")
              }
            >
              <div>
                {graph.data.nodes.length === 0 ? (
                  <div className="m2-empty">
                    <span className="empty-orbit">◎</span>
                    <h2>从一个真正想弄清的问题开始</h2>
                    <p>新建研究问题，再关联你的阅读、实验或思考记录。</p>
                    <button
                      className="primary"
                      onClick={() => setCreateKind("question")}
                    >
                      提出第一个问题
                    </button>
                  </div>
                ) : view === "canvas" ? (
                  <Canvas
                    key={scope + project}
                    graph={graph.data}
                    layout={layout.data}
                    scope={scope}
                    project={project}
                    onSelect={select}
                    detailOpen={!!(selectedNow || deletedItem)}
                    onConnect={(source, target) =>
                      setRelation({ source, target })
                    }
                  />
                ) : (
                  <>
                    <div className="node-list">
                      {graph.data.nodes
                        .slice((page - 1) * 20, page * 20)
                        .map((n) => (
                          <button
                            key={n.id}
                            className="node-row"
                            onClick={() => select(n)}
                          >
                            <span className={"kind-tag " + n.kind}>
                              {kinds[n.kind]}
                            </span>
                            <strong>{n.title}</strong>
                            <small>
                              {n.project_name}
                              {n.external ? " · 跨项目" : ""}
                            </small>
                          </button>
                        ))}
                    </div>
                    <Pagination
                      page={page}
                      total={graph.data.nodes.length}
                      onChange={setPage}
                    />
                  </>
                )}
                <details className="browse-all">
                  <summary>浏览全部对象（含尚未关联的记录）</summary>
                  <ObjectPicker
                    onPick={(n) => {
                      select(n);
                      if (!n.id.includes(":")) focus(n);
                      else setRelation({ source: n });
                    }}
                  />
                </details>
                {!selectedNow && (
                  <RelationsPanel
                    relationId={params.get("relation") || undefined}
                  />
                )}
              </div>
              {(selectedNow || deletedItem) && (
                <aside className="map-details">
                  {deletedItem ? (
                    <ItemDetail
                      id={deletedItem}
                      projects={projects}
                      onClose={() => setDeletedItem(null)}
                      onDirection={() => setCreateKind("direction")}
                    />
                  ) : (
                    selectedNow && (
                      <>
                        {selectedNow.object_kind === "research_item" ? (
                          <ItemDetail
                            key={selectedNow.object_id}
                            id={selectedNow.object_id}
                            projects={projects}
                            onClose={() => setSelected(null)}
                            onDirection={() => {
                              setOrigin(selectedNow);
                              setCreateKind("direction");
                            }}
                          />
                        ) : (
                          <article className="research-detail">
                            <div className="detail-heading">
                              <span className="kind-tag record">探索记录</span>
                              <button onClick={() => setSelected(null)}>
                                关闭详情
                              </button>
                            </div>
                            <h2>{selectedNow.title}</h2>
                            <p>{selectedNow.project_name}</p>
                            <Link to={"/records/" + selectedNow.object_id}>
                              查看完整记录、来源与历史
                            </Link>
                          </article>
                        )}
                        <div className="inline-actions">
                          <button
                            onClick={() => setRelation({ source: selectedNow })}
                            disabled={selectedNow.archived}
                          >
                            建立关联
                          </button>
                          {!selectedNow.id.includes(":") && (
                            <button onClick={() => focus(selectedNow)}>
                              展开邻居
                            </button>
                          )}
                        </div>
                        {!selectedNow.id.includes(":") && (
                          <RelationsPanel node={selectedNow} />
                        )}
                      </>
                    )
                  )}
                </aside>
              )}
            </div>
          </>
        )
      )}
      {createKind && (
        <ItemEditor
          kind={createKind}
          projects={projects}
          initialProject={project}
          onClose={() => setCreateKind(null)}
          onSaved={afterItem}
        />
      )}{" "}
      {relation && (
        <RelationEditor {...relation} onClose={() => setRelation(null)} />
      )}{" "}
      {picker && (
        <Dialog title="待关联科研记录" onClose={() => setPicker(false)}>
          <p className="muted">
            选择一条记录，再指定要关联的问题、发现或方向。
          </p>
          <ObjectPicker
            kind="record"
            unlinked
            onPick={(n) => {
              setPicker(false);
              setRelation({ source: n });
            }}
          />
        </Dialog>
      )}
      {catalog && (
        <Dialog title="已删除的研究内容" onClose={() => setCatalog(false)}>
          <ErrorNotice error={catalogQuery.error} />
          {catalogQuery.data?.items.map((i) => (
            <button
              className="node-row"
              key={i.id}
              onClick={() => {
                setSelected(null);
                setDeletedItem(i.id);
                setCatalog(false);
              }}
            >
              {kinds[i.kind]} · {i.title}
            </button>
          ))}
          {catalogQuery.data?.total === 0 && <p>没有已删除内容。</p>}
          <Pagination
            page={catalogPage}
            total={catalogQuery.data?.total || 0}
            onChange={setCatalogPage}
          />
        </Dialog>
      )}
    </section>
  );
}
