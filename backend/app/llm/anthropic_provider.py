"""Claude provider using the official Anthropic Python SDK with structured outputs.

Responses are parsed into Pydantic models by the SDK and then validated again by TraceCare's own
evidence validator. Transcript text and prompts are never logged.
"""

from __future__ import annotations

import logging
from typing import TypeVar

import anthropic
from pydantic import BaseModel, ValidationError

from app.core.config import Settings
from app.llm import prompts
from app.llm.base import ProviderError
from app.llm.schemas import ExtractionOutput, PatientExplanationOutput, RecordSimplificationOutput
from app.schemas.coverage import ChecklistTemplate
from app.schemas.facts import MedicalFact
from app.schemas.transcript import TranscriptSegment

logger = logging.getLogger("tracecare.llm")
T = TypeVar("T", bound=BaseModel)

# Server-side refusal fallback: on a policy decline the API retries on its default fallback model.
FALLBACK_BETA = "server-side-fallback-2026-07-01"


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, settings: Settings):
        self._settings = settings
        self.model = settings.anthropic_model
        self.label = f"Claude ({self.model})"
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=2,
        )

    def _call(self, system: str, user: str, output_model: type[T], purpose: str) -> T:
        s = self._settings
        try:
            response = self._client.beta.messages.parse(
                model=self.model,
                max_tokens=s.llm_max_output_tokens,
                system=system,
                messages=[{"role": "user", "content": user}],
                output_format=output_model,
                output_config={"effort": s.anthropic_effort},
                betas=[FALLBACK_BETA],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise ProviderError("auth", "Claude API authentication failed. Check ANTHROPIC_API_KEY on the server and "
                                        "that API billing is active in Anthropic Console (a Claude subscription "
                                        "does not include API credit).", 502) from exc
        except anthropic.PermissionDeniedError as exc:
            raise ProviderError("permission", "The API key does not have permission for this model or feature.",
                                502) from exc
        except anthropic.NotFoundError as exc:
            raise ProviderError("model", f"Model '{self.model}' was not found. Check ANTHROPIC_MODEL.", 502) from exc
        except anthropic.RateLimitError as exc:
            raise ProviderError("rate_limit", "The Claude API rate limit was reached. Please retry shortly, or use "
                                              "the demo provider.", 503) from exc
        except anthropic.APITimeoutError as exc:
            raise ProviderError("timeout", "The Claude API request timed out. Please retry, or use the demo "
                                           "provider.", 504) from exc
        except anthropic.BadRequestError as exc:
            logger.warning("claude bad request purpose=%s request_id=%s", purpose,
                           getattr(exc, "request_id", None))
            raise ProviderError("bad_request", "The Claude API rejected the request (it may be too long or use an "
                                               "unsupported option).", 502) from exc
        except anthropic.APIStatusError as exc:
            raise ProviderError("api_error", f"The Claude API returned an error ({exc.status_code}). Please retry, "
                                             "or use the demo provider.", 502) from exc
        except anthropic.APIConnectionError as exc:
            raise ProviderError("connection", "Could not reach the Claude API (network error).", 502) from exc
        except ValidationError as exc:
            raise ProviderError("malformed_output", "Claude returned output that did not match the expected schema.",
                                502) from exc

        logger.info("claude call purpose=%s stop=%s in=%s out=%s request_id=%s", purpose, response.stop_reason,
                    response.usage.input_tokens, response.usage.output_tokens, getattr(response, "_request_id", None))
        if response.stop_reason == "refusal":
            raise ProviderError("refusal", "Claude declined to process this transcript.", 502)
        if response.stop_reason == "max_tokens":
            raise ProviderError("truncated", "Claude's response was cut off (output token limit). Try a shorter "
                                             "transcript or raise LLM_MAX_OUTPUT_TOKENS.", 502)
        parsed = response.parsed_output
        if parsed is None:
            raise ProviderError("malformed_output", "Claude returned no structured output.", 502)
        # Validate again with our own model (defence in depth; structured output does not validate meaning).
        try:
            return output_model.model_validate(parsed.model_dump() if isinstance(parsed, BaseModel) else parsed)
        except ValidationError as exc:
            raise ProviderError("malformed_output", "Claude returned output that did not match the expected schema.",
                                502) from exc

    def extract(self, segments: list[TranscriptSegment], templates: list[ChecklistTemplate]) -> ExtractionOutput:
        return self._call(prompts.EXTRACTION_SYSTEM, prompts.extraction_user_message(segments, templates),
                          ExtractionOutput, "extract")

    def explain_for_patient(self, facts: list[MedicalFact], language: str) -> PatientExplanationOutput:
        return self._call(prompts.PATIENT_SYSTEM, prompts.patient_user_message(facts, language),
                          PatientExplanationOutput, "patient_explanation")

    def simplify_record(self, sentences, language: str) -> RecordSimplificationOutput:
        return self._call(prompts.RECORD_SYSTEM, prompts.record_user_message(sentences, language),
                          RecordSimplificationOutput, "record_explainer")
