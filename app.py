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

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
genai.configure(api_key=GEMINI_API_KEY)
LOCAL_TZ = pytz.timezone('America/Campo_Grande')

SYSTEM_PROMPT = """Você é um nutricionista especialista. Retorne EXATAMENTE um objeto JSON válido (sem markdown).
Formato: {"refeicao": "...", "itens": [...], "macros": {"calorias": 0, "proteinas": 0, "carboidratos": 0, "gorduras": 0, "fibras": 0}}"""

def enviar_mensagem_whatsapp(to_number, texto):
    url_meta = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    payload = {"messaging_product": "whatsapp", "to": to_number, "text": {"body": texto}}
    try:
        requests.post(url_meta, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"Erro ao conectar com a API da Meta: {e}")

@app.route('/webhook', methods=['GET'])
def verify():
    if request.args.get("hub.verify_token") == VERIFY_TOKEN:
        return request.args.get("hub.challenge")
    return "Falha na verificação", 403



@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.json
    try:
        if 'messages' not in data['entry'][0]['changes'][0]['value']:
            return jsonify({"status": "ignored"}), 200
        
        msg_info = data['entry'][0]['changes'][0]['value']['messages'][0]
        remetente = msg_info['from']
        texto_usuario = msg_info['text']['body']
        
        # DEBUG: Imprime para vermos se ele acha o usuário
        print(f"DEBUG: Processando mensagem de {remetente}")
        
        user_check = supabase.table("usuarios").select("*").eq("telefone", remetente).eq("ativo", True).execute()
        
        if not user_check.data:
            print(f"ERRO: Usuário {remetente} não encontrado ou inativo no Supabase.")
            return jsonify({"status": "unauthorized"}), 200
            
        tmb_usuario = user_check.data[0].get("tmb", 1905)

        model = genai.GenerativeModel('gemini-1.5-flash-latest', system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
        resposta_ia = model.generate_content(texto_usuario)
        dados = json.loads(resposta_ia.text)
        macros = dados['macros']

        supabase.table("logs_consumo").insert({
            "user_id": remetente,
            "alimento": ", ".join(dados['itens']),
            "calorias": macros.get('calorias', 0),
            "proteinas": macros.get('proteinas', 0),
            "carboidratos": macros.get('carboidratos', 0),
            "gorduras": macros.get('gorduras', 0)
        }).execute()

        agora_local = datetime.now(LOCAL_TZ)
        inicio_dia = agora_local.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        logs = supabase.table("logs_consumo").select("calorias").eq("user_id", remetente).gte("created_at", inicio_dia).execute()
        
        total_kcal = sum(int(item['calorias']) for item in logs.data)
        deficit = total_kcal - int(tmb_usuario)

        msg = (f"🍽️ *{dados.get('refeicao', 'Refeição')}*\n{', '.join(dados['itens'])}\n\n"
               f"🔥 *{macros.get('calorias', 0)} kcal* (P:{macros.get('proteinas', 0)} C:{macros.get('carboidratos', 0)} G:{macros.get('gorduras', 0)})\n"
               f"🎯 *Total hoje:* {total_kcal} kcal (Déficit: {deficit})")

        enviar_mensagem_whatsapp(remetente, msg)
        
    except Exception as e:
        print(f"ERRO CRÍTICO NO PROCESSAMENTO: {e}")
        # AGORA O BOT VAI TE AVISAR NO WHATSAPP SE DER ERRO
        enviar_mensagem_whatsapp(remetente, f"⚠️ Erro do sistema: {str(e)[:100]}")
        
    return jsonify({"status": "success"}), 200
