"""
Descrição:
    Motor de disparo automatizado de e-mails institucionais. Consome os dados
    higienizados pelo minerador e realiza as conexões SMTP seguras para envio
    dos pedidos oficiais de acesso às Leis Orgânicas em falta.
"""

import os
import time
import smtplib
import pandas as pd
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.header import Header

# Definição de caminhos e parametrizações SMTP originais do grupo
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CSV_ENTRADA_EMAILS = os.path.abspath(os.path.join(BASE_DIR, "..", "dados_processados", "cidades_com_emails_refinado_final.csv"))

# =========================================================================
# CONFIGURAÇÃO DE CREDENCIAIS (Preencher antes de executar o script)
# =========================================================================
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587

# SUBSTITUA AS STRINGS ABAIXO PELOS SEUS DADOS DE ACESSO:
EMAIL_REMETENTE = "INSIRA_AQUI_SEU_EMAIL@gmail.com"
SENHA_REMETENTE = "INSIRA_AQUI_SUA_SENHA_DE_APPLICATIVO"
# =========================================================================

CORPO_EMAIL_TEMPLATE = """Prezados representantes do município de {nome_cidade},

Boa tarde.

Meu nome é Fábio, sou aluno da Univesp (Universidade Virtual do Estado de São Paulo) e estou desenvolvendo meu Trabalho de Conclusão de Curso (TCC) no curso de Ciência de Dados.

O objetivo do projeto é realizar uma análise de similaridade textual e identificação de inconsistências em leis orgânicas municipais. Como os portais eletrônicos locais apresentaram instabilidade técnica ou formatos não processáveis pelos nossos algoritmos, solicitamos respeitosamente o envio do arquivo em formato texto (.pdf original, .doc ou .txt) contendo a Lei Orgânica do Município de {nome_cidade} atualizada.

Ressaltamos que os arquivos podem ser encaminhados em anexo (em resposta a este e-mails).

Esta pesquisa tem fins estritamente acadêmicos.

Atenciosamente,

Fábio Rodrigues
Curso de Ciência de Dados - Univesp"""

def executar_despachante_emails():
    print("Iniciando o envio controlado de e-mails institucionais via SMTP...")

    # Validação de segurança para garantir que o usuário alterou os placeholders padrão
    if "INSIRA_AQUI" in EMAIL_REMETENTE or "INSIRA_AQUI" in SENHA_REMETENTE:
        print("\n[!] Erro Crítico: Você precisa configurar seu e-mail e senha nas variáveis EMAIL_REMETENTE e SENHA_REMETENTE antes de rodar o script.")
        return

    if not os.path.exists(CSV_ENTRADA_EMAILS):
        print(f"Erro: Ficheiro de contactos '{CSV_ENTRADA_EMAILS}' nao localizado.")
        return

    df_contatos = pd.read_csv(CSV_ENTRADA_EMAILS, sep=";", encoding="utf-8-sig")

    for index, row in df_contatos.iterrows():
        cidade = row["cidade"]
        destinatarios = row["emails_identificados_limpos"]

        if pd.isna(destinatarios) or str(destinatarios).strip() == "":
            print(f"Municipio {cidade} ignorado: Sem emails validos cadastrados.")
            continue

        print(f"Enviando para {cidade} -> Destinatario(s): {destinatarios}")

        try:
            msg = MIMEMultipart()
            msg["From"] = f"Pesquisa Acadêmica Univesp <{EMAIL_REMETENTE}>"
            msg["To"] = destinatarios
            msg["Subject"] = Header(f"Solicitação de Informações: Lei Orgânica de {cidade}", "utf-8")

            # Cabeçalhos originais de confirmação solicitados pelo grupo
            msg["Disposition-Notification-To"] = EMAIL_REMETENTE
            msg["Return-Receipt-To"] = EMAIL_REMETENTE

            corpo_mensagem = CORPO_EMAIL_TEMPLATE.format(nome_cidade=cidade)
            msg.attach(MIMEText(corpo_mensagem, "plain", "utf-8"))

            # Inicialização do canal de comunicação SMTP seguro
            server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
            server.starttls()
            server.login(EMAIL_REMETENTE, SENHA_REMETENTE)

            # Conversão da string de e-mails em lista aceitável pelo SMTP
            lista_destinatarios = [e.strip() for e in destinatarios.split(",")]
            server.sendmail(EMAIL_REMETENTE, lista_destinatarios, msg.as_string())
            server.quit()

            print(f"    E-mail enviado com sucesso para {cidade}.")
            
            # Intervalo de segurança anti-spam/throttling entre envios
            time.sleep(5)

        except Exception as e:
            print(f"    Erro critico no envio para {cidade}: {e}")

    print("Pipeline de disparos da Phase 3 finalizado.")

if __name__ == "__main__":
    executar_despachante_emails()