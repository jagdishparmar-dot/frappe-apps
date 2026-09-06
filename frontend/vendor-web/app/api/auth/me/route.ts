import { NextResponse } from "next/server";
import { getSession } from "@/lib/session";
import { getLoggedUser } from "@/lib/frappe";

export async function GET() {
  const session = await getSession();
  if (!session) {
    return NextResponse.json({ authenticated: false }, { status: 401 });
  }
  const user = (await getLoggedUser()) || session.user || null;
  if (!user || user === "Guest") {
    return NextResponse.json({ authenticated: false }, { status: 401 });
  }
  return NextResponse.json({ authenticated: true, user });
}
