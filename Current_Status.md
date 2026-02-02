# Sanctions Screening Setup: What We Built and How It Works

## What we have done overall

You now have a working local sanctions screening service running on your machine using Docker:

* **Elasticsearch** = stores the searchable sanctions indexes.
* **Yente** = exposes an HTTP API that builds the indexes (from selected datasets) and answers match/search requests.
* Yente is configured to use **two datasets**:

  * `us_ofac_sdn` (OFAC SDN)
  * `un_sc_sanctions` (UN Security Council Sanctions)
* You verified the service is ready (`/readyz` returns OK) and you successfully got a match response from OFAC, and later you also confirmed UN matching works.

---
## Available API Endpoints

- **GET `/openapi.json`**  
  Returns the OpenAPI specification for the service.

- **GET `/readyz`**  
  Readiness probe (used for indexing / startup checks).

- **GET `/healthz`**  
  Health check endpoint for service monitoring.

- **POST `/match/{dataset}`**  
  Performs scored matching against the specified dataset.

- **POST `/search/{dataset}`**  
  Search interface for querying entities within a dataset.

- **POST `/reconcile/{dataset}`**  
  Reconciliation endpoint (e.g., OpenRefine-style entity resolution).

- **GET `/entities/{entity_id}`**  
  Fetch a specific entity by its unique identifier.


## Steps we completed (from beginning to first successful results)

### 1) Created the storage structure on Windows

You created persistent folders for:

* Logs and config (example: `C:\SANCTIONS-CHECK\...`)
* Data volumes for Elasticsearch and datasets (example: `D:\SANCTIONS-DATA\...`)

Goal: keep data outside containers so re-running containers doesn’t destroy indexes/logs.

---

### 2) Started Elasticsearch in Docker

* You ran Elasticsearch as a Docker container.
* You verified it is reachable using:

  * `http://127.0.0.1:9200/_cluster/health`

You saw `yellow` cluster health at times. For a single-node cluster this is normal when replica shards can’t be allocated (replicas need a second node).

---

### 3) Created a dedicated Docker network

* You created a custom Docker network (already existed later):

  * `sanctions-net`

Goal: allow containers to talk to each other by container name (DNS inside Docker network).

---

### 4) Connected Elasticsearch container to the network

* You connected the Elasticsearch container (name used in commands: `sanctions-es`) to `sanctions-net`.

Goal: Yente can reach Elasticsearch by the internal hostname `http://sanctions-es:9200`.

---

### 5) Pulled and ran Yente

* You pulled: `ghcr.io/opensanctions/yente:latest`
* You ran Yente on the same network, pointing it to Elasticsearch:

Key environment variables:

* `YENTE_INDEX_URL=http://sanctions-es:9200`
* `YENTE_MANIFEST=/data/manifest.yml`
* `YENTE_AUTO_REINDEX=true` (important for indexing)

Key port mapping correction you made:

* Yente listens inside container on **port 8000**
* You exposed it as:

  * `127.0.0.1:5000:8000`

This fixed the earlier “empty reply / wrong port” situation.

---

### 6) Fixed Elasticsearch “read-only” block when deleting old indices

At one point you tried deleting `yente-*` indices and got a `403` with a read-only block.
You fixed it by pushing settings in a way PowerShell didn’t break JSON (writing JSON to a file and using `--data-binary`), then deletion worked.

Outcome: You were able to reset indices cleanly when needed.

---

### 7) Fixed manifest issues and dataset URL selection

You tried local file paths inside manifest and hit validation errors (Yente expects `http/https` URLs for dataset sources).
You also hit `404` when guessing URLs like `/datasets/20260126/ofac/entities.ftm.json` (dataset name was wrong for that path).

Final working approach:

* Use the official OpenSanctions catalog index:

  * `https://data.opensanctions.org/datasets/latest/index.json`
* Select datasets by scope names:

  * `us_ofac_sdn`
  * `un_sc_sanctions`

Your working manifest became a “catalog manifest” (not direct dataset file paths).

---

### 8) Verified Yente is ready and indexed

You confirmed:

* `GET http://127.0.0.1:5000/openapi.json` works (API reachable)
* `GET http://127.0.0.1:5000/readyz` changed from:

  * `503 {"detail":"Index not ready."}`
    to:
  * `200 {"status":"ok"}`

That means:

* Yente finished downloading datasets
* Yente built Elasticsearch indices
* The index alias is live and Yente can answer matching queries

---

### 9) Tested the two dataset endpoints

You confirmed these endpoints exist:

* `/match/us_ofac_sdn`
* `/match/un_sc_sanctions`

You also discovered the correct request body format for `/match/{dataset}`:

* `queries` must be a **dictionary**, not a list.

Working test payload shape:

```json
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
```

---

## What is running right now (current system state)

* **Elasticsearch** running and reachable at:

  * `http://127.0.0.1:9200`
* **Yente** running and reachable at:

  * `http://127.0.0.1:5000`
* **Datasets indexed**:

  * OFAC SDN: `us_ofac_sdn`
  * UN SC Sanctions: `un_sc_sanctions`
* **Readiness**:

  * `GET /readyz` returns `{"status":"ok"}`

---

# How the request flow works (what happens internally)

## High-level logic

1. Your application sends a JSON request to Yente `/match/{dataset}`
2. Yente validates the payload and builds a “query entity” from your input (name, DOB, country, etc.)
3. Yente calls Elasticsearch to retrieve candidate entities from the indexed sanctions dataset
4. Yente scores candidates using matching logic (name similarity, aliases, DOB checks, etc.)
5. Yente returns structured results: candidate entity data + score + explanations + `match: true/false`

---

## Concrete example: `match/un_sc_sanctions`

### Request (example)

`POST http://127.0.0.1:5000/match/un_sc_sanctions`

```json
{
  "queries": {
    "q1": {
      "schema": "Person",
      "properties": {
        "name": ["JOHN DOE"],
        "country": ["us"]
      }
    }
  }
}
```

### What Yente does step-by-step

1. **API receives request**

   * Parses JSON
   * Confirms dataset = `un_sc_sanctions`
   * Confirms `queries` is a dictionary

2. **Candidate retrieval from Elasticsearch**

   * Yente sends search queries to Elasticsearch against the Yente entity index (the index Yente created during auto reindex).
   * Elasticsearch returns a set of candidate sanctions entities that roughly match the input (mostly name-based retrieval at this stage).

3. **Matching + scoring**

   * Yente compares your query entity vs each candidate.
   * It computes similarity scores (string similarity, phonetic similarity, alias overlap, etc.).
   * It applies penalties if fields conflict (country mismatch, DOB mismatch, etc.).
   * It produces:

     * overall `score`
     * `match: true/false`
     * per-feature explanations (why it scored that way)

4. **Response is returned**

   * If no good candidates are found, `results` is empty.
   * If candidates found, you get a list of matched entities with their properties and metadata.

---

## Why OFAC returned a match and UN sometimes returned none

This is normal behavior. Each dataset contains different people and different spellings/aliases.

* If the person is present in `us_ofac_sdn` but not in `un_sc_sanctions`, then:

  * OFAC endpoint returns results
  * UN endpoint returns `results: []`

When you later tested UN with a name that exists in UN data, you got UN results too.

So “empty results” is not an error. It’s a valid answer: “no match found in this dataset”.

---

# End-to-end pipeline diagram (single request)

```
[Your i-betting backend]
        |
        |  POST /match/{dataset}
        |  JSON: name, dob, country, etc.
        v
[Yente API (http://127.0.0.1:5000)]
        |
        |  1) Validate payload + pick dataset
        |  2) Build query entity
        |
        v
[Elasticsearch (http://sanctions-es:9200)]
        |
        |  3) Retrieve candidate entities from index
        v
[Yente matcher/scorer]
        |
        |  4) Score candidates (name/DOB/aliases/etc.)
        |  5) Decide match true/false + explanations
        v
[Yente API response]
        |
        v
[Your i-betting backend]
        |
        |  Store result + score + reason
        |  Decide: allow / hold / manual review
        v
[Dashboard / Withdraw workflow]
```

---

# What this setup enables in your project (practical usage)

* Your i-betting backend can call:

  * `POST /match/us_ofac_sdn`
  * `POST /match/un_sc_sanctions`
* Send user attributes (at minimum name; better: DOB/year, country, aliases)
* Receive:

  * `results[]` with entity info
  * `score`, `match`, and `explanations`
* Your backend then:

  * flags withdrawal / blocks / routes to manual review
  * logs the check for audit

Important operational note:

* You mapped Yente to `127.0.0.1:5000`, so it is reachable only from the same machine.
* To let another server/container call it, you must deploy it where the backend can reach it (same host/network) or expose it safely on an internal interface.


Below is a **delta patch** you can apply to **Document A**.
It contains **only information that is present in B but missing or under-specified in A**.
Nothing is rewritten; these are **additive sections** you can insert verbatim.

---

# Delta Patch — Additions to Upgrade Document A

## (ADD) Component Responsibilities (Clarification)

### Component roles (explicit)

* **Elasticsearch**

  * Stores an **indexed copy of sanctions entities**.
  * Optimized for **fast candidate retrieval** during matching/search.
* **Yente (OpenSanctions)**

  * Downloads/streams `entities.ftm.json` from the OpenSanctions catalog.
  * Indexes entities into Elasticsearch.
  * Executes match/search/reconcile logic.
  * Returns **scored candidate matches** with explanations.

---

## (ADD) Local Access Points Summary

### Local service endpoints

* **Elasticsearch**: `http://127.0.0.1:9200`
* **Yente API**: `http://127.0.0.1:5000`

  * Internally listens on port **8000** inside the container.

---

## (ADD) Container Connectivity Details

### Container-to-container communication

* Yente connects to Elasticsearch using Docker DNS:

  * `http://sanctions-es:9200`
* This requires both containers to be attached to the same Docker network (`sanctions-net`).
* Hostnames like `sanctions-es` are **not resolvable from the host**, only inside Docker.

---

## (ADD) Docker Network Creation (Command Reference)

### Network creation

```bash
docker network create sanctions-net
```

* Re-running this command may return “already exists”, which is expected and harmless.

---

## (ADD) Elasticsearch Single-Node Behavior

### Cluster health notes

* **Yellow cluster health** is normal for single-node Elasticsearch.
* Reason:

  * Replica shards (`rep=1`) cannot be allocated without a second node.
* This does **not** block Yente indexing or matching.

---

## (ADD) Yente Port Mapping Failure Mode (Root Cause)

### Port mapping clarification

* Yente listens on **port 8000 inside the container**.
* Incorrect mapping:

  * `5000:5000` → results in “Empty reply from server”.
* Correct mapping:

  * `127.0.0.1:5000:8000`

---

## (ADD) Manifest Validation Rules (Explicit)

### Manifest constraints

* Dataset sources **must be HTTP(S) URLs**.
* Local filesystem paths (e.g. `D:\...`) are invalid.
* Direct guessing of dataset URLs can result in `404`.
* Catalog-based manifests are the supported and stable approach.

---

## (ADD) Catalog-Based Manifest Resolution (Internal Mechanics)

### How Yente resolves datasets

1. Fetches the catalog index:

   * `index.json`
2. Filters datasets by `scopes`.
3. Resolves each dataset’s **current versioned URL**.
4. Streams `entities.ftm.json` for indexing.

---

## (ADD) Elasticsearch Index Aliasing

### Index lifecycle

* Yente creates a **new Elasticsearch index** during reindexing.
* An alias (e.g. `yente-entities`) is updated to point to the latest index.
* This allows safe reindexing without downtime.

---

## (ADD) Lifecycle Phases (Formal Separation)

### Indexing phase

* Triggered on startup or reindex.
* Reads `manifest.yml`.
* Fetches datasets and builds Elasticsearch indices.
* Completes when `/readyz` returns OK.

### Query phase

* Triggered by runtime API calls (`/match`, `/search`, `/reconcile`).
* Uses existing Elasticsearch indices.
* Does not modify index state.

---

## (ADD) Windows / PowerShell Execution Notes

### PowerShell-friendly practices

* Use UTF-8 encoded JSON files for request bodies.
* Use `--data-binary` with `curl.exe` to avoid encoding issues.
* Prefer file-based payloads over inline JSON in PowerShell.

---

## (ADD) OpenAPI Endpoint Source Attribution

### Endpoint discovery

* All available endpoints were identified by inspecting:

  * `GET /openapi.json`

---

## (ADD) Additional Visualizations

### Sequence diagram (runtime match)

* Client → Yente → Elasticsearch → Yente → Client
* Highlights candidate retrieval and scoring flow.

### Flowchart (indexing + querying)

* Separates **startup indexing** from **runtime matching** paths.

---

## (ADD) Responsibility Boundary (Product Integration)

### Responsibility split

* **Yente**

  * Matching, scoring, explanations.
* **Your backend**

  * Threshold decisions.
  * DOB/passport/country conflict handling.
  * Audit logging.
  * Final allow / hold / block decision.

---

