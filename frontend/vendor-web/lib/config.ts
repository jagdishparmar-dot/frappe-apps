import { existsSync, readFileSync } from "fs";

type SiteFile = {
  FRAPPE_URL?: string;
  FRAPPE_SITE_NAME?: string;
};

let cached: SiteFile | null | undefined;

function loadSiteFile(): SiteFile | null {
  if (cached !== undefined) return cached;
  const path = process.env.CREDENTIALS_FILE || "";
  if (!path || !existsSync(path)) {
    cached = null;
    return cached;
  }
  try {
    cached = JSON.parse(readFileSync(path, "utf8")) as SiteFile;
  } catch {
    cached = null;
  }
  return cached;
}

/** Site connection only — UI auth uses Frappe login sessions, not API keys. */
export function getFrappeConfig() {
  const file = loadSiteFile();
  const url = (process.env.FRAPPE_URL || file?.FRAPPE_URL || "").replace(/\/$/, "");
  if (!url) {
    throw new Error("FRAPPE_URL is not set");
  }
  return {
    url,
    site: process.env.FRAPPE_SITE_NAME || file?.FRAPPE_SITE_NAME || "vendors.localhost",
  };
}
