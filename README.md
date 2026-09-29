# 🧠 Autonomous Research & Report Generation System

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14.2%2B-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org/)
[![OpenAI Agents SDK](https://img.shields.io/badge/OpenAI_Agents_SDK-0.1.0-412991?style=for-the-badge&logo=openai&logoColor=white)](https://github.com/openai/openai-agents-python)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-red?style=for-the-badge&logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

A **bounded autonomous research agent**: given a natural-language question, it independently plans search queries, acquires and evaluates web evidence, chunks and indexes sources in vector storage, and synthesizes a fully cited, structured report with zero human supervision during execution.

---

## 🖼️ Interface & Workflow Showcase

### 1. Interactive Research Query Input
Simply submit any complex research question in natural language. The system initializes a dedicated research session and state machine.

![Search Bar Interface](assets/screenshots/search-bar.png)

---

### 2. Real-Time Autonomous Pipeline & Live Timeline
Watch the agent autonomously execute state transitions (`planning → searching → reading → writing → done`). Every event, query decomposition, and source acquisition step is streamed to the live visual timeline.

| Autonomous Search Planning & Execution | Detailed Live Stage Events |
| :---: | :---: |
| ![From Planning to Complete Research](assets/screenshots/planning-execution-1.png) | ![Live Timeline & State Logs](assets/screenshots/planning-execution-2.png) |

---

### 3. Synthesized Deep Research Report & Interactive Cited Sources
The synthesized report features structured markdown sections, inline interactive citation tags `[1]`, `[2]`, and a dedicated sidebar detailing verified web sources, snippets, and domains.

| Complete Report & Cited Sources | Source Cards & Domain Analytics | Citation Verification Breakdown |
| :---: | :---: | :---: |
| ![Research Report & Cited Sources](assets/screenshots/research-report-1.png) | ![Cited Sources & Web References](assets/screenshots/research-report-2.png) | ![Citation Details](assets/screenshots/research-report-3.png) |

---

## 🏗️ Theoretical Pipeline & Architecture

```
Question        → [Planner]  → Search Strategy          (OpenAI Agents SDK)
        → [Executor] → Evidence Acquisition      (Tavily / Exa / DuckDuckGo)
        → [Curator]  → Dedupe → Rank → Chunk    (Curate Service)
        → [Indexer]  → Embed → Qdrant           (Semantic Memory, report-scoped)
        → [Retriever]→ Top-k Evidence Selection (Vector Search filtered by report_id)
        → [Writer]   → Grounded, Cited Report   (OpenAI Agents SDK)
        → [Validator]→ citations(R) ⊆ sources(R)  ← Integrity Invariant
        → [Persist]  → Postgres                 (State, Provenance, Results)
```

### State Machine Flowchart

```mermaid
graph TD
    A[User Query] --> B[Planning Stage]
    B -->|Generate Query Plan| C[Searching Stage]
    C -->|Parallel Web Acquisition| D[Reading Stage]
    D -->|Dedupe, Rank & Chunk| E[Semantic Vector Indexing]
    E -->|Evidence Sufficient?| F{Check Budget & Quality}
    F -->|Thin Evidence & Rounds Left| B
    F -->|Sufficient Chunks| G[Writing Stage]
    G -->|Synthesize Report| H[Citation Verification Gate]
    H -->|Valid Citations| I[Done - Complete Report]
    H -->|Invalid Citations Dropped| I
    C -->|Error / Timeout| J[Failed Stage]
    G -->|LLM Timeout / Error| J
```

Each pipeline stage is a distinct function with a strict contract. The orchestrator acts as a deterministic state machine wrapping non-deterministic intelligence.

---

## ⚖️ Governing Principles

| Principle | How It's Enforced |
|---|---|
| **Autonomy with Bounds** | Hard caps on `MAX_QUERIES`, `MAX_SOURCES`, `MAX_ROUNDS`, and `MAX_TOTAL_SECONDS` prevent runaway API usage or execution deadlocks. |
| **Strict Grounding** | The Writer agent only receives retrieved vector chunks; system prompts prohibit outside knowledge extrapolation. |
| **Citation Integrity** | Mathematical invariant check `citations(R) ⊆ sources(R)` runs before any report is accepted. |
| **Semantic Separability** | Evidence is chunked into ~800-token passages, indexed individually with vector embeddings. |
| **Deterministic Orchestration** | Fixed state transitions, explicit retries, per-call LLM timeouts, and strongly typed Pydantic contracts. |
| **Observable State** | `report_events` table + `/api/reports/{id}/events` SSE/REST timeline; stages are fully audit-logged and resumable. |
| **Report-Scoped Memory** | Vector searches filter strictly on `report_id`, ensuring evidence never leaks across research runs. |

---

## 🛠️ Technology Stack

- **OpenAI Agents SDK**: Structured planning and report synthesis over OpenAI-compatible endpoints (NVIDIA NIM by default).
- **Web Search**: Pluggable acquisition providers: **Tavily**, **Exa**, or keyless **DuckDuckGo** (`SEARCH_PROVIDER`).
- **Qdrant Vector DB**: High-performance semantic vector database for report-scoped evidence retrieval.
- **PostgreSQL**: Relational database for reports, sources, chunks, and state event timelines.
- **FastAPI**: Async Python backend handling orchestration state machines and status endpoints.
- **Next.js 14**: React framework providing the interactive search form, live execution timeline, and markdown report reader.

---

## 📁 Repository Structure

```
research-agent/
├── docker-compose.yml             # Postgres :5434 + Qdrant :6333
├── LICENSE                        # MIT License
├── CONTRIBUTING.md                # Development & contribution guidelines
├── .env.example                   # Environment configuration template
├── README.md                      # Comprehensive project documentation
├── Agent testing images/          # Original test screenshots
├── assets/
│   └── screenshots/               # Clean screenshot gallery for README
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI entry point & lifespan
│   │   ├── config.py              # Application settings & bounded caps
│   │   ├── db.py                  # Database engine & session initialization
│   │   ├── models.py              # SQLAlchemy models (Report, Source, Chunk, ReportEvent)
│   │   ├── schemas.py             # Pydantic API request/response schemas
│   │   ├── orchestrator.py        # Bounded state machine engine
│   │   ├── routes.py              # REST API routes for report management
│   │   ├── agents/
│   │   │   ├── prompts.py         # System prompts for Planner and Writer agents
│   │   │   └── research_agents.py # Agents SDK integrations & structured outputs
│   │   └── services/
│   │       ├── search.py          # Tavily / Exa / DuckDuckGo web search service
│   │       ├── curate.py          # Deduplication, ranking, and chunking logic
│   │       ├── embeddings.py      # Vector embedding generator
│   │       └── vector.py          # Qdrant vector indexing and retrieval
│   ├── tests/                     # Pytest suite (citations, fallbacks, curation)
│   ├── pyproject.toml             # Backend dependencies and build config
│   └── Dockerfile                 # Container setup for FastAPI backend
└── frontend/
    ├── app/                       # Next.js App Router pages
    │   ├── page.tsx               # Interactive question search interface
    │   ├── reports/[id]/page.tsx   # Live timeline & cited report view
    │   └── globals.css            # Global CSS styling & design tokens
    ├── lib/
    │   └── api.ts                 # Axios / Fetch client for backend API
    ├── package.json               # Frontend dependencies
    └── tsconfig.json              # TypeScript configuration
```

---

## 🚀 Quick Start Guide

### Prerequisites
- [Docker](https://www.docker.com/) & Docker Compose
- [Python 3.11+](https://www.python.org/)
- [Node.js 18+](https://nodejs.org/)

---

### Step 1: Infrastructure Setup

Clone the repository and launch PostgreSQL and Qdrant via Docker Compose:

```bash
git clone https://github.com/your-username/research-agent.git
cd research-agent

# Launch Postgres (:5434) and Qdrant (:6333)
docker compose up -d
```

Copy `.env.example` to `.env` and set your API credentials:

```bash
cp .env.example .env
```

---

### Step 2: Environment Configuration (`.env`)

```env
# Credentials
OPENAI_API_KEY=your_openai_or_nvidia_nim_api_key
TAVILY_API_KEY=your_tavily_api_key   # Optional if using DuckDuckGo
EXA_API_KEY=your_exa_api_key       # Optional

# Search Provider: "tavily" | "exa" | "ddg"
SEARCH_PROVIDER=tavily

# LLM & Embeddings Endpoints (Defaults to NVIDIA NIM)
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
EMBEDDINGS_BASE_URL=https://integrate.api.nvidia.com/v1

# Models
PLANNER_MODEL=meta/llama-3.3-70b-instruct
WRITER_MODEL=meta/llama-3.3-70b-instruct
EMBEDDING_MODEL=nvidia/nv-embedqa-e5-v5

# Database URLs
DATABASE_URL=postgresql+psycopg://research:research@localhost:5434/research
QDRANT_URL=http://localhost:6333
```

---

### Step 3: Start Backend (FastAPI)

```bash
cd backend

# Create and activate Python virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# Install backend dependencies
pip install -e .

# Launch FastAPI application server
uvicorn app.main:app --reload --port 8000
```

The backend server will start at `http://localhost:8000`. You can inspect the Swagger API docs at `http://localhost:8000/docs`.

---

### Step 4: Start Frontend (Next.js)

In a new terminal window:

```bash
cd frontend

# Install Node dependencies
npm install

# Start Next.js development server
npm run dev
```

Open `http://localhost:3000` in your web browser to submit questions and view real-time research runs!

---

## ⚡ Bounded Autonomy Configuration

Every research budget limit can be configured via `.env` or application settings:

| Parameter | Default | Description |
|---|---|---|
| `MAX_QUERIES` | `5` | Maximum number of web search queries generated per run |
| `MAX_SOURCES` | `10` | Maximum number of unique web sources ingested and ranked |
| `MAX_ROUNDS` | `2` | Maximum planning → search iterations if initial evidence is sparse |
| `MAX_TOTAL_SECONDS` | `240.0` | Maximum wall-clock budget for an entire research run (4 minutes) |
| `TOP_K` | `12` | Number of top vector evidence chunks retrieved for synthesis |
| `PLANNER_TIMEOUT` | `45.0` | Hard per-call LLM timeout for search plan generation |
| `WRITER_TIMEOUT` | `120.0` | Hard per-call LLM timeout for final report synthesis |

---

## 📡 REST API Reference

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/reports` | Initialize a new research run (`{"query": "..."}`) |
| `GET` | `/api/reports/{id}` | Get full report details, state, sources, and markdown report |
| `GET` | `/api/reports/{id}/events` | Stream/Fetch real-time stage event timeline |
| `POST` | `/api/reports/{id}/retry` | Re-run a failed or completed report through the pipeline |
| `GET` | `/api/reports` | List recent research reports |
| `GET` | `/healthz` | System health check (Postgres + Qdrant reachability) |

---

## 🧪 Running Tests

Execute the backend test suite with pytest:

```bash
cd backend
pytest
```

Tests cover:
- Citation integrity gate & invariant checking (`test_citations.py`)
- Evidence curation, deduplication, and chunking (`test_curate.py`)
- LLM agent timeout fallbacks (`test_agent_fallbacks.py`)

---

## 📤 Pushing to GitHub

Follow these simple steps to push this repository to your GitHub account:

```bash
# 1. Initialize git (already completed)
git status

# 2. Add remote repository URL (replace with your GitHub repository URL)
git remote add origin https://github.com/YOUR_USERNAME/YOUR_REPOSITORY_NAME.git

# 3. Stage all files
git add .

# 4. Commit changes
git commit -m "feat: initial commit of Autonomous Research Agent system with docs and UI showcase"

# 5. Push to GitHub main branch
git push -u origin main
```

---

## 📜 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.
