# Chat API Refactoring: group → conversation

Automated refactoring scripts voor complete hernoemen van "group" naar "conversation" door de hele codebase.

## Waarom deze refactor?

**Semantische duidelijkheid**:
- Chat API gebruikt "conversation" (wat het is: een chat conversatie)
- Auth API gebruikt "group" voor RBAC (groep van gebruikers met permissions)
- Een `conversation_id` in Chat API verwijst naar een `group_id` in Auth API's RBAC systeem

## Scripts

### 1. `refactor_group_to_conversation.py`
**Doel**: Hernoem alle code references van group → conversation

**Wat het doet**:
- Rename `GroupService` → `ConversationService`
- Rename `GroupDetails` → `ConversationDetails`
- Update alle functie/methode namen
- Update alle variabele namen (`group_id` → `conversation_id`)
- Update API endpoints (`/groups/` → `/conversations/`)
- Update cache keys, log messages, docstrings
- Rename bestand: `group_service.py` → `conversation_service.py`
- Delete obsolete `test_groups.py`
- Fix alle import statements

**Scope**: ~668+ edits over 34+ Python bestanden

### 2. `migrate_mongodb_fields.py`
**Doel**: Rename MongoDB document fields

**Wat het doet**:
- Backup collection (safety first!)
- Rename `group_id` → `conversation_id` in alle documents
- Rename `group_name` → `conversation_name`
- Drop oude indexes die `group_id` gebruiken
- Create nieuwe indexes met `conversation_id`
- Verify migration succesvol

**Scope**: Alle documents in `messages` collection

## Uitvoering

### Stap 1: Preview (Dry Run)

```bash
# Code refactor preview
python migrations/refactor_group_to_conversation.py --dry-run

# MongoDB migratie preview
python migrations/migrate_mongodb_fields.py --dry-run
```

### Stap 2: Backup (Optional maar aanbevolen)

```bash
# MongoDB backup
mongodump --db chat_db --out backup_$(date +%Y%m%d_%H%M%S)

# Git commit huidige staat
git add -A
git commit -m "chore: pre-refactor checkpoint"
```

### Stap 3: Execute Refactor

```bash
# 1. Code refactor (Python bestanden)
python migrations/refactor_group_to_conversation.py --execute

# 2. MongoDB migratie (database fields)
python migrations/migrate_mongodb_fields.py --execute
```

### Stap 4: Verification

```bash
# 1. Check code changes
git diff

# 2. Run tests
pytest

# 3. Rebuild Docker
docker compose build --no-cache
docker compose restart chat-api

# 4. Test RBAC
./utils/test_rbac.sh

# 5. Check MongoDB
mongosh
use chat_db
db.messages.findOne()  # Should have conversation_id, not group_id
```

## Breaking Changes

⚠️ **API Endpoints Changed**:
- `POST /api/chat/groups/{group_id}/messages` → `POST /api/chat/conversations/{conversation_id}/messages`
- `GET /api/chat/groups/{group_id}/messages` → `GET /api/chat/conversations/{conversation_id}/messages`
- `PUT /api/chat/groups/{group_id}/messages/{id}` → `PUT /api/chat/conversations/{conversation_id}/messages/{id}`
- `DELETE /api/chat/groups/{group_id}/messages/{id}` → `DELETE /api/chat/conversations/{conversation_id}/messages/{id}`
- `WS /api/chat/ws/{group_id}` → `WS /api/chat/ws/{conversation_id}`

⚠️ **MongoDB Schema Changed**:
- Field `group_id` → `conversation_id`
- Field `group_name` → `conversation_name`
- Indexes recreated with new field names

## Rollback (if needed)

### Code Rollback
```bash
# Revert Git changes
git reset --hard HEAD~1

# Rebuild
docker compose build --no-cache
```

### MongoDB Rollback
```bash
# Restore from backup
mongorestore --db chat_db --drop backup_YYYYMMDD_HHMMSS/chat_db

# Or restore from automatic backup created by script
mongosh
use chat_db
db.messages_backup_YYYYMMDD_HHMMSS.renameCollection("messages", {dropTarget: true})
```

## Post-Refactor Checklist

- [ ] `pytest` - Alle tests slagen
- [ ] `./utils/test_rbac.sh` - RBAC werkt met nieuwe endpoints
- [ ] `docker compose up -d` - Service start zonder errors
- [ ] `curl http://localhost:8001/api/chat/conversations/{id}/messages` - Endpoints bereikbaar
- [ ] `mongosh` - Check `db.messages.findOne()` heeft `conversation_id`
- [ ] Logs - Geen "group_id" references meer
- [ ] Update clients/frontend met nieuwe API endpoints

## Dependencies

```bash
# Python dependencies (already in requirements.txt)
pip install motor pymongo
```

## Troubleshooting

### "No module named 'motor'"
```bash
pip install motor pymongo
```

### "Connection refused" bij MongoDB
```bash
# Check MongoDB running
docker ps | grep mongo

# Check MongoDB URL
echo $MONGODB_URL
```

### Code niet updated na script
```bash
# Rebuild Docker image
docker compose build --no-cache
docker compose restart chat-api
```

### Tests falen na refactor
```bash
# Check test_rbac.sh updated
grep "conversations" utils/test_rbac.sh

# Run pytest verbose
pytest -v
```

## Contact

Voor vragen of problemen: check CLAUDE.md of AUTHORIZATION.md
