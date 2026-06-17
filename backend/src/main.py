import paho.mqtt.client as mqtt
import psycopg2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from contextlib import asynccontextmanager
import threading
import json
from datetime import datetime
import asyncio
import pytz

from telegram import enviar_telegram

# ── WebSocket Manager ────────────────────────────────
class ConnectionManager:
    def __init__(self):
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        for connection in self.active_connections:
            await connection.send_json(message)

manager = ConnectionManager()

# ── Fuso horário ─────────────────────────────────────
fuso_brasil = pytz.timezone("America/Sao_Paulo")

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
estado_atual = {"status": "disarmed"}

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

def on_message(client, userdata, msg):
    topic = msg.topic
    raw = msg.payload.decode()

    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        payload = raw

    if topic == "security/alert":
        agora = datetime.now(fuso_brasil)

        if isinstance(payload, dict):
            zone = payload.get("zone", 0)
        else:
            zone = 0

        print(f"Alerta recebido na zona {zone} em {agora.strftime('%d/%m/%Y %H:%M:%S')}")

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

        alerta = {
            "id": alert_id,
            "zone": zone,
            "dia": agora.strftime("%d/%m/%Y"),
            "horario": agora.strftime("%H:%M:%S")
        }

        enviar_telegram(
            f"🚨 ALERTA DE INTRUSO!\n"
            f"Zona: {zone}\n"
            f"Data: {agora.strftime('%d/%m/%Y')}\n"
            f"Horário: {agora.strftime('%H:%M:%S')}"
        )

        asyncio.run(manager.broadcast(alerta))

    elif topic == "security/status":
        if isinstance(payload, dict):
            status = payload.get("status", None)
            armed  = payload.get("armed", None)

            if status is not None:
                estado_atual["status"] = status
            elif armed is not None:
                mapa = {0: "disarmed", 1: "armed", 2: "active"}
                estado_atual["status"] = mapa.get(int(armed), "disarmed")
        else:
            mapa = {"0": "disarmed", "1": "armed", "2": "active"}
            estado_atual["status"] = mapa.get(str(payload), str(payload))

        print(f"Estado atualizado: {estado_atual['status']}")

def iniciar_mqtt():
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("mosquitto", 1883, 60)
    client.loop_forever()

# ── Lifespan ─────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    await esperar_banco()
    criar_tabela()
    await esperar_mqtt()
    threading.Thread(target=iniciar_mqtt, daemon=True).start()
    print("Backend iniciado com sucesso! ✅")
    yield

app = FastAPI(lifespan=lifespan)

# ── Endpoints ────────────────────────────────────────

@app.get("/status")
def get_status():
    return {"status": estado_atual["status"]}

@app.post("/control")
def controlar_sistema(ativo: int):
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
    client.connect("mosquitto", 1883, 60)
    client.publish("security/control", str(ativo))
    client.disconnect()
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
        {
            "id": r[0],
            "zone": r[1],
            "dia": r[2].strftime("%d/%m/%Y"),
            "horario": r[2].strftime("%H:%M:%S")
        }
        for r in rows
    ]

@app.get("/alerts/zone/{zone_id}")
def alertas_por_zona(zone_id: int):
    if zone_id < 1 or zone_id > 5:
        return {"erro": "Zona inválida. Use entre 1 e 5."}
    conn = get_db()
    cur = conn.cursor()
    cur.execute("SELECT * FROM alerts WHERE zone = %s ORDER BY timestamp DESC", (zone_id,))
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [
        {
            "id": r[0],
            "zone": r[1],
            "dia": r[2].strftime("%d/%m/%Y"),
            "horario": r[2].strftime("%H:%M:%S")
        }
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
        return {"erro": "Alerta não encontrado"}
    return {
        "id": row[0],
        "zone": row[1],
        "dia": row[2].strftime("%d/%m/%Y"),
        "horario": row[2].strftime("%H:%M:%S")
    }

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# ── Fluxo Google Home (OAuth2 & Fulfillment) ──────────


import secrets
from fastapi import FastAPI, Form, Request, Depends, HTTPException
from fastapi.responses import RedirectResponse, JSONResponse

app = FastAPI()

# --- BANCO DE DADOS EM MEMÓRIA (Apenas para demonstração) ---
# Em produção, substitua por Redis ou um banco de dados relacional.
tokens_db = {
    "codes": set(),          # Armazena os authorization codes válidos
    "access_tokens": set(),  # Armazena os access tokens ativos
    "refresh_tokens": set()  # Armazena os refresh tokens ativos
}

estado_atual = {
    "armed": 0,  # 0 = Desarmado, 1 = Armado
}

# Código PIN estático para desarmar o alarme (Exigência do Google)
PIN_SEGURANCA = "1234"


# --- MOCKS DE FUNÇÕES EXTERNAS ---
def enviar_comando_mqtt(valor: int):
    # Simula o envio de comando para o broker MQTT
    print(f"[MQTT] Comando enviado: {valor}")


# --- FLUXO OAUTH2 ---

@app.get("/oauth/authorize")
async def oauth_authorize(redirect_uri: str, state: str):
    # 1. Gera um código de autorização único
    code = secrets.token_hex(16)
    tokens_db["codes"].add(code)
    
    # 2. Redireciona de volta para o Google com as credenciais
    return RedirectResponse(url=f"{redirect_uri}?code={code}&state={state}")


@app.post("/oauth/token")
async def oauth_token(
    grant_type: str = Form(...),
    code: str = Form(None),
    refresh_token: str = Form(None)
):
    # Validação do fluxo de código de autorização (Troca o code por tokens)
    if grant_type == "authorization_code":
        if not code or code not in tokens_db["codes"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        
        # Consome o código para que ele não possa ser usado novamente
        tokens_db["codes"].remove(code)
        
    # Validação do fluxo de atualização (Usa o refresh_token para gerar novo access_token)
    elif grant_type == "refresh_token":
        if not refresh_token or refresh_token not in tokens_db["refresh_tokens"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
            
    else:
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    # Criação de novos tokens válidos
    access_token = f"access-{secrets.token_hex(32)}"
    new_refresh_token = f"refresh-{secrets.token_hex(32)}"
    
    tokens_db["access_tokens"].add(access_token)
    tokens_db["refresh_tokens"].add(new_refresh_token)

    return JSONResponse({
        "token_type": "bearer",
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "expires_in": 315360000  # 10 anos (ajuste conforme sua política)
    })


# --- WEBHOOK SMART HOME ---

@app.post("/google-home-webhook")
async def google_fulfillment(request: Request):
    body = await request.json()
    inputs = body.get("inputs", [])
    request_id = body.get("requestId", "default_id")
    
    # O response_payload deve representar o objeto 'payload' exigido pelo Google
    response_payload = {}

    for i in inputs:
        intent = i.get("intent")

        # 1. INTENÇÃO: SYNC
        if intent == "action.devices.SYNC":
            response_payload = {
                "agentUserId": "usuario_local_123",
                "devices": [{
                    "id": "alarme_casa",
                    "type": "action.devices.types.SECURITY_SYSTEM",
                    "traits": ["action.devices.traits.ArmDisarm"],
                    "name": {
                        "name": "Alarme da Casa", 
                        "nicknames": ["alarme", "sistema de segurança"]
                    },
                    "willReportState": False,
                    "attributes": {
                        # Atributo crucial para que o aplicativo Google Home peça a senha ao usuário
                        "pinCodeHint": "PIN_ALWAYS_REQUIRED",
                        "availableArmLevels": {
                            "levels": [{
                                "level_name": "L1",
                                "level_values": [
                                    {"level_synonym": ["total", "modo completo"], "lang": "pt-BR"}
                                ]
                            }]
                        }
                    }
                }]
            }

        # 2. INTENÇÃO: QUERY
        elif intent == "action.devices.QUERY":
            response_payload = {
                "devices": {
                    "alarme_casa": {
                        "online": True,
                        "isArmed": bool(estado_atual["armed"])
                    }
                }
            }

        # 3. INTENÇÃO: EXECUTE
        elif intent == "action.devices.EXECUTE":
            commands_response = []
            payload_commands = i.get("payload", {}).get("commands", [])

            for cmd_block in payload_commands:
                devices = cmd_block.get("devices", [])
                executions = cmd_block.get("execution", [])
                device_ids = [d["id"] for d in devices]

                for exec_item in executions:
                    if exec_item["command"] == "action.devices.commands.ArmDisarm":
                        deve_armar = exec_item["params"]["arm"]
                        
                        # VERIFICAÇÃO DE SEGURANÇA: Se a intenção for DESARMAR (arm=False)
                        if not deve_armar:
                            challenge = exec_item.get("challenge", {})
                            pin_recebido = challenge.get("pin")
                            
                            # Se não enviou o PIN ou o PIN estiver errado, lança o desafio
                            if not pin_recebido or pin_recebido != PIN_SEGURANCA:
                                commands_response.append({
                                    "ids": device_ids,
                                    "status": "ERROR",
                                    "errorCode": "challengeNeeded",
                                    "challengeNeeded": {
                                        "type": "pinNeeded"
                                    }
                                })
                                continue  # Pula o processamento deste comando até o PIN correto chegar

                        # Executa o comando caso seja para ARMAR ou se o PIN correto já foi validado acima
                        valor_mqtt = 1 if deve_armar else 0
                        enviar_comando_mqtt(valor_mqtt)
                        estado_atual["armed"] = valor_mqtt

                        commands_response.append({
                            "ids": device_ids,
                            "status": "SUCCESS",
                            "states": {
                                "isArmed": deve_armar,
                                "online": True
                            }
                        })

            response_payload = {
                "commands": commands_response
            }

    # Retorno unificado no padrão exigido pelo Google Action SDK
    return JSONResponse({
        "requestId": request_id,
        "payload": response_payload
    })

