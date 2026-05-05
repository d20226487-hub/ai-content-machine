"use client";

import { useEffect } from "react";

interface Props {
  onClose: () => void;
  children: React.ReactNode;
  /** Tailwind max-w-* class. Default "max-w-lg". */
  size?: string;
}

export function Modal({ onClose, children, size = "max-w-lg" }: Props) {
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") onClose();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  return (
    <div
      onClick={onClose}
      className="fixed inset-0 z-50 flex items-start justify-center overflow-y-auto bg-black/40 p-4 pt-16"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className={`w-full ${size} rounded-xl bg-white dark:bg-neutral-900 p-6 shadow-xl`}
      >
        {children}
      </div>
    </div>
  );
}
