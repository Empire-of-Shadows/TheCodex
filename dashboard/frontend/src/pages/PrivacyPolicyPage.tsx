import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api/client";
import type { User } from "../api/types";
import AppHeader from "../components/AppHeader";

const EFFECTIVE_DATE = "August 1, 2026";

export default function PrivacyPolicyPage() {
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
          <h1 className="dash-hero__title">Privacy Policy</h1>
          <p className="dash-hero__sub">Effective {EFFECTIVE_DATE}</p>
        </div>
      </section>

      <div className="legal-doc">
        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>1. Overview</h2>
          <p>
            This policy explains what data TheCodex ("the bot", "we", "us") collects when you use
            the bot or the web dashboard, how we use it, and the choices you have. TheCodex is part
            of the Empire of Shadows ecosystem and is designed to work in any Discord server. The
            bot has Discord's <strong>Message Content</strong> intent enabled so it can read the
            words you type after mentioning it, but it does not store the text of your messages -
            see "Information we collect" below for exactly what is kept.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>2. Information we collect</h2>
          <ul>
            <li>
              <strong>Discord account data</strong> provided through Discord login (OAuth): your
              user ID, username, global display name, and avatar, plus the servers you are in and
              your permissions in them, which we use for access control.
            </li>
            <li>
              <strong>Suggestion text and votes:</strong> the title, description and details you
              type into the suggestion form are <strong>stored</strong> along with the suggestion's
              votes and status, so it can be reviewed and displayed. This text comes from the form
              you fill in, not from reading your messages.
            </li>
            <li>
              <strong>Would-You-Rather votes:</strong> which of the two options you picked, and the
              running totals. The questions come from a question bank we write, not from members.
            </li>
            <li><strong>Server-boost records</strong> for the servers you boost.</li>
            <li>
              <strong>Member whitelist entries</strong> used to control who may use certain
              features.
            </li>
            <li>
              <strong>A cached copy of server structure</strong> - member, role, and channel lists
              for the servers the bot is in - kept so the dashboard and bot can resolve names and
              permissions quickly, along with usage analytics.
            </li>
            <li><strong>A session cookie</strong> that keeps you signed in to the dashboard.</li>
          </ul>
          <p className="muted">
            Tag-tracker status is read live from your Discord roles and is not stored. The bot reads
            message text in three places and stores none of it: the words after a mention of the bot
            become a search query for the guide, an announcement's text is used to name the
            discussion thread opened under it, and posts in channels set up for drop tracking are
            counted without their text being examined. The bot does not archive chat history.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>3. How we use your data</h2>
          <p>
            We use this data to run the bot's features, power your dashboard, and gate admin and
            moderator features to the right people. We do not sell your data and we do not show
            advertising.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>4. Cookies</h2>
          <p>
            We use a single session cookie to identify your signed-in session on the dashboard. It
            is required for login to work. Sessions expire automatically after about 30 days, after
            which you will need to sign in again.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>5. Third parties</h2>
          <p>
            We rely on Discord for login and as the platform the bot runs on, and on our database
            and hosting infrastructure (MongoDB) to store your data. Your dashboard session is
            shared across the Empire of Shadows ecosystem, so one login covers every bot dashboard.
            We do not share your data with advertisers or data brokers.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>6. Data retention</h2>
          <p>
            We keep your votes, suggestions, and boost records until you delete them (see your
            choices below). Login sessions expire automatically. If the bot is removed from a
            server, related configuration may be cleaned up.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>7. Your choices and rights</h2>
          <p>From the dashboard you can:</p>
          <ul>
            <li>Export a copy of the data we hold for you.</li>
            <li>Delete your data, for one server or across all servers.</li>
          </ul>
          <p className="muted">
            Manage these from the <Link to="/me/privacy">Privacy &amp; Data</Link> panel after signing in.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>8. Children</h2>
          <p>
            You must meet Discord's minimum age requirement for your region to use the bot or the
            dashboard. We do not knowingly collect data from anyone below that age.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>9. Changes to this policy</h2>
          <p>
            We may update this policy from time to time. The effective date at the top of this page
            reflects the latest version, and we will note material changes where practical.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>10. Contact</h2>
          <p>
            Questions about this policy or your data can be sent to
            <a href="mailto:support@eosofficial.club"> support@eosofficial.club</a>.
          </p>
        </section>
      </div>
    </div>
  );
}
