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
estado_atual = {"armed": 0}

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
        agora = datetime.now(fuso_brasil)  # ← fuso horário correto

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
            estado_atual["armed"] = payload.get("armed")
        else:
            estado_atual["armed"] = int(payload)
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
    return {"armed": estado_atual["armed"]}

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