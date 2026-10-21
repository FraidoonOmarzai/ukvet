# Manual accuracy check: Phase 2 (step 2.14)

| Field | Value |
|---|---|
| Date | 21 Oct 2026 |
| Checked by | Fraidoon Omarzai |
| Method | ukvet report compared field by field with the public Companies House website |
| Narrative mode | Template (facts and red flags are rule-based, so this check covers them) |
| Privacy | Company numbers and field names only. No director or PSC names in this file. |

## Result

**0 errors found in about 75 values across 10 companies.**

This is a small manual spot check. It is not an accuracy rate and not the M1 metric (Phase 3 measures M1 on an eval set). It shows no errors in the fields checked, and nothing more.

## Companies and what was checked

| Company no. | Type | Checked | Result |
|---|---|---|---|
| 00445790 | Large plc | Status, incorporation date, accounts and confirmation statement dates, charges (9 total, 2 outstanding, 7 satisfied), current officers (10 directors, 1 secretary) and appointment dates | Match |
| 17491796 | New Ltd (21 days old) | Status, incorporation date, first-accounts and first-statement due dates, no filings yet | Match |
| 12115175 | Dissolved | Status, dissolution date, incorporation date, last accounts, last confirmation statement | Match |
| 01468547 | Members' voluntary liquidation | Status, dates, overdue accounts and statement, liquidation type, declaration-of-solvency and winding-up dates | Match |
| 12056899 | Active, proposal to strike off | Status and strike-off detail, overdue accounts and statement dates | Match |
| 17016019 | New Ltd with a charge | Status, dates, first-filing due dates, charges (1 outstanding) | Match |
| 03977902 | Corporate PSC | Status, dates, charges (1 outstanding), officers, same-day secretary replacement on 1 Jun 2026 | Match |
| 17313434 | New Ltd | Status, incorporation date, first-filing due dates | Match |
| 14189917 | Ltd with 3 charges | Status, dates, charges (3 outstanding) | Match |
| 12204233 | Active Ltd | Status, dates, accounts and confirmation statement dates | Match |

## Not checked

- PSC details (ownership percentages, nature of control)
- Director-network counts (Tesco "83 other companies", Google "18")
- Director appointment counts for the small companies
- Insolvency and officer lists for companies not listed above

## Notes on the method

- Two comparisons (03977902 and 12204233) first looked like mismatches. The comparison tool had returned an old copy of the pages. Checked directly in a browser, the website matched ukvet on every date. These are not ukvet errors.
- Lesson for Phase 3: record the check date and read the live page, or use recorded API fixtures, so a stale copy cannot cause a false mismatch.

## Findings from the check (rule and display fixes)

The check found no data errors, but reviewing the reports found six rule and display problems. All were fixed and tested (decision log #28 and up):

1. A solvent members' voluntary liquidation was rated HIGH. It is now MEDIUM and labelled as a solvent wind-up.
2. A proposal to strike off was not flagged. It is now a HIGH flag.
3. Directors named at incorporation counted as "officer changes". They are now excluded.
4. A single linked company in liquidation was rated MEDIUM. It is now LOW (two is MEDIUM, three or more is HIGH). This is a judgement call.
5. Red-flag evidence could be cut by the 8-finding limit. Every flag's evidence now appears first.
6. A members' voluntary liquidation produced two flags for one fact. It now produces one.

## Seed for Phase 3

Each row above becomes a labelled eval case: company number, field, expected value from the website, date checked.
