import ReactMarkdown from "react-markdown";

export default function TextPreview({ content }: { content: string }) {
  return (
    <div className="dc-text">
      <ReactMarkdown>{content || "*Empty text*"}</ReactMarkdown>
    </div>
  );
}
