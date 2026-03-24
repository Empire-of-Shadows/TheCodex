import ReactMarkdown from "react-markdown";

export default function TextPreview({ content }: { content: string }) {
  if (!content) {
    return (
      <div className="dc-text">
        <ReactMarkdown breaks>{"*Empty text*"}</ReactMarkdown>
      </div>
    );
  }

  // Split content into segments: consecutive -# lines form a subtext block,
  // everything else is a normal markdown block.
  const lines = content.split("\n");
  const segments: { type: "md" | "subtext"; text: string }[] = [];

  for (const line of lines) {
    if (line.startsWith("-# ")) {
      const stripped = line.slice(3);
      const last = segments[segments.length - 1];
      if (last?.type === "subtext") {
        last.text += "\n" + stripped;
      } else {
        segments.push({ type: "subtext", text: stripped });
      }
    } else {
      const last = segments[segments.length - 1];
      if (last?.type === "md") {
        last.text += "\n" + line;
      } else {
        segments.push({ type: "md", text: line });
      }
    }
  }

  return (
    <div className="dc-text">
      {segments.map((seg, i) =>
        seg.type === "subtext" ? (
          <div key={i} className="dc-subtext">
            <ReactMarkdown breaks>{seg.text}</ReactMarkdown>
          </div>
        ) : (
          <ReactMarkdown key={i} breaks>{seg.text}</ReactMarkdown>
        )
      )}
    </div>
  );
}
