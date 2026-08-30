# Aqui Jas

Bot Discord puro, modular e focado em funcionalidades nativas do Discord.

## Estrutura

```text
main.py
bot/
├── bot.py
├── config.py
└── cogs/
    ├── core.py
    └── v1_admin.py
```

## Comandos atuais

- `/ping` — verifica a latência
- `/sobre` — informações do bot
- `/servidor` — resumo do servidor, separando pessoas e bots
- `/ajuda` — lista os comandos

## Configuração

Defina no ambiente da hospedagem:

```env
DISCORD_TOKEN=seu_token
LOG_LEVEL=INFO
```

Nunca coloque tokens no Git.
