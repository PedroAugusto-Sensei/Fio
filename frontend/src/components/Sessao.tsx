import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { api, prepararCsrf } from "../api/client";
import type { Eu } from "../api/tipos";

interface Contexto {
  eu: Eu | null;
  carregando: boolean;
  entrar: (usuario: string, senha: string) => Promise<void>;
  /** Cadastro da empresa: cria a conta de admin e já abre a sessão. */
  registrarEmpresa: (dados: {
    empresa_nome: string;
    setores: string[];
    nome: string;
    email: string;
    senha: string;
  }) => Promise<void>;
  /** Convite aceito: cria a conta de membro e já abre a sessão. */
  aceitarConvite: (
    token: string,
    dados: { nome: string; email: string; senha: string; setor: string },
  ) => Promise<void>;
  atualizar: () => Promise<void>;
  sair: () => Promise<void>;
}

const SessaoContexto = createContext<Contexto | null>(null);

export function ProvedorSessao({ children }: { children: ReactNode }) {
  const [eu, setEu] = useState<Eu | null>(null);
  const [carregando, setCarregando] = useState(true);

  useEffect(() => {
    let ativo = true;
    (async () => {
      await prepararCsrf();
      try {
        const dados = await api.eu();
        if (ativo) setEu(dados);
      } catch {
        if (ativo) setEu(null);
      } finally {
        if (ativo) setCarregando(false);
      }
    })();
    return () => {
      ativo = false;
    };
  }, []);

  const entrar = useCallback(async (usuario: string, senha: string) => {
    setEu(await api.entrar(usuario, senha));
  }, []);

  const registrarEmpresa = useCallback<Contexto["registrarEmpresa"]>(async (dados) => {
    setEu(await api.registrarEmpresa(dados));
  }, []);

  const aceitarConvite = useCallback<Contexto["aceitarConvite"]>(async (token, dados) => {
    setEu(await api.aceitarConvite(token, dados));
  }, []);

  const atualizar = useCallback(async () => { setEu(await api.eu()); }, []);

  const sair = useCallback(async () => {
    await api.sair();
    setEu(null);
  }, []);

  const valor = useMemo(
    () => ({ eu, carregando, entrar, registrarEmpresa, aceitarConvite, sair, atualizar }),
    [eu, carregando, entrar, registrarEmpresa, aceitarConvite, sair, atualizar],
  );
  return <SessaoContexto.Provider value={valor}>{children}</SessaoContexto.Provider>;
}

export function useSessao(): Contexto {
  const contexto = useContext(SessaoContexto);
  if (!contexto) throw new Error("useSessao precisa estar dentro de <ProvedorSessao>.");
  return contexto;
}

/** Deslogado cai no login e volta para onde estava depois de entrar. */
export function RotaProtegida({ children }: { children: ReactNode }) {
  const { eu, carregando } = useSessao();
  const local = useLocation();

  if (carregando) return <p className="carregando">Carregando…</p>;
  if (!eu) return <Navigate to="/login" replace state={{ de: local.pathname + local.search }} />;
  return <>{children}</>;
}

/**
 * Rota de admin. O front esconde; quem recusa de verdade é o back, que devolve 403.
 * Esconder botão nunca foi permissão — é só não oferecer o que não vai funcionar.
 */
export function RotaDeAdmin({ children }: { children: ReactNode }) {
  const { eu } = useSessao();
  if (eu && eu.papel !== "admin") return <Navigate to="/chamados" replace />;
  return <>{children}</>;
}
