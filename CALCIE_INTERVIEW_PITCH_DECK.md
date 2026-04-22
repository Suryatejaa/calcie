# CALCIE Interview Pitch Deck

Use this as a 10-15 minute interview presentation.

---

## Slide 1 - Title
**CALCIE: Cross-Device Personal AI Companion Agent**
**Presenter:** Surya Teja
**Timeline:** 2025 - Present

**Say:**
"CALCIE is my local-first, multi-skill AI companion that works across laptop and mobile, with memory, voice interaction, safe task execution, and cross-device orchestration."

---

## Slide 2 - Problem Statement
**Current assistants are fragmented:**
- Great at conversation, weak at execution
- Good at one device, poor cross-device continuity
- Poor personalization and memory over time
- Either too rigid (commands only) or too unsafe (blind automation)

**Say:**
"I wanted an assistant that can chat, remember, search, act, and coordinate across my real devices without losing safety."

---

## Slide 3 - Vision
**Companion -> Agent progression**
- Understand intent naturally
- Route to the right skill
- Execute safely with guardrails
- Keep context and memory persistent
- Work across laptop + mobile as one system

**Say:**
"The goal is not just a chatbot. It is a practical execution system with orchestration and safety."

---

## Slide 4 - Product Snapshot
**What CALCIE does today**
- Voice + text interaction
- Smart wake logic + quick wake acknowledgment
- Multi-LLM support with automatic fallback
- Skill-based architecture: app access, search, coding, computer control, agentic execution
- Cross-device command routing (`on laptop`, `on mobile`)

**Demo examples:**
- "calcie open youtube"
- "who won last night IPL"
- "play music on mobile"
- "code read calcie.py lines 1-120"

---

## Slide 5 - System Architecture (High Level)
**Layers**
1. Input layer (voice/text)
2. Router/Arbiter (intent + typo-tolerant routing)
3. Skills layer (deterministic action modules)
4. LLM layer (provider abstraction + fallback)
5. Memory layer (SQLite + facts/profile)
6. Sync layer (FastAPI backend + mobile clients)
7. TTS/STT layer (provider cascade)

**Say:**
"This architecture lets me keep deterministic actions deterministic, while still using LLMs where reasoning is needed."

---

## Slide 6 - Core Engineering Decisions
**1) Router + Orchestration**
- Added command arbiter with confidence scoring and fuzzy correction
- Prevents misspellings from bypassing skills

**2) Prompt Decomposition**
- Replaced giant monolithic prompt with route-specific prompts
- Reduced latency and irrelevant responses

**3) Safety by Design**
- Coding uses proposal -> diff -> apply workflow
- Agentic execution has tool allowlist + task limits + stop-before-payment rule

---

## Slide 7 - Search Intelligence
**Search pipeline**
- Provider fallback: Tavily -> Exa -> DDGS
- Scrape top sources
- LLM synthesis prompt for direct answer + confidence line
- Optional source reporting

**Why this matters**
- Avoids returning raw links only
- Produces human-style, grounded answers

---

## Slide 8 - Voice UX and Responsiveness
**What improved**
- Wake acknowledgment (e.g., "Mm-hmm?", "Yeah?") immediately on wake
- Same-utterance wake+command support ("calcie open youtube")
- Bridge/ack feedback system with env-level controls
- Google TTS + Edge TTS + offline fallback

**Tradeoff handled**
- Always-on mic is responsive but battery expensive
- Added controls to tune responsiveness vs resource usage

---

## Slide 9 - Cross-Device Sync
**Backend**
- FastAPI command/message/facts APIs
- Device registration + command polling + acknowledgments

**Clients**
- Desktop runtime (`calcie.py`)
- `mobile_v1`: lightweight command execution
- `mobile_v2`: action cards, local settings, outbox retry, in-app TTS

**Reality**
- Expo Go polling means mobile execution requires app active
- Production path: push + background handling

---

## Slide 10 - Tech Stack
**Core**
- Python, FastAPI, SQLite, JSON memory stores
- Multi-LLM: Gemini / OpenAI / Claude / Grok / Ollama
- Search: Tavily, Exa, DDGS
- Voice: speech_recognition, Google TTS, edge-tts, pyttsx3

**Platform**
- macOS/Linux desktop
- Android (Expo React Native)
- Dockerized backend deployment (Render-compatible)

---

## Slide 11 - Key Challenges and How You Solved Them
**Challenge:** Monolithic prompt caused slow, irrelevant responses
**Fix:** Prompt split + route-based context trimming

**Challenge:** Skill bypass on typos
**Fix:** Fuzzy router + strict intent flags + rewrite

**Challenge:** Web search gave low-quality snippets
**Fix:** multi-source scrape + synthesis layer

**Challenge:** TTS auth failures (Google quota/OAuth)
**Fix:** ADC token + quota project handling + provider fallback

**Challenge:** Unsafe autonomous actions
**Fix:** allowlists, bounded plans, confirmation patterns

---

## Slide 12 - Impact and Learnings
**Impact**
- Built a working cross-device agent platform end-to-end
- Converted assistant behavior from generic chat to orchestrated actions
- Created a reusable architecture for adding new skills safely

**Learnings**
- Deterministic routing + LLM reasoning is stronger than pure prompting
- Safety and UX latency matter as much as model quality
- Production reliability requires explicit fallback design everywhere

---

## Slide 13 - Roadmap (Next 90 Days)
1. Push-to-talk / low-power wake mode for battery optimization
2. Production mobile background execution (push + native build)
3. Stronger observability (latency, failure-rate, provider health)
4. Unified auth/secrets strategy for cloud deployments
5. New skills (calendar/mail workflows with explicit approvals)

---

## Slide 14 - Why This Project Matters for the Role
**Demonstrates**
- Systems design under real constraints
- Backend + mobile + infra ownership
- AI engineering beyond prompt hacking
- Safety-first automation thinking
- Practical debugging and iterative product engineering

**Say:**
"This project reflects how I build: start with a working core, identify friction in real use, then harden architecture, safety, and UX."

---

## Slide 15 - Close
**CALCIE in one line:**
"A local-first, cross-device AI execution system with memory, orchestration, and guardrails."

**Ask to interviewer:**
- "Would you like me to walk through router internals or do a live command flow demo?"

---

## Optional 60-Second Intro Script
"I built CALCIE as a cross-device personal AI agent that goes beyond chat. It uses a router and skill orchestration layer to decide whether to search, execute app actions, perform coding tasks, or use agentic workflows safely. I implemented multi-LLM fallback, persistent memory, web-grounded synthesis, and desktop/mobile sync through a FastAPI backend. A key focus was reliability: prompt decomposition for latency, deterministic routing for correctness, and strict safety boundaries for automation. This project shows end-to-end ownership from architecture and backend to mobile UX and deployment."

---

## Likely Interview Questions and Suggested Answers

**Q1: Why not keep everything in one LLM prompt?**
A: It increased latency and irrelevant context bleed. Route-specific prompts reduced tokens, response time, and hallucinated carryover.

**Q2: How do you prevent unsafe automation?**
A: Tool allowlists, bounded step counts, explicit confirmations for risky flows, and no auto-finalize for purchases.

**Q3: How do you handle provider outages?**
A: Multi-provider fallback for both LLM and search; TTS has online and offline fallback chain.

**Q4: What would you productionize next?**
A: Observability, background mobile execution, stronger auth/secrets, and policy-driven permissioning per skill.
