# skyu_logs/extractors.py
from typing import Any, Dict, List, Tuple
from prefect import get_run_logger


def extract_application_ids(payload: Any) -> List[str]:
    """Extract application IDs from the applications payload."""
    logger = get_run_logger()
    logger.debug("[extract_application_ids] started")
    
    if not payload or not isinstance(payload, dict):
        logger.debug("[extract_application_ids] empty or invalid payload")
        return []
    
    # Extract application IDs from the payload structure
    # This is a placeholder implementation - adjust based on actual payload structure
    applications = payload.get('data', []) if isinstance(payload.get('data'), list) else []
    app_ids = []
    
    for app in applications:
        if isinstance(app, dict) and 'id' in app:
            app_ids.append(app['id'])
    
    logger.debug(f"[extract_application_ids] found {len(app_ids)} applications")
    return app_ids


def list_projects_from_org_payload(payload: Any) -> List[Tuple[str, str]]:
    """Extract project information from organization payload."""
    logger = get_run_logger()
    logger.debug("[list_projects_from_org_payload] started")
    
    if not payload or not isinstance(payload, dict):
        logger.debug("[list_projects_from_org_payload] empty or invalid payload")
        return []
    
    # Extract project information from the payload structure
    # This is a placeholder implementation - adjust based on actual payload structure
    projects = payload.get('data', []) if isinstance(payload.get('data'), list) else []
    project_list = []
    
    for project in projects:
        if isinstance(project, dict) and 'id' in project:
            project_id = project['id']
            project_name = project.get('name', project_id)
            project_list.append((project_id, project_name))
    
    logger.debug(f"[list_projects_from_org_payload] found {len(project_list)} projects")
    return project_list


def summarize_clusters(payload: Any) -> List[Dict[str, Any]]:
    """Summarize cluster information from clusters payload."""
    logger = get_run_logger()
    logger.info("[summarize_clusters] started")
    logger.info(f"[summarize_clusters] payload type: {type(payload)}")
    
    if not payload:
        logger.info("[summarize_clusters] empty payload")
        return []
    
    # The API returns a list of clusters directly, not wrapped in a 'data' key
    if isinstance(payload, list):
        clusters = payload
    elif isinstance(payload, dict) and 'data' in payload:
        clusters = payload['data']
    else:
        logger.info(f"[summarize_clusters] unexpected payload structure: {type(payload)}")
        return []
    
    cluster_summaries = []
    
    for cluster in clusters:
        if isinstance(cluster, dict) and 'id' in cluster:
            # Extract AWS region from the nested structure
            aws_region = 'unknown'
            if 'aws' in cluster and isinstance(cluster['aws'], dict):
                aws_region = cluster['aws'].get('region', 'unknown')
            
            # Extract environment ID
            env_id = 'unknown'
            if 'envs' in cluster and isinstance(cluster['envs'], list) and len(cluster['envs']) > 0:
                env_id = cluster['envs'][0].get('id', 'unknown')
            
            summary = {
                'id': cluster['id'],
                'name': cluster.get('name', cluster['id']),
                'status': 'connected' if cluster.get('connected', False) else 'disconnected',
                'region': aws_region,
                'provider': cluster.get('type', 'unknown'),
                'envId': env_id,
                'aws': cluster.get('aws', {})
            }
            cluster_summaries.append(summary)
    
    logger.info(f"[summarize_clusters] found {len(cluster_summaries)} clusters")
    return cluster_summaries
