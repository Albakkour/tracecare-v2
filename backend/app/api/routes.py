from __future__ import annotations

import logging
import time

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel

from app.core.config import get_settings
from app.core.security import (
    analysis_rate_limiter,
    check_password,
    client_ip,
    issue_session_token,
    require_demo_access,
)
from app.llm.base import ProviderError
from app.llm.factory import get_provider
from app.schemas.coverage import ChecklistTemplate
from app.schemas.outputs import AnalyzeRequest, AnalyzeResponse, CoverageItemUpdate
from app.services import samples
from app.services.checklist_service import get_templates, load_registry, registry_notice
from app.services.coverage_calculator import calculate_coverage
from app.services.patient_identity import contains_real_personnummer, generate_temp_personnummer
from app.services.pipeline import regenerate_after_review, run_analysis
from app.storage.database import check_db
from app.storage.repositories import EncounterRepository

logger = logging.getLogger("tracecare.api")
router = APIRouter(prefix="/api")
repo = EncounterRepository()


@router.get("/health")
def health() -> dict:
    return {"status": "ok", "service": "tracecare-api"}


@router.get("/ready")
def ready() -> dict:
    s = get_settings()
    if not check_db():
        raise HTTPException(status_code=503, detail="Database not reachable.")
    problems = s.production_problems() if s.is_production else []
    # Reports problem descriptions only — never values of secrets or connection strings.
    return {"status": "ready" if not problems else "misconfigured", "database": "ok", "config_problems": problems}


@router.get("/patients/temp-id")
def temp_patient_id() -> dict:
    """A new temporary personnummer (YYYYMMDD-TNNN). Cannot collide with a real personal identity number."""
    return {"temp_personnummer": generate_temp_personnummer()}


@router.get("/config")
def public_config() -> dict:
    s = get_settings()
    return {
        "providers": s.available_providers(),
        "default_provider": s.default_provider(),
        "model": s.anthropic_model if s.anthropic_configured else None,
        "demo_gate_enabled": bool(s.demo_access_password),
        "max_transcript_chars": s.max_transcript_chars,
    }


class SessionRequest(BaseModel):
    password: str


@router.post("/session")
def create_session(body: SessionRequest, request: Request) -> dict:
    s = get_settings()
    if not s.demo_access_password:
        return {"token": None, "expires_at": None, "gate_enabled": False}
    analysis_rate_limiter.check("session", client_ip(request))
    if not check_password(body.password):
        raise HTTPException(status_code=401, detail="Incorrect demo access password.")
    token, expires = issue_session_token()
    return {"token": token, "expires_at": expires, "gate_enabled": True}


@router.get("/templates")
def list_templates() -> dict:
    return {"notice": registry_notice(), "templates": [t.model_dump() for t in load_registry().values()]}


@router.get("/samples")
def list_samples() -> dict:
    return {"samples": samples.list_samples()}


@router.get("/samples/{sample_id}")
def get_sample(sample_id: str) -> dict:
    sample = samples.get_sample(sample_id)
    if sample is None:
        raise HTTPException(status_code=404, detail="Sample not found.")
    return sample


@router.post("/analyze", response_model=AnalyzeResponse, dependencies=[Depends(require_demo_access)])
def analyze(body: AnalyzeRequest, request: Request) -> AnalyzeResponse:
    s = get_settings()
    if len(body.transcript) > s.max_transcript_chars:
        raise HTTPException(status_code=413, detail=f"Transcript is too long ({len(body.transcript)} characters; "
                                                    f"maximum {s.max_transcript_chars}).")
    if contains_real_personnummer(body.transcript):
        raise HTTPException(status_code=422, detail="The transcript appears to contain a personal identity number "
                                                    "(personnummer). Remove it: this prototype accepts synthetic data only.")
    try:
        templates = get_templates(body.template_ids)
    except KeyError as exc:
        raise HTTPException(status_code=400, detail=f"Unknown template ID(s): {exc.args[0]}") from exc
    try:
        provider = get_provider(body.provider, s)
    except ProviderError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.user_message) from exc

    analysis_rate_limiter.check("analyze", client_ip(request))
    started = time.monotonic()
    try:
        result = run_analysis(body.transcript, templates, provider, body.language, body.patient)
    except ProviderError as exc:
        logger.warning("analysis failed provider=%s kind=%s", provider.name, exc.kind)
        raise HTTPException(status_code=exc.status_code, detail=exc.user_message) from exc

    try:
        repo.save(result)
        result.persisted = True
    except Exception as exc:  # persistence is best-effort; never fail the analysis because of it
        logger.error("could not persist encounter %s: %s", result.encounter_id, type(exc).__name__)
    logger.info("analysis encounter=%s provider=%s segments=%d facts=%d rejected=%d ms=%d",
                result.encounter_id, result.provider, len(result.segments), len(result.facts),
                len(result.rejected_facts), (time.monotonic() - started) * 1000)
    return result


def _load(encounter_id: str) -> AnalyzeResponse:
    try:
        result = repo.get(encounter_id)
    except Exception as exc:
        logger.error("could not load encounter %s: %s", encounter_id, type(exc).__name__)
        raise HTTPException(status_code=503, detail="Encounter storage unavailable.") from exc
    if result is None:
        raise HTTPException(status_code=404, detail="Encounter not found.")
    return result


@router.get("/encounters/{encounter_id}", response_model=AnalyzeResponse, dependencies=[Depends(require_demo_access)])
def get_encounter(encounter_id: str) -> AnalyzeResponse:
    return _load(encounter_id)


@router.delete("/encounters/{encounter_id}", dependencies=[Depends(require_demo_access)])
def delete_encounter(encounter_id: str) -> dict:
    if not repo.delete(encounter_id):
        raise HTTPException(status_code=404, detail="Encounter not found.")
    return {"deleted": encounter_id}


@router.patch("/encounters/{encounter_id}/coverage-items/{item_id}", response_model=AnalyzeResponse,
              dependencies=[Depends(require_demo_access)])
def update_coverage_item(encounter_id: str, item_id: str, body: CoverageItemUpdate,
                         template_id: str | None = Query(default=None)) -> AnalyzeResponse:
    result = _load(encounter_id)
    report_idx = next((i for i, r in enumerate(result.coverage_reports)
                       if r.template_id and (template_id is None or r.template_id == template_id)
                       and any(it.item_id == item_id for it in r.items)), None)
    if report_idx is None:
        raise HTTPException(status_code=404, detail="Checklist item not found in this encounter.")
    report = result.coverage_reports[report_idx]
    item = next(it for it in report.items if it.item_id == item_id)

    new_status = body.status or item.status
    if new_status == "not_applicable":
        reason = (body.not_applicable_reason or "").strip()
        if not reason:
            raise HTTPException(status_code=422, detail="A reason is required to mark an item not applicable.")
        item.not_applicable_reason = reason
    else:
        item.not_applicable_reason = None
    if body.status and body.status != item.status:
        item.validation_notes.append(f"Reviewer changed status from '{item.status}' to '{body.status}'.")
    item.status = new_status
    if body.reviewer_note is not None:
        item.reviewer_note = body.reviewer_note.strip() or None
    # Any explicit reviewer decision counts as review, except leaving the item unclear.
    if new_status == "unclear_needs_review":
        item.reviewed, item.review_state = False, "needs_review"
    elif body.confirm or body.status:
        item.reviewed, item.review_state = True, "reviewed"

    template: ChecklistTemplate = load_registry()[report.template_id]  # type: ignore[index]
    result.coverage_reports[report_idx] = calculate_coverage(template, report.items)
    result = regenerate_after_review(result, list(load_registry().values()))
    repo.save(result)
    return result
