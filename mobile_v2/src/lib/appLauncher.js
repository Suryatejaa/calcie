import { Linking } from "react-native";
import { normalize } from "./text";

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

async function tryOpenUrls(urls = []) {
  for (const url of urls) {
    if (!url) continue;
    try {
      await Linking.openURL(url);
      return url;
    } catch {
      // try next
    }
  }
  return "";
}

export async function openKnownApp(target, appOpenMode = "app_only") {
  const norm = normalize(target);
  if (!norm) return "";

  for (const route of APP_ROUTES) {
    if (!route.regex.test(norm)) continue;

    const candidates = [...(route.appUrls || [])];
    if (route.packageName) {
      candidates.push(androidIntentForPackage(route.packageName));
    }

    const opened = await tryOpenUrls(candidates);
    if (opened) return `Opened ${route.name} app.`;

    if (route.packageName) {
      const openedStore = await tryOpenUrls([`market://details?id=${route.packageName}`]);
      if (openedStore) {
        return `Opened Play Store for ${route.name} (app may not be installed).`;
      }
    }

    if (appOpenMode === "app_first" && route.fallbackUrl) {
      await Linking.openURL(route.fallbackUrl);
      return `Opened ${route.name} in browser (app launch unavailable).`;
    }
    return `Couldn't open ${route.name} app on this device.`;
  }

  return "";
}

export async function openMusic(command) {
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

export async function openWebTarget(target) {
  const norm = normalize(target);
  let url = "";

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
