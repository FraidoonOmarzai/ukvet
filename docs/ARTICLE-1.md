# ARTICLE 1: Building ukvet

Title options (pick one):
1. I built an AI due-diligence agent for UK companies. The AI is the least important part.
2. Building ukvet: an MCP server, a workflow with one LLM node, and what went wrong
3. How I made an LLM report on UK companies without letting it invent facts

Subtitle: An open-source MCP server for Companies House, an agent that cites every claim, and the mistakes I made along the way.

Medium notes: Medium has no tables, so this uses lists. Put the demo GIF right under the intro
(upload `ukvet-demo.gif`). Add 3 to 5 tags: `MCP`, `LLM`, `AI Agents`, `Python`, `Software Engineering`.
Replace the two `[...]` spots before publishing. Length about 1,400 words.

---

## Article text (paste from here)

Before you sign a contract with a company, lend it money or hire it as a supplier, you check it out.
In the UK, much of the evidence is public: Companies House publishes who runs a company, who controls
it, what debts are secured against it, whether it is in insolvency and whether it files its accounts
on time. It is all there. It is also spread over a dozen pages and a rate-limited API.

I wanted to see if an AI agent could do that check and, more importantly, prove its answers. So I built
**ukvet**. It has three parts:

- **ukvet-mcp**: an MCP server that gives Claude Desktop, Cursor or any MCP client eight read-only
  tools over Companies House data. It is on PyPI and in the official MCP Registry.
- **ukvet-agent**: a LangGraph agent that produces a short due-diligence report with a risk level, red
  flags and a citation for every claim.
- **ukvet-evals**: a versioned evaluation set and scorers that measure whether the reports are right.

The code is here: https://github.com/FraidoonOmarzai/ukvet

This article is about how it is built and what went wrong. A second article covers what the
evaluations showed.

### The idea that shaped everything: the model only writes

The first design question was how much freedom the LLM gets. A tool-calling agent that decides which
endpoints to call is the fashionable answer. I decided against it, and wrote the reasons in an
architecture decision record (ADR-007).

The nine questions the report answers are fixed: is the company active, how old is it, who are the
directors, who controls it, what charges are outstanding, is there any insolvency, and so on. Each one
maps to known endpoints. A model choosing tools adds latency, cost and randomness, lets the model
invent tool arguments, and gives an LLM that reads untrusted registry text direct access to tools.

So the graph is fixed:

Planner → Researcher → Verifier → (Researcher again if something is missing) → Reporter

The first three are plain code. Red flags and the risk level come from rules, not from the model. The
LLM appears exactly once, in the Reporter, where it writes the headline and the findings as
structured output. It sees only verified facts, it has no tools, and every claim it writes is checked.

I describe ukvet as a workflow with one LLM node and a verification loop, not as an autonomous agent.
That is deliberate. It is also the reason the results later in this series are interpretable: when a
report is wrong, I can tell whether retrieval failed or the writing failed.

### The data layer: boring, correct and citable

The MCP server (ADR-001) is where the correctness work went. A few choices:

- **Every result is citable.** Each tool returns `{found, data, source, notes}`. The `source` holds the
  public Companies House URL and a `retrieved_at` timestamp.
- **"No data" is not an error.** A company with no charges returns `found: false`. A 404 on a
  sub-endpoint is checked against the company profile, so the server never reports "no insolvency
  record" for a company that does not exist.
- **Computed facts, not LLM arithmetic.** Company age, status counts and outstanding-charge counts are
  calculated in code.
- **Data minimisation.** No dates of birth, home addresses, nationality or occupation. This is UK GDPR
  thinking applied to a tool whose subject matter is people.
- **Safe by construction.** A sliding-window rate limiter that never exceeds the API limit (600
  requests per 5 minutes, with a safety margin), retries with backoff, hard pagination caps and a
  short-lived cache. The API key is never logged.

None of this is glamorous. It is the part I would defend in an interview, because a due-diligence
tool that quietly returns the wrong thing is worse than no tool.

### Checking the model's work

The Reporter's output is verified claim by claim. Each sentence has to cite fact IDs from the verified
facts, and a checker looks at dates, numbers, names and wording that would imply wrongdoing or
advice. If the checker fails twice, ukvet falls back to a deterministic template narrative. A report is
always produced, and a field called `narrative_source` says which one you got.

That fallback turned out to matter in a way I did not expect (see below).

### The evals came before the claims

I built an evaluation set before I let myself say anything about accuracy: 48 companies, nine questions
each, 432 items, split into 30 development and 18 test companies by a salted hash fixed before any
scores existed. I looked at the test split once for the first baseline and wrote down the date and
the reason.

That discipline was put to the test during development, and I am proud of what the logs show rather
than a perfect score:

- A claim was flagged as unsupported because my scorer ignored a fact's caveats, and the model had
  correctly restated one. The scorer was wrong, not the model. I fixed the scorer and logged that I
  changed it after seeing development results.
- One of my red-flag labels disagreed with my own rule about secretaries versus directors. The label
  definition was wrong. I changed the definition and regenerated the labels, again logged.

Neither change touched the test split. The write-up says plainly that the labels and the rules come
from the same author, so a perfect recall figure partly measures consistency.

### What went wrong

This is the part I would have wanted to read before starting.

**The silent fallback.** My first live comparison run on Claude produced 30 reports, all fast, all
free, all wrong. Every one was the template fallback. The API had rejected my request with an HTTP 400
because the `temperature` parameter is deprecated for that model. The fallback did its job so well
that the run looked healthy. The fix was to stop sending temperature unless configured. The lesson is
that a graceful fallback needs a counter. ukvet now reports the fraction of reports written by the LLM
next to every result, and `ukvet-evals compare` refuses a template-only run.

**A bug in my own check script.** My endpoint check for the self-hosted model passed three rounds of
five and failed two. It looked like the server was flaky. It was my script: it created a new event
loop for each round. One loop for all rounds fixed it.

**A model with thinking on by default.** The open-weight model I tested writes a long hidden reasoning
block unless you switch it off. That slows every report and can use the token limit before the answer
starts. I found out from the server logs, not from the docs I had skimmed.

**Scope I said no to.** No hosted public demo, no person search, no monitoring. Each of those would
have created legal or security work that was not the point of the project. They are written down as
decisions, so I did not have to relitigate them every week.

### What I would do differently

- Add the "fraction written by the LLM" counter on day one, not after the silent fallback.
- Use a second labeller for the red-flag labels. One person writing both the rules and the labels
  inflates agreement.
- Release the MCP server before the agent. It is useful on its own and it is what people can try in
  five minutes: add `uvx ukvet-mcp` to Claude Desktop with a free Companies House key.

### Try it, break it

The README has the quickstart. The evaluation set, the scorers and the decision log are in the repo,
so you can check every number I quote. [OPTIONAL: one sentence on what feedback you want, for example
"If you find a company type it handles badly, open an issue."]

*ukvet contains public sector information licensed under the Open Government Licence v3.0. It is not
affiliated with or endorsed by Companies House, and it is informational only, not legal, financial or
credit advice.*

---

## Before you publish

- Add the GIF and make sure it shows a company and no named individuals.
- Check the repo link opens on GitHub while logged out.
- No trace links, no real company names beyond what the GIF shows, no keys in screenshots.
- Fill the two `[...]` spots or delete them.
