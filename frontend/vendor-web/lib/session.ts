import { cookies } from "next/headers";

export const SID_COOKIE = "frappe_sid";
export const CSRF_COOKIE = "frappe_csrf";
export const USER_COOKIE = "frappe_user";

export type SessionCookies = {
  sid: string;
  csrf?: string;
  user?: string;
};

export async function getSession(): Promise<SessionCookies | null> {
  const jar = await cookies();
  const sid = jar.get(SID_COOKIE)?.value;
  if (!sid) return null;
  return {
    sid,
    csrf: jar.get(CSRF_COOKIE)?.value,
    user: jar.get(USER_COOKIE)?.value,
  };
}

export async function requireSession(): Promise<SessionCookies> {
  const session = await getSession();
  if (!session) {
    throw new Error("Not authenticated");
  }
  return session;
}

export function parseSetCookieHeaders(headers: Headers): string[] {
  const anyHeaders = headers as Headers & { getSetCookie?: () => string[] };
  if (typeof anyHeaders.getSetCookie === "function") {
    return anyHeaders.getSetCookie();
  }
  const single = headers.get("set-cookie");
  return single ? [single] : [];
}

export function extractCookieValue(setCookieHeaders: string[], name: string): string | null {
  for (const header of setCookieHeaders) {
    const match = header.match(new RegExp(`(?:^|,\\s*)${name}=([^;]+)`));
    if (match?.[1]) return decodeURIComponent(match[1]);
  }
  // Also handle plain "sid=..." first pair
  for (const header of setCookieHeaders) {
    const first = header.split(";")[0]?.trim();
    if (first?.startsWith(`${name}=`)) {
      return decodeURIComponent(first.slice(name.length + 1));
    }
  }
  return null;
}

export function sessionCookieOptions(maxAge = 60 * 60 * 24 * 7) {
  // Local docker serves HTTP — only mark Secure when explicitly enabled (HTTPS).
  const secure = process.env.COOKIE_SECURE === "true";
  return {
    httpOnly: true,
    sameSite: "lax" as const,
    path: "/",
    secure,
    maxAge,
  };
}
