const MINUTO = 60_000;
const HORA = 60 * MINUTO;
const DIA = 24 * HORA;

/** "agora", "há 40min", "há 3h", "ontem", "há 12d" — como no protótipo. */
export function tempoRelativo(iso: string | null): string {
  if (!iso) return "—";
  const quando = new Date(iso);
  const diferenca = Date.now() - quando.getTime();

  if (diferenca < MINUTO) return "agora";
  if (diferenca < HORA) return `há ${Math.floor(diferenca / MINUTO)}min`;
  if (diferenca < DIA) return `há ${Math.floor(diferenca / HORA)}h`;

  const dias = Math.floor(diferenca / DIA);
  if (dias === 1) return "ontem";
  if (dias < 60) return `há ${dias}d`;
  return dataCurta(iso);
}

/** 21/08 */
export function dataCurta(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR", { day: "2-digit", month: "2-digit" });
}

/** 21/08/2026 */
export function dataCompleta(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("pt-BR");
}

/** 21/08/2026 09:12 */
export function dataHora(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${d.toLocaleDateString("pt-BR")} ${d.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

/** 26/08 · 14:31 */
export function dataHoraCurta(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return `${dataCurta(iso)} · ${d.toLocaleTimeString("pt-BR", {
    hour: "2-digit",
    minute: "2-digit",
  })}`;
}

/** "ontem, 08/09" — como na ficha do chamado. */
export function relativoComData(iso: string | null): string {
  if (!iso) return "—";
  return `${tempoRelativo(iso)}, ${dataCurta(iso)}`;
}

/** Só a data, para agrupar o feed por dia. */
export function chaveDoDia(iso: string): string {
  return new Date(iso).toISOString().slice(0, 10);
}
