# Quick Start Guide

Get the Sanctions Screening API running in 5 minutes.

## Prerequisites Check

Before starting, verify these services are running:

```bash
# 1. Check Elasticsearch
curl http://127.0.0.1:9200/_cluster/health
# Should return: {"status":"yellow",...} or {"status":"green",...}

# 2. Check Yente
curl http://127.0.0.1:5000/readyz
# Should return: {"status":"ok"}
```

If either fails, start the required services first.

## Setup Steps

### 1. Create Directory Structure

```bash
# Navigate to SANCTIONS-CHECK directory
cd C:\SANCTIONS-CHECK

# Create API directory
mkdir api
cd api

# Create subdirectories
mkdir services
mkdir utils
mkdir logs
```

### 2. Copy All Files

Copy all the provided files to their locations:

```
C:\SANCTIONS-CHECK\api\
├── main.py
├── config.py
├── models.py
├── requirements.txt
├── .env.example
├── README.md
├── QUICKSTART.md (this file)
│
├── services\
│   ├── __init__.py
│   ├── yente_client.py
│   └── decision_engine.py
│
└── utils\
    ├── __init__.py
    └── audit_logger.py
```

### 3. Create Virtual Environment

```bash
# In C:\SANCTIONS-CHECK\api\
python -m venv venv
```

### 4. Activate Virtual Environment

```bash
# Windows Command Prompt
venv\Scripts\activate.bat

# Windows PowerShell
venv\Scripts\Activate.ps1

# You should see (venv) in your prompt
```

### 5. Install Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

Expected output:
```
Successfully installed fastapi-0.115.6 uvicorn-0.30.6 httpx-0.27.2 pydantic-2.10.5 ...
```

### 6. Verify Installation

```bash
python -c "import fastapi; import httpx; import pydantic; print('All dependencies OK')"
# Should print: All dependencies OK
```

### 7. Start the API

```bash
python main.py
```

Expected output:
```
============================================================
Starting Sanctions Screening API v1.0.0
============================================================
Yente URL: http://127.0.0.1:5000
Datasets: us_ofac_sdn, un_sc_sanctions
Thresholds: Review=0.7, Block=0.85
Audit logs: C:\SANCTIONS-CHECK\logs\api
============================================================

Yente status: ok

INFO:     Started server process [12345]
INFO:     Waiting for application startup.
INFO:     Application startup complete.
INFO:     Uvicorn running on http://0.0.0.0:8080
```

### 8. Test the API

**Open a new terminal** and run these tests:

**Test 1: Health Check**
```bash
curl http://localhost:8080/health
```

Expected response:
```json
{
  "status": "healthy",
  "yente_status": "ok",
  "datasets_available": ["us_ofac_sdn", "un_sc_sanctions"],
  "timestamp": "2026-01-28T..."
}
```

**Test 2: Screen a Clean Person**
```bash
curl -X POST http://localhost:8080/v1/sanctions/screen/person ^
  -H "Content-Type: application/json" ^
  -d "{\"full_name\": \"Jane Smith\", \"country\": \"US\"}"
```

Expected: `"decision": "clear"`

**Test 3: Screen a Known Sanctioned Person**
```bash
curl -X POST http://localhost:8080/v1/sanctions/screen/person ^
  -H "Content-Type: application/json" ^
  -d "{\"full_name\": \"Hassan Nasrallah\", \"country\": \"LB\", \"date_of_birth\": \"1960-08-31\"}"
```

Expected: `"decision": "block"`, `"risk_level": "critical"`

### 9. View Interactive Documentation

Open your browser and visit:

**Swagger UI:** http://localhost:8080/docs

Here you can:
- See all endpoints
- Try requests interactively
- View request/response schemas

## Verify Audit Logs

After running tests, check the audit logs:

```bash
# Navigate to logs directory
cd C:\SANCTIONS-CHECK\logs\api\audit

# View today's log file
type screening_20260128.log
```

You should see JSON lines for each request.

## Common Issues

### Issue: "Cannot connect to Yente service"

**Solution:**
```bash
# 1. Check if Yente is running
docker ps | findstr yente

# 2. Check Yente health
curl http://127.0.0.1:5000/readyz

# 3. Restart Yente if needed
docker restart yente
```

### Issue: "ModuleNotFoundError: No module named 'fastapi'"

**Solution:**
```bash
# Make sure virtual environment is activated
# You should see (venv) in your prompt

# If not activated:
venv\Scripts\activate

# Reinstall dependencies
pip install -r requirements.txt
```

### Issue: Port 8080 already in use

**Solution:**

Edit `config.py` and change:
```python
API_PORT: int = 8081  # Or any other free port
```

Or use environment variable:
```bash
set API_PORT=8081
python main.py
```

### Issue: Logs directory not created

**Solution:**

The API creates log directories automatically, but if there's a permission issue:

```bash
mkdir C:\SANCTIONS-CHECK\logs\api
mkdir C:\SANCTIONS-CHECK\logs\api\audit
```

## Next Steps

1. **Integrate with your betting backend** - See README.md section "Integration with Betting Backend"

2. **Tune thresholds** - Adjust in `config.py` based on your false positive tolerance

3. **Add authentication** - Implement API key or JWT auth before exposing externally

4. **Monitor logs** - Set up log monitoring/alerting for production

5. **Performance testing** - Test with realistic load (concurrent requests)

## Testing Checklist

- [ ] Elasticsearch is running and healthy
- [ ] Yente is running and ready
- [ ] Virtual environment created and activated
- [ ] Dependencies installed successfully
- [ ] API starts without errors
- [ ] Health check returns "healthy"
- [ ] Clean person returns "clear"
- [ ] Known sanctions target returns "block"
- [ ] Audit logs are being written
- [ ] Interactive docs accessible at /docs

## Quick Commands Reference

```bash
# Start API
python main.py

# Start API with custom port
set API_PORT=8081 && python main.py

# Run with production server (4 workers)
uvicorn main:app --host 0.0.0.0 --port 8080 --workers 4

# Test health
curl http://localhost:8080/health

# Screen person (Windows CMD)
curl -X POST http://localhost:8080/v1/sanctions/screen/person ^
  -H "Content-Type: application/json" ^
  -d "{\"full_name\": \"John Doe\"}"

# View logs
type C:\SANCTIONS-CHECK\logs\api\audit\screening_*.log
```

## You're Ready!

The API is now running and ready to receive screening requests from your betting platform backend.

For detailed documentation, see `README.md`.