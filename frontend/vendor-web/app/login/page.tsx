import { Suspense } from "react";
import LoginPage from "./LoginClient";

export default function Page() {
  return (
    <Suspense fallback={<div className="container">Loading…</div>}>
      <LoginPage />
    </Suspense>
  );
}
