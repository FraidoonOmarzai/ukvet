"""ukvet Streamlit UI. Run with: streamlit run ui/app.py  (API must be running)."""

import os

import streamlit as st
from ukvet_ui.client import ApiError, request_report
from ukvet_ui.render import (
    candidate_label,
    claim_markdown,
    company_url,
    fact_sources,
    narrative_note,
    risk_label,
    severity_icon,
)

API_URL = os.environ.get("UKVET_API_URL", "http://localhost:8000")

st.set_page_config(page_title="ukvet", page_icon="🔎", layout="centered")
st.title("ukvet")
st.caption("AI due-diligence reports for UK companies, built on official Companies House data.")


def run(query: str) -> None:
    st.session_state["query"] = query
    st.session_state["error"] = None
    st.session_state["result"] = None
    try:
        with st.spinner("Checking Companies House records..."):
            st.session_state["result"] = request_report(API_URL, query)
    except ApiError as exc:
        st.session_state["error"] = exc.message


with st.form("search"):
    value = st.text_input(
        "Company name or number",
        value=st.session_state.get("query", ""),
        max_chars=200,
        placeholder="e.g. 12345678 or Acme Building Services Ltd",
    )
    submitted = st.form_submit_button("Check company", type="primary")
if submitted and value.strip():
    run(value.strip())

if st.session_state.get("error"):
    st.error(st.session_state["error"])

result = st.session_state.get("result")
if result and result.get("kind") == "needs_selection":
    st.info(result["message"])
    for candidate in result["candidates"]:
        if st.button(candidate_label(candidate), key=f"pick-{candidate['company_number']}"):
            run(candidate["company_number"])
            st.rerun()

elif result and result.get("kind") == "report":
    report = result
    st.header(f"{report['company_name']} ({report['company_number']})")
    st.markdown(f"### {risk_label(report['risk_level'])}")
    st.caption(report["assessment"])
    st.markdown(claim_markdown(report["headline"]))
    st.caption(narrative_note(report))

    if report["red_flags"]:
        st.subheader("Red flags")
        for flag in report["red_flags"]:
            st.markdown(f"{severity_icon(flag['severity'])} **{flag['title']}**")
            st.caption(f"{flag['detail']}  `[{', '.join(flag['fact_ids'])}]`")

    st.subheader("Findings")
    for finding in report["findings"]:
        st.markdown(f"- {claim_markdown(finding)}")

    if report["gaps"]:
        st.subheader("Could not be checked")
        for gap in report["gaps"]:
            st.warning(f"{gap['question_id']}: {gap['reason']}")
    for note in report["data_quality_notes"]:
        st.info(note)

    with st.expander("Evidence: every fact and its source"):
        for fact in report["facts"]:
            st.markdown(f"**{fact['id']}**: {fact['statement']}")
            for caveat in fact["caveats"]:
                st.caption(f"⚠ {caveat}")
            for endpoint, url in fact_sources(fact):
                st.caption(f"Source: [{endpoint}]({url})")
    st.link_button("Open on Companies House", company_url(report["company_number"]))

    st.divider()
    st.caption(report["disclaimer"])
    st.caption(report["attribution"])
