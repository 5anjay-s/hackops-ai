<h1 align="center"> HackOps AI</h1>

<p align="center">
  <strong>A serverless multi-agent system that discovers hackathons, evaluates them with Amazon Bedrock, and delivers a live Notion dashboard — fully automated, every day.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.13-blue?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/AWS_Lambda-Serverless-FF9900?logo=awslambda&logoColor=white" />
  <img src="https://img.shields.io/badge/Amazon_Bedrock-Nova_Micro-8B5CF6?logo=amazon&logoColor=white" />
  <img src="https://img.shields.io/badge/Notion-Synced-000000?logo=notion&logoColor=white" />
  <img src="https://img.shields.io/badge/tests-240+-22C55E?logo=pytest&logoColor=white" />
</p>

<p align="center">
  <a href="#how-it-works">How It Works</a> •
  <a href="#live-dashboard">Live Dashboard</a> •
  <a href="#demo">Demo</a> •
  <a href="#architecture">Architecture</a> •
  <a href="#aws-services">AWS Services</a> •
  <a href="#deployment">Deployment</a>
</p>

---

## How It Works

HackOps AI runs a three-agent pipeline on AWS Lambda, triggered daily by EventBridge:

| Step | Agent | Action |
|:----:|-------|--------|
| 1 | **Discovery Agent** | Scrapes Devpost, Devfolio, and Unstop — visits every detail page for deadlines, prizes, themes, team size, and organizer |
| 2 | **Intelligence Agent** | Calls Amazon Bedrock Nova Micro to generate priority, difficulty, winning probability, recommended stack, and execution strategy |
| 3 | **Workspace Agent** | Syncs to Notion with deduplication, auto serial numbers, and expired entry archiving |

**One trigger. 72 hackathons. Zero manual work.**

---

## Live Dashboard

> **[🔗 View the Hackathon Tracker on Notion](https://app.notion.com/p/3a00cf259e9e8064a44efecb2cf3ab32?v=3a00cf259e9e801d8c59000c72b76a4d)**

<p align="center">
  <img src="demo/filled notion table.png" alt="Populated Hackathon Tracker" width="750"/>
</p>

Every row includes AI-generated strategic analysis — priorities, difficulty ratings, winning probability, and recommended tech stacks. Updated automatically every 24 hours.

---

## Demo

<details>
<summary><strong>📋 Before — Empty Database</strong></summary>
<br/>
<p align="center">
  <img src="demo/empty notion table.png" alt="Empty Notion Database" width="700"/>
</p>
<p align="center"><em>The Hackathon Tracker starts completely empty. All data comes from the automated pipeline.</em></p>
</details>

<br/>

<p align="center">
  <img src="demo/demo.gif" alt="HackOps AI Demo" width="700"/>
</p>

<p align="center">
  <a href="https://youtu.be/uiK-voe0Y40">
    <img src="https://img.shields.io/badge/▶_Full_Demo_on_YouTube-FF0000?style=for-the-badge&logo=youtube&logoColor=white" alt="Watch on YouTube"/>
  </a>
</p>

**What the demo shows:**
1. Empty Notion database (zero entries)
2. AWS Lambda triggered from the console
3. Pipeline executes: Discovery → Bedrock AI → Notion sync
4. 72 hackathons appear in Notion with full AI analysis
5. EventBridge daily schedule confirmed in AWS Console

---

## Architecture

<p align="center">
  <img src="demo/arch.png" alt="Architecture Diagram" width="700"/>
</p>

```
EventBridge (rate: 1 day)
       ↓
Lambda Orchestrator ─── validates env → short-circuits if empty
       ↓
Discovery Agent ─────── Devpost API + Devfolio GraphQL + Unstop Search
       ↓                 visits detail pages, normalizes dates, validates, deduplicates
       ↓
Intelligence Agent ──── Amazon Bedrock Nova Micro (ap-south-1)
       ↓                 structured prompt → JSON response → validation
       ↓                 falls back to deterministic mock on failure
       ↓
Workspace Agent ─────── queries existing Notion pages (pagination)
       ↓                 creates new / updates existing / archives expired
       ↓                 exponential backoff on rate limits
       ↓
Notion Database ─────── 72 hackathons with 16 properties each
```

---

## AWS Services

| Service | Role in HackOps AI |
|---------|-------------------|
| **AWS Lambda** | Runs the orchestrator (`hackops-orchestrator`) — Python 3.13, 512MB, 300s timeout |
| **Amazon Bedrock** | Nova Micro model generates strategic AI analysis per hackathon (10s timeout, JSON output) |
| **Amazon EventBridge** | Daily cron trigger (`rate(1 day)`) — fully automated scheduling |
| **Amazon CloudWatch** | Captures execution logs — discovery counts, Bedrock failures, sync results |
| **AWS IAM** | Custom role with `bedrock:InvokeModel` + CloudWatch Logs permissions |

---

## What Gets Discovered

For every hackathon across 3 platforms:

| Field | Source | Notes |
|-------|--------|-------|
| Title | Listing API | Required — invalid entries discarded |
| Platform | Scraper | Devpost / Devfolio / Unstop |
| Registration URL | Listing API | Must be HTTPS |
| Registration Deadline | Detail page | Normalized from 9+ date formats |
| Submission Deadline | Detail page | Handles ranges ("Jan 1 - Mar 15") |
| Prize | Detail page | Truncated to 200 chars |
| Themes | Detail page | Max 20 items |
| Team Size | Detail page | Truncated to 100 chars |
| Organizer | Detail page | Org name or None |
| Mode | Detail page | online / offline / hybrid |
| Location | Detail page | City/venue or None |

Missing fields default to `None` — never fabricated.

---

## What Bedrock Generates

For every hackathon, Amazon Bedrock Nova Micro returns:

| Field | Output | Purpose |
|-------|--------|---------|
| **Priority** | High / Medium / Low | Strategic importance ranking |
| **Difficulty** | Easy / Medium / Hard | Challenge level |
| **Winning Probability** | 0–100% | AI-predicted win chance |
| **Recommended Stack** | 1–10 technologies | Best tools to use |
| **Recommended Team Size** | 1–20 | Optimal team configuration |
| **Execution Strategy** | Up to 2000 chars | Tactical battle plan |
| **Summary** | Up to 500 chars | One-line description |

If Bedrock is unavailable or times out, a deterministic fallback runs based on prize and theme data.

---

## Performance

| Metric | Value |
|--------|-------|
| Platforms scraped | 3 |
| Hackathons discovered | 72 per run |
| Lambda execution time | ~124 seconds |
| Memory used | 116 MB / 512 MB |
| Pages created (first run) | 72 |
| Failed operations | 0 |
| Package size | 16.45 MB |
| Automated tests | 240+ |

---

## Project Structure

```
hackops-ai/
├── lambda_function.py        # Lambda orchestrator (zero business logic)
├── main.py                   # Local dev runner
├── agents/
│   ├── discovery_agent.py    # Devpost + Devfolio + Unstop scrapers
│   ├── intelligence_agent.py # Bedrock AI + mock fallback
│   └── workspace_agent.py    # Notion CRUD + dedup + archiving
├── models/
│   └── hackathon.py          # Typed dataclasses
├── utils/
│   ├── dates.py              # Date normalization (9+ formats)
│   └── validation.py         # Input validation
├── tests/                    # 240+ tests (unit + property + integration)
├── deploy/                   # IAM policies + packaging script
└── demo/                     # Screenshots, GIF, video
```

---

## Deployment

### Prerequisites
- AWS account with Bedrock model access (Nova Micro, ap-south-1)
- Notion integration token + database
- Python 3.13, AWS CLI

### Deploy

```bash
git clone https://github.com/5anjay-s/hackops-ai.git && cd hackops-ai

# IAM role
aws iam create-role --role-name hackops-lambda-role \
  --assume-role-policy-document file://deploy/trust-policy.json
aws iam put-role-policy --role-name hackops-lambda-role \
  --policy-name hackops-bedrock-logs \
  --policy-document file://deploy/bedrock-policy.json

# Package
pip install -t deploy/package -r requirements.txt
cp lambda_function.py deploy/package/
cp -r agents models utils deploy/package/
python deploy/make_zip.py

# Create Lambda
aws lambda create-function --function-name hackops-orchestrator \
  --runtime python3.13 --handler lambda_function.lambda_handler \
  --role arn:aws:iam::<ACCOUNT>:role/hackops-lambda-role \
  --zip-file fileb://deploy/hackops-lambda.zip \
  --timeout 300 --memory-size 512 \
  --environment "Variables={NOTION_TOKEN=<token>,DATABASE_ID=<db_id>}"

# Schedule
aws events put-rule --name hackops-daily-trigger \
  --schedule-expression "rate(1 day)" --state ENABLED
aws events put-targets --rule hackops-daily-trigger \
  --targets "Id=hackops,Arn=arn:aws:lambda:ap-south-1:<ACCOUNT>:function:hackops-orchestrator"
```

### Run Locally

```bash
pip install -r requirements.txt
cp .env.example .env  # add your tokens
python main.py
```

### Run Tests

```bash
pytest tests/ -v
```

---

## Notion Schema

| Column | Type | Description |
|--------|------|-------------|
| S.No | Number | Auto-incremented |
| Hackathon | Title | Name |
| Platform | Select | Source platform |
| Deadline | Date | Registration deadline |
| Submission Deadline | Date | Submission deadline |
| Themes | Multi-select | Tags |
| Prize | Rich Text | Prize pool |
| Team Size | Rich Text | Requirement |
| Priority | Select | AI: High/Medium/Low |
| Difficulty | Select | AI: Easy/Medium/Hard |
| Winning % | Number | AI: 0-100 |
| Suggested Stack | Multi-select | AI: Technologies |
| Execution Strategy | Rich Text | AI: Battle plan |
| Status | Status | In progress / Done |
| Registration Link | URL | Direct link |
| Last Synced | Date | UTC timestamp |

---

## Implementation Highlights

- **3-platform unified scraping** — Devpost JSON API, Devfolio GraphQL, Unstop search API all feeding one pipeline
- **Detail page extraction with retry** — Visits every hackathon page; retries once after 2s; partial data on failure
- **9+ date format normalization** — ISO, month names, numeric, ranges with " - " and " to "
- **Structured AI prompting** — JSON schema enforcement with field validation and truncation
- **Graceful degradation** — No credentials → mock entire batch; single failure → mock that item only
- **Case-sensitive dedup** — Full pagination builds (title, platform) map; strict comparison
- **Exponential backoff** — 1s → 2s → 4s on Notion 429, max 3 retries
- **Contiguous serial numbers** — max(existing) + 1 with fallback
- **Auto-archiving** — Expired deadlines → "Done" status; None deadlines untouched
- **240+ automated tests** — Property-based (Hypothesis) + unit + integration

---

<p align="center">
  <sub>Built with <strong> <3 for agents </strong> on AWS </sub>
</p>
