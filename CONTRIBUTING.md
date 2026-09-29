# Contributing to Autonomous Research Agent

Thank you for your interest in contributing to the Autonomous Research Agent project! We welcome contributions, bug fixes, feature requests, and documentation improvements.

## 🛠️ Development Setup

1. **Fork & Clone the Repository**
   ```bash
   git clone https://github.com/your-username/research-agent.git
   cd research-agent
   ```

2. **Start Infrastructure Dependencies**
   Ensure Docker Desktop is running:
   ```bash
   docker compose up -d
   ```

3. **Backend Setup**
   ```bash
   cd backend
   python -m venv .venv
   # Windows: .venv\Scripts\activate
   # Linux/macOS: source .venv/bin/activate
   pip install -e .
   ```

4. **Frontend Setup**
   ```bash
   cd frontend
   npm install
   ```

5. **Environment Configuration**
   Copy `.env.example` to `.env` at the root of the repository and populate your API credentials (`OPENAI_API_KEY`, `TAVILY_API_KEY`, etc.).

## 🧪 Running Tests

Run pytest in the backend directory:
```bash
cd backend
pytest
```

## 📝 Pull Request Guidelines

- Ensure all existing tests pass and add unit tests for new agent behavior or service functions.
- Maintain clean TypeScript and Python code formatting (PEP 8, type hints, ESLint).
- Ensure the citation integrity invariant `citations ⊆ sources` is preserved across pipeline changes.
- Open a Pull Request targeting the `main` branch with a clear description of changes.

Thank you for helping build transparent, bounded autonomous research tools!
