# Environment Variables Setup

This pipeline requires several environment variables to be set before running.

## Quick Setup

1. Install `python-dotenv`:
   ```bash
   pip install python-dotenv
   ```

2. Create a `.env` file in the project root with these variables:

```bash
# Required
DEFAULT_SKYU_API_URL=https://api.skyu.io/
SKYU_EMAIL_NOTIFICATION_PATH=/v1/email/send-template
SKYU_ALERT_TO_EMAIL=alerts@yourcompany.com
SKYU_TEMPLATE_NAME=siem-alert-aggregate
DEFAULT_PROVIDER=aws
DEFAULT_RESOURCE_ID=resource_id_here

# Optional (with defaults)
SKYU_FILE_SERVICE_PATH=/file-service
SKYU_USER_AGENT=loganomaly-worker/1.0
SKYU_HTTP_TIMEOUT=20
```

## Environment Variables Reference

### Required Variables

- **SKYU_API_BASE_URL**: Base API URL for SkyU services
  - Example: `https://api.skyu.io/`

- **SKYU_EMAIL_NOTIFICATION_URL**: The API endpoint URL for sending email notifications
  - Example: `https://notify.dev.skyu.io/v1/email/send-template`

- **SKYU_ALERT_TO_EMAIL**: Email address to send alerts to
  - Example: `alerts@yourcompany.com`

- **SKYU_TEMPLATE_NAME**: Name of the email template to use
  - Example: `siem-alert-aggregate`

- **DEFAULT_PROVIDER**: Default cloud provider (e.g., "aws")

- **DEFAULT_RESOURCE_ID**: Default resource ID for file uploads

### Optional Variables

- **SKYU_FILE_SERVICE_PATH**: Path for the file service API (default: `/file-service`)

- **SKYU_USER_AGENT**: User agent string for HTTP requests (default: `loganomaly-worker/1.0`)

- **SKYU_HTTP_TIMEOUT**: HTTP request timeout in seconds (default: `20`)

- **OUT_DIR_DEFAULT**: Default output directory

## Setting Variables Without .env File

You can also set environment variables directly:

**Windows (PowerShell):**
```powershell
$env:SKYU_API_BASE_URL="https://api.skyu.io/"
$env:SKYU_EMAIL_NOTIFICATION_URL="https://notify.dev.skyu.io/v1/email/send-template"
$env:SKYU_ALERT_TO_EMAIL="alerts@yourcompany.com"
$env:SKYU_TEMPLATE_NAME="siem-alert-aggregate"
$env:DEFAULT_PROVIDER="aws"
$env:DEFAULT_RESOURCE_ID="resource_id_here"
```

**Windows (CMD):**
```cmd
set SKYU_API_BASE_URL=https://api.skyu.io/
set SKYU_EMAIL_NOTIFICATION_URL=https://notify.dev.skyu.io/v1/email/send-template
set SKYU_ALERT_TO_EMAIL=alerts@yourcompany.com
set SKYU_TEMPLATE_NAME=siem-alert-aggregate
set DEFAULT_PROVIDER=aws
set DEFAULT_RESOURCE_ID=resource_id_here
```

**Linux/Mac:**
```bash
export SKYU_API_BASE_URL="https://api.skyu.io/"
export SKYU_EMAIL_NOTIFICATION_URL="https://notify.dev.skyu.io/v1/email/send-template"
export SKYU_ALERT_TO_EMAIL="alerts@yourcompany.com"
export SKYU_TEMPLATE_NAME="siem-alert-aggregate"
export DEFAULT_PROVIDER="aws"
export DEFAULT_RESOURCE_ID="resource_id_here"
```

