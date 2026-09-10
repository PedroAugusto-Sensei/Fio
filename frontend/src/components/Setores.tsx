import { useState } from "react";
import type { KeyboardEvent } from "react";

/**
 * Os setores como chips editáveis, já preenchidos com o padrão.
 *
 * A lista existe porque `Registro.setor` é copiado dela no momento em que alguém
 * publica um registro. Tirar um setor daqui depois **não** reescreve o que já foi
 * gravado: lá é cópia histórica de quem agiu.
 */
export function Setores({
  setores,
  aoMudar,
  id = "setor-novo",
}: {
  setores: string[];
  aoMudar: (setores: string[]) => void;
  id?: string;
}) {
  const [digitando, setDigitando] = useState("");

  function acrescentar() {
    const nome = digitando.trim().replace(/\s+/g, " ");
    if (!nome) return;
    if (!setores.some((s) => s.toLowerCase() === nome.toLowerCase())) {
      aoMudar([...setores, nome]);
    }
    setDigitando("");
  }

  function tecla(evento: KeyboardEvent<HTMLInputElement>) {
    // Enter acrescenta o setor; sem isto, Enter enviaria o formulário inteiro.
    if (evento.key === "Enter" || evento.key === ",") {
      evento.preventDefault();
      acrescentar();
    } else if (evento.key === "Backspace" && !digitando && setores.length) {
      aoMudar(setores.slice(0, -1));
    }
  }

  return (
    <>
      <div className="chips-editaveis">
        {setores.map((setor) => (
          <span key={setor} className="chip-editavel">
            {setor}
            <button
              type="button"
              className="chip-tirar"
              onClick={() => aoMudar(setores.filter((s) => s !== setor))}
              aria-label={`Tirar o setor ${setor}`}
            >
              ×
            </button>
          </span>
        ))}
        {setores.length === 0 && (
          <span className="chips-vazio">Escreva pelo menos um setor.</span>
        )}
      </div>

      <div className="chips-acrescentar">
        <input
          id={id}
          className="campo"
          value={digitando}
          onChange={(e) => setDigitando(e.target.value)}
          onKeyDown={tecla}
          placeholder="Acrescentar setor"
          aria-label="Acrescentar setor"
        />
        <button type="button" className="botao" onClick={acrescentar} disabled={!digitando.trim()}>
          Acrescentar
        </button>
      </div>
    </>
  );
}
