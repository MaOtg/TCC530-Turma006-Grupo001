"""
Descrição: Baixa os documentos das leis orgânicas (prioritariamente PDFs). 
            Utiliza busca externa (DDGS) e download resiliente baseado em cookies/requests.
"""

import os
import time
import requests
import pandas as pd
from ddgs import DDGS
from bs4 import BeautifulSoup
from selenium import webdriver

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_ENTRADA = os.path.join(BASE_DIR, "..", "dados_processados", "municipios_limpos.csv")
PASTA_SAIDA = os.path.join(BASE_DIR, "..", "leis_coletadas")

os.makedirs(PASTA_SAIDA, exist_ok=True)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
}

def pdf_parece_valido(conteudo_bytes):

    """Validação prévia dos primeiros bytes do arquivo para mitigar emendas/alterações parciais."""
    try:
        texto_inicial = conteudo_bytes[:6000].decode("latin-1", errors="ignore").lower()
        if any(termo in texto_inicial for termo in ["emenda", "alteração constitucional", "altera a lei"]):
            return False
        return True
    except:
        return True

def buscar_url_externa(municipio, portal=None):

    """Consulta engines externos procurando pelo PDF oficial da Lei Orgânica."""
    queries = [
        f'"lei orgânica do município de {municipio}" pdf',
        f"lei orgânica {municipio} site:{portal}" if portal else None,
        f"{municipio} lei organica camara municipal"
    ]
    queries = [q for q in queries if q]

    try:
        with DDGS() as ddgs:
            for q in queries:
                resultados = ddgs.text(q, max_results=4)
                for r in resultados:
                    url = r["href"].lower()

                    # Filtro de domínios institucionais confiáveis
                    if any(dom in url for dom in [".gov.br", "leg.br", ".sp.gov.br", "camara"]):
                        return r["href"]
    except Exception as e:
        print(f"    [!] Erro na API do DDGS: {e}")
    return None

def baixar_com_sessao_hibrida(url_alvo, slug_municipio):

    """Inicia navegador para passar por firewalls/captchas, herda cookies e faz download via requests."""
    print("  🔑 Iniciando modo híbrido para transpor restrições de segurança...")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(options=options)
    
    try:
        driver.get(url_alvo)
        time.sleep(4) # Janela para carregamento/autenticação institucional básica
        
        # Intercepta cookies gerados pelo navegador
        cookies_selenium = driver.get_cookies()
        session_cookies = {c['name']: c['value'] for c in cookies_selenium}
        
        # Executa download de alta performance em background
        response = requests.get(url_alvo, cookies=session_cookies, headers=HEADERS, timeout=25)
        
        if response.status_code == 200 and "pdf" in response.headers.get("Content-Type", "").lower():
            if pdf_parece_valido(response.content):
                caminho = os.path.join(PASTA_SAIDA, f"{slug_municipio}.pdf")
                with open(caminho, "wb") as f:
                    f.write(response.content)
                print(f"[DOWNLOAD OK] PDF salvo em: {caminho}")
                return True
    except Exception as e:
        print(f"Erro no download híbrido: {e}")
    finally:
        driver.quit()
    return False

def executar_downloader():
    print("[START] Iniciando o Coletor e Downloader de PDFs...")
    if not os.path.exists(CSV_ENTRADA):
        print(f"Erro: CSV de entrada não localizado em {CSV_ENTRADA}")
        return

    df = pd.read_csv(CSV_ENTRADA, sep=";")
    
    for idx, row in df.iterrows():
        municipio = row["municipio"]
        slug = row["slug"]
        portal = row.get("portal_validado", None)
        
        if os.path.exists(os.path.join(PASTA_SAIDA, f"{slug}.pdf")) or os.path.exists(os.path.join(PASTA_SAIDA, f"{slug}.txt")):
            continue

        print(f"\nBuscando fontes de download para: {municipio}")
        url_documento = buscar_url_externa(municipio, portal)

        if url_documento:
            print(f"Link em potencial identificado: {url_documento}")

            # Tenta o download direto padrão
            try:
                res = requests.get(url_documento, headers=HEADERS, timeout=15)
                if res.status_code == 200 and "pdf" in res.headers.get("Content-Type", "").lower():
                    if pdf_parece_valido(res.content):
                        with open(os.path.join(PASTA_SAIDA, f"{slug}.pdf"), "wb") as f:
                            f.write(res.content)
                        print(f"[DOWNLOAD OK] PDF obtido via requisição direta.")
                        time.sleep(3)
                        continue
            except:
                pass
            
            # Se a requisição direta falhar ou exigir validação de sessão, aciona o modo Híbrido
            baixar_com_sessao_hibrida(url_documento, slug)
        else:
            print(f"Nenhum link de download confiável localizado para {municipio}.")
            
        time.sleep(3)

if __name__ == "__main__":
    executar_downloader()