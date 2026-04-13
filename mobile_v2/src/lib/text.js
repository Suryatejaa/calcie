export function normalize(input) {
  return String(input || "")
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function stripTargetPhrase(text) {
  let out = String(text || "").trim();
  out = out.replace(/\b(?:on|in|to)\s+(?:my\s+)?(?:mobile|phone|android)\b/gi, " ");
  out = out.replace(/\b(?:on|in|to)\s+(?:my\s+)?(?:laptop|desktop|mac|pc)\b/gi, " ");
  out = out.replace(/\s+/g, " ").trim();
  return out || text;
}

export function targetsLaptop(text) {
  return /\b(?:on|in|to)\s+(?:my\s+)?(?:laptop|desktop|mac|pc)\b/i.test(String(text || ""));
}

export function targetsMobile(text) {
  return /\b(?:on|in|to)\s+(?:my\s+)?(?:mobile|phone|android)\b/i.test(String(text || ""));
}
