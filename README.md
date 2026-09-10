# Fio

Os chamados de clientes ficam registrados **com as palavras originais do cliente como
descrição**, e cada setor da empresa acrescenta o que fez.

O chamado nasce de um e-mail que o próprio sistema lê da caixa da empresa. Todo e-mail lido
cai na **caixa de entrada do Fio**, e uma pessoa decide quais viram chamado — ela escolhe
*qual* e-mail vira chamado, nunca *o que* está escrito nele. A descrição do chamado é o corpo
desse e-mail, íntegro, e **nunca é editável**. Abaixo dela, os setores publicam registros em
ordem de data, cada um declarando em que situação deixou o chamado. Todos os funcionários da
empresa leem todos os chamados dela.

Cada funcionário tem **conta própria** — não existe senha compartilhada de empresa. É
`Registro.autor` que responde "quem agiu" no feed do chamado, e com login compartilhado esse
feed viraria ficção.

O Fio **não gerencia fluxo de trabalho**: não tem kanban, etapas, dono, prazo nem integração
com a ferramenta de fluxo da empresa. Ela continua usando a dela.

As regras que não podem ser quebradas estão logo abaixo e, na íntegra, em
[CLAUDE.md](CLAUDE.md). A ordem de execução e o que já foi feito estão em
[TASKS.md](TASKS.md).

---

## As invariantes — nenhuma pode ser quebrada por conveniência

1. **`Mensagem` é imutável.** Depois de criada, nunca sofre `UPDATE`. Correção do cliente é
   uma mensagem nova, nunca edição da anterior.
2. **Não existe campo `descricao` em `Chamado`.** A descrição é a `Mensagem` de `ordem = 0`.
   Se o campo existisse, alguém acabaria escrevendo nele.
3. **A situação do chamado não é armazenada em `Chamado`.** É a `situacao` do `Registro` mais
   recente, obtida por projeção. Chamado sem registro não tem situação — mostra "sem registro".
4. **Situação nunca é editada sozinha.** Só muda junto com um registro novo. Não existe
   endpoint nem tela para "atualizar status".
5. **O MIME cru é gravado antes de qualquer parse.** Se o parser errar, reprocessa-se sem
   pedir nada ao cliente.
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

Além delas, uma regra de escopo que vale para todo código autenticado: **todo queryset é
filtrado por `request.user.pessoa.empresa`; nunca `Empresa.objects.first()`.** Ver
[Escopo por empresa](#escopo-por-empresa).

---

## Como rodar

Pré-requisitos: Docker (só para o Postgres), Python 3.11+ e Node 18+.

```bash
docker compose up -d                     # Postgres 16 na porta 5433

cd backend
uv venv .venv && uv pip install --python .venv -e ".[dev]"   # ou python -m venv + pip
cp .env.example .env
python manage.py migrate
python manage.py seed_demo
python manage.py runserver               # :8000

cd ../frontend
npm install
npm run dev                              # :5173, proxy /api -> :8000
```

Abra <http://localhost:5173>. Entre com `autor.1` … `autor.5` (ou `admin`), senha `fio12345`
— `autor.1` é o administrador da empresa de demonstração. Para começar do zero em vez do
seed, use **Criar conta da minha empresa** na tela de login.
O admin do Django fica em <http://127.0.0.1:8000/admin/>.

> A porta do Postgres é **5433** porque 5432 costuma estar ocupada por uma instalação nativa.
> Para trocar: `POSTGRES_PORT=5432 docker compose up -d` e ajuste `DATABASE_URL` no `.env`.

### Testes

```bash
cd backend && python -m pytest       # precisa do Postgres de pé
cd backend && python -m pytest -m imap   # + a conexão IMAP real, se houver credencial
cd frontend && npm run typecheck
```

O teste de conexão IMAP fica fora da rodada padrão (`addopts = -m "not imap"`) e é pulado
quando não há credencial no ambiente.

Os testes rodam contra Postgres de verdade porque o produto usa `SearchVectorField` e índices
GIN — testar em outro banco não provaria nada. Os e-mails usados nos testes são arquivos MIME
de verdade, em `backend/tests/fixtures/*.eml`.

---

## Entrada de e-mail

**A única origem de uma mensagem é a caixa de e-mail da empresa, lida pelo próprio sistema.**
Não existe tela, campo, endpoint nem ação de admin que crie uma mensagem a partir de texto
digitado (invariante 7). Se um funcionário precisasse copiar e colar o e-mail para dentro do
sistema, o sistema não resolveria o problema que existe para resolver.

O caminho tem duas etapas:

1. **Ler e guardar.** Todo e-mail não lido da pasta configurada vira um `EmailRecebido` —
   inclusive resposta automática, devolução e newsletter. Nada é filtrado por conteúdo, e o
   MIME cru é gravado antes de qualquer parse.
2. **Decidir.** Na caixa de entrada do Fio (`/emails`), alguém clica em **Criar chamado** ou
   em **Descartar**. Promover copia `texto` e `bruto` para a mensagem de `ordem = 0`, com o
   mesmo `sha256`; descartar carimba `descartado_em` e o e-mail continua consultável.

**Resposta do cliente não passa pela caixa de entrada.** Quando `In-Reply-To` / `References`
casam com a mensagem de um chamado que já existe, o e-mail entra direto no chamado, sem
clique. Sem isso, cada follow-up pediria uma decisão e a caixa viraria uma segunda caixa de
e-mail para varrer todo dia.

Não existe classificação automática por conteúdo, pontuação de relevância, IA nem heurística
de assunto. A decisão é humana e explícita.

```bash
python manage.py ingest_email
```

Por cron, a cada minuto:

```cron
*/1 * * * * cd /app/backend && python manage.py ingest_email
```

### Ligar numa caixa de verdade

Em `backend/.env` — que está no `.gitignore`. **Nenhuma credencial entra em arquivo
versionado**, nem no `.env.example`, nem no README, nem em script:

```
IMAP_HOST=imap.gmail.com
IMAP_PORT=993
IMAP_USER=<endereço da caixa>
IMAP_PASSWORD=<senha de app, 16 caracteres, sem espaços>
IMAP_FOLDER=INBOX
```

A empresa é a **dona da caixa lida**: o ingest resolve `Empresa` por `caixa_email` contra o
`IMAP_USER` configurado, e nunca pela primeira empresa do banco.

Empresa criada pela interface nasce sem caixa (`caixa_email` vazio) e **não recebe chamado
nenhum**. O que falta ali não é o campo do endereço: é a **credencial**. `IMAP_PASSWORD` é
configuração por instalação, não por empresa — preencher só o endereço faria a tela dizer
"configurada" com nada funcionando por trás. Por isso `/configuracoes/membros` mostra a
situação da caixa em vermelho, somente leitura, e não oferece um campo para editá-la.
Caixa por empresa exige credencial por empresa, e está registrada em
[TASKS.md](TASKS.md) como tarefa própria, não iniciada.

TLS sempre: `MailBox` na 993, sem caminho em texto claro. Só mensagens `UNSEEN` são lidas, e
cada uma é marcada como lida **depois** do commit — se a transação falhar, o e-mail continua
não lido e volta na rodada seguinte. Falha de conexão gera uma linha de log por rodada (não
uma por tentativa) e o cron segue. Anexo acima de `ANEXO_MAX_BYTES` (10 MB por padrão) é
recusado e registrado; o texto do cliente entra do mesmo jeito.

A leitura fica atrás de `ingest.caixa.LeitorDeCaixa` (`mensagens_nao_lidas` / `marcar_lida`),
com `LeitorIMAP` como implementação. Se um dia a caixa for para a API REST do Gmail com OAuth,
entra outra implementação ali e o comando não muda.

Os três modos de instalação são **só configuração**, não caminhos de código diferentes:

| Modo | Configuração | Quando usar |
|---|---|---|
| Pasta observada | `IMAP_FOLDER=Demandas` | Padrão em produção: uma regra no servidor move para a pasta o que é demanda |
| Caixa inteira | `IMAP_FOLDER=INBOX` | Demonstração, e caixas dedicadas a atendimento |
| Encaminhamento automático | o servidor reencaminha para a caixa lida | Quando a caixa de atendimento já existe e não pode mudar |

No encaminhamento automático o remetente do envelope é o servidor da empresa. O remetente real
sai do `From` original (inclusive de um original embutido como `message/rfc822`) ou do
`Reply-To` — **nunca do envelope** (`Return-Path`). Ver `ingest/entrada.py::remetente_real`.

Não há plano B para o IMAP: se o ingest está fora do ar, não entra chamado. É consequência
aceita da invariante. O que cobre a demonstração é o `seed_demo`.

---

## Como está montado

```
fio/
  docker-compose.yml          # só o Postgres
  CLAUDE.md                   # invariantes — leia antes de mexer
  TASKS.md                    # ordem de execução
  backend/
    fio/                      # settings, urls, wsgi
    core/                     # models, escopo.py, admin, migrations, seed_demo
    ingest/                   # normalizacao.py, entrada.py, caixa.py, ingest_email
    api/                      # router django-ninja, schemas
    tests/                    # + fixtures/*.eml
  frontend/
    src/
      api/                    # client.ts, tipos.ts
      pages/                  # Login, CriarConta, Convite, Caixa, Chamados, Chamado, Membros
      components/             # Layout, ModalRegistro, TextoDoCliente, …
      styles/tokens.css       # as cores da seção 10 da especificação
```

### O que o modelo garante

- `Mensagem` é imutável: `save()` recusa qualquer objeto que já tenha `pk`, e `delete()` recusa
  exclusão avulsa. Correção do cliente é mensagem nova.
- `Mensagem` só nasce de um `EmailRecebido` já gravado: `gravar_mensagem(chamado=, origem=)`
  não tem parâmetro de texto, e `save()` recusa qualquer objeto que não tenha passado por lá.
  Antes de copiar, o `sha256` é reconferido — se não bate, nada é criado.
- `EmailRecebido` é imutável no conteúdo (`save()` levanta exceção se `texto`, `bruto`,
  `sha256`, `remetente_email`, `assunto` ou `recebido_em` mudarem) e nunca é apagado: descartar
  só carimba `descartado_em`.
- `Chamado` não tem campo `descricao` nem `situacao`. A descrição é a mensagem de `ordem = 0`;
  a situação é a do registro mais recente, obtida por projeção (`chamados_com_situacao`).
- Editar registro não faz `UPDATE`: cria uma versão nova apontando `versao_anterior` para a
  antiga, que continua no banco e acessível em `/api/chamados/{id}/registros?historico=1`.
- O MIME cru é gravado antes de qualquer parse, então dá para reprocessar sem pedir nada ao
  cliente.
- O trecho citado do e-mail é **marcado** por `citacao_offset` e pintado em cor secundária —
  nunca apagado nem escondido.
- `Pessoa` tem `papel` (`admin` / `membro`) e `Convite` guarda o link que deixa alguém criar a
  própria conta dentro de uma empresa. O papel decide três coisas: convidar, editar a lista de
  setores e mexer na caixa. Ler chamado e publicar registro é de todos.
- Tirar um setor de `Empresa.setores` **não** altera o `setor` gravado em nenhum `Registro`:
  lá é cópia histórica de quem agiu.

### Escopo por empresa

Todo queryset autenticado é escopado por `request.user.pessoa.empresa`, e por mais nada.
Não há middleware de tenant, subdomínio nem cabeçalho de empresa: o escopo sai da pessoa
logada. Toda rota parte de `core/escopo.py` — `chamados_de`, `registros_de`, `emails_de`,
`membros_de`, `convites_de` — em vez de montar `Modelo.objects.filter(...)` na mão, porque
um filtro esquecido em uma rota é vazamento de dado entre empresas.

Chamado de outra empresa devolve **404, nunca 403**: 403 confirmaria que o chamado existe.

### API

| Método | Rota |
|---|---|
| POST | `/api/auth/login`, `/api/auth/logout`, `/api/auth/registrar-empresa` |
| GET | `/api/me`, `/api/setores`, `/api/membros` |
| GET | `/api/chamados` — `busca`, `situacao`, `cliente`, `meus`, `page` |
| GET | `/api/chamados/{id}`, `/api/chamados/{id}/registros?historico=1` |
| POST | `/api/chamados/{id}/registros` |
| PUT | `/api/registros/{id}` |
| GET | `/api/emails` — `situacao` (`pendente`, `promovido`, `descartado`, `todos`), `page` |
| GET | `/api/emails/contagem`, `/api/emails/{id}` |
| POST | `/api/emails/{id}/promover`, `/api/emails/{id}/descartar` |
| POST | `/api/convites` *(admin)* — devolve `{token, url, expira_em}` |
| GET | `/api/convites` *(admin)* · DELETE `/api/convites/{id}` *(admin)* revoga |
| GET | `/api/convites/{token}` — público; 404 se não existe, 410 se usado ou expirado |
| POST | `/api/convites/{token}/aceitar` — público, cria a conta e abre a sessão |
| PUT | `/api/empresa` *(admin)* — nome e lista de setores |

Não existe `POST /api/chamados`, nem endpoint de "atualizar status": chamado nasce de um e-mail
promovido, e situação só muda junto com um registro novo. `promover` e `descartar` **não aceitam
corpo na requisição** — não há schema de entrada, e o que vier é ignorado. Promover um e-mail
que já foi promovido ou descartado devolve `409`.

---

## Contas

**A senha é individual, uma por pessoa. Não existe senha compartilhada de empresa.**

*Por quê:* `Registro.autor_id` e `Registro.setor` são a resposta do produto para "quem agiu".
O feed do chamado existe para mostrar qual pessoa de qual setor fez o quê, e quando. Com
login compartilhado, `autor_id` apontaria sempre para a mesma conta genérica e o feed viraria
ficção — diria que "a empresa" agiu, que é exatamente o que ninguém precisa saber. A empresa
é um container, não uma credencial.

Quem cadastra a empresa em **/criar-conta** vira `papel="admin"`; o resto do time entra por
convite, cada um com a própria conta e o próprio setor.

O papel decide **três** coisas e nada além: convidar pessoas, editar a lista de setores e
mexer na configuração da caixa de e-mail. **Papel não é permissão por setor** — qualquer
pessoa autenticada, admin ou membro, lê todos os chamados da sua empresa e publica registro
em qualquer um deles.

| Tela | O que faz |
|---|---|
| `/criar-conta` | Nome da empresa, setores como chips editáveis e os seus dados. Um passo, sem wizard. A configuração IMAP não entra aqui |
| `/convite/:token` | "Você foi convidado para *Empresa*": nome, e-mail, senha e setor. Link usado, revogado ou expirado mostra estado vazio com link para o login |
| `/configuracoes/membros` | Só para admin: a situação da caixa de e-mail (somente leitura), quem está na empresa, botão **Convidar pessoa** (gera o link e copia) e a lista de convites esperando, com opção de revogar |

O Fio **não manda e-mail de convite** — notificação por e-mail está fora de escopo. O link
vale 7 dias, serve uma vez e é entregue pelo canal que a empresa já usa.

O e-mail é o nome de usuário: quem se cadastra pela interface entra com o próprio e-mail.
As contas do `seed_demo` continuam entrando por `autor.1` … `autor.5`.

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

> **Permissão por setor continua fora de escopo, e `papel` não é isso.** `papel`
> (`admin` / `membro`) decide só quem convida, quem edita a lista de setores e quem mexe na
> caixa de e-mail. Ele **não** restringe qual chamado alguém lê nem em qual chamado alguém
> registra — isso é de todos, e é parte da tese. Se aparecer um pedido de "o setor X só vê os
> chamados do setor X", é permissão por setor, está fora de escopo, e não se resolve
> acrescentando valor ao `papel`.

Se algo parecer necessário durante a construção, **pare e pergunte** em vez de implementar.

---

## PWA

`display: standalone`, `start_url: /chamados`, ícones 192 e 512. O service worker existe só
para o navegador oferecer instalar — ele **não** cacheia resposta de API, porque chamado velho
na tela seria pior que tela vazia.


### IMAP pelo aplicativo

Quem cadastrou a empresa pode abrir **Configurar IMAP** no menu e informar servidor,
usuário, endereço da caixa, senha e pasta. A conexão usa TLS na porta 993.
Salvar guarda os dados; a conexão será usada pelo próximo `ingest_email`
(o agendamento do comando continua necessário).

As credenciais são individuais por empresa e a senha é cifrada com chave derivada
 de `SECRET_KEY`. Mantenha essa chave secreta, estável e incluída no procedimento
 de backup; trocar a chave exige cadastrar novamente as senhas IMAP.
Após atualizar, instale as dependências do backend e rode `python manage.py migrate`.
A migração considera o primeiro administrador das empresas existentes como criador,
conforme o fluxo de cadastro anterior. Novos cadastros gravam o criador explicitamente.
O comando sem `--empresa` lê as caixas configuradas no app e preserva a caixa legada
 do ambiente quando ela pertence a uma empresa ainda sem configuração no app.
