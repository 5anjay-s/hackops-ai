# HackOps AI 🚀

**An AI-powered multi-agent pipeline that discovers hackathons, analyzes them with Amazon Bedrock, and syncs everything to a Notion dashboard — automatically, every day.**

![Architecture](docs/architecture.png)

## Architecture

```
EventBridge Scheduler (daily cron)
        │
        ▼
┌─────────────────────────┐
│   Lambda Orchestrator   │
│  (hackops-orchestrator) │
└─────────┬───────────────┘
          │
    ┌─────┼─────────────────┐
    ▼     ▼                 ▼
┌──────┐ ┌──────────┐ ┌──────────┐
│Disco-│ │Intelli-  │ │Workspace │
│very  │ │gence     │ │Agent     │
│Agent │ │Agent     │ │          │
└──┬───┘ └────┬─────┘ └────┬─────┘
   │          │             │
   ▼          ▼             ▼
Devpost    Amazon        Notion
Devfolio   Bedrock       Database
Unstop     (Nova Micro)
```

## What It Does

1. **Discovery Agent** — Scrapes hackathon listings from Devpost, Devfolio, and Unstop. Visits detail pages for complete metadata (deadlines, prizes, themes, team size, organizer, mode, location).

2. **Intelligence Agent** — Analyzes each hackathon using Amazon Bedrock Nova Micro to generate priority ratings, difficulty assessment, winning probability, recommended tech stack, team size, and execution strategy.

3. **Workspace Agent** — Syncs enriched data to a Notion database with deduplication, auto-incremented serial numbers, and expired entry archiving.

## Tech Stack

- **Runtime:** Python 3.13 on AWS Lambda
- **AI:** Amazon Bedrock (Nova Micro) with deterministic mock fallback
- **Database:** Notion API
- **Scheduling:** Amazon EventBridge
- **Scraping:** requests + BeautifulSoup
- **Testing:** pytest + hypothesis (property-based testing)

## Project Structure

```
hackops-ai/
├── lambda_function.py          # Lambda entry point (orchestrator)
├── main.py                     # Local development entry point
├── agents/
│   ├── discovery_agent.py      # Multi-platform hackathon scraper
│   ├── intelligence_agent.py   # Bedrock AI analysis + mock fallback
│   └── workspace_agent.py      # Notion sync with dedup & archiving
├── models/
│   ├── __init__.py
│   └── hackathon.py            # Dataclasses: Hackathon, EnrichedHackathon, etc.
├── utils/
│   ├── __init__.py
│   ├── dates.py                # Date normalization (ISO 8601)
│   └── validation.py           # Hackathon data validation
├── tests/                      # 240+ tests (unit + property-based + integration)
├── deploy/
│   ├── trust-policy.json       # IAM trust policy for Lambda
│   ├── bedrock-policy.json     # IAM policy for Bedrock + CloudWatch
│   └── make_zip.py             # Deployment packaging script
├── requirements.txt
└── pytest.ini
```

## Deployment

### Prerequisites
- AWS CLI configured with appropriate IAM permissions
- Python 3.13
- Notion integration token + database with required schema

### Deploy to AWS

```bash
# 1. Create IAM role
aws iam create-role --role-name hackops-lambda-role \
  --assume-role-policy-document file://deploy/trust-policy.json

aws iam put-role-policy --role-name hackops-lambda-role \
  --policy-name hackops-bedrock-logs \
  --policy-document file://deploy/bedrock-policy.json

# 2. Package Lambda
pip install -t deploy/package requests beautifulsoup4 boto3 notion-client python-dotenv
cp lambda_function.py deploy/package/
cp -r agents models utils deploy/package/
python deploy/make_zip.py

# 3. Create Lambda function
aws lambda create-function \
  --function-name hackops-orchestrator \
  --runtime python3.13 \
  --role arn:aws:iam::<ACCOUNT_ID>:role/hackops-lambda-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://deploy/hackops-lambda.zip \
  --timeout 300 --memory-size 512 \
  --environment "Variables={NOTION_TOKEN=<token>,DATABASE_ID=<db_id>}"

# 4. Create EventBridge schedule (daily)
aws events put-rule --name hackops-daily-trigger \
  --schedule-expression "rate(1 day)" --state ENABLED

aws events put-targets --rule hackops-daily-trigger \
  --targets "Id=hackops-lambda,Arn=arn:aws:lambda:<region>:<account>:function:hackops-orchestrator"
```

### Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Set environment variables
cp .env.example .env  # Edit with your tokens

# Run the pipeline
python main.py
```

### Run Tests

```bash
pip install pytest hypothesis
pytest tests/ -v
```

## Notion Database Schema

| Column | Type | Source |
|--------|------|--------|
| S.No | Number | Auto-incremented |
| Hackathon | Title | Hackathon name |
| Platform | Select | Devpost / Devfolio / Unstop |
| Deadline | Date | Registration deadline |
| Submission Deadline | Date | Submission deadline |
| Themes | Multi-select | Hackathon themes/tags |
| Prize | Rich Text | Prize description |
| Team Size | Rich Text | Team size requirement |
| Priority | Select | High / Medium / Low |
| Difficulty | Select | Easy / Medium / Hard |
| Winning % | Number | AI-predicted win probability |
| Suggested Stack | Multi-select | Recommended technologies |
| Execution Strategy | Rich Text | AI-generated strategy |
| Status | Status | In progress / Done |
| Registration Link | URL | Direct link to hackathon |
| Last Synced | Date | UTC timestamp of last sync |

## Key Features

- **Resilient scraping** — Retries failed requests, skips broken pages, never halts the pipeline
- **Deduplication** — By registration URL (discovery) and (title, platform) pair (Notion)
- **Rate limit handling** — Exponential backoff (1s, 2s, 4s) on Notion 429 responses
- **Graceful degradation** — Falls back to deterministic mock when Bedrock is unavailable
- **Date normalization** — Handles 9+ date formats, extracts end dates from ranges
- **240+ automated tests** — Unit, property-based (hypothesis), and integration tests

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NOTION_TOKEN` | Notion integration secret token |
| `DATABASE_ID` | Notion database ID (32-char hex) |
| `AWS_REGION` | AWS region (default: ap-south-1) |

## License

MIT
