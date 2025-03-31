import aiohttp
import asyncio
import time
import tiktoken
import random
import logging
import os
from tqdm import tqdm

from loganomaly.utils import contains_secret_patterns, short_reason, clean_log_line, extract_tags
from loganomaly.prompt import build_llm_prompt, summarize_context_logs, clean_tags, VALID_TAGS
from loganomaly.llm_provider import get_llm_provider
from loganomaly import config as app_config

LLM_STATS = {
    "total_calls": 0,
    "total_time": 0.0,
    "errors": 0,
    "total_tokens": 0,
    "context_trimmed": 0
}

tokenizer = tiktoken.get_encoding("cl100k_base")
MAX_RETRIES = 3
MAX_TOTAL_TOKENS = 2048

logging.basicConfig(filename='error.log', level=logging.ERROR,
                    format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger()

os.environ["TOKENIZERS_PARALLELISM"] = "false"


def apply_dependent_anomaly_filter(row):
    if not app_config.ENABLE_DEPENDENT_ANOMALY_FILTER:
        return row

    log_line = row.get("log", "")
    classification = row.get("classification", "")

    if classification == "Unknown" and log_line.strip().startswith("at "):
        row["classification"] = "Dependent Anomaly"
        row["reason"] = "Stack trace line, follows an actual error."
        row["is_anomaly"] = 0

    return row


async def classify_log_llm(session, log_line, context_logs):
    global LLM_STATS
    start_time = time.time()
    retries = 0

    provider_name = app_config.LLM_MODEL.split(":")[0]
    provider = get_llm_provider(
        provider_name,
        app_config.LLM_ENDPOINT,
        app_config.LLM_MODEL,
        timeout=app_config.TIMEOUT
    )

    while retries < MAX_RETRIES:
        try:
            if len(log_line) > app_config.MAX_LOG_LENGTH:
                log_line = log_line[:app_config.MAX_LOG_LENGTH] + "..."

            if contains_secret_patterns(log_line):
                LLM_STATS["total_calls"] += 1
                LLM_STATS["total_time"] += time.time() - start_time
                return "Sensitive Information Leak", "Contains possible secret/token.", ["Sensitive", "Security Threat"]

            # Context summarization
            context_summary = summarize_context_logs(context_logs)
            total_text = log_line + "\n" + context_summary
            input_tokens = len(tokenizer.encode(total_text))

            if input_tokens > MAX_TOTAL_TOKENS:
                logger.warning(f"Context too large ({input_tokens} tokens), sending log only.")
                context_summary = ""
                total_text = log_line
                LLM_STATS["context_trimmed"] += 1

            prompt = build_llm_prompt(log_line, context_logs if context_summary else [])
            payload = provider.build_payload(prompt)
            headers = {'Content-Type': 'application/json'}

            async with session.post(app_config.LLM_ENDPOINT, json=payload, headers=headers, timeout=app_config.TIMEOUT) as resp:
                resp_text = await resp.text()

                if resp.status != 200:
                    logger.error(f"LLM Error: Status {resp.status}, Response: {resp_text}")
                    return "Error", f"LLM Error: {resp_text}", ["Unknown"]

                data = await resp.json()
                reply = provider.extract_response(data)

                if not reply:
                    logger.error(f"Empty reply from LLM for log: {log_line}")
                    return "Unknown", "Empty reply from LLM", ["Unknown"]

                label, reason, tags = extract_tags(reply)
                tags = clean_tags(tags, VALID_TAGS)

                output_tokens = len(tokenizer.encode(reply))
                LLM_STATS["total_tokens"] += input_tokens + output_tokens
                LLM_STATS["total_calls"] += 1
                LLM_STATS["total_time"] += time.time() - start_time

                return label, short_reason(reason), tags

        except Exception as e:
            retries += 1
            if retries >= MAX_RETRIES:
                LLM_STATS["errors"] += 1
                logger.error(f"LLM Error on log: {log_line} → {str(e)}")
                return "Error", f"LLM Error: {str(e)}", ["Unknown"]
            else:
                await asyncio.sleep(random.uniform(1, 2))


async def classify_anomalies(anomalies_df):
    global LLM_STATS

    classifications = []
    reasons = []
    cleaned_logs = []
    tags_list = []

    connector = aiohttp.TCPConnector(limit=app_config.CONCURRENCY)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = []
        for _, row in anomalies_df.iterrows():
            log_line = row["log"]
            context_logs = row.get("context_logs", [])
            tasks.append(classify_log_llm(session, log_line, context_logs))

        with tqdm(total=len(anomalies_df), desc="LLM Classification") as pbar:
            for idx, future in enumerate(asyncio.as_completed(tasks)):
                label, reason, tags = await future
                classifications.append(label)
                reasons.append(reason)
                tags_list.append(tags)
                cleaned_logs.append(clean_log_line(anomalies_df.iloc[idx]["log"]))
                pbar.update(1)

    return classifications, reasons, cleaned_logs, tags_list, LLM_STATS
