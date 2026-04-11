# CALCIE Mobile V1 (Android)

This is a lightweight Android-first client (Expo React Native) for CALCIE sync.

## What V1 does
- Registers mobile device in CALCIE sync backend
- Sends user commands/messages to cloud history
- Executes basic local mobile actions:
  - `play ...` -> opens YouTube/YouTube Music URL
  - `open ...` -> opens target URL/search
- Routes commands to laptop when user says target phrases like:
  - `... on laptop`
  - `... on desktop`
- Polls inbound commands from backend and executes them on mobile

## What V1 does not do yet
- Full local LLM inference in app
- Deep Android automation (Accessibility-based full UI control)
- Native voice pipeline parity with desktop

## Setup
1. Start backend:
```bash
python3 -m uvicorn calcie_cloud.server:app --host 0.0.0.0 --port 8000
```
2. Create `mobile_v1/.env` from `mobile_v1/.env.example` and set:
```env
EXPO_PUBLIC_CALCIE_API_BASE_URL=http://YOUR_SERVER_IP:8000
EXPO_PUBLIC_CALCIE_USER_ID=surya
EXPO_PUBLIC_CALCIE_DEVICE_ID=mobile
EXPO_PUBLIC_CALCIE_LAPTOP_DEVICE_ID=laptop
```
3. Install and run:
```bash
cd mobile_v1
npm install
npx expo start --lan
```

## Device IDs
By default:
- mobile app device id: `mobile`
- laptop device id target: `laptop`

If you change desktop IDs in laptop `.env`, keep
`EXPO_PUBLIC_CALCIE_LAPTOP_DEVICE_ID` in mobile `.env` in sync.

## Suggested V2 upgrades
- Replace hardcoded config with secure settings screen
- Add push notifications for inbound commands
- Add voice input + TTS
- Add task cards for confirm/cancel workflows
