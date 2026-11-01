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

  function renderF2(slide) {
    const track = byCode("F2");
    return `
      <section class="slide">
        <div>
          <p class="eyebrow">F2 / GLYCANML TABLE 3</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        <div class="result-grid">
          ${renderResultCard(track.tasks.immunogenicity)}
          ${renderResultCard(track.tasks.glycosylation)}
        </div>
        <div class="evidence-strip">
          <div class="evidence-item">
            <strong>${fmt(track.training.seeds)} 个种子</strong><br>
            每个 ${fmt(track.training.epochs)} epoch，batch ${fmt(track.training.batch_size)}
          </div>
          <div class="evidence-item">
            <strong>${escapeHtml(track.implementation)}</strong><br>
            TorchDrug installed: ${track.torchdrug_installed ? "true" : "false"}
          </div>
          <div class="evidence-item">
            <strong>结果解释</strong><br>
            接近论文量级，但保留实现差异和真实偏差。
          </div>
        </div>
        <p class="boundary-note">
          对齐的是 GlycanML Table 3。本地是 PyG 自实现 RGCN，不是 TorchDrug 逐位克隆；
          TorchDrug 未安装，所以没有逐位数值差。
        </p>
      </section>
    `;
  }

  function renderF3(slide) {
    const track = byCode("F3");
    const trajectory = track.trajectory;
    const tools = track.tools;
    const feasibility = track.feasibility;
    const total = feasibility.total;
    const directPct = (feasibility.direct / total) * 100;
    const replacementPct = (feasibility.replacement / total) * 100;
    const failurePct = (feasibility.service_failure / total) * 100;
    return `
      <section class="slide">
        <div>
          <p class="eyebrow">F3 / TRAJECTORY BEFORE ANSWER QUALITY</p>
          <h2>${escapeHtml(slide.title)}</h2>
          <p class="slide-thesis">${escapeHtml(slide.thesis)}</p>
        </div>
        ${workPurpose(slide)}
        <div class="f3-layout">
          <div>
            <div class="trajectory-grid">
              <div class="trajectory-item">
                <strong class="trajectory-value">${fmt(trajectory.tasks_run)}</strong>
                <span class="trajectory-label">完成任务数</span>
              </div>
              <div class="trajectory-item">
                <strong class="trajectory-value">${fmt(trajectory.exact_sequence)} / ${fmt(trajectory.tasks_run)}</strong>
                <span class="trajectory-label">完整工具轨迹精确匹配</span>
              </div>
              <div class="trajectory-item">
                <strong class="trajectory-value">${fmt(trajectory.all_expected_called)} / ${fmt(trajectory.tasks_run)}</strong>
                <span class="trajectory-label">全部期望工具被调用</span>
              </div>
              <div class="trajectory-item">
                <strong class="trajectory-value">${fmt(trajectory.any_expected_called)} / ${fmt(trajectory.tasks_run)}</strong>
                <span class="trajectory-label">至少一个期望工具被调用</span>
              </div>
              <div class="trajectory-item">
                <strong class="trajectory-value">${fmt(trajectory.tasks_with_final_answer)} / ${fmt(trajectory.tasks_run)}</strong>
                <span class="trajectory-label">有最终回答字段</span>
              </div>
              <div class="trajectory-item">
                <strong class="trajectory-value">${fmt(trajectory.tool_call_successes)} / ${fmt(trajectory.tool_calls)}</strong>
                <span class="trajectory-label">工具调用成功</span>
              </div>
            </div>
            <p class="boundary-note">
              这些是工具轨迹和输出存在性指标，不是答案正确率。
              grader 状态：${escapeHtml(trajectory.grader)}。
            </p>
          </div>
          <div class="tool-panel">
            <div class="mini-stats">
              <div class="mini-stat">
                <strong>${fmt(tools.total)}</strong>
                <span>wrapper 总数</span>
              </div>
              <div class="mini-stat">
                <strong>${fmt(tools.direct_ok)}</strong>
                <span>默认直接成功</span>
              </div>
              <div class="mini-stat">
                <strong>${fmt(tools.service_alive)}</strong>
                <span>服务存活</span>
              </div>
            </div>
            <p class="split-title">${fmt(feasibility.total)} 题按当前工具可用性重新分类</p>
            <div class="split-bar" aria-label="任务工具可行性分类">
              <span style="width:${directPct}%"></span>
              <span style="width:${replacementPct}%"></span>
              <span style="width:${failurePct}%"></span>
            </div>
            <div class="split-legend">
              <div><span>当前工具直接完成</span><strong>${fmt(feasibility.direct)}</strong></div>
              <div><span>需要替代工具</span><strong>${fmt(feasibility.replacement)}</strong></div>
              <div><span>服务失败</span><strong>${fmt(feasibility.service_failure)}</strong></div>
              <div><span>合计</span><strong>${fmt(feasibility.total)}</strong></div>
            </div>
          </div>
        </div>
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
    if (slideIndex <= 1) {
      return 0;
    }
    if (slideIndex <= 3) {
      return 1;
    }
    if (slideIndex <= 5) {
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

  function updateView() {
    const slide = slides[cursor];
    slideRoot.innerHTML = renderSlide(slide);
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
    if (/^[1-8]$/.test(key)) {
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
