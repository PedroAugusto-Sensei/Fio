import { useEffect, useRef } from "react";
import type { ReactNode } from "react";

/** Sobreposição com Esc, clique fora e foco preso — a única superfície com sombra. */
export function Modal({
  children,
  onFechar,
  rotulo,
  largo = false,
}: {
  children: ReactNode;
  onFechar: () => void;
  rotulo: string;
  largo?: boolean;
}) {
  const caixa = useRef<HTMLDivElement>(null);

  useEffect(() => {
    function tecla(evento: KeyboardEvent) {
      if (evento.key === "Escape") onFechar();
    }
    document.addEventListener("keydown", tecla);
    const antes = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    caixa.current?.querySelector<HTMLElement>("textarea, input, button")?.focus();
    return () => {
      document.removeEventListener("keydown", tecla);
      document.body.style.overflow = antes;
    };
  }, [onFechar]);

  return (
    <div
      className="fundo-modal"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onFechar();
      }}
    >
      <div
        className={`modal${largo ? " modal-largo" : ""}`}
        role="dialog"
        aria-modal="true"
        aria-label={rotulo}
        ref={caixa}
      >
        {children}
      </div>
    </div>
  );
}
