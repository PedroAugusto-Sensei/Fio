# Roteiro — contas Gmail para testar o ingest do Fio

Para colar no **Claude Desktop** (navegador integrado), deixando o seu Chrome livre.

Antes de colar: escolha um `<sufixo>` curto e troque em **todos** os lugares
(ex.: `hk26` → `fio.atendimento.hk26@gmail.com`).

## As duas contas

| Papel | Endereço | Para quê |
|---|---|---|
| **Empresa** | `fio.atendimento.<sufixo>@gmail.com` | a caixa que o Fio lê por IMAP |
| **Clientes** | `fio.clientes.<sufixo>@gmail.com` | envia por SMTP, simulando todos os clientes |

Duas coisas são sempre suas, e o roteiro para nelas: o desafio **"não sou um robô"**, se aparecer,
e o **telefone + código SMS**.

---

## Parte 1 — Criar as contas

```
Preciso criar duas contas Google pessoais para testar uma integração IMAP de um projeto meu.
Use o navegador integrado. Faça o processo abaixo INTEIRO para a conta 1 e depois repita
para a conta 2.

  Conta 1 (empresa):  fio.atendimento.<sufixo>@gmail.com
  Conta 2 (clientes): fio.clientes.<sufixo>@gmail.com

Regras que valem o tempo todo:
- Nos pontos marcados PARADA, pare e me devolva o controle. Não tente resolver sozinho.
- Se o Google recusar alguma etapa 3 vezes seguidas, pare e me explique o que aconteceu,
  em vez de continuar tentando.
- Não escreva nenhuma senha em texto na sua resposta, exceto as senhas de app do passo 10.

Passos:
1.  Abra https://accounts.google.com/signup
2.  Preencha nome e sobrenome ("Fio" / "Atendimento", depois "Fio" / "Clientes") e avance.
3.  Preencha data de nascimento e gênero (o Google exige) e avance.
4.  Na escolha do endereço, use a opção de criar o próprio endereço Gmail e digite o
    endereço da conta da vez. Se estiver ocupado, acrescente dígitos ao sufixo.
5.  Defina uma senha forte e me diga apenas que a definiu, guardando-a para o passo final.
6.  PARADA 1 — se aparecer qualquer desafio de "confirme que não é um robô", pare, tire um
    screenshot e me avise.
7.  PARADA 2 — na tela de telefone, pare e me avise. Eu informo o número e o código SMS.
    O mesmo número costuma servir para as duas contas.
8.  Pule "e-mail de recuperação" e aceite os Termos.
9.  Abra https://myaccount.google.com/signinoptions/twosv e ligue a Verificação em duas
    etapas com o mesmo telefone. Sem isso, o passo 10 não existe.
10. Abra https://myaccount.google.com/apppasswords, crie uma senha de app chamada "Fio" e
    me mostre os 16 caracteres gerados.
11. NÃO procure a opção de ligar IMAP. O Google removeu esse botão em janeiro de 2025 e o
    IMAP fica sempre ativo em contas pessoais.

Ao final, me devolva uma lista com: os dois endereços criados, as duas senhas de app, e as
duas senhas das contas.
```

---

## Parte 2 — Label e filtro (modo "pasta observada")

Só na conta da **empresa**, depois que ela existir. É o que prova que os modos de instalação do
Fio são só configuração.

```
Na conta Gmail fio.atendimento.<sufixo>@gmail.com (já logada), configure:
1. Abra https://mail.google.com/mail/u/0/#settings/labels e crie um label chamado Demandas.
2. Vá em https://mail.google.com/mail/u/0/#settings/filters e crie um filtro novo.
3. No campo "Para", coloque fio.atendimento.<sufixo>@gmail.com. Avance para criar o filtro.
4. Marque "Pular a Caixa de Entrada (Arquivar)" e "Aplicar o marcador: Demandas".
5. Crie o filtro e me confirme que ele aparece na lista de filtros.
```

---

## O que me trazer de volta

Cole aqui na conversa do Claude Code:

- os dois endereços;
- as duas senhas de app (16 caracteres cada).

Elas vão para `backend/.env`, que já está no `.gitignore`. Nenhuma credencial entra em arquivo
versionado — nem em `.env.example`, nem no README, nem em script.

---

## Detalhes que costumam morder

- **A senha de app só existe depois do 2FA ligado.** É por isso que o passo 9 vem antes do 10.
- **A senha de app é revogada quando a senha da conta muda.** Se o ingest parar de autenticar do
  nada, é a primeira coisa a checar.
- **A senha de app aparece com espaços** na tela do Google (`abcd efgh ijkl mnop`). No `.env` vai
  **sem espaços**.
- **Não procure onde ligar IMAP.** O Google removeu o botão em janeiro de 2025; IMAP fica sempre
  ativo em contas pessoais. Se você não achar a opção, está tudo certo.
- **O mesmo telefone costuma servir para as duas contas.** Se o Google recusar na segunda, me
  avise antes de arrumar outro número — pode ser mais simples usar uma conta Gmail que você já tem
  como a de clientes.

---

## Por que este roteiro existe

O Fio tem uma tese forte: a única origem de uma `Mensagem` é o ingest de e-mail (invariante 7 do
`CLAUDE.md`), e não existe plano B. Mas essa origem nunca foi exercitada contra um servidor de
verdade — `backend/.env` ainda está com os placeholders do example, e todos os testes de ingest
usam um objeto falso no lugar do `imap_tools` ("sem servidor IMAP", diz o próprio docstring).

Com as duas contas na mão, dá para fechar o aceite que o `TASKS.md` cobra no item 7 e que continua
em aberto: *"encaminhar um e-mail de verdade cria o chamado"*.
