import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  SafeAreaView,
  View,
  Text,
  TextInput,
  TouchableOpacity,
  FlatList,
  Linking,
  StyleSheet,
} from "react-native";

// V1 config (set in .env as EXPO_PUBLIC_* for deployed backend)
const API_BASE_URL =
  process.env.EXPO_PUBLIC_CALCIE_API_BASE_URL || "http://YOUR_SERVER_IP:8000";
const USER_ID = process.env.EXPO_PUBLIC_CALCIE_USER_ID || "local-user";
const DEVICE_ID = process.env.EXPO_PUBLIC_CALCIE_DEVICE_ID || "mobile";
const DEVICE_TYPE = "mobile";
const LAPTOP_DEVICE_ID = process.env.EXPO_PUBLIC_CALCIE_LAPTOP_DEVICE_ID || "laptop";
// app_only | app_first
const APP_OPEN_MODE = process.env.EXPO_PUBLIC_CALCIE_APP_OPEN_MODE || "app_only";

function normalize(input) {
  return String(input || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function stripTargetPhrase(text) {
  let out = String(text || "").trim();
  out = out.replace(/\b(?:on|in|to)\s+(?:my\s+)?(?:mobile|phone|android)\b/gi, " ");
  out = out.replace(/\b(?:on|in|to)\s+(?:my\s+)?(?:laptop|desktop|mac|pc)\b/gi, " ");
  out = out.replace(/\s+/g, " ").trim();
  return out || text;
}

function androidIntentForPackage(packageName) {
  return `intent://#Intent;package=${packageName};end`;
}

const APP_ROUTES = [
  {
    regex: /\bwhats\s?app\b/,
    name: "WhatsApp",
    packageName: "com.whatsapp",
    appUrls: ["whatsapp://send", "whatsapp://", "https://api.whatsapp.com"],
    fallbackUrl: "https://wa.me/",
  },
  {
    regex: /\bphone\b|\bdialer\b|\bcall app\b/,
    name: "Phone",
    packageName: "com.google.android.dialer",
    appUrls: ["tel:", "tel://"],
    fallbackUrl: "",
  },
  {
    regex: /\btelegram\b/,
    name: "Telegram",
    packageName: "org.telegram.messenger",
    appUrls: ["tg://resolve"],
    fallbackUrl: "https://t.me/",
  },
  {
    regex: /\binstagram\b|\big\b/,
    name: "Instagram",
    packageName: "com.instagram.android",
    appUrls: ["instagram://app"],
    fallbackUrl: "https://www.instagram.com",
  },
  {
    regex: /\binsta\b|\big\b/,
    name: "Insta",
    packageName: "com.instagram.android",
    appUrls: ["instagram://app"],
    fallbackUrl: "https://www.instagram.com",
  },
  {
    regex: /\bfacebook\b|\bfb\b/,
    name: "Facebook",
    packageName: "com.facebook.katana",
    appUrls: ["fb://facewebmodal/f?href=https://www.facebook.com"],
    fallbackUrl: "https://www.facebook.com",
  },
  {
    regex: /\bspotify\b/,
    name: "Spotify",
    packageName: "com.spotify.music",
    appUrls: ["spotify://"],
    fallbackUrl: "https://open.spotify.com",
  },
  {
    regex: /\byoutube music\b|\byt music\b|\bytmusic\b/,
    name: "YouTube Music",
    packageName: "com.google.android.apps.youtube.music",
    appUrls: ["youtubemusic://", "vnd.youtube.music://"],
    fallbackUrl: "https://music.youtube.com",
  },
  {
    regex: /\byoutube\b|\byt\b/,
    name: "YouTube",
    packageName: "com.google.android.youtube",
    appUrls: ["vnd.youtube://", "youtube://"],
    fallbackUrl: "https://www.youtube.com",
  },
  {
    regex: /\bnetflix\b/,
    name: "Netflix",
    packageName: "com.netflix.mediaclient",
    appUrls: ["nflx://www.netflix.com"],
    fallbackUrl: "https://www.netflix.com",
  },
  {
    regex: /\bprime video\b|\bamazon prime\b/,
    name: "Prime Video",
    packageName: "com.amazon.avod.thirdpartyclient",
    appUrls: ["primevideo://"],
    fallbackUrl: "https://www.primevideo.com",
  },
  {
    regex: /\bhotstar\b|\bdisney\b/,
    name: "Disney+ Hotstar",
    packageName: "in.startv.hotstar",
    appUrls: ["hotstar://"],
    fallbackUrl: "https://www.hotstar.com",
  },
  {
    regex: /\bamazon\b/,
    name: "Amazon Shopping",
    packageName: "in.amazon.mShop.android.shopping",
    appUrls: ["amazon://"],
    fallbackUrl: "https://www.amazon.in",
  },
  {
    regex: /\bgmail\b|\bemail\b/,
    name: "Gmail",
    packageName: "com.google.android.gm",
    appUrls: ["googlegmail://"],
    fallbackUrl: "https://mail.google.com",
  },
  {
    regex: /\bgoogle maps\b|\bmaps\b/,
    name: "Google Maps",
    packageName: "com.google.android.apps.maps",
    appUrls: ["geo:0,0?q=", "google.navigation:q=home"],
    fallbackUrl: "https://maps.google.com",
  },
  {
    regex: /\bchrome\b/,
    name: "Google Chrome",
    packageName: "com.android.chrome",
    appUrls: ["googlechrome://"],
    fallbackUrl: "https://www.google.com",
  },
  {
    regex: /\bplay store\b/,
    name: "Play Store",
    packageName: "com.android.vending",
    appUrls: ["market://search?q=apps"],
    fallbackUrl: "https://play.google.com/store",
  },
];

async function api(path, options = {}) {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    throw new Error(`HTTP ${res.status}: ${body}`);
  }
  return await res.json();
}

async function tryOpenAppUrls(urls = []) {
  for (const url of urls) {
    if (!url) continue;
    try {
      // On Android, canOpenURL can be false for valid custom schemes
      // depending on package visibility rules; direct open is more reliable.
      await Linking.openURL(url);
      return url;
    } catch {
      // try next url candidate
    }
  }
  return "";
}

async function openKnownAppTarget(target) {
  const norm = normalize(target);
  if (!norm) return "";

  for (const route of APP_ROUTES) {
    if (!route.regex.test(norm)) continue;

    const urlCandidates = [...(route.appUrls || [])];
    if (route.packageName) {
      urlCandidates.push(androidIntentForPackage(route.packageName));
    }

    const openedUrl = await tryOpenAppUrls(urlCandidates);
    if (openedUrl) return `Opened ${route.name} app.`;

    if (route.packageName) {
      const storeUrl = `market://details?id=${route.packageName}`;
      const openedStoreUrl = await tryOpenAppUrls([storeUrl]);
      if (openedStoreUrl) {
        return `Opened Play Store for ${route.name} (app may not be installed).`;
      }
    }

    if (APP_OPEN_MODE === "app_only") {
      return `Couldn't open ${route.name} app on this device.`;
    }

    if (route.fallbackUrl) {
      await Linking.openURL(route.fallbackUrl);
      return `Opened ${route.name} in browser (app launch unavailable).`;
    }
    return `Couldn't open ${route.name} app on this device.`;
  }
  return "";
}

async function openMusic(command) {
  const raw = String(command || "").trim();
  const norm = normalize(raw);
  let url = "https://music.youtube.com";

  if (/^play\b/.test(norm)) {
    let query = raw.replace(/^play\s*/i, "").trim();
    query = query.replace(/\b(video song|music video|song|video)\b/gi, "").trim();
    query = query.replace(/^(of|for|the)\s+/i, "").trim();
    if (query) {
      if (/video song|music video|on youtube| on yt\b/i.test(raw)) {
        url = `https://www.youtube.com/results?search_query=${encodeURIComponent(
          `${query} official video`
        )}`;
      } else {
        url = `https://music.youtube.com/search?q=${encodeURIComponent(query)}`;
      }
    }
  }
  await Linking.openURL(url);
  return `Opened: ${url}`;
}

async function openTarget(command) {
  const raw = String(command || "").trim();
  const norm = normalize(raw);
  let url = "";

  const m = raw.match(/^(?:open|launch|start)\s+(.+)$/i);
  let target = m ? m[1].trim() : raw;
  target = stripTargetPhrase(target);

  if (!target) return "No target found.";

  const forceBrowser = /\b(in|on)\s+(?:google\s+)?chrome\b|\bbrowser\b|\bweb\b/i.test(raw);
  if (!forceBrowser) {
    const appResult = await openKnownAppTarget(target);
    if (appResult) return appResult;
  }

  if (/^https?:\/\//i.test(target)) {
    url = target;
  } else if (/amazon/.test(norm)) {
    url = "https://www.amazon.in";
  } else if (/netflix/.test(norm)) {
    url = "https://www.netflix.com";
  } else if (/youtube/.test(norm)) {
    url = "https://www.youtube.com";
  } else {
    url = `https://www.google.com/search?q=${encodeURIComponent(target)}`;
  }

  await Linking.openURL(url);
  return `Opened: ${url}`;
}

async function executeLocalCommand(command) {
  const norm = normalize(command);
  if (norm.startsWith("play ") || norm === "play" || norm.includes("play music")) {
    return await openMusic(command);
  }
  if (norm.startsWith("open ") || norm.startsWith("launch ") || norm.startsWith("start ")) {
    return await openTarget(command);
  }
  return "Command received on mobile. V1 supports play/open actions.";
}

export default function App() {
  const [input, setInput] = useState("");
  const [logs, setLogs] = useState([]);
  const [status, setStatus] = useState("Starting...");
  const lastRemoteMessageId = useRef(0);
  const inFlight = useRef(false);

  const addLog = (role, text) => {
    const item = {
      id: `${Date.now()}-${Math.random()}`,
      role,
      text: String(text || ""),
    };
    setLogs((prev) => [item, ...prev]);
  };

  const register = async () => {
    await api("/devices/register", {
      method: "POST",
      body: JSON.stringify({
        user_id: USER_ID,
        device_id: DEVICE_ID,
        device_type: DEVICE_TYPE,
        label: process.env.EXPO_PUBLIC_CALCIE_DEVICE_LABEL || "CALCIE Mobile",
        metadata: { app: "calcie-mobile-v1" },
      }),
    });
  };

  const sendMessageRecord = async (role, content) => {
    await api("/messages", {
      method: "POST",
      body: JSON.stringify({
        user_id: USER_ID,
        device_id: DEVICE_ID,
        role,
        content,
      }),
    });
  };

  const routeToLaptop = async (content) => {
    await api("/commands", {
      method: "POST",
      body: JSON.stringify({
        user_id: USER_ID,
        from_device: DEVICE_ID,
        target_device: LAPTOP_DEVICE_ID,
        content,
        requires_confirm: false,
      }),
    });
  };

  const handleSend = async () => {
    const raw = input.trim();
    if (!raw || inFlight.current) return;
    inFlight.current = true;
    setInput("");
    addLog("user", raw);
    try {
      await sendMessageRecord("user", raw);

      const norm = normalize(raw);
      if (/\b(?:on|in|to)\s+(?:my\s+)?(?:laptop|desktop|mac|pc)\b/i.test(raw)) {
        const cleaned = stripTargetPhrase(raw);
        await routeToLaptop(cleaned);
        const ack = `Routed to laptop: ${cleaned}`;
        addLog("assistant", ack);
        await sendMessageRecord("assistant", ack);
      } else {
        const result = await executeLocalCommand(raw);
        addLog("assistant", result);
        await sendMessageRecord("assistant", result);
      }
    } catch (err) {
      const msg = `Send failed: ${err.message}`;
      addLog("assistant", msg);
    } finally {
      inFlight.current = false;
    }
  };

  const pollCommands = async () => {
    try {
      const data = await api(
        `/commands/poll?user_id=${encodeURIComponent(USER_ID)}&device_id=${encodeURIComponent(
          DEVICE_ID
        )}&limit=10`
      );
      const commands = data.commands || [];
      for (const cmd of commands) {
        const content = String(cmd.content || "");
        const cmdId = Number(cmd.id || 0);
        if (!content || !cmdId) continue;
        addLog("remote", `From ${cmd.from_device}: ${content}`);
        let result = "";
        let status = "done";
        try {
          result = await executeLocalCommand(content);
          addLog("assistant", result);
          await sendMessageRecord("assistant", `[remote:${cmd.from_device}] ${result}`);
        } catch (err) {
          result = `Remote command failed: ${err.message}`;
          status = "failed";
          addLog("assistant", result);
        }
        await api(`/commands/${cmdId}/ack`, {
          method: "POST",
          body: JSON.stringify({ status, result }),
        });
      }
    } catch {
      // keep quiet to avoid noisy logs
    }
  };

  const pullMessages = async () => {
    try {
      const data = await api(
        `/messages?user_id=${encodeURIComponent(USER_ID)}&limit=20&after_id=${lastRemoteMessageId.current}`
      );
      const messages = data.messages || [];
      for (const m of messages) {
        const id = Number(m.id || 0);
        if (id > lastRemoteMessageId.current) lastRemoteMessageId.current = id;
      }
    } catch {
      // ignore
    }
  };

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        await register();
        if (!mounted) return;
        setStatus("Connected");
      } catch (err) {
        if (!mounted) return;
        setStatus(`Offline (${err.message})`);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  useEffect(() => {
    const t = setInterval(() => {
      pollCommands();
      pullMessages();
    }, 3000);
    return () => clearInterval(t);
  }, []);

  const header = useMemo(() => `CALCIE Mobile V1 • ${status}`, [status]);

  return (
    <SafeAreaView style={styles.root}>
      <Text style={styles.title}>{header}</Text>
      <Text style={styles.sub}>
        Device: {DEVICE_ID} • User: {USER_ID} • Target laptop id: {LAPTOP_DEVICE_ID}
      </Text>

      <FlatList
        style={styles.list}
        data={logs}
        keyExtractor={(item) => item.id}
        renderItem={({ item }) => (
          <View style={[styles.msg, item.role === "user" ? styles.msgUser : styles.msgOther]}>
            <Text style={styles.msgRole}>{item.role}</Text>
            <Text style={styles.msgText}>{item.text}</Text>
          </View>
        )}
      />

      <View style={styles.inputRow}>
        <TextInput
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Type: play music / open amazon / play song on laptop"
          placeholderTextColor="#7f8894"
          multiline
        />
        <TouchableOpacity style={styles.btn} onPress={handleSend}>
          <Text style={styles.btnText}>Send</Text>
        </TouchableOpacity>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#0b1118", padding: 14 },
  title: { color: "#d5e3f3", fontSize: 18, fontWeight: "700" },
  sub: { color: "#93a4b8", marginTop: 4, marginBottom: 10, fontSize: 12 },
  list: { flex: 1 },
  msg: {
    padding: 10,
    borderRadius: 10,
    marginBottom: 8,
    borderWidth: 1,
  },
  msgUser: { backgroundColor: "#172437", borderColor: "#27405f" },
  msgOther: { backgroundColor: "#101820", borderColor: "#233140" },
  msgRole: { color: "#8db5df", fontSize: 11, marginBottom: 4 },
  msgText: { color: "#e7edf5", fontSize: 14 },
  inputRow: { flexDirection: "row", gap: 8, marginTop: 10 },
  input: {
    flex: 1,
    minHeight: 48,
    maxHeight: 120,
    backgroundColor: "#121e2d",
    color: "#e7edf5",
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: "#2a3f58",
  },
  btn: {
    width: 74,
    alignItems: "center",
    justifyContent: "center",
    backgroundColor: "#2c7ed6",
    borderRadius: 10,
  },
  btnText: { color: "white", fontWeight: "700" },
});
