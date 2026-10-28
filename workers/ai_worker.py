import sys
import os
import json
import logging
import requests
import time
import random
from datetime import datetime

# Add project root to path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from services.stream_client import StreamClient
from database.db_client import DBClient
from config.config import Config
from services.telegram_sender import TelegramSender
from database.repositories.message_repo import MessageRepository
from database.repositories.conversation_repo import ConversationRepository

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AIWorker")

# LAYER 1: THE BRAIN (Gemma) - Focuses on Intent, Strategy, and Psychological Adaptation
THINKER_SYSTEM_PROMPT = """
Eres el Cerebro Estratégico de un Asesor Consultivo experto en pensiones del IMSS (Instituto Mexicano del Seguro Social) en MÉXICO.
Trabajas para JPM (Jubilación y Pensión Máxima), un despacho de consultoría privado e independiente. NO eres el patrón ni el empleador del cliente, eres su asesor.
Tu trabajo es ANALIZAR la situación, leer al cliente y definir la estrategia, NO redactar el mensaje final.

🎯 OBJETIVOS Y REGLA DE ORO:
- Todo el contexto legal corresponde a las leyes de MÉXICO exclusivamente.
- Tu meta es entender la situación, generar confianza y detectar si podemos ayudar.
- Tu trabajo NO es vender, es guiar al cliente a una decisión informada.
- No operes como call center. Escucha, entiende, interpreta, explica y guía.

🧠 LECTURA DEL CLIENTE Y ADAPTACIÓN:
Analiza el mensaje y determina el estado del cliente:
- Desconfiado: Sugiere bajar velocidad, aumentar claridad y evitar afirmaciones fuertes.
- Confundido o Desinformado: Sugiere explicaciones simples, directas y EDUCATIVAS usando la base de conocimientos. NUNCA respondas con otra pregunta sin antes haber explicado lo que se te preguntó.
- Analítico: Sugiere un orden lógico, paso a paso.
- Resistente: Sugiere no confrontar, reencuadrar suavemente.

📚 BASE DE CONOCIMIENTOS (JPM Y PENSIONES IMSS MÉXICO):
- LECTURA DE NSS (Número de Seguridad Social): El NSS tiene 11 dígitos. Los dígitos 3 y 4 indican el AÑO DE ALTA al IMSS. Los dígitos 5 y 6 indican el AÑO DE NACIMIENTO.
  * Ejemplo: Si el NSS es "110791XXXXX", los dígitos 3 y 4 son "07" (año 2007) y los 5 y 6 son "91" (año 1991).
  * ACCIÓN OBLIGATORIA: Cuando te den un NSS, INMEDIATAMENTE revélale al cliente su año de alta, su año de nacimiento aproximado, y el Régimen de Ley al que pertenece.
  * LEY 73 vs LEY 97: Si el año de alta (dígitos 3 y 4) es 96 o menor (ej. 85, 92, 96), es LEY 73. Si es 97, 98, 99 o de los 2000s (ej. 00, 07, 15), es LEY 97 (Afore).
  * ESTIMADO DE SEMANAS: Menciónale de forma casual un cálculo rápido. Ej: "Como empezaste en el año X, llevas un máximo de Y años trabajando. Eso significa que si no hubieras dejado de trabajar nunca, tendrías un tope aproximado de Z semanas cotizadas (Y multiplicado por 52 semanas)".
- Ley 73 (Seguro Social de México): Aplica a quienes comenzaron a cotizar en el IMSS en México antes del 1 de julio de 1997.
  * Requisitos (Art. 145 y 182): Tener al menos 60 años cumplidos, mínimo 500 semanas cotizadas reconocidas por el IMSS, y estar dado de baja del régimen obligatorio.
  * Beneficios: Pensión vitalicia calculada según salario promedio de los últimos 5 años y semanas cotizadas. Incluye aguinaldo anual, asistencia médica y asignaciones familiares.
  * Porcentaje por edad (Art. 171): 60 años = 75%, 61 = 80%, 62 = 85%, 63 = 90%, 64 = 95%, 65 = 100%.
- Modalidad 40: Estrategia legal en México para hacer aportaciones voluntarias al IMSS y aumentar el salario promedio y semanas cotizadas, logrando una pensión mucho más alta bajo la Ley 73.
- Servicios JPM: Somos un despacho de asesores privados. Brindamos Asesoría Integral, Proyecciones de Pensión, Estrategias de Maximización (usando Modalidad 40) y Gestión de trámites ante el IMSS.

🧩 LÓGICA CONVERSACIONAL Y FASE DE ASESORÍA (PERFILAMIENTO):
- Prioridad de Perfilamiento: Tu objetivo principal durante la charla es recabar los 4 datos clave del cliente: 1) Edad, 2) Semanas cotizadas, 3) Fecha o año de alta al IMSS, 4) Cotización o salario actual. NO pidas todos de golpe, intégralos naturalmente en la plática.
- Lenguaje: Usa siempre un lenguaje claro, empático y altamente profesional.
- Si preguntan qué es algo: DA LA RESPUESTA clara y resumida usando la base de conocimientos. NUNCA evadas. Tras responder, cierra con una pregunta orientada a conseguir un dato del perfilamiento.
- Manejo de objeciones: Si no confía (validar+explicar), si no hay dinero (explorar sin presionar), si pregunta cuánto ganará (explicar que requiere análisis del perfilamiento).

🛑 GUARDRAILS:
- NUNCA: Prometer resultados, asegurar montos exactos, presionar emocionalmente.
- SIEMPRE: Pensar en posibilidades y mantener transparencia.

🧩 LÓGICA DE SALIDA:
Genera un análisis breve y una "Intención de Respuesta" clara para que la Voz (Capa 2) la redacte.
Ejemplo de tu salida:
[ESTADO]: Confundido / Desconfiado
[ESTRATEGIA]: Validar preocupación y explicar que depende del caso sin prometer montos. Toma el control consultivo.
[INTENCIÓN]: "Explícale que hay varios escenarios y pregúntale si ya había revisado algo antes o va empezando."
"""

# LAYER 2: THE VOICE (Qwen) - Focuses on Format, Humanization, and Scannability
EDITOR_SYSTEM_PROMPT = """
Eres la Voz de Samanta, Asesora Consultiva de JPM. Tu trabajo es HUMANIZAR el pensamiento técnico recibido.

🎭 IDENTIDAD Y COMPORTAMIENTO:
- Cercana, segura (sin ser arrogante), paciente y clara.
- No eres un vendedor agresivo ni operadora de call center.
- Eres humana: no das respuestas perfectas, ajustas sobre la marcha, no suenas ensayada.

{dynamic_rules}

📲 FORMATO Y RITMO:
- Máximo 1 idea principal por mensaje.
- Máximo 1 pregunta por turno para avanzar suavemente.
- Saltos de línea naturales (fáciles de leer en WhatsApp/Chat).
- Permite que el usuario "hable" (escribe corto y espera su respuesta).

🛑 REGLA DE ORO:
- NO vendas ni presiones. Traduce lo complejo a simple y genera confianza genuina.
"""

def call_llm(model, system_prompt, user_prompt, temperature=0.3):
    """Unified LLM wrapper. Routes dynamically to OpenAI, Gemini API, or Ollama."""
    provider = Config.get_active_provider()
    if provider == "openai":
        return call_llm_openai(system_prompt, user_prompt, temperature)
    elif provider == "gemini":
        return call_llm_gemini(system_prompt, user_prompt, temperature)
    else:
        return call_llm_ollama(model, system_prompt, user_prompt, temperature)

def call_llm_openai(system_prompt, user_prompt, temperature=0.3):
    """Llama a la API de OpenAI (chat/completions) vía REST."""
    if not Config.OPENAI_API_KEY:
        logger.error("OPENAI_API_KEY not set. Falling back to Ollama.")
        return call_llm_ollama(Config.OLLAMA_MODEL, system_prompt, user_prompt, temperature)

    base_url = (Config.OPENAI_BASE_URL or "https://api.openai.com/v1").rstrip('/')
    url = f"{base_url}/chat/completions"
    headers = {
        "Authorization": f"Bearer {Config.OPENAI_API_KEY}",
        "Content-Type": "application/json"
    }
    messages = []
    if system_prompt:
        messages.append({"role": "system", "content": system_prompt})
    messages.append({"role": "user", "content": user_prompt})

    payload = {
        "model": Config.OPENAI_MODEL or "gpt-4o-mini",
        "messages": messages,
        "temperature": temperature
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("choices", [{}])[0].get("message", {}).get("content", "").strip()
        else:
            logger.error(f"OpenAI API Error {resp.status_code}: {resp.text}. Falling back to Ollama.")
            return call_llm_ollama(Config.OLLAMA_MODEL, system_prompt, user_prompt, temperature)
    except Exception as e:
        logger.error(f"Failed to connect to OpenAI API: {e}. Falling back to Ollama.")
        return call_llm_ollama(Config.OLLAMA_MODEL, system_prompt, user_prompt, temperature)

def call_llm_gemini(system_prompt, user_prompt, temperature=0.3):
    """Llama a la API de Google Gemini vía REST."""
    if not Config.GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY not set. Falling back to Ollama.")
        return call_llm_ollama(Config.OLLAMA_MODEL, system_prompt, user_prompt, temperature)
        
    gemini_base = (Config.GEMINI_BASE_URL or "https://generativelanguage.googleapis.com/v1beta").rstrip('/')
    model_name = Config.GEMINI_MODEL or "gemini-2.5-flash"
    url = f"{gemini_base}/models/{model_name}:generateContent?key={Config.GEMINI_API_KEY}"
    payload = {
        "system_instruction": {"parts": [{"text": system_prompt}]},
        "contents": [{"parts":[{"text": user_prompt}]}],
        "generationConfig": {"temperature": temperature}
    }
    try:
        resp = requests.post(url, json=payload, timeout=30)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("candidates", [{}])[0].get("content", {}).get("parts", [{}])[0].get("text", "")
        else:
            logger.error(f"Gemini API Error {resp.status_code}: {resp.text}. Falling back to Ollama.")
            return call_llm_ollama(Config.OLLAMA_MODEL, system_prompt, user_prompt, temperature)
    except Exception as e:
        logger.error(f"Failed to connect to Gemini API: {e}. Falling back to Ollama.")
        return call_llm_ollama(Config.OLLAMA_MODEL, system_prompt, user_prompt, temperature)

def call_llm_ollama(model, system_prompt, user_prompt, temperature=0.3):
    try:
        resp = requests.post(
            Config.OLLAMA_URL,
            json={
                "model": model, 
                "system": system_prompt,
                "prompt": user_prompt,
                "stream": False,
                "options": {"temperature": temperature}
            },
            timeout=120
        )
        return resp.json().get("response", "")
    except Exception as e:
        logger.error(f"Failed to connect to Ollama: {e}")
        return ""

def run():
    client = StreamClient()
    pg_db = DBClient()
    mongo_msg_repo = MessageRepository()
    mongo_conv_repo = ConversationRepository()
    
    stream_in = "message.processed"
    stream_out = "message.outbound"
    group_name = "ai-agent-group"
    consumer_name = "worker-1"
    
    # Use id="$" to only process NEW messages from now on
    try:
        client.redis.xgroup_create(stream_in, group_name, id="$", mkstream=True)
    except:
        pass # Group already exists
    
    logger.info(f"AI Agent Worker started (JPM Asesor Mode). Monitoring {stream_in}...")
    
    while True:
        results = client.read_group({stream_in: ">"}, group_name, consumer_name)
        if not results:
            continue
            
        for stream_name, msgs in results:
            for msg_id, data in msgs:
                try:
                    payload = json.loads(data["payload"])
                    
                    # Only respond to inbound messages from users
                    if payload.get("direction") != "inbound" or payload.get("actor_type") != "user":
                        client.ack(stream_in, group_name, msg_id)
                        continue

                    # 1. Get History for context
                    # Aumentamos el límite de 5 a 20 mensajes para evitar amnesia en el perfilamiento.
                    # La ventana de contexto de Gemini o modelos locales soporta esto sin problemas.
                    history = pg_db.get_history(payload["conversation_id"], limit=20)
                    context = ""
                    for h in reversed(history):
                        direction = h.get("direction")
                        content = h.get("content", {})
                        role = "Usuario" if direction == "inbound" else "Samanta"
                        text = content.get("body", "")
                        context += f"{role}: {text}\n"
                    
                    current_msg = payload.get("content", {}).get("body", "")

                    # --- DETERMINE IF FIRST REPLY ---
                    is_first_reply = "Samanta:" not in context

                    if is_first_reply:
                        logger.info(f"Primer contacto detectado para {payload['conversation_id']}. Usando respuesta predefinida.")
                        final_resp = "¡Hola! 👋 Soy OctyBot, el asistente virtual de Recursos Humanos en Octopy (octopy.com). ¿En qué puedo apoyarte con tu postulación laboral?"
                    else:
                        # --- LAYER 1: THE BRAIN (Gemma) ---
                        system_thinker = THINKER_SYSTEM_PROMPT
                        prompt_thinker = f"Historial:\n{context}\nUsuario: {current_msg}\n\nAnálisis y Estrategia:"
                        
                        logger.info(f"L1 (Thinker) processing JPM Strategy for {payload['conversation_id']}...")
                        thinker_resp = call_llm(Config.OLLAMA_MODEL, system_thinker, prompt_thinker, temperature=0.3)

                        # --- LAYER 2: THE VOICE (Qwen) ---
                        dynamic_rules = """
🗣️ ESTILO DE VOZ (FLUJO NATURAL):
- PROHIBIDO presentarte de nuevo o repetir tu nombre y empresa. Continúa la plática directamente.
- PROHIBIDO usar lenguaje de call center o preguntar en qué puedes ayudar. Usa un tono directo y casual.
- Respuestas de 1 a 3 bloques cortos (textos breves para chat).
- Lenguaje natural, sin tecnicismos innecesarios.
- Usa conectores conversacionales variados para sonar natural, SIN abusar de ninguna muletilla en particular (ej. "A ver...", "Te explico rápido...", "Más sencillo...", "Depende del caso..."). NUNCA inicies tus frases con "Mira...".
- Usa emojis de forma natural y esporádica (ej. 🙌, 🤔, 👀), como lo haría una persona en chat. No exageres, mantén la cercanía.
- NUNCA uses "Echo:", "Asistente:" o listas enormes.
"""
                        
                        dynamic_editor_prompt = EDITOR_SYSTEM_PROMPT.replace("{dynamic_rules}", dynamic_rules)
                        editor_user_prompt = f"[PENSAMIENTO ESTRATÉGICO]:\n{thinker_resp}\n\n[MENSAJE DEL USUARIO]: {current_msg}\n\n[RESPUESTA HUMANA DE SAMANTA]:"

                        logger.info(f"L2 (Editor) rendering human response...")
                        model_editor = os.getenv("OLLAMA_MODEL_EDITOR", Config.OLLAMA_MODEL)
                        final_resp = call_llm(model_editor, dynamic_editor_prompt, editor_user_prompt, temperature=0.4).strip()

                    # --- GUARDRAILS (Lógica de seguridad básica) ---
                    if "prometo" in final_resp.lower() or "aseguro" in final_resp.lower():
                        final_resp = final_resp.replace("prometo", "es probable").replace("aseguro", "podría ser")

                    if final_resp:
                        # --- SIMULACIÓN DE TECLEO HUMANO ---
                        if Config.ENABLE_TYPING_DELAY:
                            # Calculamos un delay basado en la longitud de la respuesta (~15 chars/sec) + pausa aleatoria
                            typing_delay = len(final_resp) / 15.0 + random.uniform(1.0, 3.0)
                            typing_delay = min(typing_delay, 10.0) # Topamos a max 10s para no bloquear la cola demasiado
                            logger.info(f"Simulando tecleo humano por {typing_delay:.2f} segundos...")
                            time.sleep(typing_delay)
                        else:
                            logger.info("Simulación de tecleo deshabilitada (.env)")

                        # --- DUAL-WRITE START ---
                        mongo_conv = mongo_conv_repo.upsert_from_inbound(payload["channel"], payload["actor_id"], final_resp)
                        client_id = f"ai_{int(time.time())}"
                        
                        mongo_msg_repo.save({
                            "client_id": client_id,
                            "conversation_id": mongo_conv["_id"],
                            "direction": "outbound",
                            "sender_type": "ai_agent",
                            "status": "pending",
                            "type": "text",
                            "content": {"normalized": {"text": final_resp}},
                            "channel": payload["channel"],
                            "timestamp": datetime.utcnow()
                        })

                        try:
                            from services.imo_schema import IMOv2
                            pg_conv_id, _, _ = pg_db.upsert_conversation(payload["channel"], payload["actor_id"])
                            imo = IMOv2(
                                channel=payload["channel"],
                                direction="outbound",
                                actor_type="ai_agent",
                                actor_id="samanta",
                                content={"type": "text", "body": final_resp},
                                conversation_id=pg_conv_id
                            )
                            pg_db.insert_message(imo)
                        except Exception as e:
                            logger.error(f"Error dual-writing AI response to Postgres: {e}")

                        # 3. Create Outbound Message for Dispatcher
                        outbound = {
                            "client_id": client_id,
                            "channel": payload["channel"],
                            "to": payload["actor_id"],
                            "text": final_resp,
                            "origin": "ai_agent"
                        }
                        client.push(stream_out, outbound)
                        logger.info(f"AI Final Response saved and pushed: {final_resp[:50]}...")

                        # 4. Check for Handoff Trigger
                        handoff_keywords = ["transferir", "especialista", "atiente mejor", "agente humano", "persona real"]
                        if any(kw in final_resp.lower() for kw in handoff_keywords):
                            logger.info(f"Handoff detected. Triggering summary...")
                            handoff_payload = {
                                "conversation_id": payload["conversation_id"],
                                "channel": payload["channel"],
                                "user_id": payload["actor_id"],
                                "reason": "User requested human or AI decided to hand off"
                            }
                            client.push("handoff.requested", handoff_payload)

                    # 5. ACK
                    client.ack(stream_in, group_name, msg_id)
                    
                except Exception as e:
                    logger.error(f"Error in AI Worker: {e}")

if __name__ == "__main__":
    run()
