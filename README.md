# AI Codebase Engineering Agent
 
A web-based, read-only AI agent that investigates software repositories and answers codebase questions with file and line citations.
 
The agent can investigate:
- Local repositories available to the backend
- GitHub repositories through the official remote GitHub MCP server
 
Instead of sending an entire codebase to an LLM, the agent plans an investigation, searches for relevant evidence, reads only the required files, evaluates the evidence, and produces a cited answer.
 
The system is built around a bounded Plan → Act → Observe → Evaluate → Answer workflow with strict limits on tool calls, execution time, files read, context size, and investigation steps.
 
---
 
## ✨ Key Features
 
- Bounded AI codebase investigation agent
- Local repository analysis
- GitHub repository analysis
- Official remote GitHub MCP integration
- Lexical code search
- Selective file reading
- Natural-language codebase questions
- File and line citations
- Real-time agent activity through SSE
- Strict agent execution budgets
- Read-only repository investigation
- Citation validation
- FastAPI backend
- Next.js 14 + TypeScript frontend
- Standalone local MCP server
- Unified repository abstraction for local and GitHub sources
 
---
 
# 🚀 Local Setup
 
## Prerequisites
 
- Python 3.10+
- Node.js 18+
- npm
- Git
- Optional: ripgrep
 
Developed with Python 3.13 and Node.js 22.
 
## 1. Clone the Repository
 
```bash
git clone https://github.com/sharaddsingh/AI-Codebase-Agent.git
cd AI-Codebase-Agent
```
 
## 2. Create a Python Virtual Environment
 
### Windows
 
```powershell
python -m venv .venv
.venv\Scripts\activate
```
 
### macOS / Linux
 
```bash
python3 -m venv .venv
source .venv/bin/activate
```
 
## 3. Install Backend Dependencies
 
```bash
pip install -r requirements.txt
```
 
For development and testing:
 
```bash
pip install -r requirements-dev.txt
```
 
## 4. Configure Environment Variables
 
### Windows PowerShell
 
```powershell
Copy-Item .env.example .env
```
 
### macOS / Linux
 
```bash
cp .env.example .env
```
 
Edit `.env` and configure your model credentials.
 
Example:
 
```env
MODEL_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_api_key_here
```
 
If your current setup uses AgentRouter, configure the AgentRouter base URL and credentials expected by the implementation.
 
Configure the credentials required by the remote GitHub MCP integration.
 
Never commit `.env` or expose secrets through `NEXT_PUBLIC_*` variables.
 
## 5. Install Frontend Dependencies
 
```bash
cd frontend
npm install
cd ..
```
 
For local development:
 
```env
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
```
 
Place this in `frontend/.env.local`.
 
## 6. Start the Backend
 
From the project root:
 
```bash
python -m uvicorn backend.main:app --reload --port 8000
```
 
Backend: `http://localhost:8000`
 
API docs: `http://localhost:8000/docs`
 
Health check: `http://localhost:8000/api/health`
 
## 7. Start the Frontend
 
Open a second terminal:
 
```bash
cd frontend
npm run dev
```
 
Frontend: `http://localhost:3000`
 
Open `http://localhost:3000`.
 
---
 
# 🧪 Quick Test
 
1. Register a local repository using an absolute path.
2. Or register a GitHub repository using a GitHub URL.
3. Browse the repository tree.
4. Ask a question such as:
 
```text
How does authentication work?
```
 
or:
 
```text
Where is theme switching implemented?
```
 
The agent should investigate the repository and return an evidence-backed answer with file/line citations.
 
---
 
# 🏗️ Architecture
 
```text
                        AI Codebase Agent
                               |
                               v
                        FastAPI Backend
                               |
                               v
                        Agent Orchestrator
                               |
                +--------------+--------------+
                |                             |
                v                             v
       Local Repository                GitHub Repository
                |                             |
                v                             v
       Local Filesystem                GitHub MCP Client
                                             |
                                             v
                                 Remote GitHub MCP Server
                                             |
                                             v
                                          GitHub
```
 
---
 
# 🔄 Agent Workflow
 
```text
User Question
    |
    v
Task Classification
    |
    v
Investigation Planning
    |
    v
Tool Selection
    |
    v
Read-only Tool Call
    |
    v
Observation
    |
    v
Budget Evaluation
    |
    +---------- Continue ----------+
    |                              |
    |                              v
    |                        More Evidence
    |                              |
    +------------------------------+
    |
    v
Finalization
    |
    v
Citation Validation
    |
    v
Evidence-backed Answer
```
 
The agent selectively searches and reads relevant repository evidence rather than blindly sending the whole codebase to the model.
 
---
 
# 🔌 GitHub MCP Integration
 
GitHub repository investigation uses the official remote GitHub MCP server.
 
```text
AI Codebase Agent
      |
      v
GitHub MCP Client
      |
      v
api.githubcopilot.com/mcp/readonly
      |
      v
Official GitHub MCP Server
      |
      v
GitHub
```
 
The GitHub MCP integration is read-only.
 
The agent uses MCP tools to retrieve repository information and source code.
 
---
 
# 📂 Local Repository Mode
 
Local repositories are investigated through the local repository engine.
 
```text
Frontend
   |
   v
FastAPI Backend
   |
   v
Local Repository Engine
   |
   v
Filesystem
```
 
The backend can access a local repository because it is running on the same machine as that repository.
 
## Cloud Limitation
 
A cloud-hosted backend cannot directly access arbitrary folders on a user's personal computer.
 
Therefore:
 
Local development:
- Local repositories ✅
- GitHub repositories ✅
 
Cloud deployment:
- GitHub repositories ✅
- User's local filesystem ❌ without an additional local companion/agent
 
---
 
# 🤖 Agent Components
 
```text
agent/
├── model adapter
├── task classifier
├── tools
├── bounded agent loop
├── budget tracking
├── observation handling
└── citation validation
```
 
The agent gathers evidence incrementally instead of sending the entire repository to the model.
 
---
 
# 💰 Agent Budgets
 
Default configuration:
 
```env
AGENT_MAX_TOOL_CALLS=12
AGENT_MAX_SECONDS=90
AGENT_MAX_FILES=20
AGENT_MAX_CONTEXT_BYTES=200000
AGENT_MAX_STEPS=16
```
 
These limits prevent runaway loops, excessive model usage, excessive repository reads, unnecessarily large context, and uncontrolled investigation time.
 
When a budget is reached, the agent stops gathering evidence and attempts to finalize using the evidence already collected.
 
---
 
# 🔎 Retrieval
 
The current retrieval engine uses lexical search.
 
It supports:
- ripgrep when available
- pure-Python fallback when ripgrep is unavailable
 
Future retrieval improvements can include embeddings, semantic search, reranking, and hybrid retrieval.
 
---
 
# 📚 Repository Abstraction
 
Repository access is exposed through a source-independent interface.
 
Supported operations include:
- list files
- read file
- search repository
- get file metadata
 
The repository implementation determines whether the source is `LOCAL` or `GITHUB`.
 
---
 
# 📌 Citation System
 
The agent produces file and line citations based on evidence actually retrieved.
 
Example:
 
```text
frontend/components/ThemeToggle.tsx:5-63
```
 
The frontend can use citations to navigate to the referenced file and line range.
 
Citation validation helps prevent the agent from claiming evidence from files it did not retrieve.
 
---
 
# 🖥️ Frontend
 
The frontend is built with:
- Next.js 14
- TypeScript
- React
 
The interface provides:
- local repository registration
- GitHub repository registration
- repository source detection
- repository switching
- repository removal from application state
- file tree navigation
- code viewer
- open-file tabs
- file closing
- agent chat
- live investigation activity
- clickable file citations
- citation-driven file navigation
 
---
 
# 🔐 Security
 
Security is a core part of the project.
 
## Read-only Repository Access
 
The investigation workflow is designed around read-only repository operations.
 
## Local Path Containment
 
Local repository paths are validated according to the configured repository-root policy.
 
## Untrusted Repository Content
 
Repository content is treated as untrusted input and must not be treated as trusted system instructions.
 
## Server-side Secrets
 
Credentials remain server-side.
 
Never expose:
 
```text
ANTHROPIC_API_KEY
GITHUB_TOKEN
```
 
through frontend code or `NEXT_PUBLIC_*` variables.
 
## Citation Validation
 
The agent can only cite evidence retrieved during the current investigation.
 
## Execution Budgets
 
The agent is bounded by tool calls, elapsed time, files read, context size, and investigation steps.
 
See `docs/SECURITY.md` for details.
 
---
 
# 🧩 MCP Components
 
## Standalone Local MCP Server
 
Located at:
 
```text
mcp/server.py
```
 
Uses the official MCP SDK and exposes local repository capabilities to external MCP clients.
 
Run:
 
```bash
python mcp/server.py
```
 
This is separate from the normal browser workflow.
 
## Remote GitHub MCP
 
The browser-based agent uses the remote GitHub MCP integration for GitHub repositories.
 
```text
Agent
 |
 v
MCP Client
 |
 v
Remote GitHub MCP
 |
 v
GitHub
```
 
---
 
# 🧪 Testing
 
## Python Tests
 
```bash
python -m pytest
```
 
## Python Lint
 
```bash
python -m ruff check .
```
 
## Python Type Checking
 
```bash
python -m mypy code_intelligence retrieval agent backend
```
 
## Frontend Tests
 
```bash
cd frontend
npm test
```
 
## Frontend Lint
 
```bash
npm run lint
```
 
## Frontend Production Build
 
```bash
npm run build
```
 
---
 
# ⚙️ Environment Variables
 
| Variable | Default | Purpose |
|---|---|---|
| `MODEL_PROVIDER` | `anthropic` | Model provider or deterministic mock |
| `ANTHROPIC_API_KEY` | — | Server-side model credential |
| `ANTHROPIC_MODEL` | `claude-opus-5` | Model identifier |
| `ANTHROPIC_MAX_TOKENS` | `4096` | Maximum model response tokens |
| `ANTHROPIC_BASE_URL` | — | Model API base URL override |
| `AGENT_MAX_TOOL_CALLS` | `12` | Maximum tool calls per question |
| `AGENT_MAX_SECONDS` | `90` | Maximum investigation time |
| `AGENT_MAX_FILES` | `20` | Maximum files read |
| `AGENT_MAX_CONTEXT_BYTES` | `200000` | Maximum model context/tool output |
| `AGENT_MAX_STEPS` | `16` | Maximum investigation steps |
| `ALLOWED_REPO_ROOTS` | empty | Allowed local repository roots |
| `RESPECT_GITIGNORE` | `true` | Honor repository `.gitignore` |
| `DEFAULT_REPO_PATH` | empty | Optional local repository |
| `GITHUB_TOKEN` | empty | GitHub authentication where required |
| `GITHUB_API_BASE_URL` | `https://api.github.com` | GitHub API base URL where applicable |
| `LOG_LEVEL` | `INFO` | Backend logging level |
| `CORS_ORIGINS` | `http://localhost:3000` | Allowed frontend origins |
| `NEXT_PUBLIC_API_BASE_URL` | `http://localhost:8000` | Backend URL exposed to browser |
| `MCP_ALLOWED_ROOTS` | empty | Allowed roots for standalone local MCP server |
 
---
 
# 📁 Project Structure
 
```text
ai-codebase-agent/
│
├── agent/
│   ├── model adapter
│   ├── classifier
│   ├── tools
│   ├── bounded agent loop
│   ├── budgets
│   └── citation validation
│
├── backend/
│   ├── FastAPI application
│   ├── repository APIs
│   ├── file APIs
│   ├── search APIs
│   └── agent SSE
│
├── code_intelligence/
│   ├── repository interface
│   ├── local repository engine
│   ├── GitHub MCP integration
│   └── repository registry
│
├── retrieval/
│   └── lexical retrieval
│
├── mcp/
│   └── standalone local MCP server
│
├── frontend/
│   └── Next.js application
│
├── tests/
│   ├── Python test suite
│   └── fixture repositories
│
├── docs/
│   ├── ARCHITECTURE.md
│   ├── SECURITY.md
│   ├── MCP.md
│   └── ROADMAP.md
│
├── docker/
│   └── deployment scaffolding
│
├── .env.example
├── requirements.txt
├── requirements-dev.txt
└
