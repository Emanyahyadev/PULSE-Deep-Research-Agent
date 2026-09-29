# Autonomous Research & Report Generation System

[![Python](https://img.shields.io/badge/Python-3.11%2B-blue?style=for-the-badge&logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115%2B-009688?style=for-the-badge&logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![Next.js](https://img.shields.io/badge/Next.js-14.2%2B-000000?style=for-the-badge&logo=next.js&logoColor=white)](https://nextjs.org/)
[![OpenAI Agents SDK](https://img.shields.io/badge/OpenAI_Agents_SDK-0.1.0-412991?style=for-the-badge&logo=openai&logoColor=white)](https://github.com/openai/openai-agents-python)
[![Qdrant](https://img.shields.io/badge/Qdrant-Vector_DB-red?style=for-the-badge&logo=qdrant&logoColor=white)](https://qdrant.tech/)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-4169E1?style=for-the-badge&logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg?style=for-the-badge)](LICENSE)

A bounded autonomous research system that accepts natural-language inquiries, formulates search strategies, gathers and evaluates web evidence, indexes passage embeddings into vector storage, and synthesizes structured, fully cited reports without human intervention during execution.

---

## Architecture & State Machine Flowchart

The system wraps non-deterministic LLM agents inside a deterministic state machine orchestrator to enforce execution bounds, fallback mechanisms, and citation integrity invariants.

### Enterprise State Machine Diagram

```mermaid
flowchart TD
    classDef primary fill:#1e293b,stroke:#3b82f6,stroke-width:2px,color:#f8fafc;
    classDef success fill:#064e3b,stroke:#10b981,stroke-width:2px,color:#ecfdf5;
    classDef warning fill:#78350f,stroke:#f59e0b,stroke-width:2px,color:#fffbeb;
    classDef danger fill:#7f1d1d,stroke:#ef4444,stroke-width:2px,color:#fef2f2;
    classDef db fill:#312e81,stroke:#6366f1,stroke-width:2px,color:#eef2ff;

    subgraph ClientLayer ["Client & Interface Layer"]
        UserQuery["User Input: Research Query"]:::primary
    end

    subgraph OrchestratorEngine ["Deterministic State Machine Engine"]
        Planning["Stage 1: Planning<br/>(Query Decomposition)"]:::primary
        Searching["Stage 2: Searching<br/>(Parallel Web Acquisition)"]:::primary
        Reading["Stage 3: Reading & Curation<br/>(Dedupe, Rank, Chunk)"]:::primary
        VectorIndex["Semantic Vector Indexing<br/>(Passage Embeddings)"]:::primary
        EvalCheck{"Budget & Evidence<br/>Evaluation"}:::warning
        Writing["Stage 4: Writing<br/>(Grounded Report Synthesis)"]:::primary
        CitationGate{"Citation Verification Gate<br/>citations(R) ⊆ sources(R)"}:::warning
        DoneState["Stage 5: Completed Report"]:::success
        FailState["Stage 6: Execution Failed"]:::danger
    end

    subgraph MemoryStorage ["Persistence & Vector Memory"]
        QdrantStore[("Qdrant Vector DB<br/>(Report-Scoped Memory)")]:::db
        PostgresStore[("PostgreSQL DB<br/>(State Events & Provenance)")]:::db
    end

    UserQuery --> Planning
    Planning -->|Generate Plan| Searching
    Searching -->|Acquired Sources| Reading
    Reading -->|Chunk Passages| VectorIndex
    VectorIndex --> QdrantStore
    VectorIndex --> EvalCheck
    EvalCheck -->|Thin Evidence & Round Cap Remaining| Planning
    EvalCheck -->|Sufficient Evidence| Writing
    Writing --> CitationGate
    CitationGate -->|Verified Citations| DoneState
    DoneState --> PostgresStore
    Searching -->|Acquisition Timeout / Error| FailState
    Writing -->|LLM Synthesis Timeout| FailState
    FailState --> PostgresStore
```

### Theoretical Pipeline Architecture

```
User Query      → [Planner]  → Query Decomposition Strategy     (OpenAI Agents SDK)
                → [Executor] → Web Evidence Acquisition         (Tavily / Exa / DuckDuckGo)
                → [Curator]  → Deduplication → Rank → Chunk     (Curate Service)
                → [Indexer]  → Vector Embeddings → Qdrant       (Semantic Memory)
                → [Retriever]→ Top-k Evidence Selection        (Report-Scoped Filter)
                → [Writer]   → Report Synthesis                 (OpenAI Agents SDK)
                → [Validator]→ Verification: citations ⊆ sources (Integrity Invariant)
                → [Persist]  → PostgreSQL DB Persistence        (State & Timeline)
```

---

## Interface & Workflow Overview

### 1. Interactive Research Query Input
Submit complex research questions in natural language. The interface initializes a dedicated research session and state machine orchestrator.

![Search Bar Interface](./assets/screenshots/search-bar.png)

---

### 2. Autonomous Pipeline & Live Execution Timeline
View real-time state transitions (`planning → searching → reading → writing → done`). Event logs, query decompositions, and source acquisition steps stream directly to the timeline.

#### Search Query Planning & Execution
![Search Planning and Execution](./assets/screenshots/planning-execution-1.png)

#### Real-Time Event Log Timeline
![Live Timeline and Logs](./assets/screenshots/planning-execution-2.png)

---

### 3. Synthesized Research Report & Citation Verification
The generated report contains structured Markdown sections, inline interactive citation chips `[1]`, `[2]`, and a sidebar displaying verified sources, snippets, and domain metadata.

#### Synthesized Report View
![Research Report View](./assets/screenshots/research-report-1.png)

#### Cited Source Cards
![Cited Source Cards](./assets/screenshots/research-report-2.png)

#### Citation Verification Details
![Citation Verification Breakdown](./assets/screenshots/research-report-3.png)

---

## Governing Design Principles

| Principle | Enforcement Mechanism |
|---|---|
| **Autonomy with Bounds** | Strict limits on `MAX_QUERIES`, `MAX_SOURCES`, `MAX_ROUNDS`, and `MAX_TOTAL_SECONDS` prevent runaway API expenditure or infinite execution loops. |
| **Strict Grounding** | The Writer agent is constrained to retrieved evidence passages; system prompts strictly prohibit outside knowledge extrapolation. |
| **Citation Integrity** | Formal verification step `citations(R) ⊆ sources(R)` runs prior to final report acceptance. |
| **Semantic Separability** | Sources are segmented into ~800-token passages, indexed independently with vector embeddings. |
| **Deterministic Orchestration** | Typed state transitions, explicit retries, per-call LLM timeouts, and validated Pydantic schemas. |
| **Observable State** | `report_events` table + `/api/reports/{id}/events` SSE/REST timeline for auditing and monitoring. |
| **Report-Scoped Memory** | Qdrant vector queries filter strictly on `report_id`, ensuring isolation across research sessions. |

---

## Technology Stack

- **OpenAI Agents SDK**: Structured planning and report synthesis over OpenAI-compatible endpoints (NVIDIA NIM by default).
- **Web Acquisition**: Pluggable provider architecture supporting Tavily, Exa, and DuckDuckGo (`SEARCH_PROVIDER`).
- **Qdrant Vector DB**: High-performance vector database for report-scoped semantic passage search.
- **PostgreSQL**: Relational storage for reports, sources, passage chunks, and state event timelines.
- **FastAPI**: Async Python framework managing state machine orchestration and REST APIs.
- **Next.js 14**: React framework providing the search interface, live timeline, and markdown viewer.

---

## Repository Structure

```
pulse-research-agent/
├── docker-compose.yml             # Postgres :5434 + Qdrant :6333
├── LICENSE                        # MIT License
├── CONTRIBUTING.md                # Development & contribution guidelines
├── .env.example                   # Environment configuration template
├── README.md                      # Primary project documentation
├── Agent testing images/          # Test screenshots directory
├── assets/
│   └── screenshots/               # Web-optimized documentation assets
├── backend/
│   ├── app/
│   │   ├── main.py                # FastAPI entry point & lifecycle
│   │   ├── config.py              # Configuration & execution bounds
│   │   ├── db.py                  # Database engine & session setup
│   │   ├── models.py              # SQLAlchemy database models
│   │   ├── schemas.py             # Pydantic API schemas
│   │   ├── orchestrator.py        # Bounded state machine engine
│   │   ├── routes.py              # REST API endpoints
│   │   ├── agents/
│   │   │   ├── prompts.py         # System prompts for Planner and Writer
│   │   │   └── research_agents.py # Agents SDK integrations
│   │   └── services/
│   │       ├── search.py          # Web search acquisition provider
│   │       ├── curate.py          # Deduplication, ranking, and chunking
│   │       ├── embeddings.py      # Vector embedding generator
│   │       └── vector.py          # Qdrant indexing & retrieval
│   ├── tests/                     # Pytest suite
│   ├── pyproject.toml             # Backend project configuration
│   └── Dockerfile                 # Backend container definition
└── frontend/
    ├── app/                       # Next.js App Router
    │   ├── page.tsx               # Query entry interface
    │   ├── reports/[id]/page.tsx   # Live timeline & report viewer
    │   └── globals.css            # Stylesheet & design tokens
    ├── lib/
    │   └── api.ts                 # API client wrapper
    ├── package.json               # Frontend dependencies
    └── tsconfig.json              # TypeScript configuration
```

---

## Quick Start Guide

### System Prerequisites
- Docker & Docker Compose
- Python 3.11+
- Node.js 18+

---

### Step 1: Infrastructure Initialization

Clone the repository and launch PostgreSQL and Qdrant services:

```bash
git clone https://github.com/Emanyahyadev/pulse-research-agent.git
cd pulse-research-agent

docker compose up -d
```

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

---

### Step 2: Environment Configuration (`.env`)

```env
# Credentials
OPENAI_API_KEY=your_openai_or_nvidia_nim_api_key
TAVILY_API_KEY=your_tavily_api_key

# Search Provider: "tavily" | "exa" | "ddg"
SEARCH_PROVIDER=tavily

# LLM & Embeddings Endpoints
LLM_BASE_URL=https://integrate.api.nvidia.com/v1
EMBEDDINGS_BASE_URL=https://integrate.api.nvidia.com/v1

# Model Selection
PLANNER_MODEL=meta/llama-3.3-70b-instruct
WRITER_MODEL=meta/llama-3.3-70b-instruct
EMBEDDING_MODEL=nvidia/nv-embedqa-e5-v5

# Storage Endpoints
DATABASE_URL=postgresql+psycopg://research:research@localhost:5434/research
QDRANT_URL=http://localhost:6333
```

---

### Step 3: Backend Setup (FastAPI)

```bash
cd backend

# Initialize and activate Python virtual environment
python -m venv .venv

# Windows:
.venv\Scripts\activate
# Linux/macOS:
# source .venv/bin/activate

# Install backend package in editable mode
pip install -e .

# Start development server
uvicorn app.main:app --reload --port 8000
```

Backend API server runs at `http://localhost:8000`. Interactive OpenAPI documentation is available at `http://localhost:8000/docs`.

---

### Step 4: Frontend Setup (Next.js)

```bash
cd frontend

npm install
npm run dev
```

Access the frontend application at `http://localhost:3000`.

---

## Execution Caps & Bounded Configuration

Execution parameters are configured via environment variables:

| Parameter | Default | Description |
|---|---|---|
| `MAX_QUERIES` | `5` | Maximum search queries generated per research run |
| `MAX_SOURCES` | `10` | Maximum web sources ingested and ranked |
| `MAX_ROUNDS` | `2` | Maximum planning and search iterations |
| `MAX_TOTAL_SECONDS` | `240.0` | Hard wall-clock execution budget (seconds) |
| `TOP_K` | `12` | Number of vector passage chunks retrieved for report synthesis |
| `PLANNER_TIMEOUT` | `45.0` | Timeout cap for search planning LLM calls |
| `WRITER_TIMEOUT` | `120.0` | Timeout cap for report synthesis LLM calls |

---

## REST API Specification

| Method | Endpoint | Description |
|---|---|---|
| `POST` | `/api/reports` | Submit research query and initialize state machine |
| `GET` | `/api/reports/{id}` | Retrieve report status, sources, citations, and content |
| `GET` | `/api/reports/{id}/events` | Fetch or stream event timeline |
| `POST` | `/api/reports/{id}/retry` | Re-trigger pipeline execution for a report |
| `GET` | `/api/reports` | List recent research reports |
| `GET` | `/healthz` | System health and vector store connection check |

---

## Verification & Testing

Execute the backend test suite:

```bash
cd backend
pytest
```

Test coverage includes:
- Citation invariant verification (`test_citations.py`)
- Evidence curation, deduplication, and passage chunking (`test_curate.py`)
- Agent timeout fallback mechanisms (`test_agent_fallbacks.py`)

---

## License

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.
