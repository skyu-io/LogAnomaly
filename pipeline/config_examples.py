#!/usr/bin/env python3
"""
Example configurations for different pipeline runs
"""

from typing import List, Dict

def get_production_config() -> List[Dict[str, str]]:
    """Production log groups configuration"""
    return [
        {"name": "prod-lambda-1", "logGroup": "/aws/lambda/prod-service-1", "uniqueLabel": ""},
        {"name": "prod-lambda-2", "logGroup": "/aws/lambda/prod-service-2", "uniqueLabel": ""},
        {"name": "prod-eks-cluster", "logGroup": "/aws/eks/prod-cluster/cluster", "uniqueLabel": "namespace"},
    ]

def get_staging_config() -> List[Dict[str, str]]:
    """Staging log groups configuration"""
    return [
        {"name": "staging-lambda-1", "logGroup": "/aws/lambda/staging-service-1", "uniqueLabel": ""},
        {"name": "staging-eks-cluster", "logGroup": "/aws/eks/staging-cluster/cluster", "uniqueLabel": "namespace"},
    ]

def get_development_config() -> List[Dict[str, str]]:
    """Development log groups configuration"""
    return [
        {"name": "dev-lambda-1", "logGroup": "/aws/lambda/dev-service-1", "uniqueLabel": ""},
        {"name": "dev-eks-cluster", "logGroup": "/aws/eks/dev-cluster/cluster", "uniqueLabel": "namespace"},
    ]

def get_custom_config(log_groups: List[str], environment: str = "custom") -> List[Dict[str, str]]:
    """Create custom configuration from list of log groups"""
    config = []
    for i, log_group in enumerate(log_groups):
        config.append({
            "name": f"{environment}-loggroup-{i+1}",
            "logGroup": log_group,
            "uniqueLabel": ""
        })
    return config

# Example usage:
if __name__ == "__main__":
    print("Production config:")
    print(get_production_config())
    
    print("\nCustom config:")
    print(get_custom_config(["/aws/lambda/my-service", "/aws/eks/my-cluster/cluster"]))
