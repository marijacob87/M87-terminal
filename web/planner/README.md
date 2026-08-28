# M87 Planner Web

PWA estática do Planner Semanal. Ela funciona offline no navegador e pode ser instalada no iPad pelo Safari em **Compartilhar → Adicionar à Tela de Início**.

## Desenvolvimento local

Abra a pasta com um servidor estático (por exemplo, `python3 -m http.server 8080 -d web/planner`) e acesse `http://localhost:8080`.

Para testar também a sincronização local, inicie o servidor privado incluído:

```bash
M87_PLANNER_WORKSPACE_KEY='crie-uma-chave-longa' \
python3 scripts/planner_web_server.py
```

Para uso fora da rede local, a publicação Cloudflare usa os arquivos em `cloudflare/`, o esquema em `cloudflare/schema.sql` e um banco D1 — é quando computador, iPad e navegador passam a ver a mesma base em tempo real.

## Migração do Planner atual

Antes de ativar a PWA, exporte uma cópia dos seus dados atuais sem modificar o Planner desktop:

```bash
python3 scripts/export_planner_to_web.py --output /tmp/planner-web.json
```

Depois que a URL Cloudflare estiver publicada, envie essa cópia usando:

```bash
python3 scripts/import_planner_to_cloudflare.py \
  --endpoint https://m87-planner.mariane-rjacob.workers.dev
```

O comando pede a chave sem exibi-la no Terminal. Quando a URL HTTPS estiver pronta, defina `M87_PLANNER_WEB_URL` no ambiente que inicia o M87; então o comando `TODO` abrirá essa mesma PWA. Sem essa variável, ele continua abrindo o Planner desktop atual normalmente.

## Sincronização

O arquivo `app.js` mantém a interface e os dados locais e já possui sincronização contínua por uma API privada: ele busca os dados na abertura e envia alterações 500 ms após a última edição. Na publicação Cloudflare, a chave de pareamento é digitada uma única vez no próprio aparelho e não é incluída nos arquivos publicados.

Enquanto a API não estiver configurada, a versão web continua segura e utilizável offline, mas cada dispositivo guarda sua própria cópia local.
