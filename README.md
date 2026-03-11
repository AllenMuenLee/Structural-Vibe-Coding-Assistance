# FLOWD - Structural Vibe Coding Assistant

FLOWD is a PyQt6 desktop app that helps you go from a high-level task description to a structured flowchart and generated code. It uses Amazon Nova models via the OpenAI client to:

- turn a task description into a software structure (flowchart JSON)
- generate code step-by-step from that structure
- enrich an AST map with AI docstrings to improve downstream prompts

This project was built for the Amazon Nova Hackathon.

## Features
- Project dashboard with create/open flows
- Canvas UI to build and visualize flowchart steps
- AI-assisted flowchart generation from a task description
- AI-assisted code generation per step
- Code editor with chat and terminal panels
- Local caching of projects and AST/flowchart files

## Tech Stack
- Python
- PyQt6 (desktop UI)
- OpenAI Python SDK (configured for Amazon Nova)
- python-dotenv

## Setup
1. Create and activate a virtual environment (optional but recommended).
2. Install dependencies:
   ```bash
   pip install PyQt6 openai python-dotenv
   ```
3. Create a `.env` file (or edit the existing one) with:
   ```env
   NOVA_API_KEY=your_api_key_here
   ```

## Run
```bash
python main.py
```

## How It Works (High-Level)
- `src/core/ai_helper.py` sends your project description to Nova to get a flowchart JSON.
- `src/core/AstFlowchartGen.py` scans the project, builds `ast_map.json`, adds docstrings, and can generate `flowchart.json`.
- `src/core/CodeGen.py` runs each flowchart step, calls Nova for code, and writes/updates files.
- `src/core/Flowchart.py` and `src/core/Step.py` manage the in-memory flowchart model.

## Data Storage
Project metadata and cached AST/flowchart files are stored under `%APPDATA%\SVCA\` on Windows. Generated `ast_map.json` and `flowchart.json` are also saved in the project root.

## Project Structure
```
app/
  components/
  pages/
  style/
src/
  core/
  utils/
main.py
```

## Notes
- The Nova endpoints are configured through the OpenAI client with `base_url="https://api.nova.amazon.com/v1"`.
- If you see empty or invalid AI responses, verify `NOVA_API_KEY` and network access.
