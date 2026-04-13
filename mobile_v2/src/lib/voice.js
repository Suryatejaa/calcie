let speechModule = null;

async function loadSpeechModule() {
  if (speechModule) return speechModule;
  try {
    const mod = await import("expo-speech");
    speechModule = mod;
    return speechModule;
  } catch {
    return null;
  }
}

export async function speakText(text, options = {}) {
  const value = String(text || "").trim();
  if (!value) return false;

  const module = await loadSpeechModule();
  if (!module || typeof module.speak !== "function") return false;

  const rate = Number(options.rate || 0.95);
  const pitch = Number(options.pitch || 1.0);
  const language = String(options.language || "en-US");

  module.speak(value, { rate, pitch, language });
  return true;
}

export async function stopSpeaking() {
  const module = await loadSpeechModule();
  if (!module || typeof module.stop !== "function") return false;
  module.stop();
  return true;
}
