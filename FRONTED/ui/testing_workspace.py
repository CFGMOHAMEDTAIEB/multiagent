"""Staged tester workspace: normalize, review, choose action, export."""

import hashlib
import json
from html import escape

from FRONTED.ui.design import illustration, agent_team_settings, configured_team_routers
from agents.testing_team import TestingAgentTeam
from smartx.clients import bind_client
from datetime import datetime, timezone

from smartx.testing import canonicalize, generate_tests, validate_contract, verify


def render_testing_workspace(st, sources, router, client_context=None):
    st.markdown('<div class="sx-hero"><div class="sx-eyebrow">SOFTWARE QUALITY, WITH CONFIDENCE</div><h2>From requirements to ready-to-review tests.</h2><p>Bring your documents. Turn them into structured evidence, verify your data, and build test code in one guided workspace.</p></div>', unsafe_allow_html=True)
    signature = hashlib.sha256(b"".join(name.encode() + data for name, data in sources) + json.dumps(client_context, sort_keys=True).encode()).hexdigest()
    if st.session_state.get("tester_source_signature") != signature:
        for key in ("tester_json", "tester_approved", "tester_output", "tester_editor"):
            st.session_state.pop(key, None)
        st.session_state.tester_source_signature = signature
    approved_snapshot = st.session_state.get("tester_approved")
    editor_text = st.session_state.get("tester_editor", "")
    is_approved = bool(approved_snapshot and approved_snapshot["hash"] == hashlib.sha256(editor_text.encode()).hexdigest())
    stage = 3 if is_approved and st.session_state.get("tester_output") else 2 if is_approved else 1 if "tester_json" in st.session_state else 0
    for index, (column, label) in enumerate(zip(st.columns(4), ["Add & convert", "Review JSON", "Choose action", "Export results"])):
        column.markdown(f'<div class="sx-step {"active" if index == stage else ""}">{index + 1:02d} &nbsp; {label}</div>', unsafe_allow_html=True)
    if sources:
        with st.expander(f"{len(sources)} source file(s) ready", icon=":material/description:"):
            for name, data in sources:
                st.markdown(f"**{escape(name)}** / {len(data) / 1024:.1f} KB")
    st.subheader("1. Convert input files to JSON")
    st.caption("Original extracted text, tables, metadata and source references are retained. LLM interpretations are proposals requiring review. Scanned PDFs need OCR before upload.")
    if st.button("Convert files to JSON", type="primary", disabled=not sources, icon=":material/auto_awesome:"):
        try:
            with st.spinner("Extracting and normalizing sources..."):
                normalized = canonicalize(sources, router, client_context)
            st.session_state.tester_json = normalized
            st.session_state.tester_editor = json.dumps(normalized, indent=2, ensure_ascii=False, default=str)
            st.session_state.pop("tester_approved", None)
            st.session_state.pop("tester_output", None)
        except Exception as exc:
            st.error(f"Conversion failed: {exc}")
    if "tester_json" not in st.session_state:
        illustration(st)
        st.info("Upload or paste your input in the sidebar. JSON and CSV can include explicit parameter contracts; other formats retain their source content for review or live AI extraction.")
        with st.expander("Example input: parameters and observed values"):
            st.code(json.dumps({"requirements": [{"id": "REQ-1", "text": "Speed shall be between 0 and 100 km/h."}], "parameters": [{"name": "speed", "type": "integer", "min": 0, "max": 100, "unit": "km/h", "requirement_id": "REQ-1"}], "samples": [{"parameter": "speed", "value": 101}]}, indent=2), language="json")
        return
    for warning in st.session_state.tester_json.get("warnings", []):
        st.warning(warning)
    summary = st.session_state.tester_json
    for column, label, key in zip(st.columns(4), ["Source files", "Requirements", "Parameters", "Observed values"], ["sources", "requirements", "parameters", "samples"]):
        column.metric(label, len(summary.get(key, [])))
    st.subheader("2. Review the common JSON")
    st.caption("Confirm bounds are inclusive, units agree, types and domains are correct, and requirement IDs map to the right parameters. Missing information must be supplied explicitly.")
    preview_tabs = st.tabs(["Parameter overview", "Requirements", "Source preview", "JSON editor"])
    try:
        preview = json.loads(st.session_state.tester_editor)
        if not isinstance(preview, dict):
            preview = summary
    except ValueError:
        preview = summary
    with preview_tabs[0]:
        parameters = preview.get("parameters", [])
        if isinstance(parameters, list) and parameters and all(isinstance(p, dict) for p in parameters):
            st.dataframe([{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in p.items()} for p in parameters], width="stretch", hide_index=True)
        else:
            st.info("No parameter constraints yet. Add them in the JSON editor before approving.")
    with preview_tabs[1]:
        requirements = preview.get("requirements", [])
        if isinstance(requirements, list) and requirements and all(isinstance(r, dict) for r in requirements):
            st.dataframe([{k: json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for k, v in r.items()} for r in requirements], width="stretch", hide_index=True)
        else:
            st.caption("No structured requirements extracted. Original source text remains available.")
    with preview_tabs[2]:
        for source in summary.get("sources", []):
            with st.expander(source["name"], icon=":material/description:"):
                st.text(source.get("content", ""))
    with preview_tabs[3]:
        edited = st.text_area("Canonical JSON (editable)", height=360, key="tester_editor")
    reviewer = st.text_input("Reviewer name", key="tester_reviewer")
    fingerprint = hashlib.sha256(edited.encode()).hexdigest()
    if st.button("Approve this JSON", icon=":material/verified:"):
        try:
            contract = bind_client(validate_contract(json.loads(edited)), client_context)
            if not reviewer.strip():
                raise ValueError("Enter a reviewer name")
            contract.setdefault("audit", []).append({"agent": "human_review", "reviewer": reviewer.strip(), "decision": "approve", "input_hash": fingerprint, "at": datetime.now(timezone.utc).isoformat()})
            st.session_state.tester_approved = {"hash": fingerprint, "contract": contract}
            st.session_state.pop("tester_output", None)
            st.success("JSON approved. Choose your next action below.")
        except (ValueError, TypeError) as exc:
            st.error(f"Cannot approve JSON: {exc}")
    approved = st.session_state.get("tester_approved")
    ready = bool(approved and approved["hash"] == fingerprint)
    if not ready:
        st.info("Approve the current JSON before running checks or generating tests. Editing JSON invalidates its previous approval.")
    st.download_button("Download common JSON", json.dumps(approved["contract"] if ready else st.session_state.tester_json, indent=2, ensure_ascii=False), "smartx-canonical.json", "application/json", icon=":material/download:")
    st.subheader("3. Choose the tester action")
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("### :material/fact_check: Verify values")
            st.caption("Check observed inputs against approved types, bounds, and allowed domains. See exactly what passed or failed.")
    with right:
        with st.container(border=True):
            st.markdown("### :material/code: Generate test code")
            st.caption("Build reviewable pytest cases for nominal values, boundaries, and invalid inputs. Download and connect your system.")
    action = st.radio("Action", ["Verify values", "Generate test code"], horizontal=True)
    use_team = st.toggle("Collaborating AI agents", value=router.name == "ollama", disabled=router.name == "deterministic",
                         help="Planner, analyst, specialist, critic and reporter communicate using your selected LLM. Up to seven role calls and one repair cycle.")
    if use_team:
        agent_team_settings(st, router)
    if st.button("Run selected action", type="primary", disabled=not ready, icon=":material/play_arrow:"):
        contract = approved["contract"]
        if use_team:
            with st.status("Agent team is collaborating...", expanded=True) as progress:
                def show_handoff(message):
                    st.write(f"{message['sender'].title()} → {message['recipient'].title()} · {message['kind'].replace('_', ' ')}")
                output = TestingAgentTeam(router, configured_team_routers(st, router), on_message=show_handoff).run(contract, "verify" if action == "Verify values" else "generate")
                team_status = output["agent_collaboration"]["status"]
                progress.update(label="Agent review complete" if team_status == "reviewed" else "Agent run needs human review", state="complete")
        else:
            output = verify(contract) if action == "Verify values" else generate_tests(contract)
        output["input_hash"] = fingerprint
        output["review"] = contract.get("audit", [])
        if client_context:
            output["client"] = {key: client_context[key] for key in ("id", "name", "revision")}
        st.session_state.tester_output = output
    output = st.session_state.get("tester_output")
    if not output or not ready or output.get("input_hash") != fingerprint:
        return
    st.subheader("4. Results and downloads")
    collaboration = output.get("agent_collaboration")
    if collaboration:
        st.caption(f"Agent team: {collaboration['status']} · {collaboration['calls']} model role calls · {collaboration['duration_seconds']}s")
        if collaboration.get("error"):
            st.warning(collaboration["error"])
        if collaboration.get("report"):
            st.write(collaboration["report"]["summary"])
            for step in collaboration["report"]["next_steps"]:
                st.write("• " + step)
        with st.expander("Agent conversation and handoffs", icon=":material/forum:"):
            st.caption(collaboration["note"])
            for message in collaboration["messages"]:
                st.markdown(f"**{message['id']} · {message['sender'].title()} → {message['recipient'].title()}**")
                if message.get("model"):
                    st.caption("Model: " + message["model"])
                st.json(message["payload"], expanded=False)
    if output.get("client_checks"):
        st.subheader("Client convention checks")
        st.dataframe(output["client_checks"], width="stretch", hide_index=True)
    if output["agent"] == "verification":
        findings = output["findings"]
        columns = st.columns(3)
        for column, status in zip(columns, ["PASS", "FAIL", "INSUFFICIENT_INFORMATION"]):
            column.metric(status.replace("_", " "), sum(row["status"] == status for row in findings))
        status_filter = st.selectbox("Show findings", ["All findings", "PASS", "FAIL", "INSUFFICIENT_INFORMATION"])
        visible = findings if status_filter == "All findings" else [row for row in findings if row["status"] == status_filter]
        st.dataframe([{**row, "value": json.dumps(row.get("value"), ensure_ascii=False), "checks": json.dumps(row.get("checks", []))} for row in visible], width="stretch")
        st.caption(output["note"])
    else:
        st.metric("Draft test cases", len(output["cases"]))
        st.warning("Draft code has not run against your system. Implement the documented adapter and review expected acceptance/rejection before execution.")
        for issue in output["unresolved"]:
            st.warning(issue)
        st.dataframe([{**case, "value": json.dumps(case["value"], ensure_ascii=False)} for case in output["cases"]], width="stretch")
        st.code(output["code"], language="python")
        st.download_button("Download pytest code", output["code"], "test_generated.py", "text/x-python", icon=":material/download:")
        st.code('$env:SMARTX_TEST_TARGET="your_adapter:accepts"\npython -m pytest -v test_generated.py', language="powershell")
    st.download_button("Download result JSON", json.dumps(output, indent=2, ensure_ascii=False), "smartx-testing-report.json", "application/json", icon=":material/download:")
