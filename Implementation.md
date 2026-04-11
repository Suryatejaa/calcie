You are an expert Python developer. Help me build a personal AI assistant called "Jarvis" step by step.

My setup:
- OS: Linux (Ubuntu)
- Language: Python 3
- I want: voice input (mic), LLM brain (Ollama local model), voice output (text-to-speech), and a simple memory system

Build this in phases. Start with Phase 1 only. Wait for me to confirm before moving to the next phase.

---

PHASE 1 — Core loop (text only, no voice yet)
- A Python script called jarvis.py
- It takes user input from the terminal
- Sends it to Ollama API (http://localhost:11434/api/chat) using the "mistral" model
- Prints the response
- Loops until user types "exit"
- Add a system prompt that makes it behave like a personal assistant named Jarvis

PHASE 2 — Voice input
- Use the `speech_recognition` library with Google STT (free tier) or whisper (local)
- Replace terminal input with mic input
- Trigger on pressing Enter or on silence detection

PHASE 3 — Voice output
- Use `pyttsx3` for offline TTS or `edge-tts` for better quality
- Speak every response out loud after printing it

PHASE 4 — Memory
- Store each conversation turn in a local SQLite database (jarvis_memory.db)
- On each new session, load the last 10 exchanges and inject them into the system prompt as context
- This gives Jarvis memory across sessions

PHASE 5 — Tools
- Add a web search tool using DuckDuckGo (duckduckgo-search pip package)
- If the user's query needs current info, Jarvis searches and summarizes
- Add a "open app" command that uses subprocess to launch programs by name

Start now with Phase 1. Write the complete jarvis.py file with all imports, error handling, and a requirements.txt file.