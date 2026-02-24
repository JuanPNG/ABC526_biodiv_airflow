# Biodiversity Ephemeral Composer Platform

This repository implements a **production-grade ephemeral Cloud Composer 3 platform**
used to orchestrate biodiversity Dataflow Flex Template pipelines.

The system provisions Composer on demand, executes a DAG, and destroys the
environment afterward. Infrastructure and orchestration are fully automated.

---

# 1. System Overview

This architecture separates:

- **Control Plane** → Infrastructure provisioning and lifecycle orchestration
- **Data Plane** → Composer, Airflow DAG, Dataflow pipelines, storage systems

The lifecycle is fully automated and reproducible.

## 1.1 High-Level Lifecycle

1. Bootstrap Terraform provisions long-lived IAM and foundational resources.
2. Ephemeral Terraform provisions Cloud Composer.
3. Cloud Build runs `terraform apply` and syncs DAGs deterministically.
4. Workflows:
   - Waits for Composer to become RUNNING
   - Mints OAuth2 token via IAM Credentials API
   - Triggers Airflow DAG
   - Polls DAG state
   - Executes destroy trigger (best-effort)
5. Terraform destroy removes the Composer environment.

---

# 2. Architecture

## 2.1 Control Plane vs Data Plane

```
                                ┌──────────────────────────┐
                                │        Cloud Workflows   │
                                │  (Lifecycle Orchestrator)│
                                └──────────────┬───────────┘
                                               │
                                               ▼
                                ┌──────────────────────────┐
                                │        Cloud Build       │
                                │  apply / destroy trigger │
                                └──────────────┬───────────┘
                                               │
                      ┌────────────────────────┴────────────────────────┐
                      │                                                 │
                      ▼                                                 ▼
        ┌──────────────────────────┐                    ┌──────────────────────────┐
        │   Terraform Bootstrap    │                    │  Terraform Ephemeral    │
        │  (long-lived resources)  │                    │  (Composer only)        │
        └──────────────┬───────────┘                    └──────────────┬───────────┘
                       │                                                │
                       ▼                                                ▼
              IAM / Service Accounts                            Cloud Composer 3
              Custom Roles                                       Environment
              API Enablement                                     (Ephemeral)
              GCS Backend State
                                                                  │
                                                                  ▼
                                                   ┌──────────────────────────┐
                                                   │        Airflow DAG       │
                                                   │ biodiv_pipelines_dag     │
                                                   └──────────────┬───────────┘
                                                                  │
                                                                  ▼
                                                   ┌──────────────────────────┐
                                                   │   Dataflow Flex Jobs     │
                                                   └──────────────┬───────────┘
                                                                  │
                                                                  ▼
                                                   GCS / BigQuery / Elastic
```

---

# 3. Terraform Architecture

Infrastructure is split into two independent stacks.

## 3.1 Bootstrap Stack (Long-Lived)

Location: `terraform/bootstrap`

Purpose:
- Enable required Google APIs
- Create service accounts
- Create custom IAM roles
- Configure least-privilege bindings
- Configure remote state bucket

This stack is applied once per project and rarely changed.

### Resources Created

- Composer runtime service account
- Dataflow worker service account
- Cloud Build lifecycle service account
- Workflows service account
- Custom role: `composerEphemeralLifecycle`
- IAM bindings for least privilege
- GCS bucket for Terraform remote state

### Why Separate Bootstrap?

- IAM should not be destroyed accidentally
- Prevent circular dependency during destroy
- Ensure lifecycle isolation
- Allow Composer to be ephemeral without touching foundational IAM

---

## 3.2 Ephemeral Stack (Composer Only)

Location: `terraform/ephemeral`

Purpose:
- Provision a Cloud Composer 3 environment only

This stack:
- Has its own state
- Contains no IAM creation
- Can be safely destroyed

This enforces clean separation of control plane layers.

---

## 3.3 Remote Terraform State

- Stored in GCS
- No local state allowed
- Enables reproducibility and CI/CD execution
- Required for Cloud Build execution

---

# 4. Cloud Build Automation

Cloud Build executes infrastructure changes and DAG synchronization.

Two independent triggers exist:

- Apply Trigger (provision Composer + sync DAGs)
- Destroy Trigger (destroy Composer only)

Both operate exclusively on the **ephemeral Terraform stack**.

Bootstrap stack is never managed by triggers.

---

## 4.1 Apply Trigger

Purpose:

- Provision Cloud Composer 3 environment
- Ensure DAG bucket is in deterministic state

Build configuration file:
```
cloudbuild.apply.yaml
```

Execution sequence:

1. terraform init (ephemeral stack)
2. terraform apply
3. Wait for Composer creation to complete
4. Synchronize DAGs to Composer bucket using:

   gsutil rsync -d

---

### 4.1.1 Why DAG Sync Happens After Apply

Composer environment creation produces:

- A GCS bucket for DAGs
- Internal environment metadata

DAG synchronization must occur after:

- Environment exists
- Bucket is available
- Service account permissions are active

Running sync before environment creation would fail.

---

### 4.1.2 Deterministic DAG Synchronization

The command:

```
gsutil rsync -d
```

Guarantees:

- New DAGs are uploaded
- Updated DAGs are replaced
- Deleted DAGs are removed from bucket

This prevents drift between repository and Composer environment.

Without `-d`, stale DAGs could remain active.

---

### 4.1.3 Trigger Configuration

Trigger type:
- Git push trigger

Branch filter:
- Production branch (e.g. main)

Service account:
- Cloud Build lifecycle service account (created in bootstrap)

Build config:
- cloudbuild.apply.yaml

Substitutions required:

- _PROJECT_ID
- _REGION
- _TF_STATE_BUCKET
- _COMPOSER_ENV_NAME

Optional:
- _BRANCH_NAME (if workflow-driven)
- _DAG_BUCKET_PREFIX (if configurable)

These substitutions must align with Terraform variables.

---

### 4.1.4 Terraform Backend Isolation

Ephemeral stack uses:

- Remote GCS backend
- Separate state file from bootstrap

State separation guarantees:

- Destroy does not affect bootstrap resources
- IAM definitions remain intact
- Lifecycle stack remains independent

---

### 4.1.5 Permissions Required by Apply Trigger SA

Cloud Build lifecycle SA must have:

Composer lifecycle permissions:
- composer.environments.create
- composer.environments.get
- composer.environments.delete
- composer.operations.get

Storage:
- objectAdmin on Terraform state bucket
- objectAdmin on Composer DAG bucket

IAM:
- iam.serviceAccountUser on Composer runtime SA

Logging:
- roles/logging.logWriter

No additional project-wide permissions are granted.

---

## 4.2 Destroy Trigger

Purpose:

- Destroy Composer environment only

Build configuration:
```
cloudbuild.destroy.yaml
```

Execution sequence:

1. terraform init (ephemeral stack)
2. terraform destroy

No DAG sync occurs during destroy.

---

### 4.2.1 Destroy Safety Model

Destroy trigger:

- Does NOT reference bootstrap stack
- Does NOT modify IAM
- Only removes Composer environment
- Can be re-run safely

If destroy fails:
- Environment remains
- Trigger can be manually re-run
- No IAM drift occurs

---

### 4.2.2 Why Bootstrap Is Excluded From Destroy

Bootstrap contains:

- Service accounts
- Custom roles
- IAM bindings
- Remote state bucket

Destroying bootstrap would:

- Break Cloud Build execution
- Break Workflows orchestration
- Remove required identities

Bootstrap is considered foundational infrastructure and is long-lived.

---

## 4.3 Idempotency Guarantees

Apply Trigger:
- Safe to re-run
- Terraform handles state reconciliation
- DAG sync guarantees deterministic outcome

Destroy Trigger:
- Safe to re-run
- Terraform destroy is idempotent

No manual intervention required in normal operation.

---

## 4.4 Failure Model

If terraform apply fails:
- Workflow aborts
- Composer not created
- Destroy not triggered

If DAG sync fails:
- Composer exists
- Workflow detects failure
- Destroy still executes (best-effort)

If terraform destroy fails:
- Environment may persist
- Manual destroy possible
- No IAM corruption occurs

---

## 4.5 CI/CD Security Properties

This Cloud Build model ensures:

- Infrastructure changes occur only via Terraform
- No manual Composer creation
- No manual DAG uploads
- No IAM changes outside code
- Full audit trail via Cloud Build logs
- Reproducible lifecycle execution

Cloud Build acts strictly as an execution engine.
It does not contain infrastructure logic outside Terraform definitions.# 5. Workflows Orchestration

Cloud Workflows acts as the lifecycle orchestrator.

It coordinates:

- Composer creation
- DAG execution
- Environment destruction
- Success/failure propagation

Workflows does NOT create infrastructure directly.
It delegates infrastructure changes to Cloud Build.

---

## 5.1 Execution Flow

High-level execution sequence:

1. Trigger Cloud Build Apply
2. Poll Cloud Build until SUCCESS
3. Poll Composer environment until RUNNING
4. Mint OAuth2 token via IAM Credentials API
5. Trigger Airflow DAG via REST API
6. Poll DAG run state
7. Trigger Cloud Build Destroy (best-effort)
8. Return terminal result

---

## 5.2 Step 1 — Trigger Apply

API Used:

- cloudbuild.projects.triggers.run
OR
- cloudbuild.projects.builds.create (depending on implementation)

Inputs required:

- project_id
- region
- apply_trigger_id
- branch_name
- substitutions

Workflows waits for build completion by polling:

- cloudbuild.projects.builds.get

Failure behavior:

- If build fails → workflow fails immediately
- Destroy step is NOT executed (Composer not created)

---

## 5.3 Step 2 — Poll Composer Environment

API Used:

- composer.projects.locations.environments.get

Condition:

```
state == RUNNING
```

Polling strategy:

- Fixed interval (e.g., 20–30 seconds)
- Timeout configurable (recommended: 30–45 minutes)
- Abort if state == ERROR

Rationale:

Composer creation is asynchronous and can take 15–25 minutes.

---

## 5.4 Step 3 — Mint OAuth2 Token

API Used:

- iamcredentials.projects.serviceAccounts.generateAccessToken

Purpose:

- Obtain short-lived token to call Airflow REST API

Token properties:

- Lifetime: short-lived (default 3600s)
- Scoped to Cloud Platform

No service account keys are used.

Workflows service account must have:

- iam.serviceAccounts.getAccessToken

Optional:

- iam.serviceAccounts.actAs (if impersonation enforced)

---

## 5.5 Step 4 — Trigger Airflow DAG

API Used:

- Airflow REST API (Composer 3)
  POST:
  ```
  https://<composer-webserver-url>/api/v1/dags/{dag_id}/dagRuns
  ```

Headers:

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

Payload:

```
{
  "conf": { ... optional dag_conf ... }
}
```

Response contains:

- dag_run_id

Failure behavior:

- Non-2xx response → workflow fails
- Destroy still executes (best-effort)

---

## 5.6 Step 5 — Poll DAG Run State

API Used:

- GET:
  ```
  /api/v1/dags/{dag_id}/dagRuns/{dag_run_id}
  ```

Terminal states:

SUCCESS  
FAILED  

Non-terminal states:

QUEUED  
RUNNING  

Polling strategy:

- Interval: 15–30 seconds
- Timeout: configurable (recommended based on expected job duration)

State handling:

- SUCCESS → proceed to destroy
- FAILED → proceed to destroy, then fail workflow
- Timeout → proceed to destroy, then fail workflow

---

## 5.7 Step 6 — Trigger Destroy (Best-Effort)

API Used:

- cloudbuild.projects.triggers.run
  (destroy trigger)

Destroy is executed regardless of DAG outcome.

Failure handling:

- Destroy failure does NOT override DAG result
- If destroy fails, workflow logs error
- Environment may remain and can be destroyed manually

This prevents infrastructure leakage from failed DAG runs.

---

## 5.8 Failure Propagation Model

| Stage | Failure Behavior |
|--------|------------------|
| Apply build fails | Workflow fails immediately |
| Composer enters ERROR | Workflow fails |
| DAG trigger fails | Destroy executed → workflow fails |
| DAG returns FAILED | Destroy executed → workflow fails |
| Destroy fails | Workflow reports destroy error but preserves DAG result |

---

## 5.9 Idempotency and Safety

Workflow execution is safe to re-run:

- Apply is idempotent
- Composer polling is read-only
- DAG execution is isolated per run
- Destroy is idempotent

Multiple executions do not corrupt infrastructure state.

---

## 5.10 Security Model

Workflows:

- Cannot create Composer directly
- Cannot modify IAM
- Cannot launch Dataflow directly
- Only orchestrates via APIs

Authentication model:

- Short-lived OAuth tokens only
- No stored credentials
- No service account keys
- No secrets in workflow definition

All access is auditable via:
- Cloud Audit Logs
- Cloud Build Logs
- Composer Logs

---

## 5.11 Operational Characteristics

This orchestration model ensures:

- Composer exists only during execution window
- No idle environment costs
- No persistent control plane drift
- Fully automated lifecycle
- Deterministic execution

Composer is treated as ephemeral compute infrastructure, not a permanent platform.# 5. Workflows Orchestration

Cloud Workflows acts as the lifecycle orchestrator.

It coordinates:

- Composer creation
- DAG execution
- Environment destruction
- Success/failure propagation

Workflows does NOT create infrastructure directly.
It delegates infrastructure changes to Cloud Build.

---

## 5.1 Execution Flow

High-level execution sequence:

1. Trigger Cloud Build Apply
2. Poll Cloud Build until SUCCESS
3. Poll Composer environment until RUNNING
4. Mint OAuth2 token via IAM Credentials API
5. Trigger Airflow DAG via REST API
6. Poll DAG run state
7. Trigger Cloud Build Destroy (best-effort)
8. Return terminal result

---

## 5.2 Step 1 — Trigger Apply

API Used:

- cloudbuild.projects.triggers.run
OR
- cloudbuild.projects.builds.create (depending on implementation)

Inputs required:

- project_id
- region
- apply_trigger_id
- branch_name
- substitutions

Workflows waits for build completion by polling:

- cloudbuild.projects.builds.get

Failure behavior:

- If build fails → workflow fails immediately
- Destroy step is NOT executed (Composer not created)

---

## 5.3 Step 2 — Poll Composer Environment

API Used:

- composer.projects.locations.environments.get

Condition:

```
state == RUNNING
```

Polling strategy:

- Fixed interval (e.g., 20–30 seconds)
- Timeout configurable (recommended: 30–45 minutes)
- Abort if state == ERROR

Rationale:

Composer creation is asynchronous and can take 15–25 minutes.

---

## 5.4 Step 3 — Mint OAuth2 Token

API Used:

- iamcredentials.projects.serviceAccounts.generateAccessToken

Purpose:

- Obtain short-lived token to call Airflow REST API

Token properties:

- Lifetime: short-lived (default 3600s)
- Scoped to Cloud Platform

No service account keys are used.

Workflows service account must have:

- iam.serviceAccounts.getAccessToken

Optional:

- iam.serviceAccounts.actAs (if impersonation enforced)

---

## 5.5 Step 4 — Trigger Airflow DAG

API Used:

- Airflow REST API (Composer 3)
  POST:
  ```
  https://<composer-webserver-url>/api/v1/dags/{dag_id}/dagRuns
  ```

Headers:

```
Authorization: Bearer <access_token>
Content-Type: application/json
```

Payload:

```
{
  "conf": { ... optional dag_conf ... }
}
```

Response contains:

- dag_run_id

Failure behavior:

- Non-2xx response → workflow fails
- Destroy still executes (best-effort)

---

## 5.6 Step 5 — Poll DAG Run State

API Used:

- GET:
  ```
  /api/v1/dags/{dag_id}/dagRuns/{dag_run_id}
  ```

Terminal states:

SUCCESS  
FAILED  

Non-terminal states:

QUEUED  
RUNNING  

Polling strategy:

- Interval: 15–30 seconds
- Timeout: configurable (recommended based on expected job duration)

State handling:

- SUCCESS → proceed to destroy
- FAILED → proceed to destroy, then fail workflow
- Timeout → proceed to destroy, then fail workflow

---

## 5.7 Step 6 — Trigger Destroy (Best-Effort)

API Used:

- cloudbuild.projects.triggers.run
  (destroy trigger)

Destroy is executed regardless of DAG outcome.

Failure handling:

- Destroy failure does NOT override DAG result
- If destroy fails, workflow logs error
- Environment may remain and can be destroyed manually

This prevents infrastructure leakage from failed DAG runs.

---

## 5.8 Failure Propagation Model

| Stage | Failure Behavior |
|--------|------------------|
| Apply build fails | Workflow fails immediately |
| Composer enters ERROR | Workflow fails |
| DAG trigger fails | Destroy executed → workflow fails |
| DAG returns FAILED | Destroy executed → workflow fails |
| Destroy fails | Workflow reports destroy error but preserves DAG result |

---

## 5.9 Idempotency and Safety

Workflow execution is safe to re-run:

- Apply is idempotent
- Composer polling is read-only
- DAG execution is isolated per run
- Destroy is idempotent

Multiple executions do not corrupt infrastructure state.

---

## 5.10 Security Model

Workflows:

- Cannot create Composer directly
- Cannot modify IAM
- Cannot launch Dataflow directly
- Only orchestrates via APIs

Authentication model:

- Short-lived OAuth tokens only
- No stored credentials
- No service account keys
- No secrets in workflow definition

All access is auditable via:
- Cloud Audit Logs
- Cloud Build Logs
- Composer Logs

---

## 5.11 Operational Characteristics

This orchestration model ensures:

- Composer exists only during execution window
- No idle environment costs
- No persistent control plane drift
- Fully automated lifecycle
- Deterministic execution

Composer is treated as ephemeral compute infrastructure, not a permanent platform.

# 5. Workflows Orchestration

Workflows coordinates the lifecycle.

Execution sequence:

1. Trigger Cloud Build apply
2. Poll Composer until RUNNING
3. Mint OAuth2 access token via:
   - IAM Credentials API
   - `generateAccessToken`
4. Trigger Airflow REST API
5. Poll DAG run state
6. Trigger destroy (best-effort)
7. Return success or failure based on DAG terminal state

No service account keys are used.

---

# 6. IAM Model (Strict Least Privilege)

This architecture enforces strict least-privilege IAM boundaries.

No component is granted `roles/editor`.
No service account keys are created.
All authentication uses short-lived OAuth2 tokens.

---

## 6.1 Service Accounts

The system uses four dedicated service accounts.

---

### 1. Composer Runtime Service Account

Purpose:
- Runs Airflow workers
- Launches Dataflow jobs
- Accesses GCS, BigQuery, Elasticsearch

Used by:
- Cloud Composer 3 environment

Typical roles:
- roles/composer.worker
- roles/storage.objectAdmin (restricted to required buckets)
- roles/dataflow.admin (or minimal custom role if hardened)
- roles/bigquery.dataEditor (scoped to dataset)
- roles/logging.logWriter

This account NEVER:
- Creates infrastructure
- Modifies IAM
- Triggers Cloud Build

---

### 2. Dataflow Worker Service Account

Purpose:
- Executes Dataflow Flex Template jobs

Used by:
- Dataflow workers

Typical roles:
- roles/dataflow.worker
- roles/storage.objectAdmin (restricted to pipeline buckets)
- roles/bigquery.dataEditor (scoped)
- roles/logging.logWriter

This account is specified explicitly in:
```
serviceAccountEmail
```
inside Flex template environment configuration.

It is never used by Composer control plane.

---

### 3. Cloud Build Lifecycle Service Account

Purpose:
- Executes Terraform apply/destroy
- Syncs DAGs

Used by:
- Cloud Build apply trigger
- Cloud Build destroy trigger

Permissions required:

Terraform (ephemeral stack):
- composer.environments.create
- composer.environments.delete
- composer.environments.get
- composer.environments.list
- composer.operations.get
- composer.operations.list

Additionally:
- roles/storage.objectAdmin (Terraform state bucket)
- roles/storage.objectAdmin (Composer DAG bucket)
- roles/logging.logWriter
- roles/iam.serviceAccountUser (on Composer runtime SA)

This account can:
- Create and delete Composer
- Act as Composer runtime SA (for environment creation)

This account cannot:
- Modify IAM roles
- Modify bootstrap resources
- Access unrelated project resources

---

### 4. Workflows Service Account

Purpose:
- Orchestrate lifecycle
- Trigger Cloud Build
- Poll Composer state
- Mint OAuth2 tokens
- Call Airflow REST API

Permissions required:

Cloud Build:
- cloudbuild.builds.create
- cloudbuild.builds.get

Composer:
- composer.environments.get
- composer.operations.get

IAM Credentials:
- iam.serviceAccounts.getAccessToken

Optional (depending on configuration):
- iam.serviceAccounts.actAs (if required for token minting pattern)

This account CANNOT:
- Create Composer directly
- Destroy Composer directly
- Modify IAM
- Launch Dataflow

It only orchestrates.

---

## 6.2 Custom Role: composerEphemeralLifecycle

Instead of granting roles/composer.admin,
a custom role is used.

Permissions:

- composer.environments.create
- composer.environments.delete
- composer.environments.get
- composer.environments.list
- composer.operations.get
- composer.operations.list

This reduces blast radius significantly.

---

## 6.3 Trust Relationships (ActAs Edges)

Explicit trust boundaries:

Cloud Build SA
    → iam.serviceAccounts.actAs
        → Composer Runtime SA

Workflows SA
    → iam.serviceAccounts.getAccessToken
        → Composer Runtime SA (for Airflow API token)

No other service account impersonation exists.

No cross-project impersonation is used.

---

## 6.4 Token Minting Model

Workflows does NOT use service account keys.

Instead:

1. Calls IAM Credentials API:
   generateAccessToken
2. Receives short-lived OAuth2 token
3. Calls Airflow REST API
4. Token expires automatically

This eliminates:
- Key leakage risk
- Long-lived credential risk
- Secret rotation overhead

---

## 6.5 Why No roles/editor?

`roles/editor` is avoided because:

- It includes IAM modification permissions
- It includes broad compute permissions
- It increases blast radius
- It violates least-privilege principle

All permissions are explicitly enumerated.

---

## 6.6 IAM Boundary Summary

Control Plane Permissions:
- Restricted to Composer lifecycle only
- No data plane write access except DAG bucket

Data Plane Permissions:
- Restricted to GCS / BigQuery required for pipelines
- No infrastructure modification permissions

Orchestration Layer:
- Can trigger builds
- Can poll status
- Cannot modify infrastructure directly

---

## 6.7 Security Properties Achieved

This model ensures:

- No long-lived credentials
- No over-privileged service accounts
- Clear separation of duties
- Minimal blast radius
- Deterministic and auditable access patterns
- Full Infrastructure as Code IAM management

All IAM bindings are declared in Terraform.
No manual IAM changes are permitted.

# 7. Reproducibility: Deploy From Scratch (Operator Guide)

This section describes how to reproduce the entire platform from an empty
Google Cloud project.

All steps assume:

- A clean GCP project
- Billing enabled
- `gcloud` authenticated
- Terraform installed locally

---

## 7.1 Required Operator IAM

The human operator applying the bootstrap stack must have:

- roles/owner  (simplest)
OR at minimum:
- roles/resourcemanager.projectIamAdmin
- roles/iam.serviceAccountAdmin
- roles/iam.roleAdmin
- roles/storage.admin
- roles/serviceusage.serviceUsageAdmin
- roles/cloudbuild.admin
- roles/workflows.admin
- roles/composer.admin

After bootstrap, day-to-day execution does NOT require these elevated roles.

---

## 7.2 Enable Required APIs

```
gcloud services enable \
  composer.googleapis.com \
  dataflow.googleapis.com \
  cloudbuild.googleapis.com \
  workflows.googleapis.com \
  iamcredentials.googleapis.com \
  artifactregistry.googleapis.com \
  compute.googleapis.com \
  storage.googleapis.com
```

Verify:

```
gcloud services list --enabled
```

---

## 7.3 Create Remote Terraform Backend Bucket

Terraform state must never be local.

Create a versioned GCS bucket:

```
gsutil mb -p <PROJECT_ID> -l <REGION> gs://<TF_STATE_BUCKET>
gsutil versioning set on gs://<TF_STATE_BUCKET>
```

This bucket is referenced by both:
- terraform/bootstrap
- terraform/ephemeral

---

## 7.4 Apply Bootstrap Stack (Long-Lived Infrastructure)

```
cd terraform/bootstrap
terraform init \
  -backend-config="bucket=<TF_STATE_BUCKET>"

terraform apply
```

Bootstrap creates:

- Service accounts
- Custom IAM role
- IAM bindings
- Remote state configuration
- Required API enablement (if defined in stack)

Verify service accounts exist:

```
gcloud iam service-accounts list
```

Bootstrap is applied once per project.

---

## 7.5 Configure Cloud Build Triggers

Two triggers are required.

### Apply Trigger

Purpose:
- Apply ephemeral Terraform stack
- Sync DAGs to Composer bucket

Configuration requirements:

- Trigger type: Git push
- Branch filter: production branch (e.g. main)
- Build config: cloudbuild.apply.yaml
- Service account: lifecycle Cloud Build SA created in bootstrap
- Substitutions:

Required substitutions must include:
- _TF_STATE_BUCKET
- _PROJECT_ID
- _REGION
- _COMPOSER_ENV_NAME

Ensure:
- Cloud Build SA has iam.serviceAccountUser on Composer runtime SA
- Cloud Build SA has permissions defined in bootstrap

---

### Destroy Trigger

Purpose:
- Run terraform destroy (ephemeral stack only)

Configuration:

- Build config: cloudbuild.destroy.yaml
- Same service account as apply trigger
- Same substitutions

Destroy trigger must NOT reference bootstrap state.

---

## 7.6 Deploy Workflows

Deploy orchestration workflow:

```
gcloud workflows deploy biodiv-ephemeral \
  --source=biodiv_ephemeral.yaml \
  --region=<REGION> \
  --service-account=<WORKFLOWS_SERVICE_ACCOUNT>
```

The Workflows service account must have:

- composer.environments.get
- cloudbuild.builds.create
- cloudbuild.builds.get
- iam.serviceAccounts.getAccessToken
- iam.serviceAccounts.actAs (if required)
- composer operations permissions (via custom role)

These permissions are provisioned in bootstrap.

---

## 7.7 Execute Full Lifecycle

Execute the workflow:

```
gcloud workflows execute biodiv-ephemeral \
  --region=<REGION> \
  --data='{
    "project_id": "<PROJECT_ID>",
    "region": "<REGION>",
    "composer_env_name": "<ENV_NAME>",
    "apply_trigger_id": "<APPLY_TRIGGER_ID>",
    "destroy_trigger_id": "<DESTROY_TRIGGER_ID>",
    "dag_id": "biodiv_pipelines_dag",
    "branch_name": "main"
  }'
```

Lifecycle outcome:

1. Composer created
2. DAG deployed
3. DAG executed
4. Environment destroyed
5. Workflow returns terminal state

---

## 7.8 Failure Semantics

If DAG fails:
- Workflow returns failure
- Destroy trigger still executes (best-effort)

If destroy fails:
- Composer may remain
- Destroy trigger can be re-run manually

---

## 7.9 Idempotency Guarantees

- Bootstrap stack: idempotent
- Ephemeral stack: idempotent
- Apply trigger: safe to re-run
- Destroy trigger: safe to re-run
- Workflows: safe to re-execute

No manual cleanup required under normal operation.

---

## 7.10 Operational Model

Recommended usage pattern:

- Do NOT keep Composer permanently running.
- Always use workflow orchestration.
- Treat Composer as compute infrastructure, not persistent control plane.
- Never modify IAM outside Terraform.

This ensures:
- Predictable cost
- Predictable security posture
- No drift

# 8. Data Plane: Composer, Airflow, and Dataflow

The data plane executes biodiversity processing pipelines using:

- Cloud Composer 3 (Airflow 2.10.x)
- Dataflow Flex Templates
- GCS for artifacts
- BigQuery for structured outputs
- Elasticsearch for source ingestion

Composer is ephemeral. Data processing is persistent.

---

## 8.1 Airflow DAG

DAG ID:
```
biodiv_pipelines_dag
```

Execution model:

- Manual trigger via Workflows
- schedule=None
- catchup=False
- One DAG run per lifecycle execution

Pipelines execute sequentially:

1. taxonomy
2. occurrences
3. cleaning_occs
4. spatial_annotation
5. range_estimation
6. data_provenance

Each stage:

- Launches Dataflow Flex Template
- Waits synchronously (`wait_until_finished=True`)
- Writes `_SUCCESS` marker to GCS

This enforces strict stage ordering and failure propagation.

---

## 8.2 Flex Template Execution Model

Each pipeline is packaged as:

- A Docker container
- Built and stored in Artifact Registry
- Referenced by a Flex Template JSON in GCS

Flex launch configuration specifies:

- containerSpecGcsPath
- jobName (run-scoped)
- parameters
- serviceAccountEmail
- stagingLocation
- tempLocation

Dataflow runner:

- Uses Runner v2
- Executes in regional endpoint
- Uses dedicated worker service account

No classic templates are used.
All pipelines are container-based Flex Templates.

---

## 8.3 Run Isolation Model

Each DAG run writes to an isolated GCS prefix:

```
gs://<bucket>/biodiv-pipelines-dev/runs/
  window_start=<ds>/
  run_ts=<ts_nodash>/
```

Properties:

- Immutable per-run outputs
- No overwrite of previous runs
- Natural partitioning
- Supports replay and auditing

Isolation guarantees:

- Parallel runs do not conflict
- Partial runs do not corrupt previous runs
- Outputs are traceable to specific execution timestamp

---

## 8.4 Artifact Layout

Example structure:

```
runs/
  window_start=2026-01-29/
    run_ts=20260129T000000/
      taxonomy/
        taxonomy_validated.jsonl
        _SUCCESS
      occurrences/
        raw/
          occ_*.jsonl
          _SUCCESS
      cleaned/
      spatial/
      range_estimates/
      data_provenance/
      _SUCCESS
```

Each stage writes:

- Data artifacts
- Completion marker

The top-level `_SUCCESS` indicates full pipeline completion.

---

## 8.5 _SUCCESS Marker Semantics

Markers are written using GCSHook.

Properties:

- Zero-byte file
- Idempotent (overwrite allowed)
- Indicates stage-level success

Marker guarantees:

- Written only after Dataflow job completes successfully
- Not written if job fails
- Enables external orchestration or downstream systems

Markers are not used for job control inside Airflow.
They are observability artifacts.

---

## 8.6 BigQuery Write Semantics

Dataflow jobs write to BigQuery using:

- Explicit dataset
- Explicit table
- Predefined schema (JSON schema files in GCS)

Expected write behavior:

- Append mode OR truncate mode depending on pipeline configuration
- No implicit dataset creation
- Table must exist or be defined by pipeline

BigQuery IAM is scoped:

- Dataset-level permissions only
- No project-wide BigQuery admin

---

## 8.7 Dataflow Worker Identity

Each Dataflow job runs under:

```
serviceAccountEmail = <dataflow_worker_sa>
```

This ensures:

- Separation between Composer runtime identity and worker identity
- Least privilege at execution layer
- No control-plane permissions on workers

Workers can:

- Read/write GCS pipeline buckets
- Write to specific BigQuery dataset
- Write logs

Workers cannot:

- Create infrastructure
- Modify IAM
- Launch other services

---

## 8.8 Failure Model (Data Plane)

If a Dataflow job fails:

- Airflow task fails
- Downstream tasks do not execute
- `_SUCCESS` marker is not written
- DAG state becomes FAILED
- Workflow triggers destroy

Partial artifacts may remain in GCS.
They are isolated per run and do not corrupt previous runs.

---

## 8.9 Idempotency and Replay

Because runs are isolated:

- A failed run can be re-executed safely
- Re-execution produces new run_ts
- Historical outputs remain untouched

Replay model:

- Same logical date (ds)
- New run_ts
- Clean artifact partition

No manual cleanup required.

---

## 8.10 Operational Guarantees

This data plane model provides:

- Strict execution ordering
- Explicit stage boundaries
- Deterministic artifact layout
- Isolated run partitions
- Secure execution identity separation
- No shared mutable state across runs

Composer is ephemeral.
Artifacts are durable.
Execution is auditable.

---

## 8.11 Observability

Observability layers:

- Airflow task logs
- Dataflow job logs
- Cloud Logging
- BigQuery job statistics
- GCS artifact inspection

All components emit logs to Cloud Logging.
No silent failures are expected.

---

## 8.12 Security Characteristics

- No service account keys
- No implicit dataset creation
- No implicit bucket creation
- Explicit identities for each execution layer
- No cross-project execution
- No shared credentials between control and data plane

This enforces strict separation between orchestration and execution layers.

# 9. Operational Guarantees

- Infrastructure is immutable
- Composer is ephemeral
- No IAM sprawl
- No service account keys
- Deterministic DAG deployment
- Clear separation of bootstrap vs ephemeral layers

---

# 10. Production Characteristics

This platform provides:

- Secure orchestration
- Least privilege IAM
- Automated lifecycle management
- Deterministic deployments
- Full Infrastructure as Code
- Zero manual steps after bootstrap

---

End of Document