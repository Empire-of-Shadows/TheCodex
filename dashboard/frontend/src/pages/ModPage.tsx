import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { api } from "../api/client";
import type { User } from "../api/types";
import AppHeader from "../components/AppHeader";

const TEASERS: { icon: string; title: string; desc: string; accent: string }[] = [
  { icon: "🛡️", title: "Quick Actions", desc: "Warn, mute, and timeout from one panel.", accent: "var(--brand)" },
  { icon: "📜", title: "Mod Log", desc: "A searchable trail of every moderation action.", accent: "var(--success)" },
  { icon: "🔎", title: "Word Filters", desc: "Tune the filters your mod role can manage.", accent: "var(--warning)" },
];

export default function ModPage() {
  const [user, setUser] = useState<User | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    api.me().then(setUser).catch(() => {});
  }, []);

  useEffect(() => {
    if (user && !user.can_access_mod_any) navigate("/dashboard", { replace: true });
  }, [user, navigate]);

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <section className="dash-hero">
        <div className="dash-hero__orb" />
        <div className="mod-construction__sigil" aria-hidden>
          <span className="mod-construction__ring" />
          <img src="/brand/logo-mark.png" alt="" />
        </div>
        <div className="dash-hero__copy">
          <span className="dash-hero__eyebrow">Moderation</span>
          <h1 className="dash-hero__title">Mod tools are being forged</h1>
          <p className="dash-hero__sub">
            This wing of the dashboard is under construction. Moderation features for
            your role are on the way.
          </p>
          <div
            className="mod-construction__bar"
            role="progressbar"
            aria-label="Under construction"
          >
            <span />
          </div>
        </div>
      </section>

      <div style={{ padding: "0 24px 24px" }}>
        <h2 className="section-title" style={{ marginTop: 0 }}>Coming soon</h2>
        <div className="activity-grid">
          {TEASERS.map((t) => (
            <article
              key={t.title}
              className="activity-card mod-construction__teaser"
              style={{ ["--card-accent" as string]: t.accent } as React.CSSProperties}
            >
              <header className="activity-card__header">
                <span className="activity-card__sigil mod-construction__float">{t.icon}</span>
                <span className="activity-card__title">{t.title}</span>
                <span className="activity-card__featured-tag">Soon</span>
              </header>
              <p className="activity-card__detail" style={{ marginTop: 0 }}>{t.desc}</p>
              <div className="mod-construction__shimmer" aria-hidden />
            </article>
          ))}
        </div>
      </div>
    </div>
  );
}
