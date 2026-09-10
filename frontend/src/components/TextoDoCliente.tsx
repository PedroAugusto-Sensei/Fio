/**
 * Renderiza o texto do cliente inteiro. O trecho a partir de `citacaoOffset`
 * sai em cor secundária — **nunca** escondido nem cortado. Apagar a citação é
 * exatamente a perda que este produto existe para impedir.
 */
export function TextoDoCliente({
  texto,
  citacaoOffset,
  className,
}: {
  texto: string;
  citacaoOffset: number | null;
  className?: string;
}) {
  if (citacaoOffset === null || citacaoOffset <= 0 || citacaoOffset >= texto.length) {
    return <div className={className}>{texto}</div>;
  }
  return (
    <div className={className}>
      {texto.slice(0, citacaoOffset)}
      <span className="citado">{texto.slice(citacaoOffset)}</span>
    </div>
  );
}
