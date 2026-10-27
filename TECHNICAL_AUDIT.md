# Auditoría Técnica y Arquitectura del Sistema (v8.0)
**Proyecto**: Omnichannel Webhook Service (WhatsApp, Telegram, Messenger)
**Enfoque**: Documentación de arquitectura, decisiones técnicas y valuación de ingeniería.

---

## 1. Resumen Ejecutivo
El sistema es un middleware omnicanal de alto rendimiento diseñado para orquestar mensajes entre clientes finales (WhatsApp, Telegram, Messenger) y los sistemas internos (Bots de IA, CRM como Odoo, Agentes Humanos).

La arquitectura ha evolucionado de un modelo monolítico sincrónico a un **modelo asíncrono impulsado por eventos (Event-Driven)** utilizando Redis Streams y el patrón Pub/Sub. Esto garantiza alta disponibilidad, tolerancia a fallos, procesamiento no bloqueante y tiempos de respuesta de milisegundos en las APIs públicas, logrando un desacoplamiento total (Agnosticismo) de los frontends.

---

## 2. Arquitectura y Flujos de Datos

### Flujo de Entrada (Inbound - Webhook to Internal System)
1. **Recepción (`webhook.py`)**: El proveedor (Meta/Telegram) envía una petición HTTP. Se valida la firma HMAC/Secret Token y se verifica el Rate Limit.
2. **Normalización (`normalizer.py` & Adapters)**: El payload crudo se traduce al esquema universal `IMOv2`. Se extraen textos, multimedia (`media_url`/`media_id`) y contexto (respuestas).
3. **Persistencia Dual (MongoDB + PostgreSQL)**: Se guarda el estado de la conversación y el mensaje.
4. **Encolado (Redis)**: Se publica el mensaje procesado en el stream `message.normalized`.
5. **Pub/Sub (Webhooks Outbound)**: El worker `frontend_dispatcher_worker.py` lee el stream y envía el mensaje (mediante un `POST` HTTP) a todos los sistemas (Odoo, CRMs) que estén suscritos.

### Flujo de Salida (Outbound - Internal System to Provider)
1. **Recepción (`messages.py` & `message_service.py`)**: El CRM (Ej. Odoo) llama al API `/messages/send`. Se valida la idempotencia mediante `client_id`.
2. **Persistencia Provisional**: El mensaje se guarda en DB con estado `pending`.
3. **Encolado Asíncrono (Redis)**: Se publica una tarea en `message.outbound`. El API responde inmediatamente con `202 Accepted`.
4. **Despacho (`dispatcher_worker.py` & Senders)**: Un worker en segundo plano consume la tarea, ejecuta la petición HTTP hacia Meta/Telegram.
5. **Acuse de Recibo (Delivery Receipt)**: Al terminar, el worker publica el resultado (éxito/falla) en `message.status_updated`, lo cual es capturado por el Frontend Dispatcher y enviado de vuelta al CRM.

---

## 3. Postura de Seguridad y Fiabilidad

Como validación técnica de grado empresarial, el sistema cuenta con:
1. **Idempotencia Transaccional**: El uso de `client_id` previene que reintentos de red causen envíos duplicados al usuario final.
2. **Deduplicación Inbound**: El índice único `external_id` en MongoDB rechaza transparentemente las notificaciones webhooks repetidas.
3. **Prevención de Ataques Side-Channel**: El Rate Limiter con variación de límites (jittering) evita que atacantes mapeen las políticas de seguridad del firewall.
4. **Resource Management**: El Threaded Connection Pool en Postgres previene la saturación de RAM en la DB bajo picos de tráfico ("Too many connections").
5. **Fail-Safe Asíncrono**: Si las APIs de Meta caen, el webhook sigue respondiendo 200 OK inmediatamente (evitando baneos), mientras Redis encola los mensajes para reintentarlos después.

---

## 4. Valoración Comercial y Esfuerzo Técnico (Technical Valuation)

Esta sección documenta de manera objetiva el esfuerzo de ingeniería requerido para desarrollar el middleware en su estado actual (v8.0), sirviendo como referencia para asignación presupuestal o valuación de activos tecnológicos.

### Composición Ideal del Equipo (Team Topology)
El desarrollo de un sistema con arquitectura orientada a eventos, persistencia dual y mitigación de ataques requiere perfiles especializados:
- **1 Arquitecto de Software / Tech Lead Backend**: Diseño de arquitectura asíncrona, modelo Pub/Sub para agnosticismo de CRMs, modelado de datos en PostgreSQL/MongoDB, estrategias de mitigación de red (Rate Limiting dinámico, Idempotencia).
- **1-2 Desarrolladores Backend (Mid/Sr)**: Implementación de Senders/Adapters para APIs de terceros (Meta Graph API, Telegram Bot API), integración con Redis Streams y normalización de payloads (IMOv2).
- **1 Ingeniero DevOps / SRE (Parcial)**: Aprovisionamiento de contenedores, configuración de Redis, tuning de PostgreSQL (Connection Pools).

### Estimación de Tiempo de Desarrollo (Time-to-Market)
Construir, estabilizar y auditar esta arquitectura desde cero implica un esfuerzo de **8 a 12 semanas (2 a 3 meses)** de trabajo continuo:
1. **Semanas 1-2**: Diseño de base de datos, esquema universal (IMOv2) y enrutador básico.
2. **Semanas 3-5**: Desarrollo de adaptadores (WhatsApp, Messenger, Telegram) y Senders.
3. **Semanas 6-7**: Refactorización a arquitectura asíncrona (Redis Streams, Dispatcher Workers).
4. **Semanas 8-10**: Implementación de resiliencia (Connection Pooling, Idempotencia, manejo multimedia).
5. **Semanas 11-12**: Arquitectura Pub/Sub (Webhooks outbound), auditoría de seguridad (HMAC, Jitter Rate Limiting) y despliegue.

### Valuación de Mercado Estimada (Consultoría B2B)
Basado en tarifas estándar de mercado para desarrollo de software a medida (Software de Infraestructura/Middleware):
- **Agencia / Consultora LatAm (Nearshore)**: Rango de cotización entre **$18,000 USD y $35,000 USD** (Aprox. **$300,000 MXN a $600,000 MXN**), considerando un rate blend de $35-$50 USD/hora.
- **Agencia en EE.UU. / Europa (Onshore)**: Rango de cotización entre **$60,000 USD y $120,000 USD**, considerando rates de $100-$200+ USD/hora.

*Justificación Estratégica*: El valor intrínseco de este código radica en la eliminación de costos recurrentes (OPEX). Plataformas SaaS comerciales (como Twilio o MessageBird) cobran licencias mensuales altas y un margen adicional (markup) por cada mensaje enviado/recibido. En operaciones omnicanales de mediano y gran volumen (miles de chats diarios), el CAPEX de desarrollo interno se recupera en los primeros trimestres, garantizando control absoluto sobre la privacidad de la data y la integración agnóstica con múltiples sistemas internos.
