
# 🚀 LogAnomaly

**LogAnomaly** is a fast, scalable, semantic & rule-based **Log Anomaly Detection CLI** designed for modern cloud-native log pipelines.  
It detects anomalies using a combination of **statistical scoring, pattern-based rules, security leak detection, volume anomaly detection, and optional LLM-based classification**.

---

## ✨ Features

✅ Statistical & Rule-based anomaly detection  
✅ Optional LLM-based semantic classification (Mistral, TinyLlama, Phi-2, etc.)  
✅ Sensitive information leak detection  
✅ Volume-based anomaly & log flood detection  
✅ Configurable rule patterns via YAML  
✅ Auto context gathering & log cleaning  
✅ Compliance-friendly log sampling  
✅ Interactive Streamlit dashboard  
✅ JSON Summary output for audit pipelines  
✅ Plug & Play CLI usage

---

## 📥 Installation

Clone and install:

```bash
git clone https://github.com/yourorg/loganomaly.git
cd loganomaly
pip install -e .
```

---

## ⚙️ Configuration

You can configure LogAnomaly using a **YAML config file**:

```yaml
anomaly_threshold: 0.1
top_percent: 5
top_n_llm: 10
enable_llm: true
enable_spam_detection: true
spam_template_threshold: 0.8
max_log_lines: null
large_log_warning_threshold: 1000
enable_dependent_anomaly_filter: true

llm_provider: mistral
llm_config:
  endpoint: http://localhost:11434/api/generate
  model: mistral:instruct
  timeout: 10

rule_based_patterns:
  - name: "Custom Timeout"
    pattern: "execution timeout"
    reason: "Execution timed out."

security_patterns:
  - name: "Slack Token"
    pattern: "xox[baprs]-([0-9a-zA-Z]{10,48})"
```

---

## 🚀 Usage

### Detect Anomalies

```bash
loganomaly --input testdata/logs --output results --config loganomly.yaml
```

### Show Results in Dashboard

```bash
loganomaly --input testdata/logs --output results --config loganomly.yaml --show-results
```

### Disable LLM classification

```bash
loganomaly --input testdata/logs --disable-llm
```

### Compliance mode (limit max logs)

```bash
loganomaly --input testdata/logs --compliance-mode --max-logs 5000
```

---

## 📊 Output Structure

- `results/*.json` → Detected anomalies in JSON
- `results/*_summary.json` → Anomaly summary report  
- `results/*_anomalies.json` → Full anomaly details

Sample Anomaly:

```json
{
  "timestamp": "2025-03-30T05:22:12Z",
  "classification": "Operational Error",
  "reason": "Database operation failed.",
  "tag": ["Database Error"],
  "log": "ERROR: Database connection error in service payment"
}
```

Sample Summary:

```json
{
  "filename": "payment-logs.json",
  "original_log_count": 10000,
  "processed_log_count": 10000,
  "anomalies_detected": 27,
  "volume_stats": [],
  "rule_based_anomalies": 19,
  "llm_classification_done": true
}
```

---

## 🧩 Streamlit Dashboard

To visualize the results:

```bash
streamlit run loganomaly/dashboard.py
```

---

## 🔥 Competitor Analysis

| Tool                        | Statistical Detection | Rule-based Detection | LLM Integration | Dashboard | Secret Scanning | Configurable Rules |
|-----------------------------|----------------------:|--------------------:|---------------:|---------:|---------------:|------------------:|
| **LogAnomaly**              | ✅                    | ✅                  | ✅             | ✅       | ✅             | ✅               |
| Google Cloud Logs Explorer | ❌                    | ❌                  | ❌             | ✅       | ❌             | ❌               |
| New Relic Logs              | ❌                    | ❌                  | ❌             | ✅       | ❌             | ❌               |
| AWS GuardDuty               | ✅                    | ✅                  | ❌             | ❌       | ✅             | ❌               |
| LogAnomaly                  | **✅**                | **✅**              | **✅**         | **✅**   | **✅**         | **✅**           |

---

## 🤝 Contribution Guide

We welcome contributions!

### Setup

```bash
git clone https://github.com/yourorg/loganomaly.git
cd loganomaly
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Run Tests

```bash
pytest tests/
```

### Pre-commit Hooks

```bash
pre-commit install
pre-commit run --all-files
```

### PR Guidelines

- Write clear commit messages.
- Add unit tests and functional tests.
- Follow PEP8 style.
- Update `README.md` if needed.

---

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

---

## 🙌 Acknowledgements

Inspired by:
- Drain3 Log Template Miner
- detect-secrets
- Open Source LLMs (Mistral, TinyLlama, Phi-2)
