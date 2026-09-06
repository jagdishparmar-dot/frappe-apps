import { NextResponse } from "next/server";
import { loginToFrappe } from "@/lib/frappe";
import {
  SID_COOKIE,
  CSRF_COOKIE,
  USER_COOKIE,
  sessionCookieOptions,
} from "@/lib/session";

export async function POST(request: Request) {
  try {
    const { usr, pwd } = await request.json();
    if (!usr || !pwd) {
      return NextResponse.json({ error: "Username and password required" }, { status: 400 });
    }

    const result = await loginToFrappe(usr, pwd);
    const response = NextResponse.json({
      ok: true,
      message: result.message,
      user: result.user,
    });

    const opts = sessionCookieOptions();
    response.cookies.set(SID_COOKIE, result.sid, opts);
    if (result.csrf) {
      response.cookies.set(CSRF_COOKIE, result.csrf, opts);
    }
    response.cookies.set(USER_COOKIE, result.user, { ...opts, httpOnly: false });

    return response;
  } catch (err) {
    return NextResponse.json(
      { error: err instanceof Error ? err.message : "Login failed" },
      { status: 401 }
    );
  }
}
