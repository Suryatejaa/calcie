import { openKnownApp, openMusic, openWebTarget } from "../lib/appLauncher";
import { normalize, stripTargetPhrase, targetsLaptop } from "../lib/text";
import { readJson, writeJson } from "../lib/storage";
import { STORAGE_KEYS } from "../config";

const HIGH_RISK_PATTERNS = [
  /\border\b/i,
  /\bbuy\b/i,
  /\bpurchase\b/i,
  /\bcheckout\b/i,
  /\bpay\b/i,
  /\bpayment\b/i,
  /\btransfer\b/i,
  /\bsend money\b/i,
  /\bwire\b/i,
  /\bdelete\b/i,
  /\bremove\b/i,
  /\breset\b/i,
  /\bformat\b/i,
  /\buninstall\b/i,
];

function nowIso() {
  return new Date().toISOString();
}

export function isHighRiskCommand(text) {
  const value = String(text || "").trim();
  if (!value) return false;
  return HIGH_RISK_PATTERNS.some((pattern) => pattern.test(value));
}

export async function enqueueOutboxItem(item) {
  const queue = await readJson(STORAGE_KEYS.outbox, []);
  queue.push({ ...item, enqueuedAt: nowIso() });
  await writeJson(STORAGE_KEYS.outbox, queue);
  return queue.length;
}

export async function flushOutbox(api) {
  const queue = await readJson(STORAGE_KEYS.outbox, []);
  if (!queue.length) return { sent: 0, remaining: 0 };

  const remaining = [];
  let sent = 0;

  for (const item of queue) {
    try {
      if (item.kind === "message") {
        await api.addMessage(item.payload);
      } else if (item.kind === "command") {
        await api.createCommand(item.payload);
      } else {
        remaining.push(item);
        continue;
      }
      sent += 1;
    } catch {
      remaining.push(item);
    }
  }

  await writeJson(STORAGE_KEYS.outbox, remaining);
  return { sent, remaining: remaining.length };
}

export async function executeLocalCommand(command, settings) {
  const raw = String(command || "").trim();
  const norm = normalize(raw);

  if (norm.startsWith("play ") || norm === "play" || norm.includes("play music")) {
    return await openMusic(raw);
  }

  if (norm.startsWith("open ") || norm.startsWith("launch ") || norm.startsWith("start ")) {
    const m = raw.match(/^(?:open|launch|start)\s+(.+)$/i);
    const target = stripTargetPhrase(m ? m[1] : raw);

    if (!target) return "No target found.";

    const forceBrowser = /\b(in|on)\s+(?:google\s+)?chrome\b|\bbrowser\b|\bweb\b/i.test(raw);
    if (!forceBrowser) {
      const appResult = await openKnownApp(target, settings.appOpenMode);
      if (appResult) return appResult;
    }

    return await openWebTarget(target);
  }

  if (norm.startsWith("search ")) {
    const q = raw.replace(/^search\s*/i, "").trim();
    if (!q) return "No search query provided.";
    return await openWebTarget(`https://www.google.com/search?q=${encodeURIComponent(q)}`);
  }

  return "V2 supports open/play/search. More skills can be attached next.";
}

export async function sendOrRouteCommand({ api, settings, raw }) {
  const text = String(raw || "").trim();
  if (!text) return { ok: false, message: "Empty input." };

  const userPayload = {
    user_id: settings.userId,
    device_id: settings.deviceId,
    role: "user",
    content: text,
  };

  try {
    await api.addMessage(userPayload);
  } catch {
    await enqueueOutboxItem({ kind: "message", payload: userPayload });
  }

  if (targetsLaptop(text)) {
    const cleaned = stripTargetPhrase(text);
    const commandPayload = {
      user_id: settings.userId,
      from_device: settings.deviceId,
      target_device: settings.laptopDeviceId,
      content: cleaned,
      requires_confirm: false,
    };

    try {
      await api.createCommand(commandPayload);
    } catch {
      await enqueueOutboxItem({ kind: "command", payload: commandPayload });
    }

    const result = `Routed to laptop: ${cleaned}`;
    try {
      await api.addMessage({
        user_id: settings.userId,
        device_id: settings.deviceId,
        role: "assistant",
        content: result,
      });
    } catch {
      await enqueueOutboxItem({
        kind: "message",
        payload: {
          user_id: settings.userId,
          device_id: settings.deviceId,
          role: "assistant",
          content: result,
        },
      });
    }

    return { ok: true, message: result };
  }

  const localResult = await executeLocalCommand(text, settings);

  try {
    await api.addMessage({
      user_id: settings.userId,
      device_id: settings.deviceId,
      role: "assistant",
      content: localResult,
    });
  } catch {
    await enqueueOutboxItem({
      kind: "message",
      payload: {
        user_id: settings.userId,
        device_id: settings.deviceId,
        role: "assistant",
        content: localResult,
      },
    });
  }

  return { ok: true, message: localResult };
}

export async function pollAndExecuteInbound({
  api,
  settings,
  onRemoteLog,
  onHighRiskAction,
  deferHighRisk = false,
}) {
  const data = await api.pollCommands({
    userId: settings.userId,
    deviceId: settings.deviceId,
    limit: 12,
  });

  const commands = data.commands || [];
  let executed = 0;
  let deferred = 0;

  for (const cmd of commands) {
    const content = String(cmd.content || "");
    const commandId = Number(cmd.id || 0);
    if (!content || !commandId) continue;

    if (onRemoteLog) onRemoteLog(`From ${cmd.from_device}: ${content}`);

    if (deferHighRisk && isHighRiskCommand(content)) {
      deferred += 1;
      if (onHighRiskAction) {
        onHighRiskAction({
          id: `remote-${commandId}-${Date.now()}`,
          source: "remote",
          fromDevice: String(cmd.from_device || ""),
          commandId,
          content,
          createdAt: nowIso(),
        });
      }
      await api.ackCommand(commandId, {
        status: "skipped",
        result: "Deferred for local approval in mobile_v2.1 action card.",
      });
      continue;
    }

    let status = "done";
    let result = "";
    try {
      result = await executeLocalCommand(content, settings);
      executed += 1;
      await api.addMessage({
        user_id: settings.userId,
        device_id: settings.deviceId,
        role: "assistant",
        content: `[remote:${cmd.from_device}] ${result}`,
      });
    } catch (err) {
      status = "failed";
      result = `Remote command failed: ${err?.message || "unknown"}`;
    }

    await api.ackCommand(commandId, { status, result });
  }

  return { executed, deferred, count: commands.length };
}
