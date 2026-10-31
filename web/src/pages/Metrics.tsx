import { metricsData } from "../lib";
import type { MetricRow } from "../lib";

function metricDisplay(m: MetricRow) {
  const val = m.local.value;
  const fmt = (n: number) => (Math.abs(n) < 1 ? n.toFixed(4) : n.toString());
  const std = m.local.std != null ? ` ± ${m.local.std.toFixed(4)}` : "";
  const denom = m.local.denominator != null ? ` / ${m.local.denominator}` : "";
  const ref = m.reference ? `${fmt(m.reference.value)}${m.reference.std != null ? ` ± ${m.reference.std}` : ""}` : "不适用";
  const delta = m.comparison.delta_local_minus_reference;
  const cmp = m.comparison.kind === "comparable"
    ? `本地 − 参考 = ${delta != null ? (delta >= 0 ? "+" : "") + delta.toFixed(4) : "n/a"}`
    : "不可比 · 无差值";
  return { val: `${fmt(val)}${std}${denom}`, ref, cmp };
}

export function Component() {
  const d = metricsData;
  const f2 = d.f2.tasks;
  return (
    <div>
      <h1 className="page-title">核心指标</h1>
      <p className="page-sub">
        8 条指标全部来自 <code>reports/w3_day2/scorecard.json</code>，由 <code>scripts/build_w3_scorecard.py</code> 从固定源产物重算，状态 <strong>{d.scorecard_status}</strong>。
      </p>

      <section className="card">
        <h2>记分卡指标</h2>
        <p className="hint">F1/F2 与参考值可比，差值方向固定为本地减参考；F3 是轨迹指标，不生成差值。</p>
        <div style={{ overflowX: "auto" }}>
        <table>
          <thead><tr><th>赛道</th><th>指标</th><th>本地结果</th><th>参考</th><th>比较</th></tr></thead>
          <tbody>
            {d.metrics.map((m) => {
              const x = metricDisplay(m);
              return (
                <tr key={m.metric_id}>
                  <td><span className="track-tag">{m.track}</span></td>
                  <td><strong>{m.metric}</strong><div style={{ color: "var(--ink-soft)", fontSize: 12 }}>{m.subject}</div></td>
                  <td className="metric-cell num"><span className="val">{x.val}</span><div className="cmp">{m.comparison.scope_note ?? ""}</div></td>
                  <td className="num">{x.ref}</td>
                  <td>{m.comparison.kind === "comparable" ? <span className="chip ok">可比</span> : <span className="chip warn">不可比</span>}<div className="cmp">{x.cmp}</div></td>
                </tr>
              );
            })}
          </tbody>
        </table>
        </div>
      </section>

      <section className="grid two">
        <div className="card">
          <h2>F1 三方法对拍</h2>
          <p className="hint">评估池 130 行 = 82 实验阳性 + 48 未标注对照；71 行推断仅展示，不入指标。</p>
          <table>
            <thead><tr><th>方法</th><th className="num">MCC</th><th className="num">未标注保持率</th></tr></thead>
            <tbody>
              {d.f1_methods.map((m) => (
                <tr key={m.id}>
                  <td>{m.label}</td>
                  <td className="num">{m.mcc_defined ? m.mcc.toFixed(6) : "未定义"}</td>
                  <td className="num">{m.control_specificity.toFixed(4)}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="callout" style={{ marginTop: 12 }}>{d.f1_comparability_caveat}</div>
          <h3>作者检查点复算</h3>
          <p>全量 {d.f1_esm150_repro.row_count} 行，MCC {d.f1_esm150_repro.mcc.toFixed(6)}，与论文 {d.f1_esm150_repro.reference_mcc.toFixed(3)} 差 <strong>{d.f1_esm150_repro.delta >= 0 ? "+" : ""}{d.f1_esm150_repro.delta.toFixed(6)}</strong>。</p>
        </div>

        <div className="card">
          <h2>F2 GlycanML Table 3 复算</h2>
          <p className="hint">PyG 自实现，3 种子；TorchDrug 未安装，不是逐位克隆。</p>
          <table>
            <thead><tr><th>任务</th><th className="num">行数</th><th className="num">均值</th><th className="num">标准差</th></tr></thead>
            <tbody>
              <tr><td>免疫原性 AUPRC</td><td className="num">{f2.immunogenicity.rows}</td><td className="num">{f2.immunogenicity.aggregate.test_auprc.mean.toFixed(4)}</td><td className="num">{f2.immunogenicity.aggregate.test_auprc.std.toFixed(4)}</td></tr>
              <tr><td>糖基化 Macro-F1</td><td className="num">{f2.glycosylation.rows}</td><td className="num">{f2.glycosylation.aggregate.test_macro_f1.mean.toFixed(4)}</td><td className="num">{f2.glycosylation.aggregate.test_macro_f1.std.toFixed(4)}</td></tr>
            </tbody>
          </table>
          <h3>模型契约</h3>
          <p className="hint">embedding {d.f2.model.embedding.join("×")} · {d.f2.model.layers} 层 · hidden {d.f2.model.hidden_dim} · 关系通道 {d.f2.model.relation_channels} · pooling {d.f2.model.pooling.join("+")} · MLP {d.f2.model.mlp.join("→")}</p>
          <p className="hint">训练 {d.f2.training.optimizer} lr={d.f2.training.lr} · batch {d.f2.training.batch_size} · {d.f2.training.epochs} epochs · seeds 0/1/2 · scheduler {d.f2.training.scheduler} T_max={d.f2.training.T_max}</p>
        </div>
      </section>

      <section className="card">
        <h2>F3 Qwen3 4B 轨迹指标</h2>
        <p className="hint">{d.f3.model} · 50 题 · max_rounds={d.f3.max_rounds} · num_ctx={d.f3.num_ctx} · grader={d.f3.grader}</p>
        <div className="stat-row">
          <div className="stat"><div className="label">精确工具序列</div><div className="value">{d.f3.exact_sequence}<span style={{fontSize:14,color:"var(--ink-soft)"}}>/{d.f3.tasks_run}</span></div><div className="foot">轨迹完全一致，非答对题数</div></div>
          <div className="stat"><div className="label">全部期望工具已调用</div><div className="value">{d.f3.all_expected_called}<span style={{fontSize:14,color:"var(--ink-soft)"}}>/{d.f3.tasks_run}</span></div><div className="foot">不要求顺序一致</div></div>
          <div className="stat"><div className="label">任一期望工具已调用</div><div className="value">{d.f3.any_expected_called}<span style={{fontSize:14,color:"var(--ink-soft)"}}>/{d.f3.tasks_run}</span></div><div className="foot">至少调用一个</div></div>
          <div className="stat"><div className="label">存在最终回答</div><div className="value">{d.f3.tasks_with_final_answer}<span style={{fontSize:14,color:"var(--ink-soft)"}}>/{d.f3.tasks_run}</span></div><div className="foot">非空即计，不代表正确</div></div>
          <div className="stat"><div className="label">工具调用成功</div><div className="value">{d.f3.tool_call_successes}<span style={{fontSize:14,color:"var(--ink-soft)"}}>/{d.f3.tool_calls}</span></div><div className="foot">状态 ok 的调用次数</div></div>
        </div>
        <div className="boundary"><strong>口径提示</strong> 上游 Claude 18/50、Qwen3 15/50 由 GPT-4o 评分，本页数字是工具轨迹，不能与它们比较高低。</div>
      </section>

      <section className="card">
        <h2>验证计数</h2>
        <p className="hint">来自 scorecard.validations，生成器每轮强制校验。</p>
        <table>
          <thead><tr><th>项目</th><th className="num">值</th></tr></thead>
          <tbody>
            {Object.entries(d.validations).map(([k, v]) => (
              <tr key={k}><td>{k}</td><td className="num">{v}</td></tr>
            ))}
          </tbody>
        </table>
      </section>
    </div>
  );
}