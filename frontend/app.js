const sentimentLabels = {
  positive: '正向',
  neutral: '中性',
  negative: '负向',
  mixed: '混合',
};

const sourceLabels = {
  llm: 'LLM',
  rule: '规则',
  reuse: '文本复用',
  cache_legacy: '旧缓存',
  unknown: '未知',
};

const pipelineLabels = {
  idle: 'Idle',
  running: 'Running',
  completed: 'Completed',
  failed: 'Failed',
  available: 'Available',
  missing: 'Missing',
};

const els = {
  title: document.getElementById('topic-title'),
  subtitle: document.getElementById('topic-subtitle'),
  metrics: document.getElementById('metrics-grid'),
  sentimentBars: document.getElementById('sentiment-bars'),
  sourceBars: document.getElementById('source-bars'),
  moduleBars: document.getElementById('module-bars'),
  charts: document.getElementById('charts-grid'),
  reviewQueue: document.getElementById('review-queue'),
  reviewCount: document.getElementById('review-count'),
  pipelineStatus: document.getElementById('pipeline-status'),
  pipelineTask: document.getElementById('pipeline-task'),
  pipelinePid: document.getElementById('pipeline-pid'),
  pipelineReturnCode: document.getElementById('pipeline-return-code'),
  pipelineLog: document.getElementById('pipeline-log'),
  commentaryStatus: document.getElementById('commentary-status'),
  commentary: document.getElementById('llm-commentary'),
  deterministic: document.getElementById('deterministic-report'),
  refreshButton: document.getElementById('refresh-button'),
  runButton: document.getElementById('run-button'),
};

function formatModuleName(name) {
  if (!name) return '-';
  return name.replaceAll('_', ' / ').replace(/\b\w/g, (char) => char.toUpperCase());
}

function escapeHtml(text) {
  return String(text)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function applyInlineMarkdown(text) {
  return text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>').replace(/`([^`]+)`/g, '<code>$1</code>');
}

function markdownToHtml(markdown) {
  const lines = escapeHtml(markdown || '').split(/\r?\n/);
  const blocks = [];
  let listType = null;
  let listItems = [];
  let paragraph = [];

  const flushParagraph = () => {
    if (!paragraph.length) return;
    blocks.push(`<p>${applyInlineMarkdown(paragraph.join(' '))}</p>`);
    paragraph = [];
  };

  const flushList = () => {
    if (!listType || !listItems.length) return;
    const items = listItems.map((item) => `<li>${applyInlineMarkdown(item)}</li>`).join('');
    blocks.push(`<${listType}>${items}</${listType}>`);
    listType = null;
    listItems = [];
  };

  for (const rawLine of lines) {
    const line = rawLine.trim();
    if (!line) {
      flushParagraph();
      flushList();
      continue;
    }

    const headingMatch = line.match(/^(#{1,4})\s+(.+)$/);
    if (headingMatch) {
      flushParagraph();
      flushList();
      const level = Math.min(headingMatch[1].length, 4);
      blocks.push(`<h${level}>${applyInlineMarkdown(headingMatch[2])}</h${level}>`);
      continue;
    }

    const orderedMatch = line.match(/^\d+\.\s+(.+)$/);
    if (orderedMatch) {
      flushParagraph();
      if (listType && listType !== 'ol') flushList();
      listType = 'ol';
      listItems.push(orderedMatch[1]);
      continue;
    }

    const unorderedMatch = line.match(/^[-*]\s+(.+)$/);
    if (unorderedMatch) {
      flushParagraph();
      if (listType && listType !== 'ul') flushList();
      listType = 'ul';
      listItems.push(unorderedMatch[1]);
      continue;
    }

    flushList();
    paragraph.push(line);
  }

  flushParagraph();
  flushList();
  return blocks.join('');
}

function renderMetricCards(metrics) {
  els.metrics.innerHTML = metrics
    .map(
      (metric) => `
        <article class="metric-card">
          <span>${metric.label}</span>
          <strong>${metric.value}</strong>
        </article>
      `,
    )
    .join('');
}

function renderBars(container, items, formatter = (value) => value) {
  const max = Math.max(...items.map((item) => item.count), 1);
  container.innerHTML = items
    .map(
      (item) => `
        <div class="bar-item">
          <div class="bar-head">
            <span>${formatter(item.name)}</span>
            <span class="bar-meta">${item.count}</span>
          </div>
          <div class="bar-track">
            <div class="bar-fill" style="width:${(item.count / max) * 100}%"></div>
          </div>
        </div>
      `,
    )
    .join('');
}

function renderCharts(charts) {
  els.charts.innerHTML = charts
    .map(
      (chart) => `
        <figure class="chart-card">
          <img src="${chart.url}" alt="${chart.title}" loading="lazy" />
          <figcaption>${chart.title}</figcaption>
        </figure>
      `,
    )
    .join('');
}

function renderReviewQueue(queue) {
  els.reviewCount.textContent = `${queue.total} items`;
  els.reviewQueue.innerHTML = queue.items.length
    ? queue.items
        .map(
          (item) => `
            <article class="review-card">
              <div class="review-meta">
                <span class="priority-pill">${item.priority || 'P?'}</span>
                <span class="meta-chip">${escapeHtml(item.review_reason || 'manual review')}</span>
              </div>
              <p class="review-reason">${escapeHtml(item.summary_reason || '无摘要理由')}</p>
              <p class="review-comment">${escapeHtml(item.content_clean || '无可展示文本')}</p>
            </article>
          `,
        )
        .join('')
    : '<div class="empty-state">当前没有待复核样本。</div>';
}

function setStatusChip(el, rawStatus) {
  const normalized = String(rawStatus || 'missing').toLowerCase();
  el.className = `status-pill status-${normalized}`;
  el.textContent = pipelineLabels[normalized] || normalized.replaceAll('_', ' ');
}

function renderPipelineStatus(status) {
  setStatusChip(els.pipelineStatus, status.status || 'idle');
  els.pipelineTask.textContent = status.task || '-';
  els.pipelinePid.textContent = status.pid ?? '-';
  els.pipelineReturnCode.textContent = status.return_code ?? '-';
  els.pipelineLog.textContent = status.log_tail && status.log_tail.length ? status.log_tail.join('\n') : '暂无运行日志';
}

function configureRunButton(dashboard) {
  const demoMode = dashboard.data_mode === 'demo';
  els.runButton.disabled = demoMode;
  els.runButton.textContent = demoMode ? 'Demo Snapshot' : '运行完整流';
  els.runButton.title = demoMode ? `当前读取 demo 数据：${dashboard.data_source_label}` : '';
}

function renderReport(report) {
  setStatusChip(els.commentaryStatus, report.llm_commentary_status || 'missing');
  els.commentary.textContent = '';
  els.deterministic.textContent = '';
  els.commentary.innerHTML = report.llm_commentary_markdown
    ? markdownToHtml(report.llm_commentary_markdown)
    : '<div class="empty-state">当前没有可展示的 LLM 点评。</div>';
  els.deterministic.innerHTML = report.deterministic_markdown
    ? markdownToHtml(report.deterministic_markdown)
    : '<div class="empty-state">当前没有可展示的规则摘要。</div>';
}

async function fetchJson(path, options) {
  const response = await fetch(path, options);
  if (!response.ok) {
    throw new Error(`${path} => ${response.status}`);
  }
  return response.json();
}

async function loadDashboard() {
  const [dashboard, report, queue, pipeline] = await Promise.all([
    fetchJson('/api/dashboard'),
    fetchJson('/api/insight-report'),
    fetchJson('/api/review-queue?limit=8'),
    fetchJson('/api/pipeline/status'),
  ]);

  els.title.textContent = dashboard.topic.display_name;
  const modeHint = dashboard.data_mode === 'demo' ? ' · Demo Snapshot' : '';
  els.subtitle.textContent = `${dashboard.topic.game} · ${dashboard.topic.version} · 目标角色 ${dashboard.topic.target}${modeHint}`;

  configureRunButton(dashboard);
  renderMetricCards(dashboard.metrics);
  renderBars(els.sentimentBars, dashboard.sentiment_counts, (name) => sentimentLabels[name] || name);
  renderBars(els.sourceBars, dashboard.label_source_counts, (name) => sourceLabels[name] || name);
  renderBars(els.moduleBars, dashboard.top_modules, formatModuleName);
  renderCharts(dashboard.charts);
  renderReviewQueue(queue);
  renderPipelineStatus(pipeline);
  renderReport(report);
}

async function runPipeline() {
  if (els.runButton.disabled) return;
  els.runButton.disabled = true;
  els.runButton.textContent = '启动中…';
  try {
    await fetchJson('/api/pipeline/run', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ task: 'full_pipeline_report' }),
    });
    await loadDashboard();
  } catch (error) {
    window.alert(`启动失败: ${error.message}`);
  } finally {
    els.runButton.disabled = false;
    els.runButton.textContent = '运行完整流';
  }
}

let pollingHandle = null;
function startPolling() {
  if (pollingHandle) window.clearInterval(pollingHandle);
  pollingHandle = window.setInterval(async () => {
    try {
      const pipeline = await fetchJson('/api/pipeline/status');
      renderPipelineStatus(pipeline);
    } catch (error) {
      els.pipelineLog.textContent = `状态刷新失败\n${error.message}`;
    }
  }, 6000);
}

els.refreshButton.addEventListener('click', () => {
  loadDashboard().catch((error) => {
    els.commentary.innerHTML = `<div class="empty-state">加载失败：${escapeHtml(error.message)}</div>`;
  });
});

els.runButton.addEventListener('click', () => {
  runPipeline();
});

loadDashboard().catch((error) => {
  els.commentary.innerHTML = `<div class="empty-state">加载失败：${escapeHtml(error.message)}</div>`;
  els.deterministic.innerHTML = `<div class="empty-state">请确认 FastAPI 后端已启动。<br />${escapeHtml(error.message)}</div>`;
});
startPolling();
