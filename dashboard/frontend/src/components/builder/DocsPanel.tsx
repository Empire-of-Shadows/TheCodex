import { useCallback, useEffect, useRef, useState } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { api } from "../../api/client";
import type { BuilderMode } from "../../api/types";

const TOPICS = [
  { key: "getting-started", label: "Getting Started" },
  { key: "schema", label: "Schema Reference" },
  { key: "placeholders", label: "Placeholders" },
  { key: "examples", label: "Examples" },
] as const;

type TopicKey = (typeof TOPICS)[number]["key"];

interface DocsCacheEntry {
  title: string;
  content: string;
}

interface Props {
  mode: BuilderMode;
}

export default function DocsPanel({ mode }: Props) {
  const [topicIdx, setTopicIdx] = useState(0);
  const [loading, setLoading] = useState(false);
  const [doc, setDoc] = useState<DocsCacheEntry | null>(null);
  const [error, setError] = useState<string | null>(null);

  // Cache: keyed by `${mode}:${topic}`
  const cache = useRef<Record<string, DocsCacheEntry>>({});

  const topic = TOPICS[topicIdx].key;
  const builder = mode === "guide" ? "guide" : "welcome";

  const fetchDoc = useCallback(async (b: string, t: TopicKey) => {
    const cacheKey = `${b}:${t}`;
    if (cache.current[cacheKey]) {
      setDoc(cache.current[cacheKey]);
      setError(null);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const result = await api.getDocs(b as "guide" | "welcome", t);
      cache.current[cacheKey] = result;
      setDoc(result);
    } catch (err: any) {
      setError(err.message || "Failed to load documentation");
      setDoc(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchDoc(builder, topic);
  }, [builder, topic, fetchDoc]);

  const goPrev = () => setTopicIdx((i) => Math.max(0, i - 1));
  const goNext = () => setTopicIdx((i) => Math.min(TOPICS.length - 1, i + 1));

  return (
    <div className="docs-panel">
      <h3>Documentation</h3>

      <select
        className="docs-panel-select"
        value={topicIdx}
        onChange={(e) => setTopicIdx(Number(e.target.value))}
      >
        {TOPICS.map((t, i) => (
          <option key={t.key} value={i}>
            {t.label}
          </option>
        ))}
      </select>

      <div className="docs-panel-nav">
        <button className="btn btn-secondary" disabled={topicIdx === 0} onClick={goPrev} style={{ fontSize: 12 }}>
          Prev
        </button>
        <span style={{ fontSize: 12, color: "var(--text-muted)" }}>
          {topicIdx + 1} / {TOPICS.length}
        </span>
        <button className="btn btn-secondary" disabled={topicIdx === TOPICS.length - 1} onClick={goNext} style={{ fontSize: 12 }}>
          Next
        </button>
      </div>

      <div className="docs-panel-separator" />

      <div className="docs-panel-content">
        {loading && <p style={{ color: "var(--text-muted)", fontSize: 13 }}>Loading...</p>}
        {error && <p style={{ color: "var(--danger)", fontSize: 13 }}>{error}</p>}
        {!loading && doc && <ReactMarkdown remarkPlugins={[remarkGfm]}>{doc.content}</ReactMarkdown>}
      </div>
    </div>
  );
}
