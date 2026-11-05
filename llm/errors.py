"""Actionable connection errors without exposing provider payloads or secrets."""
import json
import socket
import ssl
import urllib.error


class ProviderConnectionError(RuntimeError):
    def __init__(self, message, hint, *, code="connection_error", status=None):
        super().__init__(message)
        self.hint, self.code, self.status = hint, code, status


def connection_error(exc):
    if isinstance(exc, ProviderConnectionError):
        return exc
    if isinstance(exc, urllib.error.HTTPError):
        code = None
        try:
            body = json.loads(exc.read(16384))
            error = body.get("error", {})
            code = error.get("code") if isinstance(error, dict) else None
        except (ValueError, OSError, AttributeError):
            pass
        messages = {
            400: ("The provider rejected the request (HTTP 400).", "Check the model, deployment, API version and endpoint compatibility."),
            401: ("Authentication failed (HTTP 401).", "Enter a valid key for this provider, click Apply settings, then test again."),
            403: ("Access denied (HTTP 403).", "Check model permissions and the provider's network or resource access rules."),
            404: ("Endpoint or model not found (HTTP 404).", "Check the endpoint and model/deployment name. For Ollama, install the selected model first."),
            429: ("Provider rate or quota limit reached (HTTP 429).", "Check API usage and available credits, or wait before retrying."),
        }
        if code == "insufficient_quota":
            message, hint = "API quota is exhausted (HTTP 429).", "Check API billing and available credits in your provider account."
        else:
            message, hint = messages.get(exc.code, (f"Provider returned HTTP {exc.code}.", "Check provider availability and retry. A proxy may also be blocking the request."))
        return ProviderConnectionError(message, hint, code=f"http_{exc.code}", status=exc.code)
    reason = exc.reason if isinstance(exc, urllib.error.URLError) else exc
    if isinstance(reason, ssl.SSLError):
        return ProviderConnectionError("TLS certificate verification failed.", "Check the certificate chain and your organization's proxy certificates. Keep TLS verification enabled.", code="tls_error")
    if isinstance(reason, (TimeoutError, socket.timeout)):
        return ProviderConnectionError("The provider did not respond before the timeout.", "Check connectivity or increase Timeout in AI connection settings.", code="timeout")
    if isinstance(reason, (ConnectionError, OSError)) or isinstance(exc, urllib.error.URLError):
        return ProviderConnectionError("Cannot reach the provider.", "Check the endpoint, network and proxy. For Ollama, start the server on the machine running SmartX.", code="network_error")
    if isinstance(exc, (ValueError, KeyError, IndexError, TypeError)):
        return ProviderConnectionError("The endpoint returned an unexpected response.", "Use a compatible API endpoint, not a dashboard or login-page URL. Check the model's response format.", code="invalid_response")
    return ProviderConnectionError("Provider connection failed.", "Check the saved endpoint, model and credentials, then retry.")
