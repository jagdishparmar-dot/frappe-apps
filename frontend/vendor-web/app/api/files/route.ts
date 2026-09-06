import { NextResponse } from "next/server";
import { getFrappeConfig } from "@/lib/config";
import { getSession } from "@/lib/session";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const path = searchParams.get("path");
  if (!path || !path.startsWith("/")) {
    return NextResponse.json({ error: "Invalid path" }, { status: 400 });
  }

  const session = await getSession();
  if (!session?.sid) {
    return NextResponse.json({ error: "Unauthorized" }, { status: 401 });
  }

  const { url, site } = getFrappeConfig();
  const res = await fetch(`${url}${path}`, {
    headers: {
      Cookie: `sid=${session.sid}`,
      ...(site ? { "X-Frappe-Site-Name": site } : {}),
    },
    cache: "no-store",
  });

  if (!res.ok) {
    return NextResponse.json({ error: "File not found" }, { status: res.status });
  }

  const contentType = res.headers.get("content-type") || "application/octet-stream";
  const buffer = await res.arrayBuffer();
  return new NextResponse(buffer, {
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "private, max-age=60",
    },
  });
}
