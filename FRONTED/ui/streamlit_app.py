"""Streamlit entrypoint for the SmartX MVP.

The path bootstrap is intentional: Streamlit executes this file with ``ui``
as the import context when launched from that directory.
"""

import json
import os
import csv
import sys
from dataclasses import asdict
from io import BytesIO
from pathlib import Path

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
if str(REPOSITORY_ROOT) not in sys.path:
	sys.path.insert(0, str(REPOSITORY_ROOT))

try:
	import streamlit as st
except ImportError:  # Allows compile/import checks without UI dependencies.
	st = None

from smartx.clients import ClientStore
from FRONTED.ui.client_workspace import NAVIGATION, NAV_ICONS, render_header, render_client_configuration, render_library, render_guide, render_dashboard, render_activity_or_reports
from llm.router import LLMRouter
from FRONTED.ui.design import apply_design, configured_router, provider_settings
from RAG.retriever import SessionRetriever
from smartx.pipeline import SmartXPipeline
from core.milestone3 import AgentState, JobRecord, SmartXWorkflow, WorkflowLimits, filter_traceability, report_csv, report_excel, report_json, report_pdf
from validation.configuration import ProfileConfiguration
from validation.evaluator import ValidationCase, ValidationDataset, ValidationEvaluator, build_regression_dataset
from validation.learning import LearnedCorrectionsStore
from smartx.deterministic_analysis import StructuralPlanner
from smartx.deterministic_analysis import StructuralCritic


SUPPORTED = ["txt", "md", "json", "xml", "csv", "xlsx", "xls", "xlsm", "docx", "pdf", "c", "h", "cpp", "cc", "hpp", "ptu"]


def _rows(result: dict) -> list[dict]:
	rows = []
	for entry in result.get("results", []):
		for finding in entry.get("findings", []):
			rows.append({"agent": entry["agent"], **finding})
	return rows


def _download_csv(result: dict) -> str:
	rows = _rows(result)
	columns = sorted({key for row in rows for key in row}) or ["agent", "status"]
	from io import StringIO
	buffer = StringIO()
	writer = csv.DictWriter(buffer, fieldnames=columns)
	writer.writeheader()
	writer.writerows({key: json.dumps(row.get(key, ""), ensure_ascii=False) if isinstance(row.get(key), (dict, list)) else row.get(key, "") for key in columns} for row in rows)
	return buffer.getvalue()


def _download_json(result: dict) -> str:
	return json.dumps(result, indent=2, ensure_ascii=False, default=str)


def _download_excel(result: dict) -> bytes:
	"""Return an XLSX when available, otherwise a UTF-8 CSV payload."""
	rows = _rows(result)
	try:
		import pandas as pd  # type: ignore
		target = BytesIO()
		pd.DataFrame(rows).to_excel(target, index=False, engine="openpyxl")
		return target.getvalue()
	except Exception:
		return _download_csv(result).encode("utf-8")


def _download_report(result: dict) -> str:
	document = result.get("document", {})
	lines = [
		f"SmartX review report: {document.get('title', 'Untitled')}",
		"=" * 40,
		f"Profile: {document.get('profile', 'generic')}",
		f"Confidence: {document.get('confidence', 0):.0%}",
		f"Human review required: {result.get('human_review_required', True)}",
		"",
	]
	for entry in result.get("results", []):
		lines.append(f"[{entry.get('agent', 'unknown')}] status={entry.get('status', 'unknown')}")
		for finding in entry.get("findings", []):
			lines.append(f"- {json.dumps(finding, ensure_ascii=False, default=str)}")
		for name, artifact in entry.get("artifacts", {}).items():
			lines.append(f"- {name}: {json.dumps(artifact, ensure_ascii=False, default=str)}")
	return "\n".join(lines) + "\n"


def _traceability_rows(result: dict) -> list[dict]:
	return filter_traceability(result.get("traceability", result.get("artifacts", {}).get("traceability_links", [])))


def render_validation_workspace(config_path=None) -> None:
	st.header("Validation workspace")
	st.caption("Evaluate SmartX against expected outputs. Results are quality indicators, not certification evidence.")
	config = ProfileConfiguration(config_path) if config_path else ProfileConfiguration()
	tabs = st.tabs(["Dataset", "Run evaluation", "Profile rules"])
	with tabs[0]:
		if st.button("Load built-in regression dataset"):
			st.session_state.validation_dataset = build_regression_dataset()
		dataset = st.session_state.get("validation_dataset", ValidationDataset("new-dataset"))
		st.write(f"**{dataset.name}** — {len(dataset.cases)} case(s)")
		st.dataframe([{"name": case.name, "filename": case.filename, "profile": case.profile} for case in dataset.cases], width="stretch")
		with st.form("validation_case"):
			name = st.text_input("Case name", value="case-1")
			filename = st.text_input("Filename", value="requirements.txt")
			text = st.text_area("Source content", value="The system shall record events.")
			expected = st.text_area("Expected SmartX JSON", value='{"document_type":"requirement","items":[]}')
			if st.form_submit_button("Add or replace case"):
				try:
					dataset.add_case(ValidationCase(name, filename, text.encode("utf-8"), json.loads(expected)))
					st.session_state.validation_dataset = dataset
					st.success("Case saved in the current session.")
				except json.JSONDecodeError as exc:
					st.error(f"Expected SmartX JSON is invalid: {exc}")
	with tabs[1]:
		dataset = st.session_state.get("validation_dataset", build_regression_dataset())
		if st.button("Run dataset evaluation"):
			st.session_state.validation_report = ValidationEvaluator().evaluate(dataset)
		report = st.session_state.get("validation_report")
		if report:
			st.metric("Cases", report["case_count"])
			st.json(report["metrics"])
			if report["weaknesses"]:
				st.warning("Detected weaknesses: " + "; ".join(report["weaknesses"]))
			st.download_button("Download evaluation JSON", ValidationEvaluator.report_json(report), "smartx-evaluation.json", "application/json")
			st.download_button("Download evaluation Excel", ValidationEvaluator.report_excel(report), "smartx-evaluation.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
			pdf = ValidationEvaluator.report_pdf(report)
			if pdf:
				st.download_button("Download evaluation PDF", pdf, "smartx-evaluation.pdf", "application/pdf")
	with tabs[2]:
		profile = st.selectbox("Profile", config.profiles(), key="validation-profile")
		profile_data = config.get(profile)
		rules_json = st.text_area("Rules JSON", json.dumps(profile_data.get("rules", []), indent=2), height=180)
		threshold = st.slider("Confidence threshold", 0.0, 1.0, float(profile_data.get("confidence_threshold", 0.75)))
		if st.button("Save profile configuration"):
			try:
				config.update(profile, {"rules": json.loads(rules_json), "confidence_threshold": threshold, "human_review_threshold": threshold})
				st.success("Profile configuration saved.")
			except json.JSONDecodeError as exc:
				st.error(f"Rules JSON is invalid: {exc}")


def process_sources(profile: str, provider: str, sources: list[tuple[str, bytes]], retriever: SessionRetriever, router=None, client_context=None) -> list[dict]:
	"""Process multiple pasted/uploaded sources without requiring an external provider."""
	processed = []
	for name, data in sources:
		if client_context:
			retriever.ingest_file(name, data, csv_delimiter=client_context.get("csv_delimiter", ","))
		else:
			retriever.ingest_file(name, data)
		workflow = SmartXWorkflow(
			profile=retriever.store.profile_config if hasattr(retriever.store, "profile_config") else {},
			llm_router=router or LLMRouter(provider),
			retriever=retriever,
			storage_dir=Path(retriever.store.persist_dir).parent / ".smartx_jobs",
			project=retriever.project,
		)
		state = workflow.new_state("Process uploaded engineering evidence", [(name, data)], profile=profile)
		if client_context:
			state.customer = client_context["id"]
			state.smartx_artifacts["client"] = client_context
		state.retrieved_knowledge = retriever.retrieve(data.decode("utf-8", errors="ignore")[:2000] or name, limit=5)
		state.citations = list(state.retrieved_knowledge)
		workflow.jobs.save(JobRecord(state.job_id, state.project, state.final_status, state=state.to_dict()))
		state = workflow.run(state)
		results = [{"agent": key, **value} for key, value in state.agent_results.items()]
		report = state.generated_artifacts.get("report", {})
		processed.append({
			"document": state.smartx_artifacts.get("document", {}),
			"results": results,
			"human_review_required": any(task.status == "open" for task in state.review_tasks),
			"workflow_state": state.to_dict(),
			"review_tasks": [asdict(task) for task in state.review_tasks],
			"audit": [asdict(event) for event in state.execution_history],
			"traceability": state.generated_artifacts.get("traceability_links", []),
			"report": report,
			"orchestration_job_id": state.job_id,
			"orchestration_status": state.final_status,
		})
	return processed


def main() -> None:
	try:
		from dotenv import load_dotenv
		load_dotenv(REPOSITORY_ROOT / ".env", override=False)
	except ImportError:
		pass
	if st is None:
		raise RuntimeError("Install Streamlit to run the SmartX UI")
	st.set_page_config(page_title="SX Aerospace | Engineering Platform", page_icon="✈️", layout="wide")
	apply_design(st)
	client_store = ClientStore(REPOSITORY_ROOT / ".smartx_clients")
	clients = client_store.list()
	client_lookup = {item["id"]: item for item in clients}
	pending = st.session_state.pop("pending_client_id", None)
	if pending in client_lookup:
		st.session_state.client_selector = pending
	if st.session_state.get("client_selector") not in client_lookup:
		st.session_state.client_selector = "default"
	context_columns = st.columns([2, 2, 3, 1, 1])
	with context_columns[0]:
		client_id = st.selectbox("Active client", list(client_lookup), format_func=lambda key: client_lookup[key]["name"], key="client_selector")
	client = client_lookup[client_id]
	with context_columns[1]:
		project = st.text_input("Project name", value="default", key="project-" + client_id)
	profile = client["profile"]
	scope = (client_id, client["revision"], project, profile)
	if st.session_state.get("workspace_scope") != scope:
		st.session_state.pop("retriever", None)
		st.session_state.workspace_scope = scope
		for key in ("analysis_results", "tester_json", "tester_approved", "tester_output", "tester_editor", "tester_source_signature", "verification_output", "generation_output", "pending_canonical_edit", "validation_dataset", "validation_report", "tester_reviewer"):
			st.session_state.pop(key, None)
	with context_columns[2]:
		search = st.text_input("Search project documents", placeholder="Search documents...")
	with context_columns[3]:
		with st.popover("Notifications"):
			st.caption("Current project review queue")
			st.write("Canonical review required" if st.session_state.get("tester_json") and not st.session_state.get("tester_approved") else "No pending canonical review in this session.")
	with context_columns[4]:
		with st.popover("Profile"):
			st.caption("Local workspace - no identity provider configured")
			st.write(st.session_state.get("tester_reviewer") or "Reviewer not set")
	if search:
		matches = [d for d in client_store.documents(client_id, project) if search.casefold() in (d['name'] + d.get('text', '')).casefold()]
		st.dataframe([{"Document": d['name']} for d in matches], hide_index=True)
	with st.sidebar:
		st.markdown('<div class="sx-brand"><span>SX</span> Aerospace</div>', unsafe_allow_html=True)
		st.caption(f"{client['industry']} / Configuration v{client['revision']}")
		advanced_navigation = st.toggle("Advanced workspaces", value=st.session_state.get("platform_navigation") in NAVIGATION[9:])
		if not advanced_navigation:
			st.markdown('<style>[data-testid="stSidebar"] [role="radiogroup"] > label:nth-of-type(n+10){display:none}</style>', unsafe_allow_html=True)
		workspace = st.radio("Navigation", NAVIGATION, key="platform_navigation", format_func=lambda name: f":material/{NAV_ICONS[name]}: " + ({"Reports": "Reports & Traceability", "Client configuration": "Client Configuration"}.get(name, name)))
		project_directory = client_store.project_directory(client_id, project)
		persist_directory = str(project_directory / "knowledge")
		if workspace in {"Document Library", "Processing"} and "retriever" not in st.session_state:
			with st.spinner("Opening this client's project knowledge..."):
				st.session_state.retriever = SessionRetriever(persist_directory=persist_directory, project=project, profile=profile)
		ai_scope = client_id
		if st.session_state.get("ai_client_scope") != ai_scope:
			for key in ("ai_configuration", "ai_connection_status", "team_model_assignments", "team_installed_models"):
				st.session_state.pop(key, None)
			st.session_state.team_model_assignments = dict(client["agent_models"])
			st.session_state.ai_client_scope = ai_scope
		if st.session_state.get("ai_profile_revision") != (client_id, client["revision"]):
			st.session_state.team_model_assignments = dict(client["agent_models"])
			st.session_state.ai_profile_revision = (client_id, client["revision"])
		providers = ["deterministic", "ollama"]
		configured = client["preferred_provider"] or os.getenv("SMARTX_LLM_PROVIDER", "deterministic")
		provider = st.selectbox("AI provider", providers, index=providers.index(configured) if configured in providers else 0, key=f"provider-{client_id}-{client['revision']}")
		with st.expander("Connection & source tools", expanded=workspace in {"Software tester", "Processing", "Document Library", "AI Agent Studio"}):
			provider_settings(st, provider)
			if st.button("Test provider connection", icon=":material/wifi_tethering:", width="stretch"):
				with st.spinner("Checking connection..."):
					st.session_state.ai_connection_status = {**configured_router(st, provider).connection_test(), "provider": provider}
			connection = st.session_state.get("ai_connection_status", {})
			if connection.get("provider") == provider:
				if connection.get("ok"):
					st.success("Connection verified")
				else:
					st.error(connection.get("error", "Connection failed."))
					st.info(connection.get("hint", "Apply your connection settings, then test again."))
					st.caption("Provider check: " + connection.get("code", "unknown") + ". Browser HTTP 200 responses do not confirm that the LLM request succeeded.")
			st.divider()
			st.markdown("**Source documents**")
			use_demo = st.toggle("Try sample requirements", help="Load a ready-to-use speed contract with valid and invalid observations.")
		st.markdown('<div class="sx-upload-label">Project sources</div><div class="sx-upload-help">PDF · DOCX · XLSX · XLSM · XLS · CSV · PTU · XML · JSON · C/C++ · TXT · MD</div>', unsafe_allow_html=True)
		uploaded = st.file_uploader("Choose files", type=None if workspace == "AI Agent Studio" else SUPPORTED, accept_multiple_files=True, key=f"uploads-{client_id}-{project_directory.name}", label_visibility="collapsed", help="Supported formats: PDF, DOCX, XLSX, XLSM, XLS, CSV, PTU, XML, JSON, C/C++, TXT and MD.")
		pasted = st.text_area("Paste requirements or source text", height=130, placeholder="The system shall ...", key=f"pasted-{client_id}-{project_directory.name}")
		st.info("Supported formats: PDF · DOCX · XLSX · XLSM · XLS · CSV · PTU · XML · JSON · C/C++ · TXT · MD")
		st.caption("Tool access is limited to the selected local provider and authorized retriever.")
		st.caption(f"Client data space: {client['name']} / {project}")
	render_header(st, client, project, workspace, provider)
	from FRONTED.ui.redesign import restore_draft, render_import, render_check, render_generation, render_projects, render_rules
	try:
		restore_draft(project_directory, st.session_state)
	except (ValueError, OSError) as exc:
		st.error(f"Unable to recover project draft: {exc}")
	if workspace == "Smart Import":
		render_import(st, [], configured_router(st, provider), client_store.context(client_id, project), project_directory)
		return
	if workspace == "Smart Check":
		render_check(st, project_directory)
		return
	if workspace == "Test Generation":
		render_generation(st, project_directory)
		return
	if workspace == "Projects":
		render_projects(st, client_store, client, project)
		return
	if workspace == "Rules Manager":
		render_rules(st, client_store, client, project)
		return
	if st.session_state.get("client_saved_notice"):
		st.success(st.session_state.pop("client_saved_notice"))
	if workspace == "Validation workspace":
		render_validation_workspace(project_directory / "validation_profiles.json")
		return
	sources = [(item.name, item.getvalue()) for item in (uploaded or [])]
	if pasted.strip():
		sources.insert(0, ("pasted_text.txt", pasted.encode("utf-8")))
	if use_demo and not sources:
		sources = [("sample-speed-requirements.json", json.dumps({"requirements": [{"id": "REQ-SPEED-01", "text": "Speed shall be an integer between 0 and 100 km/h."}], "parameters": [{"name": "speed", "type": "integer", "min": 0, "max": 100, "unit": "km/h", "requirement_id": "REQ-SPEED-01"}], "samples": [{"parameter": "speed", "value": value} for value in [0, 50, 100, 101, -1]]}).encode())]
	if workspace == "AI Agent Studio":
		from FRONTED.ui.agent_studio import render_studio
		render_studio(st, client_store, client, project, sources)
		return
	if workspace == "Client configuration":
		render_client_configuration(st, client_store, client)
		from FRONTED.ui.redesign import render_precision
		render_precision(st, client_store, client, project)
		return
	if workspace == "Guide":
		render_guide(st, client)
		return
	if workspace == "Dashboard":
		from FRONTED.ui.redesign import render_dashboard as render_project_dashboard
		render_project_dashboard(st, client_store, client, project)
		return
	if workspace == "Document Library":
		render_library(st, client_store, client, project, st.session_state.retriever, sources)
		return
	if workspace == "Reports":
		from FRONTED.ui.redesign import render_reports
		render_reports(st, client_store, client, project)
		return
	if workspace == "Agent activity":
		render_activity_or_reports(st, workspace)
		return
	if workspace == "Software tester":
		from FRONTED.ui.testing_workspace import render_testing_workspace
		render_testing_workspace(st, sources, configured_router(st, provider), client_store.context(client_id, project))
		return
	if st.button("Run engineering analysis", type="primary", disabled=not sources):
		try:
			with st.spinner("Indexing evidence and running agents until review is needed..."):
				st.session_state.analysis_results = process_sources(profile, provider, sources, st.session_state.retriever, configured_router(st, provider), client_store.context(client_id, project))
		except Exception as exc:
			st.error(f"Analysis failed: {exc}")
	if st.session_state.get("analysis_results"):
		try:
			results = st.session_state.analysis_results
			result = results[0] if len(results) == 1 else {"documents": [item["document"] for item in results], "document": {"title": f"{len(results)} sources"}, "results": [entry for item in results for entry in item["results"]], "human_review_required": any(item.get("human_review_required") for item in results), "review_tasks": [task for item in results for task in item.get("review_tasks", [])], "audit": [event for item in results for event in item.get("audit", [])]}
			st.success(f"Analysis saved for {len(results)} source(s)")
			cols = st.columns(3)
			cols[0].metric("Sources", len(results))
			cols[1].metric("Agents completed", sum(len(item["results"]) for item in results))
			cols[2].metric("Open reviews", sum(task.get("status") == "open" for task in result.get("review_tasks", [])))
			st.caption("Workflow: " + " / ".join(item.get("orchestration_status", "unknown") for item in results))
			if result.get("human_review_required"):
				st.warning("Human review required: extraction or analysis confidence is below the automatic acceptance threshold.")
			tabs = st.tabs(["Understanding", "Validation", "Compliance", "Traceability", "Generation", "Assistant", "Review Queue", "Audit", "Evaluation", "Reports"])
			with tabs[0]:
				confidence = result.get("document", {}).get("confidence", 0)
				st.metric("Confidence", f"{confidence:.0%}")
				document = result.get("document", result)
				understanding = document.get("metadata", {}).get("understanding", {})
				st.subheader("Understanding Inspector")
				st.json({"classification": understanding.get("classification", document.get("document_type")), "structure": understanding.get("structure", {}), "profile_suggestion": understanding.get("profile_suggestion", {}), "evidence": understanding.get("evidence", [])})
				with st.expander("Extracted document details"):
					st.json(document)
				if st.checkbox("Show deterministic plan and critic", key="show-planner"):
					plan = StructuralPlanner().plan("analyze uploaded engineering evidence", understanding)
					st.json(plan.to_dict())
					st.json(StructuralCritic().review(plan, document).to_dict())
			for tab, agent_name in zip(tabs[1:5], ["validation", "compliance", "traceability", "generation"]):
				with tab:
					entries = [entry for entry in result["results"] if entry["agent"] == agent_name]
					st.json(entries[0] if entries else {})
			with tabs[3]:
				links = _traceability_rows(result)
				st.metric("Graph links", len(links))
				if links:
					st.dataframe(links, width="stretch")
					st.download_button("Download traceability CSV", report_csv({"findings": links}), "traceability.csv", "text/csv")
					st.download_button("Download traceability Excel", report_excel({"findings": links}), "traceability.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
			with tabs[5]:
				question = st.text_input("Ask about this session")
				if st.button("Ask assistant", disabled=not question.strip()):
					context = st.session_state.retriever.retrieve(question)
					if not context:
						st.warning("No matching evidence found. Add relevant sources first.")
					else:
						answer = configured_router(st, provider).complete_json(f"Question: {question}\nEVIDENCE: {context}\nReturn an answer grounded only in evidence, and citations.", ["answer", "citations"])
						st.write(answer["answer"])
						if answer.get("warning"):
							st.warning(answer["warning"])
						with st.expander("Retrieved evidence"):
							st.json(context)
			with tabs[6]:
				st.caption("Review decisions are persisted locally and never treated as certification approval.")
				for entry in result.get("review_tasks", []):
					st.write(f"**{entry.get('kind', 'review')}** · {entry.get('status', 'open')} · {entry.get('source', '')}")
					st.json({"proposal": entry.get("proposal"), "citations": entry.get("citations", [])})
					if entry.get("status") == "open":
						with st.form("review-" + entry["id"]):
							reviewer = st.text_input("Reviewer name")
							decision = st.selectbox("Decision", ["approve", "reject"])
							comment = st.text_area("Comment")
							if st.form_submit_button("Save decision and resume"):
								if not reviewer.strip():
									st.error("Enter a reviewer name.")
								else:
									for item in results:
										state = AgentState.from_dict(item["workflow_state"])
										if any(task.id == entry["id"] for task in state.review_tasks):
											workflow = SmartXWorkflow(llm_router=configured_router(st, provider), retriever=st.session_state.retriever, project=project, storage_dir=Path(persist_directory).parent / ".smartx_jobs")
											workflow.decide(state, entry["id"], decision, reviewer.strip(), comment)
											state = workflow.run(state)
											item.update(workflow_state=state.to_dict(), results=[{"agent": key, **value} for key, value in state.agent_results.items()], review_tasks=[asdict(task) for task in state.review_tasks], audit=[asdict(event) for event in state.execution_history], orchestration_status=state.final_status, human_review_required=any(task.status == "open" for task in state.review_tasks), report=state.generated_artifacts.get("report", {}), traceability=state.generated_artifacts.get("traceability_links", []))
									st.session_state.analysis_results = results
									st.rerun()
			with tabs[7]:
				st.subheader("Audit timeline")
				st.dataframe(result.get("audit", result.get("audit_metadata", {})), width="stretch")
			with tabs[8]:
				findings = _rows(result)
				st.metric("Findings", len(findings))
				st.metric("Citation coverage", f"{sum(bool(row.get('citations')) for row in findings) / len(findings):.0%}" if findings else "0%")
				st.subheader("Mappings and citations")
				st.json({"citations": result.get("report", {}).get("citations", result.get("citations", [])), "traceability": _traceability_rows(result)})
			with tabs[9]:
				report = result.get("report", result)
				st.download_button("Download JSON report", report_json(report), "smartx-report.json", "application/json")
				st.download_button("Download findings CSV", report_csv(report), "smartx-findings.csv", "text/csv")
				st.download_button("Download Excel report", report_excel(report), "smartx-report.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
				pdf = report_pdf(report)
				if pdf:
					st.download_button("Download PDF report", pdf, "smartx-report.pdf", "application/pdf")
				else:
					st.info("PDF export is unavailable; install the optional ReportLab dependency to enable it.")
				st.download_button("Download human-readable report", _download_report(result), "smartx-report.txt", "text/plain")
		except Exception as exc:
			st.error(f"Unable to process document safely: {exc}")
	else:
		st.subheader("Start with your engineering evidence")
		st.write("Upload a document or paste requirements in the sidebar, then click Run engineering analysis.")
		cards = st.columns(3)
		with cards[0]:
			st.info("1. Add sources\n\nRequirements, design documents, source code, or test specifications.")
		with cards[1]:
			st.info("2. Analyze and review\n\nAgents extract, validate, link evidence, and pause for your decisions.")
		with cards[2]:
			st.info("3. Export findings\n\nDownload reports and traceability with a recorded review history.")
		st.subheader("Project knowledge base")
		kb_tabs = st.tabs(["Documents", "Chunks", "Retrieval test", "Maintenance"])
		with kb_tabs[0]:
			st.caption("Authorized collections")
			st.json(st.session_state.retriever.list_collections())
			st.json(st.session_state.retriever.list_documents())
		with kb_tabs[1]:
			st.json(st.session_state.retriever.preview())
		with kb_tabs[2]:
			query = st.text_input("Search authorized collection")
			if query:
				st.json(st.session_state.retriever.retrieve(query))
		with kb_tabs[3]:
			col1, col2 = st.columns(2)
			with col1:
				if st.button("Clear current collection"):
					st.session_state.retriever.clear()
					st.success("Current collection cleared.")
			with col2:
				if st.button("Rebuild current collection"):
					st.session_state.retriever.rebuild()
					st.success("Current collection rebuilt; upload sources to index it again.")
		st.markdown("Upload a source document to begin Document Understanding, Validation, Compliance, Traceability, Generation, and Assistant workflows.")


if __name__ == "__main__":
	from FRONTED.ui.web_launcher import main as launch_web_interface
	launch_web_interface()
