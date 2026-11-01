(function () {
  "use strict";

  const story = JSON.parse(document.getElementById("story-data").textContent);
  const slides = story.weeks;
  const deck = document.getElementById("deck");
  const slideRoot = document.getElementById("slide-root");
  const chapterNav = document.getElementById("chapter-nav");
  const milestoneRoot = document.getElementById("milestones");
  const stageRange = document.getElementById("stage-range");
  const stageChapter = document.getElementById("stage-chapter");
  const sourceLine = document.getElementById("slide-source");
  const progressFill = document.getElementById("progress-fill");
  const slideCounter = document.getElementById("slide-counter");
  const notesPanel = document.getElementById("speaker-notes");
  const notesCopy = document.getElementById("notes-copy");

  const params = new URLSearchParams(window.location.search);
  const requestedSlide = Number.parseInt(params.get("slide") || "1", 10);
  let cursor = clamp(Number.isFinite(requestedSlide) ? requestedSlide - 1 : 0, 0, slides.length - 1);
  let notesVisible = params.get("notes") === "1";
  let touchStartX = null;

  const demoState = {
    f1RowId: story.demos.f1.default_row_id,
    f1RuleDraft: "",
    f1RuleResult: null,
    f2TaskId: story.demos.f2.tasks[0].id,
    f2Seed: story.demos.f2.tasks[0].per_seed[0].seed,
    f3TaskId: story.demos.f3.default_task_id,
    f3Filter: "all",
    f3Step: 1,
  };

  const milestoneLabels = ["W1", "W2", "W2证据", "W2交付"];

  function clamp(value, minimum, maximum) {
    return Math.max(minimum, Math.min(maximum, value));
  }

  function escapeHtml(value) {
    return String(value)
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;")
      .replaceAll("'", "&#039;");
  }

  function fmt(value) {
    if (typeof value !== "number") {
      return escapeHtml(value);
    }
    return Number.isInteger(value) ? String(value) : String(value);
  }

  function fixed(value, digits) {
    return Number(value).toFixed(digits);
  }

  function signed(value) {
    const numeric = Number(value);
    return `${numeric >= 0 ? "+" : ""}${String(numeric)}`;
  }

  function signedFixed(value, digits) {
    const numeric = Number(value);
    return `${numeric >= 0 ? "+" : ""}${numeric.toFixed(digits)}`;
  }

  function binaryLabel(value) {
    if (value === 1 || value === true) {
      return "阳性";
    }
    if (value === 0 || value === false) {
      return "阴性";
    }
    return "无标签";
  }

  function evidenceLabel(value) {
    const labels = {
      experimental_positive: "实验阳性",
      inferred_positive: "推断阳性",
      unannotated_control: "未标注对照",
    };
    return labels[value] || value;
  }

  function reviewLabel(value) {
    const labels = {
      SUPPORTED_EXPERIMENTAL_POSITIVE: "有独立实验证据",
      MISSED_ANNOTATION_CANDIDATE: "漏注释候选",
      NO_INDEPENDENT_EVIDENCE_FOUND: "未找到独立证据",
    };
    return labels[value] || value;
  }

  function disagreementLabel(value) {
    const labels = {
      all_agree: "三种判断一致",
      both_models_call_unannotated_control_positive: "两个模型都把关照位点判为阳性",
      both_models_oppose_experimental_positive: "两个模型都反对实验阳性",
      display_only_inferred: "推断阳性，只展示",
      esm150_calls_unannotated_control_positive: "150M 把关照位点判为阳性",
      esm150_opposes_experimental_positive: "150M 反对实验阳性",
      esm35_opposes_experimental_positive: "35M 反对实验阳性",
    };
    return labels[value] || value;
  }

  function feasibilityLabel(value) {
    const labels = {
      current_tools_direct: "当前工具可直接完成",
      needs_replacement_tool: "需要替代工具",
      service_failure: "服务失败",
    };
    return labels[value] || value;
  }

  function sourceBasename(source) {
    if (!source || !source.path) {
      return "";
    }
    return String(source.path).split("/").pop();
  }

  function progressWidth(value) {
    const numeric = Number(value);
    return Math.max(0, Math.min(100, numeric * 100));
  }

  function byCode(code) {
    return story.tracks.find((track) => track.code === code);
  }

  function sourceText(slide) {
    return slide.sources.map((source) => source.label).join(" / ");
  }

  function workPurpose(slide) {
    if (!slide.work && !slide.purpose) {
      return "";
    }
    return `
      <div class="work-purpose">
        <div class="wp-item">
          <span class="wp-label">做了什么</span>
          <p>${escapeHtml(slide.work)}</p>
        </div>
        <div class="wp-item purpose">
          <span class="wp-label">有什么作用</span>
          <p>${escapeHtml(slide.purpose)}</p>
        </div>
      </div>
    `;
  }

  function renderCover(slide) {
    return `
      <section class="slide cover-slide">
        <p class="cover-kicker">${escapeHtml(slide.range)}</p>
        <h1 class="cover-title">${escapeHtml(slide.title)}</h1>
        <p class="cover-thesis">${escapeHtml(slide.thesis)}</p>
        <div class="cover-rule"></div>
        <div class="cover-meta">
          <div class="commit-card">
            <span class="commit-label">数据生成基线 / FULL GIT HEAD</span>
            <code class="commit-value">${escapeHtml(story.meta.head_commit)}</code>
          </div>
          <div class="proof-card">
            <span class="commit-label">视频开场仍在终端现场证明</span>
            <code>git -C D:\\wbworkspace\\glyco-analysis rev-parse HEAD</code>
          </div>
        </div>
        <p class="cover-foot">${escapeHtml(slide.purpose)}</p>
      </section>
    `;
  }

  function renderW1(slide) {
    const track = byCode("F1");
    const methods = track.methods;
    const benchmark = slide.benchmark;
    const counts = slide.review_counts;
    return `
      <section class="slide">
        <div>
          <p class="eyebrow">W01 / TRUSTWORTHY BASELINE</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        <div class="stat-band">
          <div class="stat">
            <span class="stat-value">${fmt(benchmark.evaluation_rows)}</span>
            <span class="stat-label">评估池总行数</span>
          </div>
          <div class="stat">
            <span class="stat-value">${fmt(benchmark.experimental_positive)}</span>
            <span class="stat-label">实验阳性</span>
          </div>
          <div class="stat">
            <span class="stat-value">${fmt(benchmark.unannotated_control)}</span>
            <span class="stat-label">未标注对照，不是阴性</span>
          </div>
          <div class="stat">
            <span class="stat-value">${fmt(benchmark.inferred_display_only)}</span>
            <span class="stat-label">推断阳性，只展示不入指标</span>
          </div>
        </div>
        <div class="review-strip">
          <div class="review-strip-head">人工复核 ${fmt(counts.reviewed_total)} 个分歧位点，按证据强弱分开记录</div>
          <div class="review-count">
            <strong>${fmt(counts.supported)}</strong>
            <span>有独立<br>实验证据</span>
          </div>
          <div class="review-count">
            <strong>${fmt(counts.missed)}</strong>
            <span>漏注释<br>候选</span>
          </div>
          <div class="review-count">
            <strong>${fmt(counts.no_evidence)}</strong>
            <span>未找到<br>独立证据</span>
          </div>
        </div>
        <div class="method-row">
          ${methods.map((method) => `
            <div class="method">
              <span class="method-name">${escapeHtml(method.label)}</span>
              <strong class="method-score">${fixed(method.mcc, 6)}</strong>
              <span class="method-note">${escapeHtml(method.note)}</span>
            </div>
          `).join("")}
        </div>
        <div class="author-callout">
          <span>150M 作者检查点独立复算</span>
          <strong>MCC ${fixed(track.headline.value, 12)}</strong>
        </div>
      </section>
    `;
  }

  function selectedF1Candidate() {
    return story.demos.f1.candidates.find(
      (candidate) => candidate.row_id === demoState.f1RowId
    ) || story.demos.f1.candidates[0];
  }

  function renderF1Method(name, verdict, probability, note) {
    const numericVerdict = verdict === 1 || verdict === true;
    return `
      <article class="f1-method ${numericVerdict ? "positive" : "negative"}">
        <span class="f1-method-name">${escapeHtml(name)}</span>
        <strong class="f1-method-call">${binaryLabel(verdict)}</strong>
        <span class="f1-method-prob">${
          typeof probability === "number" ? `概率 ${fixed(probability, 4)}` : "离散标签"
        }</span>
        <span class="f1-method-note">${escapeHtml(note)}</span>
      </article>
    `;
  }

  function renderF1MatrixCall(name, verdict) {
    const numericVerdict = verdict === 1 || verdict === true;
    return `<span class="f1-matrix-call ${numericVerdict ? "positive" : "negative"}">${escapeHtml(name)} <strong>${binaryLabel(verdict)}</strong></span>`;
  }

  function sequonMatches(rawSequence) {
    const sequence = String(rawSequence || "").toUpperCase().replace(/[^A-Z]/g, "");
    const matches = [];
    for (let index = 0; index <= sequence.length - 3; index += 1) {
      const first = sequence[index];
      const middle = sequence[index + 1];
      const third = sequence[index + 2];
      if (first === "N" && middle !== "P" && (third === "S" || third === "T")) {
        matches.push({
          position: index + 1,
          motif: sequence.slice(index, index + 3),
          context: `${sequence.slice(Math.max(0, index - 4), index)}[${sequence.slice(index, index + 3)}]${sequence.slice(index + 3, index + 7)}`,
        });
      }
    }
    return { sequence, matches };
  }

  function renderF1RuleResult() {
    if (!demoState.f1RuleResult) {
      return `
        <div class="rule-empty">
          <strong>等待运行</strong>
          <span>输入短肽后点击“运行 Sequon 规则”。</span>
        </div>
      `;
    }
    const result = demoState.f1RuleResult;
    return `
      <div class="rule-result" data-rule-match-count="${result.matches.length}">
        <div class="rule-sequence">${escapeHtml(result.sequence || "空序列")}</div>
        ${
          result.matches.length
            ? `<div class="rule-match-list">${result.matches.map((match) => `
                <div class="rule-match">
                  <span class="rule-position">#${match.position}</span>
                  <strong>${escapeHtml(match.motif)}</strong>
                  <code>${escapeHtml(match.context)}</code>
                </div>
              `).join("")}</div>`
            : `<p class="rule-no-match">没有找到合法的 N-X-S/T 位点。</p>`
        }
      </div>
    `;
  }

  function renderF1Demo(slide) {
    const demos = story.demos.f1;
    const candidate = selectedF1Candidate();
    const options = demos.candidates.map((item) => `
      <option value="${escapeHtml(item.row_id)}" ${item.row_id === candidate.row_id ? "selected" : ""}>
        ${escapeHtml(item.row_id)} · ${escapeHtml(item.protein_name)} · ${escapeHtml(item.motif)}
      </option>
    `).join("");
    return `
      <section class="slide f1-demo-slide">
        <div>
          <p class="eyebrow">F1 / LIVE CANDIDATE WORKBENCH</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        <div class="f1-workbench" data-f1-row="${escapeHtml(candidate.row_id)}">
          <div class="f1-main-panel">
            <div class="demo-toolbar">
              <label class="demo-select-wrap">
                <span>真实候选位点</span>
                <select data-demo="f1-candidate" aria-label="选择 F1 候选位点">${options}</select>
              </label>
              <div class="preset-row">
                ${demos.presets.map((preset) => `
                  <button
                    type="button"
                    class="demo-chip ${preset.row_id === candidate.row_id ? "active" : ""}"
                    data-demo="f1-preset"
                    data-row-id="${escapeHtml(preset.row_id)}"
                  >${escapeHtml(preset.label)}</button>
                `).join("")}
              </div>
            </div>
            <div class="f1-candidate-head">
              <div>
                <span class="candidate-id">${escapeHtml(candidate.accession)}:${fmt(candidate.pos)}</span>
                <strong>${escapeHtml(candidate.protein_name)}</strong>
              </div>
              <div class="candidate-tags">
                <span>${escapeHtml(evidenceLabel(candidate.evidence_class))}</span>
                <span>${escapeHtml(candidate.motif)}</span>
                <span>${candidate.evaluation_included ? "进入评估池" : "只展示"}</span>
              </div>
            </div>
            <div class="f1-method-grid">
              ${renderF1Method("UniProt 注释", candidate.uniprot_prediction, null, "数据库标签快照")}
              ${renderF1Method("序列规则", candidate.sequence_rule_prediction, null, "N-X-S/T，X 不是 P")}
              ${renderF1Method("ESM-35M 探针", candidate.esm35_prediction, candidate.esm35_probability, "本地 OOF 模型")}
              ${renderF1Method("ESM-150M 适配器", candidate.esm150_prediction, candidate.esm150_probability, "作者检查点复算")}
            </div>
            <div class="f1-preset-matrix">
              <div class="f1-matrix-head">
                <span>四个代表案例</span>
                <small>点击任意行切换上方候选</small>
              </div>
              ${demos.presets.map((preset) => {
                const row = demos.candidates.find((item) => item.row_id === preset.row_id);
                if (!row) return "";
                return `
                  <button
                    type="button"
                    class="f1-matrix-row ${row.row_id === candidate.row_id ? "active" : ""}"
                    data-demo="f1-preset"
                    data-row-id="${escapeHtml(row.row_id)}"
                  >
                    <span class="f1-matrix-case">
                      <strong>${escapeHtml(preset.label)}</strong>
                      <small>${escapeHtml(row.accession)}:${fmt(row.pos)} · ${escapeHtml(row.motif)}</small>
                    </span>
                    ${renderF1MatrixCall("UniProt", row.uniprot_prediction)}
                    ${renderF1MatrixCall("规则", row.sequence_rule_prediction)}
                    ${renderF1MatrixCall("35M", row.esm35_prediction)}
                    ${renderF1MatrixCall("150M", row.esm150_prediction)}
                  </button>
                `;
              }).join("")}
            </div>
            <div class="f1-signal-line">
              <span>分歧模式</span>
              <strong>${escapeHtml(disagreementLabel(candidate.disagreement_pattern))}</strong>
              <code>${escapeHtml(sourceBasename(candidate.source))}</code>
            </div>
          </div>
          <aside class="f1-side-panel">
            <article class="f1-review-card ${candidate.review_status ? "reviewed" : "unreviewed"}">
              <div class="panel-kicker">人工复核证据</div>
              ${
                candidate.review_status
                  ? `<strong>${escapeHtml(reviewLabel(candidate.review_status))}</strong>
                     <p>${escapeHtml(candidate.reviewer_note)}</p>
                     <code>${escapeHtml(sourceBasename(candidate.review_source))}</code>`
                  : `<strong>不在本轮 10 个重点复核样本中</strong>
                     <p>没有人工复核备注，不等于没有生物学证据，也不等于实验阴性。</p>`
              }
            </article>
            <article class="sequon-lab">
              <div class="panel-kicker">现场规则实验 / Sequon Lab</div>
              <h3>${escapeHtml(demos.rule.label)}</h3>
              <p>${escapeHtml(demos.rule.constraint)}。${escapeHtml(demos.rule.scope)}</p>
              <div class="rule-input-row">
                <input
                  type="text"
                  data-demo="f1-rule-input"
                  value="${escapeHtml(demoState.f1RuleDraft)}"
                  placeholder="例如 NST"
                  autocomplete="off"
                  spellcheck="false"
                  aria-label="输入短肽以检查 Sequon"
                >
                <button type="button" class="demo-primary" data-demo="f1-rule-run">运行规则</button>
                <button type="button" class="demo-secondary" data-demo="f1-use-motif">用当前 motif</button>
              </div>
              ${renderF1RuleResult()}
            </article>
          </aside>
        </div>
      </section>
    `;
  }

  function renderW2(slide) {
    return `
      <section class="slide">
        <div>
          <p class="eyebrow">W02 / FIVE DAYS, FIVE VERIFIABLE STEPS</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        <div class="day-grid">
          ${slide.days.map((day) => `
            <article class="day-card">
              <span class="day-name">${escapeHtml(day.day)}</span>
              <span class="day-date">${escapeHtml(day.date)}</span>
              <h3 class="day-title">${escapeHtml(day.title)}</h3>
              <p class="day-copy">${escapeHtml(day.work)}</p>
              <p class="day-purpose">${escapeHtml(day.purpose)}</p>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }

  function renderTracks(slide) {
    return `
      <section class="slide">
        <div>
          <p class="eyebrow">SYSTEM MAP / THREE DIFFERENT OBJECTS</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        <div class="track-grid">
          ${story.tracks.map((track) => `
            <article class="track">
              <span class="track-code">${escapeHtml(track.code)}</span>
              <h3 class="track-name">${escapeHtml(track.name)}</h3>
              <p class="track-question">${escapeHtml(track.question)}</p>
              ${track.table ? `<span class="table-badge">${escapeHtml(track.table)}</span>` : ""}
              <p class="track-answer">
                ${escapeHtml(track.what)}<br>
                <strong>${escapeHtml(track.purpose)}</strong>
              </p>
            </article>
          `).join("")}
        </div>
      </section>
    `;
  }

  function renderResultCard(task) {
    return `
      <article class="result-card local">
        <div class="result-head">
          <span class="result-label">${escapeHtml(task.label)}</span>
          <span class="result-metric">${escapeHtml(task.metric)}</span>
        </div>
        <strong class="result-value">${fmt(task.mean)} ± ${fmt(task.std)}</strong>
        <div class="result-reference">
          论文 Table 3 参照：${fixed(task.reference_mean, 3)} ± ${fixed(task.reference_std, 3)}
        </div>
        <div class="result-delta">local - reference: ${signed(task.delta)}</div>
      </article>
    `;
  }

  function selectedF2Task() {
    return story.demos.f2.tasks.find((task) => task.id === demoState.f2TaskId)
      || story.demos.f2.tasks[0];
  }

  function selectedF2Seed(task) {
    return task.per_seed.find((row) => row.seed === demoState.f2Seed)
      || task.per_seed[0];
  }

  function renderF2Detail(task) {
    const seed = selectedF2Seed(task);
    const testMetric = seed.test[task.test_metric_key];
    const validationMetric = seed.validation[task.validation_metric_key];
    const aggregateMetric = task.aggregate[`test_${task.test_metric_key}`];
    return `
      <div class="f2-task-row">
        ${story.demos.f2.tasks.map((item) => `
          <button
            type="button"
            class="f2-task-button ${item.id === task.id ? "active" : ""}"
            data-demo="f2-task"
            data-task-id="${escapeHtml(item.id)}"
          >
            <span>${escapeHtml(item.label)}</span>
            <strong>${fixed(item.aggregate[`test_${item.test_metric_key}`].mean, 6)}</strong>
            <small>论文 ${fixed(item.reference_mean, 3)} ± ${fixed(item.reference_std, 3)}</small>
          </button>
        `).join("")}
      </div>
      <div class="f2-demo-grid">
        <div class="f2-scoreboard">
          <div class="f2-score-head">
            <div>
              <span class="panel-kicker">三个种子的汇总</span>
              <h3>${escapeHtml(task.label)} / ${escapeHtml(task.metric)}</h3>
            </div>
            <span class="analysis-chip">Table 3</span>
          </div>
          <div class="f2-primary-score">
            <strong>${fixed(aggregateMetric.mean, 6)}</strong>
            <span>± ${fixed(aggregateMetric.std, 6)}</span>
          </div>
          <div class="score-track"><span style="width:${progressWidth(aggregateMetric.mean)}%"></span></div>
          <div class="f2-reference-row">
            <span>论文参照</span>
            <strong>${fixed(task.reference_mean, 3)} ± ${fixed(task.reference_std, 3)}</strong>
            <em>本地减论文 ${signedFixed(task.delta, 6)}</em>
          </div>
          <div class="seed-row">
            ${task.per_seed.map((row) => `
              <button
                type="button"
                class="seed-button ${row.seed === seed.seed ? "active" : ""}"
                data-demo="f2-seed"
                data-seed="${fmt(row.seed)}"
              >seed ${fmt(row.seed)}</button>
            `).join("")}
          </div>
          <div class="seed-comparison" aria-label="逐种子测试指标">
            <div class="seed-comparison-title">
              <span>逐种子 test ${escapeHtml(task.metric)}</span>
              <small>点击上方 seed 查看明细</small>
            </div>
            ${task.per_seed.map((row) => {
              const value = row.test[task.test_metric_key];
              return `
                <div class="seed-comparison-row ${row.seed === seed.seed ? "active" : ""}">
                  <span>seed ${fmt(row.seed)}</span>
                  <div><i style="width:${progressWidth(value)}%"></i></div>
                  <strong>${fixed(value, 6)}</strong>
                </div>
              `;
            }).join("")}
          </div>
          <div class="f2-seed-detail" data-f2-seed="${fmt(seed.seed)}">
            <div class="metric-tile primary">
              <span>test ${escapeHtml(task.metric)}</span>
              <strong>${fixed(testMetric, 6)}</strong>
            </div>
            <div class="metric-tile">
              <span>validation ${escapeHtml(task.metric)}</span>
              <strong>${fixed(validationMetric, 6)}</strong>
            </div>
            <div class="metric-tile">
              <span>best epoch</span>
              <strong>${fmt(seed.best_epoch)}</strong>
            </div>
            <div class="metric-tile">
              <span>选择依据</span>
              <strong>${escapeHtml(seed.validation_selection.metric)} ${fixed(seed.validation_selection.value, 4)}</strong>
            </div>
          </div>
        </div>
        <aside class="f2-contract-panel">
          <div class="panel-kicker">数据与实现契约</div>
          <div class="contract-grid">
            <div><span>样本</span><strong>${fmt(task.rows)}</strong></div>
            <div><span>train</span><strong>${fmt(task.split_counts.train)}</strong></div>
            <div><span>valid</span><strong>${fmt(task.split_counts.valid)}</strong></div>
            <div><span>test</span><strong>${fmt(task.split_counts.test)}</strong></div>
          </div>
          <div class="label-counts">
            ${Object.entries(task.label_counts).map(([label, count]) => `
              <span>类 ${escapeHtml(label)} <strong>${fmt(count)}</strong></span>
            `).join("")}
          </div>
          <p>
            ${fmt(story.demos.f2.seed_count)} 个种子，每个 ${fmt(story.demos.f2.training.epochs)} epoch，
            batch ${fmt(story.demos.f2.training.batch_size)}。
          </p>
          <div class="training-grid">
            <div><span>optimizer</span><strong>${escapeHtml(story.demos.f2.training.optimizer)}</strong></div>
            <div><span>lr</span><strong>${fmt(story.demos.f2.training.lr)}</strong></div>
            <div><span>scheduler</span><strong>${escapeHtml(story.demos.f2.training.scheduler)}</strong></div>
            <div><span>weight decay</span><strong>${fmt(story.demos.f2.training.weight_decay)}</strong></div>
          </div>
          <p><strong>${escapeHtml(story.demos.f2.implementation_label)}</strong></p>
          <p>TorchDrug installed：${story.demos.f2.torchdrug_installed ? "true" : "false"}</p>
          <code>${escapeHtml(sourceBasename(task.source))}</code>
        </aside>
      </div>
      <p class="boundary-note">
        对齐 GlycanML Table 3，不是 Table 2。这里没有伪造混淆矩阵；每个种子只展示源 JSON 中真实存在的 validation、test 和 best epoch。
      </p>
    `;
  }

  function renderF2(slide) {
    const task = selectedF2Task();
    return `
      <section class="slide f2-demo-slide" data-f2-task="${escapeHtml(task.id)}" data-f2-seed="${fmt(demoState.f2Seed)}">
        <div>
          <p class="eyebrow">F2 / INTERACTIVE RESULT INSPECTOR</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        ${renderF2Detail(task)}
      </section>
    `;
  }

  function filteredF3Tasks() {
    const tasks = story.demos.f3.tasks;
    if (demoState.f3Filter === "exact") {
      return tasks.filter((task) => task.exact_sequence);
    }
    if (demoState.f3Filter === "failure") {
      return tasks.filter((task) => task.tool_calls.some((call) => call.status !== "ok"));
    }
    if (demoState.f3Filter === "no-final") {
      return tasks.filter((task) => !task.final_answer);
    }
    return tasks;
  }

  function selectedF3Task() {
    const filtered = filteredF3Tasks();
    return filtered.find((task) => task.task_id === demoState.f3TaskId)
      || filtered[0]
      || story.demos.f3.tasks[0];
  }

  function resetF3Step(task) {
    demoState.f3Step = task.tool_calls.length ? 1 : 0;
  }

  function renderToolArgs(argumentsValue) {
    if (!argumentsValue || Object.keys(argumentsValue).length === 0) {
      return "{}";
    }
    return JSON.stringify(argumentsValue, null, 2);
  }

  function renderF3Run(task) {
    const visibleCount = Math.min(demoState.f3Step, task.tool_calls.length);
    const allVisible = visibleCount >= task.tool_calls.length;
    return `
      <div class="trace-step-list" data-visible-steps="${visibleCount}" data-total-steps="${task.tool_calls.length}">
        ${
          task.tool_calls.length
            ? task.tool_calls.slice(0, visibleCount).map((call, index) => `
                <article class="trace-step ${call.status === "ok" ? "ok" : "failed"}">
                  <span class="trace-index">${String(index + 1).padStart(2, "0")}</span>
                  <div class="trace-main">
                    <div class="trace-head">
                      <strong>${escapeHtml(call.tool)}</strong>
                      <span class="status-pill ${call.status === "ok" ? "ok" : "failed"}">${escapeHtml(call.status)}</span>
                    </div>
                    <pre>${escapeHtml(renderToolArgs(call.arguments))}</pre>
                    ${call.error ? `<p class="trace-error">${escapeHtml(call.error)}</p>` : ""}
                  </div>
                </article>
              `).join("")
            : `<div class="trace-empty">本题没有工具调用记录。</div>`
        }
        ${
          allVisible && task.tool_calls.length
            ? `<article class="final-answer ${task.final_answer ? "present" : "missing"}">
                <span class="trace-index">FINAL</span>
                <div>
                  <strong>${task.final_answer ? "最终回答字段存在" : "没有最终回答"}</strong>
                  <p>${escapeHtml(task.final_answer || "源 task JSON 中 final_answer 为空。")}</p>
                </div>
              </article>`
            : ""
        }
      </div>
      <div class="trace-controls">
        <span class="trace-progress">已显示 ${visibleCount} / ${task.tool_calls.length} 步</span>
        <button type="button" class="demo-secondary" data-demo="f3-reset-step">重置</button>
        <button type="button" class="demo-primary" data-demo="f3-next-step" ${allVisible ? "disabled" : ""}>下一步</button>
        <button type="button" class="demo-secondary" data-demo="f3-all-steps" ${allVisible ? "disabled" : ""}>显示全部</button>
      </div>
    `;
  }

  function renderF3Detail(slide, task) {
    const filtered = filteredF3Tasks();
    const filters = [
      ["all", "全部", story.demos.f3.tasks.length],
      ["exact", "完整轨迹", story.demos.f3.tasks.filter((item) => item.exact_sequence).length],
      ["failure", "含工具失败", story.demos.f3.tasks.filter((item) => item.tool_calls.some((call) => call.status !== "ok")).length],
      ["no-final", "无最终回答", story.demos.f3.tasks.filter((item) => !item.final_answer).length],
    ];
    return `
      <div class="f3-demo-top">
        <div class="filter-row">
          ${filters.map(([id, label, count]) => `
            <button
              type="button"
              class="filter-button ${demoState.f3Filter === id ? "active" : ""}"
              data-demo="f3-filter"
              data-filter="${escapeHtml(id)}"
            >${escapeHtml(label)} <strong>${fmt(count)}</strong></button>
          `).join("")}
        </div>
        <label class="task-select-wrap">
          <span>${fmt(filtered.length)} 道可选任务</span>
          <select data-demo="f3-task" aria-label="选择 F3 任务">
            ${filtered.map((item) => `
              <option value="${fmt(item.task_id)}" ${item.task_id === task.task_id ? "selected" : ""}>
                #${fmt(item.task_id)} · ${escapeHtml(item.question.slice(0, 56))}${item.question.length > 56 ? "..." : ""}
              </option>
            `).join("")}
          </select>
        </label>
      </div>
      <div class="f3-task-card">
        <div class="f3-task-heading">
          <div>
            <span class="candidate-id">TASK #${fmt(task.task_id)}</span>
            <h3>${escapeHtml(task.question)}</h3>
          </div>
          <span class="analysis-chip">${escapeHtml(feasibilityLabel(task.feasibility))}</span>
        </div>
        <div class="f3-facts">
          <span>期望工具 <strong>${task.expected_tools.map(escapeHtml).join(" / ") || "无"}</strong></span>
          <span>轨迹匹配 <strong>${task.exact_sequence ? "是" : "否"}</strong></span>
          <span>期望全命中 <strong>${task.all_expected_called ? "是" : "否"}</strong></span>
          <span>调用成功 <strong>${fmt(task.call_successes)} / ${fmt(task.called_steps)}</strong></span>
          ${task.blocking_tools ? `<span>阻断工具 <strong>${escapeHtml(task.blocking_tools)}</strong></span>` : ""}
        </div>
      </div>
      <div class="f3-player-layout">
        <div class="trace-player">
          <div class="panel-kicker">真实工具轨迹回放</div>
          ${renderF3Run(task)}
        </div>
        <aside class="f3-summary-panel">
          <div class="panel-kicker">50 题轨迹总览</div>
          <div class="trajectory-compact">
            ${renderTrajectoryFacts()}
          </div>
          <p>这些是工具轨迹和输出存在性指标，不是答案正确率。</p>
          <code>${escapeHtml(sourceBasename(task.source))}</code>
        </aside>
      </div>
    `;
  }

  function renderTrajectoryFacts() {
    const trajectory = byCode("F3").trajectory;
    return `
      <div><span>完整轨迹</span><strong>${fmt(trajectory.exact_sequence)} / ${fmt(trajectory.tasks_run)}</strong></div>
      <div><span>期望全命中</span><strong>${fmt(trajectory.all_expected_called)} / ${fmt(trajectory.tasks_run)}</strong></div>
      <div><span>至少命中一个</span><strong>${fmt(trajectory.any_expected_called)} / ${fmt(trajectory.tasks_run)}</strong></div>
      <div><span>有最终回答</span><strong>${fmt(trajectory.tasks_with_final_answer)} / ${fmt(trajectory.tasks_run)}</strong></div>
      <div><span>工具成功</span><strong>${fmt(trajectory.tool_call_successes)} / ${fmt(trajectory.tool_calls)}</strong></div>
    `;
  }

  function renderF3(slide) {
    const task = selectedF3Task();
    return `
      <section class="slide f3-demo-slide" data-f3-task="${fmt(task.task_id)}" data-f3-visible-steps="${fmt(Math.min(demoState.f3Step, task.tool_calls.length))}">
        <div>
          <p class="eyebrow">F3 / REAL TOOL TRACE PLAYER</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        ${renderF3Detail(slide, task)}
      </section>
    `;
  }

  function renderDelivery(slide) {
    const delivery = story.delivery;
    return `
      <section class="slide">
        <div>
          <p class="eyebrow">DELIVERY / REPRODUCIBLE PROOF</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        <div class="delivery-grid">
          ${delivery.proof_points.map((proof) => `
            <article class="delivery-card">
              <strong class="delivery-value">${fmt(proof.value)}<small>${escapeHtml(proof.unit)}</small></strong>
              <span class="delivery-label">${escapeHtml(proof.label)}</span>
              <p class="delivery-detail">${escapeHtml(proof.detail)}</p>
            </article>
          `).join("")}
        </div>
        <div class="closure">
          <strong>状态：${escapeHtml(delivery.status)}</strong><br>
          ${escapeHtml(delivery.closure)}
          记分卡同时保存 ${fmt(delivery.source_count)} 个源文件的路径、字节数和 SHA256。
        </div>
      </section>
    `;
  }

  function renderBoundaries(slide) {
    return `
      <section class="slide">
        <div>
          <p class="eyebrow">CLAIM BOUNDARIES / NEXT WEEK</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        <div class="boundary-layout">
          <ul class="boundary-list">
            ${story.boundaries.map((boundary) => `<li>${escapeHtml(boundary.text)}</li>`).join("")}
          </ul>
          <div class="next-panel">
            <h3>NEXT / 下一周</h3>
            <ol class="next-list">
              ${story.next.map((item) => `<li>${escapeHtml(item)}</li>`).join("")}
            </ol>
          </div>
        </div>
      </section>
    `;
  }

  function renderSlide(slide) {
    const renderers = {
      cover: renderCover,
      w1: renderW1,
      f1demo: renderF1Demo,
      w2: renderW2,
      tracks: renderTracks,
      f2: renderF2,
      f3: renderF3,
      delivery: renderDelivery,
      boundaries: renderBoundaries,
    };
    return renderers[slide.id](slide);
  }

  function milestoneIndex(slideIndex) {
    if (slideIndex <= 2) {
      return 0;
    }
    if (slideIndex <= 4) {
      return 1;
    }
    if (slideIndex <= 7) {
      return 2;
    }
    return 3;
  }

  function renderRail() {
    chapterNav.innerHTML = slides.map((slide, index) => `
      <button
        type="button"
        class="chapter-button"
        data-goto="${index}"
        aria-label="跳到第 ${index + 1} 页：${escapeHtml(slide.chapter)}"
      >
        <span class="chapter-number">${String(index + 1).padStart(2, "0")}</span>
        <span class="chapter-name">${escapeHtml(slide.chapter)}</span>
        <span class="chapter-range">${escapeHtml(slide.range)}</span>
      </button>
    `).join("");
    milestoneRoot.innerHTML = milestoneLabels.map((label, index) => `
      <span class="milestone" data-milestone="${index}">${escapeHtml(label)}</span>
    `).join("");
    chapterNav.querySelectorAll("[data-goto]").forEach((button) => {
      button.addEventListener("click", () => {
        goTo(Number.parseInt(button.dataset.goto, 10));
      });
    });
  }

  function updateChrome(slide) {
    deck.dataset.deckMounted = "true";
    deck.dataset.activeSlide = String(cursor + 1);
    deck.dataset.slideId = slide.id;
    deck.dataset.notesVisible = String(notesVisible);
    slideRoot.dataset.slideTitle = slide.title;
    stageRange.textContent = slide.range;
    stageChapter.textContent = slide.chapter;
    sourceLine.textContent = `来源：${sourceText(slide)}`;
    progressFill.style.width = `${((cursor + 1) / slides.length) * 100}%`;
    slideCounter.textContent = `${String(cursor + 1).padStart(2, "0")} / ${String(slides.length).padStart(2, "0")}`;
    notesCopy.textContent = slide.notes;
    notesPanel.setAttribute("aria-hidden", String(!notesVisible));
    document.querySelectorAll(".chapter-button").forEach((button, index) => {
      const active = index === cursor;
      button.classList.toggle("active", active);
      if (active) {
        button.setAttribute("aria-current", "page");
      } else {
        button.removeAttribute("aria-current");
      }
    });
    document.querySelectorAll("[data-milestone]").forEach((marker, index) => {
      marker.classList.toggle("active", index === milestoneIndex(cursor));
    });
  }

  function measureLayout() {
    const root = document.documentElement;
    const body = document.body;
    const stage = deck.getBoundingClientRect();
    const horizontalOverflow =
      root.scrollWidth > root.clientWidth + 1 ||
      body.scrollWidth > body.clientWidth + 1;
    const verticalOverflow =
      root.scrollHeight > root.clientHeight + 1 ||
      body.scrollHeight > body.clientHeight + 1;
    const stageContained =
      stage.left >= -1 &&
      stage.top >= -1 &&
      stage.right <= window.innerWidth + 1 &&
      stage.bottom <= window.innerHeight + 1;
    deck.dataset.layoutViewport = `${window.innerWidth}x${window.innerHeight}`;
    deck.dataset.horizontalOverflow = String(horizontalOverflow);
    deck.dataset.verticalOverflow = String(verticalOverflow);
    deck.dataset.stageContained = String(stageContained);
    deck.dataset.layoutOk = String(!horizontalOverflow && !verticalOverflow && stageContained);
  }

  function rerenderActiveSlide() {
    slideRoot.innerHTML = renderSlide(slides[cursor]);
    bindSlideInteractions();
    measureLayout();
  }

  function runF1Rule() {
    demoState.f1RuleResult = sequonMatches(demoState.f1RuleDraft);
    rerenderActiveSlide();
  }

  function bindSlideInteractions() {
    const f1Select = slideRoot.querySelector('[data-demo="f1-candidate"]');
    f1Select?.addEventListener("change", () => {
      demoState.f1RowId = f1Select.value;
      rerenderActiveSlide();
    });
    slideRoot.querySelectorAll('[data-demo="f1-preset"]').forEach((button) => {
      button.addEventListener("click", () => {
        demoState.f1RowId = button.dataset.rowId;
        rerenderActiveSlide();
      });
    });
    const ruleInput = slideRoot.querySelector('[data-demo="f1-rule-input"]');
    ruleInput?.addEventListener("input", () => {
      demoState.f1RuleDraft = ruleInput.value;
    });
    ruleInput?.addEventListener("keydown", (event) => {
      if (event.key === "Enter") {
        event.preventDefault();
        runF1Rule();
      }
    });
    slideRoot.querySelector('[data-demo="f1-rule-run"]')?.addEventListener("click", runF1Rule);
    slideRoot.querySelector('[data-demo="f1-use-motif"]')?.addEventListener("click", () => {
      demoState.f1RuleDraft = selectedF1Candidate().motif;
      demoState.f1RuleResult = sequonMatches(demoState.f1RuleDraft);
      rerenderActiveSlide();
    });

    slideRoot.querySelectorAll('[data-demo="f2-task"]').forEach((button) => {
      button.addEventListener("click", () => {
        demoState.f2TaskId = button.dataset.taskId;
        const task = selectedF2Task();
        if (!task.per_seed.some((row) => row.seed === demoState.f2Seed)) {
          demoState.f2Seed = task.per_seed[0].seed;
        }
        rerenderActiveSlide();
      });
    });
    slideRoot.querySelectorAll('[data-demo="f2-seed"]').forEach((button) => {
      button.addEventListener("click", () => {
        demoState.f2Seed = Number.parseInt(button.dataset.seed, 10);
        rerenderActiveSlide();
      });
    });

    slideRoot.querySelectorAll('[data-demo="f3-filter"]').forEach((button) => {
      button.addEventListener("click", () => {
        demoState.f3Filter = button.dataset.filter;
        const filtered = filteredF3Tasks();
        if (!filtered.some((task) => task.task_id === demoState.f3TaskId)) {
          demoState.f3TaskId = filtered[0]?.task_id ?? story.demos.f3.tasks[0].task_id;
        }
        resetF3Step(selectedF3Task());
        rerenderActiveSlide();
      });
    });
    const f3Select = slideRoot.querySelector('[data-demo="f3-task"]');
    f3Select?.addEventListener("change", () => {
      demoState.f3TaskId = Number.parseInt(f3Select.value, 10);
      resetF3Step(selectedF3Task());
      rerenderActiveSlide();
    });
    slideRoot.querySelector('[data-demo="f3-reset-step"]')?.addEventListener("click", () => {
      resetF3Step(selectedF3Task());
      rerenderActiveSlide();
    });
    slideRoot.querySelector('[data-demo="f3-next-step"]')?.addEventListener("click", () => {
      const task = selectedF3Task();
      demoState.f3Step = Math.min(demoState.f3Step + 1, task.tool_calls.length);
      rerenderActiveSlide();
    });
    slideRoot.querySelector('[data-demo="f3-all-steps"]')?.addEventListener("click", () => {
      demoState.f3Step = selectedF3Task().tool_calls.length;
      rerenderActiveSlide();
    });
  }

  function updateView() {
    const slide = slides[cursor];
    slideRoot.innerHTML = renderSlide(slide);
    bindSlideInteractions();
    updateChrome(slide);
    measureLayout();
  }

  function goTo(index) {
    cursor = clamp(index, 0, slides.length - 1);
    updateView();
  }

  function next() {
    goTo(cursor + 1);
  }

  function prev() {
    goTo(cursor - 1);
  }

  function toggleNotes(force) {
    notesVisible = typeof force === "boolean" ? force : !notesVisible;
    updateChrome(slides[cursor]);
  }

  function toggleFullscreen() {
    if (!document.fullscreenElement) {
      const target = document.documentElement;
      if (target.requestFullscreen) {
        target.requestFullscreen().catch(() => {});
      }
    } else if (document.exitFullscreen) {
      document.exitFullscreen().catch(() => {});
    }
  }

  window.addEventListener("keydown", (event) => {
    const key = event.key;
    if (event.target instanceof Element && event.target.closest("input, select, textarea")) {
      return;
    }
    if (["ArrowRight", "PageDown", " "].includes(key)) {
      event.preventDefault();
      next();
      return;
    }
    if (["ArrowLeft", "PageUp"].includes(key)) {
      event.preventDefault();
      prev();
      return;
    }
    if (key === "Home") {
      event.preventDefault();
      goTo(0);
      return;
    }
    if (key === "End") {
      event.preventDefault();
      goTo(slides.length - 1);
      return;
    }
    if (/^[1-9]$/.test(key)) {
      event.preventDefault();
      goTo(Number.parseInt(key, 10) - 1);
      return;
    }
    if (key.toLowerCase() === "n") {
      event.preventDefault();
      toggleNotes();
      return;
    }
    if (key.toLowerCase() === "f") {
      event.preventDefault();
      toggleFullscreen();
    }
  });

  window.addEventListener("touchstart", (event) => {
    touchStartX = event.changedTouches[0]?.clientX ?? null;
  }, { passive: true });

  window.addEventListener("touchend", (event) => {
    if (touchStartX === null) {
      return;
    }
    const endX = event.changedTouches[0]?.clientX ?? touchStartX;
    if (Math.abs(endX - touchStartX) > 45) {
      if (endX < touchStartX) {
        next();
      } else {
        prev();
      }
    }
    touchStartX = null;
  }, { passive: true });

  window.addEventListener("resize", measureLayout);

  window.__RECORDING_DECK__ = {
    slideCount: slides.length,
    goTo,
    next,
    prev,
    toggleNotes,
    getSlide() {
      return cursor + 1;
    },
  };

  renderRail();
  updateView();
})();
