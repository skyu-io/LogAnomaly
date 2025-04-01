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
            if not log:
                raise ValueError("No log entry found in context")
                
            # Extract key information from log
            info = {
                'severity': self._extract_severity(log),
                'component': self._extract_component(log),
                'action': self._extract_action(log),
                'error_indicators': self._find_error_indicators(log)
            }
            
            context.add_result("log_info", info)
            return True
            
        except Exception as e:
            logger.error(f"Error in thinking step: {str(e)}")
            context.add_error(self.name, e)
            return False
            
    def _extract_severity(self, log: str) -> str:
        """Extract severity level from log."""
        severity_levels = ['ERROR', 'WARN', 'INFO', 'DEBUG']
        for level in severity_levels:
            if level in log.upper():
                return level
        return 'UNKNOWN'
        
    def _extract_component(self, log: str) -> str:
        """Extract component name from log."""
        # Simple extraction based on common patterns
        patterns = [
            r'\[(.*?)\]',  # [component]
            r'(\w+)\.',    # component.action
            r'(\w+):',     # component:
        ]
        
        for pattern in patterns:
            match = re.search(pattern, log)
            if match:
                return match.group(1)
                
        return 'unknown'
        
    def _extract_action(self, log: str) -> str:
        """Extract action from log."""
        # Look for common action patterns
        patterns = [
            r':\s*(\w+)',      # component: action
            r'\.\s*(\w+)\s*:', # component.action:
        ]
        
        for pattern in patterns:
            match = re.search(pattern, log)
            if match:
                return match.group(1)
                
        return 'unknown'
        
    def _find_error_indicators(self, log: str) -> List[str]:
        """Find indicators of errors in log."""
        indicators = []
        error_patterns = [
            'error', 'exception', 'fail', 'invalid',
            'unable to', 'cannot', 'timeout', 'refused',
            'denied', 'rejected', 'unauthorized'
        ]
        
        log_lower = log.lower()
        for pattern in error_patterns:
            if pattern in log_lower:
                indicators.append(pattern)
                
        return indicators

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

Key Information:
- Severity: {severity}
- Component: {component}
- Action: {action}
- Error Indicators: {indicators}

Consider:
1. Log severity level
2. Message content and context
3. System state and transitions
4. Any error codes or exceptions

IMPORTANT: Respond with EXACTLY one of these two formats and nothing else:
- ANOMALY: <brief reason> (if the log indicates an error or anomaly)
- NORMAL (if the log is a normal operational message)

Do not provide any additional explanation or context beyond these formats.

Log entry to analyze:
{log}
""".format(
            severity=log_info['severity'],
            component=log_info['component'],
            action=log_info['action'],
            indicators=', '.join(log_info['error_indicators']) or 'none',
            log=log
        )
        
        return prompt

class LLMCallStep(WorkflowStep):
    """Make the actual LLM API call."""
    
    def __init__(
        self,
        retry_config: Optional[RetryConfig] = None,
        max_attempts: int = 3
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
    
    async def execute(self, context: WorkflowContext) -> bool:
        from loganomaly import config as app_config
        
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
                    async with aiohttp.ClientSession() as session:
                        async with session.post(
                            app_config.LLM_ENDPOINT,
                            json=payload,
                            headers={'Content-Type': 'application/json'},
                            timeout=aiohttp.ClientTimeout(total=app_config.TIMEOUT)
                        ) as resp:
                            if resp.status != 200:
                                raise LLMProviderError(
                                    f"HTTP {resp.status}",
                                    app_config.LLM_PROVIDER,
                                    status_code=resp.status
                                )
                            data = await resp.json()
                            return provider.extract_response(data)
                except aiohttp.ClientError as e:
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
            
            if not reply or not reply.strip():
                raise LLMProviderError(
                    "Empty response from model",
                    app_config.LLM_PROVIDER
                )
                
            context.add_result("llm_response", reply)
            return True
            
        except Exception as e:
            logger.error(f"Error in LLM call: {str(e)}")
            context.add_error(self.name, e)
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
            
            # Handle more verbose responses
            if response.upper().startswith('NORMAL'):
                # Extract just the classification part
                context.add_result("classification", "normal")
                # If there's a reason in parentheses or after colon, extract it
                if ':' in response:
                    reason = response.split(':', 1)[1].strip()
                    context.add_result("reason", reason)
                else:
                    context.add_result("reason", None)
                return True
                
            elif response.upper().startswith('ANOMALY:'):
                reason = response[8:].strip()
                context.add_result("classification", "anomaly")
                context.add_result("reason", reason)
                return True
                
            else:
                raise ValueError(f"Invalid response format: {response}")
                
        except Exception as e:
            logger.error(f"Error in response evaluation: {str(e)}")
            context.add_error(self.name, e)
            return False

class LogAnalysisWorkflow:
    """Main workflow for analyzing logs."""
    
    def __init__(self, config: Dict[str, Any]):
        """Initialize the workflow."""
        self.config = config
        self.steps = [
            ThinkingStep(),
            PromptGenerationStep(),
            LLMCallStep(),
            ResponseEvaluationStep()
        ]
        
    async def execute(self, log: str) -> Dict[str, Any]:
        """Execute the workflow on a log entry."""
        context = WorkflowContext()
        context.add_result("log", log)
        
        for step in self.steps:
            logger.info(f"Executing step: {step.name}")
            success = await step.execute(context)
            
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
