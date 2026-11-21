// Mirrors backend/app/schemas/*.py. Keep in sync with the Pydantic models.

export type Speaker = "clinician" | "patient" | "other" | "unknown";
export type Polarity = "positive" | "negative" | "uncertain";
export type Certainty = "explicit" | "inferred" | "unclear";
export type EvidenceStatus = "source_linked" | "needs_review" | "rejected";
export type QuoteMatch = "exact" | "normalized" | "not_found";
export type ProviderName = "demo" | "anthropic";

export type ItemStatus =
  | "asked_and_addressed"
  | "asked_but_unanswered"
  | "volunteered_not_asked"
  | "not_found_in_transcript"
  | "unclear_needs_review"
  | "not_applicable";

export type ReviewState = "provisional" | "needs_review" | "reviewed";

export interface TranscriptSegment {
  segment_id: string;
  speaker: Speaker;
  speaker_label: string | null;
  text: string;
  start_char: number;
  end_char: number;
  turn_index: number;
}

export interface EvidenceReference {
  segment_id: string;
  speaker: Speaker | null;
  quote: string;
  quote_match: QuoteMatch;
  start_char: number | null;
  end_char: number | null;
  segment_exists: boolean;
}

export interface MedicalFact {
  fact_id: string;
  category: string;
  concept: string;
  normalized_value: string;
  polarity: Polarity;
  certainty: Certainty;
  temporality: string;
  duration: string | null;
  frequency: string | null;
  severity: string | null;
  location: string | null;
  context: string | null;
  source_segment_ids: string[];
  supporting_quote: string;
  evidence_status: EvidenceStatus;
  evidence: EvidenceReference[];
  review_notes: string[];
}

export interface SymptomMention {
  symptom_id: string;
  concept: string;
  polarity: Polarity;
  fact_ids: string[];
  source_segment_ids: string[];
  supporting_quote: string;
  template_id: string | null;
  evidence_status: EvidenceStatus;
  evidence: EvidenceReference[];
  review_notes: string[];
}

export interface ChecklistItem {
  item_id: string;
  label: string;
  description: string | null;
  example_questions: string[];
}

export interface ChecklistTemplate {
  template_id: string;
  version: string;
  display_name: string;
  description: string;
  category: string;
  trigger_concepts: string[];
  status: string;
  review_required: boolean;
  disclaimer: string;
  items: ChecklistItem[];
}

export interface ChecklistAssessment {
  item_id: string;
  label: string;
  status: ItemStatus;
  clinician_question_segment_ids: string[];
  clinician_question_quotes: string[];
  information_segment_ids: string[];
  information_quotes: string[];
  question_evidence: EvidenceReference[];
  information_evidence: EvidenceReference[];
  fact_ids: string[];
  proposed_status: ItemStatus | null;
  rationale: string | null;
  review_state: ReviewState;
  reviewed: boolean;
  not_applicable_reason: string | null;
  reviewer_note: string | null;
  validation_notes: string[];
}

export interface CoverageMetric {
  label: string;
  numerator: number;
  denominator: number;
  percentage: number | null;
  available: boolean;
  message: string | null;
}

export interface CoverageReport {
  coverage_available: boolean;
  message: string | null;
  template_id: string | null;
  template_version: string | null;
  template_name: string | null;
  template_status: string | null;
  question_coverage: CoverageMetric | null;
  information_capture: CoverageMetric | null;
  assessable_count: number;
  pending_review_count: number;
  not_applicable_count: number;
  not_found_count: number;
  status_counts: Record<string, number>;
  is_provisional: boolean;
  review_status: "provisional" | "reviewed";
  items: ChecklistAssessment[];
  disclaimer: string;
}

export interface MeaningCheck {
  check: "negation" | "uncertainty" | "number";
  message: string;
}

export interface GeneratedStatement {
  statement_id: string;
  section: string;
  text: string;
  fact_ids: string[];
  checklist_item_id: string | null;
  kind: "fact" | "coverage_gap";
  needs_review: boolean;
  review_notes: string[];
  meaning_checks: MeaningCheck[];
}

export interface NoteSection {
  section_id: string;
  heading: string;
  statements: GeneratedStatement[];
  empty_message: string;
}

export interface ClinicalNote {
  title: string;
  status: string;
  disclaimer: string;
  sections: NoteSection[];
}

export interface PatientExplanation {
  language: string;
  disclaimer: string;
  intro: string;
  statements: GeneratedStatement[];
  not_established: string[];
}

export interface ValidationFinding {
  code: string;
  severity: "error" | "warning" | "info";
  message: string;
  ref_type: string | null;
  ref_id: string | null;
}

export interface PatientSummary {
  display_name: string | null;
  name_source: "entered" | "detected" | null;
  name_evidence: EvidenceReference | null;
  temp_personnummer: string | null;
  birth_date: string | null;
  age: number | null;
  is_synthetic: boolean;
}

export interface PatientInfo {
  display_name?: string;
  temp_personnummer?: string;
}

export interface AnalyzeResponse {
  encounter_id: string;
  created_at: string;
  status: "provisional_review_required" | "reviewed";
  provider: ProviderName;
  provider_label: string;
  model: string | null;
  language: string;
  patient: PatientSummary;
  chief_concern: string | null;
  segments: TranscriptSegment[];
  facts: MedicalFact[];
  rejected_facts: MedicalFact[];
  symptoms: SymptomMention[];
  coverage_reports: CoverageReport[];
  clinical_note: ClinicalNote;
  patient_explanation: PatientExplanation;
  validation_findings: ValidationFinding[];
  parse_warnings: string[];
  warnings: string[];
  persisted: boolean;
}

export interface AnalyzeRequest {
  transcript: string;
  language: "en";
  template_ids: string[];
  provider?: ProviderName;
  patient?: PatientInfo;
}

export interface CoverageItemUpdate {
  status?: ItemStatus;
  not_applicable_reason?: string;
  confirm?: boolean;
  reviewer_note?: string;
}

export interface PublicConfig {
  providers: ProviderName[];
  default_provider: ProviderName | null;
  model: string | null;
  demo_gate_enabled: boolean;
  max_transcript_chars: number;
}

export interface SampleSummary {
  sample_id: string;
  title: string;
  source: "synthetic" | "aci-bench";
  description: string;
  suggested_template_id: string | null;
  patient_name?: string | null;
  citation?: string;
}

export interface Sample extends SampleSummary {
  transcript: string;
  reference_note?: string;
}
