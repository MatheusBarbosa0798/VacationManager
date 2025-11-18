import streamlit as st
import pandas as pd
from datetime import date, timedelta
import datetime
import hashlib
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
from google.oauth2.service_account import Credentials

# =========================== CONFIGURAÇÕES ===========================
st.set_page_config(page_title="Férias da Equipe", layout="wide")
st.title("🌴 Controle de Férias da Equipe")

SHEET_ID = "SHEET_ID"

scope = [
    'https://spreadsheets.google.com/feeds',
    'https://www.googleapis.com/auth/drive'
]
creds_json = st.secrets["GSPREAD_CREDENTIALS"]
creds_dict = json.loads(creds_json)
st.write("📧 Service account email:", creds_dict["client_email"])

creds = Credentials.from_service_account_info(creds_dict, scopes=scope)

client = gspread.authorize(creds)
sheet = client.open_by_key(SHEET_ID).sheet1

# =========================== CARREGAR DADOS ===========================
try:
    data = sheet.get_all_records()
    df = pd.DataFrame(data)

    if not df.empty:
        df["Início"] = pd.to_datetime(df["Início"], errors='coerce')
        df["Fim"] = pd.to_datetime(df["Fim"], errors='coerce')
    else:
        df = pd.DataFrame(columns=["Membro", "Início", "Fim", "Cor"])

except Exception as e:
    st.error(f"Erro ao carregar dados: {e}")
    df = pd.DataFrame(columns=["Membro", "Início", "Fim", "Cor"])


# =========================== GERAR COR FIXA POR NOME ===========================
def get_cor(nome):
    h = int(hashlib.md5(nome.encode('utf-8')).hexdigest(), 16)
    cores = [
        "#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEEAD",
        "#D4A5A5", "#9B59B6", "#3498DB", "#E74C3C", "#2ECC71",
        "#F39C12", "#1ABC9C", "#8E44AD", "#E67E22"
    ]
    return cores[h % len(cores)]


# Garante a coluna de Cor
if len(df) > 0 and "Cor" not in df.columns:
    df["Cor"] = df["Membro"].apply(get_cor)


# =========================== SESSION STATE (pending save) ===========================
if "pending_save" not in st.session_state:
    st.session_state["pending_save"] = None  # dict with keys: membro, inicio, fim, cor


# =========================== ADICIONAR FÉRIAS ===========================
st.sidebar.header("➕ Adicionar Férias")

membro = st.sidebar.text_input("Nome do membro")
inicio = st.sidebar.date_input("Início", date.today())
fim = st.sidebar.date_input("Fim", date.today() + timedelta(days=14))

cor_default = df[df["Membro"] == membro]["Cor"].iloc[0] if (membro and membro in df["Membro"].values) else get_cor(membro or "default")
cor = st.sidebar.color_picker("Cor da pessoa", cor_default)

# Botão principal para iniciar tentativa de salvar
if st.sidebar.button("Salvar férias", key="btn_save_initiate"):
    if not membro.strip():
        st.sidebar.error("Digite o nome")
    elif inicio > fim:
        st.sidebar.error("Datas inválidas")
    else:
        # Converter inicio/fim para pd.Timestamp para comparações consistentes
        inicio_ts = pd.to_datetime(inicio)
        fim_ts = pd.to_datetime(fim)

        # Normaliza colunas do df caso estejam strings
        df["Início"] = pd.to_datetime(df["Início"], errors="coerce")
        df["Fim"] = pd.to_datetime(df["Fim"], errors="coerce")

        # Verificar sobreposição de datas (qualquer registro)
        conflito = df[((df["Início"] <= fim_ts) & (df["Fim"] >= inicio_ts))]

        if not conflito.empty:
            # Guardar a tentativa de salvar no session_state
            st.session_state["pending_save"] = {
                "membro": membro.strip(),
                "inicio": inicio_ts,
                "fim": fim_ts,
                "cor": cor
            }
        else:
            # Sem conflito -> salva imediatamente
            nova = pd.DataFrame([{"Membro": membro.strip(), "Início": inicio_ts, "Fim": fim_ts, "Cor": cor}])
            df = pd.concat([df, nova], ignore_index=True)

            # Converter datas para strings antes de enviar ao Sheets
            df["Início"] = pd.to_datetime(df["Início"], errors='coerce').dt.strftime("%Y-%m-%d")
            df["Fim"] = pd.to_datetime(df["Fim"], errors='coerce').dt.strftime("%Y-%m-%d")

            sheet.clear()
            sheet.update([df.columns.values.tolist()] + df.values.tolist())

            st.sidebar.success(f"Férias de {membro} cadastradas!")
            st.rerun()


# Se houver um pending_save, mostre aviso com confirmar/cancelar
if st.session_state["pending_save"] is not None:
    pending = st.session_state["pending_save"]
    st.warning("⚠ Atenção: já existe férias cadastradas que se sobrepõem a esse período.", icon="⚠️")

    # Mostrar quem entra em conflito (detalhe opcional)
    inicio_ts = pending["inicio"]
    fim_ts = pending["fim"]
    conflitos = df[((df["Início"] <= fim_ts) & (df["Fim"] >= inicio_ts))]
    if not conflitos.empty:
        st.markdown("**Registros em conflito:**")
        # mostra nomes e períodos
        conflitos_list = [
            f"- {r['Membro']} ({pd.to_datetime(r['Início']).strftime('%d/%m/%Y')} → {pd.to_datetime(r['Fim']).strftime('%d/%m/%Y')})"
            for _, r in conflitos.iterrows()
        ]
        st.markdown("\n".join(conflitos_list))

    st.info(f"Você tentou cadastrar: **{pending['membro']}** — {inicio_ts.strftime('%d/%m/%Y')} → {fim_ts.strftime('%d/%m/%Y')}")

    # Colocar botões Confirmar / Cancelar em linha
    col1, col2 = st.columns([1, 1])
    with col1:
        if st.button("Confirmar mesmo assim", key="confirm_overwrite"):
            # Realiza o salvamento
            nova = pd.DataFrame([{
                "Membro": pending["membro"],
                "Início": pending["inicio"],
                "Fim": pending["fim"],
                "Cor": pending["cor"]
            }])
            df = pd.concat([df, nova], ignore_index=True)

            # Converter datas para strings antes de enviar ao Sheets
            df["Início"] = pd.to_datetime(df["Início"], errors='coerce').dt.strftime("%Y-%m-%d")
            df["Fim"] = pd.to_datetime(df["Fim"], errors='coerce').dt.strftime("%Y-%m-%d")

            sheet.clear()
            sheet.update([df.columns.values.tolist()] + df.values.tolist())

            st.success(f"Férias de {pending['membro']} cadastradas (com sobreposição).")
            # limpa pending e rerun
            st.session_state["pending_save"] = None
            st.rerun()

    with col2:
        if st.button("Cancelar", key="cancel_overwrite"):
            st.session_state["pending_save"] = None
            st.info("Cadastro cancelado.")
            st.rerun()


# =========================== REMOVER FÉRIAS ===========================
st.sidebar.header("🗑️ Remover Férias")
if len(df) > 0:
    # garante tipos antes de formatar
    df["Início"] = pd.to_datetime(df["Início"], errors='coerce')
    df["Fim"] = pd.to_datetime(df["Fim"], errors='coerce')

    opcoes = df["Membro"] + " (" + df["Início"].dt.strftime("%d/%m/%Y") + " → " + df["Fim"].dt.strftime("%d/%m/%Y") + ")"
    remover = st.sidebar.selectbox("Selecione", opcoes)

    if st.sidebar.button("Excluir", key="btn_excluir"):
        df = df[opcoes != remover].reset_index(drop=True)
        # quando salvar, converter datas para string (YYYY-MM-DD)
        df["Início"] = pd.to_datetime(df["Início"], errors='coerce').dt.strftime("%Y-%m-%d")
        df["Fim"] = pd.to_datetime(df["Fim"], errors='coerce').dt.strftime("%Y-%m-%d")
        sheet.clear()
        sheet.update([df.columns.values.tolist()] + df.values.tolist())
        st.sidebar.success("Removido!")
        st.rerun()


# =========================== LEGENDA ===========================
st.sidebar.markdown("### 🎨 Legenda de cores")
if len(df) > 0:
    for m in sorted(df["Membro"].unique()):
        c = df[df["Membro"] == m]["Cor"].iloc[0]
        st.sidebar.markdown(f'<span style="color:{c}; font-size:28px;">●</span> {m}', unsafe_allow_html=True)


# =========================== CALENDÁRIO ===========================
ano = st.selectbox("Ano do calendário", list(range(date.today().year - 3, date.today().year + 6)), index=3)

cal_data = pd.date_range(date(ano, 1, 1), date(ano, 12, 31))
cal = pd.DataFrame({"Data": cal_data})
cal["Texto"] = ""

# garante que df tem tipos datetime para iterar
df["Início"] = pd.to_datetime(df["Início"], errors='coerce')
df["Fim"] = pd.to_datetime(df["Fim"], errors='coerce')

for _, row in df.iterrows():
    if pd.isna(row["Início"]) or pd.isna(row["Fim"]):
        continue
    mask = (cal["Data"] >= row["Início"]) & (cal["Data"] <= row["Fim"])
    nomes_coloridos = f'<span style="color:{row["Cor"]}">● {row["Membro"]}</span>'
    cal.loc[mask, "Texto"] = cal.loc[mask, "Texto"] + "<br>" + nomes_coloridos

st.header(f"📆 Calendário de Férias — {ano}")

for mes in range(1, 13):
    nome_mes = datetime.date(ano, mes, 1).strftime("%B %Y").title()
    st.subheader(nome_mes)

    mes_cal = cal[cal["Data"].dt.month == mes].copy()
    mes_cal["Dia"] = mes_cal["Data"].dt.day
    primeiro_wd = datetime.date(ano, mes, 1).weekday()

    cols = st.columns(7)
    for i, dia in enumerate(["Seg", "Ter", "Qua", "Qui", "Sex", "Sáb", "Dom"]):
        cols[i].markdown(f'<span style="color:#8b9bb4;">{dia}</span>', unsafe_allow_html=True)

    dia = 1
    for _ in range(6):
        cols = st.columns(7)
        for wd in range(7):
            if (_ == 0 and wd < primeiro_wd) or dia > len(mes_cal):
                cols[wd].write("")
            else:
                texto = mes_cal[mes_cal["Dia"] == dia]["Texto"].iloc[0] if dia <= len(mes_cal) else ""
                if texto:
                    cols[wd].markdown(
                        f'<div style="background:#ff6b6b33; border:1px solid #ff6b6b66; '
                        f'padding:14px; border-radius:14px; text-align:center; min-height:110px;">'
                        f'<strong style="font-size:19px; color:#ff6b6b;">{dia}</strong><br>'
                        f'<span style="font-size:14px;">{texto}</span></div>',
                        unsafe_allow_html=True)
                else:
                    cols[wd].markdown(
                        f'<div style="background:#0d1b2a; padding:14px; border-radius:14px; '
                        f'text-align:center; min-height:110px;">'
                        f'<strong style="font-size:19px; color:#1b98e0;">{dia}</strong></div>',
                        unsafe_allow_html=True)
                dia += 1
        if dia > len(mes_cal):
            break

    st.divider()

# =========================== LISTA COMPLETA ===========================
st.header("📋 Lista completa")
if len(df) > 0:
    df_view = df.sort_values("Início").copy()
    df_view["Período"] = df_view["Início"].dt.strftime("%d/%m/%Y") + " → " + df_view["Fim"].dt.strftime("%d/%m/%Y")
    st.dataframe(df_view[["Membro", "Período"]], use_container_width=True)
else:
    st.info("Nenhuma férias cadastrada ainda.")
