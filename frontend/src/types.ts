/**
 * TypeScript types mirroring backend/app/schemas.py.
 * Keep field names identical so request/response payloads stay in sync.
 */

export type Role = 'admin' | 'annotator' | 'clinician'
export type CancerType = 'BRCA' | 'COAD' | 'LUAD'

export interface FactSpan {
  value: string | number | boolean | Record<string, unknown> | null
  quote: string | null
  start_char: number | null
  end_char: number | null
}

export interface FactSheet {
  diagnosis_or_histologic_type: FactSpan | null
  grade: FactSpan | null
  tumor_size: FactSpan | null
  margins: FactSpan | null
  lymph_nodes_positive: FactSpan | null
  lymph_nodes_examined: FactSpan | null
  pathologic_tnm_stage: FactSpan | null
  biomarkers: FactSpan | null
}

export interface ExplanationSentence {
  sentence: string
  source_fact_keys: string[]
  quote: string | null
}

export interface ExplanationPayload {
  sentences: ExplanationSentence[]
}

export interface UserOut {
  id: number
  email: string
  name: string
  role: Role
}

export interface SessionOut {
  session_token: string
  expires_at: string
  user: UserOut
}

export interface ReportSummary {
  id: number
  tcga_barcode: string
  cancer_type: string
  project_id: string
  source: string
}

export interface ReportDetail extends ReportSummary {
  report_text: string
  gdc_metadata?: Record<string, unknown> | null
}

export interface GlossaryTerm {
  term: string
  definition: string
  short?: string | null
  aliases?: string[]
}

export interface ExplainResponse {
  report_id: number
  generation_id: number
  report_text: string
  facts: FactSheet
  explanation: ExplanationPayload
  reading_level_original: number | null
  reading_level_explanation: number | null
  provider?: string | null
  model?: string | null
  is_fallback?: boolean
  fallback_reason?: string | null
  requested_provider?: string | null
  requested_model?: string | null
  glossary?: GlossaryTerm[]
}

export interface AnnotationTaskOut {
  id: number
  batch_id: number
  report_id: number
  assignee_id: number
  status: string
  gold_labels: Record<string, FactSpan | null> | null
  completed_at: string | null
  report?: ReportDetail | null
}

export interface ReviewScores {
  accuracy: number
  completeness: number
  harm_potential: number
}

export interface ReviewTaskOut {
  id: number
  batch_id: number
  generation_id: number
  assignee_id: number
  status: string
  scores: ReviewScores | null
  flagged_sentences: number[] | null
  comments: string | null
  completed_at: string | null
  report_text?: string | null
  cancer_type?: string | null
  tcga_barcode?: string | null
  facts?: FactSheet | Record<string, unknown> | null
  explanation?: ExplanationPayload | Record<string, unknown> | null
}

export interface EvaluationSetOut {
  id: number
  name: string
  cancer_types: string[]
  report_ids: number[]
  created_at: string
}

export interface TaskBatchOut {
  id: number
  name: string
  batch_type: string
  evaluation_set_id: number | null
  assigned_user_ids: number[]
  status: string
  created_at: string
}

export interface ProgressOut {
  annotation_pending: number
  annotation_completed: number
  review_pending: number
  review_completed: number
  total_reports: number
  total_generations: number
}

export interface MetricWithCI {
  name: string
  value: number
  n: number
  ci_low: number
  ci_high: number
  method: string
}

export interface ClinicianScoreSummary {
  accuracy: MetricWithCI | null
  completeness: MetricWithCI | null
  harm_potential: MetricWithCI | null
  n_reviews: number
}

export interface InterRaterSummary {
  available: boolean
  n_items_with_multiple_raters: number
  n_pairs: number
  metric: MetricWithCI | null
}

export interface FailureExample {
  generation_id: number
  report_id: number
  cancer_type?: string | null
  check_name: string
  detail?: string | null
}

export interface ResultsSummary {
  metrics: MetricWithCI[]
  by_cancer_type: Record<string, MetricWithCI[]>
  by_field?: Record<string, MetricWithCI[]>
  auto_check_runs: number
  generations: number
  gold_annotations: number
  clinician_reviews: number
  clinician_scores?: ClinicianScoreSummary | null
  inter_rater?: InterRaterSummary | null
  failure_examples?: FailureExample[]
  fallback_generations?: number
  fallback_excluded_from_metrics?: boolean
}

export interface AboutOut {
  title: string
  body: string
}

/** Human-readable labels for fact sheet fields (interview explainability). */
export const FACT_FIELD_LABELS: Record<keyof FactSheet, string> = {
  diagnosis_or_histologic_type: 'Diagnosis / histologic type',
  grade: 'Grade',
  tumor_size: 'Tumor size',
  margins: 'Margins',
  lymph_nodes_positive: 'Lymph nodes positive',
  lymph_nodes_examined: 'Lymph nodes examined',
  pathologic_tnm_stage: 'Pathologic TNM stage',
  biomarkers: 'Biomarkers',
}

export const FACT_FIELD_KEYS = Object.keys(FACT_FIELD_LABELS) as (keyof FactSheet)[]

export const CANCER_OPTIONS: { code: CancerType; label: string }[] = [
  { code: 'BRCA', label: 'Breast' },
  { code: 'COAD', label: 'Colon' },
  { code: 'LUAD', label: 'Lung' },
]

export const DEMO_TOKENS = [
  { token: 'DEMO_ADMIN_TOKEN', role: 'admin' as Role, label: 'Admin' },
  { token: 'DEMO_ANNOTATOR_TOKEN', role: 'annotator' as Role, label: 'Annotator' },
  { token: 'DEMO_CLINICIAN_TOKEN', role: 'clinician' as Role, label: 'Clinician' },
]
