import { Link } from "react-router-dom";
import { projectData } from "../lib";

export function Component() {
  const d = projectData;
  return (
    <div>
      <h1 className="page-title">项目总览</h1>
      <p className="page-sub">{d.project.one_liner}</p>

      <div className="stat-row">
        <div className="stat"><div className="label">核心指标</div><div className="value">{d.counts.metric_rows}</div><div className="foot">记分卡 {d.counts.scorecard_status}</div></div>
        <div className="stat"><div className="label">F2 数据文件</div><div className="value">{d.counts.f2_csv_count}</div><div className="foot">{d.counts.f2_csv_bytes.toLocaleString()} 字节</div></div>
        <div className="stat"><div className="label">F3 任务</div><div className="value">{d.counts.tasks_total}</div><div className="foot">Qwen3 4B 轨迹批次</div></div>
        <div className="stat"><div className="label">工具 wrapper</div><div className="value">{d.counts.tools_total}</div><div className="foot">直接成功 {d.counts.tools_ok} · 存活 {d.counts.tools_alive}</div></div>
      </div>

      <section className="grid three" aria-label="三条研究线">
        {d.project.tracks.map((t) => (
          <article className="track-card" key={t.id}>
            <span className="track-tag">{t.id}</span>
            <h3>{t.name}</h3>
            <p>{t.what}</p>
            <p style={{ color: "var(--ink-soft)", fontSize: 13, margin: 0 }}><strong>底座</strong> · {t.base}</p>
            <p style={{ marginTop: 10, marginBottom: 0 }}><Link to={t.id === "F3" ? "/tools" : "/metrics"}>查看{t.id === "F3" ? "工具与任务" : "指标"} →</Link></p>
          </article>
        ))}
      </section>

      <section className="card" style={{ marginTop: 18 }}>
        <h2>术语表</h2>
        <p className="hint">专业名词按这里的口径理解，避免把展示值当成正确率。</p>
        <table>
          <thead><tr><th>术语</th><th>含义</th></tr></thead>
          <tbody>
            {d.terms.map((t) => (
              <tr key={t.code}><td><code>{t.code}</code></td><td>{t.plain}</td></tr>
            ))}
          </tbody>
        </table>
      </section>

      <section className="card">
        <h2>可行性五关</h2>
        <p className="hint">摘自 REPRO.md 复现手册；每关都有可检查产物。</p>
        <table>
          <thead><tr><th>#</th><th>关卡</th><th>状态</th><th>产物</th></tr></thead>
          <tbody>
            {d.gates.map((g) => (
              <tr key={g.no} className="gate-row">
                <td>{g.no}</td><td>{g.name}</td>
                <td className={g.state.startsWith("通过") ? "state-pass" : "state-wait"}>{g.state}</td>
                <td className="hash">{g.artifact}</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="callout">
          下一关是系统关：本页面展示的是真实产物生成的交付界面，端到端问答功能仍未完成。详情见<Link to="/boundaries">口径与边界</Link>。
        </div>
      </section>
    </div>
  );
}