# Quick Start Guide - Chat API

## Stap 1: Dependencies Installeren

```bash
pip install -r requirements.txt
```

## Stap 2: MongoDB Starten

**Optie A: Docker (Simpelst)**
```bash
docker run -d -p 27017:27017 --name mongodb mongo:latest
```

**Optie B: Lokale Installatie**
```bash
# Mac
brew install mongodb-community && brew services start mongodb-community

# Linux
sudo apt-get install mongodb && sudo systemctl start mongodb
```

## Stap 3: Environment Configureren

De `.env` file is al aangemaakt met development settings. Voor productie:

```bash
cp .env.example .env
# Edit .env en wijzig JWT_SECRET en MONGODB_URL
```

## Stap 4: Applicatie Starten

```bash
uvicorn app.main:app --reload --port 8001
```

Of via Python:

```bash
python -m app.main
```

## Stap 5: Testen

Open je browser:
- **API Docs**: http://localhost:8001/docs
- **Health Check**: http://localhost:8001/health

## Test Data Aanmaken

```javascript
// Start mongo shell
mongosh

// Gebruik database
use chat_db

// Maak test groep
db.groups.insertOne({
  name: "General",
  description: "General discussion",
  authorized_user_ids: ["test-user-123"],
  created_at: new Date()
})

// Kopieer de group ID uit de output
// Gebruik deze voor API calls
```

## API Testen (zonder authenticatie tijdelijk)

Voor development kun je tijdelijk de auth uitschakelen door in `app/routes/messages.py` en `app/routes/groups.py` de `Depends(get_current_user)` te commenten.

Of gebruik een test JWT token:

```python
# generate_token.py
from jose import jwt
from datetime import datetime, timedelta

secret = "dev-secret-key-change-in-production"
payload = {
    "sub": "test-user-123",
    "exp": datetime.utcnow() + timedelta(days=1)
}
token = jwt.encode(payload, secret, algorithm="HS256")
print(f"Token: {token}")
```

```bash
python generate_token.py

# Gebruik de token in API calls:
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:8001/api/chat/groups
```

## Veelvoorkomende Issues

### MongoDB connection failed
```bash
# Check of MongoDB draait
docker ps  # voor Docker
sudo systemctl status mongodb  # voor Linux
brew services list  # voor Mac
```

### Import errors
```bash
# Zorg dat je in de juiste directory bent
pwd  # moet /home/user/chat-api zijn

# Check Python versie
python --version  # moet 3.11+ zijn
```

### Poort al in gebruik
```bash
# Wijzig PORT in .env file
PORT=8002

# Of stop andere applicatie
lsof -ti:8001 | xargs kill
```

## Productie Deployment

1. Wijzig `JWT_SECRET` in `.env`
2. Zet `DEBUG=false`
3. Gebruik production MongoDB (bijv. MongoDB Atlas)
4. Configureer HTTPS
5. Setup monitoring

## Volgende Stappen

- Lees `README.md` voor volledige documentatie
- Check API docs op `/docs` voor alle endpoints
- Integreer met je auth-api
- Bouw een frontend client

## Handige Commands

```bash
# Dependencies updaten
pip install --upgrade -r requirements.txt

# Logs bekijken
tail -f logs/app.log  # als je file logging hebt ingesteld

# MongoDB data bekijken
mongosh chat_db
db.groups.find().pretty()
db.messages.find().limit(10).pretty()

# API health check
curl http://localhost:8001/health
```

Succes! 🚀
