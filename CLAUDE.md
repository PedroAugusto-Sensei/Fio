# Fio — regras permanentes do projeto

Plataforma onde os chamados de clientes ficam registrados **com as palavras originais do
cliente como descrição**, e onde cada setor acrescenta o que fez.

Entre a caixa de e-mail e o chamado existe uma etapa: todo e-mail lido vira um
`EmailRecebido`, e uma pessoa decide quais viram chamado. Ela escolhe **qual** e-mail vira
chamado — nunca **o que** está escrito nele.

O Fio **não gerencia fluxo de trabalho**: não tem kanban, etapas, dono, prazo nem integração
com ferramenta de fluxo. A empresa continua usando a ferramenta dela.

## Invariantes (nenhuma pode ser quebrada por conveniência)

1. **`Mensagem` é imutável.** Depois de criada, nunca sofre `UPDATE`. Correção do cliente é uma
   mensagem nova, nunca edição da anterior.
2. **Não existe campo `descricao` em `Chamado`.** A descrição é a `Mensagem` de `ordem = 0`.
   Se o campo existisse, alguém acabaria escrevendo nele.
3. **A situação do chamado não é armazenada em `Chamado`.** É a `situacao` do `Registro` mais
   recente, obtida por projeção. Chamado sem registro não tem situação — mostra "sem registro".
4. **Situação nunca é editada sozinha.** Só muda junto com um registro novo. Não existe endpoint
   nem tela para "atualizar status".
5. **O MIME cru é gravado antes de qualquer parse.** Se o parser errar, reprocessa-se sem pedir
   nada ao cliente.
6. **Exclusão apaga o chamado inteiro em cascata.** Não existe apagar ou editar uma mensagem.
7. **Nenhum ser humano digita ou cola a descrição.** `Mensagem` só é criada a partir de um
   `EmailRecebido` já gravado, copiando `texto` e `bruto` sem alteração. Não existe tela,
   campo, endpoint, serializer nem ação de admin que crie `Mensagem` a partir de texto
   digitado. `gravar_mensagem` recebe o e-mail de origem e mais nada — não há parâmetro de
   texto por onde algo digitado pudesse entrar.

   *Por quê:* se um funcionário precisa copiar e colar o e-mail para dentro do sistema, o
   sistema não resolve o problema que existe para resolver — ele pede justamente o trabalho
   que deveria eliminar.

   *O que o humano decide:* qual e-mail vira chamado. Só isso. Promover e descartar não
   aceitam corpo na requisição.

   *Consequência aceita:* não há plano B para o IMAP. Se o ingest está fora do ar, não entra
   chamado. Quem cobre a demonstração é o `seed_demo`, não uma tela de digitação.

8. **`EmailRecebido` é imutável no conteúdo e nunca é apagado.** `bruto`, `texto`, `sha256`,
   `remetente_email`, `assunto` e `recebido_em` não sofrem `UPDATE` depois de criados — o
   `save()` levanta exceção. Só os campos de situação mudam. Descartar carimba
   `descartado_em`; o registro continua no banco e continua consultável na tela.

   *Por quê:* se o que chegou pudesse ser apagado ou corrigido, a caixa deixaria de ser prova
   do que o cliente escreveu, e a decisão de descartar viraria uma decisão sem rastro.

## Normalização de texto

`ingest/normalizacao.py`, `NORM_V = 1`. Determinística, nunca roda de novo em texto já gravado.
**Proibido** remover assinatura, remover a citação ou "limpar" o texto. O trecho citado é
marcado por `citacao_offset` e renderizado em cor secundária — nunca apagado nem escondido.

## Entrada de e-mail

A leitura é sempre da caixa de e-mail da empresa, pelo próprio sistema, por IMAP sobre TLS
(porta 993). O caminho tem duas etapas, nesta ordem:

1. `receber_email` grava o que veio como `EmailRecebido`. **Todo** e-mail lido é gravado,
   inclusive resposta automática, devolução e newsletter. Nada é filtrado por conteúdo.
2. `promover` copia `texto` e `bruto` para uma `Mensagem`. Duas coisas disparam isso:
   - **uma pessoa**, clicando em "Criar chamado" na caixa de entrada — abre chamado novo,
     mensagem de `ordem = 0`;
   - **o próprio ingest**, quando as referências (`In-Reply-To` / `References`) casam com a
     mensagem de um chamado que já existe — entra como resposta, sem clique nenhum.

   A segunda regra não é conveniência: sem ela, cada follow-up de cliente pediria uma decisão
   e a caixa de entrada do Fio viraria uma segunda caixa de e-mail para varrer todo dia.

Não existe classificação automática por conteúdo, pontuação de relevância, IA nem heurística
de assunto. A decisão é humana e explícita.

Os três modos de instalação são **só configuração**, nunca caminhos de código diferentes:

- `IMAP_FOLDER` como variável de ambiente, padrão `INBOX`;
- **pasta observada** (padrão em produção): `IMAP_FOLDER="Demandas"`;
- **caixa inteira** (usado na demonstração): `IMAP_FOLDER="INBOX"`;
- **encaminhamento automático**: o remetente do envelope é o servidor da empresa, então o
  remetente real sai do cabeçalho `From` original, ou de `Reply-To`. **Nunca do envelope**
  (`Return-Path`).

## Acesso

Qualquer funcionário autenticado lê todos os chamados **da sua empresa** e pode publicar
registros em qualquer um deles. Não há permissão por setor no MVP — isso é intencional e
faz parte da tese.

**Não existe senha compartilhada de empresa.** Cada funcionário tem conta própria, porque
`Registro.autor` e `Registro.setor` são a resposta do produto para "quem agiu": com login
compartilhado o feed do chamado vira ficção. A empresa é um container, não uma credencial.
Quem cadastra a empresa vira `papel="admin"`; os outros entram por convite, como
`papel="membro"`. O papel decide **três** coisas e mais nada: convidar pessoas, editar a
lista de setores e mexer na configuração da caixa de e-mail.

### Escopo por empresa

**Todo queryset autenticado é escopado por `request.user.pessoa.empresa`. Nunca
`Empresa.objects.first()`.** O escopo sai da pessoa logada e só dela: não há middleware de
tenant, subdomínio nem cabeçalho de empresa. Toda rota parte de `core/escopo.py`
(`chamados_de`, `registros_de`, `emails_de`, `membros_de`, `convites_de`) — uma rota que
monte `Modelo.objects.filter(...)` na mão faz o escopo depender de quem escreveu a rota, e
é assim que dado de uma empresa vaza para outra.

Chamado de outra empresa devolve **404, nunca 403**: 403 confirmaria que o chamado existe.

O ingest resolve a empresa pela **caixa de onde leu o e-mail** (`caixa_email` contra
`IMAP_USER`), nunca pela primeira empresa do banco.

## Fora de escopo — não implementar

Kanban ou colunas · etapas do chamado · dono/responsável · prazo, SLA ou relógio · qualquer
integração com Jira, ClickUp, Slack ou Zendesk · página pública para o cliente · notificações
por e-mail · Celery ou fila · **permissões por setor** · middleware de tenant, subdomínio por
empresa ou qualquer escopo que não seja `request.user.pessoa.empresa` · edição da descrição,
em qualquer forma · **criação manual de chamado ou mensagem, em qualquer forma** ·
**classificação automática do que chega** (IA, pontuação de relevância, heurística de assunto)
· exclusão de `EmailRecebido` em qualquer operação do produto.

**Qualquer canal que não seja e-mail** — WhatsApp, telefonia, transcrição de áudio. Eram
exemplo do atendimento de uma empresa, não requisito.

**`papel` não é permissão por setor.** `admin` / `membro` decide só quem convida, quem edita
a lista de setores e quem mexe na caixa de e-mail. Não restringe qual chamado alguém lê nem
em qual chamado alguém registra — isso é de todos. "O setor X só vê os chamados do setor X"
é permissão por setor, está fora de escopo, e não se resolve acrescentando valor ao `papel`.

Se algo parecer necessário durante a construção, **pare e pergunte** em vez de implementar.
