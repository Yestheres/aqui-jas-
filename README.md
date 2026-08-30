# Aqui Jas

Bot Discord reconstruído do zero, inspirado nas ideias e aprendizados dos projetos anteriores, mas com um núcleo novo.

## Arquitetura

- **Python + discord.py 2.7**
- Slash commands como interface principal
- SQLite assíncrono para persistência
- Núcleo modular em `bot/`
- Agente separado da execução real
- Registry de ferramentas tipadas
- Ações classificadas por risco
- Executor determinístico: a IA planeja; o executor executa
- Configuração por variáveis de ambiente
- Estrutura preparada para múltiplos provedores de IA

## Estrutura

```text
.
├── bot/
│   ├── agent/
│   │   ├── models.py
│   │   ├── tools.py
│   │   └── executor.py
│   ├── cogs/
│   │   └── core.py
│   ├── bot.py
│   ├── config.py
│   └── database.py
├── main.py
├── requirements.txt
├── render.yaml
└── .env.example
```

## Rodando localmente

1. Instale Python 3.12+.
2. Crie um ambiente virtual.
3. Instale `requirements.txt`.
4. Copie `.env.example` para `.env`.
5. Preencha `DISCORD_TOKEN`.
6. Rode `python main.py`.

## Próximas camadas

1. Serviço de IA com roteador de provedores.
2. Memória conversacional real.
3. Ferramentas Discord para canais, cargos e configurações.
4. Planner estruturado com validação de argumentos.
5. Aprovação para ações médias/altas.
6. Snapshots e rollback.
7. Moderação, tickets, comunidade, bump, parceria e música.
