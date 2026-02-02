# Sanctions Screening API

FastAPI-based sanctions screening service for i-betting platform compliance.

## Overview

This API provides sanctions screening capabilities using:
- **OpenSanctions data** via Yente matching engine
- **OFAC SDN** (US Office of Foreign Assets Control)
- **UN Security Council Sanctions**

The service is designed for i-betting platforms to comply with anti-money laundering (AML) and sanctions regulations.

## Architecture

```
┌─────────────────┐
│ Betting Backend │
└────────┬────────┘
         │ POST /v1/sanctions/screen/person
         ▼
┌─────────────────┐
│  FastAPI        │
│  Wrapper        │  ← Decision engine + thresholds
│  (This Service) │  ← Audit logging
└────────┬────────┘
         │ POST /match/{dataset}
         ▼
┌─────────────────┐
│  Yente API      │  ← Fuzzy matching
│  (Port 5000)    │  ← Entity resolution
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│ Elasticsearch   │  ← Indexed sanctions data
│  (Port 9200)    │
└─────────────────┘
```

## Directory Structure

```
C:\SANCTIONS-CHECK\
│
├── api\                          # FastAPI application (this code)
│   ├── main.py                   # Main FastAPI app
│   ├── config.py                 # Configuration management
│   ├── models.py                 # Request/Response models
│   ├── requirements.txt          # Python dependencies
│   │
│   ├── services\
│   │   ├── __init__.py
│   │   ├── yente_client.py       # Yente API client
│   │   └── decision_engine.py    # Decision logic
│   │
│   └── utils\
│       ├── __init__.py
│       └── audit_logger.py       # Audit logging system
│
├── logs\
│   ├── api\                      # API logs
│   │   └── audit\                # Audit trail logs
│   │       └── screening_YYYYMMDD.log
│   └── elasticsearch\            # Elasticsearch logs
│
├── manifest.yml                  # Yente dataset configuration
└── (other files)
```

## Setup Instructions

### Prerequisites

1. **Elasticsearch** running on `http://127.0.0.1:9200`
2. **Yente** running on `http://127.0.0.1:5000`
3. **Python 3.10+** installed

### Installation Steps

1. **Navigate to the API directory:**
   ```bash
   cd C:\SANCTIONS-CHECK\api
   ```

2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   ```

3. **Activate the virtual environment:**
   ```bash
   # Windows
   venv\Scripts\activate
   ```

4. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

5. **Verify configuration:**
   
   Edit `config.py` if you need to change:
   - Yente URL (default: `http://127.0.0.1:5000`)
   - Thresholds (default: Review=0.70, Block=0.85)
   - Log paths (default: `C:\SANCTIONS-CHECK\logs\api`)

### Running the API

**Development mode (with auto-reload):**
```bash
python main.py
```

**Production mode (using uvicorn directly):**
```bash
uvicorn main:app --host 0.0.0.0 --port 8080 --workers 4
```

The API will be available at:
- **API Base:** `http://localhost:8080`
- **Interactive Docs:** `http://localhost:8080/docs`
- **ReDoc:** `http://localhost:8080/redoc`

## API Usage

### Health Check

```bash
curl http://localhost:8080/health
```

Response:
```json
{
  "status": "healthy",
  "yente_status": "ok",
  "datasets_available": ["us_ofac_sdn", "un_sc_sanctions"],
  "timestamp": "2026-01-28T10:30:00"
}
```

### Screen a Person

**Endpoint:** `POST /v1/sanctions/screen/person`

**Minimal Request (name only):**
```bash
curl -X POST http://localhost:8080/v1/sanctions/screen/person \
  -H "Content-Type: application/json" \
  -d "{\"full_name\": \"John Doe\"}"
```

**Complete Request (recommended):**
```bash
curl -X POST http://localhost:8080/v1/sanctions/screen/person \
  -H "Content-Type: application/json" \
  -d "{
    \"full_name\": \"Hassan Nasrallah\",
    \"country\": \"LB\",
    \"date_of_birth\": \"1960-08-31\",
    \"user_id\": \"user_12345\",
    \"transaction_context\": \"withdrawal\"
  }"
```

**Response Structure:**
```json
{
  "request_id": "abc123...",
  "timestamp": "2026-01-28T10:30:00",
  "decision": "block",
  "risk_level": "critical",
  "top_score": 0.95,
  "matches": [
    {
      "entity_id": "Q123456",
      "dataset": "us_ofac_sdn",
      "caption": "Hassan NASRALLAH",
      "score": 0.95,
      "match": true,
      "names": ["Hassan NASRALLAH", "Hasan Nasrallah"],
      "countries": ["LB"],
      "birth_dates": ["1960-08-31"],
      "programs": ["SDGT"],
      "source_urls": ["https://..."]
    }
  ],
  "reasons": [
    "Top match score: 0.950 (scale: 0.0-1.0, higher = stronger match)",
    "Best match: 'Hassan NASRALLAH' from US_OFAC_SDN (Entity ID: Q123456)",
    "Sanctions programs: SDGT",
    "Total candidate matches evaluated: 5",
    "BLOCK decision: Score 0.950 >= block threshold 0.85",
    "Action required: Hard hold on withdrawal, immediate compliance review..."
  ],
  "datasets_checked": ["us_ofac_sdn", "un_sc_sanctions"],
  "metadata": {
    "total_matches_found": 5,
    "matches_returned": 5,
    "thresholds": {
      "info": 0.50,
      "review": 0.70,
      "block": 0.85
    },
    "input_fields_provided": {
      "name": true,
      "country": true,
      "dob": true,
      "passport": false,
      "national_id": false
    }
  }
}
```

### Decision Logic

The API returns one of three decisions:

| Decision | Risk Level | Action Required |
|----------|-----------|----------------|
| **clear** | none/low | Proceed with transaction |
| **review** | medium/high | Soft hold, manual review within 48h, request documents |
| **block** | critical | Hard hold, immediate compliance escalation, gather KYC |

**Thresholds (configurable in `config.py`):**
- **Info threshold:** 0.50 - Log only, no action
- **Review threshold:** 0.70 - Requires manual review
- **Block threshold:** 0.85 - Hard hold

## Testing

### Test Cases

**1. Known OFAC Match (Hassan Nasrallah):**
```json
{
  "full_name": "Hassan Nasrallah",
  "country": "LB",
  "date_of_birth": "1960-08-31"
}
```
Expected: `decision: "block"`, high score

**2. Clean Person:**
```json
{
  "full_name": "Jane Smith",
  "country": "US"
}
```
Expected: `decision: "clear"`, no matches

**3. Partial Match (Review Case):**
```json
{
  "full_name": "Mohammad Ali"
}
```
Expected: Possible low-medium score matches, may trigger review

### Using the Interactive Docs

1. Navigate to `http://localhost:8080/docs`
2. Click on `POST /v1/sanctions/screen/person`
3. Click "Try it out"
4. Enter test data
5. Click "Execute"

## Audit Logs

All screening requests are logged to:
```
C:\SANCTIONS-CHECK\logs\api\audit\screening_YYYYMMDD.log
```

**Log Format:** JSON Lines (one JSON object per line)

**Log Events:**
- `screening_request` - Incoming request details
- `yente_query` - Each Yente API call
- `matches_found` - Match results per dataset
- `screening_decision` - Final decision
- `screening_error` - Any errors

**Example Log Entry:**
```json
{
  "event_type": "screening_decision",
  "timestamp": "2026-01-28T10:30:00.123456",
  "request_id": "abc123",
  "user_id": "user_12345",
  "context": "withdrawal",
  "decision": "block",
  "risk_level": "critical",
  "top_score": 0.95,
  "total_matches": 5,
  "reasons": ["..."]
}
```

## Configuration Reference

### Environment Variables

Create `.env` file in `api/` directory (optional):

```env
# Yente Configuration
YENTE_BASE_URL=http://127.0.0.1:5000

# Decision Thresholds
THRESHOLD_INFO=0.50
THRESHOLD_REVIEW=0.70
THRESHOLD_BLOCK=0.85

# Logging
LOG_BASE_DIR=C:\SANCTIONS-CHECK\logs\api
```

### Threshold Tuning

Adjust thresholds in `config.py` based on your risk tolerance:

**Conservative (fewer false negatives):**
- Review: 0.60
- Block: 0.75

**Balanced (current defaults):**
- Review: 0.70
- Block: 0.85

**Aggressive (fewer false positives):**
- Review: 0.75
- Block: 0.90

## Integration with Betting Backend

### Withdrawal Flow

```python
import requests

# Before processing withdrawal
response = requests.post(
    "http://localhost:8080/v1/sanctions/screen/person",
    json={
        "full_name": user.full_name,
        "country": user.country,
        "date_of_birth": user.dob,
        "user_id": user.id,
        "transaction_context": "withdrawal"
    }
)

result = response.json()

if result["decision"] == "clear":
    # Proceed with withdrawal
    process_withdrawal()
    
elif result["decision"] == "review":
    # Soft hold
    create_compliance_case(result)
    notify_user_pending_review()
    
elif result["decision"] == "block":
    # Hard hold
    create_urgent_compliance_case(result)
    deny_withdrawal()
    log_suspicious_activity_report(result)
```

## Troubleshooting

### API won't start

**Check Yente connectivity:**
```bash
curl http://127.0.0.1:5000/readyz
```

**Check Elasticsearch:**
```bash
curl http://127.0.0.1:9200/_cluster/health
```

### No matches found for known sanctions targets

1. Verify Yente has indexed datasets: `GET /readyz`
2. Check manifest.yml has correct scopes
3. Verify datasets in Yente: Check Yente logs

### High false positive rate

1. Increase `THRESHOLD_REVIEW` (e.g., 0.75)
2. Provide more fields (DOB, country) in requests
3. Review audit logs to identify patterns

## Production Deployment Considerations

When deploying to production:

1. **Use environment variables** for configuration
2. **Enable HTTPS** (use reverse proxy like nginx)
3. **Add authentication** (API keys, JWT, mTLS)
4. **Set up monitoring** (health check endpoints)
5. **Configure log rotation** (already handled by RotatingFileHandler)
6. **Rate limiting** (add middleware)
7. **Caching** (Redis for repeated checks)
8. **Run multiple workers** (`uvicorn --workers 4`)

## Support

For issues or questions:
1. Check audit logs: `C:\SANCTIONS-CHECK\logs\api\audit\`
2. Verify Yente status: `curl http://localhost:8080/health`
3. Review API docs: `http://localhost:8080/docs`