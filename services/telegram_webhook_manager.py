import json
import logging
import urllib.request
import urllib.error
from config.config import Config

try:
    import requests
except ImportError:
    requests = None

logger = logging.getLogger(__name__)

class TelegramWebhookManager:
    """
    Gestiona la verificación y configuración automática del Webhook de Telegram
    utilizando la API oficial de Telegram Bots.
    Soporta tanto `requests` como `urllib` estándar para máxima portabilidad y resiliencia.
    """
    _already_checked = False

    @staticmethod
    def _is_valid_token(token: str) -> bool:
        if not token or not token.strip():
            return False
        clean = token.strip()
        if clean.lower().startswith("your_") or "placeholder" in clean.lower():
            return False
        return ":" in clean

    @staticmethod
    def _is_valid_url(url: str) -> bool:
        if not url or not url.strip():
            return False
        clean = url.strip()
        if clean.lower().startswith("your_") or "placeholder" in clean.lower():
            return False
        return clean.startswith("https://")

    @classmethod
    def _http_get(cls, url: str, timeout: int = 7):
        if requests:
            resp = requests.get(url, timeout=timeout)
            return resp.status_code, resp.json()
        else:
            req = urllib.request.Request(url, headers={"User-Agent": "Omnichannel-Webhook/1.0"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return response.status, json.loads(response.read().decode("utf-8"))

    @classmethod
    def _http_post(cls, url: str, payload: dict, timeout: int = 10):
        if requests:
            resp = requests.post(url, json=payload, timeout=timeout)
            return resp.status_code, resp.json()
        else:
            data_bytes = json.dumps(payload).encode("utf-8")
            req = urllib.request.Request(
                url, 
                data=data_bytes, 
                headers={"Content-Type": "application/json", "User-Agent": "Omnichannel-Webhook/1.0"}
            )
            try:
                with urllib.request.urlopen(req, timeout=timeout) as response:
                    return response.status, json.loads(response.read().decode("utf-8"))
            except urllib.error.HTTPError as e:
                body = e.read().decode("utf-8")
                try:
                    return e.code, json.loads(body)
                except Exception:
                    return e.code, {"ok": False, "description": body}

    @classmethod
    def get_webhook_info(cls) -> dict:
        """
        Consulta getWebhookInfo en la API de Telegram para verificar el estado actual.
        """
        token = Config.TELEGRAM_BOT_TOKEN
        if not cls._is_valid_token(token):
            return {
                "ok": False,
                "error": "TELEGRAM_BOT_TOKEN no está configurado o tiene un formato inválido"
            }

        url = f"https://api.telegram.org/bot{token}/getWebhookInfo"
        try:
            status_code, data = cls._http_get(url, timeout=7)
            if status_code == 200 and data.get("ok"):
                result = data.get("result", {})
                current_url = result.get("url", "")
                return {
                    "ok": True,
                    "is_active": bool(current_url),
                    "current_url": current_url,
                    "has_custom_certificate": result.get("has_custom_certificate", False),
                    "pending_update_count": result.get("pending_update_count", 0),
                    "last_error_date": result.get("last_error_date"),
                    "last_error_message": result.get("last_error_message"),
                    "ip_address": result.get("ip_address"),
                    "allowed_updates": result.get("allowed_updates", [])
                }
            else:
                return {
                    "ok": False,
                    "error": data.get("description", f"Error HTTP {status_code}"),
                    "raw": data
                }
        except Exception as e:
            logger.warning(f"[TelegramWebhookManager] Error al consultar getWebhookInfo: {e}")
            return {"ok": False, "error": str(e)}

    @classmethod
    def set_webhook(cls, webhook_url: str = None, secret_token: str = None, drop_pending_updates: bool = False) -> dict:
        """
        Registra la URL del webhook en Telegram vía setWebhook.
        """
        token = Config.TELEGRAM_BOT_TOKEN
        if not cls._is_valid_token(token):
            return {
                "ok": False,
                "error": "TELEGRAM_BOT_TOKEN no está configurado o es inválido"
            }

        target_url = (webhook_url or Config.get_telegram_webhook_url()).strip()
        if not cls._is_valid_url(target_url):
            return {
                "ok": False,
                "error": f"URL de webhook inválida. Debe ser una URL HTTPS pública válida: '{target_url}'"
            }

        # Preparar payload
        payload = {
            "url": target_url,
            "allowed_updates": ["message", "edited_message", "callback_query"],
            "drop_pending_updates": drop_pending_updates
        }

        # Secret token si está configurado
        sec = secret_token if secret_token is not None else Config.TELEGRAM_SECRET_TOKEN
        if sec and sec.strip() and not sec.strip().lower().startswith("your_"):
            payload["secret_token"] = sec.strip()

        api_url = f"https://api.telegram.org/bot{token}/setWebhook"
        try:
            status_code, data = cls._http_post(api_url, payload, timeout=10)
            if status_code == 200 and data.get("ok"):
                logger.info(f"[TelegramWebhookManager] Webhook de Telegram configurado con éxito hacia {target_url}")
                return {
                    "ok": True,
                    "target_url": target_url,
                    "description": data.get("description", "Webhook was set"),
                    "secret_token_configured": bool("secret_token" in payload)
                }
            else:
                desc = data.get("description", f"Error HTTP {status_code}")
                logger.error(f"[TelegramWebhookManager] Error al registrar Webhook en Telegram: {desc}")
                return {
                    "ok": False,
                    "error": desc,
                    "raw": data
                }
        except Exception as e:
            logger.error(f"[TelegramWebhookManager] Excepción al configurar Webhook: {e}")
            return {"ok": False, "error": str(e)}

    @classmethod
    def delete_webhook(cls, drop_pending_updates: bool = False) -> dict:
        """
        Elimina el Webhook en Telegram (regresa a modo getUpdates / inactivo).
        """
        token = Config.TELEGRAM_BOT_TOKEN
        if not cls._is_valid_token(token):
            return {"ok": False, "error": "TELEGRAM_BOT_TOKEN no configurado"}

        api_url = f"https://api.telegram.org/bot{token}/deleteWebhook"
        try:
            status_code, data = cls._http_post(api_url, {"drop_pending_updates": drop_pending_updates}, timeout=8)
            return {
                "ok": data.get("ok", False),
                "description": data.get("description", "")
            }
        except Exception as e:
            return {"ok": False, "error": str(e)}

    @classmethod
    def auto_configure_on_startup(cls) -> dict:
        """
        Función ejecutada automáticamente al arrancar el contenedor / aplicación:
        1. Valida si cuenta con las dos variables necesarias (TELEGRAM_BOT_TOKEN y TELEGRAM_WEBHOOK_URL).
        2. Si no están configuradas, omite el proceso sin frenar el arranque.
        3. Si cuenta con las variables:
           a. Consulta si el webhook ya está ACTIVO y apunta a la URL objetivo.
           b. Si ya está activo y coincide, no realiza llamadas redundantes a Telegram.
           c. Si está inactivo o apunta a una URL distinta, llama a setWebhook para habilitarlo.
        """
        token = Config.TELEGRAM_BOT_TOKEN
        target_url = Config.get_telegram_webhook_url()

        # Validación de parámetros requeridos
        has_token = cls._is_valid_token(token)
        has_url = cls._is_valid_url(target_url)

        if not has_token or not has_url:
            missing = []
            if not has_token:
                missing.append("TELEGRAM_BOT_TOKEN")
            if not has_url:
                missing.append("WEBHOOK_DOMAIN o TELEGRAM_WEBHOOK_URL (dominio público o URL HTTPS requerida)")
            logger.info(
                f"[TelegramWebhookManager] Auto-configuración omitida al iniciar: Faltan variables requeridas: {', '.join(missing)}"
            )

            return {
                "status": "skipped",
                "reason": "missing_parameters",
                "missing": missing
            }

        logger.info(f"[TelegramWebhookManager] Verificando estado del Webhook de Telegram para URL objetivo: {target_url}...")

        # 1. Validar si ya se encuentra activo
        info = cls.get_webhook_info()
        if not info.get("ok"):
            logger.warning(
                f"[TelegramWebhookManager] No se pudo verificar el estado en Telegram ({info.get('error')}). Intentando habilitar directamente..."
            )
            set_res = cls.set_webhook(target_url)
            return {
                "status": "configured_after_error" if set_res.get("ok") else "failed",
                "set_result": set_res
            }

        current_url = (info.get("current_url") or "").strip()
        is_active = info.get("is_active", False)
        urls_match = (current_url.rstrip("/") == target_url.rstrip("/"))

        if is_active and urls_match:
            logger.info(
                f"[TelegramWebhookManager] Webhook de Telegram ya se encuentra ACTIVO y configurado correctamente: {current_url}"
            )
            return {
                "status": "already_active",
                "url": current_url,
                "pending_updates": info.get("pending_update_count", 0)
            }

        # 2. Si no se encuentra activo o la URL difiere, habilitar con los parámetros requeridos
        reason = "inactivo" if not is_active else f"URL previa difería ('{current_url}')"
        logger.info(f"[TelegramWebhookManager] Webhook requiere configuración ({reason}). Registrando hacia: {target_url}...")
        
        set_res = cls.set_webhook(target_url)
        if set_res.get("ok"):
            logger.info(f"[TelegramWebhookManager] Webhook de Telegram activado exitosamente en {target_url}")
            return {
                "status": "configured",
                "url": target_url,
                "previous_url": current_url
            }
        else:
            logger.error(f"[TelegramWebhookManager] No se pudo activar el Webhook de Telegram: {set_res.get('error')}")
            return {
                "status": "failed",
                "error": set_res.get("error")
            }
