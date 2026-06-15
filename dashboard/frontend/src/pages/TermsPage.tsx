import { useEffect, useState } from "react";
import { api } from "../api/client";
import type { User } from "../api/types";
import AppHeader from "../components/AppHeader";

const EFFECTIVE_DATE = "May 25, 2026";

export default function TermsPage() {
  const [user, setUser] = useState<User | null>(null);

  useEffect(() => {
    api.me().then(setUser).catch(() => {});
  }, []);

  return (
    <div className="app-layout">
      <AppHeader user={user} />

      <section className="dash-hero">
        <div className="dash-hero__orb" />
        <img className="dash-hero__sigil" src="/brand/logo-mark.png" alt="" />
        <div className="dash-hero__copy">
          <span className="dash-hero__eyebrow">Legal</span>
          <h1 className="dash-hero__title">Terms of Service</h1>
          <p className="dash-hero__sub">Effective {EFFECTIVE_DATE}</p>
        </div>
      </section>

      <div className="legal-doc">
        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>1. Acceptance and eligibility</h2>
          <p>
            TheCodex ("the bot", "we", "us") is a Discord bot and companion web dashboard operated
            as part of the Empire of Shadows ecosystem. By adding the bot to a server, using its
            commands, or signing in to the dashboard, you agree to these Terms of Service.
          </p>
          <p>
            You must meet Discord's minimum age requirement for your region and comply with the
            <a href="https://discord.com/terms" target="_blank" rel="noopener"> Discord Terms of Service</a>
            at all times. If you do not agree to these terms, do not use the bot or the dashboard.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>2. The service</h2>
          <p>
            TheCodex is a multi-server Discord server-guide and FAQ bot with natural-language
            search, alongside community features including Would-You-Rather prompts, a suggestion
            system, and server-boost tracking. It includes a web dashboard for viewing stats and
            configuring servers. The bot is designed to work in any Discord server, not only
            Empire of Shadows.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>3. Acceptable use</h2>
          <p>When using the bot or dashboard, you agree not to:</p>
          <ul>
            <li>Spam, flood, or manipulate votes, suggestions, or any other community feature.</li>
            <li>Harass, abuse, or harm other members.</li>
            <li>Attempt to disrupt, overload, reverse engineer, or gain unauthorized access to the service.</li>
            <li>Use the service in violation of the Discord Terms of Service or the rules of the server you are in.</li>
          </ul>
          <p className="muted">
            Server administrators configure where and how the bot runs in their server and may
            restrict access to features at their discretion.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>4. User-submitted content</h2>
          <p>
            Some features let you submit content, such as suggestions and Would-You-Rather votes.
            You are responsible for what you submit, and it must follow these terms, the Discord
            Terms of Service, and the rules of the server you are in.
          </p>
          <p>
            Server administrators and moderators may review, edit, hide, or remove submitted
            content at their discretion, and we may remove content as part of maintenance or
            anti-abuse measures.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>5. Availability and "as is"</h2>
          <p>
            The service is provided "as is" and "as available", without warranties of any kind.
            We do not guarantee that the bot or dashboard will be uninterrupted, error free, or
            available at any particular time, and features may change or be discontinued.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>6. Limitation of liability</h2>
          <p>
            To the maximum extent permitted by law, we are not liable for any indirect, incidental,
            or consequential damages, or for any loss of data or content, arising from your use of
            or inability to use the bot or dashboard.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>7. Termination</h2>
          <p>
            We may suspend or revoke access to the bot or dashboard at any time, including for
            violations of these terms. Server administrators may remove the bot from their server
            at any time. You may stop using the service and remove the bot whenever you choose.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>8. Changes to these terms</h2>
          <p>
            We may update these terms from time to time. The effective date at the top of this page
            reflects the latest version. Continued use of the bot or dashboard after an update means
            you accept the revised terms.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>9. Contact</h2>
          <p>
            Questions about these terms can be sent to
            <a href="mailto:support@eosofficial.club"> support@eosofficial.club</a>.
          </p>
        </section>
      </div>
    </div>
  );
}
