"""Compatibility launcher: the retired Streamlit entry point opens the web UI."""
from http.server import ThreadingHTTPServer
import threading
from urllib.request import urlopen
import streamlit as st
import streamlit.components.v1 as components
from FRONTED.ui.web_app import Platform, make_handler


def main():
    st.set_page_config(page_title='SX Aerospace', page_icon='✈', layout='wide', initial_sidebar_state='collapsed')
    @st.cache_resource
    def web_server():
        port = 8502
        try:
            with urlopen(f'http://127.0.0.1:{port}/app.css', timeout=1) as response:
                if response.status == 200:
                    return None
        except OSError:
            pass
        server = ThreadingHTTPServer(('127.0.0.1', port), make_handler(Platform()))
        threading.Thread(target=server.serve_forever, daemon=True).start()
        return server
    web_server()
    st.markdown('<style>header[data-testid="stHeader"],footer,[data-testid="stToolbar"],.stAppDeployButton{display:none!important}.block-container{padding:0!important;max-width:none!important}iframe{border:0!important;width:100%!important;height:100dvh!important}.stMainBlockContainer{padding:0!important}.stMain{overflow:hidden!important}</style>', unsafe_allow_html=True)
    if hasattr(st, 'iframe'):
        st.iframe('http://127.0.0.1:8502', height=1100)
    else:
        components.iframe('http://127.0.0.1:8502', height=1100, scrolling=True)
