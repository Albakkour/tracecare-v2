import os
import tempfile

# Configure the environment before the app is imported. Unit tests never call the live LLM API.
_tmpdir = tempfile.mkdtemp(prefix="tracecare-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["DEMO_MODE_ENABLED"] = "true"
os.environ["DEMO_ACCESS_PASSWORD"] = ""
os.environ["ANALYSIS_RATE_LIMIT"] = "off"
os.environ["APP_ENV"] = "test"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.core.config import get_settings  # noqa: E402

SAMPLE_TRANSCRIPT = """Doctor: What brings you here today?
Patient: I've had a headache for three days.
Doctor: Have you had a fever?
Patient: No, I haven't had a fever.
Doctor: Have you taken any medication?
Patient: Yes, but I don't remember the dosage.
Doctor: Have you noticed anything else?
Patient: Sometimes I feel dizzy."""


@pytest.fixture
def client():
    get_settings.cache_clear()
    from app.core.security import analysis_rate_limiter
    from app.main import app

    analysis_rate_limiter.reset()
    with TestClient(app) as c:
        yield c
    get_settings.cache_clear()


@pytest.fixture
def segments():
    from app.services.transcript_parser import parse_transcript

    return parse_transcript(SAMPLE_TRANSCRIPT).segments
