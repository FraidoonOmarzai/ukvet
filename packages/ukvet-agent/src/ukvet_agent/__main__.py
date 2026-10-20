"""`python -m ukvet_agent` starts the API (uvicorn)."""

import os


def main() -> None:
    import uvicorn

    uvicorn.run(
        "ukvet_agent.api:app_factory",
        factory=True,
        host=os.environ.get("UKVET_HOST", "127.0.0.1"),
        port=int(os.environ.get("UKVET_PORT", "8000")),
        log_level=os.environ.get("UKVET_LOG_LEVEL", "info"),
    )


if __name__ == "__main__":
    main()
