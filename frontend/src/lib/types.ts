export interface RepositoryOut {
  id: string;
  name: string;
  source_type: string;
  url: string | null;
  local_path: string | null;
  default_branch: string | null;
  created_at: string;
  updated_at: string;
  snapshot_count: number;
}

export interface RepositoryList {
  items: RepositoryOut[];
  total: number;
}

export interface RefOut {
  name: string;
  sha: string;
}

export interface AnalysisOptions {
  run_baseline_tests: boolean;
  run_modified_tests: boolean;
  collect_coverage: boolean;
  targeted_verification: boolean;
  hypothesis_max_examples: number;
  hypothesis_deadline_ms: number;
  property_code: string;
  property_target: string;
}

export interface AnalysisRun {
  id: string;
  repository_id: string;
  repository_name: string | null;
  baseline_ref: string | null;
  target_ref: string | null;
  resolved_baseline_sha: string | null;
  resolved_target_sha: string | null;
  status: string;
  stage: string | null;
  stage_detail: string | null;
  error_message: string | null;
  attempts: number;
  options: Record<string, unknown>;
  summary: RunSummary;
  runtime_info: {
    docker?: boolean;
    worker_image?: string;
    python_version?: string;
    dependencies?: string;
  } | null;
  created_at: string;
  started_at: string | null;
  completed_at: string | null;
  duration_seconds: number | null;
}

export interface RunSummary {
  changed_files?: number;
  changed_scopes?: number;
  uncovered_changed_lines?: number;
  proven_failures?: number;
  behavior_divergences?: number;
  regressions?: number;
  runtime_status?: string;
  runtime_note?: string;
  tests?: {
    baseline_run?: boolean;
    modified_run?: boolean;
    baseline_outcome?: string | null;
    modified_outcome?: string | null;
    count?: number;
    categories?: Record<string, number>;
  };
  verifications?: {
    attempted?: number;
    classifications?: Record<string, number>;
  };
}

export interface AnalysisList {
  items: AnalysisRun[];
  total: number;
}

export interface ChangedScopeOut {
  id: string;
  kind: string;
  name: string;
  qualname: string;
  start_line: number;
  end_line: number;
  changed_lines: number[];
  executable_lines: number[];
  covered_changed_lines: number[];
  uncovered_changed_lines: number[];
  coverage_status: string;
}

export interface ChangedFileOut {
  id: string;
  path: string;
  old_path: string | null;
  change_type: string;
  language: string | null;
  supported: boolean;
  parse_error: string | null;
  added_lines: number[];
  removed_lines: number[];
  coverage: {
    available?: boolean;
    reason?: string;
    ambiguous_context?: boolean;
    lines?: Record<string, { status: string; tests: string[] }>;
  };
  scopes: ChangedScopeOut[];
}

export interface TestRecordOut {
  id: string;
  node_id: string;
  name: string;
  baseline_outcome: string | null;
  modified_outcome: string | null;
  category: string;
  duration_ms: number | null;
  error_excerpt: string | null;
  executed_changed_lines: Record<string, number[]>;
  ran_changed_code: boolean;
}

export interface VerificationAttemptOut {
  id: string;
  scope_id: string | null;
  file_path: string;
  function_qualname: string;
  kind: string;
  classification: string;
  rationale: string | null;
  input_payload: Record<string, string> | null;
  baseline_outcome: { kind: string; repr?: string; type?: string; message?: string; traceback?: string } | null;
  modified_outcome: { kind: string; repr?: string; type?: string; message?: string; traceback?: string } | null;
  property_code: string | null;
  reproducible: boolean | null;
  minimized: boolean;
  duration_ms: number | null;
  environment: Record<string, unknown>;
  detail: Record<string, unknown>;
}

export interface JobEventOut {
  id: string;
  ts: string;
  level: string;
  stage: string | null;
  message: string;
  detail: Record<string, unknown>;
}

export interface GraphNode {
  id: string;
  type: string;
  label: string;
  data: Record<string, unknown>;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  type: string;
  data: Record<string, unknown>;
}

export interface GraphOut {
  nodes: GraphNode[];
  edges: GraphEdge[];
  truncated: boolean;
}

export interface HealthOut {
  status: string;
  version: string;
  database: string;
  docker: string;
  detail: Record<string, unknown>;
}
