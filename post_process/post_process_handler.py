# # handler_invoke.py
# from post_process.result_analyse import build_template_data
# from post_process.send_notification import send_email_notification
# from pipeline.constants import EMAIL_NOTIFICATION_URL, TO_EMAIL, TEMPLATE_NAME, USER_AGENT, TIMEOUT

# def post_process_handler(
#     *,
#     summaries_dir: str,
#     bearer_token: str,
#     org_id: str,
#     project_id: str,
#     top_k: int = 10,
#     max_reports: int | None = 25,
#     dry_run: bool = False,
# ):
#     # 1) Build the template payload (pure)
#     template_data = build_template_data(
#         summaries_dir=summaries_dir,
#         pattern="*_summary.json",
#         top_k=top_k,
#         max_reports=max_reports,
#         include_subject_preheader=True,  # optional but handy
#     )

#     # 2) Send using constants
#     status, resp = send_email_notification(
#         template_data=template_data,
#         api_url=EMAIL_NOTIFICATION_URL,
#         bearer_token=bearer_token,
#         org_id=org_id,
#         project_id=project_id,
#         to_email=TO_EMAIL,
#         template_name=TEMPLATE_NAME,
#         user_agent=USER_AGENT,
#         timeout=TIMEOUT,
#         dry_run=dry_run,
#     )
#     return status, resp, template_data
