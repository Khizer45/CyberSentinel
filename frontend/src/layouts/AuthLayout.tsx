import type { ReactNode } from "react";
import { BrandMark } from "../components/Icon";

export function AuthLayout({ children }: { children: ReactNode }) {
  return (
    <div className="auth-layout">
      <section className="auth-hero" aria-hidden="true">
        <div className="row" style={{ gap: 12, color: "#ffffff", fontWeight: 700, fontSize: "1.1rem" }}>
          <BrandMark /> CyberSentinel
        </div>
        <div className="stack">
          <h1>Machine-learning threat detection for network flow data.</h1>
          <p>
            Upload CICIDS2017 or UNSW-NB15 flow records, run approved models, and triage prioritised alerts with explanations — every
            decision recorded in an append-only audit trail.
          </p>
          <ul>
            <li>Supervised classification and anomaly detection</li>
            <li>Versioned risk policy with transparent score breakdowns</li>
            <li>Role-based access for administrators, analysts and viewers</li>
          </ul>
        </div>
        <p className="small" style={{ color: "#8d9ab4" }}>
          Model outputs are decision support, not proof of compromise.
        </p>
      </section>
      <main className="auth-panel">{children}</main>
    </div>
  );
}
