"""
Descrição:
    Este script realiza a coleta da população dos municípios paulistas via API do IBGE,
    filtra as 100 maiores cidades, gera identificadores únicos (slugs), deduz as URLs 
    institucionais das Câmaras Municipais e realiza uma varredura de profundidade (scraping)
    para identificar previamente o link direto ou a página da Lei Orgânica (LOM).
"""

import os
import re
import time
import unicodedata
import urllib3
import pandas as pd
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin

# Desabilita avisos de certificados SSL (comum em portais legislativos antigos)
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# =============================================================================
# FUNÇÕES DE LIMPEZA E TRATAMENTO TEXTUAL
# =============================================================================

def limpar_nome_municipio(txt):
    """Remove o sufixo do estado e padroniza o espaçamento do nome."""
    txt = txt.replace(" - SP", "")
    return txt.strip()


def normalizar_para_busca(txt):
    """Remove acentuações e padroniza em minúsculas para testes de string."""
    nome_limpo = limpar_nome_municipio(txt)
    return unicodedata.normalize('NFKD', nome_limpo).encode('ASCII', 'ignore').decode('ASCII').lower().strip()


def slugify(texto):
    """Cria um identificador padrão (slug) para nomenclatura de arquivos."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("utf-8")
    texto = texto.replace(" ", "-")
    return texto

# =============================================================================
# HEURÍSTICAS DE MAPEAMENTO E SCRAPING DE PORTAIS
# =============================================================================

def testar_dominios_escala(municipio, session):
    """
    Testa combinações conhecidas de URLs de Câmaras Municipais baseadas no nome.
    Retorna a primeira URL que responder com Status Code 200.
    """
    nome_base = normalizar_para_busca(municipio)
    slug_colado = nome_base.replace(" ", "")
    
    # Mapeamento de exceções específicas do estado de SP
    excecoes = {
        "sao bernardo do campo": "sbc",
        "santo andre": "sandre",
        "sao jose do rio preto": "riopreto",
        "mogi das cruzes": "mc",  
        "sao jose dos campos": "sjc",
        "campinas": "campinas",
        "itaquaquecetuba": "itaquaquecetuba",
        "praia grande": "pg",
        "sao vicente": "saovicente",
        "sorocaba": "sorocaba",
        "guarulhos": "guarulhos"
    }
    
    sigla = excecoes.get(nome_base, slug_colado)
    
    padroes = [
        f"https://www.cm{sigla}.com.br",
        f"https://www.{sigla}.sp.leg.br",
        f"https://www.camara{sigla}.sp.gov.br",
        f"https://www.cm{sigla}.sp.gov.br",
        f"https://{sigla}.sp.leg.br",
        f"https://camara{slug_colado}.sp.leg.br",
        f"https://www.camara{slug_colado}.sp.leg.br"
    ]
    
    for url in padroes:
        try:
            r = session.get(url, timeout=5, verify=False, allow_redirects=True)
            if r.status_code == 200:
                return url
        except:
            continue
    return "Não encontrado"


def extrair_lei_organica_robusto(url_portal, session):
    """
    Acessa a home do portal validado, varre os links internos usando expressões
    regulares e retorna o link direto mais provável para a Lei Orgânica.
    """
    if not url_portal or url_portal == "Não encontrado":
        return ""
    
    try:
        response = session.get(url_portal, timeout=10, verify=False, allow_redirects=True)
        url_base_real = response.url 
        soup = BeautifulSoup(response.text, 'html.parser')
        
        links_potenciais = []
        padrao_busca = re.compile(r'lei\s+org|lom|legislacao\s+mun', re.IGNORECASE)
        
        for a in soup.find_all('a', href=True):
            texto = a.get_text().strip()
            title = a.get('title', '')
            href = a['href']
            
            if padrao_busca.search(texto) or padrao_busca.search(title) or padrao_busca.search(href):
                link_completo = urljoin(url_base_real, href)
                
                # Se encontrar o arquivo direto (.pdf, .docx, .html), prioriza e retorna imediatamente
                if any(ext in link_completo.lower() for ext in ['.pdf', '.docx', '.html']):
                    return link_completo
                
                links_potenciais.append(link_completo)
        
        # Se não achou arquivo direto, retorna a URL mais curta (geralmente a página de Legislação)
        if links_potenciais:
            return sorted(links_potenciais, key=len)[0]
            
        return "Necessita busca manual"
        
    except Exception as e:
        return f"Erro de conexao: {str(e)[:20]}"

# =============================================================================
# FLUXO PRINCIPAL DE EXECUÇÃO
# =============================================================================

def main():
    print("==================================================")
    print("INICIANDO FASE 1: COLETA E HIGIENIZAÇÃO BASE")
    print("==================================================")

    # Etapa 1: Consumo de dados populacionais (IBGE)
    print("\nBuscando dados populacionais do IBGE (Censo 2022)...")
    url_pop = "https://servicodados.ibge.gov.br/api/v3/agregados/4714/periodos/2022/variaveis/93?localidades=N6[N3[35]]"
    
    try:
        response = requests.get(url_pop, timeout=15)
        response.raise_for_status()
        data = response.json()
        
        series = data[0]['resultados'][0]['series']
        df_pop = pd.DataFrame([
            {
                'municipio': item['localidade']['nome'], 
                'populacao': int(item['serie']['2022'])
            } 
            for item in series
        ])
        
        # Filtra as 100 maiores cidades
        top_100 = df_pop.nlargest(100, 'populacao').reset_index(drop=True)
        print(f"Sucesso: Dados de {len(top_100)} cidades carregados do IBGE.")
    except Exception as e:
        print(f"Erro crítico ao acessar API do IBGE: {e}")
        return

    # Etapa 2: Configuração da Sessão HTTP unificada
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36'
    })

    # Etapa 3: Varredura de Portais e Links da Lei Orgânica
    print("\nIniciando mapeamento de portais e links de profundidade...")
    
    portais_mapeados = []
    links_documentos = []
    
    # Processa linha por linha de forma limpa e sequencial
    for idx, row in top_100.iterrows():
        municipio = row['municipio']
        print(f" Processando [{idx + 1}/100]: {limpar_nome_municipio(municipio)}")
        
        # Descobre a URL inicial da Câmara
        url_portal = testar_dominios_escala(municipio, session)
        portais_mapeados.append(url_portal)
        
        # Varre a home da Câmara em busca da Lei Orgânica
        link_lom = extrair_lei_organica_robusto(url_portal, session)
        links_documentos.append(link_lom)
        
        time.sleep(0.4) # Intervalo seguro contra bloqueios de servidores (Rate Limit)

    # Etapa 4: Construção, Higienização e Engenharia de Atributos do DataFrame
    print("\nTratando colunas e gerando chaves textuais (slugs)...")
    df_export = top_100.copy()
    
    df_export['site_oficial'] = portais_mapeados
    df_export['link_documento_lom'] = links_documentos
    
    # Padronização final das strings de municípios e criação dos slugs identificadores
    df_export['municipio'] = df_export['municipio'].apply(limpar_nome_municipio)
    df_export['slug'] = df_export['municipio'].apply(slugify)
    
    # Construção de colunas de controle estruturadas
    df_export['encontrou_portal'] = df_export['site_oficial'].apply(lambda x: 'Sim' if x != "Não encontrado" else 'Não')
    df_export['portal_validado'] = df_export['site_oficial'].apply(lambda x: x if x != "Não encontrado" else "")

    # Seleção de colunas final organizada de acordo com os requisitos do projeto
    df_final = df_export[['municipio', 'slug', 'populacao', 'encontrou_portal', 'portal_validado', 'link_documento_lom']]

    # Etapa 5: Salvamento do Dataset Final Higienizado
    pasta_saida = "../dados_processados"
    os.makedirs(pasta_saida, exist_ok=True)
    arquivo_saida = os.path.join(pasta_saida, "municipios_limpos.csv")
    
    df_final.to_csv(arquivo_saida, index=False, encoding='utf-8-sig', sep=';')

    # Métricas para relatório interno
    portais_ativos = len(df_final[df_final['encontrou_portal'] == 'Sim'])
    
    print("\n" + "="*50)
    print("RELATÓRIO FINAL DA FASE 1")
    print("="*50)
    print(f"Local de destino:      {arquivo_saida}")
    print(f"Total de Municipios:   {len(df_final)}")
    print(f"Portais Identificados: {portais_ativos}")
    print("==================================================")


if __name__ == "__main__":
    main()