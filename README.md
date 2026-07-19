# 🧠 Multisource Candidate Transformer

> An end-to-end **AI-powered talent intelligence platform** that ingests candidate data from multiple sources, deduplicates profiles, enriches them with a Gemini LLM via a RAG pipeline, and serves everything through a FastAPI backend + modern **Next.js** dashboard — all backed by **MongoDB**.

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10%2B-blue?style=for-the-badge&logo=python" />
  <img src="https://img.shields.io/badge/FastAPI-0.111-green?style=for-the-badge&logo=fastapi" />
  <img src="https://img.shields.io/badge/Next.js-16-black?style=for-the-badge&logo=nextdotjs" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?style=for-the-badge&logo=react" />
  <img src="https://img.shields.io/badge/LangChain-0.3-orange?style=for-the-badge" />
  <img src="https://img.shields.io/badge/Gemini-3.5_Flash-purple?style=for-the-badge&logo=google" />
  <img src="https://img.shields.io/badge/MongoDB-Atlas-brightgreen?style=for-the-badge&logo=mongodb" />
  <img src="https://img.shields.io/badge/Tests-56_Passed-success?style=for-the-badge&logo=pytest" />
</p>

---

## 📌 Table of Contents

- [What It Does](#-what-it-does)
- [Architecture](#-architecture)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Quickstart](#-quickstart)
- [Configuration](#-configuration)
- [Usage Workflow](#-usage-workflow)
- [API Reference](#-api-reference)
- [Testing](#-testing)
- [Contributing / Forking](#-contributing--forking)

---

## ✨ What It Does

This platform solves a core problem in recruiting automation: **the same candidate appears in multiple data sources** (a spreadsheet, a resume, a GitHub profile) and needs to be intelligently unified.

| Feature | Description |
|---|---|
| 🔀 **Multi-Source Deduplication** | Upload a CSV and a PDF resume for the same person. The platform matches on email/phone and **merges** them into a single enriched profile — no duplicates. |
| 🤖 **Gemini LLM Extraction** | Structured data extraction from raw resume text using `gemini-3.5-flash` and `with_structured_output(Pydantic)` for schema-guaranteed JSON output. |
| 🔍 **RAG Semantic Search** | Natural language queries over candidates (e.g. *"Python developer with Kubernetes experience"*). Uses `all-MiniLM-L6-v2` embeddings + cosine similarity stored in MongoDB. |
| 📊 **Provenance & Confidence** | Every field tracks its **source** (CSV / Resume / LLM), **extraction method**, and a **trust score** so recruiters can see why a data point was chosen. |
| 🗄️ **100% MongoDB Backed** | Structured candidate profiles AND unstructured resume chunks/embeddings all live in MongoDB — no secondary vector database needed. |
| 🖥️ **Next.js 16 Frontend** | Modern React 19 dashboard with glassmorphism dark theme, sidebar navigation, slide-out candidate detail drawers, drag-and-drop uploads, and semantic search. |
| 🧪 **56-Test Suite** | Full `pytest` suite covering API endpoints, merger logic, and normalizers — all running offline with mocked dependencies. |

---

## 🏗️ Architecture

```
CSV / PDF / DOCX / TXT
        │
        ▼
┌─────────────────────┐
│  LangChain Loaders  │  PyPDFLoader, TextLoader, CSVLoader
└─────────┬───────────┘
          │
          ▼
┌─────────────────────┐
│   Text Splitting    │  RecursiveCharacterTextSplitter → chunks
└─────────┬───────────┘
          │
          ▼
┌────────────────────────────┐
│  MongoDB Vector Store      │  Stores chunks + MiniLM embeddings
│  (lc/mongo_vectorstore.py) │  Cosine similarity search at query time
└─────────┬──────────────────┘
          │
          ▼
┌────────────────────────────┐
│   Candidate Merger         │  Email/phone identity resolution
│   (pipeline/merger/)       │  Dedup + confidence-scored field merging
└─────────┬──────────────────┘
          │
          ▼
┌────────────────────────────┐
│  Gemini LLM Extraction     │  RAG context → structured Pydantic schema
│  (lc/extractor.py)         │  Skills, experience, education, summary
└─────────┬──────────────────┘
          │
          ▼
┌────────────────────────────────────────────────────────────┐
│  FastAPI Backend (port 8001)  ←→  Next.js Frontend (3000)  │
│  api/main.py                      frontend/ (React 19)     │
│  REST API + Swagger docs          Glassmorphism dashboard   │
└────────────────────────────────────────────────────────────┘
```

The **Next.js dev server** (port 3000) proxies all `/candidates/*` and `/health` requests to the **FastAPI backend** (port 8001) via `next.config.mjs` rewrites — no CORS issues, single browser origin.

---

## 🛠️ Tech Stack

| Layer | Technology |
|---|---|
| **LLM** | Google Gemini 3.5 Flash (`langchain-google-genai`) |
| **Embeddings** | `all-MiniLM-L6-v2` via `sentence-transformers` (local, free) |
| **Vector Store** | MongoDB with manual cosine similarity (no Pinecone/Chroma needed) |
| **AI Framework** | LangChain 0.3 (LCEL chains, `with_structured_output`, custom retrievers) |
| **Database** | MongoDB Atlas (PyMongo + certifi for TLS) |
| **Backend** | FastAPI + Uvicorn |
| **Frontend** | Next.js 16 + React 19 (App Router, Inter & JetBrains Mono fonts) |
| **Data Validation** | Pydantic v2 |
| **Testing** | pytest + httpx (56 tests, 100% pass rate) |

---

## 📂 Project Structure

```
multisource_candidate_platform/
│
├── api/                            # FastAPI backend
│   ├── main.py                     # All REST endpoints + dedup logic
│   ├── mongo_storage.py            # PyMongo CRUD layer (MongoStorage class)
│   └── storage.py                  # Legacy JSON file store (unused, kept for reference)
│
├── frontend/                       # Next.js 16 + React 19 frontend
│   ├── app/
│   │   ├── layout.js               # Root layout — providers, sidebar, drawer
│   │   ├── globals.css             # Full design system (glassmorphism dark theme)
│   │   ├── page.js                 # Dashboard — candidate cards grid
│   │   ├── upload/page.js          # Upload — CSV + Resume drag-and-drop
│   │   └── search/page.js          # Semantic search — natural language queries
│   ├── components/
│   │   ├── AppShell.js             # Layout shell (sidebar + topbar + content)
│   │   ├── Sidebar.js              # Navigation sidebar with live stats
│   │   ├── Topbar.js               # Top header bar
│   │   └── CandidateDrawer.js      # Slide-out drawer (profile/confidence/provenance)
│   ├── contexts/
│   │   ├── CandidateContext.js     # Global candidate state + API fetching
│   │   ├── DrawerContext.js        # Drawer open/close state management
│   │   └── ToastContext.js         # Toast notification system
│   ├── next.config.mjs             # API proxy rewrites → localhost:8001
│   └── package.json                # Next.js 16, React 19
│
├── lc/                             # LangChain AI layer
│   ├── llm.py                      # ChatGoogleGenerativeAI factory (@lru_cache)
│   ├── embeddings.py               # SentenceTransformer / Gemini embedding switcher
│   ├── loaders.py                  # PDF, DOCX, TXT document loaders
│   ├── splitter.py                 # RecursiveCharacterTextSplitter config
│   ├── mongo_vectorstore.py        # Chunk indexing + cosine search in MongoDB
│   ├── extractor.py                # Pydantic schema + Gemini structured extraction
│   ├── retriever.py                # RAG context builder for enrichment
│   └── conflict_resolver.py        # LLM-based field conflict resolution
│
├── pipeline/
│   ├── merger/
│   │   └── merge.py                # CandidateMerger — core dedup + merge engine
│   ├── confidence/
│   │   ├── scorer.py               # Per-field, per-source confidence scoring
│   │   └── explainer.py            # Human-readable confidence breakdown
│   ├── normalizers/
│   │   ├── phone.py                # E.164 phone normalization (phonenumbers lib)
│   │   ├── skills.py               # Skill canonicalization (rapidfuzz fuzzy match)
│   │   └── dates.py                # ISO date range normalization
│   └── parsers/
│       └── recruiter_csv.py        # Flexible CSV parser (handles varied column names)
│
├── models/
│   └── candidate.py                # Pydantic models: Candidate, Skill, Experience, etc.
│
├── tests/
│   ├── conftest.py                 # Fixtures: InMemoryStore, mocked FastAPI TestClient
│   ├── test_api.py                 # 23 API integration tests
│   ├── test_merger.py              # 18 unit tests for CandidateMerger
│   └── test_normalizers.py         # 15 unit tests for phone/skill/date normalizers
│
├── ui/                             # Legacy vanilla JS dashboard (served at /ui/)
│   ├── index.html                  # Single-page app shell
│   ├── app.js                      # Vanilla JS — dashboard, upload, search
│   └── style.css                   # Glassmorphism dark theme CSS
│
├── input/                          # (gitignored) Place test CSVs/resumes here
├── output/                         # (gitignored) Runtime artifacts
│
├── run_server.py                   # Entry point — loads .env + starts Uvicorn on port 8001
├── requirements.txt                # Python dependencies
├── .env.example                    # ← Copy this to .env and fill in your keys
└── .gitignore
```

---

## 🚀 Quickstart

### Prerequisites

- **Python 3.10+**
- **Node.js 18+** (for the Next.js frontend)
- A **MongoDB Atlas** account (free tier works perfectly) → [cloud.mongodb.com](https://cloud.mongodb.com)
- A **Google AI Studio** API key (free) → [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)

---

### Step 1 — Clone the repository

```bash
git clone https://github.com/nikghost17/multisource-candidate-transformer.git
cd multisource-candidate-transformer
```

### Step 2 — Create a virtual environment

```bash
# Create the venv
python -m venv venv

# Activate it
# Windows:
venv\Scripts\activate

# macOS / Linux:
source venv/bin/activate
```

### Step 3 — Install Python dependencies

```bash
pip install -r requirements.txt
```

> ⚠️ **First run note:** `sentence-transformers` will automatically download the `all-MiniLM-L6-v2` model (~80MB) on first use. This is a one-time download.

### Step 4 — Install frontend dependencies

```bash
cd frontend
npm install
cd ..
```

### Step 5 — Configure environment variables

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Now open `.env` and fill in your keys:

```env
GEMINI_API_KEY=your_gemini_api_key_here
GEMINI_MODEL=gemini-3.5-flash
MONGODB_URI=mongodb+srv://<user>:<password>@cluster.mongodb.net/
MONGODB_DB=candidate_platform
EMBEDDING_PROVIDER=sentence_transformers
ST_MODEL=all-MiniLM-L6-v2
```

**Getting your MongoDB URI:**
1. Go to [cloud.mongodb.com](https://cloud.mongodb.com) → Create a free cluster
2. Click **Connect** → **Drivers** → copy the connection string
3. Replace `<password>` with your database user's password
4. If your password contains `@`, encode it as `%40`

**Getting your Gemini API key:**
1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Click **Create API Key**
3. Copy the key into `.env`

### Step 6 — Start the backend

```bash
python run_server.py
```

You should see:

```
[Startup] Loaded .env

==========================================================
  Multisource Candidate Matching Platform  v1.0
==========================================================
  API Docs : http://localhost:8001/api/docs
  Web UI   : http://localhost:8001/ui/
  Health   : http://localhost:8001/health
==========================================================
```

### Step 7 — Start the frontend (separate terminal)

```bash
cd frontend
npm run dev
```

Next.js starts on port 3000 and proxies API calls to the backend on port 8001.

### Step 8 — Open the app

| URL | Purpose |
|---|---|
| 👉 **http://localhost:3000** | **Next.js Dashboard** (primary UI) |
| 📖 **http://localhost:8001/api/docs** | Swagger API Docs |
| 🎨 **http://localhost:8001/ui/** | Legacy vanilla JS dashboard |
| ✅ **http://localhost:8001/health** | Health check |

---

## ⚙️ Configuration

All configuration lives in `.env`. Copy `.env.example` to get started.

| Variable | Required | Description |
|---|---|---|
| `GEMINI_API_KEY` | ✅ Yes | Google AI Studio API key |
| `GEMINI_MODEL` | ✅ Yes | Model name (e.g. `gemini-3.5-flash`) |
| `MONGODB_URI` | ✅ Yes | Full MongoDB connection string |
| `MONGODB_DB` | No | Database name (default: `candidate_platform`) |
| `EMBEDDING_PROVIDER` | No | `sentence_transformers` (default) or `gemini` |
| `ST_MODEL` | No | HuggingFace model name (default: `all-MiniLM-L6-v2`) |

> **Which Gemini model?** Check your account's rate limits at [ai.dev/rate-limit](https://ai.dev/rate-limit). `gemini-3.5-flash` has the widest free-tier availability.

---

## 💡 Usage Workflow

### 1. Upload a Recruiter CSV

Go to the **Upload** page (`/upload`) → drag and drop a `.csv` file into the CSV zone.

The CSV can have varied column names. The parser handles all common formats:

```csv
name,email,phone,skills,title,location
Alice Johnson,alice@example.com,+14155550101,"Python,AWS,Docker",ML Engineer,San Francisco
Bob Smith,bob@example.com,+14155550202,"Java,Kubernetes",DevOps Lead,New York
```

Optionally enable **LLM conflict resolution** via the checkbox to use Gemini for resolving field conflicts between data sources.

### 2. Upload a Resume

Drop a **PDF**, **DOCX**, or **TXT** resume into the Resume zone on the same Upload page.

The platform:
- Extracts raw text via LangChain document loaders
- Matches to an existing candidate by **email or phone** (cross-upload deduplication)
- Merges the resume text and heuristic fields into the existing profile
- Chunks + indexes the resume text into MongoDB as vector embeddings

You'll see in the terminal:
```
[Dedup] Merged into existing a3f7b2d1… (Alice Johnson)
[Mongo VectorStore] Indexed 6 chunks for a3f7b2d1…
```

### 3. View Candidate Profiles

Click any **candidate card** on the Dashboard (`/`) to open the slide-out detail drawer with three tabs:

| Tab | Shows |
|---|---|
| **Profile** | AI summary, contact info, skills, experience, education, links |
| **Confidence** | Per-field confidence bars with source attribution |
| **Provenance** | Full audit trail — which source provided which field and how |

### 4. Enrich with Gemini (RAG)

Click the **✨ Enrich with Gemini** button in the candidate drawer footer.

The platform:
1. Retrieves relevant chunks from MongoDB (RAG context)
2. Sends resume text + RAG context to Gemini
3. Gemini returns a fully structured Pydantic JSON (skills, experience, education, etc.)
4. The enriched data is merged back into the existing MongoDB candidate document

### 5. Semantic Search

Go to the **Semantic Search** page (`/search`) and type a natural language query:

```
Python developer with machine learning and AWS experience
Senior DevOps engineer with Kubernetes and Docker
```

Quick-search chips are provided for common queries. The platform encodes your query with `all-MiniLM-L6-v2`, runs cosine similarity against the stored resume chunk embeddings, and returns ranked candidates with relevance scores and matched text snippets.

---

## 🔌 API Reference

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/health` | Server health check |
| `POST` | `/candidates/from-csv` | Upload recruiter CSV → ingest candidates |
| `POST` | `/candidates/from-resume` | Upload PDF/DOCX/TXT resume → ingest + enrich |
| `GET` | `/candidates` | List candidates (paginated: `?page=1&page_size=20`) |
| `GET` | `/candidates/{id}` | Get a single candidate by ID |
| `GET` | `/candidates/{id}/confidence` | Per-field confidence breakdown + provenance |
| `POST` | `/candidates/{id}/enrich` | Trigger Gemini RAG enrichment on demand |
| `GET` | `/candidates/search?q=` | Semantic similarity search |
| `POST` | `/candidates/merge` | Manually merge two candidate profiles |
| `DELETE` | `/candidates/{id}` | Delete a specific candidate |
| `DELETE` | `/candidates` | Clear all candidates (reset database) |

Full interactive docs available at **http://localhost:8001/api/docs**

---

## 🧪 Testing

The project has **56 tests** across 3 test files. All tests run **offline** — MongoDB, Gemini, and HuggingFace are fully mocked.

```bash
# Run the full test suite
venv\Scripts\python.exe -m pytest tests/ -v

# macOS / Linux
python -m pytest tests/ -v

# With coverage report
python -m pytest tests/ -v --cov=. --cov-report=term-missing
```

### Test Coverage

| File | Tests | Covers |
|---|---|---|
| `tests/test_api.py` | 23 | All HTTP endpoints — CSV upload, resume upload, list, get, enrich, delete |
| `tests/test_merger.py` | 18 | Deduplication, skill union, experience merge, confidence scoring, edge cases |
| `tests/test_normalizers.py` | 15 | Phone E.164 normalization, skill canonicalization, date range parsing |

```
======================= 56 passed in 22.18s =======================
```

---

## 🔁 Contributing / Forking

### Option A — Fork this repo and set up your own

1. Click **Fork** at the top right of [this repo](https://github.com/nikghost17/multisource-candidate-transformer)
2. Clone your fork:
   ```bash
   git clone https://github.com/<your-username>/multisource-candidate-transformer.git
   cd multisource-candidate-transformer
   ```
3. Follow the [Quickstart](#-quickstart) steps above
4. Create a feature branch:
   ```bash
   git checkout -b feat/my-new-feature
   ```
5. Make your changes, run tests, then push:
   ```bash
   python -m pytest tests/ -v   # all 56 must pass
   git add .
   git commit -m "feat: describe your change"
   git push origin feat/my-new-feature
   ```
6. Open a Pull Request from your branch → `main`

### Option B — Push your own code to GitHub

If you already have this project locally and want to push it:

```bash
cd multisource_candidate_platform

# Initialize git (if not already done)
git init
git add .
git commit -m "feat: initial commit — multisource candidate platform"

# Add the remote and push
git remote add origin https://github.com/nikghost17/multisource-candidate-transformer.git
git branch -M main
git push -u origin main
```

### What NOT to commit

The `.gitignore` is pre-configured to exclude:

| Excluded | Reason |
|---|---|
| `.env` | Contains your secret API keys — **never commit this** |
| `venv/` | Too large; recreated via `pip install -r requirements.txt` |
| `node_modules/` | Too large; recreated via `npm install` |
| `frontend/.next/` | Next.js build cache; auto-generated |
| `__pycache__/` | Python bytecode; auto-generated |
| `output/` | Runtime data; not source code |
| `input/*.pdf` | Uploaded files; not source code |

---

## 📄 License

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">
  Built with ❤️ by <a href="https://github.com/nikghost17">Nikhil Nilesh Vedak</a>
</p>
