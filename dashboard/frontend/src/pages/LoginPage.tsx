export default function LoginPage() {
  return (
    <div className="login-page">
      <h1>TheCodex Dashboard</h1>
      <p>View stats and manage your servers.</p>
      <a href="/auth/discord" className="btn btn-primary">
        Login with Discord
      </a>
      <p style={{ fontSize: "0.9rem" }}>
        <a href="https://empireofshadows.club" target="_blank" rel="noopener noreferrer">
          Main site
        </a>
        {" · "}
        <a href="https://host.empireofshadows.club" target="_blank" rel="noopener noreferrer">
          TheHost
        </a>
      </p>
    </div>
  );
}