"""Tool logic: client + mappers + "no data" semantics + source citations.

Key rules implemented here:
- "No data" is a valid result (`found=False`), never an error.
- A 404 on a company sub-endpoint is ambiguous ("no records" vs "company does not exist"), so we
  confirm the company exists via its (cached) profile before declaring "no data".
- Every result carries a `Source` with a public URL so facts can be cited and verified.
"""

from collections import Counter
from collections.abc import Callable
from datetime import date
from typing import Any, TypeVar
from urllib.parse import quote

from pydantic import ValidationError

from ukvet_mcp.client import CompaniesHouseClient, Page
from ukvet_mcp.errors import CompanyNotFound, InvalidInput, OfficerNotFound, UpstreamError
from ukvet_mcp.mappers import (
    map_appointment,
    map_charge,
    map_filing,
    map_insolvency_case,
    map_officer,
    map_profile,
    map_psc,
    map_search_hit,
)
from ukvet_mcp.models import (
    AppointmentsData,
    ChargesData,
    CompanyProfile,
    FilingsData,
    InsolvencyData,
    OfficersData,
    PscData,
    SearchData,
    Source,
    ToolResult,
)
from ukvet_mcp.normalise import (
    normalise_company_number,
    validate_category,
    validate_officer_id,
)

PUBLIC_BASE = "https://find-and-update.company-information.service.gov.uk"

M = TypeVar("M")


def _mapped[M](endpoint: str, fn: Callable[..., M], *args: Any) -> M:
    """Run a mapper; turn unexpected response shapes into a clean UpstreamError."""
    try:
        return fn(*args)
    except (KeyError, TypeError, ValueError, ValidationError):
        raise UpstreamError(
            f"Companies House returned data in an unexpected shape for {endpoint}. "
            "This may be a temporary API change; try again later."
        ) from None


class CompaniesHouseService:
    def __init__(
        self,
        client: CompaniesHouseClient,
        *,
        max_items: int = 100,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._client = client
        self._max_items = max_items
        self._today = today

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _source(endpoint: str, public_path: str, page_or_resp: Any) -> Source:
        return Source(
            endpoint=endpoint,
            url=f"{PUBLIC_BASE}{public_path}",
            retrieved_at=page_or_resp.retrieved_at,
            from_cache=page_or_resp.from_cache,
        )

    async def _collection(
        self,
        number: str,
        suffix: str,
        *,
        total_key: str,
        max_items: int | None = None,
        params: dict[str, Any] | None = None,
        stop_after: Callable[[list[dict[str, Any]]], bool] | None = None,
    ) -> Page:
        page = await self._client.get_paginated(
            f"/company/{number}{suffix}",
            items_key="items",
            total_key=total_key,
            max_items=max_items or self._max_items,
            params=params,
            stop_after=stop_after,
        )
        if page.not_found:
            # Ambiguous 404: raises CompanyNotFound if the company itself doesn't exist.
            await self.get_company_profile(number)
        return page

    # ---- search -------------------------------------------------------------------------------

    async def search_company(self, query: str, limit: int = 10) -> ToolResult[SearchData]:
        q = (query or "").strip()
        if not q:
            raise InvalidInput("query must not be empty. Provide (part of) a company name.")
        if len(q) > 200:
            raise InvalidInput("query is too long; use at most 200 characters.")
        if not 1 <= limit <= 20:
            raise InvalidInput("limit must be between 1 and 20.")

        resp = await self._client.get("/search/companies", {"q": q, "items_per_page": limit})
        body = resp.data or {}
        items = [
            _mapped("/search/companies", map_search_hit, i)
            for i in body.get("items", [])
            if isinstance(i, dict)
        ]
        raw_total = body.get("total_results")
        total = raw_total if isinstance(raw_total, int) else None
        truncated = total is not None and total > len(items)
        notes = []
        if truncated:
            notes.append(
                f"Showing {len(items)} of {total} matches. Refine the query to narrow down."
            )
        return ToolResult[SearchData](
            found=bool(items),
            data=SearchData(
                total=total, returned=len(items), truncated=truncated, query=q, items=items
            ),
            source=self._source("/search/companies", f"/search/companies?q={quote(q)}", resp),
            notes=notes,
        )

    # ---- profile (Q1, Q2, Q4) -----------------------------------------------------------------

    async def get_company_profile(self, company_number: str) -> ToolResult[CompanyProfile]:
        number = normalise_company_number(company_number)
        endpoint = f"/company/{number}"
        resp = await self._client.get(endpoint)
        if resp.status == 404 or resp.data is None:
            raise CompanyNotFound(number)
        profile = _mapped(endpoint, map_profile, resp.data, self._today())
        return ToolResult[CompanyProfile](
            found=True,
            data=profile,
            source=self._source(endpoint, f"/company/{number}", resp),
        )

    # ---- officers (Q3, Q9) --------------------------------------------------------------------

    async def get_officers(
        self, company_number: str, include_resigned: bool = False
    ) -> ToolResult[OfficersData]:
        number = normalise_company_number(company_number)
        endpoint = f"/company/{number}/officers"
        page = await self._collection(number, "/officers", total_key="total_results")
        everyone = [_mapped(endpoint, map_officer, i) for i in page.items]
        shown = everyone if include_resigned else [o for o in everyone if o.is_active]

        notes: list[str] = []
        active_count = page.first_page.get("active_count")
        resigned_count = page.first_page.get("resigned_count")
        if page.truncated:
            notes.append(
                f"Only {len(page.items)} of {page.total} officer records were fetched (cap "
                f"{self._max_items}); some officers, possibly current ones, may be missing."
            )
        if everyone and not shown:
            notes.append("The company has officer records, but all of them have resigned.")
        return ToolResult[OfficersData](
            found=bool(shown),
            data=OfficersData(
                total=page.total,
                returned=len(shown),
                truncated=page.truncated,
                active_count=active_count if isinstance(active_count, int) else None,
                resigned_count=resigned_count if isinstance(resigned_count, int) else None,
                items=shown,
            ),
            source=self._source(endpoint, f"/company/{number}/officers", page),
            notes=notes,
        )

    # ---- appointments (Q8) --------------------------------------------------------------------

    async def get_officer_appointments(
        self,
        officer_id: str,
        max_items: int = 50,
        exclude_company_number: str | None = None,
    ) -> ToolResult[AppointmentsData]:
        oid = validate_officer_id(officer_id)
        if not 1 <= max_items <= 200:
            raise InvalidInput("max_items must be between 1 and 200.")
        exclude = (
            normalise_company_number(exclude_company_number) if exclude_company_number else None
        )

        endpoint = f"/officers/{oid}/appointments"
        page = await self._client.get_paginated(
            endpoint, items_key="items", total_key="total_results", max_items=max_items
        )
        if page.not_found:
            raise OfficerNotFound(oid)

        items = [_mapped(endpoint, map_appointment, i) for i in page.items]
        notes: list[str] = []
        if exclude:
            kept = [a for a in items if a.company_number != exclude]
            if len(kept) != len(items):
                notes.append(f"Excluded the company being checked ({exclude}) from the list.")
            items = kept
        if page.truncated:
            notes.append(
                f"Showing {len(page.items)} of {page.total} appointments; status_counts cover "
                "only the listed ones."
            )
        counts = Counter(a.company_status or "unknown" for a in items)
        name = page.first_page.get("name")
        return ToolResult[AppointmentsData](
            found=bool(items),
            data=AppointmentsData(
                total=page.total,
                returned=len(items),
                truncated=page.truncated,
                officer_id=oid,
                officer_name=name if isinstance(name, str) else None,
                status_counts=dict(counts),
                items=items,
            ),
            source=self._source(endpoint, f"/officers/{oid}/appointments", page),
            notes=notes,
        )

    # ---- persons with significant control (Q5) --------------------------------------------------

    async def get_persons_with_significant_control(
        self, company_number: str, include_ceased: bool = False
    ) -> ToolResult[PscData]:
        number = normalise_company_number(company_number)
        endpoint = f"/company/{number}/persons-with-significant-control"
        page = await self._collection(
            number, "/persons-with-significant-control", total_key="total_results"
        )
        everyone = [_mapped(endpoint, map_psc, i) for i in page.items]
        shown = everyone if include_ceased else [p for p in everyone if not p.ceased]

        notes: list[str] = []
        if not shown:
            notes.append(
                "No current person with significant control is on record. This does NOT prove "
                "the company has no owner: it may be exempt, or have filed a PSC statement "
                "(not covered by this tool)."
            )
        if page.truncated:
            notes.append(f"Only {len(page.items)} of {page.total} records were fetched (cap).")
        active_count = page.first_page.get("active_count")
        ceased_count = page.first_page.get("ceased_count")
        return ToolResult[PscData](
            found=bool(shown),
            data=PscData(
                total=page.total,
                returned=len(shown),
                truncated=page.truncated,
                active_count=active_count if isinstance(active_count, int) else None,
                ceased_count=ceased_count if isinstance(ceased_count, int) else None,
                items=shown,
            ),
            source=self._source(
                endpoint, f"/company/{number}/persons-with-significant-control", page
            ),
            notes=notes,
        )

    # ---- charges (Q6) ---------------------------------------------------------------------------

    async def get_charges(self, company_number: str) -> ToolResult[ChargesData]:
        number = normalise_company_number(company_number)
        endpoint = f"/company/{number}/charges"
        page = await self._collection(number, "/charges", total_key="total_count")
        items = [_mapped(endpoint, map_charge, i) for i in page.items]
        statuses = Counter(c.status for c in items)
        notes: list[str] = []
        if page.truncated:
            notes.append(
                f"Only {len(items)} of {page.total} charges were fetched (cap); counts cover "
                "only the listed charges."
            )
        return ToolResult[ChargesData](
            found=bool(items),
            data=ChargesData(
                total=page.total,
                returned=len(items),
                truncated=page.truncated,
                outstanding_count=statuses.get("outstanding", 0),
                part_satisfied_count=statuses.get("part-satisfied", 0),
                satisfied_count=statuses.get("fully-satisfied", 0) + statuses.get("satisfied", 0),
                items=items,
            ),
            source=self._source(endpoint, f"/company/{number}/charges", page),
            notes=notes,
        )

    # ---- insolvency (Q7) ------------------------------------------------------------------------

    async def get_insolvency(self, company_number: str) -> ToolResult[InsolvencyData]:
        number = normalise_company_number(company_number)
        endpoint = f"/company/{number}/insolvency"
        resp = await self._client.get(endpoint)
        source = self._source(endpoint, f"/company/{number}/insolvency", resp)

        if resp.status == 404 or resp.data is None:
            await self.get_company_profile(number)  # CompanyNotFound if it doesn't exist
            return ToolResult[InsolvencyData](
                found=False,
                data=InsolvencyData(case_count=0, statuses=[], cases=[]),
                source=source,
                notes=["Companies House holds no insolvency record for this company."],
            )

        cases = [
            _mapped(endpoint, map_insolvency_case, c)
            for c in resp.data.get("cases", [])
            if isinstance(c, dict)
        ]
        statuses = [str(s) for s in resp.data.get("status", [])]
        return ToolResult[InsolvencyData](
            found=bool(cases),
            data=InsolvencyData(case_count=len(cases), statuses=statuses, cases=cases),
            source=source,
        )

    # ---- filing history (Q9) --------------------------------------------------------------------

    async def get_filing_history(
        self,
        company_number: str,
        since: str | None = None,
        category: str | None = None,
        max_items: int | None = None,
    ) -> ToolResult[FilingsData]:
        number = normalise_company_number(company_number)
        endpoint = f"/company/{number}/filing-history"
        cat = validate_category(category)
        since_date: date | None = None
        if since:
            try:
                since_date = date.fromisoformat(since.strip())
            except ValueError:
                raise InvalidInput("since must be a date in YYYY-MM-DD format.") from None
        if max_items is not None and not 1 <= max_items <= 500:
            raise InvalidInput("max_items must be between 1 and 500.")

        def stop_after(page: list[dict[str, Any]]) -> bool:
            # Filings are newest-first, so once a page ends before `since` we can stop fetching.
            oldest = page[-1].get("date")
            return (
                since_date is not None
                and isinstance(oldest, str)
                and oldest < since_date.isoformat()
            )

        page = await self._collection(
            number,
            "/filing-history",
            total_key="total_count",
            max_items=max_items,
            params={"category": cat} if cat else None,
            stop_after=stop_after if since_date else None,
        )
        items = [_mapped(endpoint, map_filing, i) for i in page.items]
        notes: list[str] = []
        if since_date is not None:
            items = [f for f in items if f.date is not None and f.date >= since_date]
            notes.append(f"Filtered to filings dated on or after {since_date.isoformat()}.")
        truncated = page.truncated and not page.stopped_by_predicate
        if truncated:
            notes.append(
                f"Only the newest {len(page.items)} of {page.total} filings were fetched (cap); "
                "older filings exist."
            )
        return ToolResult[FilingsData](
            found=bool(items),
            data=FilingsData(
                total=page.total,
                returned=len(items),
                truncated=truncated,
                since=since_date,
                category=cat,
                items=items,
            ),
            source=self._source(endpoint, f"/company/{number}/filing-history", page),
            notes=notes,
        )
