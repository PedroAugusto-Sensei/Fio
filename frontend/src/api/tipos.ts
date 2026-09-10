export type Situacao = "em_andamento" | "concluido" | "bloqueado" | "duvida_cliente";

export type Papel = "admin" | "membro";

export interface Eu {
  nome: string;
  setor: string;
  empresa: string;
  /** Escopo de tudo que esta pessoa vê. Todo queryset do back sai daqui. */
  empresa_id: number;
  /** Decide só convidar, editar setores e mexer na caixa. Ler e registrar é de todos. */
  papel: Papel;
  pode_configurar_imap: boolean;
  /** A caixa que o Fio lê, e a pasta observada dentro dela. */
  caixa_email: string;
  pasta_email: string;
  /** Falso na empresa sem caixa: enquanto for falso, nenhum e-mail entra para ela. */
  caixa_configurada: boolean;
  iniciais: string;
}

export interface ChamadoItem {
  id: number;
  codigo: string;
  assunto: string;
  cliente_nome: string;
  /** Primeiros ~140 caracteres da mensagem de ordem 0 — as palavras do cliente. */
  trecho_cliente: string;
  /** `null` quando ninguém registrou nada ainda. É informação, não erro. */
  situacao: Situacao | null;
  total_registros: number;
  ultimo_autor: string | null;
  ultimo_setor: string | null;
  ultima_atualizacao: string | null;
  criado_em: string;
}

export interface ListaChamados {
  itens: ChamadoItem[];
  total: number;
  pagina: number;
  paginas: number;
  por_pagina: number;
  abertos: number;
  caixa_email: string;
  pasta_email: string;
}

export interface Anexo {
  id: number;
  nome: string;
  mime: string;
  url: string;
}

export interface Mensagem {
  id: number;
  ordem: number;
  remetente: string;
  destinatario: string;
  assunto: string;
  recebido_em: string;
  texto: string;
  /** Onde começa o trecho citado. O texto vem inteiro; a citação é marcada, não cortada. */
  citacao_offset: number | null;
  sha256: string;
  anexos: Anexo[];
}

export interface Autor {
  id: number;
  nome: string;
  setor: string;
  iniciais: string;
}

export interface Registro {
  id: number;
  autor: Autor;
  setor: string;
  texto: string;
  situacao: Situacao;
  criado_em: string;
  editado_em: string | null;
  versao_anterior_id: number | null;
}

export interface Chamado {
  id: number;
  codigo: string;
  assunto: string;
  cliente_nome: string;
  cliente_email: string;
  criado_em: string;
  situacao: Situacao | null;
  ultima_atualizacao: string | null;
  descricao: Mensagem | null;
  mensagens_seguintes: Mensagem[];
  registros: Registro[];
  quem_registrou: Autor[];
  total_mensagens: number;
}

export interface RegistroPublicado {
  registro: Registro;
  situacao: Situacao | null;
  ultima_atualizacao: string | null;
  total_registros: number;
}

/* ------------------------------------------------------------------ caixa de entrada */

export type SituacaoEmail = "pendente" | "promovido" | "descartado";

/** Uma linha da caixa de entrada: o e-mail como chegou, antes de virar (ou não) chamado. */
export interface EmailItem {
  id: number;
  remetente_nome: string;
  remetente_email: string;
  assunto: string;
  /** Primeiros ~140 caracteres do que o cliente escreveu. */
  trecho: string;
  recebido_em: string;
  situacao: SituacaoEmail;
  total_anexos: number;
  chamado_id: number | null;
  chamado_codigo: string | null;
  promovido_em: string | null;
  /** `null` com situação "promovido" = entrou sozinho, por ser resposta numa conversa. */
  promovido_por: string | null;
  descartado_em: string | null;
  descartado_por: string | null;
}

export interface EmailCompleto extends EmailItem {
  destinatario: string;
  texto: string;
  /** Onde começa a citação. O texto vem inteiro; a citação é marcada, não cortada. */
  citacao_offset: number | null;
  sha256: string;
  anexos: Anexo[];
}

export interface ListaEmails {
  itens: EmailItem[];
  total: number;
  pagina: number;
  paginas: number;
  por_pagina: number;
  pendentes: number;
  caixa_email: string;
  pasta_email: string;
}

export interface Promovido {
  chamado_id: number;
  chamado_codigo: string;
  email: EmailItem;
}

/* ------------------------------------------------------------------ empresa e contas

   Não existe senha compartilhada de empresa: cada funcionário tem conta própria,
   porque é `Registro.autor` que responde "quem agiu". A empresa é um container. */

export interface Membro {
  id: number;
  nome: string;
  setor: string;
  papel: Papel;
  iniciais: string;
  /** Quem se cadastrou pela interface entra com o próprio e-mail. */
  usuario: string;
}

export interface ConviteCriado {
  id: number;
  token: string;
  /** O link inteiro, pronto para colar. O Fio não manda e-mail. */
  url: string;
  email: string;
  setor: string;
  expira_em: string;
}

export interface ConvitePendente {
  id: number;
  email: string;
  setor: string;
  url: string;
  criado_em: string;
  expira_em: string;
  criado_por: string;
}

/** O que a tela de convite sabe sem sessão: o nome da empresa e os setores. Nada mais. */
export interface ConvitePublico {
  empresa_nome: string;
  setores: string[];
  email: string;
  setor: string;
}

export interface EmpresaSalva {
  id: number;
  nome: string;
  setores: string[];
  caixa_email: string;
  pasta_email: string;
}
