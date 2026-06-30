import os
from datetime import datetime, timedelta
import pytz
from supabase import create_client, Client

# --- CONFIGURAÇÕES ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # Recomendado usar a Service Role Key para deleções

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ Erro: Variáveis de ambiente do Supabase não encontradas.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
LOCAL_TZ = pytz.timezone('America/Campo_Grande')

def faxina_mensal():
    agora_local = datetime.now(LOCAL_TZ)
    # Define o limite de retenção (30 dias)
    data_limite = (agora_local - timedelta(days=30)).isoformat()
    
    print(f"[{agora_local.strftime('%Y-%m-%d %H:%M:%S')}] Iniciando faxina de dados...")
    print(f"⏰ Removendo registros anteriores a: {data_limite}")
    
    try:
        # Executa a deleção em lote no banco de dados
        resultado = supabase.table("logs_consumo").delete().lt("created_at", data_limite).execute()
        
        registros_removidos = len(resultado.data) if resultado.data else 0
        print(f"✅ Concluído! {registros_removidos} logs antigos foram permanentemente deletados.")
        
    except Exception as e:
        print(f"❌ Erro crítico durante a execução: {e}")

if __name__ == "__main__":
    faxina_mensal()