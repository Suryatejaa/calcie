import Constants from "expo-constants";

let notificationsModule = null;
let configured = false;

async function loadNotifications() {
  if (notificationsModule) return notificationsModule;
  try {
    const mod = await import("expo-notifications");
    notificationsModule = mod;
    return notificationsModule;
  } catch {
    return null;
  }
}

async function ensurePermissions(Notifications) {
  try {
    const current = await Notifications.getPermissionsAsync();
    if (current.status === "granted") return true;
    const request = await Notifications.requestPermissionsAsync();
    return request.status === "granted";
  } catch {
    return false;
  }
}

export async function scheduleLocalAlert(title, body) {
  // Avoid importing expo-notifications in Expo Go to prevent warning noise.
  if (Constants.appOwnership === "expo") return false;

  const Notifications = await loadNotifications();
  if (!Notifications) return false;

  if (!configured) {
    Notifications.setNotificationHandler({
      handleNotification: async () => ({
        shouldShowAlert: true,
        shouldPlaySound: false,
        shouldSetBadge: false,
      }),
    });
    configured = true;
  }

  const granted = await ensurePermissions(Notifications);
  if (!granted) return false;

  try {
    await Notifications.scheduleNotificationAsync({
      content: {
        title: String(title || "CALCIE"),
        body: String(body || ""),
      },
      trigger: null,
    });
    return true;
  } catch {
    return false;
  }
}

export function isExpoGo() {
  return Constants.appOwnership === "expo";
}
