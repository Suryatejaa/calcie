import React, { useEffect, useMemo, useRef, useState } from "react";
import {
  AppState,
  FlatList,
  SafeAreaView,
  StyleSheet,
  Text,
  TextInput,
  TouchableOpacity,
  View,
} from "react-native";
import * as Device from "expo-device";
import Constants from "expo-constants";

import { DEFAULT_SETTINGS, STORAGE_KEYS } from "./src/config";
import { SyncApi } from "./src/lib/api";
import { readJson, writeJson } from "./src/lib/storage";
import { scheduleLocalAlert } from "./src/lib/notifications";
import { speakText, stopSpeaking } from "./src/lib/voice";
import {
  executeLocalCommand,
  flushOutbox,
  isHighRiskCommand,
  pollAndExecuteInbound,
  sendOrRouteCommand,
} from "./src/engine/commandEngine";

function now() {
  return new Date().toISOString();
}

function toBool(value, fallback = false) {
  if (typeof value === "boolean") return value;
  if (typeof value === "string") {
    const v = value.trim().toLowerCase();
    if (v === "1" || v === "true" || v === "yes" || v === "on") return true;
    if (v === "0" || v === "false" || v === "no" || v === "off") return false;
  }
  return fallback;
}

export default function App() {
  const [screen, setScreen] = useState("chat");
  const [settings, setSettings] = useState(DEFAULT_SETTINGS);
  const [draftSettings, setDraftSettings] = useState(DEFAULT_SETTINGS);
  const [logs, setLogs] = useState([]);
  const [pendingActions, setPendingActions] = useState([]);
  const [input, setInput] = useState("");
  const [status, setStatus] = useState("Booting...");
  const [lastSyncAt, setLastSyncAt] = useState("");
  const [outboxCount, setOutboxCount] = useState(0);
  const [pushToken, setPushToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [lastAssistantText, setLastAssistantText] = useState("");

  const inputRef = useRef(null);

  const api = useMemo(() => new SyncApi(settings.apiBaseUrl), [settings.apiBaseUrl]);

  const addLog = async (role, text) => {
    const value = String(text || "").trim();
    if (!value) return;

    const item = {
      id: `${Date.now()}-${Math.random()}`,
      role,
      text: value,
      ts: now(),
    };

    let next = [];
    setLogs((prev) => {
      next = [item, ...prev].slice(0, 250);
      return next;
    });
    await writeJson(STORAGE_KEYS.logs, next);

    if (role === "assistant") {
      setLastAssistantText(value);
      if (settings.ttsEnabled) {
        await speakText(value, { rate: 0.93, pitch: 0.95, language: "en-US" });
      }
    }
  };

  const setPendingAndPersist = async (updater) => {
    let next = [];
    setPendingActions((prev) => {
      next = typeof updater === "function" ? updater(prev) : updater;
      return next;
    });
    await writeJson(STORAGE_KEYS.pendingActions, next);
  };

  const queuePendingAction = async (action) => {
    const item = {
      id: action.id || `action-${Date.now()}-${Math.random()}`,
      source: action.source || "user",
      content: String(action.content || ""),
      fromDevice: String(action.fromDevice || ""),
      createdAt: action.createdAt || now(),
      risk: "high",
    };

    await setPendingAndPersist((prev) => [item, ...prev].slice(0, 50));
    await addLog("assistant", `Action needs approval: ${item.content}`);
  };

  const removePendingAction = async (actionId) => {
    await setPendingAndPersist((prev) => prev.filter((item) => item.id !== actionId));
  };

  const refreshOutboxCount = async () => {
    const outbox = await readJson(STORAGE_KEYS.outbox, []);
    setOutboxCount(Array.isArray(outbox) ? outbox.length : 0);
  };

  const registerPushToken = async () => {
    try {
      // Expo Go does not support Android remote push tokens; keep this optional.
      if (Constants.appOwnership === "expo") return "";
      if (!Device.isDevice) return "";

      const Notifications = await import("expo-notifications");
      const current = await Notifications.getPermissionsAsync();
      let finalStatus = current.status;
      if (finalStatus !== "granted") {
        const request = await Notifications.requestPermissionsAsync();
        finalStatus = request.status;
      }
      if (finalStatus !== "granted") return "";

      const tokenResponse = await Notifications.getExpoPushTokenAsync();
      const token = tokenResponse?.data || "";
      if (token) {
        setPushToken(token);
        await writeJson(STORAGE_KEYS.pushToken, token);
      }
      return token;
    } catch {
      return "";
    }
  };

  const registerDevice = async (settingsOverride, tokenOverride = "") => {
    const cfg = settingsOverride || settings;
    const metadata = {
      app: "calcie-mobile-v2.1",
      app_open_mode: cfg.appOpenMode,
      poll_seconds: cfg.pollSeconds,
      require_action_approval: !!cfg.requireActionApproval,
      tts_enabled: !!cfg.ttsEnabled,
      announce_inbound: !!cfg.announceInbound,
    };
    const token = tokenOverride || pushToken;
    if (token) metadata.push_token = token;

    await api.registerDevice({
      user_id: cfg.userId,
      device_id: cfg.deviceId,
      device_type: cfg.deviceType,
      label: "CALCIE Mobile V2.1",
      metadata,
    });
  };

  const runSyncTick = async () => {
    try {
      await flushOutbox(api);
      const result = await pollAndExecuteInbound({
        api,
        settings,
        deferHighRisk: !!settings.requireActionApproval,
        onRemoteLog: async (line) => {
          await addLog("remote", line);
        },
        onHighRiskAction: async (action) => {
          await queuePendingAction(action);
        },
      });

      await refreshOutboxCount();
      setStatus("Connected");
      setLastSyncAt(now());

      const count = Number(result?.count || 0);
      if (count > 0 && settings.announceInbound) {
        const message = `${count} command${count > 1 ? "s" : ""} received.`;
        const alerted = await scheduleLocalAlert("CALCIE", message);
        if (!alerted && settings.ttsEnabled) {
          await speakText(message, { rate: 0.96, pitch: 1.0, language: "en-US" });
        }
      }
    } catch {
      setStatus("Offline");
    }
  };

  const handleSend = async () => {
    const raw = input.trim();
    if (!raw || busy) return;

    setBusy(true);
    setInput("");
    await addLog("user", raw);

    try {
      if (settings.requireActionApproval && isHighRiskCommand(raw)) {
        await queuePendingAction({ source: "user", content: raw, createdAt: now() });
        setStatus("Connected");
        setLastSyncAt(now());
        return;
      }

      const result = await sendOrRouteCommand({ api, settings, raw });
      await addLog("assistant", result.message);
      setStatus("Connected");
      setLastSyncAt(now());
    } catch (err) {
      await addLog("assistant", `Send failed: ${err?.message || "unknown"}`);
      setStatus("Offline");
    } finally {
      await refreshOutboxCount();
      setBusy(false);
    }
  };

  const approveAction = async (action) => {
    if (!action) return;
    await removePendingAction(action.id);

    try {
      if (action.source === "remote") {
        const localResult = await executeLocalCommand(action.content, settings);
        await api.addMessage({
          user_id: settings.userId,
          device_id: settings.deviceId,
          role: "assistant",
          content: `[remote-approved:${action.fromDevice || "unknown"}] ${localResult}`,
        });
        await addLog("assistant", `Approved remote action: ${localResult}`);
      } else {
        const result = await sendOrRouteCommand({ api, settings, raw: action.content });
        await addLog("assistant", `Approved action: ${result.message}`);
      }
    } catch (err) {
      await addLog("assistant", `Approval failed: ${err?.message || "unknown"}`);
    } finally {
      await refreshOutboxCount();
    }
  };

  const rejectAction = async (action) => {
    if (!action) return;
    await removePendingAction(action.id);

    const message = `Rejected action: ${action.content}`;
    await addLog("assistant", message);

    if (action.source === "remote") {
      try {
        await api.addMessage({
          user_id: settings.userId,
          device_id: settings.deviceId,
          role: "assistant",
          content: `[remote-rejected:${action.fromDevice || "unknown"}] ${action.content}`,
        });
      } catch {
        // best effort only
      }
    }
  };

  const saveSettings = async () => {
    const next = {
      ...draftSettings,
      pollSeconds: Math.max(2, Number(draftSettings.pollSeconds || 3)),
      appOpenMode: draftSettings.appOpenMode === "app_first" ? "app_first" : "app_only",
      requireActionApproval: toBool(draftSettings.requireActionApproval, true),
      ttsEnabled: toBool(draftSettings.ttsEnabled, true),
      announceInbound: toBool(draftSettings.announceInbound, true),
    };
    setSettings(next);
    await writeJson(STORAGE_KEYS.settings, next);

    try {
      await registerDevice(next);
      await addLog("system", "Settings saved and device metadata updated.");
    } catch {
      await addLog("system", "Settings saved locally (register will retry).");
    }
  };

  const resetSettings = async () => {
    setDraftSettings(DEFAULT_SETTINGS);
    setSettings(DEFAULT_SETTINGS);
    await writeJson(STORAGE_KEYS.settings, DEFAULT_SETTINGS);
    await addLog("system", "Settings reset to defaults.");
  };

  const handleMicHint = async () => {
    inputRef.current?.focus();
    await addLog(
      "system",
      "Voice input tip: tap the microphone button on your mobile keyboard to dictate."
    );
  };

  const handleSpeakLast = async () => {
    if (!lastAssistantText) {
      await addLog("system", "Nothing to read yet.");
      return;
    }
    await speakText(lastAssistantText, { rate: 0.93, pitch: 0.95, language: "en-US" });
  };

  const handleStopVoice = async () => {
    await stopSpeaking();
  };

  useEffect(() => {
    let active = true;

    (async () => {
      const storedSettings = await readJson(STORAGE_KEYS.settings, DEFAULT_SETTINGS);
      const merged = { ...DEFAULT_SETTINGS, ...(storedSettings || {}) };

      if (!active) return;
      setSettings(merged);
      setDraftSettings(merged);

      const savedLogs = await readJson(STORAGE_KEYS.logs, []);
      if (active && Array.isArray(savedLogs)) {
        setLogs(savedLogs);
        const latestAssistant = savedLogs.find((item) => item?.role === "assistant");
        if (latestAssistant?.text) setLastAssistantText(String(latestAssistant.text));
      }

      const savedActions = await readJson(STORAGE_KEYS.pendingActions, []);
      if (active && Array.isArray(savedActions)) {
        setPendingActions(savedActions);
      }

      await refreshOutboxCount();

      const savedToken = await readJson(STORAGE_KEYS.pushToken, "");
      if (savedToken && active) {
        setPushToken(savedToken);
      }

      const token = (await registerPushToken()) || savedToken || "";

      try {
        await registerDevice(merged, token);
        if (active) {
          setStatus("Connected");
          setLastSyncAt(now());
        }
      } catch (err) {
        if (active) {
          setStatus(`Offline (${err?.message || "register failed"})`);
        }
      }
    })();

    return () => {
      active = false;
    };
  }, []);

  useEffect(() => {
    const intervalMs = Math.max(2, Number(settings.pollSeconds || 3)) * 1000;
    const timer = setInterval(() => {
      runSyncTick();
    }, intervalMs);
    return () => clearInterval(timer);
  }, [settings.pollSeconds, settings.apiBaseUrl, settings.userId, settings.deviceId]);

  useEffect(() => {
    const sub = AppState.addEventListener("change", (nextState) => {
      if (nextState === "active") {
        runSyncTick();
      }
    });
    return () => sub.remove();
  }, [settings.pollSeconds, settings.apiBaseUrl, settings.userId, settings.deviceId]);

  const header = useMemo(() => {
    const sync = lastSyncAt ? ` • Last sync ${lastSyncAt.slice(11, 19)}` : "";
    return `CALCIE Mobile V2.1 • ${status}${sync}`;
  }, [status, lastSyncAt]);

  const renderPendingActions = () => {
    if (!pendingActions.length) return null;
    return (
      <View style={styles.pendingWrap}>
        <Text style={styles.pendingTitle}>Action Cards ({pendingActions.length})</Text>
        {pendingActions.map((action) => (
          <View key={action.id} style={styles.actionCard}>
            <Text style={styles.actionMeta}>
              {action.source === "remote"
                ? `From ${action.fromDevice || "remote device"}`
                : "From this device"}
            </Text>
            <Text style={styles.actionText}>{action.content}</Text>
            <View style={styles.actionRow}>
              <TouchableOpacity style={styles.approveBtn} onPress={() => approveAction(action)}>
                <Text style={styles.actionBtnText}>Approve</Text>
              </TouchableOpacity>
              <TouchableOpacity style={styles.rejectBtn} onPress={() => rejectAction(action)}>
                <Text style={styles.actionBtnText}>Reject</Text>
              </TouchableOpacity>
            </View>
          </View>
        ))}
      </View>
    );
  };

  const renderChat = () => (
    <>
      <View style={styles.metricsRow}>
        <Text style={styles.metric}>Outbox: {outboxCount}</Text>
        <TouchableOpacity style={styles.smallBtn} onPress={runSyncTick}>
          <Text style={styles.smallBtnText}>Sync now</Text>
        </TouchableOpacity>
      </View>

      {renderPendingActions()}

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

      <View style={styles.voiceRow}>
        <TouchableOpacity style={styles.smallBtn} onPress={handleMicHint}>
          <Text style={styles.smallBtnText}>Mic</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.smallBtn} onPress={handleSpeakLast}>
          <Text style={styles.smallBtnText}>Speak Last</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.smallBtn} onPress={handleStopVoice}>
          <Text style={styles.smallBtnText}>Stop Voice</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.inputRow}>
        <TextInput
          ref={inputRef}
          style={styles.input}
          value={input}
          onChangeText={setInput}
          placeholder="Type: open whatsapp on mobile"
          placeholderTextColor="#7f8894"
          multiline
        />
        <TouchableOpacity style={styles.btn} onPress={handleSend}>
          <Text style={styles.btnText}>{busy ? "..." : "Send"}</Text>
        </TouchableOpacity>
      </View>
    </>
  );

  const renderToggleRow = (label, value, onToggle) => (
    <View style={styles.toggleRow}>
      <Text style={styles.settingLabel}>{label}</Text>
      <TouchableOpacity style={styles.smallBtn} onPress={onToggle}>
        <Text style={styles.smallBtnText}>{value ? "ON" : "OFF"}</Text>
      </TouchableOpacity>
    </View>
  );

  const renderSettings = () => (
    <View style={styles.settingsWrap}>
      <Text style={styles.settingLabel}>API Base URL</Text>
      <TextInput
        style={styles.settingInput}
        value={draftSettings.apiBaseUrl}
        onChangeText={(v) => setDraftSettings((s) => ({ ...s, apiBaseUrl: v }))}
      />

      <Text style={styles.settingLabel}>User ID</Text>
      <TextInput
        style={styles.settingInput}
        value={draftSettings.userId}
        onChangeText={(v) => setDraftSettings((s) => ({ ...s, userId: v }))}
      />

      <Text style={styles.settingLabel}>Device ID</Text>
      <TextInput
        style={styles.settingInput}
        value={draftSettings.deviceId}
        onChangeText={(v) => setDraftSettings((s) => ({ ...s, deviceId: v }))}
      />

      <Text style={styles.settingLabel}>Laptop Device ID</Text>
      <TextInput
        style={styles.settingInput}
        value={draftSettings.laptopDeviceId}
        onChangeText={(v) => setDraftSettings((s) => ({ ...s, laptopDeviceId: v }))}
      />

      <Text style={styles.settingLabel}>App Open Mode (`app_only` or `app_first`)</Text>
      <TextInput
        style={styles.settingInput}
        value={draftSettings.appOpenMode}
        onChangeText={(v) => setDraftSettings((s) => ({ ...s, appOpenMode: v }))}
      />

      <Text style={styles.settingLabel}>Poll Seconds (min 2)</Text>
      <TextInput
        style={styles.settingInput}
        value={String(draftSettings.pollSeconds)}
        keyboardType="numeric"
        onChangeText={(v) => setDraftSettings((s) => ({ ...s, pollSeconds: v }))}
      />

      {renderToggleRow(
        "Require Approval For High-Risk Actions",
        !!draftSettings.requireActionApproval,
        () =>
          setDraftSettings((s) => ({
            ...s,
            requireActionApproval: !toBool(s.requireActionApproval, true),
          }))
      )}

      {renderToggleRow("Voice Output (TTS)", !!draftSettings.ttsEnabled, () =>
        setDraftSettings((s) => ({ ...s, ttsEnabled: !toBool(s.ttsEnabled, true) }))
      )}

      {renderToggleRow("Inbound Alerts", !!draftSettings.announceInbound, () =>
        setDraftSettings((s) => ({ ...s, announceInbound: !toBool(s.announceInbound, true) }))
      )}

      <Text style={styles.subtle}>Push token: {pushToken ? "available" : "not granted"}</Text>

      <View style={styles.settingsBtnRow}>
        <TouchableOpacity style={styles.smallBtn} onPress={saveSettings}>
          <Text style={styles.smallBtnText}>Save</Text>
        </TouchableOpacity>
        <TouchableOpacity style={styles.smallBtn} onPress={resetSettings}>
          <Text style={styles.smallBtnText}>Reset</Text>
        </TouchableOpacity>
      </View>
    </View>
  );

  return (
    <SafeAreaView style={styles.root}>
      <Text style={styles.title}>{header}</Text>
      <Text style={styles.sub}>Device: {settings.deviceId} • User: {settings.userId}</Text>

      <View style={styles.tabs}>
        <TouchableOpacity
          style={[styles.tab, screen === "chat" && styles.tabActive]}
          onPress={() => setScreen("chat")}
        >
          <Text style={styles.tabText}>Chat</Text>
        </TouchableOpacity>
        <TouchableOpacity
          style={[styles.tab, screen === "settings" && styles.tabActive]}
          onPress={() => setScreen("settings")}
        >
          <Text style={styles.tabText}>Settings</Text>
        </TouchableOpacity>
      </View>

      {screen === "chat" ? renderChat() : renderSettings()}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: "#0b1118", padding: 14 },
  title: { color: "#d5e3f3", fontSize: 18, fontWeight: "700" },
  sub: { color: "#93a4b8", marginTop: 4, marginBottom: 8, fontSize: 12 },

  tabs: { flexDirection: "row", gap: 8, marginBottom: 10 },
  tab: {
    paddingVertical: 8,
    paddingHorizontal: 14,
    borderRadius: 10,
    backgroundColor: "#121e2d",
    borderWidth: 1,
    borderColor: "#2a3f58",
  },
  tabActive: { backgroundColor: "#213850", borderColor: "#36638d" },
  tabText: { color: "#e7edf5", fontWeight: "700" },

  metricsRow: { flexDirection: "row", justifyContent: "space-between", marginBottom: 8 },
  metric: { color: "#98aac0", fontSize: 12 },

  pendingWrap: {
    backgroundColor: "#151f2b",
    borderColor: "#2a3f58",
    borderWidth: 1,
    borderRadius: 10,
    padding: 10,
    marginBottom: 10,
    maxHeight: 220,
  },
  pendingTitle: { color: "#f6d57a", fontWeight: "700", marginBottom: 8 },
  actionCard: {
    borderWidth: 1,
    borderColor: "#3c5068",
    borderRadius: 10,
    padding: 8,
    marginBottom: 8,
    backgroundColor: "#101820",
  },
  actionMeta: { color: "#9ab3ce", fontSize: 11, marginBottom: 4 },
  actionText: { color: "#e7edf5", fontSize: 13, marginBottom: 8 },
  actionRow: { flexDirection: "row", gap: 8 },
  approveBtn: {
    backgroundColor: "#2f7d4c",
    borderRadius: 8,
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  rejectBtn: {
    backgroundColor: "#86343a",
    borderRadius: 8,
    paddingVertical: 6,
    paddingHorizontal: 10,
  },
  actionBtnText: { color: "#fff", fontWeight: "700", fontSize: 12 },

  list: { flex: 1 },
  msg: { padding: 10, borderRadius: 10, marginBottom: 8, borderWidth: 1 },
  msgUser: { backgroundColor: "#172437", borderColor: "#27405f" },
  msgOther: { backgroundColor: "#101820", borderColor: "#233140" },
  msgRole: { color: "#8db5df", fontSize: 11, marginBottom: 4 },
  msgText: { color: "#e7edf5", fontSize: 14 },

  voiceRow: { flexDirection: "row", gap: 8, marginTop: 8, marginBottom: 8 },
  inputRow: { flexDirection: "row", gap: 8, marginTop: 2 },
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

  settingsWrap: { flex: 1 },
  settingLabel: { color: "#b9cbdf", marginTop: 10, marginBottom: 4, fontSize: 12 },
  settingInput: {
    backgroundColor: "#121e2d",
    color: "#e7edf5",
    borderRadius: 10,
    paddingHorizontal: 10,
    paddingVertical: 8,
    borderWidth: 1,
    borderColor: "#2a3f58",
  },
  toggleRow: {
    marginTop: 10,
    flexDirection: "row",
    justifyContent: "space-between",
    alignItems: "center",
  },
  subtle: { color: "#8196ad", marginTop: 10, fontSize: 12 },
  settingsBtnRow: { flexDirection: "row", gap: 8, marginTop: 14 },

  smallBtn: {
    backgroundColor: "#2a4f78",
    paddingVertical: 8,
    paddingHorizontal: 12,
    borderRadius: 10,
  },
  smallBtnText: { color: "#eaf3ff", fontWeight: "700", fontSize: 12 },
});
