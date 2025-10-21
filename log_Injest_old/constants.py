# skyu_logs/constants.py
API_BASE_DEFAULT = "https://api.skyu.io/"
ORGANIZATIONS_ENDPOINT = "resource-service/organizations/find?populate=true"
APPLICATIONS_ENDPOINT = "resource-service/applications/findApplications?populate=true"
CLUSTERS_ENDPOINT = "cluster-service/cluster"
LOGS_QUERY_ENDPOINT = "credential-service/kubernetes/clusters/logs/query"
LOGS_RESULT_ENDPOINT = "credential-service/kubernetes/clusters/logs/logs"
HTTP_TIMEOUT = 30  # seconds

OUT_DIR_DEFAULT = "./logs_out"                   # <- used as out_dir
