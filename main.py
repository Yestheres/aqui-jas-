from __future__ import annotations

import re
import logging
import os
import time
from collections import defaultdict, deque
from typing import Any
from urllib.parse import urlparse

import discord
from discord import app_commands
from discord.ext import commands

from storage import Database

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
logger = logging.getLogger("discord-bot")
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN: raise RuntimeError("DISCORD_TOKEN não foi encontrado. Adicione-o nos Secrets do host.")
MAX_DESCRIPTION_LENGTH=1000; MAX_LINK_LENGTH=2000; TRAP_ROLE_NAME="Suspeito"; TRAP_TOPIC_MARKER="[ARMADILHA] Acesso restrito ao cargo Suspeito."; SPAM_WINDOW_SECONDS=8; SPAM_MESSAGE_LIMIT=6; REPEAT_WINDOW_SECONDS=30; REPEAT_MESSAGE_LIMIT=3; INVITE_WINDOW_SECONDS=60; INVITE_MESSAGE_LIMIT=3
DISCORD_INVITE_PATTERN=re.compile(r"(?:discord\.gg|discord(?:app)?\.com/invite)/[A-Za-z0-9-]+",re.IGNORECASE)
def discord_invite_code(link:str)->str|None:
 p=urlparse(link)
 if p.scheme not in {"http","https"}: return None
 h=(p.hostname or "").lower(); parts=[x for x in p.path.split("/") if x]
 if h in {"discord.gg","discord.me","discord.li"}: return parts[0] if parts else None
 if h in {"discord.com","www.discord.com","discordapp.com","www.discordapp.com"} and len(parts)>=2 and parts[0].lower()=="invite": return parts[1]
 return None
def is_valid_link(link:str)->bool: return discord_invite_code(link) is not None
async def fetch_invite_preview(bot:PartnershipBot,link:str)->tuple[str,str|None]|None:
 try: invite=await bot.fetch_invite(link,with_counts=False,with_expiration=True)
 except (discord.NotFound,discord.Forbidden,discord.HTTPException): return None
 if invite.expires_at is not None or invite.max_age not in {None,0} or invite.guild is None:return None
 return invite.guild.name,invite.guild.icon.url if invite.guild.icon else None
def status_label(status:str)->str:return {"pending":"Pendente de aprovação","publishing":"Publicando","approved":"Aprovada","rejected":"Recusada","failed":"Falha ao enviar para a staff"}.get(status,status.title())
def partnership_embed(r:dict[str,Any])->discord.Embed:
 e=discord.Embed(title="Solicitação de parceria",description=r["description"],color={"pending":discord.Color.gold(),"publishing":discord.Color.blurple(),"approved":discord.Color.green(),"rejected":discord.Color.red()}.get(r["status"],discord.Color.blurple()));e.add_field(name="Solicitante",value=f"<@{r['requester_id']}>",inline=True);e.add_field(name="Status",value=status_label(r["status"]),inline=True);e.add_field(name="Link",value=f"[Abrir link]({r['link']})",inline=False)
 if r.get("publication_channel_id"):e.add_field(name="Canal de publicação",value=f"<#{r['publication_channel_id']}>",inline=False)
 e.set_footer(text=f"Solicitação #{r['id']}");return e
def published_partnership_embed(r:dict[str,Any],name:str|None,icon:str|None)->discord.Embed:
 e=discord.Embed(title=name,description=r["description"])
 if icon:e.set_thumbnail(url=icon)
 return e
def published_partnership_view(link:str)->discord.ui.View:
 v=discord.ui.View();v.add_item(discord.ui.Button(label="Entrar no servidor",style=discord.ButtonStyle.link,url=link));return v
class SuspicionTracker:
 def __init__(self):self._message_times=defaultdict(deque);self._recent_messages=defaultdict(deque);self._recent_invites=defaultdict(deque)
 def record(self,guild_id:int,user_id:int,content:str)->str|None:
  now=time.monotonic();k=(guild_id,user_id);mt=self._message_times[k];rm=self._recent_messages[k];ri=self._recent_invites[k]
  while mt and now-mt[0]>SPAM_WINDOW_SECONDS:mt.popleft()
  while rm and now-rm[0][0]>REPEAT_WINDOW_SECONDS:rm.popleft()
  while ri and now-ri[0]>INVITE_WINDOW_SECONDS:ri.popleft()
  mt.append(now);n=" ".join(content.lower().split())
  if n:rm.append((now,n))
  if DISCORD_INVITE_PATTERN.search(content):ri.append(now)
  if len(mt)>=SPAM_MESSAGE_LIMIT:return f"{len(mt)} mensagens em {SPAM_WINDOW_SECONDS}s"
  if n:
   count=sum(x==n for _,x in rm)
   if count>=REPEAT_MESSAGE_LIMIT:return f"mensagem repetida {count} vezes"
  if len(ri)>=INVITE_MESSAGE_LIMIT:return f"{len(ri)} convites em {INVITE_WINDOW_SECONDS}s"
  if (("@everyone" in content or "@here" in content) and len(mt)>=3):return "spam com menções em massa"
  return None
class StaffView(discord.ui.View):
 def __init__(self,bot:PartnershipBot,request_id:int):super().__init__(timeout=None);self.bot=bot;self.request_id=request_id
 async def interaction_check(self,interaction:discord.Interaction)->bool:
  if not interaction.guild or not isinstance(interaction.user,discord.Member):await interaction.response.send_message("Essa ação só pode ser usada pela staff dentro do servidor.",ephemeral=True);return False
  p=interaction.user.guild_permissions
  if not(p.administrator or p.manage_guild):await interaction.response.send_message("Apenas a staff com permissão de gerenciar o servidor pode revisar parcerias.",ephemeral=True);return False
  return True
 def disable_components(self):
  for c in self.children:c.disabled=True
class ApprovalView(StaffView):
 @discord.ui.button(label="Permitir parceria",style=discord.ButtonStyle.success,custom_id="partnership:approve")
 async def approve(self,interaction:discord.Interaction,_button:discord.ui.Button[ApprovalView])->None:
  r=self.bot.database.get_request(self.request_id)
  if not r or r["status"]!="pending":await interaction.response.send_message("Essa solicitação já foi revisada ou está sendo publicada.",ephemeral=True);return
  if not self.bot.database.set_awaiting_channel(self.request_id,True):await interaction.response.send_message("Essa solicitação já está sendo revisada por outra pessoa.",ephemeral=True);return
  d=self.bot.database.get_publication_channel(interaction.guild.id if interaction.guild else 0);text=f"O canal padrão atual é <#{d}>. Escolha um canal abaixo para publicar esta parceria." if d else "Escolha o canal onde a embed desta parceria será publicada."
  await interaction.response.edit_message(content=text,embed=partnership_embed(r),view=PublicationChannelView(self.bot,self.request_id))
 @discord.ui.button(label="Recusar parceria",style=discord.ButtonStyle.danger,custom_id="partnership:reject")
 async def reject(self,interaction:discord.Interaction,_button:discord.ui.Button[ApprovalView])->None:
  if not isinstance(interaction.user,discord.Member):return
  ok=self.bot.database.review_request(self.request_id,"rejected",interaction.user.id);r=self.bot.database.get_request(self.request_id)
  if not ok or not r:await interaction.response.send_message("Essa solicitação já foi revisada por outra pessoa.",ephemeral=True);return
  self.disable_components();await interaction.response.edit_message(content="Solicitação recusada pela staff.",embed=partnership_embed(r),view=self)
class PublicationChannelView(StaffView):
 def __init__(self,bot:PartnershipBot,request_id:int):
  super().__init__(bot,request_id);r=bot.database.get_request(request_id);d=bot.database.get_publication_channel(int(r["guild_id"])) if r else None
  for c in self.children:
   if isinstance(c,discord.ui.Button) and c.custom_id=="partnership:use-default":c.disabled=d is None
 async def _publish_to_channel(self,interaction:discord.Interaction,channel:discord.abc.GuildChannel)->None:
  if not interaction.guild:return
  if not isinstance(channel,discord.TextChannel):await interaction.response.send_message("Selecione um canal de texto válido.",ephemeral=True);return
  m=interaction.guild.me
  if m:
   p=channel.permissions_for(m)
   if not(p.view_channel and p.send_messages and p.embed_links):await interaction.response.send_message("Eu preciso de **Ver canal**, **Enviar mensagens** e **Inserir links** no canal escolhido.",ephemeral=True);return
  await interaction.response.defer();r=self.bot.database.get_request(self.request_id)
  if not r or r["status"]!="pending":await interaction.followup.send("Essa solicitação já foi revisada ou está sendo publicada.",ephemeral=True);return
  preview=await fetch_invite_preview(self.bot,r["link"])
  if preview is None:await interaction.followup.send("O convite do Discord está inválido, expirado ou não é permanente. A solicitação continua pendente.",ephemeral=True);return
  if not self.bot.database.start_publication(self.request_id,interaction.user.id,channel.id):await interaction.followup.send("Essa solicitação já está sendo revisada por outra pessoa.",ephemeral=True);return
  name,icon=preview;pub=dict(r);pub["status"]="approved";pub["publication_channel_id"]=str(channel.id)
  try:msg=await channel.send(embed=published_partnership_embed(pub,name,icon),view=published_partnership_view(r["link"]))
  except (discord.Forbidden,discord.HTTPException):self.bot.database.reset_publication(self.request_id);await interaction.followup.send("Não consegui publicar a embed nesse canal. A solicitação voltou para pendente; confira as permissões e tente novamente.",ephemeral=True);return
  self.bot.database.complete_publication(self.request_id,msg.id);self.bot.database.set_publication_channel(interaction.guild.id,channel.id);self.bot.database.clear_stale_active_requests(interaction.guild.id,int(r["requester_id"]),self.request_id)
  try:
   if interaction.message:await interaction.message.delete()
  except (discord.NotFound,discord.Forbidden,discord.HTTPException):pass
  await interaction.followup.send(f"Parceria aprovada e publicada em {channel.mention}. Esse canal agora é o padrão para as próximas aprovações.",ephemeral=True)
 @discord.ui.select(cls=discord.ui.ChannelSelect,channel_types=[discord.ChannelType.text],placeholder="Selecione o canal para publicar a parceria",min_values=1,max_values=1,custom_id="partnership:publication-channel")
 async def choose_channel(self,interaction:discord.Interaction,select:discord.ui.ChannelSelect[PublicationChannelView])->None:
  if not interaction.guild:return
  s=select.values[0];c=s.resolve()
  if c is None:
   try:c=await s.fetch()
   except (discord.NotFound,discord.Forbidden,discord.HTTPException):c=None
  if c is None:await interaction.response.send_message("Não consegui carregar o canal selecionado. Tente novamente.",ephemeral=True);return
  await self._publish_to_channel(interaction,c)
 @discord.ui.button(label="Usar canal padrão",style=discord.ButtonStyle.primary,custom_id="partnership:use-default")
 async def use_default(self,interaction:discord.Interaction,_button:discord.ui.Button[PublicationChannelView])->None:
  if not interaction.guild:return
  d=self.bot.database.get_publication_channel(interaction.guild.id)
  if d is None:await interaction.response.send_message("Ainda não existe um canal padrão. Use o seletor para escolher um.",ephemeral=True);return
  c=interaction.guild.get_channel(d)
  if c is None:
   try:c=await self.bot.fetch_channel(d)
   except (discord.NotFound,discord.Forbidden,discord.HTTPException):c=None
  if not isinstance(c,discord.TextChannel):await interaction.response.send_message("O canal padrão não está disponível. Escolha outro canal no seletor.",ephemeral=True);return
  await self._publish_to_channel(interaction,c)
 @discord.ui.button(label="Voltar",style=discord.ButtonStyle.secondary,custom_id="partnership:publication-back")
 async def back(self,interaction:discord.Interaction,_button:discord.ui.Button[PublicationChannelView])->None:
  if not self.bot.database.set_awaiting_channel(self.request_id,False):await interaction.response.send_message("Essa solicitação não está mais pendente.",ephemeral=True);return
  r=self.bot.database.get_request(self.request_id)
  if not r:await interaction.response.send_message("Não encontrei essa solicitação.",ephemeral=True);return
  await interaction.response.edit_message(content="Nova solicitação de parceria aguardando decisão da staff.",embed=partnership_embed(r),view=ApprovalView(self.bot,self.request_id))
class PartnershipBot(commands.Bot):
 def __init__(self):
  i=discord.Intents.default();i.message_content=True;super().__init__(command_prefix=commands.when_mentioned_or("&","#"),intents=i);self.database=Database();self.suspicion_tracker=SuspicionTracker()
 async def setup_hook(self):
  self.database.initialize();synced=await self.tree.sync();logger.info("Comandos slash sincronizados: %s",len(synced))
  for r in self.database.list_pending_requests():
   v=PublicationChannelView(self,int(r["id"])) if r["awaiting_channel"] else ApprovalView(self,int(r["id"]));
   if r["approval_message_id"]:self.add_view(v,message_id=int(r["approval_message_id"]))
 async def on_ready(self):
  if self.user:await self.change_presence(activity=discord.Activity(type=discord.ActivityType.watching,name="/parceria | /ajuda"),status=discord.Status.online);logger.info("Bot conectado como %s",self.user)
 async def on_message(self,message:discord.Message):
  if message.author.bot:return
  if message.guild and isinstance(message.author,discord.Member):
   reason=self.suspicion_tracker.record(message.guild.id,message.author.id,message.content)
   if reason:await self.mark_suspicious(message.author,reason)
  await self.process_commands(message)
 async def mark_suspicious(self,member:discord.Member,reason:str):
  cfg=self.database.get_trap_config(member.guild.id)
  if cfg is None:return
  role=member.guild.get_role(cfg["role_id"])
  if role is None or role in member.roles:return
  bm=member.guild.me
  if bm is None or not bm.guild_permissions.manage_roles or role>=bm.top_role:return
  try:await member.add_roles(role,reason=f"Detecção automática de comportamento suspeito: {reason}")
  except (discord.Forbidden,discord.HTTPException):logger.exception("Não foi possível atribuir o cargo Suspeito a %s no servidor %s.",member.id,member.guild.id);return
bot=PartnershipBot()
@bot.tree.command(name="ping",description="Verifica se o bot está online.")
async def ping(interaction:discord.Interaction):await interaction.response.send_message(f"🏓 **{bot.user.name if bot.user else 'Bot'}** está online.\n⚡ `{round(bot.latency*1000)} ms`")
@bot.tree.command(name="sobre",description="Mostra informações sobre o bot.")
async def sobre(interaction:discord.Interaction):
 e=discord.Embed(title=f"✨ {bot.user.name if bot.user else 'Bot'}",description="Bot Discord leve e modular.",color=discord.Color.blurple())
 if bot.user:e.set_thumbnail(url=bot.user.display_avatar.url)
 e.add_field(name="🏠 Servidores",value=f"`{len(bot.guilds)}`",inline=True);e.add_field(name="📦 discord.py",value=f"`{discord.__version__}`",inline=True);await interaction.response.send_message(embed=e)
@bot.tree.command(name="servidor",description="Mostra informações básicas deste servidor.")
async def servidor(interaction:discord.Interaction):
 if interaction.guild is None:await interaction.response.send_message("Esse comando só funciona em um servidor.",ephemeral=True);return
 g=interaction.guild;e=discord.Embed(title=f"🏠 {g.name}",color=discord.Color.blurple())
 if g.icon:e.set_thumbnail(url=g.icon.url)
 e.add_field(name="👥 Membros",value=f"`{g.member_count or 'indisponível'}`",inline=True);e.add_field(name="💬 Canais",value=f"`{len(g.channels)}`",inline=True);e.add_field(name="🎭 Cargos",value=f"`{max(0,len(g.roles)-1)}`",inline=True);await interaction.response.send_message(embed=e)
@bot.tree.command(name="configurar",description="Configura o canal privado da staff.")
@app_commands.describe(canal="Canal privado onde a staff receberá as solicitações.")
@app_commands.default_permissions(manage_guild=True)
async def configurar(interaction:discord.Interaction,canal:discord.TextChannel):
 if interaction.guild is None or not isinstance(interaction.user,discord.Member):await interaction.response.send_message("Esse comando só funciona em um servidor.",ephemeral=True);return
 p=interaction.user.guild_permissions
 if interaction.user.id!=interaction.guild.owner_id and not(p.administrator or p.manage_guild):await interaction.response.send_message("❌ Você precisa ser dono do servidor, Administrador ou ter **Gerenciar Servidor**.",ephemeral=True);return
 if canal.overwrites_for(interaction.guild.default_role).view_channel is not False:await interaction.response.send_message("❌ O canal precisa ser **privado**: negue **Ver canal** para @everyone.",ephemeral=True);return
 bot.database.set_approval_channel(interaction.guild.id,canal.id);await interaction.response.send_message(f"✅ Canal da staff configurado para {canal.mention}.",ephemeral=True)
@bot.command(name="parceria")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def prefix_publication_channel(context:commands.Context[PartnershipBot]):
 if not context.guild:return
 c=context.channel
 if not isinstance(c,discord.TextChannel):return
 m=context.guild.me
 if m:
  p=c.permissions_for(m)
  if not(p.view_channel and p.send_messages and p.embed_links):await context.reply("Eu preciso de **Ver canal**, **Enviar mensagens** e **Inserir links** nesse canal.");return
 bot.database.set_publication_channel(context.guild.id,c.id)
 try:await context.message.delete()
 except (discord.NotFound,discord.Forbidden,discord.HTTPException):pass
 await context.send("✅ Este canal foi definido como **canal de publicação de parcerias**.",delete_after=5)
@bot.tree.command(name="parceria",description="Envia uma solicitação de parceria para a staff.")
@app_commands.describe(descricao="Descrição da parceria que você está propondo.",link="Link permanente de convite do servidor no Discord.")
async def partnership(interaction:discord.Interaction,descricao:str,link:str):
 if not interaction.guild:await interaction.response.send_message("Esse comando só pode ser usado dentro de um servidor.",ephemeral=True);return
 d=descricao.strip();l=link.strip()
 if not d:await interaction.response.send_message("A descrição da parceria não pode ficar vazia.",ephemeral=True);return
 if len(d)>MAX_DESCRIPTION_LENGTH:await interaction.response.send_message(f"A descrição deve ter no máximo {MAX_DESCRIPTION_LENGTH} caracteres.",ephemeral=True);return
 if len(l)>MAX_LINK_LENGTH or not is_valid_link(l):await interaction.response.send_message("Envie um convite permanente válido do Discord, como discord.gg/servidor.",ephemeral=True);return
 a=bot.database.get_approval_channel(interaction.guild.id)
 if a is None:await interaction.response.send_message("A staff ainda não configurou o canal privado. Um administrador deve usar `&canal-parceria #canal-privado`.",ephemeral=True);return
 c=interaction.guild.get_channel(a)
 if c is None:
  try:c=await bot.fetch_channel(a)
  except (discord.NotFound,discord.Forbidden,discord.HTTPException):c=None
 if not isinstance(c,discord.TextChannel):await interaction.response.send_message("O canal privado configurado não está disponível. A staff deve escolher outro canal.",ephemeral=True);return
 if c.permissions_for(interaction.guild.default_role).view_channel:await interaction.response.send_message("O canal de aprovação precisa ser privado: o cargo @everyone não pode conseguir visualizá-lo.",ephemeral=True);return
 rid=bot.database.create_request(interaction.guild.id,interaction.user.id,d,l)
 if rid is None:
  active=bot.database.get_active_request(interaction.guild.id,interaction.user.id)
  if active:await interaction.response.send_message("⚠️ Você já possui uma solicitação de parceria pendente. Aguarde a decisão da staff.",ephemeral=True)
  else:await interaction.response.send_message("Não foi possível criar a solicitação. Tente novamente.",ephemeral=True)
  return
 r=bot.database.get_request(rid)
 if r is None:await interaction.response.send_message("Não foi possível criar a solicitação. Tente novamente.",ephemeral=True);return
 try:m=await c.send(content="Nova solicitação de parceria aguardando decisão da staff.",embed=partnership_embed(r),view=ApprovalView(bot,rid))
 except (discord.Forbidden,discord.HTTPException):logger.exception("Falha ao enviar a solicitação #%s.",rid);await interaction.response.send_message("Não consegui enviar a solicitação ao canal privado da staff. Verifique as permissões do bot nesse canal.",ephemeral=True);return
 bot.database.set_message_id(rid,m.id);await interaction.response.send_message("Sua solicitação foi enviada para a staff e ficará aguardando aprovação.",ephemeral=True)
@bot.tree.command(name="ajuda",description="Mostra os comandos disponíveis do bot.")
async def help_command(interaction:discord.Interaction):
 e=discord.Embed(title="Ajuda do bot",description="Comandos disponíveis e como usá-los.",color=discord.Color.blurple());e.add_field(name="/parceria",value="Pode ser usado em qualquer canal do servidor. Informe `descricao` e `link` para enviar uma solicitação à staff.",inline=False);e.add_field(name="/configurar",value="Configura o canal privado de aprovação (staff).",inline=False);e.add_field(name="&parceria",value="Define o canal atual como canal padrão de publicação (staff).",inline=False);e.add_field(name="/ping",value="Verifica a latência do bot.",inline=False);await interaction.response.send_message(embed=e)
@bot.command(name="canal-parceria")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def canal_parceria(context:commands.Context[PartnershipBot],canal:discord.TextChannel):bot.database.set_approval_channel(context.guild.id,canal.id);await context.reply(f"✅ Canal de aprovação configurado para {canal.mention}.")
@bot.command(name="armadilha")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def armadilha(context:commands.Context[PartnershipBot],canal:discord.TextChannel):
 g=context.guild;role=discord.utils.get(g.roles,name=TRAP_ROLE_NAME)
 if role is None:role=await g.create_role(name=TRAP_ROLE_NAME,reason="Configuração da armadilha anti-spam")
 o=canal.overwrites_for(g.default_role);o.view_channel=False;await canal.set_permissions(g.default_role,overwrite=o);await canal.edit(topic=TRAP_TOPIC_MARKER);bot.database.set_trap_config(g.id,role.id,canal.id);await context.reply(f"✅ Armadilha ativada em {canal.mention}. Cargo: {role.mention}")
@bot.command(name="desarmadilha")
@commands.guild_only()
@commands.has_guild_permissions(manage_guild=True)
async def desarmadilha(context:commands.Context[PartnershipBot]):bot.database.clear_trap_config(context.guild.id);await context.reply("✅ Armadilha desativada.")
if __name__=="__main__":bot.run(TOKEN)
