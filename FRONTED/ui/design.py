"""Shared visual system and session-scoped provider configuration."""
import os
from pathlib import Path

from llm.router import LLMRouter


def apply_design(st):
    css = (Path(__file__).parent / "assets" / "platform.css").read_text(encoding="utf-8")
    st.markdown("<style>" + css + "</style>", unsafe_allow_html=True)


def configured_router(st, provider):
    values = st.session_state.get("ai_configuration", {}).get(provider, {})
    return LLMRouter(provider, **values)


def provider_settings(st, provider):
    """Secrets stay in this session; never write global environment variables."""
    with st.expander("AI connection settings", icon=":material/tune:"):
        if provider == "deterministic":
            st.caption("Ready to use. Rule-based checks run locally without credentials. Choose a live provider for AI extraction.")
            return
        azure = provider == "azure_openai"
        defaults = {
            "openai": (os.getenv("SMARTX_LLM_ENDPOINT") or "https://api.openai.com", os.getenv("SMARTX_LLM_MODEL") or "gpt-4o-mini"),
            "azure_openai": (os.getenv("AZURE_OPENAI_ENDPOINT", ""), os.getenv("SMARTX_LLM_MODEL", "")),
            "ollama": (os.getenv("OLLAMA_ENDPOINT", "http://localhost:11434"), os.getenv("OLLAMA_MODEL", "qwen3:4b-instruct")),
        }
        saved = st.session_state.get("ai_configuration", {}).get(provider, {})
        with st.form("ai-settings-" + provider + "-" + str(st.session_state.get("ai_client_scope", "session"))):
            endpoint = st.text_input("Endpoint", value=saved.get("endpoint", defaults[provider][0]))
            model = st.text_input("Deployment name" if azure else "Model", value=saved.get("model", defaults[provider][1]))
            key = None
            if provider != "ollama":
                key = st.text_input("API key", value=saved.get("api_key", ""), type="password", help="Leave blank to use the configured environment key.")
            version = st.text_input("API version", value=saved.get("api_version", os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21"))) if azure else None
            timeout = st.number_input("Timeout (seconds)", min_value=5, max_value=120, value=int(saved.get("timeout", 120 if provider == "ollama" else 30)))
            apply = st.form_submit_button("Apply settings", icon=":material/check:")
            test = st.form_submit_button("Apply & test connection", icon=":material/wifi_tethering:")
            if apply or test:
                if not endpoint.startswith(("http://", "https://")) or not model.strip():
                    st.error("Enter an HTTP(S) endpoint and a model or deployment name.")
                else:
                    values = {"endpoint": endpoint.strip(), "model": model.strip(), "timeout": timeout}
                    if provider != "ollama":
                        values["api_key"] = key or (os.getenv("AZURE_OPENAI_API_KEY") if azure else os.getenv("SMARTX_LLM_API_KEY") or os.getenv("OPENAI_API_KEY"))
                    if azure:
                        values["api_version"] = version
                    st.session_state.setdefault("ai_configuration", {})[provider] = values
                    st.session_state.pop("ai_connection_status", None)
                    st.success("Settings applied to this session.")
                    if test:
                        with st.spinner("Checking provider connection..."):
                            st.session_state.ai_connection_status = {**configured_router(st, provider).connection_test(), "provider": provider}
        st.caption("Keys are held in session memory and are excluded from report downloads. Use .env for configuration across restarts.")


def illustration(st):
    st.image(str(Path(__file__).parent / "assets" / "testing-workspace.svg"), width="stretch")


def agent_team_settings(st, router):
    from agents.testing_team import ROLES
    with st.expander("Agent team models", icon=":material/groups:"):
        st.caption("Separate roles share structured handoffs and one critic repair cycle. You can use the same installed model for every role, or assign different models.")
        if st.button("Discover installed Ollama models", disabled=router.name != "ollama", icon=":material/refresh:"):
            try:
                st.session_state.team_installed_models = router.provider.list_models()
            except Exception:
                st.warning("Cannot list models. Check your Ollama connection settings.")
        installed = st.session_state.get("team_installed_models", [])
        if installed:
            st.caption("Installed: " + ", ".join(installed))
        with st.form("agent-team-models-" + str(st.session_state.get("ai_client_scope", "session"))):
            assignments = {}
            saved = st.session_state.get("team_model_assignments", {})
            for role in ROLES:
                assignments[role] = st.text_input(role.title() + " model", value=saved.get(role, ""), placeholder=getattr(router.provider, "model", "Default provider model"))
            if st.form_submit_button("Apply agent models", icon=":material/check:"):
                st.session_state.team_model_assignments = {k: v.strip() for k, v in assignments.items() if v.strip()}
                st.success("Agent model assignments applied. Blank roles use your main provider model.")
        st.caption("Model names must already be installed in Ollama. No models are downloaded by this panel.")


def configured_team_routers(st, router):
    from agents.testing_team import ROLES
    if router.name != "ollama":
        return {}
    values = dict(st.session_state.get("ai_configuration", {}).get("ollama", {}))
    values.setdefault("endpoint", router.provider.endpoint)
    values.setdefault("timeout", router.provider.timeout)
    values["retries"] = 0
    values.pop("model", None)
    assignments = st.session_state.get("team_model_assignments", {})
    return {role: LLMRouter("ollama", model=assignments.get(role, router.provider.model), **values) for role in ROLES}
