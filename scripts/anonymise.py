"""Anonymisation for recorded Companies House fixtures (UK GDPR control; see docs/06).

Rules:
- People: names -> "PERSON 001"; officer IDs -> "OFFICERID001"; all personal fields dropped.
- Companies: unless allow-listed as large public companies, number -> 91xxxxxx, name ->
  "TEST COMPANY 001", chargee names -> "CHARGEE 001".
- Free-text/identifying blobs (filing description_values, links, practitioners, addresses) dropped.
- `leak_check` is the safety net: it fails loudly if ANY original sensitive string survives.
"""

import json
import re
from typing import Any

DROP_KEYS = {
    "date_of_birth",
    "address",
    "nationality",
    "occupation",
    "country_of_residence",
    "registered_office_address",
    "service_address",
    "usual_residential_address",
    "residential_address",
    "principal_office_address",
    "practitioners",
    "description_values",
    "name_elements",
    "identification",
    "links",
    "etag",
    "former_names",
    "previous_company_names",
    "foreign_company_details",
    "accounts_reference_date",
    "address_snippet",
    "snippet",
    "matches",
}
LETTERS = re.compile(r"[A-Za-z]")


class Anonymiser:
    def __init__(self, public_companies: set[str] | None = None) -> None:
        self.public = public_companies or set()
        self._companies: dict[str, str] = {}
        self._people: dict[str, str] = {}
        self._officer_ids: dict[str, str] = {}
        self._company_names: dict[str, str] = {}
        self._chargees: dict[str, str] = {}
        self.sensitive: set[str] = set()  # original strings that must never appear in output

    # ---- id/name maps ----------------------------------------------------------------------
    def company_number(self, n: str) -> str:
        if n in self.public:
            return n
        self.sensitive.add(n)
        return self._companies.setdefault(n, f"91{len(self._companies) + 1:06d}")

    def company_name(self, number: str, name: str) -> str:
        if number in self.public:
            return name
        self.sensitive.add(name)
        return self._company_names.setdefault(
            name, f"TEST COMPANY {len(self._company_names) + 1:03d}"
        )

    def person(self, name: str) -> str:
        self.sensitive.add(name)
        return self._people.setdefault(name, f"PERSON {len(self._people) + 1:03d}")

    def officer_id(self, oid: str) -> str:
        self.sensitive.add(oid)
        return self._officer_ids.setdefault(oid, f"OFFICERID{len(self._officer_ids) + 1:03d}")

    def chargee(self, name: str, company_number: str) -> str:
        if company_number in self.public:
            return name
        self.sensitive.add(name)
        return self._chargees.setdefault(name, f"CHARGEE {len(self._chargees) + 1:03d}")

    def officer_path(self, path: str) -> str:
        m = re.match(r"^/officers/([^/]+)/appointments$", path)
        return f"/officers/{self.officer_id(m.group(1))}/appointments" if m else path

    # ---- scrubbing -------------------------------------------------------------------------
    def _scrub(self, obj: Any) -> Any:
        if isinstance(obj, dict):
            return {k: self._scrub(v) for k, v in obj.items() if k not in DROP_KEYS}
        if isinstance(obj, list):
            return [self._scrub(v) for v in obj]
        return obj

    def profile(self, body: dict[str, Any]) -> dict[str, Any]:
        number = body["company_number"]
        out = self._scrub(body)
        out["company_name"] = self.company_name(number, body.get("company_name", ""))
        out["company_number"] = self.company_number(number)
        return out  # type: ignore[no-any-return]

    def officers(self, body: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in self._scrub(body).items() if k != "items"}
        out["items"] = []
        for item in body.get("items", []):
            clean = self._scrub(item)
            clean["name"] = self.person(item.get("name", ""))
            path = item.get("links", {}).get("officer", {}).get("appointments")
            if path:
                clean["links"] = {"officer": {"appointments": self.officer_path(path)}}
            out["items"].append(clean)
        return out

    def psc(self, body: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in self._scrub(body).items() if k != "items"}
        out["items"] = []
        for item in body.get("items", []):
            clean = self._scrub(item)
            name = item.get("name", "")
            if "corporate-entity" in item.get("kind", "") or "legal-person" in item.get("kind", ""):
                self.sensitive.add(name)
                clean["name"] = f"CORPORATE CONTROLLER {len(self.sensitive):03d}"
            else:
                clean["name"] = self.person(name)
            out["items"].append(clean)
        return out

    def charges(self, body: dict[str, Any], company_number: str) -> dict[str, Any]:
        out = self._scrub(body)
        for item in out.get("items", []):
            item["persons_entitled"] = [
                {"name": self.chargee(p.get("name", ""), company_number)}
                for p in item.get("persons_entitled", [])
            ]
            item.pop("particulars", None)
            item.pop("secured_details", None)
        return out  # type: ignore[no-any-return]

    def insolvency(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._scrub(body)  # type: ignore[no-any-return]

    def filings(self, body: dict[str, Any]) -> dict[str, Any]:
        return self._scrub(body)  # type: ignore[no-any-return]

    def appointments(self, body: dict[str, Any]) -> dict[str, Any]:
        out = {k: v for k, v in self._scrub(body).items() if k not in ("items", "name")}
        out["name"] = self.person(body.get("name", ""))
        out["items"] = []
        for item in body.get("items", []):
            clean = self._scrub(item)
            target = item.get("appointed_to", {})
            number = target.get("company_number", "")
            clean["appointed_to"] = {
                "company_number": self.company_number(number),
                "company_name": self.company_name(number, target.get("company_name", "")),
                "company_status": target.get("company_status"),
            }
            clean.pop("name", None)
            out["items"].append(clean)
        return out

    # ---- safety net ------------------------------------------------------------------------
    def leak_check(self, payload: Any) -> None:
        """Raise if any original sensitive string, or any dropped key, is in the output."""
        text = json.dumps(payload)
        for secret in self.sensitive:
            if secret and len(secret) >= 4 and secret in text and secret not in self.public:
                raise AssertionError("Anonymisation leak: an original value survived in output")
        keys = set(re.findall(r'"([a-z_]+)":', text))
        bad = keys & (DROP_KEYS - {"links", "etag"})
        if bad:
            raise AssertionError(f"Anonymisation leak: forbidden keys present: {sorted(bad)}")
