# LogAnomaly: Advanced Log Analysis with AI

LogAnomaly is a powerful log analysis tool that uses multiple AI techniques to detect anomalies and classify log patterns. It combines traditional machine learning approaches with advanced LLM-based analysis for accurate and context-aware log processing.

## Features

### Core Detection Methods
- **Local Outlier Factor (LOF)**: Identifies anomalies by detecting logs that significantly deviate from their neighbors
- **Rolling Window Detection**: Detects log floods and repetitive patterns using smart chunking
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

# Process a log entry
result = await workflow.execute("ERROR: Failed to connect to database: Connection refused")
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
from loganomaly.detectors import LOFDetector

detector = LOFDetector(n_neighbors=20)
anomalies = detector.detect(logs_df)
```

### 2. Rolling Window Detection
Smart log flood detection with pattern analysis:

```python
from loganomaly.detectors import RollingWindowDetector

detector = RollingWindowDetector(
    window_size=1000,
    threshold=0.75
)
chunks = detector.chunk_logs(logs_df)
```

### 3. LLM Classification Pipeline
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

## Recent Updates

### Version 0.1.1 (April 2025)
- **Improved Error Handling**: Enhanced error handling in all workflow steps
- **Robust Context Management**: Better context passing between workflow steps
- **Flexible Response Parsing**: Updated response evaluation to handle various LLM output formats
- **Retry Mechanism**: Implemented configurable retry logic with exponential backoff
- **Improved Prompt Engineering**: Enhanced prompts with clearer instructions and better structure
- **Workflow Resilience**: Workflow now stops on first failure to prevent cascading errors

### Architecture

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

3. **LLM Integration**
   - `LLMProvider`: Abstract interface for different LLM providers
   - Provider implementations (Ollama, OpenAI, etc.)

4. **Utilities**
   - `RetryConfig`: Configuration for retry behavior
   - `RetryState`: Tracks state for retry operations

5. **Analysis Tools**
   - `LOFDetector`: Local Outlier Factor detection
   - `RollingWindowDetector`: Pattern-based anomaly detection

This architecture ensures flexibility, extensibility, and robustness in log analysis workflows.

## Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Setup
1. Clone the repository
2. Install dependencies: `pip install -e ".[dev]"`
3. Run tests: `pytest tests/`

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
