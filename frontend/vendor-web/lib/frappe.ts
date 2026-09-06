import { getFrappeConfig } from "./config";
import { getSession, parseSetCookieHeaders, extractCookieValue } from "./session";
import type { ProfileUpdate, VendorProfile } from "./types";

function siteHeaders(): Record<string, string> {
  const { site } = getFrappeConfig();
  const headers: Record<string, string> = {
    Accept: "application/json",
  };
  if (site) headers["X-Frappe-Site-Name"] = site;
  return headers;
}

async function sessionHeaders(json = true): Promise<Record<string, string>> {
  const session = await getSession();
  if (!session?.sid) {
    throw new Error("Please sign in to continue.");
  }
  const headers = siteHeaders();
  headers.Cookie = `sid=${session.sid}`;
  if (json) headers["Content-Type"] = "application/json";
  if (session.csrf) headers["X-Frappe-CSRF-Token"] = session.csrf;
  return headers;
}

async function frappeFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const { url } = getFrappeConfig();
  const wantsJson = !(init?.body instanceof FormData);
  const res = await fetch(`${url}${path}`, {
    ...init,
    headers: {
      ...(await sessionHeaders(wantsJson)),
      ...(init?.headers || {}),
    },
    cache: "no-store",
  });

  const body = await res.json().catch(() => ({}));
  if (res.status === 401 || res.status === 403) {
    throw new Error("Session expired — please sign in again.");
  }
  if (!res.ok) {
    const message =
      body?.exception ||
      body?.message ||
      body?._server_messages ||
      `Request failed (${res.status})`;
    throw new Error(typeof message === "string" ? message : JSON.stringify(message));
  }
  return body as T;
}

async function callMethod<T>(method: string, args?: Record<string, unknown>): Promise<T> {
  const qs = args
    ? "?" +
      Object.entries(args)
        .map(([k, v]) => `${encodeURIComponent(k)}=${encodeURIComponent(JSON.stringify(v))}`)
        .join("&")
    : "";

  // Prefer POST body for mutations
  if (args && Object.keys(args).length) {
    const data = await frappeFetch<{ message: T }>(`/api/method/${method}`, {
      method: "POST",
      body: JSON.stringify(args),
    });
    return data.message;
  }
  const data = await frappeFetch<{ message: T }>(`/api/method/${method}${qs}`);
  return data.message;
}

export async function getMyVendor(): Promise<VendorProfile> {
  return callMethod<VendorProfile>("vendor_directory.api.portal.get_my_vendor");
}

export async function updateMyVendor(data: ProfileUpdate): Promise<VendorProfile> {
  return callMethod<VendorProfile>("vendor_directory.api.portal.update_my_vendor", { data });
}

export async function submitForKycReview(): Promise<VendorProfile> {
  return callMethod<VendorProfile>("vendor_directory.api.portal.submit_for_kyc_review");
}

export async function uploadKycDocument(params: {
  document_type: string;
  file_url: string;
  vendor_remarks?: string;
}): Promise<VendorProfile> {
  return callMethod<VendorProfile>("vendor_directory.api.portal.upload_kyc_document", params);
}

/** Upload a file to Frappe, return the file_url. */
export async function uploadFile(file: File, folder = "Home/Vendors"): Promise<string> {
  const { url } = getFrappeConfig();
  const session = await getSession();
  if (!session?.sid) throw new Error("Please sign in to continue.");

  const form = new FormData();
  form.append("file", file, file.name);
  form.append("is_private", "1");
  form.append("folder", folder);
  form.append("doctype", "Vendor");

  const res = await fetch(`${url}/api/method/upload_file`, {
    method: "POST",
    headers: {
      ...siteHeaders(),
      Cookie: `sid=${session.sid}`,
      ...(session.csrf ? { "X-Frappe-CSRF-Token": session.csrf } : {}),
    },
    body: form,
    cache: "no-store",
  });

  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.message || body?.exception || "File upload failed");
  }
  const fileUrl = body?.message?.file_url || body?.file_url;
  if (!fileUrl) throw new Error("Upload succeeded but no file URL was returned.");
  return fileUrl as string;
}

export type LoginResult = {
  message?: string;
  sid: string;
  csrf?: string;
  user: string;
};

async function tryExtractCsrf(url: string, sid: string): Promise<string | undefined> {
  try {
    const res = await fetch(`${url}/app`, {
      headers: {
        ...siteHeaders(),
        Accept: "text/html",
        Cookie: `sid=${sid}`,
      },
      cache: "no-store",
    });
    const html = await res.text();
    const match = html.match(/csrf_token["']?\s*[:=]\s*["']([^"']+)/);
    return match?.[1];
  } catch {
    return undefined;
  }
}

export async function loginToFrappe(usr: string, pwd: string): Promise<LoginResult> {
  const { url } = getFrappeConfig();
  const res = await fetch(`${url}/api/method/login`, {
    method: "POST",
    headers: { ...siteHeaders(), "Content-Type": "application/json" },
    body: JSON.stringify({ usr, pwd }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body?.message || "Login failed");
  }

  const setCookies = parseSetCookieHeaders(res.headers);
  const sid = extractCookieValue(setCookies, "sid");
  if (!sid) {
    throw new Error("Login succeeded but no session cookie was returned.");
  }

  const csrf = await tryExtractCsrf(url, sid);
  const user =
    body?.full_name ||
    extractCookieValue(setCookies, "user_id") ||
    usr;

  return {
    message: body?.message || "Logged In",
    sid,
    csrf,
    user: String(user),
  };
}

export async function logoutFromFrappe() {
  const { url } = getFrappeConfig();
  const session = await getSession();
  if (!session?.sid) return;
  await fetch(`${url}/api/method/logout`, {
    method: "POST",
    headers: {
      ...siteHeaders(),
      "Content-Type": "application/json",
      Cookie: `sid=${session.sid}`,
      ...(session.csrf ? { "X-Frappe-CSRF-Token": session.csrf } : {}),
    },
    cache: "no-store",
  }).catch(() => undefined);
}

export async function getLoggedUser(): Promise<string | null> {
  try {
    const data = await frappeFetch<{ message: string }>(
      "/api/method/frappe.auth.get_logged_user"
    );
    return data.message || null;
  } catch {
    return null;
  }
}

export function filePublicUrl(fileUrl: string): string {
  if (!fileUrl) return "";
  if (fileUrl.startsWith("http")) return fileUrl;
  const { url } = getFrappeConfig();
  return `${url}${fileUrl.startsWith("/") ? "" : "/"}${fileUrl}`;
}
