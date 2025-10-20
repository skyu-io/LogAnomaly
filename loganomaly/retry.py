"""Retry logic for handling transient errors."""

import logging
import asyncio
import random
from typing import Callable, TypeVar, Optional, List, Dict, Any
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

T = TypeVar('T')

@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    initial_delay: float = 1.0  # seconds
    max_delay: float = 10.0  # seconds
    backoff_factor: float = 2.0
    jitter: float = 0.1
    
    # List of error types that should trigger a retry
    retryable_errors: List[str] = None
    
    def __post_init__(self):
        # Default retryable errors if none specified
        if self.retryable_errors is None:
            self.retryable_errors = [
                "timeout", "connection", "rate limit",
                "server error", "503", "502", "504",
                "too many requests", "capacity"
            ]

class RetryState:
    """Tracks state for retry operations."""
    
    def __init__(self, config: RetryConfig):
        self.config = config
        self.attempts = 0
        self.last_error: Optional[Exception] = None
        self.start_time = time.time()
        self.history: List[Dict[str, Any]] = []
        
    def should_retry(self, error: Exception) -> bool:
        """Determine if another retry attempt should be made."""
        self.attempts += 1
        self.last_error = error
        
        # Record attempt history
        self.history.append({
            "attempt": self.attempts,
            "error": str(error),
            "time": time.time() - self.start_time
        })
        
        # Check if error is retryable
        error_str = str(error).lower()
        is_retryable = any(
            err_type in error_str 
            for err_type in self.config.retryable_errors
        )
        
        if not is_retryable:
            logger.debug(f"Error not retryable: {error}")
            return False
            
        if self.attempts >= self.config.max_attempts:
            logger.debug(f"Max attempts ({self.config.max_attempts}) reached")
            return False
            
        return True
        
    async def get_delay(self) -> float:
        """Calculate the next retry delay with exponential backoff and jitter."""
        delay = min(
            self.config.initial_delay * (self.config.backoff_factor ** (self.attempts - 1)),
            self.config.max_delay
        )
        
        # Add jitter
        jitter = self.config.jitter * delay * (2 * random.random() - 1)
        delay = max(0, delay + jitter)
        
        return delay
        
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the retry operation."""
        return {
            "attempts": self.attempts,
            "total_time": time.time() - self.start_time,
            "success": self.last_error is None,
            "last_error": str(self.last_error) if self.last_error else None,
            "history": self.history
        }

async def with_retry(
    operation: Callable[[], T],
    config: Optional[RetryConfig] = None,
    error_callback: Optional[Callable[[Exception, RetryState], None]] = None
) -> T:
    """Execute an operation with retry logic.
    
    Args:
        operation: Async function to execute
        config: Retry configuration
        error_callback: Optional callback for retry errors
        
    Returns:
        Result of the operation
        
    Raises:
        The last error encountered if all retries fail
    """
    if config is None:
        config = RetryConfig()
        
    state = RetryState(config)
    
    while True:
        try:
            if asyncio.iscoroutinefunction(operation):
                result = await operation()
            else:
                result = operation()
            return result
            
        except Exception as e:
            if not state.should_retry(e):
                raise
                
            if error_callback:
                if asyncio.iscoroutinefunction(error_callback):
                    await error_callback(e, state)
                else:
                    error_callback(e, state)
                    
            delay = await state.get_delay()
            await asyncio.sleep(delay)
