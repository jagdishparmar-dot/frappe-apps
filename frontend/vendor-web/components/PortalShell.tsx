import Link from "next/link";
import { getSession } from "@/lib/session";
import { LogoutButton } from "@/components/LogoutButton";

const NAV = [
  { href: "/", label: "Dashboard" },
  { href: "/profile", label: "My Profile" },
  { href: "/documents", label: "KYC Documents" },
];

export async function PortalShell({
  children,
  pathname,
}: {
  children: React.ReactNode;
  pathname?: string;
}) {
  const session = await getSession();

  return (
    <div className="portal-shell">
      <aside className="portal-sidebar">
        <div>
          <div className="portal-brand">Vendor Portal</div>
          <p className="muted" style={{ color: "rgba(232,242,236,0.65)", margin: "0.35rem 0.6rem 0", fontSize: "0.85rem" }}>
            Manage your profile & KYC
          </p>
        </div>
        <nav className="portal-nav">
          {NAV.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className={pathname === item.href ? "active" : undefined}
            >
              {item.label}
            </Link>
          ))}
        </nav>
        <div style={{ marginTop: "auto", padding: "0.6rem" }}>
          <div style={{ fontSize: "0.85rem", opacity: 0.8, marginBottom: "0.65rem" }}>
            {session?.user || "Vendor"}
          </div>
          <LogoutButton />
        </div>
      </aside>
      <div className="portal-main">{children}</div>
    </div>
  );
}
