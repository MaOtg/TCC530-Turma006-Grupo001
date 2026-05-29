"""
Descrição: Analisa os resultados da coleta de dados das leis, gerando um relatório 
            de auditoria com o status real do conteúdo de cada município.
"""

import os
import pandas as pd
from bs4 import BeautifulSoup

try:
    import pdfplumber
except ImportError:
    print("[Aviso] Biblioteca 'pdfplumber' não encontrada. Instale com: pip install pdfplumber")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_COLETA = os.path.join(BASE_DIR, "..", "leis_coletadas")
ARQUIVO_AUDITORIA = os.path.join(BASE_DIR, "..", "dados_processados", "auditoria_coleta_lom.csv")

def analisar_qualidade_texto(texto):

    """Aplica regras semânticas básicas para auditar a qualidade do texto capturado."""
    if not texto or len(texto.strip()) == 0:
        return "vazio"
    
    texto_lower = texto.lower()
    
    if len(texto_lower) < 1500:
        return "documento_incompleto_ou_curto"
    if "login" in texto_lower and "senha" in texto_lower:
        return "bloqueado_tela_de_login"
    if "404" in texto_lower or "not found" in texto_lower or "página não encontrada" in texto_lower:
        return "erro_http_portal"
    if "lei orgânica" not in texto_lower and "lom" not in texto_lower:
        return "texto_suspeito_outra_lei"
        
    return "coleta_validada_ok"

def extrair_texto_arquivo(caminho_completo, extensao):

    """Extrai string pura de texto dependendo do formato de arquivo coletado."""
    texto = ""
    if extensao == ".txt":
        with open(caminho_completo, "r", encoding="utf-8", errors="ignore") as f:
            texto = f.read()
    elif extensao == ".html":
        with open(caminho_completo, "r", encoding="utf-8", errors="ignore") as f:
            soup = BeautifulSoup(f, "html.parser")
            texto = soup.get_text(separator=" ")
    elif extensao == ".pdf":
        try:
            with pdfplumber.open(caminho_completo) as pdf:
                for pagina in pdf.pages:
                    t_pag = pagina.extract_text()
                    if t_pag:
                        texto += t_pag + "\n"
        except Exception as e:
            return f"Erro na leitura do PDF: {str(e)}"
    return texto

def executar_auditoria():
    print("[START] Executando Auditoria de Conteúdo Jurídico...")
    
    if not os.path.exists(PASTA_COLETA):
        print(f"Erro: Pasta de coleta '{PASTA_COLETA}' não existe.")
        return

    arquivos = os.listdir(PASTA_COLETA)
    registros_auditoria = []

    for arq in arquivos:
        caminho_completo = os.path.join(PASTA_COLETA, arq)
        if os.path.isdir(caminho_completo):
            continue

        slug, extensao = os.path.splitext(arq)
        extensao = extensao.lower()
        tamanho_kb = round(os.path.getsize(caminho_completo) / 1024, 2)
        
        print(f"Analisando integridade técnica de: {arq}")
        
        texto_extraido = extrair_texto_arquivo(caminho_completo, extensao)
        
        if texto_extraido.startswith("Erro na leitura"):
            status_auditoria = "erro_leitura_pdf"
            caracteres = 0
        else:
            status_auditoria = analisar_qualidade_texto(texto_extraido)
            caracteres = len(texto_extraido)

        registros_auditoria.append({
            "slug_municipio": slug,
            "nome_arquivo": arq,
            "formato_extensao": extensao,
            "tamanho_arquivo_kb": tamanho_kb,
            "volume_caracteres_texto": caracteres,
            "status_auditoria": status_auditoria
        })

    # Exportação do relatório consolidado
    df_auditoria = pd.DataFrame(registros_auditoria)
    os.makedirs(os.path.dirname(ARQUIVO_AUDITORIA), exist_ok=True)
    df_auditoria.to_csv(ARQUIVO_AUDITORIA, index=False, sep=";", encoding="utf-8-sig")
    
    print(f"\nAuditoria Concluída! Relatório gerado em: {ARQUIVO_AUDITORIA}")
    if not df_auditoria.empty:
        print("\nSumário da qualidade da coleta:")
        print(df_auditoria["status_auditoria"].value_counts())

if __name__ == "__main__":
    executar_auditoria()