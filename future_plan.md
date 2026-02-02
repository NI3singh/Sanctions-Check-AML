([Past chat][1])([Past chat][2])([Past chat][3])

## Current status (what is already done and working)

* **Elasticsearch** is running in Docker and reachable from the host (`127.0.0.1:9200`).
* **Yente** is running in Docker, connected to Elasticsearch via the Docker network, and exposed on the host (`127.0.0.1:5000` mapped to container `8000`).
* `GET http://127.0.0.1:5000/readyz` returns `{"status":"ok"}` meaning **indices exist and Yente is ready**.
* `POST /match/us_ofac_sdn` works and returns matches (your “HASSAN NASRALLAH” test returned an OFAC match with score and features).
* `POST /match/un_sc_sanctions` also works now (your later message confirms you got results).

So the “sanctions search engine” part is working.

---

## What you must build next (so backend team can actually use it)

You need two additional layers:

1. **Deployment layer**: run this stack on a server that the i-betting backend can reach

* Right now everything is on your local machine (`127.0.0.1`). That address is only valid on your own machine.
* Backend team needs a stable internal URL like `http://sanctions-service:8080/...` or `https://sanctions.company.internal/...`.

2. **Decision layer (wrapper service)**: a small API you own that:

* accepts your application’s user details (name, DOB, country, ids, address, etc.)
* calls Yente internally
* applies your rules to decide: `CLEAR / REVIEW / BLOCK`
* returns a clean response format for backend + dashboard
* logs the request + decision (audit trail)

Yente is the matcher/search engine. Your wrapper is the “brain” + integration contract.

---

## Target end-state (what you hand to backend team)

Backend team calls **one endpoint** you control:

* `POST /v1/sanctions/screen/person`
  They send user details; you respond with:
* `decision`: `clear|review|block`
* `risk_score`: 0–100 (optional)
* `matches`: top matches with dataset, score, entity id, summary
* `reasons`: human-readable rule explanations
* `request_id`: for auditing/dashboard linking

Backend does not call Yente directly.

---

## Step-by-step plan from “today” to “usable module” (Python/FastAPI)

### Step 1 — Freeze the working setup into Docker Compose (repeatable deployment)

Stop using long `docker run ...` commands. Put everything into `docker-compose.yml` so it can be deployed on any server exactly the same way.

Create: `C:\SANCTIONS-CHECK\deploy\docker-compose.yml`

```yaml
services:
  elasticsearch:
    image: docker.elastic.co/elasticsearch/elasticsearch:8.12.0
    container_name: sanctions-es
    environment:
      - discovery.type=single-node
      - xpack.security.enabled=false
      - ES_JAVA_OPTS=-Xms2g -Xmx2g
    ports:
      - "9200:9200"
    volumes:
      - D:/SANCTIONS-DATA/elasticsearch/data:/usr/share/elasticsearch/data
    networks:
      - sanctions-net

  yente:
    image: ghcr.io/opensanctions/yente:latest
    container_name: yente
    depends_on:
      - elasticsearch
    environment:
      - YENTE_INDEX_URL=http://sanctions-es:9200
      - YENTE_MANIFEST=/data/manifest.yml
      - YENTE_AUTO_REINDEX=true
    ports:
      - "5000:8000"
    volumes:
      - C:/SANCTIONS-CHECK/logs/yente:/app/logs
      - C:/SANCTIONS-CHECK/manifest.yml:/data/manifest.yml:ro
    networks:
      - sanctions-net

  sanctions-wrapper:
    build: ./sanctions-wrapper
    container_name: sanctions-wrapper
    depends_on:
      - yente
    environment:
      - YENTE_BASE_URL=http://yente:8000
      - DATASETS=us_ofac_sdn,un_sc_sanctions
      - DECISION_BLOCK_SCORE=0.90
      - DECISION_REVIEW_SCORE=0.75
    ports:
      - "8080:8080"
    networks:
      - sanctions-net

networks:
  sanctions-net:
    name: sanctions-net
```

Reason:

* repeatability
* easy move from laptop → staging server → production server
* wrapper can call Yente by container name (`http://yente:8000`) reliably

Run (from that folder):

```powershell
docker compose up -d --build
```

---

### Step 2 — Use a correct manifest format (the format you ended up using is the right direction)

The “datasets:” manifest caused “cannot identify resource” warnings earlier because Yente expects catalog/index-driven metadata for versioning. The working approach is:

```yaml
catalogs:
  - url: https://data.opensanctions.org/datasets/latest/index.json
    resource_name: entities.ftm.json
    scopes:
      - us_ofac_sdn
      - un_sc_sanctions
```

Reason:

* `latest/index.json` tells Yente the **actual current dataset build path** (date-stamped URLs)
* Yente can see dataset version metadata and reindex correctly when updates happen
* you avoid hardcoding dated dataset URLs

---

### Step 3 — Implement the wrapper API (FastAPI) that backend will call

Create folder:
`C:\SANCTIONS-CHECK\deploy\sanctions-wrapper\`

#### 3.1 `requirements.txt`

```txt
fastapi==0.115.6
uvicorn[standard]==0.30.6
httpx==0.27.2
pydantic==2.10.5
python-dotenv==1.0.1
```

#### 3.2 `main.py` (MVP: person screening only, 2 datasets)

```python
import os
import uuid
from typing import Any, Dict, List, Literal, Optional

import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

YENTE_BASE_URL = os.getenv("YENTE_BASE_URL", "http://127.0.0.1:5000").rstrip("/")
DATASETS = [d.strip() for d in os.getenv("DATASETS", "us_ofac_sdn,un_sc_sanctions").split(",") if d.strip()]
BLOCK_SCORE = float(os.getenv("DECISION_BLOCK_SCORE", "0.90"))
REVIEW_SCORE = float(os.getenv("DECISION_REVIEW_SCORE", "0.75"))

app = FastAPI(title="Sanctions Screening Wrapper", version="1.0.0")


class PersonInput(BaseModel):
    full_name: str = Field(..., min_length=2)
    country: Optional[str] = Field(None, description="ISO2 like 'in', 'lb', etc.")
    dob: Optional[str] = Field(None, description="YYYY-MM-DD if known")
    passport_number: Optional[str] = None
    national_id: Optional[str] = None
    request_id: Optional[str] = None


class MatchEntity(BaseModel):
    dataset: str
    entity_id: str
    caption: str
    score: float
    match: bool
    properties: Dict[str, Any] = {}
    source_urls: List[str] = []


class ScreenResponse(BaseModel):
    request_id: str
    decision: Literal["clear", "review", "block"]
    top_score: float
    matches: List[MatchEntity]
    reasons: List[str]


def build_yente_query(person: PersonInput) -> Dict[str, Any]:
    props: Dict[str, List[Any]] = {"name": [person.full_name]}

    # Add optional signals if available. These improve matching confidence.
    if person.country:
        props["country"] = [person.country.lower()]
    if person.dob:
        props["birthDate"] = [person.dob]
    if person.passport_number:
        props["passportNumber"] = [person.passport_number]
    if person.national_id:
        # Different datasets store different identifier properties; keep as weak signal.
        props["idNumber"] = [person.national_id]

    return {
        "queries": {
            "q1": {
                "schema": "Person",
                "properties": props
            }
        }
    }


def decide(matches: List[MatchEntity]) -> (str, float, List[str]):
    if not matches:
        return "clear", 0.0, ["No candidate matches returned by Yente."]

    top = max(m.score for m in matches)
    best = max(matches, key=lambda m: m.score)

    reasons: List[str] = []
    reasons.append(f"Top match score={top:.3f} from dataset={best.dataset}, entity_id={best.entity_id}.")

    # Hard rules (MVP):
    # - block if score >= BLOCK_SCORE
    # - review if score >= REVIEW_SCORE
    # - else clear
    if top >= BLOCK_SCORE:
        reasons.append(f"Score >= {BLOCK_SCORE:.2f} threshold -> BLOCK.")
        return "block", top, reasons

    if top >= REVIEW_SCORE:
        reasons.append(f"Score >= {REVIEW_SCORE:.2f} threshold -> REVIEW.")
        return "review", top, reasons

    reasons.append("Score below review threshold -> CLEAR.")
    return "clear", top, reasons


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/v1/sanctions/screen/person", response_model=ScreenResponse)
async def screen_person(person: PersonInput):
    rid = person.request_id or str(uuid.uuid4())
    payload = build_yente_query(person)

    all_matches: List[MatchEntity] = []

    timeout = httpx.Timeout(10.0, connect=5.0)
    async with httpx.AsyncClient(timeout=timeout) as client:
        # Ensure Yente is ready
        rz = await client.get(f"{YENTE_BASE_URL}/readyz")
        if rz.status_code != 200:
            raise HTTPException(status_code=503, detail="Yente not ready")

        for ds in DATASETS:
            resp = await client.post(f"{YENTE_BASE_URL}/match/{ds}", json=payload)
            if resp.status_code != 200:
                raise HTTPException(status_code=502, detail=f"Yente error for dataset {ds}: {resp.text}")

            data = resp.json()
            results = data.get("responses", {}).get("q1", {}).get("results", [])

            for r in results:
                props = r.get("properties", {}) or {}
                srcs = props.get("sourceUrl", []) or []
                all_matches.append(
                    MatchEntity(
                        dataset=ds,
                        entity_id=r.get("id", ""),
                        caption=r.get("caption", ""),
                        score=float(r.get("score", 0.0)),
                        match=bool(r.get("match", False)),
                        properties=props,
                        source_urls=list(srcs),
                    )
                )

    # Sort matches by score desc, keep top N (MVP)
    all_matches.sort(key=lambda m: m.score, reverse=True)
    top_matches = all_matches[:5]

    decision, top_score, reasons = decide(top_matches)
    return ScreenResponse(
        request_id=rid,
        decision=decision,
        top_score=top_score,
        matches=top_matches,
        reasons=reasons,
    )
```

#### 3.3 `Dockerfile`

```dockerfile
FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8080
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]
```

Reason:

* backend team gets a stable contract and does not deal with Yente’s raw schema
* you control thresholds, logging, and how to interpret matches
* you can evolve logic without breaking backend

---

### Step 4 — How the runtime flow works (what happens on a withdrawal)

Example request to your wrapper:

```http
POST http://<server>:8080/v1/sanctions/screen/person
Content-Type: application/json

{
  "full_name": "HASSAN NASRALLAH",
  "country": "lb",
  "dob": "1960-08-31"
}
```

Internal pipeline:

1. **Wrapper** receives request, generates `request_id`, builds a Yente query object.
2. Wrapper calls `GET yente/readyz`. If not ready → returns 503 to backend.
3. Wrapper calls:

   * `POST yente/match/us_ofac_sdn`
   * `POST yente/match/un_sc_sanctions`
4. **Yente**:

   * reads query
   * runs matching logic (name similarity, phonetic, identifiers, etc.)
   * queries **Elasticsearch indices** that contain the sanctioned entities
   * returns candidate matches + score + features/explanations
5. Wrapper:

   * merges matches across datasets
   * applies your decision rules (block/review/clear)
   * returns a clean response to backend
6. Backend:

   * if `block` → block withdrawal immediately and flag account
   * if `review` → hold withdrawal and create a case for compliance
   * if `clear` → proceed

---

## Flow diagram (single request)

```
[ i-betting backend ]
        |
        |  POST /v1/sanctions/screen/person  (name, dob, country, ids)
        v
[ Sanctions Wrapper (FastAPI) ]
        |
        |  GET /readyz
        v
[ Yente API ]
        |
        |  Elasticsearch queries (indexes for us_ofac_sdn + un_sc_sanctions)
        v
[ Elasticsearch ]
        |
        |  candidate hits + scores
        v
[ Yente API ]
        |
        |  results + explanations
        v
[ Sanctions Wrapper ]
        |
        |  rules engine => CLEAR / REVIEW / BLOCK
        v
[ i-betting backend + dashboard ]
```

---

## Why your earlier JSON failed (so you can recognize it instantly)

* Yente `/match/{dataset}` expects:

  * `queries` as a **dictionary** keyed by query ids (`q1`, `q2`, …)
  * each query contains `schema` + `properties`
* Your failing payload used `queries` as a **list**, so it returned:
  `Input should be a valid dictionary`

Your working payload is the correct shape.

---

## About “latest data replacement” (UN + OFAC) in your current setup

With this manifest:

```yaml
catalogs:
  - url: https://data.opensanctions.org/datasets/latest/index.json
    resource_name: entities.ftm.json
    scopes:
      - us_ofac_sdn
      - un_sc_sanctions
```

and:

* `YENTE_AUTO_REINDEX=true`

You have implemented:

* **automatic periodic update checks** (Yente cron)
* **reindexing when a newer dataset version appears in `latest/index.json`**

What is still missing for “production-grade update safety”:

* explicit operational controls:

  * a scheduled call to `/updatez` (optional) to force refresh
  * monitoring and alerting if indexing fails
  * disk-space monitoring (Elasticsearch can go read-only on low disk, which you already hit once)

---

## Minimum “handoff package” to backend team (what you give them)

1. A deployed URL of wrapper:

* `http://sanctions-wrapper.internal:8080`

2. API contract:

* Endpoint: `POST /v1/sanctions/screen/person`
* Inputs: `full_name`, optional `country`, `dob`, `passport_number`, `national_id`
* Output: `decision`, `top_score`, `matches`, `reasons`, `request_id`

3. Integration rules on their side:

* `block` → deny withdrawal + log compliance case
* `review` → hold withdrawal + queue for human review
* `clear` → proceed

4. Operational note:

* Yente must stay internal; backend talks only to wrapper.

---

## Next improvements after MVP (still compatible with what you built)

* Add allowlist/whitelist and internal exceptions (VIPs, previously cleared identities) keyed by immutable identifiers.
* Add stronger rules:

  * block on exact passport/national-id match regardless of name score
  * raise decision to review when country mismatch exists but score high
  * separate thresholds for OFAC vs UN if desired
* Add audit DB:

  * store request, response, decision, operator actions, timestamps
* Add caching:

  * cache negative results for short windows to reduce load during high withdrawal bursts
* Add auth:

  * internal API key or mTLS between backend and wrapper

This is the shortest path from your current “Yente works locally” state to a deployable sanctions module the backend team can call.

