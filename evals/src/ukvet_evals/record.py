"""Record ANONYMISED snapshots from the live Companies House API (needs CH_API_KEY).

Personal data never touches disk un-anonymised: every body is scrubbed in memory, then checked by
the anonymiser's own leak check before the snapshot is written. The real-number -> alias mapping is
kept in data/raw/eval_mapping.json (git-ignored) so re-recording gives the same aliases.

This reuses scripts/anonymise.py (the same UK GDPR control as the test fixtures).
"""

import importlib.util
import json
import time
from collections.abc import Callable
from datetime import date, timedelta
from pathlib import Path
from types import ModuleType
from typing import Any

from ukvet_evals.constants import MAX_APPOINTMENTS, MAX_DIRECTORS, MAX_LIST_ITEMS, WINDOW_DAYS
from ukvet_evals.snapshot import Endpoint, Snapshot, SnapshotMeta

Fetch = Callable[[str, dict[str, Any] | None], tuple[int, dict[str, Any] | None]]
FILINGS_CAP = 500
FILINGS_MARGIN_DAYS = 35


def load_anonymiser_module(root: Path) -> ModuleType:
    path = root / "scripts" / "anonymise.py"
    spec = importlib.util.spec_from_file_location("ukvet_anonymise", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_anonymiser(root: Path, public: set[str]) -> Any:
    """An Anonymiser whose alias tables persist between sessions (so aliases never collide)."""
    base = load_anonymiser_module(root).Anonymiser
    mapping = root / "data" / "raw" / "eval_mapping.json"

    class Persistent(base):  # type: ignore[misc, valid-type]
        _FIELDS = ("_companies", "_people", "_officer_ids", "_company_names", "_chargees")

        def __init__(self) -> None:
            super().__init__(public_companies=public)
            if mapping.exists():
                data = json.loads(mapping.read_text(encoding="utf-8"))
                for name in self._FIELDS:
                    getattr(self, name).update(data.get(name, {}))
                self.sensitive.update(data.get("sensitive", []))

        def save(self) -> None:
            mapping.parent.mkdir(parents=True, exist_ok=True)
            data = {name: getattr(self, name) for name in self._FIELDS}
            data["sensitive"] = sorted(self.sensitive)
            mapping.write_text(json.dumps(data, indent=1, sort_keys=True), encoding="utf-8")

    return Persistent()


def _paged(
    fetch: Fetch, path: str, cap: int, stop: Callable[[list[dict[str, Any]]], bool] | None = None
) -> tuple[int, dict[str, Any] | None, bool]:
    """Fetch pages (newest first) up to `cap` items -> (status, merged body, truncated)."""
    items: list[dict[str, Any]] = []
    first: dict[str, Any] | None = None
    per = min(100, cap)
    while True:
        status, body = fetch(path, {"items_per_page": per, "start_index": len(items)})
        if status != 200 or body is None:
            return status, None, False
        if first is None:
            first = {k: v for k, v in body.items() if k != "items"}
        page = [i for i in body.get("items", []) if isinstance(i, dict)]
        items.extend(page)
        if not page or len(page) < per or len(items) >= cap or (stop and stop(page)):
            break
    assert first is not None  # noqa: S101 - loop always runs once
    total = first.get("total_results", first.get("total_count"))
    truncated = isinstance(total, int) and total > len(items[:cap]) and not (stop and stop(items))
    return 200, {**first, "items": items[:cap]}, truncated


def record_company(
    fetch: Fetch, number: str, as_of: date, anon: Any, *, public: bool = False
) -> Snapshot | None:
    """Fetch, anonymise and assemble a snapshot. Returns None if the company does not exist."""
    status, profile = fetch(f"/company/{number}", None)
    if status != 200 or profile is None:
        return None
    alias = anon.company_number(number)
    truncated: list[str] = []
    eps: dict[str, Endpoint] = {
        "profile": Endpoint(status=200, body=anon.profile(profile)),
    }

    def put(
        key: str,
        suffix: str,
        scrub: Callable[[dict[str, Any]], dict[str, Any]],
        cap: int,
        stop: Callable[[list[dict[str, Any]]], bool] | None = None,
    ) -> dict[str, Any] | None:
        st, body, cut = _paged(fetch, f"/company/{number}{suffix}", cap, stop)
        eps[key] = Endpoint(status=st, body=scrub(body) if body else None)
        if cut:
            truncated.append(key)
        return body

    officers_raw = put("officers", "/officers", anon.officers, MAX_LIST_ITEMS)
    put("psc", "/persons-with-significant-control", anon.psc, MAX_LIST_ITEMS)
    put("charges", "/charges", lambda b: anon.charges(b, number), MAX_LIST_ITEMS)
    st, ins = fetch(f"/company/{number}/insolvency", None)
    eps["insolvency"] = Endpoint(status=st, body=anon.insolvency(ins) if ins else None)
    cutoff = (as_of - timedelta(days=WINDOW_DAYS + FILINGS_MARGIN_DAYS)).isoformat()
    put(
        "filings",
        "/filing-history",
        anon.filings,
        FILINGS_CAP,
        lambda page: str(page[-1].get("date") or "9999") < cutoff,
    )

    appointments: dict[str, Endpoint] = {}
    directors = [
        o
        for o in (officers_raw or {}).get("items", [])
        if not o.get("resigned_on") and "director" in str(o.get("officer_role") or "unknown")
    ]
    for o in directors[:MAX_DIRECTORS]:
        link = ((o.get("links") or {}).get("officer") or {}).get("appointments")
        if not link:
            continue
        st, body, _ = _paged(fetch, link, MAX_APPOINTMENTS)
        anon_path = anon.officer_path(link)
        oid = anon_path.split("/")[2]
        appointments[oid] = Endpoint(status=st, body=anon.appointments(body) if body else None)

    snap = Snapshot(
        meta=SnapshotMeta(
            company_number=alias,
            as_of=as_of,
            recorded=date.today(),
            public=public,
            truncated=truncated,
        ),
        endpoints=eps,
        appointments=appointments,
    )
    anon.leak_check(snap.model_dump(mode="json"))
    return snap


def http_fetch(api_key: str, sleep: float = 0.25) -> tuple[Fetch, Callable[[], None]]:
    """A polite (about 4 requests/s) sync fetcher; the caller must call the returned close()."""
    import httpx

    client = httpx.Client(
        base_url="https://api.company-information.service.gov.uk", auth=(api_key, ""), timeout=20
    )

    def fetch(path: str, params: dict[str, Any] | None) -> tuple[int, dict[str, Any] | None]:
        time.sleep(sleep)
        r = client.get(path, params=params)
        if r.status_code == 200:
            body = r.json()
            return 200, body if isinstance(body, dict) else None
        if r.status_code == 404:
            return 404, None
        r.raise_for_status()
        raise RuntimeError(f"unexpected status {r.status_code} for {path}")

    return fetch, client.close
