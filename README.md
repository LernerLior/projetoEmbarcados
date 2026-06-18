# 🔒 Sistema de Segurança com ESP32

Sistema de detecção de intrusos com ESP32, comunicação MQTT e backend em Python.

---

## 👥 Membros do Grupo

| Nome |
|---|
| FERNANDO YAMAMOTO LICHTENFELS RICCIO |
| DYLAN KIYOSHI KANEKO NISHINA |
| LIOR LERNER |
| VINICIUS FIORAVANTE SILVA |

---
## 📋 Link de acesso aos githubs utilizados:

| Propósito | Link |
|---|---|
| Programação do FPGA e ESP32 | https://github.com/Ricciow/Embarcados/ | 
| Backend do aplicativo | https://github.com/LernerLior/projetoEmbarcados| 
| Frontend do aplicativo | https://github.com/ViniciusFS1/Embarcados_House_App_Front|

---
## 📋 Sobre o Projeto

Sistema embarcado de segurança com detecção de intrusos via sensores conectados a um ESP32 e uma FPGA. O backend recebe alertas em tempo real via MQTT, identifica qual das 5 zonas foi ativada, salva no banco de dados, envia notificação pelo Telegram e disponibiliza as informações para um aplicativo mobile via REST API e WebSocket.

---

## 🏗️ Arquitetura

```
FPGA (Basys 3) + Sensores (5 zonas)
      │
      │ Serial (UART)
      ▼
 ESP32
      │
      │ MQTT
      ▼
 Mosquitto (Broker)
      │
      │ MQTT
      ▼
 Backend Python (FastAPI)
      │
      ├── REST API   ──► Aplicativo
      ├── WebSocket  ──► Alertas em tempo real
      ├── PostgreSQL ──► Histórico de alertas por zona
      └── Telegram   ──► Notificação instantânea
```

---

## 🛠️ Tecnologias

- **ESP32** — Microcontrolador com comunicação WiFi e MQTT
- **FPGA (Basys 3)** — Leitura dos sensores de intrusão
- **MQTT / Mosquitto** — Protocolo de comunicação IoT
- **Python / FastAPI** — Backend e API REST
- **PostgreSQL** — Banco de dados
- **Docker / Docker Compose** — Containerização
- **Telegram Bot** — Notificações em tempo real

---

## 📁 Estrutura do Projeto

```
projeto/
├── docker-compose.yml
├── docker-compose.local.yml
├── mosquitto/
│   └── config/
│       └── mosquitto.conf
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   └── src/
│       ├── main.py
│       └── telegram.py
└── esp32/
    └── security_esp32.ino
```

---

## 🚀 Como Rodar

### Pré-requisitos
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado
- [Arduino IDE](https://www.arduino.cc/en/software) instalado
- Biblioteca `PubSubClient` instalada no Arduino IDE

### 1. Clone o repositório
```bash
git clone https://github.com/seu-usuario/nome-do-repo.git
cd nome-do-repo
```

### 2. Configure o Telegram
Em `backend/src/telegram.py` substitua as credenciais:
```python
TELEGRAM_TOKEN   = "SEU_TOKEN_AQUI"
TELEGRAM_CHAT_ID = "SEU_CHAT_ID_AQUI"
```

### 3. Configure o ESP32
Em `esp32/security_esp32.ino` substitua os placeholders:
```cpp
const char* ssid        = "SEU_WIFI_AQUI";
const char* password    = "SUA_SENHA_AQUI";
const char* mqtt_server = "IP_DO_SERVIDOR_AQUI";
```

### 4. Suba os containers
```bash
docker compose -f docker-compose.local.yml up -d --build
```

### 5. Verifique se está tudo rodando
```bash
docker ps
```

Deve aparecer:
```
mqtt_broker      ✅
postgres_db      ✅
backend_python   ✅
```

### 6. Carregue o código no ESP32
- Abre o `security_esp32.ino` no Arduino IDE
- Seleciona a placa: `Tools → Board → ESP32 Arduino → ESP32 Dev Module`
- Seleciona a porta: `Tools → Port → COM?`
- Clica em Upload

---

## 📡 Tópicos MQTT

| Tópico | Direção | Payload | Descrição |
|---|---|---|---|
| `security/alert` | ESP32 → Backend | `{"zone": 1}` até `{"zone": 5}` | Sensor ativado em uma zona |
| `security/status` | ESP32 → Backend | `0`, `1` ou `2` | Estado atual do sistema |
| `security/control` | Backend → ESP32 | `0`, `1` ou `2` | Mudar estado do sistema |

### Estados do sistema

| Valor | Estado | Descrição |
|---|---|---|
| `0` | `disarmed` | Sistema desativado |
| `1` | `armed` | Sistema armado, monitorando |
| `2` | `active` | Sensor disparado, alarme ativo |

---

## 🔌 Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/status` | Retorna o estado atual do sistema |
| `POST` | `/control?ativo=1` | Arma o sistema |
| `POST` | `/control?ativo=0` | Desarma o sistema |
| `GET` | `/alerts` | Retorna histórico completo de alertas |
| `GET` | `/alerts/{id}` | Retorna um alerta específico |
| `GET` | `/alerts/zone/{zone_id}` | Retorna alertas de uma zona específica (1 a 5) |
| `WS` | `/ws/alerts` | Alertas em tempo real via WebSocket |

### Exemplos de resposta

**GET /status**
```json
{
    "status": "armed"
}
```

**GET /alerts**
```json
[
    {
        "id": 1,
        "zone": 3,
        "dia": "17/06/2026",
        "horario": "20:32:05"
    }
]
```

---

## 📲 Notificação Telegram

Quando um sensor é ativado, o sistema envia automaticamente uma mensagem no Telegram:

```
🚨 ALERTA DE INTRUSO!
Zona: 3
Data: 17/06/2026
Horário: 20:32:05
```

### Como configurar o bot

1. Pesquisa `@BotFather` no Telegram
2. Manda `/newbot` e segue as instruções
3. Guarda o token gerado
4. Pesquisa `@userinfobot` para pegar seu Chat ID
5. Substitui as credenciais em `backend/src/telegram.py`

---

## 📖 Documentação da API

Com o projeto rodando, acesse:
```
http://localhost:8000/docs
```

O FastAPI gera automaticamente uma interface para testar todos os endpoints.

---

## 🗄️ Banco de Dados

| Campo | Tipo | Descrição |
|---|---|---|
| `id` | SERIAL | Identificador único |
| `zone` | INT (1-5) | Zona que foi ativada |
| `timestamp` | TIMESTAMP | Data e horário do alerta (fuso: America/Sao_Paulo) |

---

## 🧪 Como Testar Localmente

### Forma 1 — Interface automática do FastAPI
Com o projeto rodando, acesse:
```
http://localhost:8000/docs
```

### Forma 2 — Simulando o ESP32 pelo terminal

Entre no container do broker:
```bash
docker exec -it mqtt_broker sh
```

**Simula sistema desarmado:**
```bash
mosquitto_pub -t "security/status" -m "0"
```

**Simula sistema armado:**
```bash
mosquitto_pub -t "security/status" -m "1"
```

**Simula sistema ativo (alarme):**
```bash
mosquitto_pub -t "security/status" -m "2"
```

**Simula alerta na zona 1:**
```bash
mosquitto_pub -t "security/alert" -m '{"zone": 1}'
```

**Simula alerta na zona 3:**
```bash
mosquitto_pub -t "security/alert" -m '{"zone": 3}'
```

### Fluxo sugerido
```
1. docker compose -f docker-compose.local.yml up -d --build
2. Abre http://localhost:8000/docs
3. Testa GET /status → deve retornar {"status": "disarmed"}
4. Publica "1" no security/status → testa GET /status → {"status": "armed"}
5. Publica alerta na zona 2 → testa GET /alerts
6. Verifica notificação no Telegram
7. Testa GET /alerts/zone/2 → retorna só alertas da zona 2
```

---

## 🔌 Protocolo ESP32 ↔ FPGA (UART)

| Byte recebido | Bit 7 | Bit 6 | Descrição |
|---|---|---|---|
| Evento de sensor | `1` | — | Bits 0-4 indicam zonas ativas |
| Mudança de estado | `0` | `1` | Bits 0-1 indicam o estado |

| Bits 0-1 | Estado |
|---|---|
| `00` | disarmed |
| `01` | armed |
| `10` | active |

---

## ⚙️ Variáveis de Ambiente (docker-compose.local.yml)

| Variável | Valor padrão | Descrição |
|---|---|---|
| `POSTGRES_USER` | admin | Usuário do banco |
| `POSTGRES_PASSWORD` | senha123 | Senha do banco |
| `POSTGRES_DB` | seguranca | Nome do banco |
