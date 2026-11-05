"""Chatbot global : un bouton en bas à gauche ouvre un panneau sur le quart gauche de la page."""
from html import escape

import streamlit as st

from plm import assistant
from plm import local_llm
from plm.chat_queries import SUGGESTIONS
from ui import theme
from ui.state import MAIN_EXPLORER, open_part

def no_math(text):
    """Streamlit lirait les $ comme une formule mathématique."""
    return text.replace("$", "\\$")


@st.cache_data(ttl=10, show_spinner=False)
def local_status():
    return local_llm.status()


def screen_context(model):
    selected = model.nodes.get(st.session_state.get("selected_id"))
    tab = st.session_state.get("main_tab", MAIN_EXPLORER)
    opened = f"fiche ouverte : {selected.label} ({selected.product['plm_id']})" if selected else "aucune fiche ouverte"
    return f"Écran de l'utilisateur : onglet « {tab} », {opened}."


def render_sources(model, message, index):
    sources = message.get("sources", [])
    if not sources:
        return
    with st.expander(f"Sources PLM ({len(sources)})"):
        for position, source in enumerate(sources):
            plm = f" · <code>{escape(source['plm_id'])}</code>" if source.get("plm_id") else ""
            theme.html(f'<div class="plm-source"><b>{escape(source["label"])}</b>{plm} · <code>{escape(source["id"])}</code><br>{escape(source.get("fields", ""))}</div>')
            if source["type"] == "Pièce" and position < 8:
                node = model.nodes.get(source["id"]) or model.nodes_by_part.get(source["id"], [None])[0]
                if node and st.button("Ouvrir la fiche", key=f"src_{index}_{source['id']}", type="tertiary"):
                    open_part(node.id)
                    st.rerun()  # toute la page : la fiche s'ouvre dans l'onglet Product Explorer
        st.caption("Liste issue des outils réellement appelés pour cette réponse.")


def set_pending(question):
    st.session_state.pending_question = question


def clear_chat():
    st.session_state.chat_messages = []


def set_open(value):
    st.session_state.chat_open = value


def render_panel(model):
    messages = st.session_state.setdefault("chat_messages", [])
    with st.container(key="chat_panel"):
        title, close = st.columns([5, 1], vertical_alignment="center")
        with title:
            theme.html('<div style="font-size:1.05rem;font-weight:700">Assistant PLM</div>')
        close.button("", icon=":material/close:", key="chat_close", type="tertiary", on_click=set_open, args=(False,), help="Fermer l'assistant")
        use_ollama = st.toggle("Utiliser Ollama", key="chat_use_ollama", persist_state="session",
                               help="Désactivé : assistant intégré historique, sans installation. Activé : modèle local Ollama, avec secours automatique.")
        if not use_ollama:
            st.caption("Assistant intégré · réponses guidées et calculs PLM, sans installation ni serveur.")
        elif local_status():
            st.caption(f"IA locale · {local_llm.MODEL} · historique et outils de calcul PLM.")
        else:
            st.caption("Ollama indisponible · l’assistant intégré reste opérationnel.")

        history = st.container(height=500, border=False, key="chat_history", autoscroll=True)
        with history:
            if not messages:
                st.markdown("Interrogez le produit en langage naturel. Chaque réponse cite les sources PLM utilisées.")
                for number, suggestion in enumerate(SUGGESTIONS):
                    st.button(suggestion, key=f"suggest_{number}", on_click=set_pending, args=(suggestion,), width="stretch")
            for index, message in enumerate(messages):
                with st.chat_message(message["role"]):
                    st.markdown(no_math(message["content"]))
                    if message["role"] == "assistant":
                        render_sources(model, message, index)

        question = st.chat_input("Posez votre question…", key="chat_input") or st.session_state.pop("pending_question", None)
        if messages:
            st.button("Effacer la conversation", key="chat_clear", on_click=clear_chat, type="tertiary")

    if question:
        conversation = [{"role": m["role"], "content": m["content"]} for m in messages]
        messages.append({"role": "user", "content": question})
        with history:
            with st.chat_message("user"):
                st.markdown(no_math(question))
            with st.chat_message("assistant"):
                with st.status("Interrogation des données PLM…") as status:
                    answer = assistant.ask(model, question, conversation, screen_context(model), backend="ollama" if use_ollama else "integrated", on_tool=lambda label: status.update(label=f"{label}…"))
        messages.append({"role": "assistant", "content": answer["text"], "sources": answer["sources"], "mode": answer["mode"]})
        st.rerun(scope="fragment")


@st.fragment
def render(model):
    """Fragment : ouvrir le panneau ou poser une question ne recalcule pas le reste de la page."""
    if st.session_state.get("chat_open"):
        render_panel(model)
    else:
        with st.container(key="chat_toggle"):
            st.button("Assistant PLM", icon=":material/chat:", key="chat_open_button", on_click=set_open, args=(True,))
