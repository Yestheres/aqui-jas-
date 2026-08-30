# Aqui Jas

Bot Discord modular, leve e sem dependência de IA.

## Estrutura

```text
Discord
  ↓
Cogs / comandos
  ↓
Serviços do bot
  ↓
Discord API
  ↓
SQLite / auditoria quando necessário
```

A ideia agora é construir o bot como um bot Discord tradicional e confiável. Recursos mais complexos podem ser adicionados como módulos independentes no futuro.

## Comandos atuais

- `/ping` — verifica a latência.
- `/sobre` — mostra informações do bot.
- `/ajuda` — mostra os comandos disponíveis.
- `/servidor` — mostra informações do servidor.

## Configuração

```env
DISCORD_TOKEN=your_bot_token_here
DEV_GUILD_ID=123456789012345678
DATABASE_PATH=data/bot.sqlite3
LOG_LEVEL=INFO
```

`DEV_GUILD_ID` é opcional e serve para sincronização imediata dos slash commands durante os testes.

## Execução

```bash
pip install -r requirements.txt
python main.py
```

Nunca coloque tokens no Git.
