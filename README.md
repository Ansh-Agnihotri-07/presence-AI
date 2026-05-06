# Presence AI

**Autonomous Hybrid AI Assistant with Real Execution and Builder System**

*Version: v0.1 (Experimental)*

## Overview
A modular AI assistant that routes tasks across multiple LLMs and can generate + execute real code projects locally.

Presence AI doesn't just return text or simulate outputs—it acts upon its environment to execute code, build applications, and automate system tasks.

## Who is this for?
- Developers experimenting with agentic AI systems
- Students exploring autonomous coding systems
- Researchers studying LLM orchestration

> [!WARNING]
> **⚠️ Warning: Real Execution**
> This system executes real commands on your machine.
> Use only in a controlled environment.

## Key Features
- **Hybrid Routing (Groq + Gemini + Local):** Automatically routes tasks to the most suitable LLM based on complexity and speed requirements.
- **Builder Agent:** Writes, builds, and runs real code directly on the host machine.
- **Memory + Session System:** Maintains persistent context across sessions to remember past interactions and preferences.
- **Error Detection + Auto Repair:** Attempts automatic error detection and repair (experimental, not fully reliable yet).
- **Real Execution (No Simulation):** Actions taken by the AI interact with the real filesystem and OS environments.

## Architecture Overview
Presence AI is composed of several interdependent subsystems:
- **Router:** The intelligent decision layer that evaluates prompts and selects the appropriate underlying engine (Local, Speed, or Reasoning).
- **Builder:** An autonomous sub-agent that writes files, checks for syntax errors, creates run scripts, and observes output.
- **Agents:** Specialized modules that handle specific capabilities (e.g., screen reading, system commands, etc.).
- **Memory:** A robust, persistent storage system for maintaining continuity between sessions.
- **UI:** A lightweight, non-intrusive "Orb" interface for seamless desktop presence.

## Project Structure
```text
presence_ai/
├── core/         # Core configuration, startup, and utilities
├── ai/           # LLM engines and routing logic
├── builder/      # Autonomous execution and project building
├── agents/       # Specialized tool integration
├── memory/       # Context and session management
├── ui/           # Desktop interface components
├── main.py       # Application entry point
├── config.py     # Configuration (loaded from core)
├── README.md
├── .gitignore
├── .env.example
└── LICENSE
```

## Quick Start
Get up and running in a few simple steps:
```bash
git clone https://github.com/Ansh-Agnihotri-07/presence-AI
cd presence-AI
pip install -r requirements.txt
python main.py
```

## Example Build
**Prompt:**
> "Build a task manager web app"

**Output:**
- Created 6 files
- Installed dependencies
- Ran Flask server
- Available at http://127.0.0.1:5000

## Installation
For a more detailed setup:
1. **Clone the repository:**
   ```bash
   git clone https://github.com/Ansh-Agnihotri-07/presence-AI
   cd presence-AI
   ```
2. **Create a virtual environment:**
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows use: venv\Scripts\activate
   ```
3. **Install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
4. **Configure environment variables:**
   - Copy `.env.example` to `.env`.
   - Add your API keys (Groq, Gemini, etc.).

## Usage Examples
Interact with Presence AI through natural language prompts:
- **"Explain TCP vs UDP"**
  - *Result:* Uses the deep reasoning engine to provide a technical explanation.
- **"Set a reminder"**
  - *Result:* Leverages the scheduling system to trigger an event at a specified time.

## Safety Features
Given its ability to execute real code, Presence AI incorporates several safety mechanisms:
- **API Protection:** Safeguards against exposing sensitive keys in outputs.
- **Rate Limiting:** Prevents runaway loops or excessive API charges.
- **Schema Validation:** Ensures inputs and outputs conform to expected structures before execution.
- **Sandboxed Execution:** Limits the scope of commands that the Builder Agent can execute autonomously.

## Known Limitations (IMPORTANT)
- **Complex Apps:** The Builder Agent may struggle to generate or repair highly complex applications from a single prompt.
- **Repair Loop:** The autonomous error-repair mechanism is still evolving and may occasionally loop indefinitely on subtle logic bugs.
- **UI Styling:** The current desktop UI (Orb) is functional but lacks final polish and advanced customization.

## Roadmap
- Improve Builder reliability for multi-file architecture generation.
- Add support for scaffolding more frameworks (e.g., Next.js, Django).
- Upgrade the UI with better visualizations of AI reasoning.
- Implement a streamlined deployment system for generated applications.
