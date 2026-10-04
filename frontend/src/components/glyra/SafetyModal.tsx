import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";
import { Check, Info, X } from "lucide-react";

const SafetyContext = createContext<{ open: () => void }>({ open: () => {} });

export function useSafety() {
  return useContext(SafetyContext);
}

export function SafetyProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false);
  const open = useCallback(() => setIsOpen(true), []);

  useEffect(() => {
    if (!isOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setIsOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [isOpen]);

  return (
    <SafetyContext.Provider value={{ open }}>
      {children}
      {isOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-background/70 p-4 backdrop-blur-sm"
          onClick={() => setIsOpen(false)}
          role="presentation"
        >
          <div
            role="dialog"
            aria-modal="true"
            aria-label="Safety comes first"
            onClick={(e) => e.stopPropagation()}
            className="glass-card animate-rise relative w-full max-w-lg p-8"
          >
            <button
              onClick={() => setIsOpen(false)}
              aria-label="Close"
              className="absolute right-5 top-5 rounded-lg p-1.5 text-subtle transition-colors hover:bg-accent hover:text-foreground"
            >
              <X className="size-4" />
            </button>
            <span className="flex size-11 items-center justify-center rounded-xl border border-teal/30 bg-teal/10">
              <Info className="size-5 text-teal" />
            </span>
            <p className="eyebrow mt-5 text-teal">Glyra explains</p>
            <h2 className="mt-2 text-2xl font-bold">Safety comes first</h2>
            <p className="mt-3 text-sm leading-relaxed text-muted-foreground">
              Glyra is informational and does not replace professional medical advice. If you have
              severe symptoms or an emergency, contact emergency services. For concerning high or
              low readings, follow your care plan or contact your care team.
            </p>
            <button
              onClick={() => setIsOpen(false)}
              className="mt-7 inline-flex items-center gap-2 rounded-lg bg-teal px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-glow transition-opacity hover:opacity-90"
            >
              Got it <Check className="size-4" />
            </button>
          </div>
        </div>
      )}
    </SafetyContext.Provider>
  );
}
