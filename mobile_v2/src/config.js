export const DEFAULT_SETTINGS = {
  apiBaseUrl: process.env.EXPO_PUBLIC_CALCIE_API_BASE_URL || "https://calcie.onrender.com",
  userId: process.env.EXPO_PUBLIC_CALCIE_USER_ID || "local-user",
  deviceId: process.env.EXPO_PUBLIC_CALCIE_DEVICE_ID || "mobile-v2",
  deviceType: process.env.EXPO_PUBLIC_CALCIE_DEVICE_TYPE || "mobile",
  laptopDeviceId: process.env.EXPO_PUBLIC_CALCIE_LAPTOP_DEVICE_ID || "laptop",
  appOpenMode: process.env.EXPO_PUBLIC_CALCIE_APP_OPEN_MODE || "app_only",
  pollSeconds: Number(process.env.EXPO_PUBLIC_CALCIE_POLL_SECONDS || 3),
  requireActionApproval: String(
    process.env.EXPO_PUBLIC_CALCIE_REQUIRE_ACTION_APPROVAL || "1"
  ).trim() !== "0",
  ttsEnabled: String(process.env.EXPO_PUBLIC_CALCIE_TTS_ENABLED || "1").trim() !== "0",
  announceInbound: String(process.env.EXPO_PUBLIC_CALCIE_ANNOUNCE_INBOUND || "1").trim() !== "0",
};

export const STORAGE_KEYS = {
  settings: "calcie_v2_settings",
  logs: "calcie_v2_logs",
  outbox: "calcie_v2_outbox",
  pushToken: "calcie_v2_push_token",
  pendingActions: "calcie_v2_pending_actions",
};
