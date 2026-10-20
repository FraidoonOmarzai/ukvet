"""FastAPI service: POST /v1/reports and GET /health.

The MCP session is opened once, in the app lifespan, and shared by all requests. Every request has
a hard deadline (UKVET_REQUEST_TIMEOUT_SECONDS) and the number of concurrent reports is capped so
one busy client cannot exhaust the Companies House rate limit (600 requests / 5 minutes).
"""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from dataclasses import dataclass
from typing import Annotated

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from ukvet_agent import __version__
from ukvet_agent.errors import AgentError, ReportTimeout
from ukvet_agent.graph import Deps, build_graph, run_report
from ukvet_agent.llm import LlmSettings, build_writer
from ukvet_agent.mcp_client import McpToolClient
from ukvet_agent.schemas import NeedsSelection, Report
from ukvet_agent.settings import AgentSettings

log = logging.getLogger("ukvet_agent.api")

DepsFactory = Callable[[], AbstractAsyncContextManager[Deps]]


class ReportRequest(BaseModel):
    company: Annotated[
        str,
        Field(
            min_length=1,
            max_length=200,
            description="A company name or an 8-character company number.",
            examples=["12345678", "Acme Building Services Ltd"],
        ),
    ]


@dataclass
class Runtime:
    graph: object
    deps: Deps
    semaphore: asyncio.Semaphore


@asynccontextmanager
async def default_deps() -> AsyncIterator[Deps]:
    """Production wiring: stdio MCP session + optional LLM writer."""
    settings = AgentSettings()
    llm = LlmSettings()
    writer = build_writer(llm)  # raises AgentConfigError at start-up if misconfigured
    async with McpToolClient.stdio(timeout_seconds=settings.tool_timeout_seconds) as tools:
        yield Deps(
            tools=tools,
            settings=settings,
            writer=writer,
            llm_timeout_seconds=llm.timeout_seconds + 2,
        )


def _error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": code, "message": message})


def create_app(deps_factory: DepsFactory = default_deps) -> FastAPI:
    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with deps_factory() as deps:
            app.state.runtime = Runtime(
                graph=build_graph(deps),
                deps=deps,
                semaphore=asyncio.Semaphore(deps.settings.max_concurrent_reports),
            )
            yield

    app = FastAPI(
        title="ukvet",
        version=__version__,
        description="AI due-diligence reports for UK companies, built on Companies House data.",
        lifespan=lifespan,
    )

    @app.exception_handler(AgentError)
    async def agent_error(_: Request, exc: AgentError) -> JSONResponse:
        message = str(exc) if exc.http_status < 500 else "The report could not be generated."
        if exc.http_status >= 500:
            log.warning("report failed: %s: %s", type(exc).__name__, exc)
        return _error(exc.http_status, type(exc).__name__, message)

    @app.exception_handler(Exception)
    async def unexpected(_: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error", exc_info=exc)
        return _error(500, "InternalError", "Something went wrong. Please try again.")

    @app.post("/v1/reports", response_model=Report | NeedsSelection)
    async def create_report(body: ReportRequest, request: Request) -> Report | NeedsSelection:
        runtime: Runtime = request.app.state.runtime
        deadline = runtime.deps.settings.request_timeout_seconds
        try:
            async with asyncio.timeout(deadline):
                async with runtime.semaphore:
                    return await run_report(runtime.graph, body.company)
        except TimeoutError:
            raise ReportTimeout(f"The report took longer than {deadline:g} seconds.") from None

    @app.get("/health")
    async def health(request: Request) -> JSONResponse:
        runtime: Runtime = request.app.state.runtime
        try:
            tools = await runtime.deps.tools.ping()
        except Exception:
            return JSONResponse(status_code=503, content={"status": "degraded", "mcp": "down"})
        writer = runtime.deps.writer
        return JSONResponse(
            content={
                "status": "ok",
                "version": __version__,
                "mcp_tools": tools,
                "narrative": writer.model_name if writer else "template-only",
            }
        )

    return app


def app_factory() -> FastAPI:
    """Entry point for `uvicorn --factory ukvet_agent.api:app_factory`."""
    return create_app()
