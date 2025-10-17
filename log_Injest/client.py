# skyu_logs/client.py
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from prefect import get_run_logger
import requests

from .constants import (
    API_BASE_DEFAULT,
    ORGANIZATIONS_ENDPOINT,
    APPLICATIONS_ENDPOINT,
    CLUSTERS_ENDPOINT,
    LOGS_QUERY_ENDPOINT,
    LOGS_RESULT_ENDPOINT,
)
from .http_client import build_url, new_session
from .skyu_api_service import get_org_info, get_applications, get_clusters
from .extractors import extract_application_ids, list_projects_from_org_payload, summarize_clusters
from .logs_flow import retrieve_app_logs_for_cluster

class SkyuClient:
    def __init__(
        self,
        *,
        token: str,
        orgid: str,
        base_url: str = API_BASE_DEFAULT,
        session: Optional[requests.Session] = None,
    ) -> None:
        self.token = token
        self.orgid = orgid
        self.base_url = base_url
        self.session = session or new_session()

        self.org_url = build_url(base_url, ORGANIZATIONS_ENDPOINT)
        self.applications_url = build_url(base_url, APPLICATIONS_ENDPOINT)
        self.clusters_url = build_url(base_url, CLUSTERS_ENDPOINT)
        self.logs_query_url = build_url(base_url, LOGS_QUERY_ENDPOINT)
        self.logs_result_url = build_url(base_url, LOGS_RESULT_ENDPOINT)

    def list_projects(self) -> List[Tuple[str, str]]:
        logger = get_run_logger()
        payload = get_org_info(self.session, self.org_url, self.token, self.orgid)
        projects = list_projects_from_org_payload(payload)
        if not projects:
            logger.debug("[list_projects] no projects found")
        return projects

    def list_app_ids(self, project_id: str) -> List[str]:
        payload = get_applications(self.session, self.applications_url, self.token, self.orgid, project_id)
        return extract_application_ids(payload)

    def get_clusters_summary(self, project_id: str) -> List[Dict[str, Any]]:
        payload = get_clusters(self.session, self.clusters_url, self.token, self.orgid, project_id)
        return summarize_clusters(payload)

    def fetch_logs_for_project(
        self,
        *,
        project_id: str,
        credential_id: str,
        out_dir: Optional[Path] = Path("./logs_out"),
        start: Optional[str] = None,
        end: Optional[str] = None,
        namespace_override: Optional[str] = None,
        log_group_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        logger = get_run_logger()
        apps_mapping: Dict[str, Dict[str, List[str]]] = {self.orgid: {}}
        clusters_by_project: Dict[str, List[Dict[str, Any]]] = {}
        logs_aggregated: List[Dict[str, Any]] = []

        
        app_ids = self.list_app_ids(project_id)
        apps_mapping[self.orgid][project_id] = app_ids

        clusters = self.get_clusters_summary(project_id)
        clusters_by_project[project_id] = clusters

        if not clusters:
            for app_id in app_ids:
                logger.debug(f"No clusters available for this app: {app_id} (project {project_id})")
            return {
                "apps_info": apps_mapping,
                "clusters_info": clusters_by_project,
                "logsSummary_acquired": [],
            }

        for cs in clusters:
            region = (cs.get("aws") or {}).get("region")
            cluster_name = cs.get("name")
            env_id = cs.get("envId")
            if not region or not cluster_name or not env_id:
                continue

            for app_id in app_ids:
                namespace = namespace_override or f"project-{project_id.split('_', 1)[-1]}-prod"
                log_group = log_group_override or f"/aws/containerinsights/{cluster_name}/application"

                retrieve_app_logs_for_cluster(
                    session=self.session,
                    logs_query_url=self.logs_query_url,
                    logs_result_url=self.logs_result_url,
                    token=self.token,
                    orgid=self.orgid,
                    project_id=project_id,
                    credential_id=credential_id,
                    region=region,
                    cluster_name=cluster_name,
                    env_id=env_id,
                    app_id=app_id,
                    namespace=namespace,
                    log_group=log_group,
                    out_dir=out_dir,
                    logs_aggregated=logs_aggregated,
                    start=start,
                    end=end,
                )

        return {
            "apps_info": apps_mapping,
            "clusters_info": clusters_by_project,
            "logsSummary_acquired": [
                {"projectId": it["projectId"], "cluster": it["cluster"], "appId": it["appId"], "count": len(it["results"])}
                for it in logs_aggregated
            ],
        }

    def fetch_logs_for_all_projects(
        self,
        *,
        credential_id: str,
        namespace_override: Optional[str] = None,
        log_group_override: Optional[str] = None,
        out_dir: Optional[Path] = Path("./logs_out"),
        start: Optional[str] = None,
        end: Optional[str] = None,
    ) -> Dict[str, Any]:
        logger = get_run_logger()
        apps_mapping: Dict[str, Dict[str, List[str]]] = {self.orgid: {}}
        clusters_by_project: Dict[str, List[Dict[str, Any]]] = {}
        logs_aggregated: List[Dict[str, Any]] = []

        projects = self.list_projects()
        if not projects:
            return {"apps_info": apps_mapping, "clusters_info": {}, "logsSummary_acquired": []}

        for project_id, _name in projects:
            clusters_by_project.setdefault(project_id, [])

            try:
                app_ids = self.list_app_ids(project_id)
                apps_mapping[self.orgid][project_id] = app_ids
            except Exception as e:
                logger.debug(f"[WARN] applications request failed for project {project_id}: {e}")
                apps_mapping[self.orgid][project_id] = []
                app_ids = []

            try:
                summaries = self.get_clusters_summary(project_id)
                clusters_by_project[project_id].extend(summaries)
            except Exception as e:
                logger.debug(f"[WARN] clusters request failed for project {project_id}: {e}")
                continue

            if not clusters_by_project.get(project_id):
                for app_id in app_ids:
                    logger.debug(f"No clusters available for this app: {app_id} (project {project_id})")
                continue

            for cs in clusters_by_project.get(project_id, []):
                region = (cs.get("aws") or {}).get("region")
                cluster_name = cs.get("name")
                env_id = cs.get("envId")
                if not region or not cluster_name or not env_id:
                    continue

                for app_id in app_ids:
                    namespace = namespace_override or f"project-{project_id.split('_', 1)[-1]}-prod"
                    log_group = log_group_override or f"/aws/containerinsights/{cluster_name}/application"

                    retrieve_app_logs_for_cluster(
                        session=self.session,
                        logs_query_url=self.logs_query_url,
                        logs_result_url=self.logs_result_url,
                        token=self.token,
                        orgid=self.orgid,
                        project_id=project_id,
                        credential_id=credential_id,
                        region=region,
                        cluster_name=cluster_name,
                        env_id=env_id,
                        app_id=app_id,
                        namespace=namespace,
                        log_group=log_group,
                        out_dir=out_dir,
                        logs_aggregated=logs_aggregated,
                        start=start,
                        end=end,
                    )

        return {
            "apps": apps_mapping,
            "clusters": clusters_by_project,
            "logsSummary": [
                {"projectId": it["projectId"], "cluster": it["cluster"], "appId": it["appId"], "count": len(it["results"])}
                for it in logs_aggregated
            ],
        }
