import os

# === General Config ===
INPUT_FOLDER = "tests/cloudwatch"
RESULTS_FOLDER = "results"
MAX_LOG_LINES = None  # Compliance mode (limit log lines)
LARGE_LOG_WARNING_THRESHOLD = 100000

# === Statistical Detection Config ===
TOP_PERCENT = 0.05  # Top anomalies to classify
ANOMALY_THRESHOLD = 0  # Threshold to trigger LLM
USE_DRAIN3_LIGHT = False

# === Repetitive Template Detection ===
ENABLE_SPAM_DETECTION = True
SPAM_TEMPLATE_THRESHOLD = 0.75

# === Rolling Window Detection ===
ENABLE_ROLLING_WINDOW = True
ROLLING_WINDOW_SIZE = 1000
ROLLING_WINDOW_THRESHOLD = 0.75

# === LOF Detection ===
ENABLE_LOF = True
LOF_N_NEIGHBORS = 5
LOF_CONTAMINATION = 0.05  # Ratio of anomalies

# === Rule & Security Pattern ===
ADDITIONAL_SECURITY_PATTERNS = []
ADDITIONAL_RULE_BASED_PATTERNS = []

# === Dependent Anomaly Filter ===
ENABLE_DEPENDENT_ANOMALY_FILTER = True

# === LLM Config ===
ENABLE_LLM = True
LLM_ENDPOINT = "http://localhost:11434/api/generate"
LLM_MODEL = "mistral:instruct"
CONCURRENCY = 5  # Reduced concurrency to avoid overwhelming Ollama
MAX_LOG_LENGTH = 512
MAX_REASON_LENGTH = None
TOP_N_LLM = 10
TIMEOUT = 30  # Increased timeout for LLM requests
LLM_PROVIDER = "ollama"

# === Compliance Mode ===
COMPLIANCE_MODE = False
SUMMARY_ONLY = False
VERBOSE = False

# === Non Anomalies folder ===
NON_ANOMALIES_FOLDER = "non_anomalies"

# === Drain3 Paths ===
DRAIN3_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "drain3", "drain3.ini")
DRAIN3_STATE_PATH = os.path.join(os.path.dirname(__file__), "drain3", "drain3_state.json")
DRAIN3_LOG_DIR = os.path.join(os.path.dirname(__file__), "drain3", "drain3_logs")

# === YAML Config Loader ===
YAML_CONFIG = {}

# === Ensure result folder ===
os.makedirs(RESULTS_FOLDER, exist_ok=True)
