import { useEffect, useState, type ReactNode } from "react";

function formatTimestamp(): string {
  const now = new Date();
  let hours = now.getHours();
  const minutes = now.getMinutes().toString().padStart(2, "0");
  const ampm = hours >= 12 ? "PM" : "AM";
  hours = hours % 12 || 12;
  return `Today at ${hours}:${minutes} ${ampm}`;
}

interface Props {
  children: ReactNode;
}

export default function MessageChrome({ children }: Props) {
  const [timestamp, setTimestamp] = useState(formatTimestamp);

  useEffect(() => {
    const interval = setInterval(() => setTimestamp(formatTimestamp()), 60_000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="dc-message">
      <div className="dc-message-avatar">IC</div>
      <div className="dc-message-content">
        <div className="dc-message-header">
          <span className="dc-message-author">Imperial Codex</span>
          <span className="dc-message-badge">BOT</span>
          <span className="dc-message-timestamp">{timestamp}</span>
        </div>
        {children}
      </div>
    </div>
  );
}
