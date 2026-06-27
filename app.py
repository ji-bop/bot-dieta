import os
import json
import requests
from datetime import datetime
import pytz
from flask import Flask, request, jsonify
from supabase import create_client, Client
import google.generativeai as genai

app = Flask(__name__)

@app.route('/', methods=['GET'])
def ping():
    return "Bot online!", 200

# --- CONFIGURAÇÕES E CHAVES ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")
META_TOKEN = os.environ.get("META_TOKEN")
VERIFY_TOKEN = os.environ.get("VERIFY_TOKEN")
PHONE_NUMBER_ID = os.environ.get("PHONE_NUMBER_ID")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

# Inicializa Supabase e Gemini
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)

# --- FUSO HORÁRIO LOCAL ---
# Define o fuso horário correto (UTC-4) para evitar resets no horário de Londres
LOCAL_TZ = pytz.timezone('America/Campo_Grande')

# --- PROMPT DO GEMINI ---
SYSTEM_PROMPT = """Você é um nutricionista especialista e um extrator de dados de saúde estruturados.
Sua única função é ler uma lista de alimentos informada pelo usuário, calcular os macronutrientes totais estimados (baseado em tabelas como TACO ou USDA) e retornar EXATAMENTE um objeto JSON válido.
Não inclua nenhuma palavra ou formatação (como ```json) antes ou depois do JSON.

Regras:
1. Se a quantidade não for dita, assuma uma porção padrão de bom senso (ex: 1 unidade média, 1 colher de sopa, 1 copo de 200ml).
2. Todos os valores numéricos em "macros" devem ser inteiros.

Formato obrigatório de saída:
{
  "refeicao": "Inferir pelo tipo de comida (ex: Café da Manhã, Almoço, Lanche, Jantar)",
  "itens": ["lista", "detalhada", "dos", "alimentos", "interpretados"],
  "macros": {
    "calorias": 0,
    "proteinas": 0,
    "carboidratos": 0,
    "gorduras": 0,
    "fibras": 0
  }
}"""

def enviar_mensagem_whatsapp(to_number, texto):
    """Função auxiliar para envio de mensagens via API da Meta"""
    url_meta = f"[https://graph.facebook.com/v18.0/](https://graph.facebook.com/v18.0/){PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "text": {"body": texto}
    }
    try:
        requests.post(url_meta, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao conectar com a API da Meta: {e}")

# --- ROTA DE VERIFICAÇÃO DA META (GET) ---
@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Falha na verificação", 403

# --- ROTA DE RECEBIMENTO DE MENSAGENS (POST) ---
@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    
    # Validação estrutural básica da mensagem recebida
    try:
        if 'messages' not in data['entry'][0]['changes'][0]['value']:
            return jsonify({"status": "ignored"}), 200
        
        msg_info = data['entry'][0]['changes'][0]['value']['messages'][0]
        remetente = msg_info['from']
        
        if 'text' not in msg_info:
            return jsonify({"status": "ignored"}), 200
            
        texto_usuario = msg_info['text']['body']
    except Exception:
        return jsonify({"status": "invalid_structure"}), 200

    try:
        # 1. SEGURANÇA E TMB DINÂMICA: Busca dados do usuário ativo
        user_check = supabase.table("usuarios").select("*").eq("telefone", remetente).eq("ativo", True).execute()
        if not user_check.data:
            return jsonify({"status": "unauthorized"}), 200
            
        usuario = user_check.data[0]
        tmb_usuario = usuario.get("tmb", 1905) # Puxa o valor da coluna nova (fallback 1905 se estiver nulo)

        # 2. INTELIGÊNCIA: Gemini configurado para responder nativamente em JSON
        model = genai.GenerativeModel(
            'gemini-2.5-flash', 
            system_instruction=SYSTEM_PROMPT,
            generation_config={"response_mime_type": "application/json"}
        )
        resposta_ia = model.generate_content(texto_usuario)
        dados_refeicao = json.loads(resposta_ia.text)
        macros = dados_refeicao['macros']

        # 3. BANCO DE DADOS: Salva o log da refeição
        nova_refeicao = {
            "user_id": remetente,
            "alimento": ", ".join(dados_refeicao['itens']),
            "calorias": macros.get('calorias', 0),
            "proteinas": macros.get('proteinas', 0),
            "carboidratos": macros.get('carboidratos', 0),
            "gorduras": macros.get('gorduras', 0)
        }
        supabase.table("logs_consumo").insert(nova_refeicao).execute()

        # 4. MATEMÁTICA COM FUSO HORÁRIO: Define início do dia no fuso local com offset correto
        agora_local = datetime.now(LOCAL_TZ)
        inicio_dia_iso = agora_local.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        
        # Filtra os logs a partir da meia-noite do fuso local
        logs_hoje = supabase.table("logs_consumo").select("calorias").eq("user_id", remetente).gte("created_at", inicio_dia_iso).execute()
        
        total_kcal = sum(int(item['calorias']) for item in logs_hoje.data)
        deficit = total_kcal - int(tmb_usuario)

        # 5. RESPOSTA FORMATADA E ENVIO
        mensagem_final = (
            f"🍽️ *{dados_refeicao.get('refeicao', 'Refeição')}*\n"
            f"Registrado: {nova_refeicao['alimento']}\n\n"
            f"*{macros.get('calorias', 0)} kcal* ({macros.get('proteinas', 0)}g P | {macros.get('carboidratos', 0)}g C | {macros.get('gorduras', 0)}g G)\n"
            f"------------------------\n"
            f"🎯 *Total hoje:* {total_kcal} kcal\n"
            f"⚖️ *Déficit:* {total_kcal} - {int(tmb_usuario)} = *{deficit} kcal*"
        )

        resposta = model.generate_content(prompt)
        dados_ia = json.loads(resposta.text.strip())
        
        # --- ADICIONE ESTA LINHA: ---
        print(f"DADOS BRUTOS DA IA: {dados_ia}")
        
        enviar_mensagem_whatsapp(remetente, mensagem_final)

    except Exception as e:
        print(f"Erro crítico no processamento: {e}")
        # Envio de feedback ao usuário em vez de quebrar em silêncio
        enviar_mensagem_whatsapp(remetente, "⚠️ Desculpe, ocorreu um erro interno ao processar ou salvar sua refeição. Por favor, tente novamente em instantes.")

    return jsonify({"status": "success"}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
