"""Flashcard display, FSRS evaluation, and learning step UI."""

import streamlit as st
import time
import datetime

from db.core import get_conn, ItemType
from fsrs import calcular_fsrs
from ui.state import proximo_item_fila, now_utc, hoje_str
from ui.tutor_panel import render_tutor_ai


def render_flashcard(item_atual, api_key, dificuldade, fila, idx):
    card = item_atual["item"]

    is_learning = item_atual.get("is_learning", False)
    unlock_time = item_atual.get("unlock_time", 0)
    target_interval = item_atual.get("target_interval", 1)

    if unlock_time > time.time():
        render_learning_lock(item_atual, fila, idx, unlock_time)
        return

    st.markdown("## 🃏 Flashcard")
    if is_learning:
        st.caption("🔄 Fase de Fixação (Learning Step)")

    st.info(card["front"])

    if not st.session_state["revelar_flashcard"]:
        if st.button("Mostrar Resposta", use_container_width=True):
            st.session_state["revelar_flashcard"] = True
            st.rerun()
        return

    st.success(card["back"])
    hoje_data = now_utc().date()
    try:
        last_rev_data = datetime.datetime.strptime(
            card["last_review"], "%Y-%m-%d"
        ).date()
        elapsed_days = (hoje_data - last_rev_data).days
    except Exception:
        elapsed_days = 0

    render_tutor_ai(card, api_key)

    st.markdown("---")

    if not is_learning:
        render_fsrs_evaluation(card, elapsed_days)
    else:
        render_learning_evaluation(card, elapsed_days, unlock_time, target_interval)


def render_learning_lock(item_atual, fila, idx, unlock_time):
    restante = int(unlock_time - time.time())
    minutos = restante // 60
    segundos = restante % 60

    is_last_unlocked = True
    for next_item in fila[idx + 1 :]:
        if next_item.get("unlock_time", 0) < time.time():
            is_last_unlocked = False
            break

    if is_last_unlocked:
        st.warning("⏳ Aguardando tempo de fixação...")
        st.info(
            f"O cérebro precisa de um intervalo. "
            f"Este card estará disponível em **{minutos}m {segundos}s**."
        )
        if st.button("🔄 Checar Tempo", use_container_width=True, type="primary"):
            st.rerun()
    else:
        st.warning("⏳ Este card está em tempo de fixação (Spaced Learning).")
        st.info(
            "Pule para o próximo item e este card retornará "
            "automaticamente na hora certa."
        )
        if st.button(
            "Pular para o próximo disponível ➡️", use_container_width=True
        ):
            st.session_state["fila_estudo"].append(item_atual)
            st.session_state["idx_atual"] += 1
            st.rerun()


def render_fsrs_evaluation(card, elapsed_days):
    st.write("Avalie sua resposta (FSRS):")
    g_info = {}
    for g in [1, 2, 3, 4]:
        g_info[g] = calcular_fsrs(
            g, card["difficulty"], card["stability"],
            max(0, elapsed_days), card["repetitions"], card["lapses"],
        )

    col1, col2, col3, col4 = st.columns(4)

    if col1.button("Again (<1m)", use_container_width=True):
        _save_fsrs_and_advance(card, 1, g_info)

    if col2.button("Hard (5m)", use_container_width=True):
        _save_fsrs_and_advance(card, 2, g_info)

    if col3.button(f"Good ({g_info[3][3]}d)", use_container_width=True):
        _save_fsrs_and_advance(card, 3, g_info)

    if col4.button(f"Easy ({g_info[4][3]}d)", use_container_width=True):
        _save_fsrs_and_advance(card, 4, g_info)


def _save_fsrs_and_advance(card, grade, g_info):
    d, s, r, interval, reps, lapses = g_info[grade]
    conn = get_conn()

    if grade <= 2:
        delay = 60 if grade == 1 else 300
        conn.execute(
            """INSERT INTO srs_state
               (object_id, object_type, repetitions, stability, difficulty,
                last_review, due, lapses)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(object_id, object_type) DO UPDATE SET
                repetitions=excluded.repetitions, stability=excluded.stability,
                difficulty=excluded.difficulty, last_review=excluded.last_review,
                due=excluded.due, lapses=excluded.lapses""",
            (card["id"], ItemType.FLASHCARD.value, reps, s, d,
             hoje_str(), hoje_str(), lapses),
        )
        conn.commit()
        st.session_state["fila_estudo"].append({
            "type": "flashcard", "item": card, "is_learning": True,
            "unlock_time": time.time() + delay, "target_interval": interval,
        })
        toast_msg = (
            "Enviado para fixação (1 min) 🔄"
            if grade == 1
            else "Enviado para fixação (5 min) 🔄"
        )
        st.toast(toast_msg)
    else:
        prox = (now_utc() + datetime.timedelta(days=interval)).strftime("%Y-%m-%d")
        conn.execute(
            """INSERT INTO srs_state
               (object_id, object_type, repetitions, stability, difficulty,
                last_review, due, lapses)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(object_id, object_type) DO UPDATE SET
                repetitions=excluded.repetitions, stability=excluded.stability,
                difficulty=excluded.difficulty, last_review=excluded.last_review,
                due=excluded.due, lapses=excluded.lapses""",
            (card["id"], ItemType.FLASHCARD.value, reps, s, d,
             hoje_str(), prox, lapses),
        )
        conn.commit()
        st.toast(f"Próxima revisão em: {interval} dia(s)")

    proximo_item_fila()


def render_learning_evaluation(card, elapsed_days, unlock_time, target_interval):
    st.write("Avalie sua resposta (Learning Step):")
    l_info = {}
    for g in [1, 2, 3, 4]:
        l_info[g] = calcular_fsrs(
            g, card["difficulty"], card["stability"],
            max(0, elapsed_days), card["repetitions"], card["lapses"],
        )

    col1, col2, col3, col4 = st.columns(4)

    if col1.button("Again (<1m)", use_container_width=True):
        d, s, r, interval, reps, lapses = l_info[1]
        conn = get_conn()
        conn.execute(
            """INSERT INTO srs_state
               (object_id, object_type, repetitions, stability, difficulty,
                last_review, due, lapses)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(object_id, object_type) DO UPDATE SET
                repetitions=excluded.repetitions, stability=excluded.stability,
                difficulty=excluded.difficulty, last_review=excluded.last_review,
                due=excluded.due, lapses=excluded.lapses""",
            (card["id"], ItemType.FLASHCARD.value, reps, s, d,
             hoje_str(), hoje_str(), lapses),
        )
        conn.commit()
        st.session_state["fila_estudo"].append({
            "type": "flashcard", "item": card, "is_learning": True,
            "unlock_time": time.time() + 60, "target_interval": interval,
        })
        st.toast("Voltou para fixação (1 min) 🔄")
        proximo_item_fila()

    if col2.button("Hard (5m)", use_container_width=True):
        d, s, r, interval, reps, lapses = l_info[2]
        conn = get_conn()
        conn.execute(
            """INSERT INTO srs_state
               (object_id, object_type, repetitions, stability, difficulty,
                last_review, due, lapses)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(object_id, object_type) DO UPDATE SET
                repetitions=excluded.repetitions, stability=excluded.stability,
                difficulty=excluded.difficulty, last_review=excluded.last_review,
                due=excluded.due, lapses=excluded.lapses""",
            (card["id"], ItemType.FLASHCARD.value, reps, s, d,
             hoje_str(), hoje_str(), lapses),
        )
        conn.commit()
        st.session_state["fila_estudo"].append({
            "type": "flashcard", "item": card, "is_learning": True,
            "unlock_time": time.time() + 300, "target_interval": interval,
        })
        st.toast("Enviado para fixação (5 min) 🔄")
        proximo_item_fila()

    if col3.button(f"Good ({l_info[3][3]}d)", use_container_width=True):
        d, s, r, interval, reps, lapses = l_info[3]
        prox = (now_utc() + datetime.timedelta(days=interval)).strftime("%Y-%m-%d")
        conn = get_conn()
        conn.execute(
            """INSERT INTO srs_state
               (object_id, object_type, repetitions, stability, difficulty,
                last_review, due, lapses)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(object_id, object_type) DO UPDATE SET
                repetitions=excluded.repetitions, stability=excluded.stability,
                difficulty=excluded.difficulty, last_review=excluded.last_review,
                due=excluded.due, lapses=excluded.lapses""",
            (card["id"], ItemType.FLASHCARD.value, reps, s, d,
             hoje_str(), prox, lapses),
        )
        conn.commit()
        st.toast(f"Próxima revisão em: {interval} dia(s)")
        proximo_item_fila()

    if col4.button(f"Easy ({l_info[4][3]}d)", use_container_width=True):
        d, s, r, interval, reps, lapses = l_info[4]
        prox = (now_utc() + datetime.timedelta(days=interval)).strftime("%Y-%m-%d")
        conn = get_conn()
        conn.execute(
            """INSERT INTO srs_state
               (object_id, object_type, repetitions, stability, difficulty,
                last_review, due, lapses)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(object_id, object_type) DO UPDATE SET
                repetitions=excluded.repetitions, stability=excluded.stability,
                difficulty=excluded.difficulty, last_review=excluded.last_review,
                due=excluded.due, lapses=excluded.lapses""",
            (card["id"], ItemType.FLASHCARD.value, reps, s, d,
             hoje_str(), prox, lapses),
        )
        conn.commit()
        st.toast(f"Próxima revisão em: {interval} dia(s)")
        proximo_item_fila()
