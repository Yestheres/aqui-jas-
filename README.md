# Bot Discord de parcerias

Bot em Python para solicitações de parceria, aprovação da staff e proteção anti-spam.

## Executar

pip install -r requirements.txt
python main.py

Configure DISCORD_TOKEN como variável secreta antes de iniciar.

## Comandos principais

- /parceria — envia uma solicitação com descrição e convite permanente do Discord.
- /ajuda — mostra os comandos disponíveis.
- /configurar #canal — configura o canal privado da staff.
- &canal-parceria #canal — configura o canal privado da staff pelo prefixo.
- &armadilha — configura o canal atual como armadilha anti-spam.
- &armadilha #canal — configura outro canal como armadilha.
- &desarmadilha — restaura o canal da armadilha.

A armadilha cria ou reutiliza o cargo Suspeito, restringe o canal para esse cargo e atribui o cargo automaticamente após sinais de spam. O bot precisa de Gerenciar canais, Gerenciar cargos e estar acima do cargo Suspeito.

Nunca coloque o DISCORD_TOKEN em arquivos, commits ou mensagens.
