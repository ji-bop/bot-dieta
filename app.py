import os
from flask import Flask, request, jsonify

app = Flask(__name__)

# Rota de teste para ver se o bot está "acordado"
@app.route('/', methods=['GET'])
def home():
    return "Bot de Dieta Online e rodando!"

# Rota principal (Webhook) onde o WhatsApp vai bater
@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    # O WhatsApp exige uma verificação na hora de conectar
    if request.method == 'GET':
        challenge = request.args.get('hub.challenge')
        return str(challenge)

    # Aqui é onde receberemos a mensagem do usuário depois de conectados
    if request.method == 'POST':
        dados = request.get_json()
        print("Mensagem recebida:", dados)
        return jsonify({"status": "sucesso"}), 200

if __name__ == "__main__":
    # Puxa a porta dinâmica do Render ou usa 5000 localmente
    porta = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=porta)