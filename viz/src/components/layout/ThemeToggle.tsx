import { Moon, Sun } from 'lucide-react';

interface Props {
  dark: boolean;
  onToggle: () => void;
}

export function ThemeToggle({ dark, onToggle }: Props) {
  return (
    <button
      onClick={onToggle}
      className="p-2 rounded-lg transition-colors hover:bg-[var(--color-border)]"
      title={dark ? 'Switch to light mode (D)' : 'Switch to dark mode (D)'}
    >
      {dark ? <Sun size={18} /> : <Moon size={18} />}
    </button>
  );
}
