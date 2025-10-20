"""Template mining utilities using Drain3."""

import logging
from typing import Dict, List, Optional
from drain3 import TemplateMiner
from drain3.template_miner_config import TemplateMinerConfig

logger = logging.getLogger(__name__)

def create_template_miner(
    max_clusters: int = 1000,
    max_dist: float = 0.6,
    extra_delimiters: Optional[List[str]] = None
) -> TemplateMiner:
    """Create a configured template miner instance."""
    
    config = TemplateMinerConfig()
    config.profiling_enabled = False
    config.drain_autosave = False  # Disable autosave to reduce logging
    
    # Cluster parameters
    config.max_clusters = max_clusters
    config.max_dist = max_dist
    
    # Add custom delimiters if provided
    if extra_delimiters:
        config.extra_delimiters.extend(extra_delimiters)
        
    # Create miner with quiet logging
    miner = TemplateMiner(config)
    
    # Set Drain3's internal logger to WARNING level
    logging.getLogger("drain3").setLevel(logging.WARNING)
    
    return miner

def extract_templates(logs: List[str], **miner_kwargs) -> Dict[str, List[str]]:
    """Extract templates from a list of logs."""
    miner = create_template_miner(**miner_kwargs)
    templates = {}
    
    for log in logs:
        result = miner.add_log_message(log)
        template = result.template_mined
        
        if template not in templates:
            templates[template] = []
        templates[template].append(log)
        
    return templates

def get_template_stats(templates: Dict[str, List[str]]) -> Dict[str, int]:
    """Get statistics about template distribution."""
    return {
        template: len(logs)
        for template, logs in templates.items()
    }
