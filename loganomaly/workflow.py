"""Workflow implementation for log analysis."""

import logging
import asyncio
from typing import Dict, Any, Optional, List
import aiohttp
import re
from .retry import RetryConfig, with_retry
from .llm_provider import get_llm_provider, LLMProviderError

logger = logging.getLogger(__name__)

class WorkflowContext:
    """Context for workflow execution."""
    
    def __init__(self):
        self.results = {}
        self.errors = {}
        
    def add_result(self, key: str, value: Any):
        """Add a result to the context."""
        self.results[key] = value
        
    def get_result(self, key: str, default: Any = None) -> Any:
        """Get a result from the context."""
        return self.results.get(key, default)
        
    def add_error(self, key: str, error: Exception):
        """Add an error to the context."""
        self.errors[key] = str(error)
        
    def get_error_summary(self) -> str:
        """Get a summary of all errors."""
        return "; ".join(f"{k}: {v}" for k, v in self.errors.items())

class WorkflowStep:
    """Base class for workflow steps."""
    
    def __init__(self, name: str):
        self.name = name
        
    async def execute(self, context: WorkflowContext) -> bool:
        raise NotImplementedError("Subclass must implement execute")

class ThinkingStep(WorkflowStep):
    """Think about the log entry and extract relevant information."""
    
    def __init__(self):
        super().__init__("thinking")
        
    async def execute(self, context: WorkflowContext) -> bool:
        try:
            log = context.get_result("log")
            context_logs = context.get_result("context_logs", [])
            
            if not log:
                raise ValueError("No log entry found in context")
                
            # Extract key information from log
            info = {
                'severity': self._extract_severity(log),
                'component': self._extract_component(log),
                'action': self._extract_action(log),
                'error_indicators': self._find_error_indicators(log),
                'context_logs': [l.get('log', '') for l in context_logs if 'log' in l],
                'patterns': self._find_patterns(log, context_logs)
            }
            
            # Add additional context analysis
            info['is_startup_related'] = self._is_startup_related(log)
            info['contains_sensitive_info'] = self._contains_sensitive_info(log)
            info['has_numeric_values'] = bool(re.search(r'\d+', log))
            
            context.add_result("log_info", info)
            return True
            
        except Exception as e:
            logger.error(f"Error in thinking step: {str(e)}")
            context.add_error(self.name, e)
            return False
            
    def _extract_severity(self, log: str) -> str:
        """Extract severity level from log."""
        # Check for standard log level formats
        severity_patterns = [
            r'\[(ERROR|WARN|INFO|DEBUG|TRACE|FATAL)\]',  # [INFO]
            r'(ERROR|WARN|INFO|DEBUG|TRACE|FATAL):',     # INFO:
            r'(ERROR|WARN|INFO|DEBUG|TRACE|FATAL) -'     # INFO -
        ]
        
        for pattern in severity_patterns:
            match = re.search(pattern, log, re.IGNORECASE)
            if match:
                return match.group(1).upper()
        
        # Check for presence of error-indicating terms
        if re.search(r'error|exception|fail|crash|fatal', log, re.IGNORECASE):
            return 'ERROR'
        elif re.search(r'warn|caution|attention', log, re.IGNORECASE):
            return 'WARN'
            
        return 'UNKNOWN'
        
    def _extract_component(self, log: str) -> str:
        """Extract component name from log."""
        # Try multiple patterns to extract component
        patterns = [
            r'\[([A-Za-z0-9._-]+)\]',        # [component]
            r'([A-Za-z0-9._-]+)\s*:',        # component:
            r'([A-Za-z0-9._-]+)\.(connect|init|start|config|process)', # component.action
        ]
        
        for pattern in patterns:
            match = re.search(pattern, log)
            if match:
                component = match.group(1)
                # Clean up common prefixes/suffixes
                component = re.sub(r'^(service|module|component)\.', '', component)
                return component
                
        # Extract first word after timestamp or log level as fallback
        match = re.search(r'(?:\d{4}-\d{2}-\d{2}|\[(?:INFO|DEBUG|ERROR|WARN)\])[:\s]+([A-Za-z0-9._-]+)', log)
        if match:
            return match.group(1)
                
        return 'unknown'
        
    def _extract_action(self, log: str) -> str:
        """Extract action from log."""
        # Look for common action patterns
        patterns = [
            r':\s*([A-Za-z0-9._-]+)',      # component: action
            r'\.\s*([A-Za-z0-9._-]+)\s*:', # component.action:
            r'(initializing|starting|configuring|processing|connecting|loading|saving|updating|creating|deleting|sending|receiving)',  # action verbs
        ]
        
        for pattern in patterns:
            match = re.search(pattern, log, re.IGNORECASE)
            if match:
                return match.group(1).lower()
                
        # Try to find a verb-noun pattern
        match = re.search(r'\b(init|start|stop|config|process|connect|disconnect|load|save|update|create|delete|send|receive)\s+([A-Za-z0-9._-]+)', log, re.IGNORECASE)
        if match:
            return f"{match.group(1).lower()}_{match.group(2).lower()}"
                
        return 'unknown'
        
    def _find_error_indicators(self, log: str) -> List[str]:
        """Find indicators of errors in log."""
        indicators = []
        error_patterns = [
            'error', 'exception', 'fail', 'invalid',
            'unable to', 'cannot', 'timeout', 'refused',
            'denied', 'rejected', 'unauthorized', 'crash',
            'fatal', 'critical', 'unexpected', 'undefined',
            'null', 'missing', 'not found', 'unavailable'
        ]
        
        log_lower = log.lower()
        for pattern in error_patterns:
            if pattern in log_lower:
                indicators.append(pattern)
                
        return indicators
        
    def _is_startup_related(self, log: str) -> bool:
        """Check if log is related to system startup."""
        startup_terms = [
            'start', 'init', 'boot', 'launch', 'starting',
            'initializing', 'booting', 'launching', 'loading',
            'configuring', 'configuration', 'setup'
        ]
        
        log_lower = log.lower()
        return any(term in log_lower for term in startup_terms)
        
    def _contains_sensitive_info(self, log: str) -> bool:
        """Check if log contains potentially sensitive information."""
        sensitive_patterns = [
            r'password', r'secret', r'token', r'key', r'credential',
            r'auth', r'login', r'user', r'account', r'api[-_]?key',
            r'[a-zA-Z0-9+/]{40,}', r'[0-9a-f]{32,}'  # Long base64 or hex strings
        ]
        
        for pattern in sensitive_patterns:
            if re.search(pattern, log, re.IGNORECASE):
                return True
                
        return False
        
    def _find_patterns(self, log: str, context_logs: List[Dict[str, Any]]) -> List[str]:
        """Find common patterns or sequences in logs."""
        patterns = []
        
        # Check for common log patterns
        if re.search(r'retry|retrying|attempt', log, re.IGNORECASE):
            patterns.append('retry_operation')
            
        if re.search(r'connect|connection', log, re.IGNORECASE):
            patterns.append('connection_operation')
            
        if re.search(r'config|configuration', log, re.IGNORECASE):
            patterns.append('configuration_operation')
            
        # Check for sequence patterns in context logs
        context_log_texts = [l.get('log', '') for l in context_logs if 'log' in l]
        if context_log_texts:
            if any('start' in l.lower() for l in context_log_texts) and any('complete' in l.lower() for l in context_log_texts):
                patterns.append('start_complete_sequence')
                
            if any('request' in l.lower() for l in context_log_texts) and any('response' in l.lower() for l in context_log_texts):
                patterns.append('request_response_sequence')
                
        return patterns

class PromptGenerationStep(WorkflowStep):
    """Generate a prompt for the LLM."""
    
    def __init__(self):
        super().__init__("prompt_generation")
        
    async def execute(self, context: WorkflowContext) -> bool:
        try:
            log = context.get_result("log")
            log_info = context.get_result("log_info")
            
            if not log or not log_info:
                raise ValueError("Missing required context")
                
            prompt = self._build_prompt(log, log_info)
            context.add_result("prompt", prompt)
            return True
            
        except Exception as e:
            logger.error(f"Error in prompt generation: {str(e)}")
            context.add_error(self.name, e)
            return False
            
    def _build_prompt(self, log: str, log_info: Dict[str, Any]) -> str:
        """Build the LLM prompt."""
        prompt = """You are a log analysis expert. Analyze this log entry and determine if it indicates an error, anomaly, or unusual behavior.

Log entry to analyze:
{log}

Key Information:
- Severity: {severity}
- Component: {component}
- Action: {action}
- Error Indicators: {indicators}
- Context Logs: {context_logs}
- Patterns: {patterns}
- Is Startup Related: {is_startup_related}
- Contains Sensitive Info: {contains_sensitive_info}
- Has Numeric Values: {has_numeric_values}

Context logs (if available):
{context_logs}

INSTRUCTIONS:
1. Analyze the log message content, severity, and context
2. Determine if this is a normal operational message or indicates an anomaly/error
3. Respond in EXACTLY the following format:

CLASSIFICATION: [normal/anomaly]
REASON: [brief explanation of your classification]
TAGS: [comma-separated list of relevant tags]

Examples of correct responses:
---
CLASSIFICATION: normal
REASON: Standard informational message about system startup
TAGS: info, startup, configuration
---
CLASSIFICATION: anomaly
REASON: Database connection failure indicates a potential issue
TAGS: error, database, connectivity
---

IMPORTANT: Your response MUST follow this exact format with these exact headings. Do not add any additional text, explanations, or formatting. Always include all three sections: CLASSIFICATION, REASON, and TAGS.
"""
        
        # Format the prompt with log information
        formatted_prompt = prompt.format(
            log=log,
            severity=log_info.get("severity", "Unknown"),
            component=log_info.get("component", "Unknown"),
            action=log_info.get("action", "Unknown"),
            indicators=", ".join(log_info.get("error_indicators", [])) or "None",
            patterns=", ".join(log_info.get("patterns", [])) or "None",
            is_startup_related=log_info.get("is_startup_related", False),
            contains_sensitive_info=log_info.get("contains_sensitive_info", False),
            has_numeric_values=log_info.get("has_numeric_values", False),
            context_logs=self._format_context_logs(log_info.get("context_logs", []))
        )
        
        return formatted_prompt

    def _format_context_logs(self, context_logs: List[Dict[str, Any]]) -> str:
        """Format context logs for the prompt."""
        if not context_logs:
            return "None"
            
        formatted_logs = []
        for log_entry in context_logs:
            if isinstance(log_entry, dict) and 'log' in log_entry:
                timestamp = log_entry.get('timestamp', '')
                log_text = log_entry.get('log', '')
                if timestamp and log_text:
                    formatted_logs.append(f"- [{timestamp}] {log_text}")
                else:
                    formatted_logs.append(f"- {log_text}")
            elif isinstance(log_entry, str):
                formatted_logs.append(f"- {log_entry}")
                
        return "\n".join(formatted_logs[:5])  # Limit to 5 context logs to avoid token limits

class LLMCallStep(WorkflowStep):
    """Make the actual LLM API call."""
    
    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        max_attempts: int = 3,
        session: Optional[aiohttp.ClientSession] = None
    ):
        super().__init__("llm_call")
        if retry_config is None:
            retry_config = RetryConfig(
                max_attempts=max_attempts,
                initial_delay=1.0,
                max_delay=10.0,
                backoff_factor=2.0,
                jitter=0.1,
                retryable_errors=[
                    "timeout", "connection reset", "too many requests",
                    "capacity", "rate limit", "server error",
                    "502", "503", "504", "500", "empty response"
                ]
            )
        self.retry_config = retry_config
        self.session = session
    
    async def execute(self, context: WorkflowContext) -> bool:
        from loganomaly import config as app_config
        logger.info(f"Executing LLM call step")
        try:
            # Use configured provider name
            provider = get_llm_provider(
                app_config.LLM_PROVIDER,
                app_config.LLM_ENDPOINT,
                app_config.LLM_MODEL,
                timeout=app_config.TIMEOUT
            )
            
            prompt = context.get_result("prompt")
            if not prompt:
                raise ValueError("No prompt found in context")
                
            payload = provider.build_payload(prompt)
            
            async def make_llm_call():
                try:
                    async with self.session.post(
                        app_config.LLM_ENDPOINT,
                        json=payload,
                        headers={'Content-Type': 'application/json'}
                    ) as resp:
                        try:
                            logger.info(f"Making LLM call to {app_config.LLM_ENDPOINT}")
                            async with self.session.post(
                                app_config.LLM_ENDPOINT,
                                json=payload,
                                headers={'Content-Type': 'application/json'},
                                timeout=aiohttp.ClientTimeout(total=app_config.TIMEOUT),
                                raise_for_status=False
                            ) as resp:
                                if resp.status != 200:
                                    error_text = await resp.text()
                                    logger.error(f"LLM HTTP error {resp.status}: {error_text}")
                                    raise LLMProviderError(
                                        f"HTTP {resp.status}: {error_text[:100]}...",
                                        app_config.LLM_PROVIDER,
                                        status_code=resp.status
                                    )
                                    
                                try:
                                    data = await resp.json()
                                except Exception as e:
                                    logger.error(f"Failed to parse JSON response: {str(e)}")
                                    return f"Error processing response: Invalid JSON"
                                
                                # Add debug logging to see the raw response
                                logger.debug(f"Raw LLM response data: {data}")
                                
                                response = provider.extract_response(data)
                                
                                # Log the extracted response
                                logger.debug(f"Extracted LLM response: {response}")
                                
                                return response
                        except asyncio.TimeoutError:
                            logger.error(f"LLM request timed out after {app_config.TIMEOUT}s")
                            return "Error: LLM request timed out"
                except aiohttp.ClientError as e:
                    logger.error(f"LLM client error: {str(e)}")
                    raise LLMProviderError(
                        str(e),
                        app_config.LLM_PROVIDER,
                        status_code=getattr(e, 'status', None)
                    )
            
            async def on_retry_error(error: Exception, state):
                delay = await state.get_delay()
                logger.warning(
                    f"LLM call attempt {state.attempts} failed: {str(error)}. "
                    f"Retrying in {delay:.2f}s"
                )
                context.add_result(
                    "retry_status",
                    f"Attempt {state.attempts}/{self.retry_config.max_attempts}"
                )
            
            reply = await with_retry(
                make_llm_call,
                config=self.retry_config,
                error_callback=on_retry_error
            )
            
            # Even if we get an empty or error response from the provider,
            # we'll still continue the workflow with the response we got
            # The provider now returns helpful error messages instead of empty strings
            context.add_result("llm_response", reply)
            
            # Log a warning if the response seems problematic
            if reply.startswith("Error") or reply.startswith("No response") or reply.startswith("Empty response"):
                logger.warning(f"Potentially problematic LLM response: {reply}")
            
            return True
            
        except Exception as e:
            logger.error(f"Error in LLM call: {str(e)}")
            context.add_error("llm_call", e)
            context.add_result("llm_response", f"Error: {str(e)}")
            logger.error("LLM Error: " + str(e))
            return False

class ResponseEvaluationStep(WorkflowStep):
    """Evaluate the LLM response."""
    
    def __init__(self):
        super().__init__("response_evaluation")
        
    async def execute(self, context: WorkflowContext) -> bool:
        try:
            response = context.get_result("llm_response")
            if not response:
                raise ValueError("No LLM response found in context")
                
            # Parse and validate response
            response = response.strip()
            
            # Log the raw response for debugging
            logger.info(f"Raw LLM response for evaluation: {response}")
            
            # Check if response contains error messages from provider
            error_indicators = ["Error processing", "No response generated", "Empty response", 
                               "Error:", "timed out", "Invalid JSON"]
            if any(err in response for err in error_indicators):
                logger.warning(f"LLM returned an error response: {response}")
                context.add_result("classification", "Error")
                context.add_result("reason", f"LLM Error: {response.split(':', 1)[1].strip() if ':' in response else ''}")
                context.add_result("tags", ["Unknown"])
                return True
            
            # Try to extract classification, reason, and tags using regex patterns
            classification = "Unknown"
            reason = response  # Use the entire response as the reason by default
            tags = ["Unknown"]
            
            # Try to extract classification (case insensitive)
            class_patterns = [
                r"(?i)classification:\s*(\w+)",  # CLASSIFICATION: normal
                r"(?i)^(normal|anomaly|error)",  # NORMAL: or ANOMALY: or ERROR:
                r"(?i)this is (normal|anomalous|an anomaly|an error)"  # This is normal/anomalous/an error
            ]
            
            for pattern in class_patterns:
                match = re.search(pattern, response)
                if match:
                    class_value = match.group(1).lower()
                    if class_value in ["normal", "anomaly", "anomalous"]:
                        classification = class_value.capitalize()
                    elif class_value in ["error"]:
                        classification = "Error"
                    break
            
            # Try to extract reason
            reason_patterns = [
                r"(?i)reason:\s*(.+?)(?=\n|tags:|$)",  # REASON: something
                r"(?i)because\s+(.+?)(?=\n|tags:|$)",  # because something
                r"(?i):\s*(.+?)(?=\n|tags:|$)"         # NORMAL: something
            ]
            
            for pattern in reason_patterns:
                match = re.search(pattern, response)
                if match:
                    extracted_reason = match.group(1).strip()
                    if extracted_reason:
                        reason = extracted_reason
                        break
            
            # Try to extract tags
            tags_match = re.search(r"(?i)tags:\s*(.+?)(?=\n|$)", response)
            if tags_match:
                tags_str = tags_match.group(1).strip()
                tags = [tag.strip() for tag in tags_str.split(",") if tag.strip()]
            
            logger.info(f"Extracted classification: {classification}, reason: {reason[:50]}..., tags: {tags}")
            
            # Set results
            context.add_result("classification", classification)
            context.add_result("reason", reason)
            context.add_result("tags", tags)
            
            return True
                
        except Exception as e:
            logger.error(f"Error in response evaluation: {str(e)}")
            context.add_error(self.name, e)
            
            # Even if there's an error, provide default values
            context.add_result("classification", "Error")
            context.add_result("reason", f"Error: {str(e)}")
            context.add_result("tags", ["Unknown"])
            
            return False

class LogAnalysisWorkflow:
    """Main workflow for analyzing logs."""
    
    def __init__(self, config: Dict[str, Any], session: Optional[aiohttp.ClientSession] = None):
        """Initialize the workflow."""
        self.config = config
        self.session = session
        self.steps = [
            ThinkingStep(),
            PromptGenerationStep(),
            LLMCallStep(session=session),
            ResponseEvaluationStep()
        ]
        
    async def execute(self, log: str) -> Dict[str, Any]:
        """Execute the workflow on a log entry."""
        context = WorkflowContext()
        context.add_result("log", log)
        
        for step in self.steps:
            success = await step.execute(context)
            logger.info(f"Executing step: {step.name}")

            
            if not success:
                logger.warning(f"Step {step.name} indicated failure: {context.errors.get(step.name)}")
                break  # Stop workflow on first failure
                
        return {
            'log': log,
            'classification': context.get_result("classification"),
            'reason': context.get_result("reason"),
            'llm_response': context.get_result("llm_response"),
            'errors': context.errors
        }

async def classify_log_llm(log_line: str, context_logs: List[str] = None) -> Dict[str, Any]:
    """Classify a log line using the workflow pipeline."""
    pipeline = LogAnalysisWorkflow({})
    result = await pipeline.execute(log_line)
    return result
