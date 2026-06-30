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
    
    # --- CORREÇÃO DO 9º DÍGITO (BRASIL) ---
    if to_number.startswith("55") and len(to_number) == 12:
        to_number = to_number[:4] + "9" + to_number[4:]
        print(f"DEBUG: Número corrigido para envio: {to_number}")
    # --------------------------------------
    
    url_meta = f"https://graph.facebook.com/v18.0/{PHONE_NUMBER_ID}/messages"
    headers = {"Authorization": f"Bearer {META_TOKEN}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_number,
        "text": {"body": texto}
    }
    
    print(f"DEBUG: Tentando enviar mensagem para {to_number}...")
    try:
        response = requests.post(url_meta, headers=headers, json=payload, timeout=10)
        print(f"DEBUG: Resposta da Meta (Status {response.status_code}): {response.text}")
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
        
        print(f"DEBUG: Processando mensagem de {remetente}")
        
        user_check = supabase.table("usuarios").select("*").eq("telefone", remetente).eq("ativo", True).execute()
        
        if not user_check.data:
            print(f"ERRO: Usuário {remetente} não encontrado ou inativo no Supabase.")
            return jsonify({"status": "unauthorized"}), 200
            
        tmb_usuario = user_check.data[0].get("tmb", 1905)
        
        # --- ATUALIZAÇÃO DE TMB (META) ---
        if texto_usuario_lower.startswith("!meta ") or texto_usuario_lower.startswith("meta "):
            try:
                nova_tmb = int(texto_usuario_lower.split(" ")[1])
                supabase.table("usuarios").update({"tmb": nova_tmb}).eq("telefone", remetente).execute()
                enviar_mensagem_whatsapp(remetente, f"🎯 Sua nova meta diária foi atualizada para {nova_tmb} kcal!")
                return jsonify({"status": "success"}), 200
            except ValueError:
                enviar_mensagem_whatsapp(remetente, "⚠️ Formato inválido. Use: *meta 2000* (substituindo pelo valor desejado).")
                return jsonify({"status": "success"}), 200
        # ----------------------------------------
        
        # --- INTERCEPTAÇÃO DO COMANDO EXTRATO ---
        comandos_extrato = ["extrato", "resumo", "diario", "diário"]
        if texto_usuario_lower in comandos_extrato:
            agora_local = datetime.now(LOCAL_TZ)
            inicio_dia = agora_local.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
            
            logs = supabase.table("logs_consumo").select("*").eq("user_id", remetente).gte("created_at", inicio_dia).order("created_at").execute()
            
            if not logs.data:
                enviar_mensagem_whatsapp(remetente, "📭 Seu extrato de hoje está vazio. Mande a primeira refeição!")
                return jsonify({"status": "success"}), 200
                
            linhas_extrato = ["📊 *Extrato do Dia*\n"]
            for log in logs.data:
                # Tratamento de horário para o fuso local
                try:
                    hora_utc = datetime.fromisoformat(log['created_at'].replace('Z', '+00:00'))
                    hora_str = hora_utc.astimezone(LOCAL_TZ).strftime('%H:%M')
                except:
                    hora_str = "--:--"
                
                sinal = "+" if log['calorias'] > 0 else ""
                linhas_extrato.append(f"• {hora_str} - {log['alimento']} ({sinal}{log['calorias']} kcal)")
                
            mensagem_extrato = "\n".join(linhas_extrato)
            enviar_mensagem_whatsapp(remetente, mensagem_extrato)
            return jsonify({"status": "success"}), 200
        # ----------------------------------------

        # Se não for extrato, processa a refeição/treino via IA
        model = genai.GenerativeModel('gemini-2.5-flash', system_instruction=SYSTEM_PROMPT, generation_config={"response_mime_type": "application/json"})
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
        
        # Busca todos os macros do dia para somar
        logs = supabase.table("logs_consumo").select("calorias, proteinas, carboidratos, gorduras").eq("user_id", remetente).gte("created_at", inicio_dia).execute()
        
        total_kcal = sum(int(item.get('calorias', 0)) for item in logs.data)
        total_p = sum(int(item.get('proteinas', 0)) for item in logs.data)
        total_c = sum(int(item.get('carboidratos', 0)) for item in logs.data)
        total_g = sum(int(item.get('gorduras', 0)) for item in logs.data)
        
        meta_diaria = int(tmb_usuario)
        restam = meta_diaria - total_kcal
        
        # Tom neutro e controle de saldo negativo
        if restam >= 0:
            msg_saldo = f"restam {restam} kcal"
        else:
            msg_saldo = f"você passou do saldo do dia em {abs(restam)} kcal"

        # Adiciona um ícone diferente se for exercício (calorias negativas)
        icone = "🏃" if macros.get('calorias', 0) < 0 else "✅"

        msg = (
            f"{icone} {dados.get('refeicao', 'Registro')} ({macros.get('calorias', 0)} kcal) salvo.\n"
            f"Saldo do dia: {total_kcal}/{meta_diaria} kcal — {msg_saldo}.\n"
            f"P: {total_p}g | C: {total_c}g | G: {total_g}g.\n\n"
            f"💡 Digite \"extrato\" para ver o dia completo."
        )

        enviar_mensagem_whatsapp(remetente, msg)
        
    except Exception as e:
        print(f"ERRO CRÍTICO NO PROCESSAMENTO: {e}")
        enviar_mensagem_whatsapp(remetente, f"⚠️ Erro do sistema: {str(e)[:100]}")
        
    return jsonify({"status": "success"}), 200
