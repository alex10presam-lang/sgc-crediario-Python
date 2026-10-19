"""Streamlit presentation. Every data operation goes through Services."""

from datetime import date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pandas as pd
import streamlit as st

from sgc.database import Database
from sgc.money import add_months, brl
from sgc.reports import payment_pdf
from sgc.security import DomainError, authenticate
from sgc.services import Services


@st.cache_resource
def database():
    return Database()


def operation_key(kind):
    return st.session_state.setdefault("request_" + kind, uuid4().hex)


def complete(kind, message):
    st.session_state["request_" + kind] = uuid4().hex
    st.session_state["notice"] = message
    st.rerun()


def login(db):
    left, right = st.columns([1.25, 1], gap="large")
    with left:
        st.html(
            '<p class="eyebrow">SGC / CREDIÁRIO</p><h1 class="hero">Cada parcela.<br>Uma história<br>bem registrada.</h1><p class="intro">Vendas, estoque e recebimentos no mesmo lugar. Um projeto de gestão local, com atenção aos detalhes que fecham a conta.</p><div class="ledger-note">01 — ORGANIZAR &nbsp; 02 — VENDER &nbsp; 03 — ACOMPANHAR</div>'
        )
    with right:
        st.subheader("Entre no espaço de trabalho")
        st.caption("Demonstração local · use apenas dados fictícios.")
        with st.form("login"):
            company = st.text_input("Empresa", value="aurora", max_chars=50)
            username = st.text_input("Usuário", value="admin", max_chars=40)
            password = st.text_input("Senha", type="password", max_chars=256)
            submitted = st.form_submit_button("Entrar", type="primary", width="stretch")
        if submitted:
            try:
                actor = authenticate(db, company, username, password)
                st.session_state.clear()
                st.session_state["actor"] = actor
                st.session_state["last_activity"] = datetime.now()
                st.rerun()
            except DomainError as error:
                st.error(str(error))
        st.caption(
            "Primeiro acesso? Prepare os exemplos com `python -m sgc.demo`. As credenciais de demonstração estão no README."
        )


def installment_table(rows):
    return pd.DataFrame(
        [
            {
                "Venda": r["sale_id"],
                "Parcela": r["number"] or "Entrada",
                "Cliente": r["customer"],
                "Vencimento": r["due_date"].strftime("%d/%m/%Y"),
                "Valor": brl(r["amount"]),
                "Recebido": brl(r["paid"]),
                "Saldo": brl(r["balance"]),
                "Situação": r["status"],
            }
            for r in rows
        ]
    )


def overview(service):
    st.html(
        '<p class="eyebrow">VISÃO GERAL / 01</p><h1>Contas claras.<br>Próximos passos à vista.</h1>'
    )
    st.caption(
        "Valores da empresa conectada, calculados a partir das parcelas e recebimentos registrados."
    )
    summary = service.summary()
    for column, label, key in zip(
        st.columns(4),
        ["Total contratado", "Recebido", "A receber", "Em atraso"],
        ["total", "paid", "balance", "overdue"],
    ):
        column.metric(label, brl(summary[key]))
    st.divider()
    left, right = st.columns([1.5, 1])
    rows = service.installments()
    with left:
        st.subheader("Agenda de recebimentos")
        if rows:
            monthly = {}
            for row in rows:
                if row["balance"]:
                    month = row["due_date"].strftime("%Y-%m")
                    monthly[month] = monthly.get(month, 0) + row["balance"] / 100
            if monthly:
                chart = pd.DataFrame(
                    {
                        "Mês": sorted(monthly),
                        "Saldo (R$)": [monthly[m] for m in sorted(monthly)],
                    }
                ).set_index("Mês")
                st.bar_chart(chart, color="#246451", height=280)
            else:
                st.success("Todos os valores registrados foram recebidos.")
        else:
            st.info("Cadastre o primeiro cliente e registre uma venda para começar.")
    with right:
        st.subheader("O que merece atenção")
        overdue = [r for r in rows if r["balance"] and r["due_date"] < date.today()]
        st.metric("Parcelas vencidas", len(overdue))
        st.caption(
            "O saldo é mantido em aberto em pagamentos parciais. Acréscimos só entram no valor quando informados na venda."
        )
        st.html(
            '<div class="ledger-note">LEITURA DO PAINEL<br>Vendas canceladas são excluídas dos indicadores. Entradas e pagamentos à vista estão incluídos no recebido.</div>'
        )
    st.subheader("Carteira da empresa")
    if rows:
        st.dataframe(installment_table(rows), hide_index=True, width="stretch")


def customers_page(service, role):
    st.title("Clientes")
    st.caption("Cadastros disponíveis para os atendimentos desta empresa.")
    if role in {"admin", "vendedor"}:
        with st.expander("Cadastrar cliente"):
            with st.form("customer", clear_on_submit=True):
                name = st.text_input("Nome", max_chars=160)
                phone = st.text_input("Telefone (opcional)", max_chars=40)
                if st.form_submit_button("Salvar cliente", type="primary"):
                    service.add_customer(name, phone)
                    complete("customer", "Cliente cadastrado.")
    rows = service.customers()
    st.dataframe(
        pd.DataFrame(rows).rename(columns={"id": "Código", "name": "Cliente", "phone": "Telefone"}),
        hide_index=True,
        width="stretch",
    )


def stock_page(service, role):
    st.title("Estoque")
    st.caption(
        "O estoque é descontado na confirmação da venda e devolvido no cancelamento permitido."
    )
    rows = service.products()
    if role == "admin":
        with st.expander("Cadastrar produto"):
            with st.form("product", clear_on_submit=True):
                name = st.text_input("Produto", max_chars=160)
                price = st.number_input(
                    "Preço de venda (R$)",
                    min_value=0.01,
                    max_value=1_000_000.0,
                    step=1.0,
                )
                quantity = st.number_input(
                    "Estoque inicial", min_value=0, max_value=1_000_000, step=1
                )
                if st.form_submit_button("Salvar produto", type="primary"):
                    service.add_product(name, price, int(quantity))
                    complete("product", "Produto cadastrado.")
        if rows:
            with st.expander("Registrar entrada de estoque"):
                with st.form("restock"):
                    selected = st.selectbox(
                        "Produto para reposição", rows, format_func=lambda r: r["name"]
                    )
                    quantity = st.number_input(
                        "Quantidade recebida", min_value=1, max_value=1_000_000, step=1
                    )
                    if st.form_submit_button("Registrar entrada"):
                        service.restock(selected["id"], int(quantity))
                        complete("stock", "Entrada de estoque registrada.")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Código": r["id"],
                    "Produto": r["name"],
                    "Preço": brl(r["price"]),
                    "Disponível": r["stock"],
                }
                for r in rows
            ]
        ),
        hide_index=True,
        width="stretch",
    )


def sale_page(service):
    st.title("Nova venda")
    st.caption("Escolha o cliente, confira os valores e confirme as condições de pagamento.")
    customers = service.customers()
    if not customers:
        st.info("Cadastre um cliente antes de registrar uma venda.")
        return
    mode = st.radio("Modalidade", ["Venda avulsa", "Produtos do estoque"], horizontal=True)
    products = service.products() if mode == "Produtos do estoque" else []
    items = []
    total = 0
    if mode == "Produtos do estoque":
        selected = st.multiselect(
            "Itens da venda",
            products,
            format_func=lambda r: f"{r['name']} · {brl(r['price'])} · {r['stock']} disponíveis",
        )
        for product in selected:
            quantity = st.number_input(
                "Quantidade · " + product["name"],
                min_value=1,
                max_value=1000,
                step=1,
                key=f"qty_{product['id']}",
            )
            items.append((product["id"], int(quantity)))
            total += product["price"] * quantity
        st.metric("Subtotal dos produtos", brl(total))
    with st.form("sale"):
        customer = st.selectbox(
            "Cliente da venda",
            customers,
            format_func=lambda r: f"{r['name']} · #{r['id']}",
        )
        description = st.text_input("Descrição da venda", max_chars=160)
        amount = (
            st.number_input(
                "Preço à vista (R$)",
                min_value=0.01,
                max_value=1_000_000.0,
                value=100.0,
                step=10.0,
            )
            if mode == "Venda avulsa"
            else total / 100
        )
        cash = st.checkbox("Pagamento integral à vista")
        entry = st.number_input("Entrada (R$)", min_value=0.0, max_value=1_000_000.0, step=10.0)
        count = st.number_input("Número de parcelas", min_value=1, max_value=48, value=3, step=1)
        first_due = st.date_input(
            "Primeiro vencimento",
            value=add_months(date.today(), 1),
            min_value=date.today(),
            max_value=date(2100, 12, 31),
        )
        interest = st.number_input(
            "Acréscimo único sobre o saldo financiado (%)",
            min_value=0.0,
            max_value=100.0,
            step=0.5,
        )
        st.caption(
            "À vista: entrada igual ao total, sem acréscimo. No crediário, o acréscimo informado incide uma única vez sobre o saldo após a entrada. Os centavos são distribuídos entre as parcelas."
        )
        submitted = st.form_submit_button("Confirmar venda", type="primary")
    if submitted:
        if mode == "Produtos do estoque" and not items:
            raise DomainError("Selecione pelo menos um produto.")
        identifier = service.create_sale(
            customer["id"],
            description,
            amount=amount,
            items=items,
            entry=amount if cash else entry,
            count=int(count),
            first_due=first_due,
            interest_percent=0 if cash else interest,
            request_key=operation_key("sale"),
        )
        complete("sale", f"Venda #{identifier} registrada. Consulte as parcelas no painel.")


def collections_page(service, role):
    st.title("Cobrança e recebimentos")
    st.caption(
        "Receba valores parciais, antecipe parcelas ou ajuste um vencimento mantendo o registro da operação."
    )
    rows = service.installments()
    open_rows = [r for r in rows if r["balance"]]
    if rows:
        st.dataframe(installment_table(rows), hide_index=True, width="stretch")
    if open_rows:

        def labels(row):
            return f"Venda #{row['sale_id']} / parcela {row['number']} · {row['customer']} · saldo {brl(row['balance'])}"

        pay, reschedule = st.tabs(["Receber pagamento", "Alterar vencimento"])
        with pay:
            with st.form("payment"):
                selected = st.selectbox("Parcela para receber", open_rows, format_func=labels)
                amount = st.number_input(
                    "Valor recebido (R$)",
                    min_value=0.01,
                    max_value=1_000_000.0,
                    step=10.0,
                )
                st.caption(
                    "O excedente será destinado às próximas parcelas da mesma venda. Valores acima desse saldo são recusados integralmente."
                )
                if st.form_submit_button("Registrar recebimento", type="primary"):
                    identifier = service.receive(selected["id"], amount, operation_key("payment"))
                    complete(
                        "payment",
                        f"Recebimento #{identifier} registrado. O comprovante está disponível abaixo.",
                    )
        with reschedule:
            with st.form("reschedule"):
                selected = st.selectbox("Parcela para alterar", open_rows, format_func=labels)
                due_date = st.date_input(
                    "Novo vencimento",
                    min_value=date.today(),
                    max_value=date(2100, 12, 31),
                )
                if st.form_submit_button("Salvar vencimento"):
                    service.reschedule(selected["id"], due_date)
                    complete("reschedule", "Vencimento atualizado.")
    else:
        st.info("Não há parcelas em aberto nesta empresa.")
    st.subheader("Comprovantes e estornos")
    payments = service.payments()
    if payments:
        selected = st.selectbox(
            "Recebimento",
            payments,
            format_func=lambda p: (
                f"#{p['id']} · venda #{p['sale_id']} · {brl(p['amount'])}"
                + (" · estornado" if p["reversed"] else "")
            ),
        )
        st.download_button(
            "Baixar comprovante em PDF",
            payment_pdf(service.payment_details(selected["id"])),
            file_name=f"recebimento-{selected['id']}.pdf",
            mime="application/pdf",
        )
        if not selected["is_entry"] and not selected["reversed"]:
            st.caption(
                "Estorno disponível por cinco minutos para o recebimento mais recente da venda. O cobrador só pode desfazer seus próprios recebimentos."
            )
            confirmed = st.checkbox("Confirmo o estorno deste recebimento")
            if st.button("Desfazer recebimento", disabled=not confirmed):
                service.reverse_payment(selected["id"])
                complete("reverse", "Recebimento estornado; saldo restaurado.")
    if role == "admin":
        with st.expander("Cancelar venda sem recebimentos"):
            with st.form("cancel"):
                identifier = st.number_input("Número da venda", min_value=1, step=1)
                confirmed = st.checkbox(
                    "Confirmo o cancelamento e a devolução dos itens ao estoque"
                )
                if st.form_submit_button("Cancelar venda"):
                    if not confirmed:
                        raise DomainError("Confirme o cancelamento antes de continuar.")
                    service.cancel_sale(int(identifier))
                    complete("cancel", "Venda cancelada e estoque devolvido.")


def account_page(service, role):
    st.title("Conta e administração")
    with st.expander("Alterar minha senha"):
        with st.form("password", clear_on_submit=True):
            current = st.text_input("Senha atual", type="password", max_chars=256)
            new = st.text_input("Nova senha", type="password", max_chars=256)
            confirmation = st.text_input("Repita a nova senha", type="password", max_chars=256)
            if st.form_submit_button("Alterar senha"):
                if new != confirmation:
                    raise DomainError("As senhas não conferem.")
                service.change_password(current, new)
                st.session_state.clear()
                st.session_state["notice"] = "Senha alterada. Entre novamente."
                st.rerun()
    if role != "admin":
        return
    team, audit = st.tabs(["Equipe", "Auditoria"])
    with team:
        users = service.users()
        st.dataframe(
            pd.DataFrame(users).rename(
                columns={
                    "name": "Nome",
                    "username": "Usuário",
                    "role": "Perfil",
                    "active": "Ativo",
                }
            ),
            hide_index=True,
            width="stretch",
        )
        with st.expander("Cadastrar pessoa na equipe"):
            with st.form("new_user", clear_on_submit=True):
                name = st.text_input("Nome da pessoa", max_chars=160)
                username = st.text_input("Nome de usuário", max_chars=40)
                password = st.text_input(
                    "Senha inicial (mínimo 12 caracteres)",
                    type="password",
                    max_chars=256,
                )
                user_role = st.selectbox("Perfil", ["vendedor", "cobrador", "admin"])
                if st.form_submit_button("Cadastrar usuário"):
                    service.add_user(name, username, password, user_role)
                    complete("user", "Pessoa adicionada à equipe.")
        with st.expander("Desativar uma conta"):
            active = [u for u in users if u["active"] and u["id"] != service.actor.user_id]
            if active:
                selected = st.selectbox(
                    "Conta a desativar", active, format_func=lambda u: u["username"]
                )
                confirmed = st.checkbox("Confirmo a desativação da conta")
                if st.button("Desativar conta", disabled=not confirmed):
                    service.deactivate_user(selected["id"])
                    complete("user", "Conta desativada.")
    with audit:
        st.caption(
            "Últimos 200 eventos da empresa conectada. Senhas não são incluídas nos registros."
        )
        st.dataframe(pd.DataFrame(service.audit()), hide_index=True, width="stretch")
        st.info(
            "Backup completo é uma ferramenta do operador da máquina: python -m sgc.backup. Ele inclui todas as empresas locais e não é disponibilizado por usuário na interface."
        )


def main():
    st.set_page_config(page_title="SGC · Crediário", page_icon="◈", layout="wide")
    style = (Path(__file__).parent / "assets" / "app.css").read_text(encoding="utf-8")
    st.html("<style>" + style + "</style>")
    db = database()
    if "notice" in st.session_state:
        st.success(st.session_state.pop("notice"))
    actor = st.session_state.get("actor")
    if not actor:
        login(db)
        return
    if datetime.now() - st.session_state.get("last_activity", datetime.min) > timedelta(minutes=30):
        st.session_state.clear()
        st.session_state["notice"] = "Sessão encerrada após 30 minutos sem atividade."
        st.rerun()
    service = Services(db, actor)
    try:
        identity = service.identity()
    except DomainError:
        st.session_state.clear()
        st.rerun()
    st.session_state["last_activity"] = datetime.now()
    role = identity["role"]
    with st.sidebar:
        st.html('<div class="wordmark">sgc<span>CONTROLE DE CREDIÁRIO</span></div>')
        st.text(identity["company"].upper())
        st.caption(identity["name"] + " · " + role)
        menus = ["Visão geral", "Clientes"]
        if role in {"admin", "vendedor"}:
            menus += ["Nova venda", "Estoque"]
        if role in {"admin", "cobrador"}:
            menus += ["Cobrança"]
        menus += ["Minha conta"]
        choice = st.radio("Espaço de trabalho", menus, label_visibility="collapsed")
        st.divider()
        st.caption(
            "PORTFÓLIO / DEMONSTRAÇÃO LOCAL\nDados fictícios. Sem conexão bancária ou sincronização em nuvem."
        )
        if st.button("Encerrar sessão", width="stretch"):
            st.session_state.clear()
            st.rerun()
    try:
        if choice == "Visão geral":
            overview(service)
        elif choice == "Clientes":
            customers_page(service, role)
        elif choice == "Estoque":
            stock_page(service, role)
        elif choice == "Nova venda":
            sale_page(service)
        elif choice == "Cobrança":
            collections_page(service, role)
        elif choice == "Minha conta":
            account_page(service, role)
    except DomainError as error:
        st.error(str(error))
