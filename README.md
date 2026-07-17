<p align="center">
  <img src="demo/arch.png" alt="HackOps AI Architecture" width="700"/>
</p>

<h1 align="center">HackOps AI</h1>

<p align="center">
  <strong>An autonomous multi-agent system that discovers hackathons, evaluates them with AI, and delivers a curated dashboard — zero manual effort.</strong>
</p>

<p align="center">
  <a href="#demo">Demo</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#features">Features</a> •
  <a href="#live-dashboard">Live Dashboard</a> •
  <a href="#tech-stack">Tech Stack</a> •
  <a href="#deployment">Deployment</a>
</p>

---

## Demo

> The Notion database starts **completely empty**. A single Lambda invocation populates it with 70+ AI-analyzed hackathons in under 2 minutes.

<p align="center">
  <img src="demo/empty notion table.png" alt="Empty Notion Table" width="700"/>
  <br/>
  <em>Before — Empty Hackathon Tracker</em>
</p>

<p align="center">
  <a href="demo/demo.mp4">
    <img src="https://img.shields.io/badge/▶_Watch_Demo-blue?style=for-the-badge&logo=youtube" alt="Watch Demo"/>
  </a>
</p>

https://github.com/user-attachments/assets/demo.mp4

**What happens in the video:**
1. Empty Notion database shown
2. AWS Lambda triggered via console
3. Pipeline runs: Discovery → Intelligence → Workspace
4. Notion fills with 70+ hackathons — complete with AI-generated priorities, strategies, and tech stack recommendations

---

## Live Dashboard

🔗 **[View the Hackathon Tracker on Notion](https://app.notion.com/p/3a00cf259e9e8064a44efecb2cf3ab32?v=3a00cf259e9e801d8c59000c72b76a4d)**

Browse the live, auto-updated hackathon database with AI-curated insights.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Amazon EventBridge                         │
│                   (Daily Cron Trigger)                        │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│               HackOps Orchestrator (Lambda)                   │
│          Python 3.13 • 512MB • 300s timeout                  │
└────────┬──────────────────┬──────────────────┬──────────────┘
         │                  │                  │
         ▼                  ▼                  ▼
┌────────────────┐  ┌───────────────┐  ┌───────────────┐
│  Discovery     │  │ Intelligence  │  │  Workspace    │
│  Agent         │  │ Agent         │  │  Agent        │
│                │  │               │  │               │
│ • Devpost      │  │ • Bedrock     │  │ • Create      │
│ • Devfolio     │  │   Nova Micro  │  │ • Update      │
│ • Unstop       │  │ • Mock        │  │ • Archive     │
│                │  │   Fallback    │  │ • Dedup       │
└────────────────┘  └───────────────┘  └───────┬───────┘
                                               │
                                               ▼
                                    ┌───────────────────┐
                                    │  Notion Database   │
                                    │  (Mission Board)   │
                                    └───────────────────┘
```

**Flow:** EventBridge triggers daily → Lambda orchestrates 3 agents in sequence → Discovery scrapes 3 platforms → Intelligence enriches with AI analysis → Workspace syncs to Notion with deduplication.

---

## Features

| Feature | Description |
|---------|-------------|
| 🔍 **Multi-Platform Discovery** | Scrapes Devpost, Devfolio, and Unstop with pagination and detail page visits |
| 🧠 **AI Analysis** | Amazon Bedrock Nova Micro evaluates priority, difficulty, winning probability, and recommends tech stacks |
| 🔄 **Smart Sync** | Deduplication by (title, platform), auto-incrementing serial numbers, expired entry archiving |
| 🛡️ **Resilient** | Retry with backoff, graceful degradation, per-item fallback — never halts the pipeline |
| ⏰ **Fully Automated** | EventBridge triggers daily — no manual intervention needed |
| 🧪 **240+ Tests** | Unit, property-based (Hypothesis), and integration tests |

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Runtime** | Python 3.13, AWS Lambda |
| **AI** | Amazon Bedrock (Nova Micro, ap-south-1) |
| **Scheduling** | Amazon EventBridge |
| **Database** | Notion API |
| **Scraping** | requests, BeautifulSoup4 |
| **Testing** | pytest, Hypothesis |
| **IAM** | Custom role with Bedrock + CloudWatch permissions |

---

## Project Structure

```
hackops-ai/
├── lambda_function.py          # Lambda entry point (orchestrator)
├── main.py                     # Local development runner
├── agents/
│   ├── discovery_agent.py      # Multi-platform scraper (Devpost, Devfolio, Unstop)
│   ├── intelligence_agent.py   # Bedrock AI + deterministic mock fallback
│   └── workspace_agent.py      # Notion CRUD with dedup, archiving, rate limiting
├── models/
│   └── hackathon.py            # Dataclasses: Hackathon, EnrichedHackathon, SyncResult
├── utils/
│   ├── dates.py                # Date normalization (9+ formats → ISO 8601)
│   └── validation.py           # Input validation with strict rules
├── tests/                      # 240+ tests (unit + property-based + integration)
├── deploy/
│   ├── trust-policy.json       # IAM trust policy
│   ├── bedrock-policy.json     # Bedrock + CloudWatch permissions
│   └── make_zip.py             # Lambda packaging script
├── demo/
│   ├── arch.png                # Architecture diagram
│   ├── demo.mp4                # Working demo video
│   └── empty notion table.png  # Before state
├── requirements.txt
└── .env.example
```

---

## Deployment

### Prerequisites

- AWS account with Bedrock model access (Nova Micro in ap-south-1)
- Notion integration token + database
- Python 3.13, AWS CLI

### Quick Deploy

```bash
# 1. Clone
git clone https://github.com/5anjay-s/hackops-ai.git
cd hackops-ai

# 2. Create IAM role
aws iam create-role --role-name hackops-lambda-role \
  --assume-role-policy-document file://deploy/trust-policy.json

aws iam put-role-policy --role-name hackops-lambda-role \
  --policy-name hackops-bedrock-logs \
  --policy-document file://deploy/bedrock-policy.json

# 3. Package & deploy Lambda
pip install -t deploy/package -r requirements.txt
cp lambda_function.py deploy/package/
cp -r agents models utils deploy/package/
python deploy/make_zip.py

aws lambda create-function \
  --function-name hackops-orchestrator \
  --runtime python3.13 \
  --role arn:aws:iam::<ACCOUNT_ID>:role/hackops-lambda-role \
  --handler lambda_function.lambda_handler \
  --zip-file fileb://deploy/hackops-lambda.zip \
  --timeout 300 --memory-size 512 \
  --environment "Variables={NOTION_TOKEN=<token>,DATABASE_ID=<db_id>}"

# 4. Schedule daily trigger
aws events put-rule --name hackops-daily-trigger \
  --schedule-expression "rate(1 day)" --state ENABLED

aws events put-targets --rule hackops-daily-trigger \
  --targets "Id=hackops-lambda,Arn=arn:aws:lambda:ap-south-1:<ACCOUNT_ID>:function:hackops-orchestrator"
```

### Run Locally

```bash
pip install -r requirements.txt
cp .env.example .env   # Add your tokens
python main.py
```

### Run Tests

```bash
pytest tests/ -v
```

---

## Notion Database Schema

| Column | Type | Description |
|--------|------|-------------|
| S.No | Number | Auto-incremented serial |
| Hackathon | Title | Hackathon name |
| Platform | Select | Devpost / Devfolio / Unstop |
| Deadline | Date | Registration deadline |
| Submission Deadline | Date | Submission deadline |
| Themes | Multi-select | Tags/themes |
| Prize | Rich Text | Prize pool |
| Team Size | Rich Text | Size requirement |
| Priority | Select | High / Medium / Low (AI) |
| Difficulty | Select | Easy / Medium / Hard (AI) |
| Winning % | Number | AI win probability (0-100) |
| Suggested Stack | Multi-select | AI tech recommendations |
| Execution Strategy | Rich Text | AI battle plan |
| Status | Status | In progress / Done |
| Registration Link | URL | Direct link |
| Last Synced | Date | UTC sync timestamp |

---

## How It Works

```
Empty Notion DB → Lambda Trigger → 72 hackathons populated in ~2 min
```

1. **Discovery Agent** hits Devpost API, Devfolio GraphQL, and Unstop search API — fetches listings, visits detail pages, normalizes dates, validates data, deduplicates by URL.

2. **Intelligence Agent** sends each hackathon to Bedrock Nova Micro for strategic analysis. If Bedrock is down, falls back to a deterministic algorithm based on prize/themes.

3. **Workspace Agent** queries Notion for existing entries, creates new pages, updates existing ones, archives expired hackathons, handles rate limits with exponential backoff.

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NOTION_TOKEN` | Notion integration secret |
| `DATABASE_ID` | Target database ID |
| `AWS_REGION` | AWS region (default: `ap-south-1`) |

---

<p align="center">
  Built with ☕ and AWS
</p>
