import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";

import { api } from "../api/client";

interface Contexto {
  /** Quantos e-mails esperam decisão. É o contador da navegação. */
  pendentes: number;
  recarregar: () => Promise<void>;
}

const PendentesContexto = createContext<Contexto | null>(null);

/** O cron roda a cada minuto; conferir no mesmo passo mantém o número honesto. */
const INTERVALO = 60_000;

export function ProvedorPendentes({ children }: { children: ReactNode }) {
  const [pendentes, setPendentes] = useState(0);

  const recarregar = useCallback(async () => {
    try {
      const { pendentes: quantos } = await api.pendentes();
      setPendentes(quantos);
    } catch {
      // Contador é informação de apoio: se falhar, a tela continua funcionando.
    }
  }, []);

  useEffect(() => {
    void recarregar();
    const relogio = window.setInterval(() => void recarregar(), INTERVALO);
    return () => window.clearInterval(relogio);
  }, [recarregar]);

  const valor = useMemo(() => ({ pendentes, recarregar }), [pendentes, recarregar]);
  return <PendentesContexto.Provider value={valor}>{children}</PendentesContexto.Provider>;
}

export function usePendentes(): Contexto {
  const contexto = useContext(PendentesContexto);
  if (!contexto) throw new Error("usePendentes precisa estar dentro de <ProvedorPendentes>.");
  return contexto;
}
