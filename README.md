# Aqui Jas

Bot Discord reconstruído do zero, com arquitetura modular e agente IA separado da execução real.

## Fluxo do Agent

`pedido → IA → JSON Plan → validação → preview → confirmação → executor → Discord → auditoria`

A IA **não recebe acesso direto à API do Discord**. Ela apenas propõe ações estruturadas; o executor controlado valida permissões, hierarquia, risco e referências entre ações.

## V1 atual

- Configuração de IA por servidor (`/configia`)
- OpenAI-compatible API
- OpenRouter como padrão (`openrouter/free`)
- Memória conversacional por servidor/usuário
- Auditoria de ações
- Planos JSON versionados
- `plan → preview → execute`
- Referências `$action_X.result.campo`
- Idempotência básica para criação de canais/cargos
- Confirmação para ações de risco médio/alto
- Canais, categorias, slowmode, permissões de canal, cargos e membros

## Comandos

- `/ping`
- `/sobre`
- `/ajuda`
- `/servidor`
- `/configia`
- `/iastatus`
- `/iaremover`
- `/ia`
- `/agente`

## Sincronização dos slash commands

Para desenvolvimento, configure `DEV_GUILD_ID` com o ID do seu servidor. O bot sincroniza os comandos diretamente nessa guilda durante o startup, evitando esperar pela propagação global.

Em produção, ele também sincroniza as guildas conhecidas quando conecta.

## Configuração

```env
DISCORD_TOKEN=...
DEV_GUILD_ID=123456789012345678
DATABASE_PATH=data/bot.sqlite3
LOG_LEVEL=INFO
AI_API_KEY=
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=openrouter/free
```

A chave da IA do servidor é configurada pelo `/configia`. Ela é armazenada por `guild_id` e não é exibida nas respostas do bot.

## Execução local

```bash
pip install -r requirements.txt
python main.py
```

## Próximas camadas

V2: catálogo e executor mais amplo.

V3: moderação.

V4: comunidade.

V5: música.

V6: snapshots e rollback.

V7: Agent completo.
