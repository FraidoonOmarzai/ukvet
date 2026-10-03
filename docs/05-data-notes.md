# Data Notes — Companies House API

| Field | Value |
|---|---|
| Version | 0.1 (Spike results) |
| Owner | Fraidoon Omarzai |
| Status | ✅ Spike completed |

---

## 1. Access

| Item | Value |
|---|---|
| Base URL | `https://api.company-information.service.gov.uk` |
| Auth | HTTP Basic — API key as username, empty password |
| Key type | REST API key, live environment |
| Rate limit | 600 requests / 5 minutes per key |
| Rate-limit response | HTTP 429 |
| Cost | Free |
| Licence | Open Government Licence v3.0 — attribution required |

## 2. Endpoints

| Endpoint | Purpose | "No data" behaviour | Paginated? | Notes |
|---|---|---|---|---|
| `GET /search/companies?q=` | Find company by name | 200 + empty `items` | Yes | |
| `GET /company/{n}` | Profile | 404 if company does not exist | No | |
| `GET /company/{n}/officers` | Directors, secretaries | 200 + `items` | Yes | |
| `GET /company/{n}/filing-history` | Filings | 200 + `items` | Yes | `description` contains filing codes |
| `GET /company/{n}/persons-with-significant-control` | Owners / controllers | 200 + `items` | Yes | |
| `GET /company/{n}/charges` | Secured debts | 200 + empty `items` when no charges | Yes | |
| `GET /company/{n}/insolvency` | Insolvency cases | 404 when no insolvency record | No | |
| `GET /officers/{id}/appointments` | A person's appointments | 200 + `items` | Yes | Path comes from `links.officer.appointments` |

## 3. Question → data mapping

Status: ✅ answerable · 🟡 partial · ❌ not answerable

| ID | Question | Endpoint(s) | Field(s) | Status | Notes |
|---|---|---|---|---|---|
| Q1 | Active / dissolved / liquidation? | profile | `company_status`, `date_of_cessation` | ✅ | |
| Q2 | How old? | profile | `date_of_creation` | ✅ | |
| Q3 | Current directors? | officers | `name`, `officer_role`, `appointed_on`, `resigned_on` | ✅ | Filter out resigned |
| Q4 | Accounts / confirmation statement overdue? | profile | `accounts.overdue`, `confirmation_statement.overdue` | ✅ | |
| Q5 | Who controls it? | psc | `name`, `kind`, `natures_of_control` | ✅ | Corporate PSCs identified |
| Q6 | Charges? | charges + profile | `status`, `classification`, `created_on`, `has_charges` | ✅ | 200 + empty items means no charges |
| Q7 | Insolvency history? | insolvency + profile | `cases`, `has_insolvency_history` | ✅ | 404 can mean no insolvency record |
| Q8 | Directors linked to failed companies? | officers → appointments | `appointed_to.company_status` | ✅ | Appointment calls per active director |
| Q9 | Recent director/address changes? | officers, filing-history | dates; filing codes | ✅ | `AD01` identifies registered-office address changes |
| Q10 | Red flags summary | Q1–Q9 | — | 🟡 | Synthesis layer |

## 4. Test set used in the spike

| Category | Company number | Notes |
|---|---|---|
| Large plc | 00445790 | Lots of data |
| New Ltd (< 1 year) | 17491796 | Little data |
| Dissolved | 12115175 | Status handling |
| Insolvency / liquidation | 01468547 | Insolvency endpoint |
| Overdue accounts | 12056899 | Overdue flag |
| Has charges | 17016019 | Charges present |
| No charges | 17491796 | Empty charges response |
| Corporate PSC | 03977902 | Corporate PSC case |

## 5. Measurements

| Measure | Value |
|---|---|
| API calls per full report (median / max) | 7.0 / 11.0 |
| Q8 calls per report (median / max) | 1.0 / 5 |
| Reports per 5 minutes within rate limit | 85 theoretical |
| API latency per call (median / p95, ms) | 38 / 189 |
| Estimated sequential API time per report (s) | 0.3 |
| Calls that could run in parallel | Profile, officers, filing history, PSC, charges, insolvency |

## 6. Quirks and gotchas

- Charges with no data return **HTTP 200 with an empty `items` list**.
- Insolvency with no data returns **HTTP 404**.
- Different endpoints therefore use different "no data" behaviour.
- Q8 requires the officers response before appointment lookups can begin.
- Appointment responses already contain the linked company's `company_status`.
- The same person may appear under multiple officer IDs, so identity matching needs care.
- Filing history uses machine-readable codes such as `AD01`; these need mapping to plain English.
- `AD01` was observed for registered-office address changes.
- Q8 can create many linked-company results, but does not require one extra API call per linked company.

## 7. Decisions triggered by the spike

| Decision | Reason | Logged in decision log? |
|---|---|---|
| Limit Q8 to a manageable number of directors | Controls API call budget | |
| Treat 200 + empty charges list as "no charges" | Observed behaviour | |
| Treat insolvency 404 as "no insolvency record" | Observed behaviour | |
| Run independent API calls in parallel | Reduces report latency | |
| Use cached/recorded fixtures for evals | Avoid repeated API usage | |

## 8. Assumptions updated

| ID | Assumption | Result |
|---|---|---|
| A4 | Data can answer Q1–Q10 | 🟡 Mostly supported; Q10 is synthesis |
| A5 | Report possible in < 30 s within rate limits | 🟢 API portion has substantial headroom; LLM time still needs measurement |

---

## 9. Spike Summary

### Authentication
- API authentication worked successfully.
- Rate-limit headers reported **600 requests / 5 minutes**.

### API behaviour
- Most tested endpoints returned HTTP 200.
- Charges with no records returned **200 + empty `items`**.
- Insolvency with no record returned **404**.

### Performance
- Typical report required approximately **7 API calls**.
- Maximum observed was **11 API calls**.
- Median API latency was approximately **38 ms**.
- 95th-percentile API latency was **189 ms**.
- Estimated sequential API time was approximately **0.3 seconds**.
- Theoretical capacity at 7 calls/report and a 600-call limit is approximately **85 reports per 5 minutes**.

### Parallelisation
The main independent calls — profile, officers, filing history, PSC, charges, and insolvency — can largely run in parallel. Director appointment lookups must happen after officers are retrieved.

### Evaluation strategy
Repeated evals should use **cached responses or recorded fixtures** rather than calling the live Companies House API every time. This avoids rate-limit usage and makes eval results faster and more reproducible.

### Overall conclusion
The Companies House API portion appears fast enough to support the **30-second M7 target**. The remaining measurement needed is the **full end-to-end time including LLM generation**.

