# Rodando o projeto local pela primeira vez

Este guia parte do zero: você acabou de baixar os arquivos e quer ver o
backend + banco + dashboard funcionando no seu PC antes de pensar em
deploy de verdade.

Duas formas de seguir isso:
- **Manual**, comando por comando (abaixo)
- **Pedindo pro Claude Code fazer** — no fim do guia tem um prompt pronto
  pra colar

## 0. Organize as pastas

Baixe os arquivos que criei nesta conversa e organize assim:

```
meu-projeto/
  backend/              (tudo que veio da pasta backend/)
  dashboard/             (vamos criar agora, no passo 3)
  edge-detection/         (o módulo de detecção, opcional pra este teste)
```

## 1. Pré-requisitos

Instale, se ainda não tiver:

- **Docker Desktop** — https://www.docker.com/products/docker-desktop
  (sobe o Postgres sem precisar instalar banco na mão)
- **Node.js 18+** — https://nodejs.org (pro dashboard)
- **Python 3.12+** — só necessário se for rodar o backend fora do Docker

## 2. Backend + banco de dados

```bash
cd backend
cp .env.example .env
```

Abra o `.env` criado e ajuste pelo menos:
- `JWT_SECRET` — qualquer texto aleatório longo, só pra testar local
- Deixe `AUTO_CREATE_TABLES=true` por enquanto (cria as tabelas
  automaticamente, sem precisar rodar Alembic ainda — mais rápido pra
  um primeiro teste)
- Pode deixar as variáveis de `S3_*` e `SMTP_*` em branco por ora — o
  upload de clipe e o envio de convite por email só vão falhar
  silenciosamente até você configurar um provedor real

Suba tudo com Docker:

```bash
docker compose up --build
```

Isso sobe o Postgres **e** a API juntos. Deixe esse terminal aberto.

Teste se subiu:

```bash
curl http://localhost:8000/health
# deve responder {"status":"ok"}
```

A documentação interativa da API fica em `http://localhost:8000/docs` —
útil pra testar endpoints direto do navegador sem precisar do dashboard.

## 3. Dashboard web

Em outro terminal:

```bash
npm create vite@latest dashboard -- --template react
cd dashboard
npm install lucide-react
```

Abra `dashboard/src/App.jsx` no editor, apague o conteúdo, e cole o
conteúdo do arquivo `app-with-onboarding.jsx` que eu criei.

Rode:

```bash
npm run dev
```

Abra o link que aparece no terminal (geralmente `http://localhost:5173`).
Como o `API_BASE` no topo do arquivo já está apontando pra
`http://localhost:8000`, ele deve conversar direto com o backend que
você subiu no passo 2.

## 4. Testando de ponta a ponta

1. No dashboard, clique em **"Criar conta"**
2. Preencha empresa, primeira loja, seus dados — isso chama o backend
   de verdade e cria os registros no Postgres
3. Você cai direto no painel, já logado
4. Pra ver um alerta de teste aparecer, use `http://localhost:8000/docs`,
   ache o endpoint `POST /v1/stores/{store_id}/alerts` e envie um alerta
   de teste manualmente (o `store_id` você pega na tela de "Adicionar
   loja" ou direto no banco)

## 5. (Opcional) Módulo de detecção com a webcam

Só faça isso depois do resto estar funcionando.

```bash
cd edge-detection
pip install -r requirements.txt
```

Edite `config.py`: troque o `source` da câmera de exemplo por `"0"`
(webcam do notebook), e o `api_key`/`store_id` pelos valores reais da
loja que você criou no passo 4.

```bash
python main.py
```

## Se preferir pedir pro Claude Code fazer tudo isso

Depois de instalar o Claude Code (veja a resposta anterior) e abrir o
terminal dentro da pasta `meu-projeto/`, cole:

```
Tenho um backend FastAPI na pasta backend/, com Dockerfile e
docker-compose.yml prontos, e um arquivo dashboard/app-with-onboarding.jsx
que é um componente React. Quero rodar tudo localmente pela primeira vez:

1. Configure o .env do backend a partir do .env.example (gere um
   JWT_SECRET aleatório, deixe AUTO_CREATE_TABLES=true)
2. Suba o backend com docker compose up --build
3. Crie um projeto Vite novo dentro de dashboard/, instale lucide-react,
   e coloque o conteúdo de app-with-onboarding.jsx como o App.jsx
4. Rode o dashboard com npm run dev
5. Confirme que http://localhost:8000/health responde OK antes de
   terminar
```

Ele vai pedir permissão antes de cada passo que instala algo ou roda
comando — é só ir aprovando.

## Problemas comuns

- **`docker compose up` falha com porta em uso** — algo já está usando
  5432 (Postgres) ou 8000 (API) no seu PC. Feche o que estiver usando,
  ou troque a porta no `docker-compose.yml`
- **Dashboard carrega mas dá erro de CORS** — confirme que o backend
  está com `ALLOWED_ORIGINS` incluindo `http://localhost:5173`. O
  backend recusa subir com `ALLOWED_ORIGINS` vazio ou `*` (proteção
  contra roubo de sessão entre sites), então é preciso listar a origem
  explicitamente mesmo em teste local
- **`npm create vite` pede confirmação e trava num script não
  interativo** — responda as perguntas manualmente na primeira vez em
  vez de automatizar
