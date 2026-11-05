"""Client administration, document library and engineering guide pages."""
import json
import hashlib
from html import escape

from smartx.clients import DEFAULT_CLIENT, ALIAS_FIELDS


NAVIGATION = ["Dashboard", "Projects", "Smart Import", "Smart Check", "Test Generation", "AI Agent Studio", "Client configuration", "Rules Manager", "Reports", "Guide", "Document Library", "Software tester", "Processing", "Validation workspace", "Agent activity"]
NAV_ICONS = {"Guide": "explore", "Dashboard": "space_dashboard", "Document Library": "folder_open", "Software tester": "fact_check", "Processing": "account_tree", "Validation workspace": "rule", "Client configuration": "settings", "Agent activity": "forum", "Reports": "description"}
NAV_ICONS["AI Agent Studio"] = "hub"
NAV_ICONS.update({"Projects":"folder_open", "Smart Import":"upload_file", "Smart Check":"fact_check", "Test Generation":"code", "Rules Manager":"rule"})


def goto(st, page):
    st.session_state.platform_navigation = page


def render_header(st, client, project, page, provider=None):
    connection = st.session_state.get('ai_connection_status', {})
    availability = (str(provider).title() + ' connected') if connection.get('ok') and connection.get('provider') == provider else 'Provider not verified'
    st.markdown(f'<div class="platform-header"><div class="platform-mark">SX</div><div><strong>SX Aerospace</strong><small>{escape(client["industry"])} · {escape(client["profile"].upper())}</small></div><div class="platform-location">{escape(page)}</div><div class="platform-service">{escape(availability)}</div><div class="platform-client">{escape(client["name"])}<small>{escape(project)}</small></div></div>', unsafe_allow_html=True)
    st.caption(f"{client['name']} / {project} / {page}     ·     Client configuration v{client['revision']}")


def mapping_editor(st, label, mapping, key, targets=None):
    import pandas as pd
    st.markdown("**" + label + "**")
    frame = pd.DataFrame([{"client_name": k, "canonical_name": v} for k, v in mapping.items()], columns=["client_name", "canonical_name"])
    target_column = st.column_config.SelectboxColumn("Platform field / type", options=sorted(targets)) if targets else st.column_config.TextColumn("Meaning / preferred term")
    return st.data_editor(frame, num_rows="dynamic", hide_index=True, width="stretch", key=key,
                          column_config={"client_name": st.column_config.TextColumn("Client term / column"), "canonical_name": target_column})


def mapping_values(frame):
    result = {}
    for row in frame.fillna("").to_dict("records"):
        key, value = str(row["client_name"]).strip(), str(row["canonical_name"]).strip()
        if not key and not value:
            continue
        if not key or not value or key in result:
            raise ValueError("Each mapping needs a unique client term and a platform field or meaning")
        result[key] = value
    return result


def render_client_configuration(st, store, client):
    st.header("Client configuration", anchor=False)
    st.caption("Manage how this client names, writes, structures and verifies engineering information. Saved revisions apply to the next analysis.")
    create, configure, transfer = st.tabs(["Create client", "Edit active client", "Import / export"])
    with create:
        with st.form("new-client"):
            name = st.text_input("New client name", placeholder="Company or customer name")
            industry = st.text_input("Industry / programme", value="Aerospace")
            if st.form_submit_button("Create client", type="primary", icon=":material/add_business:"):
                try:
                    record = store.save({**DEFAULT_CLIENT, "name": name.strip(), "industry": industry.strip()})
                    st.session_state.pending_client_id = record["id"]
                    st.rerun()
                except ValueError as exc:
                    st.error(str(exc))
    with configure:
        with st.form("client-editor-" + client["id"]):
            sections = st.tabs(["Identity", "Writing conventions", "Data mappings", "Verification rules", "Agent defaults"])
            with sections[0]:
                name = st.text_input("Client name", value=client["name"])
                industry = st.text_input("Industry", value=client["industry"])
                description = st.text_area("Client / programme information", value=client["description"])
                contact = st.text_input("Client contact", value=client["contact"])
                languages = ["English", "French", "Arabic", "Bilingual"]
                language = st.selectbox("Working language", languages, index=languages.index(client["language"]) if client["language"] in languages else 0)
                profiles = list(dict.fromkeys(["generic", "do178c", "gt44", "airbus", "safran", client["profile"]]))
                profile = st.selectbox("Engineering profile", profiles, index=profiles.index(client["profile"]))
            with sections[1]:
                prefix = st.text_input("Requirement identifier prefix", value=client["requirement_prefix"], help="Example: ACME-SWR- or REQ-. Empty disables the prefix check.")
                keywords = st.text_input("Normative words (comma separated)", value=", ".join(client["normative_keywords"]), help="Examples: shall, must, doit, devra")
                required = st.text_input("Required requirement fields (comma separated)", value=", ".join(client["required_requirement_fields"]))
                writing = st.text_area("Writing and interpretation guidance", value=client["writing_guidance"], height=130)
                glossary = mapping_editor(st, "Client vocabulary / abbreviations", client["glossary"], "glossary-" + client["id"])
                st.caption("Example: Vitesse → speed, SWR → Software requirement. Add rows using the table's + control.")
            with sections[2]:
                delimiters = [",", ";", "\t", "|"]
                delimiter = st.selectbox("CSV column separator", delimiters, index=delimiters.index(client["csv_delimiter"]), format_func=lambda x: {",": "Comma (,)", ";": "Semicolon (;)", "\t": "Tabulation", "|": "Pipe (|)"}[x])
                decimal = st.selectbox("Decimal separator in source tables", [".", ","], index=0 if client["decimal_separator"] == "." else 1)
                st.caption("Map the client's table headers to canonical names. Original source tables remain available.")
                aliases = mapping_editor(st, "Source column mappings", client["column_aliases"], "aliases-" + client["id"], ALIAS_FIELDS)
                type_aliases = mapping_editor(st, "Client data type names", client["type_aliases"], "types-" + client["id"], {"integer", "number", "string", "boolean"})
                st.caption("Examples: Identifiant → requirement_id, Exigence → text, Valeur → value, entier → integer.")
            with sections[3]:
                st.caption("Rules are evaluated deterministically. Targets: requirement_text, requirement_id, parameter_unit. Operators: required, contains, starts_with.")
                import pandas as pd
                rules = st.data_editor(pd.DataFrame(client["rules"], columns=["id", "target", "operator", "value", "severity"]), num_rows="dynamic", hide_index=True, width="stretch", key="rules-" + client["id"],
                    column_config={"id": st.column_config.TextColumn("Rule ID"), "target": st.column_config.SelectboxColumn("Check", options=["requirement_text", "requirement_id", "parameter_unit"]),
                                   "operator": st.column_config.SelectboxColumn("Condition", options=["required", "contains", "starts_with"]), "value": st.column_config.TextColumn("Expected text / prefix"),
                                   "severity": st.column_config.SelectboxColumn("Severity", options=["warning", "error"])})
                st.caption("Example: UNIT-01 · parameter_unit · required · error ensures each parameter has a unit.")
            with sections[4]:
                providers = ["", "deterministic", "ollama", "openai", "azure_openai"]
                preferred = st.selectbox("Preferred provider", providers, index=providers.index(client["preferred_provider"]), format_func=lambda x: x or "Use environment default")
                models = {role: st.text_input(role.title() + " default model", value=client["agent_models"].get(role, ""), placeholder="Inherit provider model") for role in ("planner", "analyst", "verifier", "generator", "critic", "reporter")}
                st.caption("API keys are not saved in client profiles. Configure credentials through AI connection settings for the active client session.")
            if st.form_submit_button("Save client configuration", type="primary", icon=":material/save:"):
                try:
                    record = store.save({**client, "name": name, "industry": industry, "description": description, "contact": contact, "language": language, "profile": profile,
                                         "requirement_prefix": prefix, "normative_keywords": [x.strip() for x in keywords.split(",") if x.strip()], "required_requirement_fields": [x.strip() for x in required.split(",") if x.strip()],
                                         "writing_guidance": writing, "glossary": mapping_values(glossary), "decimal_separator": decimal, "csv_delimiter": delimiter, "column_aliases": mapping_values(aliases), "type_aliases": mapping_values(type_aliases),
                                         "rules": [r for r in rules.fillna("").to_dict("records") if any(str(v).strip() for v in r.values())],
                                         "preferred_provider": preferred, "agent_models": {role: model.strip() for role, model in models.items() if model.strip()}})
                    st.session_state.client_saved_notice = f"{record['name']} saved as configuration v{record['revision']}."
                    st.rerun()
                except (ValueError, TypeError) as exc:
                    st.error(f"Cannot save client: {exc}")
    with transfer:
        st.download_button("Export client configuration", json.dumps(client, indent=2, ensure_ascii=False), "client-configuration.json", "application/json", icon=":material/download:")
        uploaded = st.file_uploader("Import a client configuration", type=["json"], key="client-profile-import")
        if st.button("Import as new client", disabled=uploaded is None, icon=":material/upload:"):
            try:
                record = store.import_profile(json.loads(uploaded.getvalue()))
                st.session_state.pending_client_id = record["id"]
                st.rerun()
            except (ValueError, TypeError) as exc:
                st.error(f"Cannot import client: {exc}")


def render_library(st, store, client, project, retriever, sources):
    st.header("Document Library", anchor=False)
    st.caption(f"Documents for {client['name']} / {project}. Other client and project collections are kept separate.")
    guidance = st.checkbox("Use selected documents as client guidance", help="Guidance excerpts are supplied as reference data to the agents, never as executable instructions.")
    if st.button("Add selected sources to library", disabled=not sources, type="primary", icon=":material/library_add:"):
        for name, data in sources:
            try:
                store.add_document(client["id"], project, name, data, guidance)
                retriever.ingest_file(name, data, project_rules=guidance, csv_delimiter=client["csv_delimiter"])
                if guidance:
                    for key in ("tester_json", "tester_approved", "tester_output", "tester_editor", "tester_source_signature", "analysis_results"):
                        st.session_state.pop(key, None)
                st.success(f"Added {name}")
            except (ValueError, OSError) as exc:
                st.error(f"{name}: {exc}")
    documents = store.documents(client["id"], project)
    if not documents:
        st.info("Upload source files in the sidebar, then add them here. Mark style guides and client terminology documents as guidance.")
    for document in documents:
        with st.expander(document["name"] + (" · Client guidance" if document["guidance"] else ""), icon=":material/description:"):
            st.text(document["text"])
            st.caption("Source SHA-256: " + document["hash"])
    query = st.text_input("Search this client's project knowledge", placeholder="Find requirements, terminology or guidance...")
    if query:
        st.json(retriever.retrieve(query), expanded=False)


def render_guide(st, client):
    st.header("Engineering workflow guide", anchor=False)
    st.caption("A requirements-to-verification workspace inspired by the V-model. This guide describes the platform workflow; it does not assert compliance with a standard.")
    columns = st.columns(6)
    labels = [("description", "01", "Source information", "Client requirements, data, specifications and conventions."), ("data_object", "02", "Canonical contract", "Normalize supported files into one source-linked JSON."), ("verified_user", "03", "Human review", "Confirm constraints, units, identifiers and interpretation."), ("code", "04", "Test development", "Generate draft tests with nominal, boundary and invalid values."), ("fact_check", "05", "Verification", "Check observed values using approved rules and constraints."), ("assignment", "06", "Evidence & review", "Inspect agent handoffs and export reports and test code.")]
    paths = ["M6 3h9l4 4v14H6z M9 10h7 M9 14h7 M9 18h5", "M8 5L2 12l6 7 M16 5l6 7-6 7 M14 3l-4 18", "M12 2l9 4v7c0 5-9 9-9 9S3 18 3 13V6z M7 12l3 3 7-7", "M8 5L2 12l6 7 M16 5l6 7-6 7", "M4 5h16v16H4z M7 12l3 3 7-7", "M6 3h12v18H6z M9 8h6 M9 12h6 M9 16h4"]
    for column, (icon, number, title, description), path in zip(columns, labels, paths):
        column.markdown(f'<div class="guide-lane"><div class="guide-cap"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="{path}"/></svg><small>STAGE {number}</small><strong>{title}</strong></div><p>{description}</p></div>', unsafe_allow_html=True)
    left, right = st.columns(2)
    with left:
        with st.container(border=True):
            st.markdown("### Requirements & client context")
            st.write("Define client terminology and writing rules, upload source evidence, then review the normalized contract.")
            st.button("Configure this client", icon=":material/settings:", on_click=goto, args=(st, "Client configuration"), width="stretch")
    with right:
        with st.container(border=True):
            st.markdown("### Verification & test generation")
            st.write("Use trusted checks and collaborating LLM roles to produce findings and draft test artifacts.")
            st.button("Open software tester", type="primary", icon=":material/play_arrow:", on_click=goto, args=(st, "Software tester"), width="stretch")
    st.info(f"Active client: {client['name']} · {client['language']} · configuration v{client['revision']}. Configure your own conventions before importing client-specific documents.")


def render_dashboard(st, store, client, project):
    st.header("Project dashboard", anchor=False)
    documents = store.documents(client["id"], project)
    normalized = st.session_state.get("tester_json", {})
    result = st.session_state.get("tester_output", {})
    metrics = [("Library documents", len(documents)), ("Requirements in session", len(normalized.get("requirements", []))), ("Observed FAIL findings", sum(x.get("status") == "FAIL" for x in result.get("findings", []))), ("Agent role calls", result.get("agent_collaboration", {}).get("calls", 0))]
    for column, (label, value) in zip(st.columns(4), metrics):
        column.metric(label, value)
    st.subheader("Active client conventions")
    st.write(f"**{client['name']}** · {client['language']} · requirement prefix `{client['requirement_prefix'] or 'No prefix rule'}`")
    st.write(client["writing_guidance"])
    st.caption("Session metrics describe the current browser session, not a historical project-wide test execution total.")
    st.button("Continue testing", type="primary", on_click=goto, args=(st, "Software tester"))


def render_activity_or_reports(st, page):
    result = st.session_state.get("tester_output")
    st.header(page, anchor=False)
    if not result:
        st.info("Run a software tester action to populate this view for the selected client and project.")
        st.button("Open software tester", on_click=goto, args=(st, "Software tester"))
        return
    edited = st.session_state.get("tester_editor", "")
    if edited and result.get("input_hash") != hashlib.sha256(edited.encode()).hexdigest():
        st.info("The contract has changed since this result. Approve the edited JSON and rerun before exporting current results.")
        return
    if page == "Agent activity":
        team = result.get("agent_collaboration", {})
        if not team:
            st.info("This action used deterministic checks. Enable collaborating AI agents on the next run to see agent messages.")
        for message in team.get("messages", []):
            with st.expander(f"{message['id']} · {message['sender']} → {message['recipient']}"):
                st.json(message)
    else:
        st.download_button("Download tester report", json.dumps(result, indent=2, ensure_ascii=False), "smartx-testing-report.json", "application/json", icon=":material/download:")
        if "code" in result:
            st.download_button("Download pytest code", result["code"], "test_generated.py", "text/x-python", icon=":material/code:")
        approved = st.session_state.get("tester_approved")
        if approved:
            st.download_button("Download approved contract", json.dumps(approved["contract"], indent=2, ensure_ascii=False), "smartx-canonical.json", "application/json")
