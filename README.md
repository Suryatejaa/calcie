# CALCIE

**A Personal AI Companion That Lives With You, Not In A Browser Tab**

CALCIE is a local-first AI assistant designed to become a persistent companion across your devices.

Unlike traditional AI chat applications that forget context between sessions, CALCIE combines memory, voice, automation, local execution, and cloud-assisted intelligence into a unified personal AI experience.

Currently available as a public macOS Alpha.

---

## Why I Built CALCIE

Most AI assistants today are incredibly capable and surprisingly forgetful.

They can answer questions, write code, and summarize documents, but they do not truly feel personal.

CALCIE was built around a different idea:

> Your AI assistant should remember you, learn from you, adapt to you, and stay with you across devices.

The long-term vision is a personal AI companion with:

- Persistent memory
- Voice interaction
- Cross-device continuity
- Local-first execution
- Optional cloud intelligence
- User-controlled personalization

---

## What CALCIE Does

### Conversational AI

- Natural language chat
- Multi-provider AI routing
- Context-aware responses
- Memory-aware conversations

### Voice Assistant

- Push-to-talk interaction
- Speech-to-text processing
- Text-to-speech responses
- Hands-free workflows

### Personal Memory

- User profile awareness
- Preference retention
- Learned aliases and context
- Memory import capabilities

### Automation Layer

- Local system actions
- Workflow execution
- Extensible tool architecture
- Future agentic capabilities

### Cross-Device Vision

CALCIE is designed to become available across:

- macOS
- Windows
- Linux
- Mobile devices

while preserving a shared identity and memory layer.

---

## Current Product Status

### Public Alpha

CALCIE is currently available as a public macOS Alpha.

Current capabilities:

- Native macOS menu bar application
- Voice push-to-talk
- Local runtime execution
- Cloud-assisted update infrastructure
- Launch-at-login support
- Built-in media player
- Memory import workflow

---

## Architecture

```text
User
  ↓
Native Desktop Shell
  ↓
Local Runtime
  ↓
Memory Layer
  ↓
Tool & Automation Layer
  ↓
AI Provider Routing
  ↓
Response Generation
```

Current implementation:

```text
macOS Shell
      ↓
Local Runtime
      ↓
Local Control API
      ↓
Memory + Skills
      ↓
AI Providers
```

---

## Design Philosophy

### Local-First

Your assistant should continue functioning even when cloud services are unavailable.

### Memory-Driven

Conversations should build upon previous interactions rather than starting from zero.

### Provider Agnostic

CALCIE is not tied to a single AI vendor.

It can route requests across multiple providers and evolve as the AI ecosystem changes.

### Human-Centric

The assistant should adapt to the user rather than forcing the user to adapt to the assistant.

---

## Technical Highlights

### AI Infrastructure

- Multi-provider LLM routing
- OpenAI integration
- Gemini integration
- Claude integration
- Local model support roadmap

### Systems Design

- Native desktop integration
- Local HTTP communication layer
- Cloud-assisted release management
- Modular runtime architecture

### Memory Architecture

- Persistent memory model
- Profile retrieval
- Context enrichment
- User personalization

---

## Challenges Solved

### Problem

Most AI assistants lose context between sessions.

### Solution

Designed CALCIE around persistent memory and profile retrieval rather than isolated conversations.

---

### Problem

Users become dependent on a single AI provider.

### Solution

Implemented provider-agnostic routing supporting multiple AI models.

---

### Problem

Cloud-only assistants create latency, privacy, and reliability concerns.

### Solution

Built CALCIE as a local-runtime-first system with optional cloud assistance.

---

## Roadmap

### Near-Term

- macOS Alpha Hardening
- Windows Tray Application
- Better Memory Retrieval
- Improved Onboarding

### Mid-Term

- Offline Local Models
- Cross-Device Sync
- Expanded Automation Skills
- Mobile Applications

### Long-Term

- Persistent Personal AI Identity
- Fully Adaptive User Profiles
- Hybrid Local + Cloud Intelligence
- Wearable Device Integration

---

## Tech Stack

### AI

- OpenAI
- Gemini
- Claude

### Backend

- Python
- FastAPI

### Memory & Storage

- ChromaDB
- Supabase

### Infrastructure

- Docker
- Render
- Cloudflare R2

### Platforms

- macOS
- Windows (Planned)

---

## Vision

Today's AI assistants answer questions.

Tomorrow's assistants will know who you are.

CALCIE is an attempt to build that future.

Not just another chatbot.

A personal AI companion that remembers, learns, and grows alongside its owner.

---

## About Me

Surya Teja

AI Systems Builder | Founding Engineer

Currently building AI products focused on memory, agents, workflow automation, and intelligent systems.

Open to:
- Founding Engineer Roles
- AI Engineer Roles
- Agent Engineer Roles
- Early-Stage AI Startups