# CALCIE Mobile V2.1 (Android)

V2.1 builds on V2 and adds safety + usability upgrades for daily use.

## What is new in V2.1
- High-risk command detection and **Action Cards** (Approve / Reject).
- Deferred execution for risky inbound remote commands.
- App wake-up sync: refresh queue when app returns to foreground.
- Local inbound alerts (notification scheduling best-effort).
- In-app voice output (TTS) using `expo-speech`.
- Voice input pathway in Expo Go via keyboard dictation shortcut (`Mic` helper button).

## Core behaviors
- `open ...`, `play ...`, `search ...` still work as before.
- If a command looks risky (`buy`, `order`, `pay`, `delete`, `transfer`, etc.) and approval is enabled:
  - command is queued in Action Cards
  - you must approve before execution
- Remote risky commands are acknowledged as `skipped` in backend and moved to local Action Cards.

## Env config
Create `mobile_v2/.env` from `.env.example`:

```env
EXPO_PUBLIC_CALCIE_API_BASE_URL=https://calcie.onrender.com
EXPO_PUBLIC_CALCIE_USER_ID=local-user
EXPO_PUBLIC_CALCIE_DEVICE_ID=mobile-v2
EXPO_PUBLIC_CALCIE_DEVICE_TYPE=mobile
EXPO_PUBLIC_CALCIE_LAPTOP_DEVICE_ID=laptop
EXPO_PUBLIC_CALCIE_APP_OPEN_MODE=app_only
EXPO_PUBLIC_CALCIE_POLL_SECONDS=3
EXPO_PUBLIC_CALCIE_REQUIRE_ACTION_APPROVAL=1
EXPO_PUBLIC_CALCIE_TTS_ENABLED=1
EXPO_PUBLIC_CALCIE_ANNOUNCE_INBOUND=1
```

## Run
```bash
cd mobile_v2
npm install
npx expo start -c --lan
```

## Notes
- Expo Go must stay running for polling-based command execution.
- Notification module integration is disabled in Expo Go to avoid SDK 53+ warning noise.
- In Expo Go, inbound alert fallback is voice announcement when TTS is enabled.
- Remote push wakeups require development/production builds (not Expo Go).
- V2.1 still uses the same backend API contract from `calcie_cloud/server.py`.

## V2.1 UI quick guide
- `Chat` tab:
  - Action Cards (if any risky commands are pending)
  - command feed
  - `Mic` helper (focus input + dictation tip)
  - `Speak Last` / `Stop Voice`
- `Settings` tab:
  - endpoint + IDs
  - app open mode
  - polling interval
  - toggles for approval, TTS, inbound alerts
