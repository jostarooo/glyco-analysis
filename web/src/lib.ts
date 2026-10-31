import project from "./data/project.json";
import metrics from "./data/metrics.json";
import tools from "./data/tools.json";
import boundaries from "./data/boundaries.json";

export interface Track { id: string; name: string; what: string; base: string; }
export interface Term { code: string; plain: string; }
export interface Gate { no: number; name: string; state: string; artifact: string; }
export interface SourceMeta { role: string; path: string; sha256: string; byte_count: number; }
export interface MetricRow {
  metric_id: string;
  track: string;
  subject: string;
  metric: string;
  unit: string;
  local: { value: number; std: number | null; n: number | null; denominator: number | null; source: string; locator: string };
  comparison: { kind: string; delta_local_minus_reference?: number; reason?: string; scope_note?: string };
  reference: { value: number; std: number | null; label: string; track: string; unit: string; citation: string } | null;
}
export interface ToolRow {
  group: string; tool: string; method: string; url: string;
  http_status: string; class: string; error: string;
}
export interface FeasibilityRow {
  revised_category: string; original_category: string;
  blocking_tools: string; w3_classes: string; decision_reason: string;
}
export interface TaskRow {
  task_id: string; site: string; steps: string; tools: string; question: string;
  feasibility: FeasibilityRow;
}
export interface RecheckBlocker { tool: string; class: string; root_cause: string; }

export const projectData = project as unknown as {
  schema_version: string;
  head_commit: string;
  project: { title: string; one_liner: string; tracks: Track[] };
  terms: Term[];
  gates: Gate[];
  counts: {
    tools_total: number; tools_ok: number; tools_alive: number;
    tasks_total: number; f2_csv_count: number; f2_csv_bytes: number;
    metric_rows: number; scorecard_status: string; scorecard_schema: string;
  };
  sources: SourceMeta[];
  generated_by: string;
};

export const metricsData = metrics as unknown as {
  schema_version: string;
  scorecard_status: string;
  policy: Record<string, string>;
  validations: Record<string, number>;
  benchmark_pool: Record<string, unknown> & {
    evaluation_rows: number; experimental_positive: number;
    unannotated_control: number; inferred_display_only: number; proteins: number;
  };
  f1_comparability_caveat: string;
  f1_methods: Array<{
    id: string; label: string; mcc: number; mcc_defined: boolean;
    roc_auc: number | null; control_specificity: number;
    confusion: { tp: number; fp: number; tn: number; fn: number };
  }>;
  f1_esm150_repro: {
    mcc: number; reference_mcc: number; delta: number;
    row_count: number; confusion: { tp: number; fp: number; tn: number; fn: number };
  };
  f2: {
    model: { embedding: number[]; layers: number; hidden_dim: number; relation_channels: number; pooling: string[]; mlp: number[] };
    training: { optimizer: string; lr: number; weight_decay: number; batch_size: number; epochs: number; scheduler: string; T_max: number };
    vocab: { active_units: number; relation_ids: number; embedding_rows: number };
    tasks: Record<string, {
      rows: number; split_counts: Record<string, number>; label_counts: Record<string, number>;
      selection_metric: string; report_metric: string;
      aggregate: Record<string, { mean: number; std: number; n: number }>;
      num_classes: number;
    }>;
    torchdrug_installed: boolean;
    torchdrug_notes: string[];
  };
  f3: {
    model: string; tasks_run: number; max_rounds: number; num_ctx: number;
    exact_sequence: number; all_expected_called: number; any_expected_called: number;
    tasks_with_tool_call: number; tasks_with_final_answer: number;
    tool_call_successes: number; tool_calls: number; grader: string;
  };
  metrics: MetricRow[];
  sources: SourceMeta[];
};

export const toolsData = tools as unknown as {
  schema_version: string;
  snapshot_note: string;
  tools: ToolRow[];
  tool_summary: {
    total_tools: number; directly_ok: number; service_alive: number;
    service_alive_rate: number; class_counts: Record<string, number>;
    by_group: Record<string, { total: number; ok: number; alive: number }>;
  };
  recheck: {
    total_blocked_tools: number;
    recheck_class_counts: Record<string, number>;
    service_reachable: number; default_transport_ok: number;
    task_fit_counts: Record<string, number>;
    probe_accepted_tools: string[];
    persistent_blockers: RecheckBlocker[];
    generated_at: string | null;
  };
  tasks: TaskRow[];
  task_summary: { total_tasks: number; step_distribution: Record<string, number> };
  sources: SourceMeta[];
};

export const boundariesData = boundaries as unknown as {
  schema_version: string;
  scorecard_boundaries: string[];
  policy: Record<string, string>;
  f1_pool: Record<string, unknown> & {
    evaluation_rows: number; experimental_positive: number;
    unannotated_control: number; inferred_display_only: number; proteins: number;
  };
  f1_caveat: string;
  f2_torchdrug_notes: string[];
  f2_data_url_fixes: string[];
  f3_grader: string;
  recheck_notes: string[];
  sources: SourceMeta[];
};

export function shortCommit(commit: string): string {
  return commit.slice(0, 7);
}

export function formatPct(n: number, digits = 2): string {
  return (n * 100).toFixed(digits) + "%";
}