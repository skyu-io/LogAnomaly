# log-anomaly-pipeline (Prefect 3.4.23)

A small, modular Prefect 3.x flow (validated on **v3.4.23**) that orchestrates a log‑anomaly workflow end‑to‑end:

---

## Contents

* [Overview](#overview)
* [Prerequisites](#prerequisites)
* [Installation](#installation)
* [Usage](#usage)

  * [Run locally](#run-locally)
* [Testing locally](#testing-locally)
* [Troubleshooting](#troubleshooting)
* [Future enhancements](#future-enhancements)

---

## Overview

This repo provides a single `worker.py` that defines a **Prefect 3.x** pipeline (validated on **v3.4.23**) named `log-anomaly-pipeline`. The pipeline coordinates a sequence of **tasks** and **subflows** to fetch inputs, run an anomaly detector, analyze results, optionally send email notifications, and upload a final report.

> ⚠️ The example functions are placeholders (`print(...)`). Replace them with your real implementations (e.g., call binaries, REST APIs, AWS SDK, etc.).

---

## Architecture

High‑level DAG (tasks vs. subflows):

```
log-anomaly-pipeline (flow)
│
├── install_packages [task]            (skipped when --skip-install)
├── prepare_prerequisite [task]
│   ├── execute_cloudwatchLog_injetion [flow]
│   └── download_config_yaml           [flow]
├── execute_logAnomaly [task]
└── report_postProcess [task]
    ├── analyze_report(dry_run)        [flow]
    │   └── send_notification_emails   [flow] (skipped when dry_run=True)
    └── upload_report                  [flow]
```

**Design choices**

* Uses `@flow` and `@task` decorators from Prefect 3.x
* `get_run_logger()` used for structured logs
* `dry_run` gate controls notification sending
* `skip_install` gate controls environment provisioning step

---

## Prerequisites

* Python 3.9+ (3.10/3.11 recommended)
* **Prefect 3.4.23** (other 3.x versions may work, but this README targets 3.4.23)
* (Optional) Access to AWS CloudWatch, config service ("SkyU"), SMTP or email provider, file-service endpoint

---

## Installation

Create and activate a virtual environment, then install a pinned Prefect version to match your runtime:

```bash
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install --upgrade pip
pip install "prefect==3.4.23"
```

If you publish a Docker image or run in CI, also pin `prefect==3.4.23` there for reproducibility.

---

---

## Usage

### Run locally

```bash
python worker.py
```

### Parameters

* `run_id` *(str)*: defaults to `YYYYMMDD-HHMMSS` UTC timestamp.
* `skip_install` *(bool)*: skip `install_packages()` when `True`.
* `dry_run` *(bool)*: when `True`, `analyze_report()` will **not** call `send_notification_emails()`.

### Examples

```bash
# Normal run
python worker.py

# Skip installing packages (e.g., image already has deps)
python -c "from worker import pipeline; pipeline(skip_install=True)"

# Dry-run to suppress emails
python -c "from worker import pipeline; pipeline(dry_run=True)"
```

> You can also import `pipeline` in notebooks or other Python modules and call it with parameters.

---

## Flow & Task reference

### `@task install_packages()`

Installs runtime dependencies. Recommended:

* Make this a no‑op in Docker/CI and set `skip_install=True`.

### `@flow execute_cloudwatchLog_injetion()`

Download required CloudWatch log streams. Consider parameters for account/region/time window, and add retries.

### `@flow download_config_yaml()`

Retrieve YAML configuration from "SkyU". Validate schema and log the selected config version/commit.

### `@task prepare_prerequisite()`

Composes the two subflows, execute_cloudwatchLog_injetion and download_config_yaml and ensures they complete before anomaly detection.

### `@task execute_logAnomaly()`

Run the anomaly binary or Python library. Emit structured artifacts (JSON, CSV) for analysis.

### `@flow analyze_report(dry_run: bool)`

Reads detector output, evaluates rules/thresholds, and conditionally dispatches notifications. Uses `get_run_logger()` to record the dry‑run skip.

### `@flow send_notification_emails()`

Send emails with summaries/links. Externalize recipients in config and add rate‑limits.

### `@flow upload_report()`

Uploads final reports/artifacts to a file service (or S3/GCS). Return a URI for downstream use.

---

## Observability

* Uses `get_run_logger()` for structured messages.
* To view runtime details, launch the Prefect UI appropriate for 3.x and/or enable log streaming in your execution environment.
* Add `task_run_name`/`flow_run_name` templates if you want human‑readable run names including `run_id`.

---

<!-- ## Packaging & Deployment

* **Pin Prefect**: ensure runners, CI, and Docker images use `prefect==3.4.23`.
* **Containers (optional)**: bake system deps (curl, AWS CLI, mail client) and your anomaly binary into the image; then set `skip_install=True`.
* **Secrets/Blocks**: if you adopt Prefect Blocks (e.g., for credentials), reference them inside your tasks/subflows. This sample keeps things literal for clarity.
* **Deployments**: Prefect 3.x CLI verbs differ from 2.x. Follow the Prefect 3.4.23 docs for current `deploy`/work‑pool patterns. Keep environment parity with this README’s version pin. -->

---

## Local UI server (self‑hosted) — start, connect, verify

> These steps run the **Prefect Server UI locally** and connect your SDK to it so runs appear in the dashboard.

1. **Start the server** in a new terminal:

   ```bash
   prefect server start
   ```

   The UI will be at **[http://127.0.0.1:4200](http://127.0.0.1:4200)** (stop with `CTRL+C`).

2. **Point your SDK at the local API** (one‑time per profile):

   ```bash
   prefect config set PREFECT_API_URL="http://127.0.0.1:4200/api"
   ```

   Optional: verify with

   ```bash
   prefect config view | grep PREFECT_API_URL
   ```

3. **Run the flow** (in your project terminal):

   ```bash
   python worker.py
   ```

4. **Check the UI**:

   * Open [http://127.0.0.1:4200](http://127.0.0.1:4200)
   * Go to **Flow runs** and confirm you see your `log-anomaly-pipeline` run.



---

## Troubleshooting

* **Email sent during tests** → set `dry_run=True` (default off) and guard the email subflow.
* **Long setup time** → use `skip_install=True` with a prebuilt image containing dependencies.

---

## Future enhancements

* Add retries/backoff and timeouts to networked steps.
* Add validation for YAML schema and anomaly outputs.
