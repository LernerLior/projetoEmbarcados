import paho.mqtt.client as mqtt
import psycopg2
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import threading
import json
from datetime import datetime

app = FastAPI()

# WebSocket Manager
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

# Banco de dados 
def get_db():
    return psycopg2.connect(
        host="postgres",
        database="seguranca",
        user="admin",
        password="senha123"
    )

def criar_tabela():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS alerts (
            id SERIAL PRIMARY KEY,
            timestamp TIMESTAMP NOT NULL
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

# MQTT 
estado_atual = {"armed": 0}

def on_connect(client, userdata, flags, rc):
    print("Conectado ao broker MQTT!")
    client.subscribe("security/alert")
    client.subscribe("security/status")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = json.loads(msg.payload.decode())

    if topic == "security/alert":
        agora = datetime.now()
        print(f"Alerta recebido em {agora.strftime('%d/%m/%Y %H:%M:%S')}")

        # salva no banco
        conn = get_db()
        cur = conn.cursor()
        cur.execute("INSERT INTO alerts (timestamp) VALUES (%s) RETURNING id", (agora,))
        alert_id = cur.fetchone()[0]
        conn.commit()
        cur.close()
        conn.close()

        # monta o alerta
        alerta = {
            "id": alert_id,
            "dia": agora.strftime("%d/%m/%Y"),
            "horario": agora.strftime("%H:%M:%S")
        }

        # dispara para todos os apps conectados via WebSocket
        import asyncio
        asyncio.run(manager.broadcast(alerta))

    elif topic == "security/status":
        estado_atual["armed"] = payload.get("armed")
        print(f"Estado atualizado: {'armado' if estado_atual['armed'] else 'desarmado'}")

def iniciar_mqtt():
    client = mqtt.Client()
    client.on_connect = on_connect
    client.on_message = on_message
    client.connect("mosquitto", 1883, 60)
    client.loop_forever()

threading.Thread(target=iniciar_mqtt, daemon=True).start()
criar_tabela()

# Endpoints 

@app.get("/status")
def get_status():
    return {"armed": estado_atual["armed"]}

@app.post("/control")
def controlar_sistema(ativo: int):
    client = mqtt.Client()
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
            "dia": r[1].strftime("%d/%m/%Y"),
            "horario": r[1].strftime("%H:%M:%S")
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
        "dia": row[1].strftime("%d/%m/%Y"),
        "horario": row[1].strftime("%H:%M:%S")
    }

@app.websocket("/ws/alerts")
async def websocket_alerts(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)