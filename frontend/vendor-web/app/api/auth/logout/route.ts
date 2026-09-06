import { NextResponse } from "next/server";
import { logoutFromFrappe } from "@/lib/frappe";
import { SID_COOKIE, CSRF_COOKIE, USER_COOKIE } from "@/lib/session";

export async function POST() {
  try {
    await logoutFromFrappe();
  } catch {
    // clear local cookies even if Frappe logout fails
  }
  const response = NextResponse.json({ ok: true });
  response.cookies.set(SID_COOKIE, "", { path: "/", maxAge: 0 });
  response.cookies.set(CSRF_COOKIE, "", { path: "/", maxAge: 0 });
  response.cookies.set(USER_COOKIE, "", { path: "/", maxAge: 0 });
  return response;
}
