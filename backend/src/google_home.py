import secrets
import paho.mqtt.client as mqtt
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse

router = APIRouter()

# ── Tokens em memória ────────────────────────────────
tokens_db = {
    "codes": set(),
    "access_tokens": set(),
    "refresh_tokens": set()
}

# ── PIN para desarmar ────────────────────────────────
PIN_SEGURANCA = "1234"  # ← mude para o PIN que quiser

# ── Estado compartilhado com o main.py ───────────────
estado_atual = None  # será injetado pelo main.py

def set_estado(estado: dict):
    global estado_atual
    estado_atual = estado

# ── OAuth2 ───────────────────────────────────────────
@router.get("/oauth/authorize")
async def oauth_authorize(redirect_uri: str, state: str):
    code = secrets.token_hex(16)
    tokens_db["codes"].add(code)
    return RedirectResponse(url=f"{redirect_uri}?code={code}&state={state}")

@router.post("/oauth/token")
async def oauth_token(
    grant_type: str = Form(...),
    code: str = Form(None),
    refresh_token: str = Form(None)
):
    if grant_type == "authorization_code":
        if not code or code not in tokens_db["codes"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
        tokens_db["codes"].remove(code)

    elif grant_type == "refresh_token":
        if not refresh_token or refresh_token not in tokens_db["refresh_tokens"]:
            return JSONResponse({"error": "invalid_grant"}, status_code=400)
    else:
        return JSONResponse({"error": "unsupported_grant_type"}, status_code=400)

    access_token = f"access-{secrets.token_hex(32)}"
    new_refresh_token = f"refresh-{secrets.token_hex(32)}"

    tokens_db["access_tokens"].add(access_token)
    tokens_db["refresh_tokens"].add(new_refresh_token)

    return JSONResponse({
        "token_type": "bearer",
        "access_token": access_token,
        "refresh_token": new_refresh_token,
        "expires_in": 315360000
    })

# ── Webhook Google Home ──────────────────────────────
@router.post("/google-home-webhook")
async def google_fulfillment(request: Request):
    body = await request.json()
    inputs = body.get("inputs", [])
    request_id = body.get("requestId", "default_id")
    response_payload = {}

    for i in inputs:
        intent = i.get("intent")

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

        elif intent == "action.devices.QUERY":
            response_payload = {
                "devices": {
                    "alarme_casa": {
                        "online": True,
                        "isArmed": estado_atual["status"] == "armed"
                    }
                }
            }

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

                        # Exige PIN para desarmar
                        if not deve_armar:
                            challenge = exec_item.get("challenge", {})
                            pin_recebido = challenge.get("pin")

                            if not pin_recebido or pin_recebido != PIN_SEGURANCA:
                                commands_response.append({
                                    "ids": device_ids,
                                    "status": "ERROR",
                                    "errorCode": "challengeNeeded",
                                    "challengeNeeded": {"type": "pinNeeded"}
                                })
                                continue

                        # Publica no MQTT
                        valor_mqtt = 1 if deve_armar else 0
                        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)
                        client.connect("mosquitto", 1883, 60)
                        client.publish("security/control", str(valor_mqtt))
                        client.disconnect()

                        # Atualiza estado
                        estado_atual["status"] = "armed" if deve_armar else "disarmed"

                        commands_response.append({
                            "ids": device_ids,
                            "status": "SUCCESS",
                            "states": {
                                "isArmed": deve_armar,
                                "online": True
                            }
                        })

            response_payload = {"commands": commands_response}

    return JSONResponse({
        "requestId": request_id,
        "payload": response_payload
    })