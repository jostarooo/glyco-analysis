import { boundariesData } from "../lib";

export function Component() {
  const d = boundariesData;
  const pool = d.f1_pool;
  return (
    <div>
      <h1 className="page-title">口径与边界</h1>
      <p className="page-sub">这一页解释界面里每个数字"是什么、不是什么"，防止把轨迹指标读成成绩，或把服务问题读成数据结论。</p>

      <section className="card">
        <h2>记分卡边界</h2>
        {d.scorecard_boundaries.map((b, i) => (
          <div className="boundary" key={i}><strong>边界 {i + 1}</strong> · {b}</div>
        ))}
      </section>

      <section className="grid two">
        <div className="card">
          <h2>F1 评估池口径</h2>
          <table>
            <tbody>
              <tr><td>评估行</td><td className="num">{pool.evaluation_rows}</td></tr>
              <tr><td>实验阳性</td><td className="num">{pool.experimental_positive}</td></tr>
              <tr><td>未标注对照（不是阴性）</td><td className="num">{pool.unannotated_control}</td></tr>
              <tr><td>推断仅展示（不入指标）</td><td className="num">{pool.inferred_display_only}</td></tr>
              <tr><td>蛋白数</td><td className="num">{pool.proteins}</td></tr>
            </tbody>
          </table>
          <div className="callout">{d.f1_caveat}</div>
        </div>

        <div className="card">
          <h2>F2 实现边界</h2>
          <ul style={{ margin: "6px 0 0", paddingLeft: 20 }}>
            {d.f2_torchdrug_notes.map((n, i) => <li key={i} style={{ marginBottom: 8 }}>{n}</li>)}
          </ul>
          <h3>上游数据 URL 修正</h3>
          {d.f2_data_url_fixes.length > 0
            ? <p className="hint">{d.f2_data_url_fixes.join("、")} 存在上游 URL 错指，本地修正并记录为 PASS_URL_FIX。</p>
            : <p className="hint">无记录。</p>}
        </div>
      </section>

      <section className="card">
        <h2>F3 轨迹边界</h2>
        <div className="boundary"><strong>不是答案正确率</strong> · exact_sequence=19 是工具调用轨迹完全一致的题数；tasks_with_final_answer=39 只表示最终回答字段非空。grader = {d.f3_grader}。</div>
        <div className="boundary"><strong>不可比上游</strong> · 上游 Claude 18/50、Qwen3 15/50 由 GPT-4o 评分，本界面不生成任何与它们相减的差值。</div>
        <div className="boundary"><strong>8B 目录不是成绩</strong> · reports/w2_day2/f3_qwen3_8b_50_incomplete 是中断调试目录，不进入指标。</div>
      </section>

      <section className="card">
        <h2>工具复测边界</h2>
        {d.recheck_notes.map((n, i) => (
          <div className="boundary" key={i}><strong>{i === 0 ? "TLS 失败" : "空结果"} ≠ 结论</strong> · {n}</div>
        ))}
      </section>

      <section className="card">
        <h2>来源哈希与生成政策</h2>
        <p className="hint">每个数字都能指回仓库产物；sha256 由 build_web_data.py 写入，界面只读展示。</p>
        <table>
          <thead><tr><th>角色</th><th>路径</th><th>字节数</th><th>SHA256 摘要</th></tr></thead>
          <tbody>
            {d.sources.map((s) => (
              <tr key={s.role}>
                <td>{s.role}</td>
                <td className="hash">{s.path}</td>
                <td className="num">{s.byte_count.toLocaleString()}</td>
                <td className="hash">{s.sha256.slice(0, 16)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
        <div className="callout">
          生成政策 · delta_sign={d.policy.delta_sign} · f2_comparison={d.policy.f2_comparison} · f3_comparison={d.policy.f3_comparison} · timestamp_policy={d.policy.timestamp_policy}
        </div>
        <p className="hint">复现命令：REPRO.md「W3 可重算 F1/F2/F3 记分卡」与「web 数据契约」两节；生成器 <code>scripts/build_web_data.py --check</code> 在文档被改或输出过期时退出 1。</p>
      </section>
    </div>
  );
}