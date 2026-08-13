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
              <strong>Would-You-Rather votes:</strong> which of the two options you picked, when
              you picked it, and the running totals. Questions come from a question bank we write
              and from members: a question you submit is{" "}
              <strong>stored</strong> with your Discord ID so staff can review it and so you can
              be credited if it goes out.
            </li>
            <li>
              <strong>Notification preferences,</strong> such as whether you asked to be pinged
              when a new Would-You-Rather question is posted.
            </li>
            <li><strong>Server-boost records</strong> for the servers you boost.</li>
            <li>
              <strong>Member whitelist entries</strong> used to control who may use certain
              features. These are written by server staff, not by you.
            </li>
            <li>
              <strong>An audit log</strong> of admin actions, recording who changed a setting and
              when, for servers you help manage.
            </li>
            <li>
              <strong>A cached copy of server structure</strong> - member, role, and channel lists
              for the servers the bot is in - kept so the dashboard and bot can resolve names and
              permissions quickly, along with usage analytics. Your part of that cache is a
              snapshot of your server profile: your nickname, your roles, and when you joined.
            </li>
            <li><strong>A session cookie</strong> that keeps you signed in to the dashboard.</li>
          </ul>
          <p className="eos-muted">
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
            We use this data to run the bot's features, power your dashboard, and gate admin
            features to the right people. We do not sell your data and we do not show
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
            We keep the records described above until you delete them from the Privacy &amp; Data
            panel (see your choices below). Two kinds of records are kept even then: whitelist
            entries, which are written by staff and also control your access to the server, and
            the admin audit log, which expires on its own after one year. Turning data collection
            off stops new records from being written but does not remove existing ones. Login
            sessions expire automatically. If the bot is removed from a server, the data it
            stored for that server is deleted after a short grace period.
          </p>
        </section>

        <section className="section card">
          <h2 className="section-title" style={{ marginTop: 0 }}>7. Your choices and rights</h2>
          <p>From the dashboard you can:</p>
          <ul>
            <li>Turn off data collection, for one feature or for everything.</li>
            <li>Export a copy of the data we hold for you.</li>
            <li>Delete your data, for one server or across all servers.</li>
          </ul>

          <h3 className="section-title" style={{ fontSize: "1rem" }}>
            Turning off data collection
          </h3>
          <p>
            You can tell Codex to stop recording new data about you, either all of it at once or
            one feature at a time: Would-You-Rather, suggestions, boost tracking, and the member
            snapshot. These choices are tied to your account, so they apply in{" "}
            <strong>every server</strong> that uses Codex, and they take effect within about a
            minute.
          </p>
          <p>
            Opting out is <strong>forward-looking only</strong>. It stops future collection and
            never removes what is already stored - deleting your data is the separate control for
            that. With a feature turned off: your Would-You-Rather votes are acknowledged but not
            counted and you cannot submit questions; your suggestions still post but always
            anonymously, with no status messages, no record tied to you, and no editing them
            afterwards; boost records and the member snapshot simply stop being written.
          </p>
          <p>
            Two things survive a delete request. Your whitelist entry, if a server's staff added
            one, is a moderation record they wrote and is also what grants your access, so only
            staff can remove it - it is still included in your export. Audit entries for admin
            actions stay so servers keep a complete history of who changed what. Suggestions you
            sent anonymously cannot be exported or deleted either, because nothing links them to
            you.
          </p>
          <p className="eos-muted">
            Manage all of these from the <Link to="/me/privacy">Privacy &amp; Data</Link> panel
            after signing in.
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
