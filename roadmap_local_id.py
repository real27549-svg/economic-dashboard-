"""브라우저 로컬 사용자 ID (로그인 없음)."""

from __future__ import annotations

import json
import uuid

import streamlit as st
import streamlit.components.v1 as components

_SESSION_KEY = "roadmap_local_id"


def ensure_local_user_id() -> str:
    if st.session_state.get(_SESSION_KEY):
        return st.session_state[_SESSION_KEY]

    uid = st.query_params.get("uid")
    if isinstance(uid, list):
        uid = uid[0] if uid else None
    if uid:
        st.session_state[_SESSION_KEY] = uid
        _sync_local_storage(uid)
        return uid

    new_id = str(uuid.uuid4())
    st.session_state[_SESSION_KEY] = new_id
    st.query_params["uid"] = new_id
    _sync_local_storage(new_id)
    return new_id


def restore_local_user_id(pasted_id: str) -> str | None:
    cleaned = (pasted_id or "").strip()
    if not cleaned or len(cleaned) < 8:
        return None
    st.session_state[_SESSION_KEY] = cleaned
    st.query_params["uid"] = cleaned
    _sync_local_storage(cleaned)
    return cleaned


def _sync_local_storage(local_id: str) -> None:
    components.html(
        f"""
        <script>
        (function() {{
            try {{
                localStorage.setItem("roadmap_local_id", {json.dumps(local_id)});
            }} catch (e) {{}}
        }})();
        </script>
        """,
        height=0,
    )
