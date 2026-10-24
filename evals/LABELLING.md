# Labelling guide (write labels from this page, NOT from ukvet's output)

Labels are only worth having if they do not come from the code they grade.
Rule: **label a company before you run the rules on it.** Use the live website page or the raw
snapshot JSON, apply the definitions below, and write `flags.jsonl`. Never edit a label after seeing
a result without a note in `notes` saying why.

## Red-flag definitions

Reference date is the company's `as_of`. "Recent" means the last 365 days. "Failed status" means
liquidation, administration, receivership, voluntary-arrangement or insolvency-proceedings.

| id | Raise it when | Severity |
|---|---|---|
| `status` | Status is `dissolved`, or a failed status → **high**. Failed status `liquidation` where every insolvency case is a members' voluntary liquidation (a solvent wind-up) → **medium**. Any other status that is not active/open/registered → **medium** | as stated |
| `strike_off` | Status detail is `active-proposal-to-strike-off` | high |
| `insolvency` | At least one insolvency case is on file. All cases members' voluntary → medium. Not raised separately when status is liquidation and every case is members' voluntary (`status` already covers it) | high / medium |
| `age` | Company is active and under 1 year old → medium; under 2 years → low | medium / low |
| `accounts_overdue` | Accounts are marked overdue | medium |
| `confirmation_overdue` | Confirmation statement is marked overdue | medium |
| `charges` | At least one outstanding charge | low |
| `network` | Among the first 5 current directors' other appointments (excluding this company), count distinct companies in a failed status: 3 or more → high; 2 → medium; 1 → low. If none, 5 or more dissolved companies → low | as stated |
| `officer_turnover` | Officer appointments + resignations in the last 365 days, **not counting appointments within 30 days of incorporation**: 3 or more → medium; exactly 2 → low | medium / low |
| `address_changes` | 2 or more registered-office changes (filing type AD01) in the last 365 days | medium |
| `no_directors` | Company is active and has no current director | medium |
| `no_psc` | Company is active and has no current person with significant control | info |

If you think a definition is wrong, do not "fix" it in the label. Label by the definition, then
note the disagreement in `notes`: that is a finding about the rule, and it belongs in the report.

## Writing a row

```json
{"company": "c007", "labeller": "FO", "labelled_on": "2026-10-25",
 "expected": [{"id": "status", "severity": "high"}, {"id": "insolvency", "severity": "high"}],
 "second_labeller_expected": ["status", "insolvency"], "notes": ""}
```
- `expected: []` means "I expect no flags". `expected: null` means "not labelled yet" (skipped).
- `severity` is optional; when given, severity agreement is scored too.
- `second_labeller_expected`: flag ids chosen independently by a second person, on about 20% of
  companies. Agreement and kappa appear in the report.

## Golden values (hand-read from the website)

For each golden company read at least five fields from the public page, with today's date:
status, incorporation date, next accounts due and overdue state, next confirmation statement due,
number of current officers or PSCs, charge counts. Use the field names in `ukvet_evals/fields.py`.
Pages change daily: golden values are compared with a snapshot recorded the **same day**, and
`as_of` is that day. Do not use a cached page or a web-fetch tool; use a real browser.

## Abstention expectations

`gen-abstention` drafts each case from a written dependency table (`constants.py`). Review each:
- Which questions must become gaps? (a failed tool removes the questions that depend on it)
- Which facts must be absent? (nothing may be invented to fill the hole)
- Risk level: leave `expected_risk` empty to check the documented rule, or set it if you have a
  specific expectation (e.g. a high flag from another fact must still win).
