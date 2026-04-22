# CALCIE Mobile V1 (Android)

This is a lightweight Android-first client (Expo React Native) for CALCIE sync.

## What V1 does
- Registers mobile device in CALCIE sync backend
- Sends user commands/messages to cloud history
- Executes basic local mobile actions:
  - `play ...` -> opens YouTube/YouTube Music URL
  - `open ...` -> app-first launch for common apps (WhatsApp, YouTube, YouTube Music, Chrome, Instagram, Telegram, Spotify, Netflix, Prime Video, Hotstar, Amazon, Gmail, Maps, Play Store), then fallback
- Routes commands to laptop when user says target phrases like:
  - `... on laptop`
  - `... on desktop`
- Polls inbound commands from backend and executes them on mobile

## What V1 does not do yet
- Full local LLM inference in app
- Deep Android automation (Accessibility-based full UI control)
- Native voice pipeline parity with desktop
- True always-on background command execution when app is fully closed

## Setup
1. Start backend:
```bash
python3 -m uvicorn calcie_cloud.server:app --host 0.0.0.0 --port 8000
```
2. Create `mobile_v1/.env` from `mobile_v1/.env.example` and set:
```env
EXPO_PUBLIC_CALCIE_API_BASE_URL=http://YOUR_SERVER_IP:8000
EXPO_PUBLIC_CALCIE_USER_ID=local-user
EXPO_PUBLIC_CALCIE_DEVICE_ID=mobile
EXPO_PUBLIC_CALCIE_LAPTOP_DEVICE_ID=laptop
EXPO_PUBLIC_CALCIE_APP_OPEN_MODE=app_only
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
- Add push notifications (FCM + Expo Notifications) for closed-app wakeups
- Add voice input + TTS
- Add task cards for confirm/cancel workflows

## Important sync behavior
- V1 uses polling from the running app process.
- If the Expo app is force-closed, inbound commands are queued in backend and run when app opens again.
- For near real-time closed-app behavior, use push notifications + background handling in a production build.

## App launch fallback order (Android)
1. Try app deep links directly.
2. Try Android package intent.
3. Try Play Store app page.
4. If `EXPO_PUBLIC_CALCIE_APP_OPEN_MODE=app_first`, fallback to browser.
5. If `EXPO_PUBLIC_CALCIE_APP_OPEN_MODE=app_only`, never fallback to browser.
