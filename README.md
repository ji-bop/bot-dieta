# 🍏 NutriBot - Assistente de Dieta via WhatsApp

Um chatbot integrado ao WhatsApp para registro prático de refeições e treinos. O sistema utiliza Inteligência Artificial para extrair calorias e macronutrientes de mensagens em texto livre e mantém o controle do saldo calórico diário do usuário.

## 🚀 Funcionalidades

* **Processamento de Linguagem Natural:** Relate refeições de forma natural (ex: "Comi 2 ovos e um pão") e a IA extrai os dados nutricionais.
* **Cálculo de Déficit Calórico:** O bot subtrai as calorias consumidas da Taxa Metabólica Basal (TMB) dinâmica do usuário.
* **Registro de Exercícios:** Suporte a gasto calórico (ex: "Corri 5km") com dedução automática do saldo diário.
* **Extrato Diário:** Comando rápido (`extrato`, `resumo`, `diário`) para visualizar todas as refeições do dia via WhatsApp.
* **Atualização de Meta:** Comando rápido (`!meta 2000`) para o usuário alterar a própria TMB em tempo real.

## 🛠️ Tecnologias Utilizadas

* **Backend:** Python / Flask
* **Banco de Dados:** Supabase (PostgreSQL)
* **Inteligência Artificial:** Google Gemini (gemini-2.5-flash)
* **Mensageria:** Meta Cloud API (WhatsApp Business)
* **Deploy:** Render (Web Service via Gunicorn)

## ⚙️ Configuração e Instalação

Para rodar este projeto localmente ou em produção, você precisará configurar as seguintes Variáveis de Ambiente (`.env`):

| Variável | Descrição |
| :--- | :--- |
| `SUPABASE_URL` | URL do seu projeto no Supabase. |
| `SUPABASE_KEY` | Chave de serviço (Service Role) ou Anon Key do Supabase. |
| `META_TOKEN` | Token de Acesso Permanente do Usuário do Sistema na Meta. |
| `VERIFY_TOKEN` | Token de verificação de Webhook criado por você (ex: `meu_token_secreto`). |
| `PHONE_NUMBER_ID` | ID do número de telefone registrado na Meta. |
| `GEMINI_API_KEY` | Chave de API do Google AI Studio. |

## 🗄️ Estrutura do Banco de Dados (Supabase)

O sistema exige duas tabelas principais:

1. **usuarios**: `id`, `telefone` (string, +55...), `tmb` (int, valor padrão recomendado: 1905), `ativo` (boolean).
2. **logs_consumo**: `id`, `user_id` (referência ao telefone), `alimento` (text), `calorias` (int), `proteinas` (int), `carboidratos` (int), `gorduras` (int), `created_at` (timestamp).

*Nota: É necessário desativar o RLS ou configurar as Policies corretas para permitir operações de `INSERT` e `UPDATE` via API.*

## 🔒 Privacidade

Os dados de consumo são cruzados estritamente com o número de telefone remetente cadastrado. Usuários não autorizados (sem cadastro prévio na tabela `usuarios`) são bloqueados no primeiro contato.
