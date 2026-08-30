# Aqui Jas

Bot Discord modular com agente IA controlado.

## Arquitetura

```text
Discord
  ↓
Cogs / comandos
  ↓
AgentService
  ↓
IA gera um Plan JSON
  ↓
Validator (schema, risco, IDs e dependências)
  ↓
Preview
  ↓
Confirmação
  ↓
Executor controlado
  ↓
Discord API
  ↓
Audit log (SQLite)
```

A IA não recebe acesso direto à API do Discord. Ela propõe ações; o executor valida permissões e executa apenas ações presentes no catálogo.

## V1

- IA configurável por servidor com `/configia`
- Fallback global opcional por variáveis de ambiente
- Memória conversacional por servidor + usuário
- `/ia`, `/iastatus`, `/iaremover`
- `/agente` com plan → preview → confirmação → execução
- IDs como alvo principal
- Referências entre ações (`$action_1.result.channel_id`)
- Idempotência básica para criação de canais e cargos
- Verificação de permissões do bot
- Verificação de hierarquia de cargos
- Risco alto com confirmação obrigatória
- `stop_and_report` para falhas
- Auditoria das ações executadas/falhas
- V1 do Agent focada em canais, cargos, permissões e mensagens

### Ações do Agent na V1

`create_channel`, `update_channel`, `delete_channel`, `move_channel`, `set_channel_permissions`, `sync_channel_permissions`, `create_role`, `update_role`, `delete_role`, `assign_role`, `remove_role`, `send_message`, `delete_message`.

Ações de moderação de membros como ban/kick/timeout não ficam expostas ao Agent na V1. A intenção é tratá-las em uma camada própria de moderação posteriormente.

## IA

Cada servidor pode usar sua própria chave, endpoint e modelo. A configuração do servidor tem prioridade.

Opcionalmente, para desenvolvimento, é possível definir no ambiente da hospedagem:

```env
AI_API_KEY=
AI_BASE_URL=https://openrouter.ai/api/v1
AI_MODEL=openrouter/free
```

Essas variáveis funcionam apenas como fallback quando o servidor não possui uma configuração própria.

## Slash commands

Para sincronização imediata em desenvolvimento, defina:

```env
DEV_GUILD_ID=123456789012345678
```

O bot também sincroniza os comandos nas guilds em que está conectado.

## Execução local

```bash
pip install -r requirements.txt
python main.py
```

Nunca coloque tokens ou API keys no Git.
