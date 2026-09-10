import type {
  Chamado,
  ConviteCriado,
  ConvitePendente,
  ConvitePublico,
  EmailCompleto,
  EmailItem,
  EmpresaSalva,
  Eu,
  ListaChamados,
  ListaEmails,
  Membro,
  Promovido,
  Registro,
  RegistroPublicado,
  Situacao,
} from "./tipos";

/** Erro da API já com a mensagem em português que o back mandou. */
export class ErroApi extends Error {
  status: number;
  constructor(mensagem: string, status: number) {
    super(mensagem);
    this.name = "ErroApi";
    this.status = status;
  }
}

function cookie(nome: string): string {
  const achado = document.cookie
    .split(";")
    .map((p) => p.trim())
    .find((p) => p.startsWith(`${nome}=`));
  return achado ? decodeURIComponent(achado.slice(nome.length + 1)) : "";
}

/** O Django só planta o csrftoken quando alguém pede. Chamado uma vez, no boot. */
export async function prepararCsrf(): Promise<void> {
  if (cookie("csrftoken")) return;
  await fetch("/api/csrf", { credentials: "same-origin" });
}

async function pedir<T>(caminho: string, opcoes: RequestInit = {}): Promise<T> {
  const metodo = (opcoes.method ?? "GET").toUpperCase();
  const cabecalhos: Record<string, string> = { Accept: "application/json" };

  if (opcoes.body) cabecalhos["Content-Type"] = "application/json";
  if (!["GET", "HEAD", "OPTIONS"].includes(metodo)) {
    await prepararCsrf();
    cabecalhos["X-CSRFToken"] = cookie("csrftoken");
  }

  const resposta = await fetch(`/api${caminho}`, {
    ...opcoes,
    headers: { ...cabecalhos, ...(opcoes.headers ?? {}) },
    credentials: "same-origin",
  });

  if (resposta.status === 204) return undefined as T;

  let corpo: unknown = null;
  try {
    corpo = await resposta.json();
  } catch {
    corpo = null;
  }

  if (!resposta.ok) {
    const erro =
      corpo && typeof corpo === "object" && "erro" in corpo
        ? String((corpo as { erro: unknown }).erro)
        : "Não foi possível falar com o servidor. Tente de novo.";
    throw new ErroApi(erro, resposta.status);
  }
  return corpo as T;
}

function query(params: Record<string, string | number | boolean | undefined>): string {
  const busca = new URLSearchParams();
  for (const [chave, valor] of Object.entries(params)) {
    if (valor === undefined || valor === "" || valor === false) continue;
    busca.set(chave, String(valor));
  }
  const texto = busca.toString();
  return texto ? `?${texto}` : "";
}

export interface ConfigImap {
  host: string; usuario: string; caixa_email: string; pasta: string; senha_configurada: boolean;
}

export const api = {
  imap: () => pedir<ConfigImap>("/empresa/imap"),
  salvarImap: (dados: Omit<ConfigImap, "senha_configurada"> & { senha: string }) =>
    pedir<ConfigImap>("/empresa/imap", { method: "PUT", body: JSON.stringify(dados) }),
  entrar: (usuario: string, senha: string) =>
    pedir<Eu>("/auth/login", { method: "POST", body: JSON.stringify({ usuario, senha }) }),

  sair: () => pedir<{ ok: boolean }>("/auth/logout", { method: "POST" }),

  eu: () => pedir<Eu>("/me"),

  setores: () => pedir<{ setores: string[] }>("/setores"),

  chamados: (params: {
    busca?: string;
    situacao?: string;
    cliente?: string;
    meus?: boolean;
    page?: number;
  }) => pedir<ListaChamados>(`/chamados${query(params)}`),

  chamado: (id: number) => pedir<Chamado>(`/chamados/${id}`),

  publicarRegistro: (chamadoId: number, texto: string, situacao: Situacao) =>
    pedir<RegistroPublicado>(`/chamados/${chamadoId}/registros`, {
      method: "POST",
      body: JSON.stringify({ texto, situacao }),
    }),

  corrigirRegistro: (registroId: number, texto: string, situacao: Situacao) =>
    pedir<RegistroPublicado>(`/registros/${registroId}`, {
      method: "PUT",
      body: JSON.stringify({ texto, situacao }),
    }),

  historico: (chamadoId: number) =>
    pedir<Registro[]>(`/chamados/${chamadoId}/registros?historico=1`),

  /* --------------------------------------------------- caixa de entrada
     Promover e descartar não mandam corpo nenhum. Não existe, em lugar
     nenhum deste cliente, um caminho que envie texto de mensagem. */

  emails: (params: { situacao?: string; page?: number }) =>
    pedir<ListaEmails>(`/emails${query(params)}`),

  email: (id: number) => pedir<EmailCompleto>(`/emails/${id}`),

  pendentes: () => pedir<{ pendentes: number }>("/emails/contagem"),

  promoverEmail: (id: number) =>
    pedir<Promovido>(`/emails/${id}/promover`, { method: "POST" }),

  descartarEmail: (id: number) =>
    pedir<EmailItem>(`/emails/${id}/descartar`, { method: "POST" }),

  /* --------------------------------------------------- empresa e contas
     Cada funcionário tem conta própria: não existe senha de empresa. */

  registrarEmpresa: (dados: {
    empresa_nome: string;
    setores: string[];
    nome: string;
    email: string;
    senha: string;
  }) => pedir<Eu>("/auth/registrar-empresa", { method: "POST", body: JSON.stringify(dados) }),

  /** Sem sessão: é a tela de quem ainda não tem conta. */
  convite: (token: string) => pedir<ConvitePublico>(`/convites/${encodeURIComponent(token)}`),

  aceitarConvite: (
    token: string,
    dados: { nome: string; email: string; senha: string; setor: string },
  ) =>
    pedir<Eu>(`/convites/${encodeURIComponent(token)}/aceitar`, {
      method: "POST",
      body: JSON.stringify(dados),
    }),

  membros: () => pedir<{ itens: Membro[] }>("/membros"),

  convites: () => pedir<{ itens: ConvitePendente[] }>("/convites"),

  criarConvite: (dados: { email?: string; setor?: string }) =>
    pedir<ConviteCriado>("/convites", { method: "POST", body: JSON.stringify(dados) }),

  revogarConvite: (id: number) => pedir<void>(`/convites/${id}`, { method: "DELETE" }),

  salvarEmpresa: (dados: { nome: string; setores: string[] }) =>
    pedir<EmpresaSalva>("/empresa", { method: "PUT", body: JSON.stringify(dados) }),
};
