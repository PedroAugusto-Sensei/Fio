# Fio — ordem de execução

- [x] **1. Base** — projeto Django, Postgres no docker-compose, `settings` com env, app `core`,
      modelos da seção 4, migrations, admin com `Mensagem` somente leitura.
      *Aceite:* `seed_demo` roda e o admin mostra chamados, mensagens e registros.
- [x] **2. Tela do chamado (fatia vertical)** — endpoint `GET /chamados/{id}`, front com o bloco
      da descrição e o feed de registros, dados vindos do seed.
      *Aceite:* abrir `/chamados/1` mostra o e-mail íntegro no topo e os registros em ordem.
- [x] **3. Publicar registro** — `POST /chamados/{id}/registros`, modal no front, situação
      obrigatória, feed atualiza sem recarregar a página.
      *Aceite:* publicar um registro muda a situação do chamado e não toca em nenhuma mensagem.
- [x] **4. Lista de chamados** — `GET /chamados` com a projeção da situação, tabela, chips de
      filtro, trecho do cliente visível.
      *Aceite:* a lista abre sem N+1 e mostra "sem registro".
- [x] **5. Login e sessão** — telas e proteção de rota.
      *Aceite:* deslogado cai no login; logado, `/me` devolve nome e setor.
- [x] **5.1. Cadastro de empresa e contas individuais** — `Pessoa.papel`, `Convite`,
      `core/escopo.py`, `POST /auth/registrar-empresa`, convites, `/membros`,
      `PUT /empresa`, telas `/criar-conta`, `/convite/:token` e `/configuracoes/membros`.
      Não existe senha compartilhada de empresa: `Registro.autor` é a resposta para "quem
      agiu", e com login compartilhado o feed vira ficção.
      *Aceite:* pessoa da empresa A recebe 404 em chamado da empresa B, e a lista de A não
      mostra nada de B; membro (não admin) recebe 403 ao convidar ou editar a empresa.
- [x] **6. Normalização** — `normalizacao.py`, testada com e-mails reais em fixture
      (`tests/fixtures/*.eml`).
      *Aceite:* testes 4 e 6 da seção 12 passam.
- [x] **7. Ingest IMAP** — comando, dedupe, threading, anexos, `IMAP_FOLDER` por ambiente e
      remetente real vindo do `From` original / `Reply-To` (nunca do envelope).
      *Aceite:* testes 2 e 3 passam; encaminhar um e-mail de verdade cria o chamado.
- [x] **8. Busca** — `SearchVectorField`, índices GIN, parâmetro `busca`.
      *Aceite:* buscar uma palavra que só existe no corpo do e-mail encontra o chamado.
- [x] **9. PWA + link** — manifesto, ícones, botão "Copiar link do chamado".
      *Aceite:* o navegador oferece instalar; o link colado abre direto no chamado.
- [x] **10. Acabamento** — estados vazios, erros em português, responsivo até 768px.
- [x] **11. Caixa de entrada** — `EmailRecebido` entre a caixa e o chamado, conexão IMAP real
      sobre TLS com timeout e uma repetição, `GET /emails`, `promover`, `descartar`, tela com
      contador de pendentes.
      *Aceite:* encaminhar um e-mail de verdade faz ele aparecer na caixa em até um minuto;
      "Criar chamado" abre o chamado com as palavras exatas; responder aquele e-mail entra no
      mesmo chamado sozinho.

## Não iniciada

- [ ] **Caixa de e-mail por empresa** — exige credencial por empresa (senha de app
      criptografada no banco, ou OAuth), ingest iterando sobre as empresas com caixa
      configurada em vez de ler uma única variável de ambiente, e tela de configuração
      para o admin. **Escopo real, não é ajuste de campo.**
      Hoje: `IMAP_*` é uma configuração por instalação, e a empresa é resolvida por
      `caixa_email` contra `IMAP_USER`. Empresa criada pela interface nasce sem caixa e
      não recebe chamado — `/configuracoes/membros` diz isso em vermelho, e é só o que
      se pode dizer com honestidade enquanto a credencial não for por empresa.

## A invariante 7 depois da caixa de entrada

O ingest não cria mais `Chamado` direto. Ele grava `EmailRecebido`; `Mensagem` só nasce de um
`EmailRecebido` já gravado, copiando `texto` e `bruto` sem alteração. A garantia que sustenta
o produto continua de pé: nenhum ser humano escreve a descrição. O que o humano passa a fazer
é escolher **qual** e-mail vira chamado.

## O escopo por empresa (tarefa 5.1)

Antes havia uma empresa só, criada pelo seed, e `.filter(empresa=...)` espalhado pelas
rotas passava despercebido quando faltava. Com cadastro pela interface, faltar um filtro
é vazamento de dado entre empresas. Por isso o escopo saiu das rotas e virou um lugar só:
`core/escopo.py`. Nenhuma rota monta `Modelo.objects.filter(...)` na mão, e o ingest
resolve a empresa pela caixa de onde leu o e-mail — nunca `Empresa.objects.first()`.

## Removido pela correção de escopo

A entrada manual saiu do produto (invariante 7 do CLAUDE.md). Foram apagados, não desativados:
`POST /chamados`, `ChamadoIn`, `criar_chamado_colado`, o campo `Mensagem.canal` e a constante
`CANAIS`, o botão "Novo chamado" e o modal correspondente. Não existe plano B para o IMAP.
