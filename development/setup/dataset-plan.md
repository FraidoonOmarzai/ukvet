# The whole dataset plan

## 1. The goal
You want a **test set of about 28 real UK companies** that is varied enough to expose mistakes in ukvet. If it contains only healthy companies, ukvet will score high without proving anything. The set must include awkward cases: dissolved, in liquidation, brand new, many directors, and so on.

For each company, the tool saves a frozen, anonymised copy of its Companies House data. Later you check ukvet's answers against that copy, and against your own reading of the website.

## 2. How many companies, and why 28
- The plan needs **200+ test items**. Each company gives 9 items (one per question Q1 to Q9), so 25 to 28 companies reach it.
- **Minimum is 25. Aim for 28.** More is fine.
- One company can have **several tags**, so 28 companies can cover all the tag minimums below.

## 3. What a tag is
A tag is a label **you** write on a company to say what kind of case it is, for example `dissolved`. You choose it by looking at the company's page. Tags exist so the dataset has enough of each kind. `validate` counts them and tells you what is missing.

## 4. The tags and how many of each
| Tag | Minimum | What to look for | Where to find it |
|---|---|---|---|
| `large-plc` | 3 | Big listed company (Tesco, etc.) | Search a famous name |
| `healthy-small` | 4 | Normal active small company, nothing wrong | Any ordinary Ltd |
| `under-1-year` | 3 | Incorporated less than a year ago | Search "advanced search", filter by incorporation date |
| `1-to-2-years` | 2 | Incorporated 1 to 2 years ago | Same filter |
| `dissolved` | 3 | Status dissolved | Advanced search, status = dissolved |
| `liquidation-mvl` | 2 | In liquidation, "members' voluntary" | Status = liquidation; open the Insolvency tab |
| `liquidation-creditors` | 2 | In liquidation, "creditors' voluntary" | Same, other type |
| `administration-or-receivership` | 2 | In administration or receivership | Status filter |
| `strike-off-proposal` | 2 | Page shows "Active - Proposal to Strike Off" | Status filter, active proposals |
| `overdue-filings` | 3 | Accounts or confirmation statement shown as overdue | Look for the red "overdue" notice on the overview page |
| `charges-outstanding` | 2 | Charges tab has outstanding charges | Browse small companies with a loan |
| `charges-all-satisfied` | 2 | Charges tab, all satisfied | Same |
| `corporate-psc` | 2 | "People with significant control" is another company | People tab |
| `no-psc` | 2 | No person with significant control listed | People tab |
| `llp-or-sc-or-ni` | 3 | One LLP, one Scottish (SC...), one Northern Irish (NI...) | Numbers starting `OC`, `SC`, `NI` |
| `many-appointments-director` | 2 | A director with many other companies | Click a director, see the appointments list |
| `corporate-officer` | 2 | A company acts as a director or secretary | People tab, officer is a company |
| `officer-changes-12m` | 3 | Directors joined or left in the last year | Officers tab, dates this year |
| `address-change-12m` | 2 | Registered office changed this year | Filing history, "change of registered office address" |

## 5. Suggested plan: about 28 companies
Overlap tags to reach every minimum:

| Group | Companies | Tags to put |
|---|---|---|
| Big listed companies | 3 | `large-plc` (add `--public`) |
| Ordinary healthy | 4 | `healthy-small`; make two of them `charges-all-satisfied` and one `corporate-psc` |
| New companies | 5 | 3 × `under-1-year` (make 2 of them `no-psc`), 2 × `1-to-2-years` |
| Dissolved | 3 | `dissolved` |
| Liquidation | 4 | 2 × `liquidation-mvl`, 2 × `liquidation-creditors` |
| Admin or receivership | 2 | `administration-or-receivership` |
| Strike-off | 2 | `strike-off-proposal` |
| Overdue | 3 | `overdue-filings`; give two of them `charges-outstanding` |
| LLP, Scottish, NI | 3 | `llp-or-sc-or-ni` |
| Busy directors | 2 | `many-appointments-director`, `corporate-officer`, `officer-changes-12m` as they fit |

That is 31 slots, and overlaps bring it to about 28. Keep a spreadsheet so you don't record the same company twice.

## 6. How to record one company
1. Find the company on Companies House and **copy its number**. It has 8 characters, so keep leading zeros (`03977902`, not `3977902`).
2. Open PowerShell in the ukvet folder and run:
   ```powershell
   uv run ukvet-evals record 03977902 --dataset v0.1 --tags dissolved
   ```
3. Several companies with the same tags can go in one command:
   ```powershell 
   uv run ukvet-evals record 12056899 17016019 --dataset v0.1 --tags healthy-small
   ```
4. Several tags on one company are comma-separated, with no spaces:
   ```powershell
   uv run ukvet-evals record 17313434 --dataset v0.1 --tags under-1-year,no-psc
   ```
5. Large listed companies only: add `--public <same number>`:
   ```powershell
   uv run ukvet-evals record 00445790 --dataset v0.1 --public 00445790 --tags large-plc
   ```

It prints a line like `03977902 -> 91000090 (c004) recorded`. If it prints `not found, skipped`, the number is wrong.

## 7. After each batch
Run `uv run ukvet-evals validate --dataset v0.1`. Look at two things:
- `companies` goes up toward 28.
- `tags_missing` shrinks toward `{}`.

Any `LEAK` or `ERROR ... LEAK` line means stop and send it to me.

## 8. What comes after recording (don't do yet)
1. `choose-salt`, then `set-splits --lock`, once, when all companies are recorded.
2. Hand-check about 25 companies on the website into `golden.jsonl`.
3. `build-items` to create the answer key.

## Three rules
- Don't commit `evals/snapshots/` until `validate` says no leaks and you've searched a few files for real names.
- Keep `data\raw\eval_mapping.json` private and backed up.
- Don't look at scores until the split is locked.


---
Good that the tests and demo both work. Here is how the real data gets made, as a short recipe.

## What "the dataset" is
It is a folder of saved copies of real Companies House answers for about 28 companies, with the personal data replaced by fake names. Your tests replay those copies instead of calling the live API. You make it with one command per batch of companies, so you never write the data yourself.

## Step by step (PowerShell, from `C:\Users\44787\Desktop\ukvet`)

**1. Check your key.** Your `.env` must contain `CH_API_KEY=...`. You already have this.

**2. Record the large public companies first.** Large listed companies keep their real name, and people are still anonymised:
```powershell
uv run ukvet-evals record 00445790 --dataset v0.1 --public 00445790 --tags large-plc
```
This takes about a minute per company. It prints a line like `00445790 -> 00445790 (c001) recorded`. The first run creates the folders `evals/datasets/v0.1` and `evals/snapshots/v0.1` itself.

**3. Record every other company in groups that share the same tags.** For example:
```powershell
uv run ukvet-evals record 12056899 17016019 --dataset v0.1 --tags healthy-small
uv run ukvet-evals record 03977902 --dataset v0.1 --tags dissolved
uv run ukvet-evals record 17313434 --dataset v0.1 --tags under-1-year,no-psc
```
Put your own numbers and tags in. A company that matches several tags gets them all, comma-separated with no spaces. Each company becomes `c001`, `c002`, and so on. Its real number is replaced by a fake one starting `91...`.

**4. Back up one private file.** `data\raw\eval_mapping.json` links the real numbers to the fake ones. It is git-ignored, so don't delete it and never commit it. Without it you can't tell which fake company is which real one.

**5. Fix the dev/test split. Do this once, before looking at any score:**
```powershell
uv run ukvet-evals choose-salt --dataset v0.1
uv run ukvet-evals set-splits --dataset v0.1 --lock
```

**6. Make the answer key:**
```powershell
uv run ukvet-evals build-items --dataset v0.1
uv run ukvet-evals validate --dataset v0.1
```
`validate` checks for leaked personal data. Warnings about missing coverage are normal at this point.

## Your own checking comes after recording (golden set)
- Open `evals\datasets\v0.1\golden.jsonl` (create it if it doesn't exist).
- For 25 companies, open the real company page in your browser and copy about five values into one line per company, for example status and next accounts due. The line format is in `evals/README.md`.
- Then run `build-items` again. Any disagreement it prints is a bug or a typo that you should look at.

## Order to remember
1. Pick the companies (spreadsheet).
2. `record`.
3. `choose-salt` then `set-splits --lock`.
4. `golden.jsonl` (your hand-checking).
5. `build-items`.
6. `label-template` and `gen-abstention` (flags and failure cases, later).

## Two things that can go wrong
- **"Set CH_API_KEY"** means `.env` is not in the repo root or has a typo.
- **A company is "not found, skipped"** means the number is wrong. Check it for a missing leading zero (company numbers have 8 digits).