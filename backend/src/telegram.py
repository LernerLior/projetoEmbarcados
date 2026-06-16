import requests

TELEGRAM_TOKEN = "8910691960:AAGIepc8nvvIOMH90YIefK-pkGpdY_CaY50"
TELEGRAM_CHAT_ID = "8624295736"

def enviar_telegram(mensagem: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": mensagem
    }
    try:
        response = requests.post(url, json=payload)
        print(f"Telegram status: {response.status_code}")
        print(f"Telegram resposta: {response.text}")
    except Exception as e:
        print(f"Erro ao enviar Telegram: {e}")