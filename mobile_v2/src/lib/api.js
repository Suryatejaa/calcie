export class SyncApi {
  constructor(baseUrl) {
    this.baseUrl = String(baseUrl || "").replace(/\/$/, "");
  }

  async request(path, options = {}) {
    const res = await fetch(`${this.baseUrl}${path}`, {
      headers: { "Content-Type": "application/json" },
      ...options,
    });
    if (!res.ok) {
      const body = await res.text();
      throw new Error(`HTTP ${res.status}: ${body}`);
    }
    return await res.json();
  }

  async health() {
    return await this.request("/health");
  }

  async registerDevice(payload) {
    return await this.request("/devices/register", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async addMessage(payload) {
    return await this.request("/messages", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async createCommand(payload) {
    return await this.request("/commands", {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }

  async pollCommands({ userId, deviceId, limit = 10 }) {
    const q =
      `/commands/poll?user_id=${encodeURIComponent(userId)}` +
      `&device_id=${encodeURIComponent(deviceId)}&limit=${encodeURIComponent(limit)}`;
    return await this.request(q);
  }

  async ackCommand(commandId, payload) {
    return await this.request(`/commands/${commandId}/ack`, {
      method: "POST",
      body: JSON.stringify(payload),
    });
  }
}
