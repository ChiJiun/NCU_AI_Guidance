import ReactMarkdown from 'react-markdown';
import remarkGfm from 'remark-gfm';

/** AI 回答的 Markdown（樣式見 v2.css 的 .v2-prose）。 */
export default function Markdown({ text }: { text: string }) {
  return (
    <div className="v2-prose">
      <ReactMarkdown
        remarkPlugins={[remarkGfm]}
        components={{
          a: ({ children, href }) => (
            <a href={href} target="_blank" rel="noopener noreferrer">
              {children}
            </a>
          ),
          table: ({ children }) => (
            <div className="overflow-x-auto">
              <table>{children}</table>
            </div>
          ),
        }}
      >
        {text}
      </ReactMarkdown>
    </div>
  );
}
