"""Aplicativo local para classificar produtos por setor usando Gemini via Selenium.

O script lê o arquivo ``SMG11.F170.csv``, envia lotes de produtos para o Gemini,
valida as respostas contra uma lista fechada de setores e salva uma base de
conhecimento incremental em CSV. Opcionalmente, também espelha o andamento para
um endpoint do Google Apps Script.
"""

import os
import re
import threading
import time

import customtkinter as ctk
import pandas as pd
import pyperclip
import requests
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

# =====================================================================
# CONFIGURAÇÃO DE COMUNICAÇÃO NUVEM (INSIRA SEU LINK DO APPS SCRIPT AQUI)
# =====================================================================
URL_APPS_SCRIPT = "https://script.google.com/macros/s/SUA_URL_AQUI_GERADA_NA_IMPLANTACAO/exec"

# Dicionário global para espelhamento rápido de estado.
ESTADO_COMPARTILHADO = {
    "status": "Pronto",
    "nome_arquivo": "Nenhum",
    "total": 0,
    "processados": 0,
    "pendentes": 0,
    "erros": 0,
    "ultimo_produto": "-",
    "ultimo_setor": "-",
}


def sincronizar_com_a_nuvem(novos_dados):
    """Atualiza estados locais e dispara um POST assíncrono ao Apps Script."""
    global ESTADO_COMPARTILHADO
    ESTADO_COMPARTILHADO.update(novos_dados)

    if URL_APPS_SCRIPT and "SUA_URL_AQUI" not in URL_APPS_SCRIPT:

        def disparar_post():
            try:
                requests.post(URL_APPS_SCRIPT, json=ESTADO_COMPARTILHADO, timeout=5)
            except requests.RequestException:
                pass  # Previne travamentos se houver oscilação de internet.

        # Dispara em uma thread separada para o Python não travar esperando a resposta da web.
        t = threading.Thread(target=disparar_post)
        t.daemon = True
        t.start()


# =====================================================================
# CONFIGURAÇÕES DE DIRETÓRIO LOCAL E PROMPTS
# =====================================================================
PASTA_TRABALHO = r"C:\Users\saaesilva\Desktop\IA SETORIZAR"
CAMINHO_SMG11 = r"C:\Users\saaesilva\Desktop\Arquivos\SMG11.F170.csv"
CAMINHO_RESERVA = r"C:\Users\saaesilva\Desktop\SMG11.F170.csv"

ARQUIVO_BASE_CONHECIMENTO = os.path.join(PASTA_TRABALHO, "ia_base_conhecimento.csv")
ARQUIVO_LOG_ERROS = os.path.join(PASTA_TRABALHO, "erros_lotes.txt")
TAMANHO_LOTE = 30

SETORES_VALIDOS = [
    "AC.CARNES BOVINAS (CORTES TRADICIONAIS)",
    "AC.CARNES BOVINAS (CORTES NOBRES / CHURRASCO)",
    "AC. AVES/FRANGO",
    "AC. SUINOS/PORCO",
    "AC. EMBUTIDOS/LINGUICA",
    "AC. MIUDOS/VISCERAS",
    "AC. AUTOATEND/BANDEJ",
    "LJ01-G.U",
    "LJ01-LEITE L.VIDA/BEB.LACTEA",
    "LJ02-CHICLETES/BALAS/PIRULITOS",
    "LJ02-SALGADINHO/AMENDOIM",
    "LJ02-DOCES POP./GELATINA",
    "LJ02-CHOCOLATES/BOMBOM",
    "LJ02-ADOCANTES E DIET/LIGHT",
    "LJ02-BEB.CHAS",
    "LJ04-FIL.CAFE/CAFE",
    "LJ04-BIC.RECHEA/BISC.WAFER",
    "LJ04-BISC.SALGADOS/BISC.MAIZENA",
    "LJ04-CHOCOL. E  ACHO.PO",
    "LJ04-CEREAIS",
    "LJ04-CONF.CONFEITARIA",
    "LJ04-MIST.BOLO ATE 1KG",
    "LJ04-CHA GELADOS",
    "LJ06-MOLHOS/EXTRATOS",
    "LJ06-LEITE.PO",
    "LJ06-ENLATADOS/CONSERVAS",
    "LJ06-MACARAO.INST",
    "LJ06-QUEIJO RALADO",
    "LJ06-CREME E LEITE CONDESADO",
    "LJ06-ALIM.INFATIL",
    "LJ06-MACARAO COMUM",
    "LJ08-MAION/CATCHUP E BARB.",
    "LJ08-OLEO.SOJA/OLEO.COMPOSTO",
    "LJ08-TEMPEROS/CONDIMENTOS/SAL",
    "LJ08-FARINACEOS",
    "LJ08-MOLHOS PIM/ALH/ING E DIVERSOS",
    "LJ08-AZEITES",
    "LJ22-ARROZ",
    "LJ22-FEIJAO",
    "LJ22-ACUCAR",
    "LJ22-FARINHA TRIGO",
    "LJ10-AUTOMOTIVOS",
    "LJ10-ACESSORIOS PETSHOP",
    "LJ10-CAMPING",
    "LJ10-FOSFORO/VELA/PAPELAR",
    "LJ10-ELETRODOMESTICOS",
    "LJ10-PAPEL HIGIENICO",
    "LJ10-CAMA MESA BANHO",
    "LJ10-BRINQUEDOS KIDS",
    "LJ10-FERRAMENTAS",
    "LJ10-PNEUS",
    "LJ10-RACAO KAT",
    "LJ10-RACAO DOG",
    "LJ10-LAMPADAS",
    "LJ10-SANDALIAS",
    "LJ10-PAPELARIA",
    "LJ12-UTIL.ALUMINIO",
    "LJ12-UTENS.DOMESTICO/PLASTICOS",
    "LJ12-BALDES/LIXEIRAS/SACO.LIXO",
    "LJ12-LA.ACO/VASSOURAS/FLANELAS",
    "LJ12-AGUA SANITARIA /ALVEJANTES",
    "LJ12-GARRAF.TERMICAS",
    "LJ12-INSETICIDAS",
    "LJ14-SABAO.PDC/DET.LIQUIDO",
    "LJ14-DESIFETATES/LIMPADORES/CERAS",
    "LJ14-SAB LIQ",
    "LJ14-DETERGENTE.PO",
    "LJ14-AMACIANTES ROUPA",
    "LJ16-SHAMPOO",
    "LJ16-FRALDAS BEBE",
    "LJ16-SABONETES",
    "LJ16-DESODORANTES AERO",
    "LJ16-CONDICIONADORES",
    "LJ16-FRALDAS ESPECIAIS",
    "LJ16-CREME DENTAL",
    "LJ16-CREME DE PETEAR",
    "LJ16-DESODORANTES ROLON/CREME",
    "LJ16-CREME HIDRATANTE PELE",
    "LJ16-TINTA CABELO",
    "LJ16-GILETE APARADOR",
    "LJ16-INFATIL",
    "LJ16-HIG. PESSOAL",
    "LJ16-ESCOVA/BUCHA BANHO",
    "LJ16-ABSORVENTE",
    "LJ16-CREME HIDRATANTE CAB.",
    "LJ18-COPOS DESCARTAVEIS",
    "LJ18-PAPEL TOALHA/GUARDANAPOS",
    "LJ18-FILM.PVC/PAPEL.ALUM",
    "LJ18-FESTINHAS",
    "LJ18-SUCOS PRONTOS",
    "LJ18-SUCOS POLPAS NATURAL",
    "LJ18-REFR.PO",
    "LJ18-ISOTONICO",
    "LJ18-AGUAS MINERAIS",
    "LJ18-EMBALAGENS",
    "LJ18-AGUA DE COCO",
    "LJ18-COPO VIDRO / UTILITARIOS VIDRO",
    "LJ20-ENERGETICOS",
    "LJ20-LICOR",
    "LJ20-VODKA",
    "LJ20-WISKY",
    "LJ20-VINHOS",
    "LJ20-CACHACA",
    "LJ20-APERITIVOS",
    "LJ20-CERVEJA LATA",
    "LJ20-CERVEJA LONG NECK",
    "LJ20-REF.LATA",
    "LJ20-REF.PET",
    "LJ20-ESPUMANTES",
    "LJ20-GIN",
    "LJ20-BEBIDAS QUENTES",
    "RF.REQUIJAO BAG",
    "RF.CALABRESA/LINGUICAS DEFUMADAS",
    "RF.MORTADELAS",
    "RF.MANTEIGAS",
    "RF.SORVETES/ACAI",
    "RF.MASSAS",
    "RF.APRESUNTADO/PRESUNTO",
    "RF.QUEIJO PRATO/ MUSSARELAS",
    "RF.IOGURTES",
    "RF.REQUEIJAO POTES",
    "RF.MARGARINAS",
    "RF.CARNES RESFRIADAS BOVINAS",
    "RF.CARNES CONGELADAS",
    "RF.LINFG.CONGELADA/SUINOS",
    "RF.FRANGO CONG/CORTES.FRANGO",
    "RF.CARNES PEIXES",
    "RF.PRATOS PRONTOS/POUPA",
    "RF.FATIADOS DIVERSOS",
    "RF.BACON",
    "RF.CHARQUE/BACALHAU/SALGADOS",
    "RF.MARGARINA.BALDE/GORDU.VEGETAL",
    "RF.SAZONAIS FRIOS",
    "RF.FRUTOS DO MAR",
    "RF.SALSICHAS",
    "HF.INDUSTRIALIZADOS",
    "HF.FRUTAS",
    "HF.FOLHAGEM/GOMA",
    "HF.VERDURA/LEGUME",
    "HF.RAIZES/TUBERCULOS",
    "HF.TOMATE",
    "HF.CEBOLA",
    "HF.BATATA LAVADA",
    "HF.OVOS",
    "HF.ALHOS",
    "HF.PAES/PANETONES",
    "LJ22-PANIFICACAO/ART FORMA",
    "LJ00-SAZONAL LOJA",
    "LJ00-NATALINA",
    "LJ00-TABACARIA",
    "LJ00-CHEK-STAND",
    "CF.CAFETERIA - INSUMOS",
    "CF.BEBIDAS",
    "CF.CONFEITARIA",
    "CF.BOMBONIERE",
    "CF.SALGADOS FRITO/ASSADOS",
    "LJ00-SEM SETOR",
]

ROBO_ATIVO = True


def registrar_erro(log_msg):
    timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
    with open(ARQUIVO_LOG_ERROS, "a", encoding="utf-8") as f:
        f.write(f"[{timestamp}] {log_msg}\n")


def iniciar_base_csv():
    if not os.path.exists(PASTA_TRABALHO):
        os.makedirs(PASTA_TRABALHO)
    if not os.path.exists(ARQUIVO_BASE_CONHECIMENTO):
        df_vazio = pd.DataFrame(columns=["DESCRICAO", "EMBALAGEM", "SETOR_LOJA_IA"])
        df_vazio.to_csv(ARQUIVO_BASE_CONHECIMENTO, index=False, sep=";", encoding="utf-8-sig")


def ler_arquivo_origem():
    caminho_real = CAMINHO_SMG11 if os.path.exists(CAMINHO_SMG11) else CAMINHO_RESERVA
    if not os.path.exists(caminho_real):
        return None, None

    df_csv = None
    for sep in [";", ",", "\t"]:
        for encoding in ["latin1", "utf-8", "cp1252"]:
            try:
                df_teste = pd.read_csv(caminho_real, sep=sep, encoding=encoding, nrows=5)
                if "DESCRICAO" in [str(c).upper().strip() for c in df_teste.columns]:
                    df_csv = pd.read_csv(caminho_real, sep=sep, encoding=encoding, on_bad_lines="skip")
                    break
            except (OSError, UnicodeDecodeError, pd.errors.ParserError):
                continue
        if df_csv is not None:
            break

    if df_csv is None:
        return None, None

    df_csv.columns = [str(c).upper().strip() for c in df_csv.columns]
    c_desc = "DESCRICAO"
    c_emb = next((c for c in df_csv.columns if c in ["EMBALAGEM", "EMB"]), None)
    c_cod = next((c for c in df_csv.columns if c in ["CODIGO", "COD_PROD", "ID_PRODUTO"]), None)
    c_forn = next((c for c in df_csv.columns if c in ["FORNECEDOR", "FORN"]), None)
    c_cat = next((c for c in df_csv.columns if c in ["CATEGORIA", "DEPARTAMENTO", "GRUPO"]), None)

    df_dados = pd.DataFrame()
    df_dados["descricao"] = df_csv[c_desc].astype(str).str.upper().str.strip()
    df_dados["embalagem"] = df_csv[c_emb].astype(str).str.upper().str.strip() if c_emb else ""
    df_dados["codigo"] = df_csv[c_cod].astype(str).str.strip() if c_cod else ""
    df_dados["fornecedor"] = df_csv[c_forn].astype(str).str.upper().str.strip() if c_forn else ""
    df_dados["categoria_antiga"] = df_csv[c_cat].astype(str).str.upper().str.strip() if c_cat else ""
    return df_dados, os.path.basename(caminho_real)


def classificar_e_salvar_continuo(ui_callback=None, ui_log=None):
    global ROBO_ATIVO
    ROBO_ATIVO = True

    if ui_log:
        ui_log("⏳ Analisando arquivos de dados e históricos...")
    iniciar_base_csv()

    df_processar, nome_arquivo_atual = ler_arquivo_origem()
    if df_processar is None:
        if ui_log:
            ui_log("❌ ERRO: Arquivo SMG11.F170.csv original não localizado.")
        return

    total_geral = len(df_processar)
    ja_processados_contagem = 0

    try:
        df_ja_feito = pd.read_csv(ARQUIVO_BASE_CONHECIMENTO, sep=";", encoding="utf-8-sig")
        descricoes_feitas = set(df_ja_feito["DESCRICAO"].astype(str).str.upper().str.strip())
        ja_processados_contagem = len(descricoes_feitas)
        df_processar = df_processar[~df_processar["descricao"].isin(descricoes_feitas)].reset_index(drop=True)
    except (OSError, KeyError, pd.errors.ParserError):
        pass

    if df_processar.empty:
        if ui_log:
            ui_log("🎉 Todos os itens do arquivo já constam na base de conhecimento!")
        info = {"status": "Finalizado", "total": total_geral, "processados": total_geral, "pendentes": 0}
        sincronizar_com_a_nuvem(info)
        if ui_callback:
            ui_callback(info)
        return

    df_processar["temp_id"] = df_processar.index
    total_pendentes = len(df_processar)

    info_inicial = {
        "status": "Aguardando Login",
        "nome_arquivo": nome_arquivo_atual,
        "total": total_geral,
        "processados": ja_processados_contagem,
        "pendentes": total_pendentes,
        "erros": 0,
    }
    sincronizar_com_a_nuvem(info_inicial)
    if ui_callback:
        ui_callback(info_inicial)

    if ui_log:
        ui_log(f"📊 Arquivo carregado. Falta processar {total_pendentes} itens.")

    options = Options()
    pasta_execucao = os.getcwd()
    options.add_argument(f"--user-data-dir={os.path.join(pasta_execucao, 'perfil_robo')}")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])

    driver = webdriver.Chrome(options=options)
    contador_erros = 0

    try:
        driver.get("https://gemini.google.com/app")
        wait = WebDriverWait(driver, 60)

        if ui_log:
            ui_log("🔐 Janela aberta. Faça login na conta corporativa se solicitado...")
        wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@role='textbox']")))

        if ui_log:
            ui_log("✅ Conexão estabelecida com o Gemini! Iniciando automação...")
        sincronizar_com_a_nuvem({"status": "Rodando"})
        if ui_callback:
            ui_callback({"status": "Rodando"})

        prompt_setores = ", ".join(SETORES_VALIDOS)

        for i in range(0, len(df_processar), TAMANHO_LOTE):
            if not ROBO_ATIVO:
                if ui_log:
                    ui_log("Submetendo encerramento de processos do navegador...")
                break

            lote_df = df_processar.iloc[i : i + TAMANHO_LOTE]
            linhas_produtos = []
            for _, r in lote_df.iterrows():
                ctx = f" | Cod: {r['codigo']}" if r["codigo"] else ""
                ctx += f" | Forn: {r['fornecedor']}" if r["fornecedor"] else ""
                ctx += f" | Cat_Antiga: {r['categoria_antiga']}" if r["categoria_antiga"] else ""
                linhas_produtos.append(f"{r['temp_id']}|{r['descricao']} ({r['embalagem']}){ctx}")

            prompt_final = (
                f"Setores disponiveis: [{prompt_setores}]\n\n"
                "Classifique os itens abaixo respondendo EXCLUSIVAMENTE no formato: ID|SETOR_CORRETO.\n"
                "Nao invente setores, nao altere o ID e nao escreva nenhuma saudacao ou texto explicativo.\n\n"
                "Produtos:\n" + "\n".join(linhas_produtos)
            )

            resultados_lote = {}
            sucesso_lote = False

            for tentativa in range(1, 4):
                if not ROBO_ATIVO:
                    break
                try:
                    caixa_texto = wait.until(EC.element_to_be_clickable((By.XPATH, "//div[@role='textbox']")))
                    caixa_texto.click()
                    time.sleep(0.2)

                    caixa_texto.send_keys(Keys.CONTROL, "a")
                    caixa_texto.send_keys(Keys.BACKSPACE)
                    time.sleep(0.2)

                    pyperclip.copy(prompt_final)
                    caixa_texto.send_keys(Keys.CONTROL, "v")
                    time.sleep(1)

                    try:
                        botao_enviar = driver.find_element(
                            By.XPATH,
                            "//button[@aria-label='Enviar mensagem' or contains(@class, 'send-button')]",
                        )
                        botao_enviar.click()
                    except Exception:
                        caixa_texto.send_keys(Keys.ENTER)

                    if ui_log:
                        ui_log(
                            f"📡 Lote [{ja_processados_contagem + 1} a "
                            f"{min(ja_processados_contagem + TAMANHO_LOTE, total_geral)}] enviado..."
                        )

                    time.sleep(6)
                    wait.until(
                        EC.element_to_be_clickable(
                            (By.XPATH, "//button[@aria-label='Enviar mensagem' or contains(@class, 'send-button')]")
                        )
                    )
                    time.sleep(1.5)

                    respostas = driver.find_elements(By.TAG_NAME, "message-content")
                    if not respostas:
                        raise RuntimeError("Sem retorno visual da IA.")

                    texto_resposta = respostas[-1].text
                    linhas_lote_computadas = 0
                    ultimo_prod_nome = "-"
                    ultimo_setor_nome = "-"

                    for linha in texto_resposta.split("\n"):
                        if "|" in linha:
                            parts = linha.split("|")
                            if len(parts) >= 2:
                                try:
                                    id_limpo = int(re.sub(r"\D", "", parts[0].strip()))
                                    setor_nome = parts[1].strip().upper()
                                    setor_valido = next((s for s in SETORES_VALIDOS if s.upper() == setor_nome), None)
                                    if setor_valido:
                                        resultados_lote[id_limpo] = setor_valido
                                        linhas_lote_computadas += 1
                                        match_df = lote_df[lote_df["temp_id"] == id_limpo]
                                        if not match_df.empty:
                                            ultimo_prod_nome = match_df.iloc[0]["descricao"]
                                            ultimo_setor_nome = setor_valido
                                except ValueError:
                                    continue

                    if linhas_lote_computadas > 0:
                        sucesso_lote = True
                        ja_processados_contagem += linhas_lote_computadas
                        total_pendentes -= linhas_lote_computadas

                        if ui_log:
                            ui_log(f"📝 Sucesso! {linhas_lote_computadas} itens consolidados.")
                        pacote_atualizacao = {
                            "processados": ja_processados_contagem,
                            "pendentes": total_pendentes,
                            "ultimo_produto": ultimo_prod_nome,
                            "ultimo_setor": ultimo_setor_nome,
                        }
                        sincronizar_com_a_nuvem(pacote_atualizacao)
                        if ui_callback:
                            ui_callback(pacote_atualizacao)
                        break
                    raise RuntimeError("A resposta retornou fora do padrão estruturado.")
                except Exception as e:
                    registrar_erro(f"Instabilidade no lote {i} (Tentativa {tentativa}): {str(e)}")
                    time.sleep(5)

            if sucesso_lote:
                lote_df = lote_df.copy()
                lote_df["SETOR_LOJA_IA"] = lote_df["temp_id"].map(resultados_lote)
                lote_df = lote_df[lote_df["SETOR_LOJA_IA"].notna()].copy()
                if not lote_df.empty:
                    df_salvar = pd.DataFrame(
                        {
                            "DESCRICAO": lote_df["descricao"],
                            "EMBALAGEM": lote_df["embalagem"],
                            "SETOR_LOJA_IA": lote_df["SETOR_LOJA_IA"],
                        }
                    )
                    df_salvar.to_csv(
                        ARQUIVO_BASE_CONHECIMENTO,
                        mode="a",
                        header=False,
                        index=False,
                        sep=";",
                        encoding="utf-8-sig",
                    )
            else:
                contador_erros += TAMANHO_LOTE
                registrar_erro(f"FALHA DEFINITIVA: O bloco iniciado no índice {i} foi pulado.")
                if ui_log:
                    ui_log("❌ Lote com problemas pulado para segurança dos dados.")
                sincronizar_com_a_nuvem({"erros": contador_erros})
                if ui_callback:
                    ui_callback({"erros": contador_erros})

        if ROBO_ATIVO:
            if ui_log:
                ui_log("🎉 Varredura completa concluída com êxito!")
            sincronizar_com_a_nuvem({"status": "Concluído"})
            if ui_callback:
                ui_callback({"status": "Concluído"})
        else:
            if ui_log:
                ui_log("⏸ Operação pausada com sucesso.")
            sincronizar_com_a_nuvem({"status": "Pausado"})
            if ui_callback:
                ui_callback({"status": "Pausado"})

    except Exception as e:
        registrar_erro(f"Erro fatal crítico: {str(e)}")
        if ui_log:
            ui_log(f"❌ Erro crítico operacional: {str(e)}")
        sincronizar_com_a_nuvem({"status": "Erro"})
        if ui_callback:
            ui_callback({"status": "Erro"})
    finally:
        driver.quit()


def parar_robo(ui_callback=None):
    global ROBO_ATIVO
    ROBO_ATIVO = False
    sincronizar_com_a_nuvem({"status": "Parando..."})
    if ui_callback:
        ui_callback({"status": "Parando..."})


# =====================================================================
# INTERFACE GRÁFICA LOCAL (CUSTOMTKINTER)
# =====================================================================
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("green")


class AppIASetorizar(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Sistema Corporativo - IA SETORIZAR")
        self.geometry("1050x730")
        self.resizable(False, False)

        self.status_var = ctk.StringVar(value="Status: Pronto")
        self.arquivo_var = ctk.StringVar(value="Arquivo: Nenhum")
        self.total_var = ctk.StringVar(value="Total: 0")
        self.processados_var = ctk.StringVar(value="Processados: 0")
        self.pendentes_var = ctk.StringVar(value="Pendentes: 0")
        self.erros_var = ctk.StringVar(value="Erros: 0")
        self.ultimo_produto_var = ctk.StringVar(value="Último Item Analisado: -")
        self.ultimo_setor_var = ctk.StringVar(value="Setor Atribuído: -")
        self.montar_layout()

    def montar_layout(self):
        titulo = ctk.CTkLabel(self, text="🤖 IA SETORIZAR", font=("Arial", 28, "bold"), text_color="#2ecc71")
        titulo.pack(pady=15)

        frame_cards = ctk.CTkFrame(self, fg_color="#1e272e", corner_radius=10)
        frame_cards.pack(fill="x", padx=25, pady=10)

        labels_config = [
            (self.status_var, "#f1c40f"),
            (self.arquivo_var, "#ffffff"),
            (self.total_var, "#3498db"),
            (self.processados_var, "#2ecc71"),
            (self.pendentes_var, "#e67e22"),
            (self.erros_var, "#e74c3c"),
        ]
        for var, cor in labels_config:
            lbl = ctk.CTkLabel(frame_cards, textvariable=var, font=("Arial", 14, "bold"), text_color=cor)
            lbl.pack(side="left", expand=True, padx=10, pady=15)

        self.barra_progresso = ctk.CTkProgressBar(self, width=980, height=15, progress_color="#2ecc71")
        self.barra_progresso.pack(pady=15)
        self.barra_progresso.set(0)

        frame_display = ctk.CTkFrame(self, fg_color="#2c3e50", corner_radius=8, height=90)
        frame_display.pack(fill="x", padx=25, pady=5)
        frame_display.pack_propagate(False)

        lbl_prod = ctk.CTkLabel(
            frame_display,
            textvariable=self.ultimo_produto_var,
            font=("Arial", 14, "bold"),
            text_color="#ecf0f1",
        )
        lbl_prod.pack(pady=(15, 2))
        lbl_setor = ctk.CTkLabel(
            frame_display,
            textvariable=self.ultimo_setor_var,
            font=("Arial", 14, "bold"),
            text_color="#2ecc71",
        )
        lbl_setor.pack(pady=2)

        lbl_log_titulo = ctk.CTkLabel(self, text="Console de Execução Local:", font=("Arial", 12, "bold"))
        lbl_log_titulo.pack(anchor="w", padx=25, pady=(15, 0))

        self.txt_log = ctk.CTkTextbox(self, width=990, height=230, font=("Consolas", 12), fg_color="#0f172a")
        self.txt_log.pack(pady=5)

        frame_botoes = ctk.CTkFrame(self, fg_color="transparent")
        frame_botoes.pack(pady=15)

        self.btn_iniciar = ctk.CTkButton(
            frame_botoes,
            text="▶ Iniciar Robô",
            font=("Arial", 13, "bold"),
            fg_color="#27ae60",
            command=self.acao_iniciar,
        )
        self.btn_iniciar.pack(side="left", padx=8)

        self.btn_parar = ctk.CTkButton(
            frame_botoes,
            text="⏸ Pausar",
            font=("Arial", 13, "bold"),
            fg_color="#c0392b",
            command=self.acao_parar,
            state="disabled",
        )
        self.btn_parar.pack(side="left", padx=8)

        btn_pasta = ctk.CTkButton(
            frame_botoes,
            text="📁 Abrir Diretório",
            font=("Arial", 13, "bold"),
            fg_color="#7f8c8d",
            command=self.acao_abrir_pasta,
        )
        btn_pasta.pack(side="left", padx=8)

    def injetar_log(self, mensagem):
        self.txt_log.insert("end", f">> {mensagem}\n")
        self.txt_log.see("end")

    def ui_callback_seguro(self, dados):
        self.after(0, lambda: self.atualizar_dados_ui(dados))

    def ui_log_seguro(self, mensagem):
        self.after(0, lambda: self.injetar_log(mensagem))

    def atualizar_dados_ui(self, dicionario_dados):
        if "status" in dicionario_dados:
            self.status_var.set(f"Status: {dicionario_dados['status']}")
        if "nome_arquivo" in dicionario_dados:
            self.arquivo_var.set(f"Arquivo: {dicionario_dados['nome_arquivo']}")
        if "total" in dicionario_dados:
            self.total_var.set(f"Total: {dicionario_dados['total']}")
        if "processados" in dicionario_dados:
            self.processados_var.set(f"Processados: {dicionario_dados['processados']}")
        if "pendentes" in dicionario_dados:
            self.pendentes_var.set(f"Pendentes: {dicionario_dados['pendentes']}")
        if "erros" in dicionario_dados:
            self.erros_var.set(f"Erros: {dicionario_dados['erros']}")
        if "ultimo_produto" in dicionario_dados:
            self.ultimo_produto_var.set(f"Último Item Analisado: {dicionario_dados['ultimo_produto']}")
        if "ultimo_setor" in dicionario_dados:
            self.ultimo_setor_var.set(f"Setor Atribuído: {dicionario_dados['ultimo_setor']}")

        try:
            tot = int(self.total_var.get().split(": ")[1])
            proc = int(self.processados_var.get().split(": ")[1])
            if tot > 0:
                self.barra_progresso.set(proc / tot)
        except (IndexError, ValueError):
            pass

        if dicionario_dados.get("status") in ["Concluído", "Finalizado", "Erro", "Pausado"]:
            self.btn_iniciar.configure(state="normal")
            self.btn_parar.configure(state="disabled")

    def acao_iniciar(self):
        self.btn_iniciar.configure(state="disabled")
        self.btn_parar.configure(state="normal")
        thread_motor = threading.Thread(
            target=classificar_e_salvar_continuo,
            args=(self.ui_callback_seguro, self.ui_log_seguro),
        )
        thread_motor.daemon = True
        thread_motor.start()

    def acao_parar(self):
        parar_robo(self.ui_callback_seguro)
        self.ui_log_seguro("🛑 Solicitando interrupção segura do robô. Sincronizando nuvem...")
        self.btn_parar.configure(state="disabled")

    def acao_abrir_pasta(self):
        if os.path.exists(PASTA_TRABALHO):
            os.startfile(PASTA_TRABALHO)


if __name__ == "__main__":
    app = AppIASetorizar()
    app.mainloop()
