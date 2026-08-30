# Aqui Jas

Bot Discord reconstruído do zero, com arquitetura modular e orientada a agente.

## V1
- Slash commands
- Configuração de IA por servidor
- API OpenAI-compatible por servidor
- OpenRouter como padrão
- SQLite assíncrono para persistência
- Diagnóstico do servidor
- Central de ajuda
- Base de Agent com ações, risco e executor
- Estrutura preparada para múltiplos provedores

## Comandos atuais
- `/ping`
- `/sobre`
- `/ajuda`
- `/servidor`
- `/configia`
- `/iastatus`
- `/iaremover`
- `/ia`

## Configuração
Defina `DISCORD_TOKEN` nas variáveis de ambiente da hospedagem.

A IA é configurada separadamente em cada servidor com `/configia`.

## Próximas versões
V2: ferramentas Discord e Agent operacional.
V3: moderação.
V4: comunidade.
V5: música.
V6: backup, snapshots e rollback.
V7: Agent completo.
