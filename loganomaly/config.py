import os

# === General Config ===
INPUT_FOLDER = "tests/cloudwatch"
RESULTS_FOLDER = "results"
MAX_LOG_LINES = None  # Compliance mode (limit log lines)
LARGE_LOG_WARNING_THRESHOLD = 100000

# === Statistical Detection Config ===
TOP_PERCENT = 0.05  # Top anomalies to classify
ANOMALY_THRESHOLD = 0  # Threshold to trigger LLM
USE_DRAIN3_LIGHT = True  # Faster template mining (depth=3, threshold=0.5)
EMBEDDING_MODEL = "sentence-transformers/paraphrase-MiniLM-L6-v2"
EMBEDDING_BATCH_SIZE = 128  # Batch size for embedding model encode
EMBEDDING_BATCH_THRESHOLD = 1000  # Use batching only when above this many rows
USE_EMBEDDING_POOL = True  # Reuse multi-process pools for SentenceTransformer.encode
EMBEDDING_CPU_WORKERS = None  # None = auto (min(logical_cpus, 4))
EMBEDDING_POOL_DEVICES = ["cpu"]   # Override target devices, e.g., ["cpu"] * 4
USE_FAISS = False  # Note: faiss-cpu crashes on Apple Silicon with Python 3.13
FAISS_HNSW_M = 32  # HNSW parameter (CPU fallback)
FAISS_EF_SEARCH = 64  # HNSW search parameter (CPU fallback)

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
BEHAVIORAL_RULES = []

# === Behavioral Detection Config ===
ENABLE_BEHAVIORAL_DETECTION = False
BEHAVIORAL_RULES_FILE = None

# === Client-Specific Field Extraction Config ===
CLIENT_CONFIG_FILE = None

# === Dependent Anomaly Filter ===
ENABLE_DEPENDENT_ANOMALY_FILTER = True

# === LLM Config ===
ENABLE_LLM = True
LLM_ENDPOINT = "http://localhost:11434/api/generate"
LLM_MODEL = "mistral:instruct"
CONCURRENCY = 8  # Reduced concurrency to avoid overwhelming Ollama
MAX_LOG_LENGTH = 512
MAX_REASON_LENGTH = None
TOP_N_LLM = 10000
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
