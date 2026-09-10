import type { Situacao } from "../api/tipos";
import { rotuloCurto, tomDe } from "../lib/situacoes";

/** Ponto colorido + rótulo. `null` vira "sem registro" em vermelho — informação, não erro. */
export function PontoSituacao({
  situacao,
  maiuscula = false,
}: {
  situacao: Situacao | null;
  maiuscula?: boolean;
}) {
  const texto = rotuloCurto(situacao);
  return (
    <span className={`situacao situacao-${tomDe(situacao)}`}>
      <span className="ponto" />
      <span>{maiuscula ? texto.charAt(0).toUpperCase() + texto.slice(1) : texto}</span>
    </span>
  );
}

export function Avatar({ iniciais, title }: { iniciais: string; title?: string }) {
  return (
    <span className="avatar" title={title} aria-hidden="true">
      {iniciais}
    </span>
  );
}

/** Iniciais a partir do nome, para quando o back mandou só a string. */
export function iniciaisDe(nome: string | null): string {
  if (!nome) return "?";
  const partes = nome.split(/\s+/).filter(Boolean);
  if (partes.length === 0) return "?";
  if (partes.length === 1) return partes[0].slice(0, 2).toUpperCase();
  return (partes[0][0] + partes[partes.length - 1][0]).toUpperCase();
}
