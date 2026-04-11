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
const USER_ID = process.env.EXPO_PUBLIC_CALCIE_USER_ID || "surya";
const DEVICE_ID = process.env.EXPO_PUBLIC_CALCIE_DEVICE_ID || "mobile";
const DEVICE_TYPE = "mobile";
const LAPTOP_DEVICE_ID = process.env.EXPO_PUBLIC_CALCIE_LAPTOP_DEVICE_ID || "laptop";

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
        label: "Surya Mobile",
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
