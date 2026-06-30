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

SYSTEM_PROMPT = """Você é um nutricionista especialista. 
Se o usuário relatar uma refeição, calcule as calorias e macros positivos.
Se o usuário relatar um EXERCÍCIO FÍSICO (ex: 'corri 5km', 'musculação'), coloque a refeição como 'Treino', macros zerados, e as calorias devem ser NEGATIVAS (ex: -300).
Retorne EXATAMENTE um objeto JSON válido (sem markdown).
Formato: {"refeicao": "...", "itens": [...], "macros": {"calorias": 0, "proteinas": 0, "carboidratos": 0, "gorduras": 0, "fibras": 0}}"""

def enviar_mensagem_whatsapp(to_number, texto):
    """Função auxiliar para envio de mensagens via API da Meta"""
    if to_number.startswith("55") and len(to_number) == 12:
        to_number = to_number[:4] + "9" + to_number[4:]
    
    url_meta = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "text": {"body": texto}
    }
    
    try:
        requests.post(url_meta, headers=headers, json=payload, timeout=10)
    except Exception as e:
        print(f"ERRO CRÍTICO NO ENVIO: {e}")

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
        texto_usuario_lower = texto_usuario.lower().strip()
        
        user_check = supabase.table("usuarios").select("*").eq("telefone", remetente).eq("ativo", True).execute()
        
        if not user_check.data:
            return jsonify({"status": "unauthorized"}), 200
            
        # Proteção contra NoneType na TMB
        tmb_usuario = user_check.data[0].get("tmb") or 1905
        
        # --- ATUALIZAÇÃO DE TMB (META) ---
        if texto_usuario_lower.startswith("!meta ") or texto_usuario_lower.startswith("meta "):
            try:
                partes = texto_usuario_lower.split(" ")
                nova_tmb = int(partes