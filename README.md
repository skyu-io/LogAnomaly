# LogAnomaly: Advanced Log Analysis with AI

LogAnomaly is a powerful log analysis tool that uses multiple AI techniques to detect anomalies and classify log patterns. It combines traditional machine learning approaches with advanced LLM-based analysis for accurate and context-aware log processing.

## Features

### Core Detection Methods
- **Local Outlier Factor (LOF)**: Identifies anomalies by detecting logs that significantly deviate from their neighbors
- **Rolling Window Detection**: Detects log floods and repetitive patterns using smart chunking
- **Template Mining**: Extracts log patterns to identify common message structures
- **LLM Classification**: Advanced log analysis using Large Language Models with multi-step verification

### Smart Workflow Architecture
The system uses a flexible pipeline architecture that enables:

- **Modular Processing**: Each step is independent and can be modified or replaced
- **Quality Control**: Built-in evaluation and feedback loops
- **Automatic Retries**: Smart retry mechanism with exponential backoff and jitter
- **Extensible Design**: Easy to add new detection methods or processing steps
- **Robust Error Handling**: Comprehensive error handling with detailed context tracking

```python
# Example: Using the log analysis workflow
from loganomaly.workflow import LogAnalysisWorkflow

# Create a workflow with default steps
workflow = LogAnalysisWorkflow({})

Clone and install:

```bash
git clone https://github.com/skyu-io/LogAnomaly.git
cd loganomaly
pip install -e .
```

### Advanced LLM Processing
The LLM-based classification includes multiple enhancement layers:

1. **Pre-Processing (ThinkingStep)**
   - Log severity extraction (ERROR, WARN, INFO, DEBUG)
   - Component identification
   - Action classification
   - Error indicator detection

2. **Smart Prompting (PromptGenerationStep)**
   - Context-aware prompt generation
   - Structured information inclusion
   - Clear response format instructions

3. **Quality Control (ResponseEvaluationStep)**
   - Strict response format validation
   - Flexible parsing for various LLM responses
   - Detailed error reporting

4. **Resilient API Calls (LLMCallStep)**
   - Configurable retry mechanism
   - Error categorization and handling
   - Timeout management

### Comprehensive Analytics
The system provides detailed analytics for log data:

1. **Template Diversity Metrics**
   - Unique template count
   - Template entropy (measure of log diversity)
   - Top template ratio (dominance of most common pattern)

2. **Time-Based Analysis**
   - Log rate calculations (per second, minute, hour)
   - Peak log rate detection
   - Error rate over time
   - Time span analysis

3. **Component Analysis**
   - Automatic component extraction
   - Component distribution metrics
   - Top components identification

4. **Security Analysis**
   - Sensitive information detection
   - Security leak reporting
   - Pattern-based security scanning

### Interactive Dashboard
The built-in dashboard provides:

- **Visual Analytics**: Interactive charts and graphs for all metrics
- **Anomaly Browser**: Searchable and filterable anomaly display
- **Template Analysis**: Visual representation of log patterns
- **Component Distribution**: Pie charts of component frequency
- **Severity Distribution**: Visualization of log levels

## Getting Started

### Quick Start

1. **Install LogAnomaly**

```bash
pip install loganomaly
```

2. **Create a basic configuration file**

```bash
# Create config.yaml
cat > config.yaml << EOL
detectors:
  lof:
    enabled: true
    neighbors: 20
    contamination: 0.1
  
  rolling_window:
    enabled: true
    window_size: 1000
    repetition_threshold: 0.75

llm:
  provider: "ollama"
  model: "mistral:instruct"
  endpoint: "http://localhost:11434/api/generate"
  timeout: 30
  max_retries: 3
EOL
```

3. **Install and run Ollama with Mistral:instruct**

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh

# Pull the Mistral:instruct model
ollama pull mistral:instruct

# Start Ollama server (if not already running)
ollama serve
```

4. **Run LogAnomaly on your log files**

```bash
# Analyze logs in a directory
loganomaly --input /path/to/logs --output results --config config.yaml

# Show the dashboard with results
loganomaly --input /path/to/logs --output results --config config.yaml --show-results
```

### Example: Analyzing a Sample Log File

Here's a complete example of analyzing a sample log file:

```bash
# Create a sample log file
cat > sample.log << EOL
2025-04-01T12:00:01 INFO [UserService] User login successful: user123
2025-04-01T12:00:05 INFO [UserService] User profile updated: user123
2025-04-01T12:00:10 ERROR [DatabaseService] Connection failed: timeout after 30s
2025-04-01T12:00:15 WARN [SecurityService] Multiple failed login attempts: user456
2025-04-01T12:00:20 INFO [UserService] User logout: user123
2025-04-01T12:00:25 ERROR [DatabaseService] Connection failed: timeout after 30s
2025-04-01T12:00:30 ERROR [DatabaseService] Connection failed: timeout after 30s
2025-04-01T12:00:35 ERROR [DatabaseService] Connection failed: timeout after 30s
2025-04-01T12:00:40 WARN [SecurityService] Suspicious activity detected: user789
2025-04-01T12:00:45 INFO [SystemService] System health check: OK
EOL

# Create a minimal configuration
cat > minimal_config.yaml << EOL
llm:
  provider: "ollama"
  model: "mistral:instruct"
  endpoint: "http://localhost:11434/api/generate"
EOL

# Run analysis and show dashboard
loganomaly --input sample.log --output results --config minimal_config.yaml --show-results
```

### Using Ollama with Different Models

LogAnomaly works with any Ollama model. Here's how to use different models:

#### Mistral:instruct (Recommended)

```yaml
# config.yaml
llm:
  provider: "ollama"
  model: "mistral:instruct"
  endpoint: "http://localhost:11434/api/generate"
```

```bash
# Pull the model
ollama pull mistral:instruct

# Run LogAnomaly
loganomaly --input logs/ --output results --config config.yaml
```

#### Llama3

```yaml
# config.yaml
llm:
  provider: "ollama"
  model: "llama3"
  endpoint: "http://localhost:11434/api/generate"
```

```bash
# Pull the model
ollama pull llama3

# Run LogAnomaly
loganomaly --input logs/ --output results --config config.yaml
```

#### Custom Prompt Template

You can customize the prompt template for better results with specific models:

```yaml
# config.yaml
workflow:
  steps:
    prompt:
      template: "custom"
      custom_template: |
        <s>[INST] You are a log analysis expert. Analyze this log:
        
        {log}
        
        Is this log normal or anomalous? If anomalous, explain why.
        
        Answer in this format:
        CLASSIFICATION: [normal/anomaly]
        REASON: [your explanation]
        TAGS: [comma-separated tags] [/INST]
        </s>
```

### Troubleshooting

#### Ollama Connection Issues

If you encounter connection issues with Ollama:

1. Ensure Ollama is running: `ollama serve`
2. Check if the endpoint is correct in your config: `http://localhost:11434/api/generate`
3. Verify the model is pulled: `ollama list`

#### Memory Issues

If you encounter memory issues with large log files:

```bash
git clone https://github.com/skyu-io/LogAnomaly.git
cd loganomaly
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Installation

```bash
pip install loganomaly
```

## Configuration

### Basic Configuration
```yaml
# config.yaml
detectors:
  lof:
    enabled: true
    neighbors: 20
    contamination: 0.1
  
  rolling_window:
    enabled: true
    window_size: 1000
    repetition_threshold: 0.75

llm:
  provider: "ollama"  # or "openai", "anthropic", etc.
  model: "llama3"
  endpoint: "http://localhost:11434/api/generate"
  timeout: 30
  max_retries: 3
```

### Advanced Workflow Configuration
```yaml
workflow:
  retry:
    max_attempts: 3
    initial_delay: 1.0
    max_delay: 10.0
    backoff_factor: 2.0
    jitter: 0.1
  
  steps:
    thinking:
      enabled: true
    
    prompt:
      template: "enhanced"
    
    llm_call:
      provider: "ollama"
      model: "llama3"
```

## Usage Examples

### Basic Usage
```python
from loganomaly import LogAnalyzer

analyzer = LogAnalyzer()
results = await analyzer.analyze_logs(logs_df)
```

### Command Line Interface
```bash
# Analyze logs in a directory
loganomaly --input /path/to/logs --output /path/to/results --config config.yaml

# Analyze a specific log file
loganomaly --input /path/to/logfile.log --output /path/to/results

# Analyze and show dashboard
loganomaly --input /path/to/logs --output /path/to/results --show-results
```

### Batch Processing
```python
async with LogAnalyzer() as analyzer:
    results = await analyzer.analyze_batch(
        logs_df,
        batch_size=100,
        max_concurrent=5
    )
```

## Advanced Features

### 1. Local Outlier Factor (LOF)
The LOF detector identifies anomalies by comparing each log's density to its neighbors:

```python
from loganomaly.detectors.lof_detector import detect_anomalies_lof

anomalies = detect_anomalies_lof(logs_df, contamination=0.05)
```

### 2. Rolling Window Detection
Smart log flood detection with pattern analysis:

```python
from loganomaly.detectors.rolling_window_detector import rolling_window_chunking

chunked_logs = rolling_window_chunking(
    logs_df,
    window_size=1000,
    repetition_threshold=0.75
)
```

### 3. Template Mining
Extract log templates to identify patterns:

```python
from loganomaly.pattern_miner import mine_templates

logs_with_templates = mine_templates(logs_df)
```

### 4. LLM Classification Pipeline
Advanced log classification with multi-step verification:

```python
from loganomaly.workflow import LogAnalysisWorkflow

# Create a workflow with default steps
workflow = LogAnalysisWorkflow({})

# Process a log entry
result = await workflow.execute("ERROR: Failed to connect to database: Connection refused")
```

## Extending the System

### Creating Custom Steps
```python
from loganomaly.workflow import WorkflowStep

class MyDetectorStep(WorkflowStep):
    def __init__(self):
        super().__init__("my_detector")
        
    async def execute(self, context):
        # 1. Get data from context
        log = context.get_result("log")
        
        # 2. Process the data
        result = my_detection_logic(log)
        
        # 3. Add results to context
        context.add_result("my_detection", result)
        
        return True  # Continue pipeline
```

### Custom Evaluation Logic
```python
class CustomEvaluationStep(ResponseEvaluationStep):
    def __init__(self):
        super().__init__("custom_evaluation")
    
    async def execute(self, context):
        # Custom evaluation logic
        response = context.get_result("llm_response")
        
        # Your custom validation logic
        if my_validation_logic(response):
            context.add_result("classification", "custom_class")
            return True
            
        return False
```

## Output Format

### Summary JSON
The tool generates a comprehensive summary JSON with the following sections:

```json
{
  "filename": "example.log",
  "original_log_count": 1000,
  "processed_log_count": 1000,
  "anomalies_detected": 15,
  "volume_stats": [...],
  "template_diversity": {
    "unique_templates": 45,
    "template_entropy": 3.2,
    "top_template_ratio": 0.12
  },
  "time_metrics": {
    "logs_per_second": 1.2,
    "peak_rate_per_minute": 120,
    "time_span_seconds": 3600,
    "error_rate": 0.05
  },
  "component_metrics": {
    "unique_components": 12,
    "top_components": [...]
  },
  "log_severity_summary": {...},
  "tag_summary": {...}
}
```

### Anomalies JSON
Detailed information about detected anomalies:

```json
[
  {
    "log": "ERROR: Database connection failed",
    "timestamp": "2025-04-01T12:34:56",
    "classification": "anomaly",
    "reason": "Connection failure indicates system issue",
    "tags": ["error", "database", "connectivity"]
  }
]
```

## Recent Updates

### Version 0.1.2 (April 2025)
- **Enhanced Analytics**: Added template diversity, time-based, and component metrics
- **Interactive Dashboard**: Added visualizations with Plotly integration
- **Multiple Detectors**: Support for combining different detection methods
- **Improved Error Handling**: Enhanced error handling in all workflow steps
- **Flexible Response Parsing**: Updated response evaluation to handle various LLM output formats
- **Retry Mechanism**: Implemented configurable retry logic with exponential backoff
- **Improved Prompt Engineering**: Enhanced prompts with clearer instructions and better structure
- **Workflow Resilience**: Workflow now stops on first failure to prevent cascading errors

## Architecture

The LogAnomaly system is built on a modular architecture with the following components:

1. **Core Workflow Engine**
   - `WorkflowContext`: Manages state and data passing between steps
   - `WorkflowStep`: Base class for all processing steps
   - `LogAnalysisWorkflow`: Orchestrates the execution of steps

2. **Processing Steps**
   - `ThinkingStep`: Extracts key information from logs
   - `PromptGenerationStep`: Creates structured prompts for LLMs
   - `LLMCallStep`: Handles API calls with retry logic
   - `ResponseEvaluationStep`: Validates and processes LLM responses

3. **Detection Modules**
   - `LOFDetector`: Local Outlier Factor detection
   - `RollingWindowDetector`: Pattern-based anomaly detection
   - `TemplateMiner`: Log template extraction

4. **LLM Integration**
   - `LLMProvider`: Abstract interface for different LLM providers
   - Provider implementations (Ollama, OpenAI, etc.)

5. **Utilities**
   - `RetryConfig`: Configuration for retry behavior
   - `RetryState`: Tracks state for retry operations

This architecture ensures flexibility, extensibility, and robustness in log analysis workflows.

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.


pip install -e .