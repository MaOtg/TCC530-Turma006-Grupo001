"""
Transição: law_quality_scoring_engine.py

Descrição:
    Este script consolida a inteligência de auditoria e validação de documentos do grupo.
    Atuando como elo entre a Fase 2 e a Fase 3, ele analisa os arquivos baixados de forma 
    automatizada (Fase 2), extrai o conteúdo de texto (tratando PDFs e HTMLs), aplica a 
    matriz de pontuação heurística para validar a integridade jurídica e separa o dataset 
    em duas frentes:
        1. leis_filtradas/ -> Municípios com sucesso (prontos para análise de similaridade).
        2. cidades_para_mineracao.csv -> Lista de municípios que falharam na Fase 2 
           e que servirão de entrada obrigatória para a Fase 3 (Mineração de E-mails).
"""

import os
import shutil
from collections import defaultdict
import pandas as pd
import pdfplumber
from bs4 import BeautifulSoup

# Configuração de caminhos relativos para portabilidade absoluta no Git
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PASTA_ORIGEM = os.path.abspath(os.path.join(BASE_DIR, "..", "leis_coletadas"))
PASTA_FINAL = os.path.abspath(os.path.join(BASE_DIR, "..", "leis_filtradas"))
ARQUIVO_FALTANTES = os.path.abspath(os.path.join(BASE_DIR, "..", "dados_processados", "cidades_para_mineracao.csv"))
ARQUIVO_LOG_GERAL = os.path.abspath(os.path.join(BASE_DIR, "..", "dados_processados", "auditoria_inspecao_geral.csv"))

os.makedirs(PASTA_FINAL, exist_ok=True)
os.makedirs(os.path.dirname(ARQUIVO_FALTANTES), exist_ok=True)

def extrair_texto_documento(caminho_completo, nome_arquivo):
    """
    Realiza a extração de texto bruto baseada na extensão do arquivo coletado,
    conforme lógica original de verificação do grupo.
    """
    texto = ""
    try:
        if nome_arquivo.lower().endswith(".pdf"):
            with pdfplumber.open(caminho_completo) as pdf:
                for pagina in pdf.pages:
                    conteudo_pagina = pagina.extract_text()
                    if conteudo_pagina:
                        texto += conteudo_pagina + "\n"
                        
        elif nome_arquivo.lower().endswith(".html"):
            with open(caminho_completo, "r", encoding="utf-8", errors="ignore") as f:
                soup = BeautifulSoup(f, "html.parser")
                texto = soup.get_text(separator=" ")
                
        return texto
    except:
        return None

def analisar_status_texto(texto):
    """
    Valida o conteúdo textual e categoriza o status do arquivo.
    """
    if not texto or texto.strip() == "":
        return "erro_conteudo_vazio"

    texto_lower = texto.lower()

    if len(texto_lower) < 500:
        return "muito_curto"

    if "login" in texto_lower:
        return "pagina_login"

    if "erro" in texto_lower:
        return "pagina_erro"

    if "lei orgânica" not in texto_lower:
        return "texto_suspeito"

    return "ok"

def avaliar_heuristica_score(caminho_arquivo):
    """
    Aplica a lógica de pesos heurísticos desenvolvida pelo grupo,
    inspecionando o cabeçalho binário do arquivo para mitigar emendas parciais.
    """
    try:
        with open(caminho_arquivo, "rb") as f:
            cabecalho = f.read(10000)
            
        texto_cabecalho = cabecalho.decode("latin-1", errors="ignore").lower()
        score = 0

        # Atribuidores Positivos
        if "lei orgânica do município" in texto_cabecalho:
            score += 10
        if "câmara municipal" in texto_cabecalho:
            score += 3
        if "prefeitura" in texto_cabecalho:
            score += 2

        # Penalizadores Negativos
        if "emenda" in texto_cabecalho:
            score -= 10
        if "alteração" in texto_cabecalho or "altera" in texto_cabecalho:
            score -= 10

        return score
    except:
        return -999

def executar_scoring_engine():
    print("==========================================================")
    print("EXECUÇÃO DO MOTOR DE SCORE - AUDITORIA E TRIAGEM DA COLETA")
    print("==========================================================")
    
    if not os.path.exists(PASTA_ORIGEM):
        print(f"Erro Crítico: A pasta de origem da Fase 2 '{PASTA_ORIGEM}' não existe.")
        return

    arquivos = os.listdir(PASTA_ORIGEM)
    grupos_municipios = defaultdict(list)
    historico_completo = []

    # Agrupa múltiplos arquivos por município através do nome base (slug)
    for arq in arquivos:
        caminho_completo = os.path.join(PASTA_ORIGEM, arq)
        if os.path.isdir(caminho_completo):
            continue
        slug_municipio = arq.split(".")[0]
        grupos_municipios[slug_municipio].append(caminho_completo)

    cidades_sucesso = 0
    cidades_falhas = 0
    lista_municipios_para_recoleta = []

    print(f"Analisando downloads de {len(grupos_municipios)} municípios...")

    for municipio, caminhos in grupos_municipios.items():
        melhor_score = -999
        melhor_caminho = None
        status_validacao_final = "erro"
        volume_caracteres = 0

        # Avalia os arquivos disponíveis para o município
        for caminho in caminhos:
            nome_arq = os.path.basename(caminho)
            texto_extraido = extrair_texto_documento(caminho, nome_arq)
            status_texto = analisar_status_texto(texto_extraido)
            score_heuristico = avaliar_heuristica_score(caminho)

            # O arquivo é elegível como Lei Orgânica se o status for OK e o score heurístico for favorável
            if status_texto == "ok" and score_heuristico >= 2:
                if score_heuristico > melhor_score:
                    melhor_score = score_heuristico
                    melhor_caminho = caminho
                    status_validacao_final = "VALIDADO_OK"
                    volume_caracteres = len(texto_extraido) if texto_extraido else 0
            else:
                # Se falhou e nenhum arquivo anterior foi validado como OK, registra o motivo da falha
                if status_validacao_final != "VALIDADO_OK":
                    status_validacao_final = f"FALHA_{status_texto.upper()}"
                    mejor_caminho = caminho
                    melhor_score = score_heuristico
                    volume_caracteres = len(texto_extraido) if texto_extraido else 0

        # Tomada de decisão com base nos testes consolidados do grupo
        if status_validacao_final == "VALIDADO_OK" and melhor_caminho:
            cidades_sucesso += 1
            nome_arquivo_final = os.path.basename(melhor_caminho)
            destino_final = os.path.join(PASTA_FINAL, nome_arquivo_final)
            shutil.copy2(melhor_caminho, destino_final)
            
            historico_completo.append({
                "municipio_slug": municipio,
                "status_auditoria": "VALIDADO_OK",
                "score_atribuido": melhor_score,
                "tamanho_texto_caracteres": volume_caracteres,
                "arquivo_eleito": nome_arquivo_final
            })
        else:
            cidades_falhas += 1
            lista_municipios_para_recoleta.append({"municipio_slug": municipio})
            
            historico_completo.append({
                "municipio_slug": municipio,
                "status_auditoria": status_validacao_final,
                "score_atribuido": melhor_score,
                "tamanho_texto_caracteres": volume_caracteres,
                "arquivo_eleito": os.path.basename(melhor_caminho) if melhor_caminho else "Nenhum"
            })

    # Exportação do log geral de auditoria para documentação metodológica do TCC
    df_log = pd.DataFrame(historico_completo)
    df_log.to_csv(ARQUIVO_LOG_GERAL, index=False, sep=";", encoding="utf-8-sig")

    # Exportação da lista de corte com as cidades pendentes para a mineração de e-mails
    df_faltantes = pd.DataFrame(lista_municipios_para_recoleta)
    df_faltantes.to_csv(ARQUIVO_FALTANTES, index=False, sep=";", encoding="utf-8-sig")

    print("\n" + "="*50)
    print("RELATÓRIO CONSOLIDADO DA AUDITORIA (TRIAGEM)")
    print("="*50)
    print(f"Leis Orgânicas Válidas (Sucesso Fase 2):       {cidades_sucesso}")
    print(f"Arquivos Rejeitados (Direcionados à Fase 3):   {cidades_falhas}")
    print(f"Destino da Base Limpa:                         {PASTA_FINAL}")
    print(f"Lista gerada para Início da Fase 3 (CSV):      {ARQUIVO_FALTANTES}")
    print("==========================================================")

if __name__ == "__main__":
    executar_scoring_engine()