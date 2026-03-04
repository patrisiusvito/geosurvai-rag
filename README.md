title: GeoSurvAI RAG
emoji: 🌍
colorFrom: blue
colorTo: green
sdk: docker
app_port: 7860
pinned: false


# GeoSurvAI RAG

On-premise RAG system for monitoring seismic survey and geological study activities under SKK Migas. Features automated dashboard scraping, hybrid Text-to-SQL + Semantic querying, and a chat interface powered by Gemini.

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Chat UI (FastAPI)                  │
├─────────────────────────────────────────────────────┤
│                   Query Router                       │
│         ┌──────────┼──────────────┐                  │
│    Quantitative  Precomputed   Semantic              │
│    (Text-to-SQL)  (Cache)     (ChromaDB)             │
├─────────────────────────────────────────────────────┤
│              DuckDB  │  ChromaDB                     │
├─────────────────────────────────────────────────────┤
│            Auto-Sync Scheduler                       │
│   Playwright Scraper → Excel Ingestion → Cache       │
└─────────────────────────────────────────────────────┘
```

## Features

- **Hybrid Query Engine**: Routes questions to Text-to-SQL (quantitative), precomputed cache (executive briefs), or semantic search (contextual)
- **Text-to-SQL**: Gemini 2.5 Flash generates DuckDB SQL from natural language with validation and auto-retry
- **Auto-Sync Pipeline**: Playwright scrapes authenticated dashboards on a cron schedule, downloads Excel data, runs semantic analysis on screenshots, ingests into DuckDB, and refreshes the precomputed cache
- **On-Premise**: All data stays local — DuckDB + ChromaDB, no cloud database dependencies

## Project Structure

```
geosurvai-rag/
├── app/
│   ├── main.py                 # FastAPI app with lifespan
│   ├── api/
│   │   └── chat.py             # Chat endpoint & query routing
│   ├── core/
│   │   ├── query_router.py     # Routes questions to appropriate engine
│   │   ├── sql_engine.py       # Text-to-SQL with Gemini
│   │   └── precomputed.py      # Pre-computed cache for common queries
│   ├── data/
│   │   └── ingestion.py        # Excel → DuckDB ingestion pipeline
│   ├── db/
│   │   └── duckdb_conn.py      # DuckDB connection manager
│   ├── llm/
│   │   ├── client.py           # Ollama/Gemini client setup
│   │   └── prompts.py          # System prompts, schema, few-shot examples
│   └── scraper/
│       ├── browser.py          # Playwright multi-dashboard scraper
│       ├── scheduler.py        # APScheduler auto-sync with ingestion
│       ├── semantic.py         # Screenshot semantic analysis
│       └── config.py           # Scraper target configuration
├── db/                         # DuckDB database (gitignored)
├── data/                       # Downloaded Excel & cache (gitignored)
├── screenshots/                # Dashboard screenshots (gitignored)
├── static/                     # Chat UI frontend
├── config.py                   # App-wide configuration
├── requirements.txt
├── .gitignore
└── README.md
```

## Setup

### Prerequisites
- Python 3.10+
- Google Chrome (for authenticated scraping)
- Playwright browsers: `playwright install chromium`

### Installation

```bash
git clone https://github.com/patrisiusvito/geosurvai-rag.git
cd geosurvai-rag

# Create environment
conda create -n rag-env python=3.11
conda activate rag-env

# Install dependencies
pip install -r requirements.txt
```

### Environment Variables

Create a `.env` file:
```env
GEMINI_API_KEY=your_gemini_api_key
OLLAMA_HOST=http://localhost:11434
```

### Run

```bash
python app/main.py
```

- Chat UI: http://localhost:8000
- API docs: http://localhost:8000/docs
- Trigger sync: `POST /api/sync`

## API Endpoints

| Endpoint | Method | Description |
|---|---|---|
| `/api/chat` | POST | Natural language query |
| `/api/sync` | POST | Trigger dashboard scrape + ingestion |
| `/health` | GET | Health check |
| `/docs` | GET | Swagger API documentation |

## Tech Stack

- **Backend**: FastAPI + Uvicorn
- **Database**: DuckDB (analytical queries)
- **Vector Store**: ChromaDB (semantic search)
- **LLM**: Gemini 2.5 Flash (Text-to-SQL), Ollama (routing/chat)
- **Scraper**: Playwright (authenticated Chrome sessions)
- **Scheduler**: APScheduler (cron-based auto-sync)

## License

Proprietary. All rights reserved.
