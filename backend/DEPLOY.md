# Guia de deploy

Este guia cobre como colocar as quatro peças já construídas no ar:
backend (API), banco de dados + storage, dashboard web, e a box de
detecção instalada em cada loja.

Vou sugerir uma combinação concreta de serviços — dá pra trocar por
outra a qualquer momento, já que nada no código está preso a um provedor
específico.

## Visão geral

```
[ Box de detecção, na loja ]  --HTTPS-->  [ Backend (API) ]  <--HTTPS--  [ Dashboard web/mobile ]
                                                  |
                                          [ Postgres gerenciado ]
                                                  |
                                       [ Storage S3-compatível (clipes) ]
```

## 1. Banco de dados (Postgres gerenciado)

Não hospede o Postgres você mesmo — use um serviço gerenciado (backup
automático, menos operação):

- **Opções**: Neon, Supabase, Railway, RDS (AWS), Cloud SQL (GCP)

## 2. Storage dos clipes (S3-compatível)

- **Opções**: Cloudflare R2 (mais barato, sem custo de egress — importante
  porque vídeo pesa), Backblaze B2, ou AWS S3 direto
- Crie o bucket configurado em `CLIPS_BUCKET`, gere uma access key, e
  preencha `S3_ENDPOINT_URL` / `S3_ACCESS_KEY` / `S3_SECRET_KEY`
- Configure uma **política de expiração automática de objetos** no bucket
  (ex: 30 dias) — isso implementa na prática a retenção de clipes que
  discutimos para conformidade com a LGPD, sem precisar de um job
  separado rodando

## 3. Backend (API)

O `Dockerfile` e o `docker-compose.yml` já estão prontos. Para publicar:

- **Opções mais simples**: Railway, Render ou Fly.io — todas fazem
  deploy direto de um Dockerfile com poucos cliques, e têm certificado
  HTTPS automático
- **Opção mais robusta/self-managed**: AWS ECS/Fargate ou um VPS com
  Docker + um proxy reverso (Caddy/Traefik) na frente pro HTTPS

Passos, independente do provedor escolhido:

1. Configure as variáveis de ambiente de `.env.example` no painel do
   provedor (nunca commitar o `.env` de verdade no git)
2. Rode a migração antes do primeiro deploy:
   ```bash
   alembic revision --autogenerate -m "schema inicial"
   alembic upgrade head
   ```
   (rode isso localmente apontando pro banco de produção na primeira
   vez, ou como um passo de deploy/CI depois)
3. Publique a imagem do `Dockerfile`
4. Confirme que `GET /health` responde `{"status": "ok"}` no domínio
   publicado

## 4. Email transacional

Configure de verdade as variáveis `SMTP_*` com um provedor (SendGrid,
Amazon SES, Postmark) — sem isso os convites de equipe não saem. A
maioria tem um plano gratuito suficiente pro volume de um SaaS
começando (SES é o mais barato por email, mas exige "sair da sandbox").

## 5. Dashboard web (o artifact React)

O componente já criado (`app-with-onboarding.jsx`) precisa virar um
projeto real antes de publicar:

```bash
npm create vite@latest dashboard -- --template react
cd dashboard
npm install lucide-react
# copie o conteúdo do .jsx pra src/App.jsx
npm run build
```

Publicar o resultado (pasta `dist/`):

- **Opções**: Vercel, Netlify, Cloudflare Pages — todas com deploy
  automático a cada push no git, e HTTPS de graça

Depois de publicar:
- Ajuste a constante `API_BASE` no topo do arquivo pra apontar pro
  domínio real do backend (passo 3)
- Configure `ALLOWED_ORIGINS` no backend com o domínio do dashboard
  publicado — sem isso o navegador bloqueia as chamadas por CORS
- Configure `APP_BASE_URL` no backend com esse mesmo domínio — é o que
  monta o link dentro do email de convite

## 6. Box de detecção (na loja)

Diferente das outras peças, essa roda fisicamente dentro de cada loja,
não numa nuvem:

- Hardware sugerido para começar: um mini-PC com GPU de entrada (ex:
  NVIDIA Jetson Orin Nano) ou, pra validar sem custo de hardware
  dedicado, um notebook comum rodando o script
- Instale as dependências (`pip install -r requirements.txt` do módulo
  de detecção) direto na box
- Configure, por loja, o `config.py` com a `api_base_url` (domínio do
  backend publicado) e a `api_key` (gerada automaticamente quando a
  loja foi criada — mostrada uma vez na tela de cadastro/"Adicionar loja")
- Rode como serviço persistente (ex: `systemd` no Linux), não só
  `python main.py` manual, pra reiniciar sozinho se cair

## Checklist antes de anunciar pra clientes reais

- [x] `ALLOWED_ORIGINS` restrito ao domínio real do dashboard (não `*`) —
      confirmado em produção (`app.vigialoja.com.br` / `api.vigialoja.com.br`)
- [x] `JWT_SECRET` trocado por um valor aleatório longo, fora do git
- [x] Migrações via Alembic rodando, `AUTO_CREATE_TABLES=false`
- [ ] Política de expiração automática configurada no bucket de clipes
      (bucket R2 criado, mas a regra de expiração em si ainda não foi
      confirmada como configurada)
- [x] Email transacional testado de ponta a ponta (boas-vindas chegando
      via SendGrid) — falta só confirmar SPF/DKIM do domínio pra reduzir
      chance de cair em spam
- [x] HTTPS em todas as pontas (backend, dashboard) — confirmado com
      domínio próprio
- [ ] Backup automático do Postgres confirmado ativo no provedor
      escolhido (Railway)
