import paho.mqtt.client as mqtt
import psycopg2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, status, Request, Form
from fastapi.responses import RedirectResponse, JSONResponse
from contextlib import asynccontextmanager
import threading
import json
from datetime import datetime
import asyncio
import secrets

# ── WebSocket Manager ────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

manager = ConnectionManager()

# ── Banco de dados ───────────────────────────────────
def get_db():
    return psycopg2.connect(
        host="postgres",
        database="seguranca",
        user="admin",
        password="senha123"
    )

async def esperar_banco():
    print("Aguardando PostgreSQL ficar pronto...")
    while True:
        try:
            conn = get_db()
            conn.close()
            print("PostgreSQL pronto! ✅")
            return
        except Exception as e:
            print(f"PostgreSQL ainda não está pronto: {e}")
            await asyncio.sleep(2)

def criar_tabela():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY,
            zone INT NOT NULL CHECK (zone BETWEEN 1 AND 5),
            timestamp TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# ── MQTT ─────────────────────────────────────────────
estado_atual = {"armed": 0}
main_loop = None 

async def esperar_mqtt():
    print("Aguardando Mosquitto ficar pronto...")
    while True:
        try:
            client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
            client.connect("mosquitto", 1883, 60)
            client.disconnect()
            print("Mosquitto pronto! ✅")
            return
        except Exception as e:
            print(f"Mosquitto ainda não está pronto: {e}")
            await asyncio.sleep(2)

def on_connect(client, userdata, flags, rc):
    print("Conectado ao broker MQTT!")
    client.subscribe("security/alert")
    client.subscribe("security/status")

def enviar_comando_mqtt(ativo: int):
    """Função auxiliar para publicar de forma síncrona/segura no MQTT"""
    try:
        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
        client.connect("mosquitto", 1883, 60)
        client.publish("security/control", str(ativo))
        client.disconnect()
    except Exception as e:
        print(f"Falha ao enviar comando via MQTT: {e}")

def on_message(client, userdata, msg):
    global main_loop
    topic = msg.topic
    raw = msg.payload.decode()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw

    if topic == "security/alert":
        agora = datetime.now()

        if isinstance(payload, dict):
            zone = payload.get("zone", 1)
        else:
            try:
                zone = int(payload)
            except ValueError:
                zone = 1

        if zone < 1 or zone > 5:
            zone = 1

        print(f"Alerta recebido na zona {zone} em {agora.strftime('%d/%m/%Y %H:%M:%S')}")

        try:
            conn = get_db()
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO alerts (zone, timestamp) VALUES (%s, %s) RETURNING id",
                (zone, agora)
            )
            alert_id = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()
        except Exception as db_err:
            print(f"Erro ao salvar no banco: {db_err}")
            return

        alerta = {
            "id": alert_id,
            "zone": zone,
            "dia": agora.strftime("%d/%m/%Y"),
            "horario": agora.strftime("%H:%M:%S")
        }

        if main_loop:
            asyncio.run_coroutine_threadsafe(manager.broadcast(alerta), main_loop)

    elif topic == "security/status":
        if isinstance(payload, dict):
            estado_atual["armed"] = int(payload.get("armed", 0))
        else:
            try:
                estado_atual["armed"] = int(payload)
            except ValueError:
                estado_atual["armed"] = 0
        print(f"Estado atualizado: {'armado' if estado_atual['armed'] else 'desarmado'}")

def iniciar_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("mosquitto", 1883, 60)
    client.loop_forever()

# ── Lifespan ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    global main_loop
    main_loop = asyncio.get_running_loop()
    await esperar_banco()
    criar_tabela()
    await esperar_mqtt()
    threading.Thread(target=iniciar_mqtt, daemon=True).start()
    print("Backend iniciado com sucesso! ✅")
    yield

app = FastAPI(lifespan=lifespan)

# ── Endpoints Originais (React) ──────────────────────

@app.get("/status")
def get_status():
    return {"armed": estado_atual["armed"]}

@app.post("/control")
def controlar_sistema(ativo: int):
    if ativo not in:
        raise HTTPException(status_code=400, detail="Valor de controle deve ser 0 ou 1.")
    enviar_comando_mqtt(ativo)
    return {"status": "enviado", "ativo": ativo}

@app.get("/alerts")
def listar_alertas():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alerts ORDER BY timestamp DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "zone": r[1], "dia": r[2].strftime("%d/%m/%Y"), "horario": r[2].strftime("%H:%M:%S")}
        for r in rows
    ]

@app.get("/alerts/zone/{zone_id}")
def alertas_por_zona(zone_id: int):
    if zone_id < 1 or zone_id > 5:
        raise HTTPException(status_code=400, detail="Zona inválida. Use entre 1 e 5.")
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alerts WHERE zone = %s ORDER BY timestamp DESC", (zone_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {"id": r[0], "zone": r[1], "dia": r[2].strftime("%d/%m/%Y"), "horario": r[2].strftime("%H:%M:%S")}
        for r in rows
    ]

@app.get("/alerts/{alert_id}")
def get_alerta(alert_id: int):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alerts WHERE id = %s", (alert_id,))
    row = cur.fetchone()
    cur.close()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="Alerta não encontrado")
    return {"id": row[0], "zone": row[1], "dia": row[2].strftime("%d/%m/%Y"), "horario": row[2].strftime("%H:%M:%S")}

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)

# ── Fluxo Google Home (OAuth2 & Fulfillment) ──────────

@app.get("/oauth/authorize")
async def oauth_authorize(redirect_uri: str, state: str):
    # Tela temporária para o aplicativo Google Home aprovar o vínculo de conta
    # Em produção, você colocaria uma tela de login real aqui.
    code = secrets.token_hex(16)
    return RedirectResponse(url=f"{redirect_uri}?code={code}&state={state}")

@app.post("/oauth/token")
async def oauth_token(grant_type: str = Form(...), code: str = Form(None), refresh_token: str = Form(None)):
    # Entrega as chaves de acesso que a Google usará para validar as requisições de voz
    return JSONResponse({
        "token_type": "bearer",
        "access_token": "google-access-token-valido",
        "refresh_token": "google-refresh-token-valido",
        "expires_in": 3600
    })

@app.post("/smarthome/fulfillment")
async def google_fulfillment(request: Request):
    body = await request.json()
    inputs = body.get("inputs", [])
    response_payload = {}

    for i in inputs:
        intent = i.get("intent")

        # 1. SYNC: Diz ao ecossistema Google que existe um Alarme
        if intent == "action.devices.SYNC":
            response_payload = {
                "agentUserId": "usuario_local_123",
                "devices": [{
                    "id": "alarme_casa",
                    "type": "action.devices.types.SECURITY_SYSTEM",
                    "traits": ["action.devices.traits.ArmDisarm"],
                    "name": {"name": "Alarme da Casa", "nicknames": ["alarme", "sistema de segurança"]},
                    "willReportState": False,
                    "attributes": {
                        "availableArmLevels": {
                            "levels": [{
                                "level_name": "L1",
                                "level_values": [{"level_synonym": ["total", "modo completo"], "lang": "pt-BR"}]
                            }]
                        }
                    }
                }]
            }

        # 2. QUERY: Responde para a Google se o alarme está ativo ou não
        elif intent == "action.devices.QUERY":
            response_payload = {
                "devices": {
                    "alarme_casa": {
                        "online": True,
                        "isArmed": bool(estado_atual["armed"])
                    }
                }
            }

        # 3. EXECUTE: Dispara quando você fala "Ok Google, arme o alarme"
        elif intent == "action.devices.EXECUTE":
