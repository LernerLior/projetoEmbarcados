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

## 📋 Sobre o Projeto

Sistema embarcado de segurança com detecção de intrusos via sensores conectados a um ESP32. O backend recebe alertas em tempo real via MQTT, identifica qual das 5 zonas foi ativada e disponibiliza as informações para um aplicativo mobile via REST API e WebSocket.

---

## 🏗️ Arquitetura

```
ESP32 + Sensores (5 zonas)
      │
      │ MQTT
      ▼
 Mosquitto (Broker)
      │
      │ MQTT
      ▼
 Backend Python (FastAPI)
      │
      ├── REST API  ──► Aplicativo
      ├── WebSocket ──► Alertas em tempo real
      └── PostgreSQL ─► Histórico de alertas por zona
```

---

## 🛠️ Tecnologias

- **ESP32** — Microcontrolador com sensores de intrusão
- **MQTT / Mosquitto** — Protocolo de comunicação IoT
- **Python / FastAPI** — Backend e API REST
- **PostgreSQL** — Banco de dados
- **Docker / Docker Compose** — Containerização

---

## 📁 Estrutura do Projeto

```
projeto/
├── docker-compose.yml
├── mosquitto/
│   └── config/
│       └── mosquitto.conf
└── backend/
    ├── Dockerfile
    ├── requirements.txt
    └── src/
        └── main.py
```

---

## 🚀 Como Rodar

### Pré-requisitos
- [Docker Desktop](https://www.docker.com/products/docker-desktop/) instalado

### 1. Clone o repositório
```bash
git clone https://github.com/seu-usuario/nome-do-repo.git
cd nome-do-repo
```

### 2. Suba os containers
```bash
docker compose up -d --build
```

### 3. Verifique se está tudo rodando
```bash
docker ps
```

Deve aparecer:
```
mqtt_broker      ✅
postgres_db      ✅
backend_python   ✅
```

---

## 📡 Tópicos MQTT

| Tópico | Direção | Payload | Descrição |
|---|---|---|---|
| `security/alert` | ESP32 → Backend | `{"zone": 1}` até `{"zone": 5}` | Sensor ativado em uma zona |
| `security/status` | ESP32 → Backend | `{"armed": 1}` ou `{"armed": 0}` | Estado do sistema |
| `security/control` | Backend → ESP32 | `1` ou `0` | Armar ou desarmar |

---

## 🔌 Endpoints

| Método | Endpoint | Descrição |
|---|---|---|
| `GET` | `/status` | Retorna se o sistema está armado ou desarmado |
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
    "armed": 1
}
```

**GET /alerts**
```json
[
    {
        "id": 1,
        "zone": 3,
        "dia": "09/06/2026",
        "horario": "14:32:05"
    },
    {
        "id": 2,
        "zone": 1,
        "dia": "09/06/2026",
        "horario": "15:10:22"
    }
]
```

**GET /alerts/zone/3**
```json
[
    {
        "id": 1,
        "zone": 3,
        "dia": "09/06/2026",
        "horario": "14:32:05"
    }
]
```

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
| `timestamp` | TIMESTAMP | Data e horário do alerta |

---

## 🧪 Como Testar Localmente

### Forma 1 — Interface automática do FastAPI
Com o projeto rodando, acesse:
```
http://localhost:8000/docs
```
Teste todos os endpoints clicando, sem precisar de nenhuma ferramenta extra.

### Forma 2 — Simulando o ESP32 pelo terminal

Entre no container do broker:
```bash
docker exec -it mqtt_broker sh
```

**Simula alerta na zona 1:**
```bash
mosquitto_pub -t "security/alert" -m '{"zone": 1}'
```

**Simula alerta na zona 3:**
```bash
mosquitto_pub -t "security/alert" -m '{"zone": 3}'
```

**Simula o ESP32 armado:**
```bash
mosquitto_pub -t "security/status" -m '{"armed": 1}'
```

**Simula o ESP32 desarmado:**
```bash
mosquitto_pub -t "security/status" -m '{"armed": 0}'
```

### Fluxo sugerido
```
1. docker compose up -d --build
2. Abre http://localhost:8000/docs
3. Testa GET /status → deve retornar {"armed": 0}
4. Simula ESP32 armando → testa GET /status novamente
5. Simula alerta na zona 2 → testa GET /alerts
6. Testa GET /alerts/zone/2 → deve retornar só os alertas da zona 2
```

---

## ⚙️ Variáveis de Ambiente (docker-compose.yml)

| Variável | Valor padrão | Descrição |
|---|---|---|
| `POSTGRES_USER` | admin | Usuário do banco |
| `POSTGRES_PASSWORD` | senha123 | Senha do banco |
| `POSTGRES_DB` | seguranca | Nome do banco |