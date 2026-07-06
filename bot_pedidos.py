import tkinter as tk
from tkinter import ttk, messagebox
from playwright.sync_api import sync_playwright
import threading
import time
import math
import os
from decimal import Decimal, ROUND_HALF_UP, ROUND_DOWN

# =========================
# CONFIG
# =========================
USUARIO = "Pedro"
SENHA   = "Unis7171"
URL     = "https://discomercio.com.br/sistemav2/central"
URL_SIMULADOR = "https://simulador-margens.vercel.app/"
USUARIO_SIM = "sac@unisarcondicionado.com.br"
SENHA_SIM   = "sac@unisarcondicionado.com.br"

CAMPOS_POR_LINHA = 7
IDX_QTDE        = 0
IDX_PRECO_LISTA = 3
IDX_VL_UNIT     = 5

# =========================
# HELPERS DE MOEDA
# =========================
def parse_brl(valor_str: str) -> Decimal:
    return Decimal(valor_str.strip().replace(".", "").replace(",", "."))

def fmt_brl(valor: Decimal) -> str:
    s = f"{valor:,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".")

# =========================
# DISTRIBUIÇÃO POR DESCONTO LINEAR
# =========================
def distribuir_por_desconto(qtds, precos_lista, total_desejado):
    total_desejado = Decimal(str(total_desejado))
    qtds = [int(q) for q in qtds]
    precos_lista = [Decimal(str(p)) for p in precos_lista]
    n = len(qtds)

    total_lista = sum(q * p for q, p in zip(qtds, precos_lista))
    if total_lista == 0:
        return precos_lista.copy()

    fator = total_desejado / total_lista
    base = [(p * fator).quantize(Decimal("0.01"), rounding=ROUND_DOWN) for p in precos_lista]
    soma_base = sum(qtds[i] * base[i] for i in range(n))
    diff_cents = int(((total_desejado - soma_base) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

    ajustes = [0] * n
    restante = diff_cents
    ordem = sorted(range(n), key=lambda i: qtds[i])

    for idx in ordem:
        if restante <= 0:
            break
        vezes = restante // qtds[idx]
        ajustes[idx] = vezes
        restante -= vezes * qtds[idx]

    if restante > 0:
        ajustes[ordem[0]] += 1

    novos = [base[i] + Decimal(ajustes[i]) * Decimal("0.01") for i in range(n)]
    return novos

# =========================
# HELPERS DE VALIDAÇÃO DO SIMULADOR
# =========================
def calcular_qtd_parcelas(pagamento):
    opcao = pagamento.get("opcao")
    try:
        if opcao == "1":
            return 0
        elif opcao == "2":
            return 1
        elif opcao in ("3", "4"):
            return int(pagamento.get("pc_qtde", 0))
        elif opcao == "5":
            return 1 + int(pagamento.get("prest_qtde", 0))
        elif opcao == "6":
            return 1 + int(pagamento.get("demais_qtde", 0))
    except (ValueError, TypeError):
        return None
    return None


def extrair_min_parcelas(texto):
    import re
    if not texto:
        return None
    numeros = re.findall(r'(\d+)\s*x', texto)
    if not numeros:
        if "vista" in texto.lower() or "à vista" in texto.lower():
            return 0
        return None
    return int(numeros[0])


# =========================
# AUTOMAÇÃO
# =========================
def rodar_automacao(pedido, vendedor, valor_desejado, pagamento, log_fn, email_sim=None, num_margem_input=None):
    email_sim = email_sim or USUARIO_SIM
    try:
        with sync_playwright() as p:
            context = p.chromium.launch_persistent_context(
                user_data_dir="session", headless=False, slow_mo=80)
            page = context.new_page()

            BLOCKER = """
(function() {
    window.userIntervened = false;
    window.botAllowKeyboard = false;
    window.botPerformingAction = false;

    function injectOverlay() {
        if (document.getElementById('bot-blocker-overlay')) return;
        const overlay = document.createElement('div');
        overlay.id = 'bot-blocker-overlay';
        overlay.style.cssText = 'position:fixed;top:0;left:0;width:100vw;height:100vh;z-index:2147483647;background:transparent;cursor:not-allowed;pointer-events:auto;';
        ['mousedown','pointerdown','touchstart','click','dblclick','contextmenu'].forEach(evt => {
            overlay.addEventListener(evt, (e) => {
                window.userIntervened = true;
                e.preventDefault();
                e.stopPropagation();
            }, true);
        });
        document.documentElement.appendChild(overlay);
    }

    injectOverlay();
    window.addEventListener('DOMContentLoaded', injectOverlay);
    window.addEventListener('load', injectOverlay);
    new MutationObserver(injectOverlay).observe(document.documentElement, {childList:true, subtree:true});

    window.addEventListener('keydown', (e) => {
        if (!window.botAllowKeyboard) {
            window.userIntervened = true;
            e.preventDefault();
            e.stopPropagation();
        }
    }, true);
})();
"""
            page.add_init_script(BLOCKER)

            def check_intervention():
                try:
                    if page.evaluate("window.userIntervened"):
                        raise Exception("Intervenção do usuário detectada")
                except Exception as e:
                    if "Intervenção do usuário detectada" in str(e):
                        raise e

            def wait_for_ajax(has_delay=False):
                if has_delay:
                    time.sleep(0.15)
                try:
                    page.locator("#divAjaxRunning").wait_for(state="hidden", timeout=15000)
                except Exception:
                    pass

            def run_step(action_fn, trigger_ajax=True):
                wait_for_ajax(has_delay=False)
                check_intervention()
                try:
                    page.evaluate("""() => {
                        const o = document.getElementById('bot-blocker-overlay');
                        if (o) o.style.pointerEvents = 'none';
                        window.botAllowKeyboard = true;
                        window.botPerformingAction = true;
                    }""")
                except Exception:
                    pass
                action_fn()
                try:
                    time.sleep(0.05)
                    page.evaluate("""() => {
                        const o = document.getElementById('bot-blocker-overlay');
                        if (o) o.style.pointerEvents = 'auto';
                        window.botAllowKeyboard = false;
                        window.botPerformingAction = false;
                    }""")
                except Exception:
                    pass
                check_intervention()
                if trigger_ajax:
                    wait_for_ajax(has_delay=True)

            def preenche_tabela_local(name, nth, valor_fmt):
                def act():
                    el = page.locator(f'[name="{name}"]').nth(nth)
                    el.click(); el.select_text(); el.fill(valor_fmt)
                    el.dispatch_event("change")
                    el.dispatch_event("input")
                    el.dispatch_event("blur")
                run_step(act, trigger_ajax=True)

            def preenche_el_local(selector, valor):
                def act():
                    el = page.locator(selector)
                    el.click(); el.select_text(); el.fill(str(valor))
                    el.dispatch_event("change")
                    el.dispatch_event("input")
                    el.dispatch_event("blur")
                run_step(act, trigger_ajax=True)

            def radio_local(value):
                def act():
                    page.evaluate(f"""
                        const rb = document.querySelector('input[name="rb_forma_pagto"][value="{value}"]');
                        if (rb) {{ rb.removeAttribute('disabled'); rb.click(); }}
                    """)
                run_step(act, trigger_ajax=True)

            def preenche_pagamento_local(dados):
                opcao = dados["opcao"]
                run_step(lambda: page.evaluate("window.scrollTo(0, document.body.scrollHeight)"))
                time.sleep(0.5)
                if opcao == "1":
                    radio_local("1")
                    run_step(lambda: page.locator("#op_av_forma_pagto").select_option(dados["forma"]))
                    run_step(lambda: page.locator("#op_av_forma_pagto").dispatch_event("change"))
                    wait_for_ajax()
                elif opcao == "2":
                    radio_local("5")
                    run_step(lambda: page.locator("#op_pu_forma_pagto").select_option(dados["forma"]))
                    run_step(lambda: page.locator("#op_pu_forma_pagto").dispatch_event("change"))
                    wait_for_ajax()
                    preenche_el_local("#c_pu_vencto_apos", dados["pu_vencto"])
                elif opcao == "3":
                    radio_local("2")
                    preenche_el_local("#c_pc_qtde", dados["pc_qtde"])
                elif opcao == "4":
                    radio_local("6")
                    preenche_el_local("#c_pc_maquineta_qtde", dados["pc_qtde"])
                elif opcao == "5":
                    radio_local("3")
                    run_step(lambda: page.locator("#op_pce_entrada_forma_pagto").select_option(dados["entrada_forma"]))
                    run_step(lambda: page.locator("#op_pce_entrada_forma_pagto").dispatch_event("change"))
                    wait_for_ajax()
                    preenche_el_local("#c_pce_entrada_valor", dados["entrada_valor"])
                    run_step(lambda: page.locator("#op_pce_prestacao_forma_pagto").select_option(dados["prest_forma"]))
                    run_step(lambda: page.locator("#op_pce_prestacao_forma_pagto").dispatch_event("change"))
                    wait_for_ajax()
                    preenche_el_local("#c_pce_prestacao_qtde", dados["prest_qtde"])
                    preenche_el_local("#c_pce_prestacao_periodo", dados["prest_dias"])
                elif opcao == "6":
                    radio_local("4")
                    run_step(lambda: page.locator("#op_pse_prim_prest_forma_pagto").select_option(dados["prim_forma"]))
                    run_step(lambda: page.locator("#op_pse_prim_prest_forma_pagto").dispatch_event("change"))
                    wait_for_ajax()
                    preenche_el_local("#c_pse_prim_prest_valor", dados["prim_valor"])
                    preenche_el_local("#c_pse_prim_prest_apos",  dados["prim_apos"])
                    run_step(lambda: page.locator("#op_pse_demais_prest_forma_pagto").select_option(dados["demais_forma"]))
                    run_step(lambda: page.locator("#op_pse_demais_prest_forma_pagto").dispatch_event("change"))
                    wait_for_ajax()
                    preenche_el_local("#c_pse_demais_prest_qtde",  dados["demais_qtde"])
                    preenche_el_local("#c_pse_demais_prest_periodo", dados["demais_dias"])
                time.sleep(0.5)

            # ── Execução ──────────────────────────────────────────────────
            log_fn("🌐 Abrindo sistema...")
            run_step(lambda: page.goto(URL))
            wait_for_ajax()

            log_fn("🔐 Fazendo login...")
            run_step(lambda: page.fill("input[name='usuario']", USUARIO))
            run_step(lambda: page.fill("input[name='senha']",   SENHA))
            with context.expect_page() as nova:
                run_step(lambda: page.click("input[name='bCONSULTAR']"))
            page = nova.value
            page.add_init_script(BLOCKER)

            # Registrar handler para caixas de diálogo (alert, confirm, etc.)
            rt_alert_detected = [False]
            def handle_dialog(dialog):
                log_fn(f"💬 Diálogo do sistema: '{dialog.message}' - Aceitando...")
                if dialog.type == "alert" or "inválido" in dialog.message.lower() or "percentual" in dialog.message.lower():
                    rt_alert_detected[0] = True
                dialog.accept()
            page.on("dialog", handle_dialog)

            run_step(lambda: page.wait_for_load_state("networkidle"))
            wait_for_ajax()

            log_fn("🔎 Pesquisando pedido...")
            run_step(lambda: page.fill("#pedido_selecionado", pedido))
            run_step(lambda: page.click("#CONSULTAR"))
            wait_for_ajax()

            log_fn("🔍 Verificando vendedor...")
            vendedor_input = vendedor.strip().upper()
            vendedor_locator = page.locator("td").filter(
                has=page.locator("p.Rf", has_text="VENDEDOR")).locator("p.C")
            vendedor_sistema = ""
            if vendedor_locator.count() > 0:
                vendedor_sistema = vendedor_locator.first.inner_text().replace("\xa0", " ").strip().upper()
            log_fn(f"  Vendedor no sistema: '{vendedor_sistema}' | Esperado: '{vendedor_input}'")
            if vendedor_input not in vendedor_sistema and vendedor_sistema not in vendedor_input:
                log_fn(f"❌ Vendedor não confere! Esperado: '{vendedor_input}', encontrado: '{vendedor_sistema}'")
                context.close()
                return

            log_fn("🔍 Verificando indicador...")
            indicador_locator = page.locator("td").filter(
                has=page.locator("p.Rf", has_text="INDICADOR")).locator("p.C")
            indicador_texto = ""
            if indicador_locator.count() > 0:
                indicador_texto = indicador_locator.first.inner_text().replace("\xa0", " ").strip()
            indicador_vazio = not indicador_texto
            if indicador_vazio:
                log_fn("  Indicador: (vazio/sem indicador)")
            else:
                log_fn(f"  Indicador: '{indicador_texto}'")
            log_fn(f"  Indicador vazio: {indicador_vazio}")

            log_fn("✏️ Entrando em modificação...")
            run_step(lambda: page.click("#bMODIFICA"))
            wait_for_ajax()

            log_fn("🔄 Zerando desconto...")
            run_step(lambda: page.fill("#c_desc_linear", "0"))
            run_step(lambda: page.click("#btnDescLinear"))
            wait_for_ajax()

            # ── Preenche número da margem se vazio ────────────────────────
            if num_margem_input:
                ctrl_atual = page.locator("#c_id_ctrl_negociacao").input_value().strip()
                if not ctrl_atual:
                    log_fn(f"🔢 Preenchendo número da margem: '{num_margem_input}'...")
                    preenche_el_local("#c_id_ctrl_negociacao", num_margem_input)
                else:
                    log_fn(f"  Número da margem já preenchido: '{ctrl_atual}'")

            log_fn("📋 Lendo itens...")
            todos      = page.locator("input.PLLd").all()
            num_linhas = len(todos) // CAMPOS_POR_LINHA
            qtds, precos, linhas = [], [], []
            for linha in range(num_linhas):
                base      = linha * CAMPOS_POR_LINHA
                qtd_val   = todos[base + IDX_QTDE].input_value().strip()
                preco_val = todos[base + IDX_PRECO_LISTA].input_value().strip()
                if qtd_val and preco_val and qtd_val not in ("","0") and preco_val not in ("","0,00"):
                    qtds.append(int(qtd_val))
                    precos.append(parse_brl(preco_val))
                    linhas.append(linha)
                    log_fn(f"  Linha {linha}: qtd={qtd_val}  lista={preco_val}")

            if not linhas:
                log_fn("❌ Nenhum item encontrado!")
                context.close()
                return

            log_fn("🧮 Calculando desconto...")
            novos = distribuir_por_desconto(qtds, precos, valor_desejado)
            soma  = sum(q * v for q, v in zip(qtds, novos))
            log_fn(f"  ✔ Total: {fmt_brl(soma)}")

            log_fn("✍️ Preenchendo valores...")
            for i, linha in enumerate(linhas):
                fmt = fmt_brl(novos[i])
                log_fn(f"  Linha {linha}: {fmt}")
                preenche_tabela_local("c_vl_NF",       linha, fmt)
                preenche_tabela_local("c_vl_unitario",  linha, fmt)

            log_fn("💰 Preenchendo pagamento...")
            preenche_pagamento_local(pagamento)

            # ── Lê número de controle de negociação ───────────────────────
            log_fn("🔢 Lendo número de controle de negociação...")
            run_step(lambda: page.evaluate("window.scrollTo(0, 0)"))
            time.sleep(0.5)
            num_ctrl = page.locator("#c_id_ctrl_negociacao").input_value().strip()
            log_fn(f"  Número de controle: '{num_ctrl}'")

            if not num_ctrl:
                log_fn("🚨 Campo de controle de negociação está vazio! Cancelando e encerrando...")
                context.close()
                time.sleep(1)
                os._exit(1)

            # ── Verifica no simulador ─────────────────────────────────────
            log_fn("🌐 Abrindo simulador para validação...")
            sim_page = context.new_page()
            sim_page.add_init_script(BLOCKER)
            sim_page.goto(URL_SIMULADOR)
            sim_page.wait_for_load_state("networkidle")
            time.sleep(1.5)

            def check_sim():
                try:
                    if sim_page.evaluate("window.userIntervened"):
                        raise Exception("Intervenção do usuário detectada")
                except Exception as e:
                    if "Intervenção do usuário detectada" in str(e):
                        raise e

            ja_logado = False
            try:
                email_field = sim_page.locator("#l-email")
                if email_field.count() == 0:
                    ja_logado = True
                else:
                    ja_logado = not email_field.first.is_visible()
            except Exception:
                ja_logado = False

            if ja_logado:
                log_fn("🔓 Já está logado no simulador, pulando login...")
            else:
                log_fn("🔐 Logando no simulador...")
                try:
                    sim_page.locator("#l-email").fill(email_sim)
                    sim_page.locator("#l-senha").fill(SENHA_SIM)
                    sim_page.locator("button.btn-entrar").click()
                    sim_page.wait_for_load_state("networkidle")
                    time.sleep(2)
                except Exception as e:
                    log_fn(f"  Aviso login simulador: {e}")

            num_ctrl_limpo = "".join(ch for ch in num_ctrl if ch.isdigit())
            log_fn(f"🔍 Buscando '{num_ctrl_limpo}' no simulador...")
            try:
                campo_busca = sim_page.locator("#cq-num")
                campo_busca.wait_for(state="visible", timeout=10000)
                campo_busca.click()
                campo_busca.fill("")
                campo_busca.fill(num_ctrl_limpo)
                valor_no_campo = campo_busca.input_value()
                log_fn(f"  Valor no campo após preencher: '{valor_no_campo}'")
                if valor_no_campo != num_ctrl_limpo:
                    campo_busca.fill("")
                    campo_busca.type(num_ctrl_limpo, delay=80)
                sim_page.locator("button.btn-save[onclick*='buscarConsulta']").click()
                sim_page.wait_for_load_state("networkidle")
                time.sleep(2)
            except Exception as e:
                log_fn(f"  Aviso busca simulador: {e}")

            # ── Validação 1: Status ──────────────────────────────────────
            status_ok = False
            status_texto = ""
            status_completo = ""
            try:
                sim_page.locator("span.st-aprovado, span.st-aprov-auto, span[class^='st-']").first.wait_for(
                    state="visible", timeout=10000)
            except Exception:
                pass

            try:
                for sel in ("span.st-aprovado", "span.st-aprov-auto"):
                    status_el = sim_page.locator(sel)
                    if status_el.count() > 0 and status_el.first.is_visible():
                        status_completo = status_el.first.inner_text().strip()
                        status_texto = status_completo
                        if "Aprovado" in status_texto or "Aprovação" in status_texto or "Automática" in status_texto:
                            status_ok = True
                            break
            except Exception as e:
                log_fn(f"  Aviso status: {e}")
            log_fn(f"  Status encontrado: '{status_texto}' | Aprovado: {status_ok}")

            # ── Validação 2: Pagamento ───────────────────────────────────
            opcao = pagamento.get("opcao", "")
            forma_escolhida = ""
            if opcao == "1":
                forma_escolhida = "vista"
            elif opcao == "2":
                f = pagamento.get("forma", "")
                forma_escolhida = "vista" if f in ("1", "2") else "boleto"
            elif opcao in ("3", "4"):
                forma_escolhida = "cartão"
            elif opcao in ("5", "6"):
                entrada = pagamento.get("entrada_forma", pagamento.get("prim_forma", ""))
                prest   = pagamento.get("prest_forma",   pagamento.get("demais_forma", ""))
                ref = prest if prest else entrada
                forma_escolhida = "cartão" if ref in ("5", "7") else "boleto"

            pagamento_ok = False
            pagamento_texto = ""
            try:
                pag_el = sim_page.locator("#cq-pagamento")
                pag_el.first.wait_for(state="visible", timeout=8000)
                if pag_el.count() > 0 and pag_el.first.is_visible():
                    pagamento_texto = pag_el.first.inner_text().strip().lower()
                    pagamento_ok = forma_escolhida in pagamento_texto
            except Exception as e:
                log_fn(f"  Aviso pagamento: {e}")

            log_fn(f"  Pagamento: '{pagamento_texto}' | Esperado: '{forma_escolhida}' | OK: {pagamento_ok}")

            # ── Lê RT ────────────────────────────────────────────────────
            rt_valor = ""
            try:
                rt_el = sim_page.locator("#cq-rt")
                if rt_el.count() > 0 and rt_el.first.is_visible():
                    rt_texto = rt_el.first.inner_text().strip()
                    if rt_texto and rt_texto not in ("-", "0", "0%", ""):
                        rt_valor = rt_texto
                        log_fn(f"  RT encontrado: '{rt_valor}'")
                    else:
                        log_fn("  RT vazio ou zero — não será preenchido")
            except Exception as e:
                log_fn(f"  Aviso RT: {e}")

            sim_page.close()

            if not status_ok or not pagamento_ok:
                log_fn(f"🚨 Validação falhou (Aprovado: {status_ok} | Pagamento: {pagamento_ok})! Cancelando...")
                context.close()
                time.sleep(1)
                os._exit(1)

            log_fn("✅ Aprovado e pagamento confere! Confirmando pedido...")

            # ── Preenche RT (considerando indicador) ─────────────────────
            if indicador_vazio:
                log_fn("⚠️ Indicador vazio — RT será mantido em 0%...")
                run_step(lambda: page.evaluate("window.scrollTo(0, 0)"))
                time.sleep(0.3)

                def zera_rt_indicador():
                    el = page.locator("#c_perc_RT")
                    el.click(); el.select_text()
                    el.fill("0,0")
                    el.dispatch_event("change")
                    el.dispatch_event("input")
                    el.dispatch_event("blur")
                run_step(zera_rt_indicador, trigger_ajax=False)
                time.sleep(0.5)
            elif rt_valor:
                log_fn(f"💡 Preenchendo RT: {rt_valor}...")
                run_step(lambda: page.evaluate("window.scrollTo(0, 0)"))
                time.sleep(0.3)

                rt_alert_detected[0] = False

                def preenche_rt():
                    el = page.locator("#c_perc_RT")
                    el.click(); el.select_text()
                    el.fill(rt_valor.replace("%", "").strip().replace(".", ","))
                    el.dispatch_event("change")
                    el.dispatch_event("input")
                    el.dispatch_event("blur")
                run_step(preenche_rt, trigger_ajax=False)
                time.sleep(0.5)

                if rt_alert_detected[0]:
                    log_fn("⚠️ RT inválido detectado! Resetando valor para '0,0'...")
                    def reseta_rt():
                        el = page.locator("#c_perc_RT")
                        el.click(); el.select_text()
                        el.fill("0,0")
                        el.dispatch_event("change")
                        el.dispatch_event("input")
                        el.dispatch_event("blur")
                    run_step(reseta_rt, trigger_ajax=False)
                    time.sleep(0.5)
            else:
                log_fn("  RT vazio — pulando preenchimento de RT")

            # ── Preenche observação com status + margem (DEVE SER ANTES DE CONFIRMAR) ──
            log_fn("📝 Preenchendo observação do pedido...")
            run_step(lambda: page.evaluate("window.scrollTo(0, document.body.scrollHeight)"))
            time.sleep(0.5)

            texto_obs = f"{status_completo} - #{num_ctrl}"

            def preenche_obs():
                obs_el = page.locator("#c_obs1")
                obs_el.click()
                time.sleep(0.2)
                # Vai pro final do texto e aperta Enter 2x
                page.keyboard.press("End")
                time.sleep(0.1)
                page.keyboard.press("Enter")
                time.sleep(0.1)
                page.keyboard.press("Enter")
                time.sleep(0.1)
                # Digita no formato: status - #numero_da_margem
                page.keyboard.type(texto_obs, delay=30)
                obs_el.dispatch_event("change")
                obs_el.dispatch_event("input")
                obs_el.dispatch_event("blur")
            run_step(preenche_obs, trigger_ajax=False)
            time.sleep(0.5)
            log_fn("  ✔ Observação preenchida!")
            log_fn(f"    + {texto_obs}")

            # ── Confirma ─────────────────────────────────────────────────
            run_step(lambda: page.evaluate("document.getElementById('bCONFIRMA').click()"))
            wait_for_ajax()

            # Aguarda a gravação ser processada e retornar para o modo leitura (botão bMODIFICA visível)
            # ou aguarda 3 segundos como segurança
            try:
                page.locator("#bMODIFICA").wait_for(state="visible", timeout=6000)
                log_fn("  Confirmado e retornado para a tela de visualização.")
            except Exception:
                time.sleep(3)

            # ── Salva número do pedido no simulador ──────────────────────
            log_fn(f"📋 Salvando número do pedido '{pedido}' no simulador...")
            try:
                sim_page2 = context.new_page()
                sim_page2.add_init_script(BLOCKER)
                sim_page2.goto(URL_SIMULADOR)
                sim_page2.wait_for_load_state("networkidle")
                time.sleep(1.5)

                try:
                    ef = sim_page2.locator("#l-email")
                    if ef.count() > 0 and ef.first.is_visible():
                        sim_page2.locator("#l-email").fill(email_sim)
                        sim_page2.locator("#l-senha").fill(SENHA_SIM)
                        sim_page2.locator("button.btn-entrar").click()
                        sim_page2.wait_for_load_state("networkidle")
                        time.sleep(2)
                except: pass

                try:
                    cb = sim_page2.locator("#cq-num")
                    cb.wait_for(state="visible", timeout=10000)
                    cb.fill(""); cb.fill(num_ctrl_limpo)
                    sim_page2.locator("button.btn-save[onclick*='buscarConsulta']").click()
                    sim_page2.wait_for_load_state("networkidle")
                    time.sleep(2)
                except Exception as e:
                    log_fn(f"  Aviso busca: {e}")

                cp = sim_page2.locator("#cq-pedido")
                cp.wait_for(state="visible", timeout=8000)
                cp.fill(""); cp.fill(pedido)
                sim_page2.locator("button.btn-save[onclick*='salvarNumeroPedido']").click()
                sim_page2.wait_for_load_state("networkidle")
                time.sleep(1)
                log_fn(f"  ✔ Pedido '{pedido}' salvo no simulador!")
                sim_page2.close()
            except Exception as e:
                log_fn(f"  Aviso ao salvar no simulador: {e}")

            log_fn("🎉 FINALIZADO COM SUCESSO!")
            context.close()

    except Exception as e:
        if "Intervenção do usuário detectada" in str(e):
            log_fn("🚨 INTERVENÇÃO DETECTADA! Encerrando programa por segurança...")
            time.sleep(1)
            os._exit(1)
        else:
            log_fn(f"❌ ERRO NA AUTOMAÇÃO: {str(e)}")


# =========================
# INTERFACE GRÁFICA
# =========================
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Bot de Pedidos — Discomercio")
        self.resizable(False, False)
        self.configure(bg="#f0f0f0")
        self.frames = {}
        for F in (TelaPedido, TelaPagamento, TelaAvista, TelaParcUnica,
                  TelaCartaoNet, TelaCartaoMaq, TelaParcelado, TelaSemEntrada, TelaLog):
            self.frames[F.__name__] = F(self)
        self.dados = {}
        self.show("TelaPedido")

    def show(self, name):
        for f in self.frames.values():
            f.pack_forget()
        self.frames[name].pack(fill="both", expand=True, padx=24, pady=20)
        if hasattr(self.frames[name], "on_show"):
            self.frames[name].on_show()

def label(parent, text, bold=False):
    f = ("Segoe UI", 10, "bold") if bold else ("Segoe UI", 10)
    tk.Label(parent, text=text, bg="#f0f0f0", font=f).pack(anchor="w", pady=(8,0))

def entry(parent, textvariable=None, width=30):
    e = ttk.Entry(parent, textvariable=textvariable, width=width, font=("Segoe UI", 10))
    e.pack(anchor="w", pady=(2,0))
    return e

def btn(parent, text, command, primary=False):
    bg = "#185FA5" if primary else "#e0e0e0"
    fg = "white"   if primary else "black"
    b  = tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                   font=("Segoe UI", 10, "bold" if primary else "normal"),
                   relief="flat", padx=14, pady=6, cursor="hand2")
    b.pack(side="left", padx=(0,8), pady=(16,0))
    return b

def combo(parent, values, textvariable=None, width=28):
    c = ttk.Combobox(parent, values=values, textvariable=textvariable,
                     state="readonly", width=width, font=("Segoe UI", 10))
    c.pack(anchor="w", pady=(2,0))
    return c

def title(parent, text):
    tk.Label(parent, text=text, bg="#f0f0f0",
             font=("Segoe UI", 13, "bold"), fg="#185FA5").pack(anchor="w", pady=(0,12))

def row(parent):
    f = tk.Frame(parent, bg="#f0f0f0")
    f.pack(anchor="w")
    return f

def combo_forma(parent, formas, var):
    textos = [f"{v} – {t}" for v,t in formas]
    c = combo(parent, textos, width=32)
    c.current(0)
    def on_change(e):
        var.set(c.get().split(" – ")[0])
    c.bind("<<ComboboxSelected>>", on_change)
    var.set(formas[0][0])
    return c

FORMAS_AV  = [("1","Dinheiro"),("2","Depósito"),("6","Boleto AV")]
FORMAS_PU  = [("1","Dinheiro"),("2","Depósito"),("4","Boleto")]
FORMAS_ENT = [("1","Dinheiro"),("2","Depósito"),("4","Boleto"),
              ("6","Boleto AV"),("5","Cartão (internet)"),("7","Cartão (maquineta)")]
FORMAS_PRE = [("1","Dinheiro"),("2","Depósito"),("4","Boleto"),
              ("5","Cartão (internet)"),("7","Cartão (maquineta)")]
FORMAS_PSE = [("2","Depósito"),("4","Boleto"),
              ("5","Cartão (internet)"),("7","Cartão (maquineta)")]

class TelaPedido(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#f0f0f0")
        self.app = master
        title(self, "🛒  Dados do Pedido")
        label(self, "Número do pedido")
        self.pedido = tk.StringVar()
        entry(self, self.pedido)
        label(self, "Nome vendedor")
        self.vendedor = tk.StringVar()
        entry(self, self.vendedor)
        label(self, "Valor desejado (ex: 28.700,00)")
        self.valor = tk.StringVar()
        entry(self, self.valor)
        label(self, "Número da margem (se vazio, usa o já preenchido no sistema)")
        self.num_margem = tk.StringVar()
        entry(self, self.num_margem, width=15)
        label(self, "Email Vercel (opcional — deixe vazio para usar o padrão)")
        self.email_sim = tk.StringVar()
        entry(self, self.email_sim, width=35)
        r = row(self)
        btn(r, "Próximo →", self.avancar, primary=True)

    def avancar(self):
        if not self.pedido.get() or not self.valor.get() or not self.vendedor.get():
            messagebox.showwarning("Atenção", "Preencha todos os campos.")
            return
        try:
            parse_brl(self.valor.get())
        except:
            messagebox.showerror("Erro", "Valor inválido. Use o formato: 28.700,00")
            return
        self.app.dados["pedido"]    = self.pedido.get().strip().upper()
        self.app.dados["valor"]     = self.valor.get().strip()
        self.app.dados["vendedor"]  = self.vendedor.get().strip().upper()
        self.app.dados["num_margem"] = self.num_margem.get().strip()
        self.app.dados["email_sim"]  = self.email_sim.get().strip() or USUARIO_SIM
        self.app.show("TelaPagamento")

OPCOES_PAG = [
    ("1","À Vista"), ("2","Parcela Única"),
    ("3","Parcelado no Cartão (internet)"), ("4","Parcelado no Cartão (maquineta)"),
    ("5","Parcelado com Entrada"), ("6","Parcelado sem Entrada (Boleto)"),
]

class TelaPagamento(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#f0f0f0")
        self.app = master
        title(self, "💳  Forma de Pagamento")
        self.opcao = tk.StringVar(value="1")
        for val, texto in OPCOES_PAG:
            tk.Radiobutton(self, text=texto, variable=self.opcao, value=val,
                           bg="#f0f0f0", font=("Segoe UI", 10),
                           activebackground="#f0f0f0").pack(anchor="w", pady=3)
        r = row(self)
        btn(r, "← Voltar",  lambda: master.show("TelaPedido"))
        btn(r, "Próximo →", self.avancar, primary=True)

    def avancar(self):
        self.app.dados["opcao"] = self.opcao.get()
        destinos = {"1":"TelaAvista","2":"TelaParcUnica","3":"TelaCartaoNet",
                    "4":"TelaCartaoMaq","5":"TelaParcelado","6":"TelaSemEntrada"}
        self.app.show(destinos[self.opcao.get()])

class TelaAvista(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#f0f0f0")
        self.app = master
        title(self, "💵  À Vista")
        self.forma = tk.StringVar()
        label(self, "Forma de pagamento")
        combo_forma(self, FORMAS_AV, self.forma)
        r = row(self)
        btn(r, "← Voltar", lambda: master.show("TelaPagamento"))
        btn(r, "✔ Executar", self.executar, primary=True)

    def executar(self):
        self.app.dados["forma"] = self.forma.get()
        self.app.show("TelaLog")
        threading.Thread(target=self._rodar, daemon=True).start()

    def _rodar(self):
        rodar_automacao(self.app.dados["pedido"], self.app.dados["vendedor"],
            parse_brl(self.app.dados["valor"]),
            {"opcao":"1","forma":self.app.dados["forma"]},
            self.app.frames["TelaLog"].log,
            email_sim=self.app.dados.get("email_sim"),
            num_margem_input=self.app.dados.get("num_margem"))

class TelaParcUnica(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#f0f0f0")
        self.app = master
        title(self, "📄  Parcela Única")
        self.forma  = tk.StringVar()
        self.vencto = tk.StringVar()
        label(self, "Forma de pagamento"); combo_forma(self, FORMAS_PU, self.forma)
        label(self, "Vencendo após (dias)"); entry(self, self.vencto, width=10)
        r = row(self)
        btn(r, "← Voltar", lambda: master.show("TelaPagamento"))
        btn(r, "✔ Executar", self.executar, primary=True)

    def executar(self):
        self.app.show("TelaLog")
        threading.Thread(target=self._rodar, daemon=True).start()

    def _rodar(self):
        rodar_automacao(self.app.dados["pedido"], self.app.dados["vendedor"],
            parse_brl(self.app.dados["valor"]),
            {"opcao":"2","forma":self.forma.get(),"pu_vencto":self.vencto.get()},
            self.app.frames["TelaLog"].log,
            email_sim=self.app.dados.get("email_sim"),
            num_margem_input=self.app.dados.get("num_margem"))

class TelaCartaoNet(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#f0f0f0")
        self.app = master
        title(self, "💳  Cartão (internet)")
        self.qtde = tk.StringVar()
        label(self, "Quantidade de vezes"); entry(self, self.qtde, width=10)
        r = row(self)
        btn(r, "← Voltar", lambda: master.show("TelaPagamento"))
        btn(r, "✔ Executar", self.executar, primary=True)

    def executar(self):
        self.app.show("TelaLog")
        threading.Thread(target=self._rodar, daemon=True).start()

    def _rodar(self):
        rodar_automacao(self.app.dados["pedido"], self.app.dados["vendedor"],
            parse_brl(self.app.dados["valor"]),
            {"opcao":"3","pc_qtde":self.qtde.get()},
            self.app.frames["TelaLog"].log,
            email_sim=self.app.dados.get("email_sim"),
            num_margem_input=self.app.dados.get("num_margem"))

class TelaCartaoMaq(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#f0f0f0")
        self.app = master
        title(self, "💳  Cartão (maquineta)")
        self.qtde = tk.StringVar()
        label(self, "Quantidade de vezes"); entry(self, self.qtde, width=10)
        r = row(self)
        btn(r, "← Voltar", lambda: master.show("TelaPagamento"))
        btn(r, "✔ Executar", self.executar, primary=True)

    def executar(self):
        self.app.show("TelaLog")
        threading.Thread(target=self._rodar, daemon=True).start()

    def _rodar(self):
        rodar_automacao(self.app.dados["pedido"], self.app.dados["vendedor"],
            parse_brl(self.app.dados["valor"]),
            {"opcao":"4","pc_qtde":self.qtde.get()},
            self.app.frames["TelaLog"].log,
            email_sim=self.app.dados.get("email_sim"),
            num_margem_input=self.app.dados.get("num_margem"))

class TelaParcelado(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#f0f0f0")
        self.app = master
        title(self, "🏦  Parcelado com Entrada")
        self.ent_forma   = tk.StringVar()
        self.ent_valor   = tk.StringVar()
        self.prest_forma = tk.StringVar()
        self.prest_qtde  = tk.StringVar()
        self.prest_dias  = tk.StringVar()
        label(self, "Forma da entrada", bold=True); combo_forma(self, FORMAS_ENT, self.ent_forma)
        label(self, "Valor da entrada (ex: 14.900,00)"); entry(self, self.ent_valor)
        tk.Frame(self, bg="#ddd", height=1).pack(fill="x", pady=10)
        label(self, "Forma das prestações", bold=True); combo_forma(self, FORMAS_PRE, self.prest_forma)
        label(self, "Quantidade de parcelas"); entry(self, self.prest_qtde, width=10)
        label(self, "Parcelas a cada (dias)"); entry(self, self.prest_dias, width=10)
        r = row(self)
        btn(r, "← Voltar", lambda: master.show("TelaPagamento"))
        btn(r, "✔ Executar", self.executar, primary=True)

    def executar(self):
        self.app.show("TelaLog")
        threading.Thread(target=self._rodar, daemon=True).start()

    def _rodar(self):
        rodar_automacao(self.app.dados["pedido"], self.app.dados["vendedor"],
            parse_brl(self.app.dados["valor"]),
            {"opcao":"5","entrada_forma":self.ent_forma.get(),
             "entrada_valor":self.ent_valor.get(),
             "prest_forma":self.prest_forma.get(),"prest_qtde":self.prest_qtde.get(),
             "prest_dias":self.prest_dias.get()},
            self.app.frames["TelaLog"].log,
            email_sim=self.app.dados.get("email_sim"),
            num_margem_input=self.app.dados.get("num_margem"))

class TelaSemEntrada(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#f0f0f0")
        self.app = master
        title(self, "📋  Parcelado sem Entrada")
        self.prim_forma   = tk.StringVar()
        self.prim_valor   = tk.StringVar()
        self.prim_apos    = tk.StringVar()
        self.demais_forma = tk.StringVar()
        self.demais_qtde  = tk.StringVar()
        self.demais_dias  = tk.StringVar()
        label(self, "1ª Prestação — Forma", bold=True); combo_forma(self, FORMAS_PSE, self.prim_forma)
        label(self, "Valor da 1ª prestação (ex: 5.000,00)"); entry(self, self.prim_valor)
        label(self, "Vencendo após (dias)"); entry(self, self.prim_apos, width=10)
        tk.Frame(self, bg="#ddd", height=1).pack(fill="x", pady=10)
        label(self, "Demais Prestações — Forma", bold=True); combo_forma(self, FORMAS_PSE, self.demais_forma)
        label(self, "Quantidade de parcelas"); entry(self, self.demais_qtde, width=10)
        label(self, "Parcelas a cada (dias)"); entry(self, self.demais_dias, width=10)
        r = row(self)
        btn(r, "← Voltar", lambda: master.show("TelaPagamento"))
        btn(r, "✔ Executar", self.executar, primary=True)

    def executar(self):
        self.app.show("TelaLog")
        threading.Thread(target=self._rodar, daemon=True).start()

    def _rodar(self):
        rodar_automacao(self.app.dados["pedido"], self.app.dados["vendedor"],
            parse_brl(self.app.dados["valor"]),
            {"opcao":"6","prim_forma":self.prim_forma.get(),
             "prim_valor":self.prim_valor.get(),"prim_apos":self.prim_apos.get(),
             "demais_forma":self.demais_forma.get(),"demais_qtde":self.demais_qtde.get(),
             "demais_dias":self.demais_dias.get()},
            self.app.frames["TelaLog"].log,
            email_sim=self.app.dados.get("email_sim"),
            num_margem_input=self.app.dados.get("num_margem"))

class TelaLog(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#f0f0f0")
        self.app = master
        title(self, "⚙️  Executando...")
        self.txt = tk.Text(self, height=18, width=55, font=("Consolas", 9),
                           bg="#1e1e1e", fg="#d4d4d4", relief="flat", state="disabled")
        self.txt.pack()
        r = row(self)
        btn(r, "↩ Novo pedido", self.novo, primary=True)

    def on_show(self):
        self.txt.configure(state="normal")
        self.txt.delete("1.0", "end")
        self.txt.configure(state="disabled")

    def log(self, msg):
        self.txt.configure(state="normal")
        self.txt.insert("end", msg + "\n")
        self.txt.see("end")
        self.txt.configure(state="disabled")

    def novo(self):
        self.app.dados = {}
        self.app.frames["TelaPedido"].pedido.set("")
        self.app.frames["TelaPedido"].vendedor.set("")
        self.app.frames["TelaPedido"].valor.set("")
        self.app.frames["TelaPedido"].num_margem.set("")
        self.app.frames["TelaPedido"].email_sim.set("")
        self.app.show("TelaPedido")

# =========================
# MAIN
# =========================
if __name__ == "__main__":
    app = App()
    app.mainloop()
