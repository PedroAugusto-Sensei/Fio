import type { Situacao } from "../api/tipos";

/** Cores da seção 10: concluído = ok; em andamento e dúvida = atenção; bloqueado = alerta. */
export const SITUACOES: { valor: Situacao; rotulo: string; tom: Tom }[] = [
  { valor: "em_andamento", rotulo: "Em andamento", tom: "atencao" },
  { valor: "concluido", rotulo: "Concluído", tom: "ok" },
  { valor: "bloqueado", rotulo: "Bloqueado", tom: "alerta" },
  { valor: "duvida_cliente", rotulo: "Dúvida com o cliente", tom: "atencao" },
];

export type Tom = "ok" | "atencao" | "alerta";

const POR_VALOR = new Map(SITUACOES.map((s) => [s.valor, s]));

/** Rótulo curto, como aparece na lista ("em andamento", "sem registro"). */
export function rotuloCurto(situacao: Situacao | null): string {
  if (situacao === null) return "sem registro";
  return (POR_VALOR.get(situacao)?.rotulo ?? situacao).toLowerCase();
}

export function rotulo(situacao: Situacao | null): string {
  if (situacao === null) return "Sem registro";
  return POR_VALOR.get(situacao)?.rotulo ?? situacao;
}

/** "sem registro" é vermelho, igual a bloqueado: é informação, não erro. */
export function tomDe(situacao: Situacao | null): Tom {
  if (situacao === null) return "alerta";
  return POR_VALOR.get(situacao)?.tom ?? "atencao";
}
