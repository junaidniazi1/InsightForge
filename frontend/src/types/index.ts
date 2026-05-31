export type SourceType = "file_csv" | "file_excel" | "db_connection";

export type DatasetStatus = "uploaded" | "profiling" | "profiled" | "cleaned" | "error";

// ===========================================================================
// Phase 8 — DB Connections
// ===========================================================================

export interface DbConnection {
  id: string;
  user_id: string;
  name: string;
  db_type: "postgres" | "mysql" | "sqlite";
  host: string;
  port: number;
  database: string;
  username: string;
  created_at: string;
}

export interface TableInfo {
  schema?: string;
  name: string;
  type: string;
}

export interface ColumnInfo {
  name: string;
  type: string;
}

export interface DbConnectionDetail extends DbConnection {
  tables: TableInfo[];
}

export interface TestConnectionResponse {
  success: boolean;
  message: string;
}

export interface ImportResponse {
  dataset_id: string;
  storage_path: string;
  row_count: number;
  background_job_id: string | null;
}


export interface Dataset {
  id: string;
  user_id: string;
  name: string;
  source_type: SourceType;
  storage_path: string | null;
  row_count: number | null;
  column_count: number | null;
  status: DatasetStatus;
  created_at: string;
}

export interface PreviewResponse {
  dataset_id: string;
  name: string;
  source_type: SourceType;
  columns: string[];
  rows: Record<string, unknown>[];
  page: number;
  page_size: number;
  total_rows: number | null;
  truncated: boolean;
}

// ===========================================================================
// Phase 2 — Data Health
// ===========================================================================

export type Severity = "low" | "medium" | "high";

export type SemanticType =
  | "numeric"
  | "categorical"
  | "datetime"
  | "boolean"
  | "text"
  | "id_like";

export interface NumericStats {
  min: number | null;
  max: number | null;
  mean: number | null;
  median: number | null;
  std: number | null;
  q1: number | null;
  q2: number | null;
  q3: number | null;
  skewness: number | null;
  kurtosis: number | null;
}

export interface TopValue {
  value: unknown;
  count: number;
  pct: number;
}

export interface ColumnProfile {
  name: string;
  dtype: string;
  semantic_type: SemanticType;
  null_count: number;
  null_pct: number;
  unique_count: number;
  unique_pct: number;
  sample_values: unknown[];
  memory_bytes: number;
  numeric_stats: NumericStats | null;
  top_values: TopValue[] | null;
}

export interface Issue {
  id: string;
  column: string | null;
  issue_type: string;
  severity: Severity;
  description: string;
  suggested_fix: string;
  fix_options: string[];
}

export interface IqrOutlierColumn {
  column: string;
  outlier_count: number;
  outlier_pct: number;
  lower_bound: number;
  upper_bound: number;
  severity: Severity;
  suggested_fix: string;
  fix_options: string[];
}

export interface ZscoreOutlierColumn {
  column: string;
  outlier_count: number;
  outlier_pct: number;
  threshold: number;
  mean: number;
  std: number;
  severity: Severity;
  suggested_fix: string;
  fix_options: string[];
}

export interface IsolationForestOutliers {
  method: "isolation_forest";
  method_description: string;
  available: boolean;
  reason?: string;
  outlier_row_count?: number;
  outlier_row_pct?: number;
  row_indices_sample?: number[];
  fitted_on_rows?: number;
  sampled?: boolean;
  numeric_columns_used?: string[];
  contamination?: string;
  severity?: Severity;
  suggested_fix?: string;
  fix_options?: string[];
}

export interface OutlierGroups {
  iqr: {
    method: "iqr";
    method_description: string;
    columns: IqrOutlierColumn[];
  };
  zscore: {
    method: "zscore";
    method_description: string;
    columns: ZscoreOutlierColumn[];
  };
  isolation_forest: IsolationForestOutliers;
}

export interface ProfileSummary {
  row_count: number;
  column_count: number;
  duplicate_row_count: number;
  total_memory_bytes: number;
  overall_missing_pct: number;
  sampled: boolean;
  sample_rows_used: number;
  profiled_at: string;
  quality_score: number;
  quality_breakdown: { reason: string; points: number }[];
}

export interface Profile {
  summary: ProfileSummary;
  columns: ColumnProfile[];
  issues: Issue[];
  outliers: OutlierGroups;
}

export type ProfileStatus = "needs_profiling" | "running" | "ready" | "failed";

export interface JobRecord {
  id: string;
  status: "queued" | "running" | "succeeded" | "failed";
  created_at?: string | null;
  updated_at?: string | null;
  error?: string | null;
}

export interface ProfileEnvelope {
  status: ProfileStatus;
  profile?: Profile | null;
  profiled_at?: string | null;
  job?: JobRecord | null;
  error?: string | null;
}

export interface ProfileTriggerResponse {
  job: JobRecord;
  already_running: boolean;
}

// Stash format for accepted fixes (consumed by Phase 3).
export interface AcceptedFix {
  issue_id: string;
  column: string | null;
  issue_type: string;
  fix: string;
}

// ===========================================================================
// Phase 3 — Cleaning
// ===========================================================================

export type OpGroup = "core" | "text" | "datetime" | "column" | "transform";
export type OpAppliesTo = "any" | "numeric" | "categorical" | "datetime" | "text" | "dataset";
export type OpParamType =
  | "string"
  | "number"
  | "boolean"
  | "select"
  | "list"
  | "mapping";

export interface OpParamSchema {
  name: string;
  type: OpParamType;
  label: string;
  description?: string;
  default?: unknown;
  options?: string[];
}

export interface OperationCatalogItem {
  id: string;
  label: string;
  description: string;
  applies_to: OpAppliesTo;
  params: OpParamSchema[];
}

export interface OperationCatalog {
  groups: Partial<Record<OpGroup, OperationCatalogItem[]>>;
}

export interface CleanStep {
  op: string;
  columns: string[];
  params: Record<string, unknown>;
  /** Phase 6 — set by the auto-clean agent so each step can render a "why". */
  rationale?: string;
}

export interface CleanPreviewResponse {
  op: string;
  summary?: string | null;
  log?: Record<string, unknown> | null;
  columns_before: string[];
  columns_after: string[];
  sample_before: Record<string, unknown>[];
  sample_after: Record<string, unknown>[];
  error?: string | null;
}

export interface NullCountDiff {
  before: number;
  after: number;
}

export interface ChangedRow {
  index: number;
  before: Record<string, unknown>;
  after: Record<string, unknown>;
}

export interface CleanDiff {
  rows_before: number;
  rows_after: number;
  columns_before: number;
  columns_after: number;
  duplicates_before: number;
  duplicates_after: number;
  columns_added: string[];
  columns_dropped: string[];
  null_counts: Record<string, NullCountDiff>;
  changed_rows_sample: ChangedRow[];
}

export interface CleanResponse {
  cleaned_version_id: string;
  version_no: number;
  storage_path: string;
  diff: CleanDiff;
  steps_applied: Record<string, unknown>[];
  reprofile_job_id?: string | null;
  quality_score_before?: number | null;
}

// ===========================================================================
// Phase 4 — Dashboard / charts
// ===========================================================================

export type ChartEngine = "plotly" | "echarts" | "kpi";
export type ChartType =
  | "histogram"
  | "box"
  | "violin"
  | "kde"
  | "scatter_3d"
  | "heatmap"
  | "scatter"
  | "line"
  | "bar"
  | "pie"
  | "kpi";

export type FilterKind = "categorical" | "numeric_range" | "datetime_range";

export interface FilterOption {
  column: string;
  kind: FilterKind;
  values?: string[];
  min?: number | string;
  max?: number | string;
}

export interface FilterOptionsResponse {
  version_id: string;
  filters: FilterOption[];
}

export interface FilterClause {
  column: string;
  type: "in" | "range";
  values?: unknown[];
  min?: number | string | null;
  max?: number | string | null;
}

export interface ChartEncoding {
  x?: string;
  y?: string;
  color?: string;
  agg?: string;
  columns?: string[];
  method?: string;
}

export interface ChartPresentation {
  /** Named palette from CHART_THEME.PALETTES. */
  palette?: string;
  /** Override axis labels (empty / undefined uses column names). */
  x_label?: string;
  y_label?: string;
  /** Show / hide the legend (default depends on chart type). */
  legend?: boolean;
}

export interface ChartSpec {
  chart_type: ChartType;
  encoding: ChartEncoding;
  title?: string | null;
  bins?: number | null;
  top_n?: number | null;
  filters?: FilterClause[];
  /** Phase 6 — presentation-only (no backend refetch when only this changes). */
  presentation?: ChartPresentation;
}

export interface ChartSuggestion {
  chart_type: ChartType;
  engine: ChartEngine;
  title: string;
  encoding: ChartEncoding;
  rationale: string;
  score: number;
  bins?: number | null;
  top_n?: number | null;
}

export interface ChartSuggestionsResponse {
  version_id: string;
  version_label: string;
  kpis: ChartSuggestion[];
  suggestions: ChartSuggestion[];
}

export interface ChartDataResponse {
  chart_type: ChartType;
  engine: ChartEngine;
  data: Record<string, unknown>;
  meta: Record<string, unknown>;
}

// --- Dashboards ---

export interface DashboardChart {
  id: string;
  dashboard_id: string;
  chart_type: ChartType;
  config: ChartSpec;
  position: number;
}

export interface Dashboard {
  id: string;
  user_id: string;
  dataset_id: string;
  name: string;
  layout: Record<string, unknown>;
  created_at: string;
  charts: DashboardChart[];
}

export interface DashboardListItem {
  id: string;
  name: string;
  dataset_id: string;
  layout: Record<string, unknown>;
  created_at: string;
  chart_count: number;
}

// Grid layout item, shape compatible with react-grid-layout.
export interface GridLayoutItem {
  i: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface DashboardLayout {
  items: GridLayoutItem[];
  filters?: FilterClause[];
}

// ===========================================================================
// Phase 5 — AI
// ===========================================================================

export interface AISummaryResponse {
  version_id: string;
  version_label: string;
  text: string;
  created_at?: string | null;
  cached: boolean;
}

export type AIStoryResponse = AISummaryResponse;

export type FindingSeverity = "info" | "notable" | "concern";

export interface AIFinding {
  title: string;
  detail: string;
  severity: FindingSeverity;
  columns?: string[] | null;
}

export interface AISuggestedAnalysis {
  label: string;
  question?: string | null;
}

export interface AIInsightsResponse {
  version_id: string;
  version_label: string;
  findings: AIFinding[];
  suggested_analyses: AISuggestedAnalysis[];
  created_at?: string | null;
  cached: boolean;
}

export interface AIResultTable {
  name?: string | null;
  columns: string[];
  rows: Record<string, unknown>[];
  truncated: boolean;
  row_count: number;
}

export interface AIAskResponse {
  version_id: string;
  version_label: string;
  question: string;
  answer: string;
  analysis_spec: Record<string, unknown>;
  result_table: AIResultTable;
  suggested_chart?: Record<string, unknown> | null;
}

export interface AIConversationTurn {
  role: "user" | "assistant" | "system";
  content: string;
  created_at: string;
  payload?: {
    answer?: string;
    analysis_spec?: Record<string, unknown>;
    result_table?: AIResultTable;
    suggested_chart?: Record<string, unknown> | null;
  } | null;
}

export interface AIConversationResponse {
  dataset_id: string;
  turns: AIConversationTurn[];
}

// ===========================================================================
// Phase 6 — Auto-clean agent
// ===========================================================================

export interface AutoPlanStep {
  op: string;
  columns: string[];
  params: Record<string, unknown>;
  rationale: string;
}

export interface AutoPlanResponse {
  version_id: string;
  version_label: string;
  steps: AutoPlanStep[];
  summary: string;
  explanation?: string | null;
}

// ===========================================================================
// Phase 7 — Analyst Workbench
// ===========================================================================

export interface WorkbenchChart {
  title: string;
  spec: ChartSpec;
  data: ChartDataResponse;
}

export interface WorkbenchEnvelope<R = Record<string, unknown>> {
  result: R;
  charts: WorkbenchChart[];
  interpretation: string;
}

export interface WorkbenchErrorPayload {
  reason: string;
  message: string;
}

// ----- Describe -----
export interface DescribeColumnStats {
  name: string;
  count: number;
  missing: number;
  missing_pct: number;
  mean: number;
  median: number;
  mode: number | null;
  std: number;
  variance: number;
  min: number;
  max: number;
  range: number;
  q1: number;
  q3: number;
  iqr: number;
  skewness: number;
  kurtosis: number;
  coef_variation: number | null;
}

export interface DescribeResult {
  columns: DescribeColumnStats[];
  n_rows: number;
}

// ----- Correlation -----
export type CorrelationMethod = "pearson" | "spearman" | "kendall";

export interface CorrelationPair {
  a: string;
  b: string;
  r: number;
  p_value: number;
  n: number;
  significant: boolean;
}

export interface CorrelationResult {
  method: CorrelationMethod;
  columns: string[];
  matrix: (number | null)[][];
  top_pairs: CorrelationPair[];
}

// ----- Hypothesis tests -----
export type HypothesisTest =
  | "ttest_one"
  | "ttest_two"
  | "anova"
  | "chi_square"
  | "mann_whitney";

export interface HypothesisRecommendation {
  recommendation: HypothesisTest | null;
  reason: string;
}

// ----- Time-series -----
export type TsFrequency = "D" | "W" | "ME" | "QE" | "YE";
export type TsAgg = "mean" | "sum" | "min" | "max" | "median";
export type TsMode = "resample" | "decompose" | "acf_pacf" | "stationarity";

// ----- Phase 7B ML -----

export interface ClusterProfile {
  cluster: number;
  size: number;
  size_pct: number;
  means: Record<string, number>;
  top_distinguishing_features: string[];
}

export interface ClusteringResult {
  best_k: number;
  ks: number[];
  inertias: number[];
  silhouettes: number[];
  best_silhouette: number;
  cluster_sizes: Record<string, number>;
  cluster_profiles: ClusterProfile[];
  features: string[];
  rows_used: number;
  rows_dropped: number;
}

export interface PCAComponentLoading {
  feature: string;
  loading: number;
}

export interface PCAComponent {
  component: string;
  explained_variance: number;
  cumulative: number;
  loadings: PCAComponentLoading[];
}

export interface PCAResult {
  features: string[];
  n_components: number;
  explained_variance_ratio: number[];
  cumulative_variance: number[];
  components: PCAComponent[];
  n_for_90pct: number;
  rows_used: number;
  rows_dropped: number;
}

export interface AnomalyFlaggedRow {
  __index: number;
  __score: number;
  [feature: string]: number;
}

export interface AnomalyResult {
  features: string[];
  contamination: number;
  threshold: number;
  flagged_count: number;
  flagged_pct: number;
  flagged_rows: AnomalyFlaggedRow[];
  truncated: boolean;
  max_flagged: number;
  rows_used: number;
  rows_dropped: number;
}

export interface FeatureImportanceItem {
  feature: string;
  importance: number;
}

export interface FeatureImportanceResult {
  target: string;
  problem_type: "regression" | "classification";
  oob_score: number;
  feature_importances: FeatureImportanceItem[];
  top_n: number;
  dropped_features: string[];
  n_rows_used: number;
  n_features_used: number;
}

export type ModelProblemType = "regression" | "classification";

export interface ModelMetricsRegression {
  model: string;
  r2: number;
  rmse: number;
  mae: number;
}

export interface ModelMetricsClassification {
  model: string;
  accuracy: number;
  precision_macro: number;
  recall_macro: number;
  f1_macro: number;
}

export interface ModelResult {
  target: string;
  problem_type: ModelProblemType;
  classes?: string[];
  n_train: number;
  n_test: number;
  metrics: Array<ModelMetricsRegression | ModelMetricsClassification>;
  best_model: string;
  confusion_matrix?: number[][];
  feature_importances: FeatureImportanceItem[];
  predictions_count: number;
  dropped_features: string[];
  warnings: string[];
}
