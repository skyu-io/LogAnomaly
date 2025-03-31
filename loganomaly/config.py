import os

# === Config ===
INPUT_FOLDER = "tests/cloudwatch"
RESULTS_FOLDER = "results"
TOP_PERCENT = 0.05  # Top anomalies to classify
ENABLE_LLM = True
LLM_ENDPOINT = "http://localhost:11434/api/generate"
LLM_MODEL = "mistral:instruct"
CONCURRENCY = 10
MAX_LOG_LENGTH = 512
MAX_REASON_LENGTH = None
ANOMALY_THRESHOLD = 0
CONTEXT_WINDOW_SECONDS = 30
TOP_N_LLM = 10
TIMEOUT = 10 # Timeout for LLM requests

os.makedirs(RESULTS_FOLDER, exist_ok=True)

# === Repetitive Template Detection ===
ENABLE_SPAM_DETECTION = True
SPAM_TEMPLATE_THRESHOLD = 0.75

# === Log Sampling (Compliance) ===
MAX_LOG_LINES = None

# === Drain3 Fast Mode ===
USE_DRAIN3_LIGHT = False
NON_ANOMALIES_FOLDER = "non_anomalies"
ENABLE_DEPENDENT_ANOMALY_FILTER = True
LARGE_LOG_WARNING_THRESHOLD = 100000

DRAIN3_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "drain3", "drain3.ini")
DRAIN3_STATE_PATH = os.path.join(os.path.dirname(__file__), "drain3", "drain3_state.json")
DRAIN3_LOG_DIR = os.path.join(os.path.dirname(__file__), "drain3", "drain3_logs")

# === LLM Provider ===
LLM_PROVIDER = "ollama"


ADDITIONAL_SECURITY_PATTERNS = []
ADDITIONAL_RULE_BASED_PATTERNS = []