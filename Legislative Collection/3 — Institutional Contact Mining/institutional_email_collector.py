"""
Descrição:
    Realiza a mineração automatizada de endereços de e-mail institucionais das Câmaras
    e Prefeituras que falharam na fase de download automático. Inclui navegação proativa
    em subpáginas de contacto e aplicação de filtros de refino estrutural e semântico.
"""

import os
import re
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager # type: ignore
from selenium.webdriver.common.by import By

# Caminhos relativos padrão do repositório
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_ENTRADA_MUNICIPIOS = os.path.abspath(os.path.join(BASE_DIR, "..", "dados_processados", "municipios_limpos.csv"))
CSV_CIDADES_FALTANTES = os.path.abspath(os.path.join(BASE_DIR, "..", "dados_processados", "cidades_para_mineracao.csv"))
CSV_SAIDA_CONTATOS = os.path.abspath(os.path.join(BASE_DIR, "..", "dados_processados", "cidades_com_emails_refinado_final.csv"))

def configurar_driver():
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    servico = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=servico, options=chrome_options)

def email_eh_valido(email):
    """
    Filtro do grupo para descartar lixo técnico, bibliotecas de código e extensões.
    """
    if not email or "@" not in email:
        return False
        
    blacklist = [
        "fontawesome", "select2", "datatables", "jquery", "bootstrap", 
        "sentry", "w3.org", "example", "format", "rc.", "min.js", 
        "v1.", "v2.", "v4.", "v5.", "node_modules", "github", "npm"
    ]
    
    email_lower = email.lower().strip()
    if any(termo in email_lower for termo in blacklist):
        return False
        
    if re.search(r"\.(js|css|png|jpg|jpeg|gif|pdf|zip)$", email_lower):
        return False
        
    return True

def refinar_emails_institucionais(lista_emails):
    """
    Aplica a regra de negócio de relevância do grupo, priorizando termos nobres
    e removendo e-mails de departamentos puramente técnicos.
    """
    if not lista_emails:
        return ""

    emails = [e.strip().lower().strip(".") for e in lista_emails]
    emails = list(set([e for e in emails if len(e) > 5 and email_eh_valido(e)]))

    termos_nobres = [
        "ouvidoria", "contato", "prefeitura", "imprensa", "presidencia", 
        "administracao", "falecom", "faleconosco", "camara", "atendimento",
        "comunicacao", "gabinete", "secretaria", "geral", "portal"
    ]
    termos_exclusao = ["geoprocessamento", "ti", "suporte", "tecnico", "manutencao", "desenvolvimento"]

    institucionais = []
    for email in emails:
        usuario = email.split("@")[0]
        if any(termo in usuario for termo in termos_nobres):
            if not any(exc in usuario for exc in termos_exclusao):
                institucionais.append(email)

    # Fallback: se não houver e-mails com termos nobres, mantém o primeiro e-mail limpo encontrado
    if not institucionais and emails:
        primeiro = emails[0]
        if not any(exc in primeiro for exc in termos_exclusao):
            institucionais.append(primeiro)

    return ", ".join(institucionais)

def extrair_emails_texto(texto):
    padrao = r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
    return re.findall(padrao, texto)

def executar_minerador_emails():
    print("Iniciando processo de mineracao de emails institucionais...")
    
    if not os.path.exists(CSV_CIDADES_FALTANTES) or not os.path.exists(CSV_ENTRADA_MUNICIPIOS):
        print("Erro: Ficheiros de entrada nao localizados.")
        return

    # Carrega os alvos mapeados que necessitam de contacto humano
    df_faltantes = pd.read_csv(CSV_CIDADES_FALTANTES, sep=";", encoding="utf-8-sig")
    df_municipios = pd.read_csv(CSV_ENTRADA_MUNICIPIOS, sep=";", encoding="utf-8-sig")
    
    # Faz o merge para recuperar as URLs originais da câmara e prefeitura
    df_alvos = df_municipios[df_municipios["slug"].isin(df_faltantes["municipio_slug"])].copy()

    driver = configurar_driver()
    resultados_finais = []

    for index, row in df_alvos.iterrows():
        cidade = row["municipio"]
        emails_acumulados = []
        
        print(f"Processando municipio: {cidade}")
        
        for col_url in ["endereco_camara", "endereco_prefeitura"]:
            url = row.get(col_url, "")
            if pd.isna(url) or str(url).strip() == "":
                continue
                
            if not str(url).startswith("http"):
                url = "http://" + str(url)
                
            try:
                driver.get(url)
                time.sleep(3)
                
                # Coleta inicial na Home Page
                emails_home = extrair_emails_texto(driver.page_source)
                emails_acumulados.extend(emails_home)
                
                # Tentativa de navegacao baseada em cliques estruturais caso necessario
                for termo_clique in ["Contato", "Fale Conosco", "Ouvidoria", "SIC"]:
                    try:
                        elemento_link = driver.find_element(By.PARTIAL_LINK_TEXT, termo_clique)
                        elemento_link.click()
                        time.sleep(3)
                        emails_acumulados.extend(extrair_emails_texto(driver.page_source))
                        driver.back()
                        time.sleep(2)
                    except:
                        continue
            except Exception as e:
                print(f"    Erro ao acessar URL {url}: {str(e)[:40]}")

        # Executa as regras de higienizacao e filtragem semantica do grupo
        lista_bruta = [e.lower() for e in emails_acumulados]
        emails_refinados = refinar_emails_institucionais(lista_bruta)
        
        print(f"    Resultado limpo: {emails_refinados if emails_refinados else 'Nenhum encontrado'}")
        
        resultados_finais.append({
            "cidade": cidade,
            "slug": row["slug"],
            "emails_identificados_limpos": emails_refinados
        })

    driver.quit()

    # Exporta o dataset final polido pronto para os disparos SMTP
    df_saida = pd.DataFrame(resultados_finais)
    os.makedirs(os.path.dirname(CSV_SAIDA_CONTATOS), exist_ok=True)
    df_saida.to_csv(CSV_SAIDA_CONTATOS, index=False, sep=";", encoding="utf-8-sig")
    print(f"Processo concluido. Ficheiro salvo em: {CSV_SAIDA_CONTATOS}")

if __name__ == "__main__":
    executar_minerador_emails()