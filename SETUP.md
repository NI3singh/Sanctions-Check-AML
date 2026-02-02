# Sanctions Screening System - Complete Setup Guide

Local OpenSanctions **Yente** API + **Elasticsearch** backend for Windows with Docker.

## System Architecture

```
C:\SANCTIONS-CHECK\           → Configuration, logs, code
D:\SANCTIONS-DATA\            → Persistent data (Elasticsearch indices)
Docker Network: sanctions-net → Internal container communication
Elasticsearch: 127.0.0.1:9200 → Container name: sanctions-es
Yente API: 127.0.0.1:5000     → Container name: yente (internal port 8000)
```

---

## Prerequisites

### Required Software
- **Docker Desktop** (Linux containers mode)
- **PowerShell** (Windows built-in)
- **curl.exe** (Windows built-in)
- **Python 3.10+** (optional, for pretty-printing JSON)

### Docker Desktop Configuration
**IMPORTANT:** Enable file sharing for drives C: and D:
1. Open Docker Desktop
2. Settings → Resources → File Sharing
3. Add `C:\` and `D:\` if not already listed
4. Apply & Restart

---

## Step 1: Create Directory Structure

Run in PowerShell as Administrator:

```powershell
# C: drive - Configuration and logs
mkdir C:\SANCTIONS-CHECK -Force | Out-Null
mkdir C:\SANCTIONS-CHECK\logs -Force | Out-Null
mkdir C:\SANCTIONS-CHECK\logs\elasticsearch -Force | Out-Null
mkdir C:\SANCTIONS-CHECK\logs\yente -Force | Out-Null

# D: drive - Persistent data storage
mkdir D:\SANCTIONS-DATA -Force | Out-Null
mkdir D:\SANCTIONS-DATA\elasticsearch\data -Force | Out-Null

# Optional: Dataset storage structure (for future use)
mkdir D:\SANCTIONS-DATA\datasets\raw\ofac -Force | Out-Null
mkdir D:\SANCTIONS-DATA\datasets\raw\un -Force | Out-Null
mkdir D:\SANCTIONS-DATA\datasets\normalized -Force | Out-Null
mkdir D:\SANCTIONS-DATA\datasets\archive -Force | Out-Null

Write-Host "Directory structure created successfully" -ForegroundColor Green
```

**Verify:**
```powershell
Test-Path C:\SANCTIONS-CHECK
Test-Path D:\SANCTIONS-DATA\elasticsearch\data
# Both should return: True
```

---

## Step 2: Create Docker Network

```powershell
docker network create sanctions-net
```

**Expected output:**
- First time: `<network-id>` (success)
- If exists: `Error response from daemon: network with name sanctions-net already exists` (this is fine)

**Verify:**
```powershell
docker network ls | Select-String "sanctions-net"
```

---

## Step 3: Start Elasticsearch

### Pull Image

```powershell
docker pull docker.elastic.co/elasticsearch/elasticsearch:8.11.3
```

### Run Container

```powershell
docker run -d `
  --name sanctions-es `
  --restart unless-stopped `
  --network sanctions-net `
  -p 127.0.0.1:9200:9200 `
  -e "discovery.type=single-node" `
  -e "xpack.security.enabled=false" `
  -e "xpack.security.http.ssl.enabled=false" `
  -e "ES_JAVA_OPTS=-Xms1g -Xmx1g" `
  -v "D:\SANCTIONS-DATA\elasticsearch\data:/usr/share/elasticsearch/data" `
  -v "C:\SANCTIONS-CHECK\logs\elasticsearch:/usr/share/elasticsearch/logs" `
  docker.elastic.co/elasticsearch/elasticsearch:8.11.3
```

**Configuration Explained:**
- `--name sanctions-es` - Container name (used by Yente for internal connection)
- `--network sanctions-net` - Connects to custom network
- `-p 127.0.0.1:9200:9200` - Binds to localhost only (not exposed externally)
- `discovery.type=single-node` - Single-node cluster (no clustering)
- `xpack.security.enabled=false` - Disables authentication (local use only)
- `ES_JAVA_OPTS=-Xms1g -Xmx1g` - Allocates 1GB RAM (adjust based on your system)
- Volumes map data and logs to persistent storage

### Wait for Startup

```powershell
# Watch logs (Ctrl+C to exit)
docker logs sanctions-es -f

# Or check last 50 lines
docker logs sanctions-es --tail 50
```

**Look for:**
```
"message":"started"
```

### Verify Elasticsearch is Running

```powershell
# Basic health check
curl.exe http://127.0.0.1:9200

# Cluster health (should show yellow or green)
curl.exe "http://127.0.0.1:9200/_cluster/health?pretty"

# List indices (will be empty initially)
curl.exe "http://127.0.0.1:9200/_cat/indices?v"
```

**Expected Health Status:**
- `yellow` - Normal for single-node (replicas can't allocate)
- `green` - All good (unlikely in single-node)
- `red` - Problem (check logs)

---

## Step 4: Create Yente Manifest

This configuration tells Yente which sanctions datasets to index.

```powershell
@"
catalogs:
  - url: https://data.opensanctions.org/datasets/latest/index.json
    resource_name: entities.ftm.json
    scopes:
      - us_ofac_sdn
      - un_sc_sanctions
"@ | Set-Content -Encoding utf8 C:\SANCTIONS-CHECK\manifest.yml
```

**What this does:**
- Fetches the OpenSanctions catalog index
- Downloads latest versions of OFAC SDN and UN SC Sanctions
- Auto-updates when new dataset versions are published

**Verify file created:**
```powershell
Get-Content C:\SANCTIONS-CHECK\manifest.yml
```

---

## Step 5: Start Yente

### Pull Latest Image

```powershell
docker pull ghcr.io/opensanctions/yente:latest
```

### Remove Old Container (if exists)

```powershell
docker rm -f yente 2>$null
```

### Run Yente Container

```powershell
docker run -d `
  --name yente `
  --restart unless-stopped `
  --network sanctions-net `
  -e "YENTE_INDEX_URL=http://sanctions-es:9200" `
  -e "YENTE_MANIFEST=/data/manifest.yml" `
  -e "YENTE_AUTO_REINDEX=true" `
  -p 127.0.0.1:5000:8000 `
  -v "C:\SANCTIONS-CHECK\logs\yente:/app/logs" `
  -v "C:\SANCTIONS-CHECK\manifest.yml:/data/manifest.yml:ro" `
  ghcr.io/opensanctions/yente:latest
```

**Configuration Explained:**
- `YENTE_INDEX_URL=http://sanctions-es:9200` - Connects to Elasticsearch via Docker network
- `YENTE_MANIFEST=/data/manifest.yml` - Points to dataset configuration
- `YENTE_AUTO_REINDEX=true` - Auto-reindexes when datasets update
- `-p 127.0.0.1:5000:8000` - **CRITICAL:** Maps host port 5000 to container port 8000
- Volumes mount logs and manifest into container

**IMPORTANT PORT MAPPING:**
- Yente listens on port **8000** inside the container
- We map it to port **5000** on the host
- Incorrect mapping (5000:5000) causes "Empty reply from server"

### Monitor Indexing Process

```powershell
# Follow logs in real-time
docker logs yente -f

# Or check last 100 lines
docker logs yente --tail 100
```

**What to look for:**
```
INFO Indexing entities ... dataset=us_ofac_sdn
INFO Indexed 12345 entities dataset=us_ofac_sdn
INFO Index is now aliased to: yente-entities
INFO Indexing entities ... dataset=un_sc_sanctions
INFO Indexed 6789 entities dataset=un_sc_sanctions
```

**Indexing time:** 2-10 minutes depending on internet speed and system performance.

---

## Step 6: Verify Yente is Ready

### Check Container Status

```powershell
docker ps --filter "name=yente"
```

Should show STATUS as `Up` with port `0.0.0.0:5000->8000/tcp`

### Test OpenAPI Endpoint

```powershell
curl.exe -I http://127.0.0.1:5000/openapi.json
```

**Expected:** `HTTP/1.1 200 OK`

### Check Readiness

```powershell
curl.exe http://127.0.0.1:5000/readyz
```

**During indexing:**
```json
{"detail":"Index not ready."}
```
Status: 503

**After indexing completes:**
```json
{"status":"ok"}
```
Status: 200

**Wait until you get `{"status":"ok"}` before proceeding.**

---

## Step 7: Test Sanctions Matching

### Create Test Request File

```powershell
@'
{
  "queries": {
    "q1": {
      "schema": "Person",
      "properties": {
        "name": ["HASSAN NASRALLAH"]
      }
    }
  }
}
'@ | Set-Content -Encoding utf8 C:\SANCTIONS-CHECK\test_request.json
```

**IMPORTANT:** The request format is:
- `queries` must be an **object/dictionary**, not an array
- Each query has a key (e.g., "q1")
- Schema must be "Person" for individual screening

### Test OFAC SDN Matching

```powershell
curl.exe -X POST http://127.0.0.1:5000/match/us_ofac_sdn `
  -H "Content-Type: application/json" `
  --data-binary "@C:\SANCTIONS-CHECK\test_request.json" | python -m json.tool
```

**Expected response:**
```json
{
  "responses": {
    "q1": {
      "query": {...},
      "results": [
        {
          "id": "...",
          "caption": "Hassan NASRALLAH",
          "score": 0.95,
          "match": true,
          "properties": {
            "name": ["Hassan NASRALLAH"],
            "country": ["LB"],
            ...
          }
        }
      ],
      "status": 200
    }
  }
}
```

### Test UN Sanctions Matching

```powershell
curl.exe -X POST http://127.0.0.1:5000/match/un_sc_sanctions `
  -H "Content-Type: application/json" `
  --data-binary "@C:\SANCTIONS-CHECK\test_request.json" | python -m json.tool
```

### Test Clean Name (No Match Expected)

```powershell
@'
{
  "queries": {
    "q1": {
      "schema": "Person",
      "properties": {
        "name": ["Jane Smith"]
      }
    }
  }
}
'@ | Set-Content -Encoding utf8 C:\SANCTIONS-CHECK\clean_test.json

curl.exe -X POST http://127.0.0.1:5000/match/us_ofac_sdn `
  -H "Content-Type: application/json" `
  --data-binary "@C:\SANCTIONS-CHECK\clean_test.json" | python -m json.tool
```

**Expected:** `"results": []` (empty array, no matches)

---

## Step 8: Download API Specification

```powershell
curl.exe http://127.0.0.1:5000/openapi.json -o C:\SANCTIONS-CHECK\openapi.json

# View available endpoints
python -c "import json; d=json.load(open(r'C:\SANCTIONS-CHECK\openapi.json',encoding='utf-8')); print('\n'.join(sorted(d['paths'].keys())))"
```

**Available endpoints:**
```
/entities/{entity_id}
/healthz
/match/{dataset}
/openapi.json
/readyz
/reconcile/{dataset}
/search/{dataset}
```

---

## How the System Works

### Request Flow

```
1. Client (your API wrapper)
   ↓ POST /match/us_ofac_sdn
2. Yente API (port 5000)
   ↓ Converts to structured query
3. Yente queries Elasticsearch (internal: sanctions-es:9200)
   ↓ Text search, fuzzy matching
4. Elasticsearch returns candidate entities
   ↓
5. Yente scores candidates
   ↓ Name similarity, phonetics, DOB/country matching
6. Yente returns scored results
   ↑
7. Client receives matches with scores and explanations
```

### Data Persistence

- **Elasticsearch indices:** `D:\SANCTIONS-DATA\elasticsearch\data`
- **Yente logs:** `C:\SANCTIONS-CHECK\logs\yente`
- **Elasticsearch logs:** `C:\SANCTIONS-CHECK\logs\elasticsearch`

**Containers can be restarted without losing indexed data.**

---

## Container Management

### View Running Containers

```powershell
docker ps
```

### Stop Containers

```powershell
docker stop yente sanctions-es
```

### Start Containers

```powershell
docker start sanctions-es
docker start yente
```

### Restart Containers

```powershell
docker restart sanctions-es
docker restart yente
```

### View Logs

```powershell
# Elasticsearch
docker logs sanctions-es --tail 100

# Yente
docker logs yente --tail 100

# Follow logs (Ctrl+C to stop)
docker logs yente -f
```

### Check Resource Usage

```powershell
docker stats sanctions-es yente
```

---

## Troubleshooting

### Issue 1: Empty reply from server on port 5000

**Cause:** Wrong port mapping (mapped 5000:5000 instead of 5000:8000)

**Fix:**
```powershell
docker rm -f yente
# Then re-run Step 5 with correct mapping: -p 127.0.0.1:5000:8000
```

### Issue 2: Yente stuck at "Index not ready" (503)

**Causes:**
- Indexing still in progress (wait 5-10 minutes)
- Elasticsearch unreachable
- Dataset download failed

**Checks:**
```powershell
# Check Yente logs for errors
docker logs yente --tail 200

# Verify Elasticsearch is healthy
curl.exe "http://127.0.0.1:9200/_cluster/health?pretty"

# Check if Yente can reach ES
docker exec yente curl -s http://sanctions-es:9200
```

### Issue 3: Elasticsearch returns 403 (read-only)

**Cause:** Disk space low, triggered read-only mode

**Fix:**
```powershell
# Create unlock settings file
'{"index.blocks.read_only":false,"index.blocks.read_only_allow_delete":false}' `
  | Set-Content -Encoding ascii C:\SANCTIONS-CHECK\es_unlock.json

# Apply settings
curl.exe -X PUT "http://127.0.0.1:9200/_all/_settings" `
  -H "Content-Type: application/json" `
  --data-binary "@C:\SANCTIONS-CHECK\es_unlock.json"

# Free up disk space, then restart ES
docker restart sanctions-es
```

### Issue 4: "Cannot identify resource" in Yente logs

**Cause:** Old manifest format or incorrect dataset URLs

**Fix:** Use catalog-based manifest (Step 4), not direct dataset URLs

### Issue 5: Elasticsearch won't start / permission errors

**Cause:** Data directory permissions or Docker file sharing

**Fix:**
```powershell
# Stop ES
docker stop sanctions-es

# Remove data directory
Remove-Item -Recurse -Force D:\SANCTIONS-DATA\elasticsearch\data\*

# Verify Docker has access to D: drive (Settings → Resources → File Sharing)

# Restart ES
docker start sanctions-es
```

### Issue 6: Yente returns validation error on request

**Cause:** Request format incorrect (queries as array instead of object)

**Correct format:**
```json
{
  "queries": {
    "q1": {...}
  }
}
```

**Incorrect format:**
```json
{
  "queries": [
    {...}
  ]
}
```

### Issue 7: Performance is slow

**Elasticsearch memory:**
```powershell
# Allocate more RAM (e.g., 2GB instead of 1GB)
docker stop sanctions-es
docker rm sanctions-es

# Re-run Step 3 with:
# -e "ES_JAVA_OPTS=-Xms2g -Xmx2g"
```

---

## Complete Reset (Nuclear Option)

If everything is broken and you want to start fresh:

```powershell
# Stop and remove containers
docker stop yente sanctions-es
docker rm yente sanctions-es

# Remove Elasticsearch data (loses indexed datasets)
Remove-Item -Recurse -Force D:\SANCTIONS-DATA\elasticsearch\data\*

# Remove logs (optional)
Remove-Item -Recurse -Force C:\SANCTIONS-CHECK\logs\*

# Start from Step 3 (Elasticsearch)
```

**WARNING:** This deletes all indexed data. Yente will need to re-download and re-index datasets (5-10 minutes).

---

## What You Have After Setup

### Services Running

| Service | URL | Purpose |
|---------|-----|---------|
| Elasticsearch | http://127.0.0.1:9200 | Data storage |
| Yente API | http://127.0.0.1:5000 | Matching engine |

### Available Endpoints

- `GET /readyz` - Service readiness check
- `GET /healthz` - Health check
- `POST /match/us_ofac_sdn` - Match against OFAC
- `POST /match/un_sc_sanctions` - Match against UN
- `GET /openapi.json` - API specification

### Indexed Datasets

- **OFAC SDN** (US Office of Foreign Assets Control)
- **UN SC Sanctions** (United Nations Security Council)

### Persistent Data

- Elasticsearch indices in `D:\SANCTIONS-DATA\elasticsearch\data`
- Logs in `C:\SANCTIONS-CHECK\logs\`
- Configuration in `C:\SANCTIONS-CHECK\manifest.yml`

---

## Next Steps

1. **Verify everything works:** Run all tests in Step 7
2. **Install FastAPI wrapper:** See `QUICKSTART.md` in the `api/` folder
3. **Integrate with betting backend:** Use the wrapper's `/v1/sanctions/screen/person` endpoint

---

## Maintenance

### Update Datasets

Yente auto-updates with `YENTE_AUTO_REINDEX=true`. To force immediate update:

```powershell
docker restart yente
```

Watch logs to see reindexing:
```powershell
docker logs yente -f
```

### Monitor Disk Space

Check Elasticsearch data size:
```powershell
Get-ChildItem D:\SANCTIONS-DATA\elasticsearch\data -Recurse | Measure-Object -Property Length -Sum
```

### Backup

To backup indexed data:
```powershell
# Stop Elasticsearch
docker stop sanctions-es

# Copy data directory
Copy-Item -Recurse D:\SANCTIONS-DATA\elasticsearch\data D:\SANCTIONS-DATA\backup_YYYYMMDD

# Restart
docker start sanctions-es
```

---

## System Requirements

### Minimum

- **CPU:** 2 cores
- **RAM:** 4 GB (2 GB for ES, 1 GB for Yente, 1 GB for OS)
- **Disk:** 10 GB free (5 GB for ES data, 5 GB for datasets/logs)

### Recommended

- **CPU:** 4 cores
- **RAM:** 8 GB
- **Disk:** 20 GB free
- **SSD** for better Elasticsearch performance

---

## Security Notes

**This setup is for LOCAL DEVELOPMENT ONLY.**

Security features disabled:
- Elasticsearch authentication (`xpack.security.enabled=false`)
- SSL/TLS encryption
- Network exposure (bound to 127.0.0.1)

**For production:**
1. Enable Elasticsearch security
2. Use HTTPS reverse proxy
3. Implement API authentication
4. Use proper network isolation
5. Enable firewall rules

---

## Setup Verification Checklist

- [ ] Directories created on C: and D: drives
- [ ] Docker network `sanctions-net` exists
- [ ] Elasticsearch container running on port 9200
- [ ] Elasticsearch health check returns success
- [ ] Yente container running on port 5000
- [ ] Yente `/readyz` returns `{"status":"ok"}`
- [ ] OFAC test request returns matches
- [ ] UN test request works
- [ ] Clean name test returns no matches
- [ ] Logs being written to `C:\SANCTIONS-CHECK\logs\`

**If all checkboxes are ticked, setup is complete and working correctly.**