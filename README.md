# Chat API

Een productie-klare FastAPI applicatie voor real-time chat met WebSocket ondersteuning en MongoDB.

## Features

- **Real-time WebSocket Chat** - Live berichten broadcasting
- **REST API** - CRUD operaties voor groepen en berichten
- **MongoDB + Beanie ODM** - Type-safe document models
- **JWT Authenticatie** - Gedeeld secret met auth-api
- **Groep-gebaseerde Autorisatie** - User-based access control
- **Structured Logging** - Met correlation IDs
- **CORS Support** - Voor frontend integratie

## Project Structuur

```
chat-api/
├── app/
│   ├── main.py              # FastAPI applicatie
│   ├── config.py            # Settings
│   ├── core/                # Exceptions & logging
│   ├── db/                  # MongoDB connectie
│   ├── models/              # Group & Message documents
│   ├── schemas/             # Pydantic schemas
│   ├── services/            # ChatService & ConnectionManager
│   ├── routes/              # Groups, Messages, WebSocket
│   └── middleware/          # Auth & correlation
├── requirements.txt         # Python dependencies
├── .env                     # Environment variables
└── README.md               # Deze file
```

## Snelle Start

### 1. Installeer Dependencies

```bash
# Maak virtual environment
python3 -m venv venv
source venv/bin/activate  # Op Windows: venv\Scripts\activate

# Installeer packages
pip install -r requirements.txt
```

### 2. Start MongoDB

Je hebt MongoDB nodig. Optie A (Docker) of B (Lokaal):

**Optie A: Docker**
```bash
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

**Optie B: Lokale installatie**
```bash
# Mac
brew install mongodb-community
brew services start mongodb-community

# Linux
sudo apt-get install mongodb
sudo systemctl start mongodb
```

### 3. Start de Applicatie

```bash
# Development mode met auto-reload
uvicorn app.main:app --reload --port 8001

# Of via Python
python -m app.main
```

De API is nu beschikbaar op:
- **API**: http://localhost:8001
- **Docs**: http://localhost:8001/docs
- **Health**: http://localhost:8001/health

## API Endpoints

### Groups

```
GET    /api/chat/groups           - Haal gebruikers groepen op
GET    /api/chat/groups/{id}      - Haal specifieke groep op
```

### Messages

```
GET    /api/chat/groups/{id}/messages    - Haal berichten op (met paginatie)
POST   /api/chat/groups/{id}/messages    - Maak nieuw bericht
PUT    /api/chat/messages/{id}           - Update bericht (alleen eigen)
DELETE /api/chat/messages/{id}           - Verwijder bericht (soft delete)
```

### WebSocket

```
WS     /api/chat/ws/{group_id}?token=JWT - Real-time chat verbinding
```

## Authenticatie

Alle endpoints (behalve /health en /) vereisen een JWT token in de Authorization header:

```bash
curl -H "Authorization: Bearer YOUR_JWT_TOKEN" \
  http://localhost:8001/api/chat/groups
```

Voor WebSocket verbindingen, geef de token als query parameter:

```javascript
const ws = new WebSocket(`ws://localhost:8001/api/chat/ws/${groupId}?token=${token}`);
```

## Test Data Aanmaken

### Via MongoDB Shell

```javascript
// Start mongo shell
mongosh

// Gebruik database
use chat_db

// Maak test groep
db.groups.insertOne({
  name: "General",
  description: "General discussion",
  authorized_user_ids: ["user-123", "user-456"],
  created_at: new Date()
})

// Maak test bericht
db.messages.insertOne({
  group_id: "GROUP_ID_FROM_ABOVE",
  sender_id: "user-123",
  content: "Hello, world!",
  created_at: new Date(),
  updated_at: new Date(),
  is_deleted: false
})
```

### Via Python

```python
from motor.motor_asyncio import AsyncIOMotorClient
import asyncio

async def create_test_data():
    client = AsyncIOMotorClient("mongodb://localhost:27017")
    db = client.chat_db

    # Maak groep
    group = await db.groups.insert_one({
        "name": "General",
        "description": "Test group",
        "authorized_user_ids": ["user-123"],
        "created_at": datetime.utcnow()
    })

    print(f"Group created: {group.inserted_id}")

asyncio.run(create_test_data())
```

## WebSocket Berichten

### Client -> Server

**Ping**
```json
{
  "type": "ping"
}
```

**Typing indicator**
```json
{
  "type": "typing"
}
```

### Server -> Client

**Connected**
```json
{
  "type": "connected",
  "message": "Connected to group {group_id}",
  "user_id": "user-123"
}
```

**New message**
```json
{
  "type": "new_message",
  "message": {
    "id": "...",
    "group_id": "...",
    "sender_id": "...",
    "content": "...",
    "created_at": "...",
    "updated_at": "...",
    "is_deleted": false
  }
}
```

**Message updated**
```json
{
  "type": "message_updated",
  "message": { ... }
}
```

**Message deleted**
```json
{
  "type": "message_deleted",
  "message_id": "..."
}
```

**User joined**
```json
{
  "type": "user_joined",
  "user_id": "...",
  "connection_count": 3
}
```

## Configuratie

Alle settings worden beheerd via `.env` file of environment variables:

- `MONGODB_URL` - MongoDB connection string
- `DATABASE_NAME` - Database naam
- `JWT_SECRET` - **MOET HETZELFDE ZIJN ALS AUTH-API**
- `JWT_ALGORITHM` - JWT algoritme (default: HS256)
- `PORT` - API poort (default: 8001)
- `DEBUG` - Debug mode (true/false)

## Integratie met Auth-API

1. Zorg dat `JWT_SECRET` in beide APIs hetzelfde is
2. Gebruik de user UUIDs van auth-api in `authorized_user_ids`
3. De chat-api valideert tokens die door auth-api zijn uitgegeven

## Troubleshooting

### MongoDB connection failed

```bash
# Check of MongoDB draait
docker ps  # Als je Docker gebruikt
# OF
sudo systemctl status mongodb  # Voor Linux

# Test verbinding
mongosh mongodb://localhost:27017
```

### Import errors

```bash
# Zorg dat je in de root directory bent (waar app/ folder is)
pwd  # Moet /home/user/chat-api zijn

# En dat virtual environment actief is
which python  # Moet .../venv/bin/python zijn
```

### JWT validation fails

- Check dat `JWT_SECRET` in `.env` correct is
- Zorg dat het HETZELFDE is als in je auth-api
- Test met een verse token van auth-api

## Development

### Code Style

- Volg PEP 8
- Type hints voor alle functies
- Docstrings voor publieke functies

### Logging

De app gebruikt structured logging met correlation IDs:

```python
logger.info("message", key=value, another_key=another_value)
```

### Testing

```bash
# Installeer test dependencies
pip install pytest pytest-asyncio httpx

# Run tests
pytest
```

## Sandbox Mode

Deze setup is klaar voor sandbox gebruik:
- MongoDB draait lokaal (geen Docker vereist)
- Debug mode enabled voor development
- Auto-reload bij code changes
- Uitgebreide logging

## Productie Checklist

Voor productie deployment:

- [ ] Verander `JWT_SECRET` naar een sterke random string
- [ ] Zet `DEBUG=false`
- [ ] Configureer production MongoDB (bijv. MongoDB Atlas)
- [ ] Voeg rate limiting toe
- [ ] Setup monitoring (Prometheus/Grafana)
- [ ] Configureer HTTPS
- [ ] Review CORS origins
- [ ] Setup backup strategie voor database

## License

MIT
