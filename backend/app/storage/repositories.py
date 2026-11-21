from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete

from app.core.config import get_settings
from app.schemas.outputs import AnalyzeResponse
from app.storage.database import Encounter, get_sessionmaker


class EncounterRepository:
    def save(self, result: AnalyzeResponse) -> None:
        first = next((r for r in result.coverage_reports if r.template_id), None)
        with get_sessionmaker()() as session:
            session.merge(Encounter(
                id=result.encounter_id,
                created_at=result.created_at,
                language=result.language,
                template_id=first.template_id if first else None,
                template_version=first.template_version if first else None,
                provider=result.provider,
                transcript_text=None,
                # A stored encounter is by definition persisted (the review UI depends on this flag).
                analysis_result={**result.model_dump(mode="json"), "persisted": True},
                review_status=result.status,
            ))
            days = get_settings().encounter_retention_days
            if days > 0:  # automatic retention: demo data does not accumulate
                cutoff = datetime.now(timezone.utc) - timedelta(days=days)
                session.execute(delete(Encounter).where(Encounter.created_at < cutoff))
            session.commit()

    def get(self, encounter_id: str) -> AnalyzeResponse | None:
        with get_sessionmaker()() as session:
            row = session.get(Encounter, encounter_id)
            if row is None:
                return None
            result = AnalyzeResponse.model_validate(row.analysis_result)
            result.persisted = True
            return result

    def delete(self, encounter_id: str) -> bool:
        with get_sessionmaker()() as session:
            row = session.get(Encounter, encounter_id)
            if row is None:
                return False
            session.delete(row)
            session.commit()
            return True
