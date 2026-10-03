import { useQueryClient } from "@tanstack/react-query";
import { Archive, Plus, RotateCcw } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api, json, type Project } from "./api";

import { Dialog, ErrorNotice } from "./common";
export function ProjectManager({
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
