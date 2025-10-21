#!/usr/bin/env python3
"""
Usage examples for the log anomaly pipeline with different configurations
"""

from worker import pipeline, run_pipeline_with_config
from config_examples import get_production_config, get_staging_config, get_custom_config

def run_default_pipeline():
    """Run pipeline with default configuration"""
    print("Running pipeline with default configuration...")
    pipeline()

def run_production_pipeline():
    """Run pipeline with production log groups"""
    print("Running pipeline with production configuration...")
    production_config = get_production_config()
    run_pipeline_with_config(production_config)

def run_staging_pipeline():
    """Run pipeline with staging log groups"""
    print("Running pipeline with staging configuration...")
    staging_config = get_staging_config()
    run_pipeline_with_config(staging_config)

def run_custom_pipeline():
    """Run pipeline with custom log groups"""
    print("Running pipeline with custom configuration...")
    custom_log_groups = [
        "/aws/lambda/my-custom-service",
        "/aws/eks/my-custom-cluster/cluster",
        "/aws/lambda/another-service"
    ]
    custom_config = get_custom_config(custom_log_groups, "my-env")
    run_pipeline_with_config(custom_config)

def run_dry_run():
    """Run pipeline in dry-run mode"""
    print("Running pipeline in dry-run mode...")
    pipeline(dry_run=True)

if __name__ == "__main__":
    # Choose which example to run
    run_default_pipeline()
    # run_production_pipeline()
    # run_staging_pipeline()
    # run_custom_pipeline()
    # run_dry_run()
