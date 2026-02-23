import { Copy, Check } from 'lucide-react';
import { useState } from 'react';

interface Props {
  yaml: string;
}

export function YamlPreview({ yaml }: Props) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    await navigator.clipboard.writeText(yaml);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <section>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-base font-semibold">Scenario YAML Preview</h3>
        <button onClick={handleCopy} className="btn-small">
          {copied ? <><Check size={14} /> Copied</> : <><Copy size={14} /> Copy</>}
        </button>
      </div>
      <pre className="p-4 rounded-xl border border-[var(--color-border)] bg-[var(--color-bg)] text-xs overflow-x-auto max-h-80 whitespace-pre font-mono">
        {yaml}
      </pre>
    </section>
  );
}
