"""Logging setup. Never log transcripts, prompts, API keys, or database URLs."""

import logging


def configure_logging() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # The HTTP client libraries can log request URLs/headers at DEBUG; keep them quiet.
    for noisy in ("httpx", "httpx2", "anthropic", "httpcore"):
        logging.getLogger(noisy).setLevel(logging.WARNING)


logger = logging.getLogger("tracecare")
