import { useEffect, useRef, useState } from "react";
import {
  Activity,
  ArrowDownToLine,
  ArrowRight,
  ArrowUpRight,
  BarChart3,
  BookOpen,
  Check,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  CircleHelp,
  Clock3,
  Code2,
  Copy,
  Database,
  FileCode2,
  FlaskConical,
  Layers3,
  Loader2,
  Play,
  Plus,
  Search,
  Terminal,
  X,
  Zap,
} from "./icons";
import type { LucideIcon } from "lucide-react";
import "./App.css";

type Task = {
  id: string;
  title: string;
  category: string;
  description: string;
  metric: string;
  source: string;
  size: number;
};
type Config = {
  name: string;
  model: {
    backend: string;
    name: string;
    temperature: number;
    max_tokens: number;
    base_url?: string;
    api_key_env?: string;
  };
  tasks: string[];
  limit: number;
  seed: number;
  batch_size: number;
  prompts?: Record<string, string>;
};
type Run = {
  id: string;
  name: string;
  status: string;
  created_at: string;
  config: Config;
  completed: number;
  total: number;
  duration: number;
  error?: string;
  results: Record<string, { score: number; metric: string; count: number }>;
  manifest: Record<string, unknown>;
};
type Sample = {
  task: string;
  sample_id: string;
  prompt: string;
  prediction: string;
  reference: string;
  score: number;
  metric: string;
  latency_seconds: number;
};
type Saved = { id: string; name: string; config: Config };
const defaultConfig = (): Config => ({
  name: "My evaluation",
  model: {
    backend: "demo",
    name: "demo-baseline",
    temperature: 0,
    max_tokens: 64,
  },
  tasks: ["demo_reasoning", "demo_math", "demo_knowledge"],
  limit: 20,
  seed: 42,
  batch_size: 4,
});
const percent = (n: number) => `${(n * 100).toFixed(1)}%`;
const average = (r: Run) => {
  const scores = Object.values(r.results);
  return scores.length
    ? scores.reduce((a, x) => a + x.score, 0) / scores.length
    : null;
};
const date = (s: string) =>
  new Date(s).toLocaleDateString(undefined, { month: "short", day: "numeric" });
const icons: Record<string, LucideIcon> = {
  Reasoning: Layers3,
  Commonsense: Zap,
  Reading: BookOpen,
  Mathematics: FlaskConical,
  Demo: Terminal,
};
async function api<T>(url: string, data?: unknown): Promise<T> {
  const response = await fetch(
    `/api${url}`,
    data === undefined
      ? undefined
      : {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(data),
        },
  );
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(
      typeof body.detail === "string"
        ? body.detail
        : body.detail
          ? body.detail
              .map(
                (e: { loc: string[]; msg: string }) =>
                  `${e.loc.join(".")}: ${e.msg}`,
              )
              .join("; ")
          : `Request failed (${response.status})`,
    );
  }
  return response.json();
}
function download(name: string, value: unknown) {
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(value, null, 2)], { type: "application/json" }),
  );
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  a.click();
  URL.revokeObjectURL(url);
}
function Badge({ status }: { status: string }) {
  return (
    <span className={`badge ${status}`}>
      <span />
      {status[0].toUpperCase() + status.slice(1)}
    </span>
  );
}
function Modal({
  title,
  children,
  close,
  wide = false,
}: {
  title: string;
  children: React.ReactNode;
  close: () => void;
  wide?: boolean;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const closeRef = useRef(close);
  useEffect(() => {
    closeRef.current = close;
  }, [close]);
  useEffect(() => {
    const previous = document.activeElement as HTMLElement;
    ref.current?.focus();
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") closeRef.current();
      if (e.key === "Tab") {
        const items = Array.from(
          ref.current?.querySelectorAll<HTMLElement>(
            'button:not(:disabled), input, select, textarea, a[href], [tabindex="0"]',
          ) || [],
        );
        if (!items.length) {
          e.preventDefault();
          return;
        }
        const first = items[0],
          last = items[items.length - 1];
        if (
          e.shiftKey &&
          (document.activeElement === first ||
            document.activeElement === ref.current)
        ) {
          e.preventDefault();
          last.focus();
        } else if (!e.shiftKey && document.activeElement === last) {
          e.preventDefault();
          first.focus();
        }
      }
    };
    document.addEventListener("keydown", handler);
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", handler);
      document.body.style.overflow = overflow;
      previous?.focus();
    };
  }, []);
  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) close();
      }}
    >
      <div
        className={`modal ${wide ? "wide" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={title}
        ref={ref}
        tabIndex={-1}
      >
        <div className="modal-heading">
          <div>
            <span className="eyebrow">BENCHLAB WORKSPACE</span>
            <h2>{title}</h2>
          </div>
          <button
            className="icon-button"
            aria-label="Close dialog"
            onClick={close}
          >
            <X size={20} />
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

function App() {
  const [page, setPage] = useState("Overview");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [runs, setRuns] = useState<Run[]>([]);
  const [saved, setSaved] = useState<Saved[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [search, setSearch] = useState("");
  const [status, setStatus] = useState("All runs");
  const [category, setCategory] = useState("All tasks");
  const [builder, setBuilder] = useState(false);
  const [config, setConfig] = useState<Config>(defaultConfig);
  const [advanced, setAdvanced] = useState(false);
  const [configText, setConfigText] = useState("");
  const [busy, setBusy] = useState(false);
  const [formError, setFormError] = useState("");
  const [detail, setDetail] = useState<Run | null>(null);
  const [samples, setSamples] = useState<Sample[]>([]);
  const [sampleOffset, setSampleOffset] = useState(0);
  const [sampleLoading, setSampleLoading] = useState(false);
  const [detailTab, setDetailTab] = useState("Results");
  const [selected, setSelected] = useState<string[]>([]);
  const [compare, setCompare] = useState(false);
  const [docs, setDocs] = useState(false);

  async function refresh() {
    try {
      const [t, r, c] = await Promise.all([
        api<Task[]>("/tasks"),
        api<Run[]>("/runs"),
        api<Saved[]>("/configs"),
      ]);
      setTasks(t);
      setRuns(r);
      setSaved(c);
      setError("");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setLoading(false);
    }
  }
  useEffect(() => {
    void refresh();
    const timer = setInterval(() => void refresh(), 3000);
    return () => clearInterval(timer);
  }, []);
  useEffect(() => {
    if (notice) {
      const timer = setTimeout(() => setNotice(""), 4500);
      return () => clearTimeout(timer);
    }
  }, [notice]);
  useEffect(() => {
    setDetail((current) =>
      current ? runs.find((r) => r.id === current.id) || current : null,
    );
  }, [runs]);
  const detailId = detail?.id;
  const detailCompleted = detail?.completed;
  useEffect(() => {
    if (!detailId) return;
    let active = true;
    setSampleLoading(true);
    api<Sample[]>(`/runs/${detailId}/samples?limit=20&offset=${sampleOffset}`)
      .then((s) => {
        if (active) setSamples(s);
      })
      .catch((e) => {
        if (active) setError(e.message);
      })
      .finally(() => {
        if (active) setSampleLoading(false);
      });
    return () => {
      active = false;
    };
  }, [detailId, detailCompleted, sampleOffset]);

  function navigate(name: string) {
    setPage(name);
    setSearch("");
  }
  function openBuilder(value = defaultConfig()) {
    setConfig(value);
    setConfigText(JSON.stringify(value, null, 2));
    setAdvanced(false);
    setFormError("");
    setBuilder(true);
  }
  async function submit(action: "run" | "save" | "validate") {
    setBusy(true);
    setFormError("");
    try {
      const value: Config = advanced ? JSON.parse(configText) : config;
      await api("/configs/validate", value);
      if (action === "validate") {
        setNotice("Configuration is valid. Ready to evaluate.");
        return;
      }
      if (action === "save") {
        await api("/configs", value);
        setNotice("Configuration saved to your workspace.");
        setBuilder(false);
        navigate("Configurations");
      } else {
        const result = await api<{ id: string }>("/runs", value);
        setNotice(`Evaluation ${result.id} queued.`);
        setBuilder(false);
        navigate("Evaluations");
        setStatus("All runs");
      }
      await refresh();
    } catch (e) {
      setFormError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function exportRun(run: Run) {
    try {
      const all: Sample[] = [];
      for (let offset = 0; offset < run.completed; offset += 1000)
        all.push(
          ...(await api<Sample[]>(
            `/runs/${run.id}/samples?limit=1000&offset=${offset}`,
          )),
        );
      download(`${run.id}.json`, { ...run, samples: all });
      setNotice("Results and sample logs exported.");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  function openDetail(run: Run) {
    setDetail(run);
    setSampleOffset(0);
    setSamples([]);
    setDetailTab("Results");
  }
  const completed = runs.filter((r) => r.status === "completed");
  const active = runs.filter((r) => ["queued", "running"].includes(r.status));
  const latest = completed[0];
  const filteredRuns = runs.filter(
    (r) =>
      (status === "All runs" || r.status === status.toLowerCase()) &&
      `${r.name} ${r.config.model.name} ${r.id}`
        .toLowerCase()
        .includes(search.toLowerCase()),
  );
  const filteredTasks = tasks.filter(
    (t) =>
      (category === "All tasks" || t.category === category) &&
      `${t.title} ${t.category}`.toLowerCase().includes(search.toLowerCase()),
  );
  const available = tasks.filter((t) =>
    config.model.backend === "demo" ? t.category === "Demo" : true,
  );

  const taskCard = (task: Task) => {
    const Icon = icons[task.category] || Database;
    return (
      <button
        key={task.id}
        className="task-card"
        onClick={() =>
          openBuilder({
            ...defaultConfig(),
            name: `${task.title} evaluation`,
            model: {
              ...defaultConfig().model,
              backend: task.category === "Demo" ? "demo" : "hf",
              name:
                task.category === "Demo"
                  ? "demo-baseline"
                  : "Qwen/Qwen2.5-0.5B-Instruct",
            },
            tasks: [task.id],
          })
        }
      >
        <div className="task-card-top">
          <div className={`task-icon ${task.category.toLowerCase()}`}>
            <Icon size={21} strokeWidth={1.6} />
          </div>
          <ArrowUpRight size={17} />
        </div>
        <h3>{task.title}</h3>
        <p>{task.description}</p>
        <div className="task-card-footer">
          <span>{task.category}</span>
          <span>{task.size?.toLocaleString()} samples</span>
        </div>
      </button>
    );
  };
  const runTable = (compact = false) => (
    <div className="table-wrap">
      <table className="run-table">
        <thead>
          <tr>
            <th className="check-cell">
              <span className="mini-grid">▦</span>
            </th>
            <th>Evaluation / model</th>
            <th>Tasks</th>
            <th>Status</th>
            <th>
              Avg. score{" "}
              <span title="Unweighted mean of task scores; compare only matching protocols and tasks.">
                ⓘ
              </span>
            </th>
            <th>Created</th>
            <th>
              <span className="sr-only">Actions</span>
            </th>
          </tr>
        </thead>
        <tbody>
          {(compact ? filteredRuns.slice(0, 5) : filteredRuns).map((run) => (
            <tr key={run.id}>
              <td className="check-cell">
                <input
                  type="checkbox"
                  aria-label={`Select ${run.name}`}
                  checked={selected.includes(run.id)}
                  onChange={(e) =>
                    setSelected(
                      e.target.checked
                        ? [...selected, run.id]
                        : selected.filter((id) => id !== run.id),
                    )
                  }
                />
              </td>
              <td>
                <button className="run-title" onClick={() => openDetail(run)}>
                  {run.name}
                  <span>
                    <span
                      className={`backend-dot ${run.config.model.backend}`}
                    />
                    {run.config.model.name}
                  </span>
                </button>
              </td>
              <td>
                <span className="task-pill">
                  {run.config.tasks[0]?.replace("demo_", "")}
                </span>
                {run.config.tasks.length > 1 && (
                  <span className="extra-pill">
                    +{run.config.tasks.length - 1}
                  </span>
                )}
              </td>
              <td>
                <Badge status={run.status} />
              </td>
              <td className="score-cell">
                {average(run) !== null ? percent(average(run)!) : "—"}
              </td>
              <td className="muted">
                {date(run.created_at)}
                <small>
                  {new Date(run.created_at).toLocaleTimeString([], {
                    hour: "2-digit",
                    minute: "2-digit",
                  })}
                </small>
              </td>
              <td>
                <button
                  className="icon-button"
                  aria-label={`View ${run.name}`}
                  onClick={() => openDetail(run)}
                >
                  <ChevronRight size={18} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!filteredRuns.length && (
        <div className="empty-state">
          <FlaskConical size={30} />
          <h3>
            {search || status !== "All runs"
              ? "No matching evaluations"
              : "Your first evaluation is a click away"}
          </h3>
          <p>
            {search || status !== "All runs"
              ? "Try a different search or status."
              : "Run the bundled demo to explore scores, prompts, and sample logs."}
          </p>
          {!search && status === "All runs" && (
            <button className="primary" onClick={() => openBuilder()}>
              <Play size={15} /> Run a demo
            </button>
          )}
        </div>
      )}
    </div>
  );

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            navigate("Overview");
          }}
        >
          <span className="brand-mark">
            <BarChart3 size={23} />
          </span>
          benchlab<span className="brand-period">.</span>
        </a>
        <button className="workspace-switch" onClick={() => setDocs(true)}>
          <span className="workspace-avatar">B</span>
          <span>
            Personal workspace<small>Local environment</small>
          </span>
          <ChevronDown size={14} />
        </button>
        <span className="nav-label">WORKSPACE</span>
        <nav>
          {[
            { name: "Overview", icon: BarChart3 },
            { name: "Evaluations", icon: Activity },
            { name: "Task library", icon: Layers3 },
            { name: "Configurations", icon: FileCode2 },
          ].map(({ name, icon: Icon }) => (
            <button
              key={name}
              className={`nav-item ${page === name ? "active" : ""}`}
              onClick={() => navigate(name)}
            >
              <Icon size={18} strokeWidth={1.7} />
              {name}
              {name === "Evaluations" && (
                <span className="nav-count">{runs.length}</span>
              )}
            </button>
          ))}
        </nav>
        <div className="sidebar-bottom">
          <div className="terminal-card">
            <Terminal size={20} />
            <h4>Made for your workflow.</h4>
            <p>
              Same engine. Your terminal.
              <br />
              Run evaluations anywhere.
            </p>
            <button onClick={() => setDocs(true)}>
              Explore the CLI <ArrowUpRight size={14} />
            </button>
          </div>
          <button className="nav-item" onClick={() => setDocs(true)}>
            <BookOpen size={18} />
            Documentation
            <ArrowUpRight size={14} />
          </button>
          <div className="profile">
            <div className="profile-avatar">L</div>
            <div>
              Local developer<small>Personal account</small>
            </div>
            <span className="online-dot" />
          </div>
        </div>
      </aside>
      <div className="main-shell">
        <header className="topbar">
          <div className="breadcrumb">
            Workspace <ChevronRight size={14} />
            <strong>{page}</strong>
          </div>
          <div className="topbar-right">
            <span className="environment">
              <span className={error ? "offline-dot" : "online-dot"} />
              {error ? "Connection issue" : "Local environment"}
            </span>
            <span className="topbar-divider" />
            <button
              className="icon-button"
              aria-label="Help"
              onClick={() => setDocs(true)}
            >
              <CircleHelp size={19} />
            </button>
            <span className="top-avatar">L</span>
          </div>
        </header>
        <main>
          {error && (
            <div role="alert" className="error-banner">
              {error}
              <button onClick={() => void refresh()}>Retry connection</button>
            </div>
          )}
          <div className="page-heading">
            <div>
              <div className="eyebrow">
                {page === "Overview"
                  ? "MEASURE. UNDERSTAND. IMPROVE."
                  : "YOUR EVALUATION WORKSPACE"}
              </div>
              <h1>
                {page === "Overview" ? "A clearer view of your models." : page}
              </h1>
              <p>
                {page === "Overview"
                  ? "Repeatable evaluations. Meaningful results. All in one workspace."
                  : page === "Evaluations"
                    ? "Every experiment, with the details that make it reproducible."
                    : page === "Task library"
                      ? "Find the right challenge for your next model evaluation."
                      : "Save your setup. Make your next experiment a little easier."}
              </p>
            </div>
            <button className="primary" onClick={() => openBuilder()}>
              <Plus size={17} />
              {page === "Configurations"
                ? "New configuration"
                : "New evaluation"}
            </button>
          </div>
          {loading ? (
            <div className="loading-state">
              <Loader2 className="spin" />
              Connecting to your workspace…
            </div>
          ) : (
            <>
              {page === "Overview" && (
                <>
                  <section className="stats-grid">
                    <div className="stat">
                      <span>
                        Total evaluations <Activity size={16} />
                      </span>
                      <strong>{runs.length.toString().padStart(2, "0")}</strong>
                      <small>
                        <span className="green-text">
                          {completed.length} completed
                        </span>
                        <span>across your workspace</span>
                      </small>
                    </div>
                    <div className="stat">
                      <span>
                        Models evaluated <Layers3 size={16} />
                      </span>
                      <strong>
                        {new Set(
                          runs.map(
                            (r) =>
                              `${r.config.model.backend}:${r.config.model.name}`,
                          ),
                        ).size
                          .toString()
                          .padStart(2, "0")}
                      </strong>
                      <small>Local, accelerated, and API models</small>
                    </div>
                    <div className="stat">
                      <span>
                        Samples evaluated <Database size={16} />
                      </span>
                      <strong>
                        {runs
                          .reduce((n, r) => n + r.completed, 0)
                          .toLocaleString()}
                      </strong>
                      <small>Every prediction, scored and logged</small>
                    </div>
                    <div className="stat">
                      <span>
                        Active evaluations <Clock3 size={16} />
                      </span>
                      <strong>
                        {active.length.toString().padStart(2, "0")}
                        <span className="stat-live" />
                      </strong>
                      <small>
                        {active.length
                          ? "Working through your queue"
                          : "Ready when you are"}
                      </small>
                    </div>
                  </section>
                  <section className="feature-grid">
                    <div className="welcome-panel">
                      <div className="welcome-content">
                        <span className="mini-label">
                          <span /> BUILT FOR REPRODUCIBILITY
                        </span>
                        <h2>
                          Less setup.
                          <br />
                          More understanding.
                        </h2>
                        <p>
                          Choose a model, pick your tasks, and let
                          <br className="desktop-break" /> the results tell the
                          story.
                        </p>
                        <button onClick={() => openBuilder()}>
                          Run your first benchmark <ArrowRight size={16} />
                        </button>
                        <span className="offline-note">
                          <CheckCircle2 size={13} /> Try the demo. No API key
                          needed.
                        </span>
                      </div>
                      <div className="hero-art" aria-hidden="true">
                        <div className="orbit orbit-one" />
                        <div className="orbit orbit-two" />
                        <div className="art-dot dot-one" />
                        <div className="art-dot dot-two" />
                        <div className="floating-tag">
                          <Check size={12} /> evaluation complete
                        </div>
                        <div className="art-chart">
                          <span />
                          <span />
                          <span />
                          <span />
                          <span />
                          <span />
                        </div>
                        <div className="art-baseline" />
                        <span className="art-cross">+</span>
                      </div>
                    </div>
                    <div className="latest-panel">
                      <div className="section-header">
                        <h3>Latest snapshot</h3>
                        <span className="neutral-badge">
                          {latest?.config.model.backend === "demo"
                            ? "Demo baseline"
                            : "Task scores"}
                        </span>
                      </div>
                      {latest ? (
                        <>
                          <p>
                            {latest.name}
                            <span>{latest.config.model.name}</span>
                          </p>
                          <div className="score-bars">
                            {Object.entries(latest.results)
                              .slice(0, 3)
                              .map(([id, result], index) => (
                                <div className="score-row" key={id}>
                                  <span>
                                    {tasks.find((t) => t.id === id)?.title ||
                                      id}
                                  </span>
                                  <strong>{percent(result.score)}</strong>
                                  <div className="bar-track">
                                    <div
                                      className={`bar-fill bar-${index}`}
                                      style={{ width: percent(result.score) }}
                                    />
                                  </div>
                                </div>
                              ))}
                          </div>
                          <button
                            className="text-link"
                            onClick={() => openDetail(latest)}
                          >
                            Explore results <ArrowRight size={14} />
                          </button>
                        </>
                      ) : (
                        <div className="snapshot-empty">
                          <BarChart3 size={30} />
                          <p>
                            Your next insight lives here.
                            <span>
                              Complete an evaluation to see task scores.
                            </span>
                          </p>
                        </div>
                      )}
                    </div>
                  </section>
                </>
              )}
              {(page === "Overview" || page === "Evaluations") && (
                <section className="runs-section">
                  <div className="section-header">
                    <div className="inline-title">
                      <h2>
                        {page === "Overview"
                          ? "Recent evaluations"
                          : "Evaluation history"}
                      </h2>
                      <span className="count-badge">{runs.length}</span>
                    </div>
                    <div className="section-actions">
                      {selected.length > 0 && (
                        <button
                          className="secondary small"
                          onClick={() => setCompare(true)}
                        >
                          Compare ({selected.length})
                        </button>
                      )}
                      <button
                        className="secondary small"
                        onClick={() => {
                          download("benchlab-runs.json", runs);
                          setNotice(
                            "Run summaries exported. Open a run to export its sample logs.",
                          );
                        }}
                      >
                        <ArrowDownToLine size={14} />
                        Export
                      </button>
                      {page === "Overview" && (
                        <button
                          className="text-link"
                          onClick={() => navigate("Evaluations")}
                        >
                          View all <ArrowRight size={14} />
                        </button>
                      )}
                    </div>
                  </div>
                  <div className="runs-box">
                    <div className="table-toolbar">
                      <div className="tabs">
                        {["All runs", "Completed", "Running", "Failed"].map(
                          (tab) => (
                            <button
                              key={tab}
                              className={status === tab ? "active" : ""}
                              onClick={() => setStatus(tab)}
                            >
                              {tab}
                              {tab === "All runs" && <span>{runs.length}</span>}
                            </button>
                          ),
                        )}
                      </div>
                      <label className="search">
                        <Search size={15} />
                        <input
                          aria-label="Search evaluations"
                          placeholder="Search evaluations…"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </label>
                    </div>
                    {runTable(page === "Overview")}
                    <div className="table-footer">
                      <span>
                        Showing{" "}
                        {Math.min(
                          filteredRuns.length,
                          page === "Overview" ? 5 : 200,
                        )}{" "}
                        of {runs.length} evaluations
                      </span>
                      <span>
                        <span className="online-dot" /> Automatically saved to
                        your workspace
                      </span>
                    </div>
                  </div>
                </section>
              )}
              {(page === "Overview" || page === "Task library") && (
                <section className="tasks-section">
                  <div className="section-header">
                    <div>
                      <h2>
                        {page === "Overview"
                          ? "Good questions make better models."
                          : "Explore tasks"}
                      </h2>
                      <p>
                        {page === "Overview"
                          ? "Start with a benchmark from the task library."
                          : `${tasks.length} tasks · Standard datasets and offline demo samplers`}
                      </p>
                    </div>
                    {page === "Overview" && (
                      <button
                        className="text-link"
                        onClick={() => navigate("Task library")}
                      >
                        Explore task library <ArrowRight size={14} />
                      </button>
                    )}
                  </div>
                  {page === "Task library" && (
                    <div className="library-toolbar">
                      <div className="tabs">
                        {[
                          "All tasks",
                          "Reasoning",
                          "Commonsense",
                          "Reading",
                          "Mathematics",
                          "Demo",
                        ].map((c) => (
                          <button
                            key={c}
                            className={category === c ? "active" : ""}
                            onClick={() => setCategory(c)}
                          >
                            {c}
                          </button>
                        ))}
                      </div>
                      <label className="search">
                        <Search size={15} />
                        <input
                          aria-label="Search tasks"
                          placeholder="Search tasks…"
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                        />
                      </label>
                    </div>
                  )}
                  <div className="task-grid">
                    {(page === "Overview"
                      ? tasks.filter((t) =>
                          [
                            "arc_challenge",
                            "hellaswag",
                            "boolq",
                            "gsm8k",
                          ].includes(t.id),
                        )
                      : filteredTasks
                    ).map(taskCard)}
                  </div>
                  {page === "Task library" && !filteredTasks.length && (
                    <div className="empty-state">
                      No tasks match your search.
                    </div>
                  )}
                  <div className="library-note">
                    <CircleHelp size={14} /> Benchmarks use generated answers.
                    Dataset downloads and optional backend packages are
                    required.{" "}
                    <button onClick={() => setDocs(true)}>
                      Learn more <ArrowUpRight size={12} />
                    </button>
                  </div>
                </section>
              )}
              {page === "Configurations" && (
                <div className="config-grid">
                  {saved.map((item) => (
                    <div className="saved-card" key={item.id}>
                      <FileCode2 size={24} />
                      <h3>{item.name}</h3>
                      <p>{item.config.model.name}</p>
                      <div className="config-meta">
                        <span>{item.config.tasks.length} tasks</span>
                        <span>Seed {item.config.seed}</span>
                        <span>{item.config.limit} sample limit</span>
                      </div>
                      <div className="saved-actions">
                        <button
                          className="secondary"
                          onClick={() =>
                            download(`${item.id}.json`, item.config)
                          }
                        >
                          <ArrowDownToLine size={15} />
                          Download
                        </button>
                        <button
                          className="primary"
                          onClick={() => openBuilder(item.config)}
                        >
                          Use configuration <ArrowRight size={14} />
                        </button>
                      </div>
                    </div>
                  ))}
                  <button
                    className="new-config-card"
                    onClick={() => openBuilder()}
                  >
                    <Plus size={25} />
                    <h3>Create a reusable setup</h3>
                    <p>
                      Pick your tasks and model once.
                      <br />
                      Run it again whenever you need.
                    </p>
                  </button>
                </div>
              )}
            </>
          )}
          <footer className="page-footer">
            <span>
              <span className="footer-mark">▥</span> A little more confidence in
              every model.
            </span>
            <span>
              BenchLab <span className="version">v0.1.0</span>
              <span className="footer-sep">/</span>
              <button onClick={() => setDocs(true)}>
                Documentation <ArrowUpRight size={12} />
              </button>
            </span>
          </footer>
        </main>
      </div>
      {notice && (
        <div className="toast" role="status">
          <CheckCircle2 size={18} />
          {notice}
          <button
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            <X size={14} />
          </button>
        </div>
      )}
      {builder && (
        <Modal title="Set up an evaluation" close={() => setBuilder(false)}>
          <div className="builder-intro">
            One configuration. Repeatable results.
          </div>
          <div className="builder-tabs">
            <button
              className={!advanced ? "active" : ""}
              onClick={async () => {
                if (advanced) {
                  try {
                    const result = await api<{ config: Config }>(
                      "/configs/validate",
                      JSON.parse(configText),
                    );
                    setConfig(result.config);
                    setAdvanced(false);
                    setFormError("");
                  } catch (e) {
                    setFormError((e as Error).message);
                  }
                }
              }}
            >
              Guided setup
            </button>
            <button
              className={advanced ? "active" : ""}
              onClick={() => {
                setConfigText(JSON.stringify(config, null, 2));
                setAdvanced(true);
              }}
            >
              <Code2 size={14} />
              JSON configuration
            </button>
          </div>
          {advanced ? (
            <label className="field">
              Configuration
              <textarea
                className="code-editor"
                value={configText}
                onChange={(e) => setConfigText(e.target.value)}
                spellCheck={false}
              />
              <small>
                Use JSON here; the CLI also accepts YAML. Add custom prompt
                overrides with the “prompts” mapping.
              </small>
            </label>
          ) : (
            <div className="form-body">
              <label className="field">
                Evaluation name
                <input
                  value={config.name}
                  onChange={(e) =>
                    setConfig({ ...config, name: e.target.value })
                  }
                />
              </label>
              <div className="form-row">
                <label className="field">
                  Model backend
                  <select
                    value={config.model.backend}
                    onChange={(e) => {
                      const backend = e.target.value;
                      setConfig({
                        ...config,
                        model: {
                          ...config.model,
                          backend,
                          name:
                            backend === "demo"
                              ? "demo-baseline"
                              : backend === "api"
                                ? "your-model-id"
                                : "Qwen/Qwen2.5-0.5B-Instruct",
                        },
                        tasks:
                          backend === "demo"
                            ? defaultConfig().tasks
                            : ["arc_easy"],
                      });
                    }}
                  >
                    <option value="demo">Demo · no setup required</option>
                    <option value="hf">Hugging Face · local</option>
                    <option value="vllm">vLLM · accelerated</option>
                    <option value="api">API · compatible endpoint</option>
                  </select>
                </label>
                <label className="field">
                  Model identifier
                  <input
                    value={config.model.name}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        model: { ...config.model, name: e.target.value },
                      })
                    }
                  />
                </label>
              </div>
              {config.model.backend === "api" && (
                <div className="form-row">
                  <label className="field">
                    Base URL
                    <input
                      placeholder="https://api.openai.com/v1"
                      value={config.model.base_url || ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          model: { ...config.model, base_url: e.target.value },
                        })
                      }
                    />
                  </label>
                  <label className="field">
                    API key environment variable
                    <input
                      placeholder="OPENAI_API_KEY"
                      value={config.model.api_key_env || ""}
                      onChange={(e) =>
                        setConfig({
                          ...config,
                          model: {
                            ...config.model,
                            api_key_env: e.target.value,
                          },
                        })
                      }
                    />
                    <small>Set the secret on the API server.</small>
                  </label>
                </div>
              )}
              <div className="info-note">
                <CircleHelp size={15} />
                {config.model.backend === "demo"
                  ? "A deterministic toy baseline on synthetic tasks. No model download or API key. These scores are for demonstration."
                  : config.model.backend === "api"
                    ? "Calls the server-side endpoint. Provider usage may incur charges."
                    : `Requires the ${config.model.backend} and benchmarks extras. The first run downloads model weights and task datasets.`}
              </div>
              <div className="field">
                Select tasks{" "}
                <span className="field-hint">
                  {config.tasks.length} selected
                </span>
                <div className="task-checks">
                  {available.map((t) => (
                    <label
                      key={t.id}
                      className={config.tasks.includes(t.id) ? "selected" : ""}
                    >
                      <input
                        type="checkbox"
                        checked={config.tasks.includes(t.id)}
                        onChange={(e) =>
                          setConfig({
                            ...config,
                            tasks: e.target.checked
                              ? [...config.tasks, t.id]
                              : config.tasks.filter((id) => id !== t.id),
                          })
                        }
                      />
                      <span>
                        {t.title}
                        <small>
                          {t.metric.replaceAll("_", " ")} · {t.size} samples
                        </small>
                      </span>
                    </label>
                  ))}
                </div>
              </div>
              <div className="form-row three">
                <label className="field">
                  Samples per task
                  <input
                    type="number"
                    min={1}
                    max={100000}
                    value={config.limit}
                    onChange={(e) =>
                      setConfig({ ...config, limit: Number(e.target.value) })
                    }
                  />
                </label>
                <label className="field">
                  Random seed
                  <input
                    type="number"
                    min={0}
                    value={config.seed}
                    onChange={(e) =>
                      setConfig({ ...config, seed: Number(e.target.value) })
                    }
                  />
                </label>
                <label className="field">
                  Batch size
                  <input
                    type="number"
                    min={1}
                    max={128}
                    value={config.batch_size}
                    onChange={(e) =>
                      setConfig({
                        ...config,
                        batch_size: Number(e.target.value),
                      })
                    }
                  />
                </label>
              </div>
            </div>
          )}
          {formError && (
            <div className="form-error" role="alert">
              {formError}
            </div>
          )}
          <div className="modal-actions">
            <button
              className="text-link"
              disabled={busy}
              onClick={() => void submit("validate")}
            >
              <CheckCircle2 size={15} />
              Validate config
            </button>
            <div>
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void submit("save")}
              >
                Save configuration
              </button>
              <button
                className="primary"
                disabled={busy}
                onClick={() => void submit("run")}
              >
                {busy ? (
                  <Loader2 size={15} className="spin" />
                ) : (
                  <Play size={15} />
                )}
                Run evaluation
              </button>
            </div>
          </div>
        </Modal>
      )}
      {detail && (
        <Modal title={detail.name} wide close={() => setDetail(null)}>
          <div className="detail-meta">
            <Badge status={detail.status} />
            <span>{detail.config.model.name}</span>
            <code>{detail.id}</code>
            <button
              className="secondary small"
              onClick={() => void exportRun(detail)}
            >
              <ArrowDownToLine size={14} />
              Export JSON
            </button>
          </div>
          {detail.config.model.backend === "demo" && (
            <div className="info-note">
              <Terminal size={15} />
              Demo results use synthetic tasks and a toy baseline; they do not
              measure a language model.
            </div>
          )}
          {detail.error && <div className="form-error">{detail.error}</div>}
          <div className="run-progress">
            <span>
              {detail.completed} / {detail.total} samples
            </span>
            <span>
              {detail.duration.toFixed(2)} seconds · Seed {detail.config.seed}
            </span>
            <div className="bar-track">
              <div
                className="bar-fill"
                style={{
                  width: `${detail.total ? (detail.completed / detail.total) * 100 : 0}%`,
                }}
              />
            </div>
          </div>
          <div className="tabs detail-tabs">
            {["Results", "Sample logs", "Configuration", "Manifest"].map(
              (tab) => (
                <button
                  key={tab}
                  className={detailTab === tab ? "active" : ""}
                  onClick={() => setDetailTab(tab)}
                >
                  {tab}
                </button>
              ),
            )}
          </div>
          {detailTab === "Results" && (
            <div className="result-grid">
              {Object.entries(detail.results).map(([id, r]) => (
                <div className="result-card" key={id}>
                  <span>{tasks.find((t) => t.id === id)?.title || id}</span>
                  <strong>{percent(r.score)}</strong>
                  <small>
                    {r.metric} · {r.count} samples
                  </small>
                </div>
              ))}
              {!Object.keys(detail.results).length && (
                <div className="empty-state">
                  {detail.status === "failed"
                    ? "No completed task scores. Check the error above."
                    : "Task scores appear as each task completes."}
                </div>
              )}
            </div>
          )}
          {detailTab === "Sample logs" && (
            <div className="sample-logs">
              {sampleLoading ? (
                <p>Loading samples…</p>
              ) : (
                samples.map((s) => (
                  <details key={`${s.task}-${s.sample_id}`}>
                    <summary>
                      <span
                        className={
                          s.score === 1 ? "sample-pass" : "sample-fail"
                        }
                      >
                        {percent(s.score)}
                      </span>
                      <span>
                        {s.task} <small>Sample {s.sample_id}</small>
                      </span>
                      <ChevronDown size={15} />
                    </summary>
                    <div className="sample-content">
                      <label>Prompt</label>
                      <pre>{s.prompt}</pre>
                      <div className="sample-answer">
                        <div>
                          <label>Model response</label>
                          <pre>{s.prediction || "(empty)"}</pre>
                        </div>
                        <div>
                          <label>Reference answer</label>
                          <pre>{s.reference}</pre>
                        </div>
                      </div>
                      <small>
                        {s.metric} · {s.latency_seconds.toFixed(3)}s per sample
                        (batch average)
                      </small>
                    </div>
                  </details>
                ))
              )}
              <div className="pagination">
                <button
                  className="secondary small"
                  disabled={sampleOffset === 0}
                  onClick={() =>
                    setSampleOffset(Math.max(0, sampleOffset - 20))
                  }
                >
                  Previous
                </button>
                <span>
                  {detail.completed ? sampleOffset + 1 : 0}–
                  {Math.min(sampleOffset + 20, detail.completed)} of{" "}
                  {detail.completed}
                </span>
                <button
                  className="secondary small"
                  disabled={sampleOffset + 20 >= detail.completed}
                  onClick={() => setSampleOffset(sampleOffset + 20)}
                >
                  Next
                </button>
              </div>
            </div>
          )}
          {(detailTab === "Configuration" || detailTab === "Manifest") && (
            <pre className="json-view">
              {JSON.stringify(
                detailTab === "Configuration" ? detail.config : detail.manifest,
                null,
                2,
              )}
            </pre>
          )}
          <div className="modal-actions">
            <span className="muted">
              Saved {date(detail.created_at)} · Generated-answer protocol
            </span>
            <button
              className="secondary"
              onClick={() => {
                const cfg = detail.config;
                setDetail(null);
                openBuilder(cfg);
              }}
            >
              <Copy size={14} />
              Reuse configuration
            </button>
          </div>
        </Modal>
      )}
      {compare && (
        <Modal title="Compare evaluations" wide close={() => setCompare(false)}>
          <div className="info-note">
            Compare scores only when task data, prompt hashes, and evaluation
            protocols match. Open each run’s manifest to verify.
          </div>
          <div className="table-wrap">
            <table className="comparison-table">
              <thead>
                <tr>
                  <th>Task / run</th>
                  {runs
                    .filter((r) => selected.includes(r.id))
                    .map((r) => (
                      <th key={r.id}>
                        {r.name}
                        <small>{r.config.model.name}</small>
                      </th>
                    ))}
                </tr>
              </thead>
              <tbody>
                {[
                  ...new Set(
                    runs
                      .filter((r) => selected.includes(r.id))
                      .flatMap((r) => r.config.tasks),
                  ),
                ].map((id) => (
                  <tr key={id}>
                    <td>{tasks.find((t) => t.id === id)?.title || id}</td>
                    {runs
                      .filter((r) => selected.includes(r.id))
                      .map((r) => (
                        <td key={r.id}>
                          {r.results[id] ? percent(r.results[id].score) : "—"}
                        </td>
                      ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Modal>
      )}
      {docs && (
        <Modal
          title="Your workspace, your workflow."
          close={() => setDocs(false)}
        >
          <div className="docs-body">
            <p>
              BenchLab runs the same evaluation engine from the CLI and this
              workspace. Configurations, scores, and sample logs live in a local
              SQLite database.
            </p>
            <h3>Start in your terminal</h3>
            <pre>
              pip install -e '.[dev]'{"\n"}benchlab tasks{"\n"}benchlab validate
              examples/demo.yaml{"\n"}benchlab run --config examples/demo.yaml
              {"\n"}benchlab results
            </pre>
            <h3>Choose your backend</h3>
            <p>
              <b>Demo</b> is an offline toy baseline. Install{" "}
              <code>[hf,benchmarks]</code> for Hugging Face or{" "}
              <code>[vllm,benchmarks]</code> for accelerated inference. The API
              adapter uses a compatible chat completion endpoint with a
              server-side environment key.
            </p>
            <h3>Make it your own</h3>
            <p>
              Add YAML task definitions and JSONL samples with{" "}
              <code>--task-dir</code>. Customize prompts in your config and add
              metrics through the <code>benchlab.metrics</code> Python
              entry-point group.
            </p>
            <h3>Understand your scores</h3>
            <p>
              Tasks use generated answers, not likelihood-based rankings. Demo
              samplers are synthetic; standard benchmark datasets download on
              demand. Seeds and hashes help audit runs, but provider and GPU
              behavior can vary.
            </p>
            <a
              className="text-link"
              href="/api/docs"
              target="_blank"
              rel="noreferrer"
            >
              API reference <ArrowUpRight size={14} />
            </a>
          </div>
        </Modal>
      )}
    </div>
  );
}
export default App;
