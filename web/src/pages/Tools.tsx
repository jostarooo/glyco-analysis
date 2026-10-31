import { useMemo, useState } from "react";
import { toolsData } from "../lib";

const FEAS_LABEL: Record<string, string> = {
  current_tools_direct: "当前工具可直接完成",
  needs_replacement_tool: "需要替代工具",
  service_failure: "服务失败",
};

export function Component() {
  const d = toolsData;
  const [toolQuery, setToolQuery] = useState("");
  const [taskFilter, setTaskFilter] = useState<string>("all");
  const [taskQuery, setTaskQuery] = useState("");

  const filteredTools = useMemo(() => {
    const q = toolQuery.trim().toLowerCase();
    if (!q) return d.tools;
    return d.tools.filter((t) => (t.tool + " " + t.group + " " + t.class).toLowerCase().includes(q));
  }, [toolQuery, d.tools]);

  const filteredTasks = useMemo(() => {
    const q = taskQuery.trim().toLowerCase();
    return d.tasks.filter((t) => {
      const cat = t.feasibility?.revised_category ?? "unknown";
      if (taskFilter !== "all" && cat !== taskFilter) return false;
      if (!q) return true;
      return (t.task_id + " " + t.site + " " + t.tools + " " + t.question).toLowerCase().includes(q);
    });
  }, [taskFilter, taskQuery, d.tasks]);

  const counts = d.recheck ? d.recheck : null;
  const w2 = d.tool_summary.class_counts;
  const countBy = (key: "revised_category" | "original_category") => {
    const acc: Record<string, number> = {};
    for (const t of d.tasks) {
      const v = t.feasibility?.[key] ?? "unknown";
      acc[v] = (acc[v] ?? 0) + 1;
    }
    return acc;
  };
  const revisedCounts = countBy("revised_category");
  const originalCounts = countBy("original_category");
  return (
    <div>
      <h1 className="page-title">工具与任务</h1>
      <p className="page-sub">{d.snapshot_note} 本页只读展示，不执行任何工具。</p>

      <div className="stat-row">
        <div className="stat"><div className="label">W2 盘点 wrapper</div><div className="value">{d.tool_summary.total_tools}</div><div className="foot">直接 ok {d.tool_summary.directly_ok} · 存活 {d.tool_summary.service_alive}（{ (d.tool_summary.service_alive_rate * 100).toFixed(2) }%）</div></div>
        <div className="stat"><div className="label">W3 复测阻断工具</div><div className="value">{counts?.total_blocked_tools ?? "-"}</div><div className="foot">服务可达 {counts?.service_reachable ?? "-"} · 默认传输 ok {counts?.default_transport_ok ?? "-"}</div></div>
        <div className="stat"><div className="label">任务分类（最新）</div><div className="value">{revisedCounts.current_tools_direct ?? 0}/{revisedCounts.needs_replacement_tool ?? 0}/{revisedCounts.service_failure ?? 0}</div><div className="foot">直接 / 替代 / 失败，合计 {d.tasks.length}</div></div>
        <div className="stat"><div className="label">W2 原始口径</div><div className="value">{originalCounts.current_tools_direct ?? 0}/{originalCounts.needs_replacement_tool ?? 0}/{originalCounts.service_failure ?? 0}</div><div className="foot">历史证据保留，不改写</div></div>
      </div>

      <section className="card">
        <h2>工具可行性复测摘要</h2>
        <div className="grid two">
          <div>
            <h3>W2 盘点状态</h3>
            <table>
              <thead><tr><th>状态</th><th className="num">工具数</th></tr></thead>
              <tbody>
                {Object.entries(w2).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>)}
              </tbody>
            </table>
          </div>
          <div>
            <h3>W3 任务级复测</h3>
            <table>
              <thead><tr><th>复测类别</th><th className="num">工具数</th></tr></thead>
              <tbody>
                {counts && Object.entries(counts.recheck_class_counts).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>)}
              </tbody>
            </table>
            <h3>任务适配</h3>
            <table>
              <thead><tr><th>task_fit</th><th className="num">工具数</th></tr></thead>
              <tbody>
                {counts && Object.entries(counts.task_fit_counts).map(([k, v]) => <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>)}
              </tbody>
            </table>
          </div>
        </div>
        {counts && counts.persistent_blockers.length > 0 && (
          <div>
            <h3>持续阻断工具</h3>
            <table>
              <thead><tr><th>工具</th><th>类别</th><th>根因</th></tr></thead>
              <tbody>
                {counts.persistent_blockers.map((b) => (
                  <tr key={b.tool}><td><code>{b.tool}</code></td><td><span className="chip bad">{b.class}</span></td><td style={{ maxWidth: 520, wordBreak: "break-word" }}>{b.root_cause}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="card">
        <h2>{d.tools.length} 个工具 wrapper</h2>
        <div className="controls">
          <input className="search" placeholder="搜索工具名、分组或状态…" value={toolQuery} onChange={(e) => setToolQuery(e.target.value)} />
          <span className="chip">{filteredTools.length} / {d.tools.length}</span>
        </div>
        <div style={{ maxHeight: 420, overflow: "auto", border: "1px solid var(--line)", borderRadius: 10 }}>
          <table>
            <thead style={{ position: "sticky", top: 0, background: "var(--card)" }}><tr><th>分组</th><th>工具</th><th>方法</th><th className="num">HTTP</th><th>状态</th></tr></thead>
            <tbody>
              {filteredTools.map((t) => (
                <tr key={t.tool}>
                  <td>{t.group}</td>
                  <td><code>{t.tool}</code></td>
                  <td>{t.method}</td>
                  <td className="num">{t.http_status}</td>
                  <td><span className={"chip " + (t.class === "ok" ? "ok" : t.class === "unreachable" ? "bad" : "warn")}>{t.class}</span></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section className="card">
        <h2>{d.tasks.length} 道任务可行性</h2>
        <div className="controls">
          <div className="filters">
            <button className={taskFilter === "all" ? "on" : ""} onClick={() => setTaskFilter("all")}>全部</button>
            <button className={taskFilter === "current_tools_direct" ? "on" : ""} onClick={() => setTaskFilter("current_tools_direct")}>可直接完成</button>
            <button className={taskFilter === "needs_replacement_tool" ? "on" : ""} onClick={() => setTaskFilter("needs_replacement_tool")}>需要替代</button>
            <button className={taskFilter === "service_failure" ? "on" : ""} onClick={() => setTaskFilter("service_failure")}>服务失败</button>
          </div>
          <input className="search" placeholder="搜索题号、站点或问题…" value={taskQuery} onChange={(e) => setTaskQuery(e.target.value)} />
        </div>
        <div style={{ maxHeight: 520, overflow: "auto", border: "1px solid var(--line)", borderRadius: 10 }}>
          <table>
            <thead style={{ position: "sticky", top: 0, background: "var(--card)" }}><tr><th>题号</th><th>站点</th><th>步数</th><th>期望工具</th><th>最新分类</th><th>W2 原始</th><th>阻断工具 / 原因</th></tr></thead>
            <tbody>
              {filteredTasks.map((t) => {
                const f = t.feasibility ?? { revised_category: "unknown", original_category: "unknown", blocking_tools: "", w3_classes: "", decision_reason: "" };
                return (
                  <tr key={t.task_id}>
                    <td>{t.task_id}</td>
                    <td>{t.site}</td>
                    <td>{t.steps}</td>
                    <td style={{ maxWidth: 220 }}><code>{t.tools}</code></td>
                    <td><span className={"chip " + (f.revised_category === "current_tools_direct" ? "ok" : f.revised_category === "service_failure" ? "bad" : "warn")}>{FEAS_LABEL[f.revised_category] ?? f.revised_category}</span></td>
                    <td>{FEAS_LABEL[f.original_category] ?? f.original_category}</td>
                    <td style={{ maxWidth: 320 }}>
                      {f.blocking_tools ? <code>{f.blocking_tools}</code> : <span style={{ color: "var(--ink-soft)" }}>无阻断</span>}
                      {f.w3_classes ? <div style={{ fontSize: 12, color: "var(--ink-soft)" }}>{f.w3_classes}</div> : null}
                      {f.decision_reason ? <div style={{ fontSize: 12, color: "var(--ink-soft)", marginTop: 3 }}>{f.decision_reason}</div> : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}