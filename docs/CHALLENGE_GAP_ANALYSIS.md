# Hackathon ideas 1 and 5 — what TraceCare covers

Checked against the "Hacking Healthcare: Rules & Inspiration" brief.

## Idea 1 — "Show the receipts"

> Build an AI that drafts the note from the doctor-patient conversation, where every sentence links back to the
> exact moment in the conversation it came from. It could also flag what is missing, such as a symptom nobody
> asked about. Data: ACI-Bench … includes both human and automatic speech-recognition transcripts, so you can test
> how your system copes with transcription errors.

| Requirement | Status | Where |
|---|---|---|
| Draft the note from the conversation | Done. Patient-reported sections plus the clinician's examination findings, assessment, plan, prescriptions, advice and follow-up, each documented as stated (never added) | Clinical note tab |
| Every sentence links back to its source | Done. Each sentence carries fact IDs; each fact has validated segment IDs and a verbatim quote with character offsets. Unsupported facts are rejected | Fact badges → evidence panel |
| "Exact moment" in the conversation | Done for text: "Show in transcript" jumps to and highlights the turn, showing "turn X of N". Audio timestamps are not possible because inputs are text transcripts | Evidence panel → Transcript tab |
| Flag what is missing | Done. 20 symptom checklists plus a general fallback. Two separate metrics: clinician question coverage and information capture. Missing topics stay counted and are marked "not found — review" | Coverage tab, Review tab |
| "A symptom nobody asked about" | Done. Every symptom the patient mentions is checked for a clinician question or response; unexplored ones are flagged and listed in the note's gap section | Review tab → "Symptoms nobody followed up" |
| Test robustness to transcription errors (ASR) | Done (engineering metric). The pipeline runs on ACI-Bench human and ASR transcripts; results are compared side by side | Evaluation page |
| Swapped or unclear speaker labels | Done. Speaker-plausibility checks; the ACI-Bench sample with swapped labels triggers pending items and a warning | Sample D2N114 |

**Remaining gaps (idea 1)**
- ASR results were produced with the deterministic demo engine. Run `scripts/evaluate_aci.py --provider anthropic --limit N` for Claude numbers (costs API credit).
- The checklists are demo dimensions written by the team, not reviewed by clinicians. A clinical advisor should review them before any real use.
- No audio input or diarisation (out of scope by design).

## Idea 5 — "Do you understand your own medical record?"

> Build a translator from clinical language into everyday language, or into another language. Every simplified
> sentence should point back to the original and flag where the meaning might have changed. A strong demo: show the
> original and the plain version side by side, with the risky simplifications highlighted. Data: PLABA … aligned
> sentence by sentence, so you can check your output line by line.

| Requirement | Status | Where |
|---|---|---|
| Clinical language → everyday language | Done. Record explainer for pasted clinical notes, plus a patient after-visit summary for consultations | Record explainer page; Patient summary tab |
| …or into another language | Done for Swedish (svenska), with Swedish-aware meaning checks and headings. Requires the Claude engine | Language selector |
| Each simplified sentence points back to the original | Done. Plain sentences cite record sentence IDs (R001…) or fact IDs → transcript turns | Side-by-side table; "Show sources" |
| Flag where meaning might have changed | Done. Deterministic checks for lost or added negation, lost hedge/uncertainty, and missing or changed numbers. Original sentences with no plain version are flagged as possibly dropped content | Risk badges; Review tab; "Check meaning" |
| Side-by-side with risky simplifications highlighted | Done. Two columns, with risk levels (check carefully / compare) and a "flagged only" filter | Record explainer |
| Use PLABA to check output line by line | Done. 9,000+ aligned sentence pairs calibrate the checks: false-alarm rate on human rewrites, and detection rate on deliberately corrupted rewrites (negation removed, number changed, hedge removed) | Evaluation page |
| Copy the summary in one go | Done | "Copy summary" / "Copy" / "Copy note" |

**Remaining gaps (idea 5)**
- The meaning checks are heuristics: they catch negation, number and hedge changes, but not every kind of semantic drift (e.g. a wrong body side written in words, or a changed drug name). A clinician must review shared text.
- Swedish *input* records are not yet tested. Output can be Swedish; the source is assumed to be English.
- The demo engine's record "simplification" is only glossary substitution. Real rewriting needs Claude.
- No reading-level score is computed (e.g. LIX for Swedish). This would be an easy addition.
