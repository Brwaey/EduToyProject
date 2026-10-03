import { LoaderCircle, X } from "lucide-react";
import { useEffect, useId, useRef, type ReactNode } from "react";
import ReactMarkdown, { defaultUrlTransform } from "react-markdown";

export function ErrorNotice({ error }: { error: unknown }) {
  return error ? (
    <div className="error" role="alert">
      {error instanceof Error ? error.message : String(error)}
    </div>
  ) : null;
}
export function Loading() {
  return (
    <div className="loading" role="status">
      <LoaderCircle className="spin" size={18} />
      正在载入…
    </div>
  );
}
export function Markdown({ children }: { children: string }) {
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
export function Options({ values }: { values: Record<string, string> }) {
  return Object.entries(values).map(([v, label]) => (
    <option key={v} value={v}>
      {label}
    </option>
  ));
}
export function useDirtyGuard(dirty: boolean) {
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
export function Dialog({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement>(null);
  const headingId = useId();
  useEffect(() => {
    ref.current?.showModal();
    return () => ref.current?.close();
  }, []);
  return (
    <dialog
      ref={ref}
      className="dialog"
      aria-labelledby={headingId}
      onCancel={(event) => {
        event.preventDefault();
        onClose();
      }}
    >
      <header>
        <h2 id={headingId}>{title}</h2>
        <button className="icon-button" onClick={onClose} aria-label="关闭">
          <X size={20} />
        </button>
      </header>
      {children}
    </dialog>
  );
}
