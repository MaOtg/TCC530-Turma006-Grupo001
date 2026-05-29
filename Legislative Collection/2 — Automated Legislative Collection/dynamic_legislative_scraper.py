"""
Descrição: Realiza a varredura dinâmica e interativa nos portais municipais (Câmaras/Prefeituras)
            utilizando Selenium para interagir com menus, iframes e JS.
"""

import os
import time
import re
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager  # type: ignore
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configuração de caminhos base relativos para portabilidade
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_ENTRADA = os.path.join(BASE_DIR, "..", "dados_processados", "municipios_limpos.csv") # Ajuste se necessário
PASTA_SAIDA = os.path.join(BASE_DIR, "..", "leis_coletadas")

os.makedirs(PASTA_SAIDA, exist_ok=True)

def configurar_driver():
    chrome_options = Options()

    # Desative o headless caso precise debugar visualmente
    chrome_options.add_argument("--headless") 
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
    
    servico = Service(ChromeDriverManager().install())
    return webdriver.Chrome(service=servico, options=chrome_options)

def clicar_com_espera(driver, texto_link):

    """Tenta clicar em um link esperando ele ficar disponível no DOM."""
    try:
        elemento = WebDriverWait(driver, 8).until(
            EC.element_to_be_clickable((By.PARTIAL_LINK_TEXT, texto_link))
        )
        print(f"    [Ação] Clicando em: '{texto_link}'")
        elemento.click()
        time.sleep(4)
        return True
    except:
        return False

def extrair_texto_com_iframe(driver):

    """Varre a página e frames internos procurando indícios de artigos jurídicos."""
    # Testa se o texto está no contexto principal
    texto_principal = driver.find_element(By.TAG_NAME, "body").text
    if "ART." in texto_principal.upper() or "ARTIGO 1" in texto_principal.upper():
        return texto_principal
        
    # Se não achou, investiga Iframes ativos na página
    iframes = driver.find_elements(By.TAG_NAME, "iframe")
    for frame in iframes:
        try:
            driver.switch_to.frame(frame)
            texto_frame = driver.find_element(By.TAG_NAME, "body").text
            if "ART." in texto_frame.upper() or "ARTIGO 1" in texto_frame.upper():
                return texto_frame
        except:
            pass
        finally:
            driver.switch_to.default_content()
            
    return None

def executar_scraper_dinamico():
    print("[START] Iniciando Varredura Dinâmica nos Portais (Selenium)...")
    
    if not os.path.exists(CSV_ENTRADA):
        print(f"Erro: Arquivo de entrada não encontrado em {CSV_ENTRADA}")
        return

    df = pd.read_csv(CSV_ENTRADA, sep=";")
    driver = configurar_driver()

    for idx, row in df.iterrows():
        municipio = row["municipio"]
        slug = row["slug"]
        
        # Define as URLs prioritárias para buscar (Câmara e depois Prefeitura)
        urls_alvo = []
        if "endereco_camara" in df.columns and pd.notna(row["endereco_camara"]):
            urls_alvo.append(("CÂMARA", str(row["endereco_camara"]).strip()))
        if "portal_validado" in df.columns and pd.notna(row["portal_validado"]):
            urls_alvo.append(("PREFEITURA", str(row["portal_validado"]).strip()))

        # Pula se o arquivo final higienizado ou estruturado já existir
        caminho_saida_html = os.path.join(PASTA_SAIDA, f"{slug}.html")
        caminho_saida_txt = os.path.join(PASTA_SAIDA, f"{slug}.txt")
        if os.path.exists(caminho_saida_html) or os.path.exists(caminho_saida_txt):
            print(f"[-] {municipio} já possui coleta local. Pulando...")
            continue

        print(f"\nDesafio Técnico: {municipio}")
        sucesso_municipio = False

        for tipo, url in urls_alvo:
            if not url.startswith("http"):
                url = "http://" + url

            print(f"Tentando {tipo}: {url}")
            try:
                driver.get(url)
                time.sleep(3)

                # Fluxo de cliques baseado em palavras-chave conhecidas
                if not clicar_com_espera(driver, "Lei Orgânica"):
                    if not clicar_com_espera(driver, "Legislação"):
                        clicar_com_espera(driver, "Atividade Legislativa")

                # Captura e validação do conteúdo textual
                texto_lei = extrair_texto_com_iframe(driver)
                
                if texto_lei and len(texto_lei) > 4000:
                    with open(caminho_saida_txt, "w", encoding="utf-8") as f:
                        f.write(texto_lei)
                    print(f"[SUCESSO] Texto da lei extraído via portal da {tipo}!")
                    sucesso_municipio = True
                    break
                else:
                    print(f"Conteúdo insuficiente ou menu vazio na URL da {tipo}.")

            except Exception as e:
                print(f"Falha ao processar URL da {tipo}: {str(e)[:50]}")
            finally:
                driver.switch_to.default_content()

        if not sucesso_municipio:
            print(f"Não foi possível extrair texto dinamicamente para {municipio}.")

    driver.quit()
    print("\nFim da execução do Scraper Dinâmico.")

if __name__ == "__main__":
    executar_scraper_dinamico()