# Ephemeral Cloud Composer (Composer 3) Lifecycle

## Overview

This project implements an **ephemeral Cloud Composer lifecycle** using Cloud Run and Cloud Scheduler.
It runs a DAG that orchestrates Apache Beam pipelines to ingest, transform, and enrich biodiveristy 
records associated to species with reference genomes and completed genome annotations.

Each execution:

* creates a Composer environment
* restores it from a snapshot
* runs the DAG
* deletes the environment

This approach minimizes cost while ensuring reproducibility through snapshots.

### Architecture

The lifecycle is orchestrated via Cloud Run services:

* **create-service** → creates the environment
* **load-service** → restores snapshot state
* **trigger-service** → triggers DAG execution
* **delete-service** → deletes the environment (called from DAG)

Cloud Scheduler coordinates execution timing.

### Lifecycle Flow

```text id="flow1"
Cloud Scheduler
    ↓
create-service (06:00)
    ↓
(wait ~35 min)
    ↓
load-service (06:35)
    ↓
(wait ~40 min)
    ↓
trigger-service (07:15)
    ↓
Airflow DAG runs
    ↓
delete-service (from DAG)
```

---

## Quick Start

Run the full lifecycle manually:

### Prerequisites

* gcloud authenticated
* Cloud Run services deployed:

  * `bp-composer-create`
  * `bp-composer-load`
  * `bp-composer-trigger`
  * `bp-composer-delete`
* Snapshot available
* Secret Manager configured

---

### 1. Set variables

```bash id="qs1"
PROJECT_ID="your-project"
REGION="your-region"
ENV_NAME="bp-composer-ephemeral"

CREATE_URL=$(gcloud run services describe bp-composer-create \
  --project "$PROJECT_ID" --region "$REGION" \
  --format='value(status.url)')

LOAD_URL=$(gcloud run services describe bp-composer-load \
  --project "$PROJECT_ID" --region "$REGION" \
  --format='value(status.url)')

TRIGGER_URL=$(gcloud run services describe bp-composer-trigger \
  --project "$PROJECT_ID" --region "$REGION" \
  --format='value(status.url)')

SNAPSHOT_PATH="gs://<bucket>/composer-snapshots/<snapshot-root>"
```

---

### 2. Create environment

```bash id="qs2"
curl -X POST "$CREATE_URL" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

Wait until:

```bash id="qs3"
gcloud composer environments describe "$ENV_NAME" \
  --location "$REGION" \
  --project "$PROJECT_ID" \
  --format="value(state)"
```

Expected:

```text id="qs4"
RUNNING
```

---

### 3. Load snapshot

```bash id="qs5"
curl -X POST "$LOAD_URL" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)" \
  -H "Content-Type: application/json" \
  -d "{\"snapshot_path\":\"$SNAPSHOT_PATH\"}"
```

Wait ~35 minutes.

---

### 4. Trigger DAG

```bash id="qs6"
curl -X POST "$TRIGGER_URL" \
  -H "Authorization: Bearer $(gcloud auth print-identity-token)"
```

---

### 5. Monitor execution

* Open Airflow UI
* Confirm DAG is running
* Observe Dataflow jobs

---

### 6. Verify deletion

Environment should transition to:

```text id="qs7"
DELETING
```

---

## In detail

### Environment Design

#### Snapshot-based Environment

The environment is restored from a **pre-built snapshot** containing:

* DAGs
* Variables
* Connections
* PyPI packages
* Airflow metadata DB

This ensures consistent execution across runs.

* **NOTE:** Snapshot path must be the root directory

---

### Secret Management

Composer is configured to use **Secret Manager as Airflow backend**.

#### Configuration

This should be run when configuring the bootstrap composer environment that will serve as
the base for the snapshot.

```bash id="sd1"
gcloud composer environments update "$ENV_NAME" \
  --location "$REGION" \
  --project "$PROJECT_ID" \
  --update-airflow-configs \
secrets.backend=airflow.providers.google.cloud.secrets.secret_manager.CloudSecretManagerBackend,\
secrets.backend_kwargs='{"project_id":"'"$PROJECT_ID"'","variables_prefix":"gbdp","connections_prefix":"airflow-connections","sep":"_"}'
```

#### Naming Convention

```text id="sd2"
gbdp_<variable_name>
```

Example:

```text id="sd3"
Variable.get("elasticsearch_password")
→ gbdp_elasticsearch_password
```

#### IAM

Composer service account must have:

```text id="sd4"
roles/secretmanager.secretAccessor
```

---

### Storage Strategy

A persistent bucket is used:

```text id="sd5"
gs://<bucket>-composer-ephemeral
```

Benefits:

* stable DAG location
* no bucket churn
* easier debugging

Constraint:

* only one active environment at a time

---

### Service Design

#### create-service

Creates environment with:

* Airflow image version
* workloads config
* service account
* custom bucket

#### load-service

* restores snapshot
* validates snapshot path
* asynchronous

#### trigger-service

* fetches Airflow URI dynamically
* triggers DAG via REST API

#### delete-service

* deletes environment
* idempotent
* called from DAG

---

### DAG Design

#### Execution Model

```python id="sd6"
schedule=None
catchup=False
```

* no automatic runs
* only externally triggered

---

#### Flow

```text id="sd7"
validate_config → gate → pipelines/skip → delete
```

---

#### Configuration

Loaded via:

```python id="sd8"
cfg = load_config()
```

Sources:

* Airflow Variables
* Secret Manager

Important:

* resolved at import time
* requires snapshot restore

---

#### Gate Logic

* determines if pipelines should run based on a minimum threshold of new species with complete annotations.
* prevents unnecessary Dataflow execution

---

#### Dataflow Apache Beam Pipelines

Pipelines are run using Dataflow flex-templates whose specifications can are defined
in `dataflow_specs.py`. You can find the code base and documentation of these pipelines
here [TODO_LINK](). 

These pipelines are triggered from the DAG using the operator:

```python id="sd9"
DataflowStartFlexTemplateOperator
```

---

#### Delete Step

```python id="sd10"
trigger_rule="all_done"
```

* always executes
* triggers environment deletion

---

### IAM and Security

#### Service Accounts

* Composer runtime (Using compute service account by default.)
* Scheduler invoker (Using a dedicated scheduler service account.)

#### Required Role

```text id="sd11"
roles/run.invoker
```

Scheduler uses OIDC authentication.

---

### Scheduler Configuration

The ephemeral composer environment will run the first day of every month with fixed-delay
orchestration for each service.

```text id="sd12"
create  → 0 6 1 * *
load    → 35 6 1 * *
trigger → 15 7 1 * *
```

---

### Operational Considerations

#### Timing

* no readiness checks
* relies on time buffers

#### Snapshot integrity

* ensure no temporary values
* snapshot is production-ready

#### Deletion

* asynchronous
* logs may disappear

#### Idempotency

* services tolerate retries
