import sys
import discord
from discord import app_commands
from discord.ui import Button, View
import random
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import math
import sqlite3  # NOVO: import do SQLite
import os

sys.stdout.reconfigure(encoding='utf-8')

# Configurações
PREFIX = '!'
API_NINJAS_KEY = 'SUA_API_KEY'  # Opcional: para comandos de IA

class Fort(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        
        # Sistema de economia e jogos
        self.user_balances = {}
        self.user_inventory = {}
        self.daily_cooldowns = {}
        self.ship_data = {}
        self.marriage_data = {}
        self.divorce_cooldowns = {}
        self.anniversary_data = {}
        self.ship_history = {}
        
        # Sistema de chamadas
        self.call_data = {}
        self.call_participants = {}
        
        # NOVO: Inicializa banco de dados e carrega dados
        self.init_database()
        self.load_data()
    
    # ===== NOVAS FUNÇÕES SQLITE =====
    def init_database(self):
        """Cria o banco de dados SQLite"""
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        # Cria tabela para economia (saldo dos usuários)
        c.execute('''CREATE TABLE IF NOT EXISTS economia
                     (user_id TEXT PRIMARY KEY, saldo INTEGER)''')
        
        # Cria tabela para cooldowns diários
        c.execute('''CREATE TABLE IF NOT EXISTS daily_cooldowns
                     (user_id TEXT PRIMARY KEY, data TEXT)''')
        
        # Cria tabela para cooldowns de divórcio
        c.execute('''CREATE TABLE IF NOT EXISTS divorce_cooldowns
                     (user_id TEXT PRIMARY KEY, data TEXT)''')
        
        # Cria tabela genérica para todos os outros dados JSON
        c.execute('''CREATE TABLE IF NOT EXISTS dados_json
                     (tipo TEXT PRIMARY KEY, dados TEXT)''')
        
        conn.commit()
        conn.close()
        
        print("✅ Banco de dados SQLite inicializado!")
    
    def load_data(self):
        """Carrega dados do SQLite"""
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        # Carrega economia (saldo dos usuários)
        c.execute('SELECT user_id, saldo FROM economia')
        self.user_balances = {}
        for user_id, saldo in c.fetchall():
            self.user_balances[user_id] = saldo
        
        # Carrega daily cooldowns
        c.execute('SELECT user_id, data FROM daily_cooldowns')
        self.daily_cooldowns = {}
        for user_id, data in c.fetchall():
            self.daily_cooldowns[user_id] = data
        
        # Carrega divorce cooldowns
        c.execute('SELECT user_id, data FROM divorce_cooldowns')
        self.divorce_cooldowns = {}
        for user_id, data in c.fetchall():
            self.divorce_cooldowns[user_id] = datetime.fromisoformat(data) if data else None
        
        # Carrega todos os outros dados da tabela genérica
        c.execute('SELECT tipo, dados FROM dados_json')
        for tipo, dados_json in c.fetchall():
            dados = json.loads(dados_json)
            if tipo == 'inventory':
                self.user_inventory = dados
            elif tipo == 'ships':
                self.ship_data = dados
            elif tipo == 'marriages':
                self.marriage_data = dados
            elif tipo == 'anniversary':
                self.anniversary_data = dados
            elif tipo == 'ship_history':
                self.ship_history = dados
            elif tipo == 'calls':
                self.call_data = dados
            elif tipo == 'call_participants':
                self.call_participants = dados
        
        conn.close()
        
        # Tenta importar dados dos arquivos JSON antigos se o banco estiver vazio
        self.import_from_json_if_empty()
    
    def import_from_json_if_empty(self):
        """Importa dados dos arquivos JSON antigos se o banco estiver vazio"""
        if not self.user_balances:  # Se não há dados no banco
            try:
                # Tenta carregar dos JSONs antigos
                with open('economy.json', 'r', encoding='utf-8') as f:
                    self.user_balances = json.load(f)
                with open('inventory.json', 'r', encoding='utf-8') as f:
                    self.user_inventory = json.load(f)
                with open('ships.json', 'r', encoding='utf-8') as f:
                    self.ship_data = json.load(f)
                with open('marriages.json', 'r', encoding='utf-8') as f:
                    self.marriage_data = json.load(f)
                with open('anniversary.json', 'r', encoding='utf-8') as f:
                    self.anniversary_data = json.load(f)
                with open('ship_history.json', 'r', encoding='utf-8') as f:
                    self.ship_history = json.load(f)
                with open('calls.json', 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.call_data = data.get('calls', {})
                    self.call_participants = data.get('participants', {})
                
                print("✅ Dados importados dos arquivos JSON antigos!")
                self.save_data()  # Salva no SQLite imediatamente
            except FileNotFoundError:
                print("ℹ️ Nenhum arquivo JSON antigo encontrado. Começando do zero.")
            except Exception as e:
                print(f"⚠️ Erro ao importar JSONs: {e}")
    
    def save_data(self):
        """Salva dados no SQLite"""
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        # Salva economia (linha por linha)
        for user_id, saldo in self.user_balances.items():
            c.execute('''INSERT OR REPLACE INTO economia (user_id, saldo)
                         VALUES (?, ?)''', (user_id, saldo))
        
        # Salva daily cooldowns
        for user_id, data in self.daily_cooldowns.items():
            c.execute('''INSERT OR REPLACE INTO daily_cooldowns (user_id, data)
                         VALUES (?, ?)''', (user_id, data))
        
        # Salva divorce cooldowns
        for user_id, data in self.divorce_cooldowns.items():
            data_str = data.isoformat() if data else None
            c.execute('''INSERT OR REPLACE INTO divorce_cooldowns (user_id, data)
                         VALUES (?, ?)''', (user_id, data_str))
        
        # Salva todos os outros dados como JSON
        dados_para_salvar = [
            ('inventory', self.user_inventory),
            ('ships', self.ship_data),
            ('marriages', self.marriage_data),
            ('anniversary', self.anniversary_data),
            ('ship_history', self.ship_history),
            ('calls', self.call_data),
            ('call_participants', self.call_participants)
        ]
        
        for tipo, dados in dados_para_salvar:
            c.execute('''INSERT OR REPLACE INTO dados_json (tipo, dados)
                         VALUES (?, ?)''', (tipo, json.dumps(dados, ensure_ascii=False)))
        
        conn.commit()
        conn.close()

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Comandos sincronizados!")

    async def on_ready(self):
        print(f"✅ Bot {self.user} ligado com sucesso!")
        print(f"📊 Servidores: {len(self.guilds)}")
        print(f"👥 Usuários: {len(self.users)}")
        print(f"📢 Sistema de Chamadas: ATIVO")
        print(f"💖 Sistema de Ship: ATIVO")
        print(f"💒 Sistema de Casamento: ATIVO")
        print(f"💰 Sistema de Economia: ATIVO")
        print(f"🎮 Sistema de Jogos: ATIVO")
        print(f"💾 Banco de Dados: SQLite")
        await self.change_presence(activity=discord.Game(name="📢 Use /ajuda"))

bot = Fort()

# ==================== SISTEMA DE CHAMADAS COMPLETO ====================

class CallButton(Button):
    def __init__(self, call_id: str, emoji: str):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Confirmar Presença",
            emoji=emoji,
            custom_id=f"call_{call_id}"
        )
        self.call_id = call_id
    
    async def callback(self, interaction: discord.Interaction):
        try:
            user_id = str(interaction.user.id)
            call_id = self.call_id
            
            if call_id not in bot.call_data:
                await interaction.response.send_message("❌ Esta chamada não existe mais!", ephemeral=True)
                return
            
            call = bot.call_data[call_id]
            
            if call_id not in bot.call_participants:
                bot.call_participants[call_id] = []
            
            if user_id in bot.call_participants[call_id]:
                await interaction.response.send_message("❌ Você já confirmou presença!", ephemeral=True)
                return
            
            bot.call_participants[call_id].append(user_id)
            bot.save_data()
            
            # ATUALIZA EMBED
            try:
                channel = bot.get_channel(int(call['channel_id']))
                if channel:
                    message = await channel.fetch_message(int(call['message_id']))
                    if message and message.embeds:
                        embed = message.embeds[0]
                        
                        # Cria lista de participantes
                        participantes_text = ""
                        participantes_list = []
                        
                        for pid in bot.call_participants[call_id]:
                            member = interaction.guild.get_member(int(pid))
                            if member:
                                participantes_list.append(member.mention)
                        
                        if participantes_list:
                            if len(participantes_list) <= 20:
                                for i, mention in enumerate(participantes_list, 1):
                                    participantes_text += f"{i}. {mention}\n"
                            else:
                                for i, mention in enumerate(participantes_list[:20], 1):
                                    participantes_text += f"{i}. {mention}\n"
                                participantes_text += f"\n... e mais {len(participantes_list) - 20} pessoas"
                        else:
                            participantes_text = "Ninguém confirmou ainda"
                        
                        # Cria novo embed
                        novo_embed = discord.Embed(
                            title=embed.title,
                            description=embed.description,
                            color=discord.Color.blue()
                        )
                        
                        for field in embed.fields:
                            if not field.name.startswith("✅ Confirmados"):
                                novo_embed.add_field(name=field.name, value=field.value, inline=field.inline)
                        
                        novo_embed.add_field(
                            name=f"✅ **Confirmados: {len(bot.call_participants[call_id])}**",
                            value=participantes_text,
                            inline=False
                        )
                        
                        if embed.thumbnail:
                            novo_embed.set_thumbnail(url=embed.thumbnail.url)
                        if embed.footer:
                            novo_embed.set_footer(text=embed.footer.text)
                        if embed.timestamp:
                            novo_embed.timestamp = embed.timestamp
                        
                        await message.edit(embed=novo_embed)
            except Exception as e:
                print(f"Erro ao atualizar embed: {e}")
            
            # MENSAGEM PRIVADA
            try:
                embed_privado = discord.Embed(
                    title="✅ PRESENÇA CONFIRMADA!",
                    description=f"**{call['titulo']}**",
                    color=discord.Color.green()
                )
                
                embed_privado.add_field(name="📅 Data", value=call['data_hora'], inline=True)
                embed_privado.add_field(name="📍 Local", value=call['local'], inline=True)
                
                if call['descricao']:
                    embed_privado.add_field(name="📝 Descrição", value=call['descricao'][:100], inline=False)
                
                embed_privado.add_field(name="👤 Organizador", value=f"<@{call['criador_id']}>", inline=True)
                embed_privado.add_field(name="📊 Total", value=f"{len(bot.call_participants[call_id])} confirmados", inline=True)
                embed_privado.set_footer(text="Obrigado por confirmar! 🎉")
                
                await interaction.user.send(embed=embed_privado)
            except:
                pass
            
            await interaction.response.send_message(
                f"✅ **Presença confirmada!** Agora temos **{len(bot.call_participants[call_id])}** confirmado(s)!",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"Erro no botão: {e}")
            await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

class CallView(View):
    def __init__(self, call_id: str, emoji: str):
        super().__init__(timeout=None)
        self.add_item(CallButton(call_id, emoji))

@bot.tree.command(name="chamada", description="📢 Criar uma chamada com @everyone e botão")
@app_commands.describe(
    titulo="Título do evento",
    data_hora="Data e hora (ex: 25/12 às 20h)",
    local="Local do evento",
    descricao="Descrição detalhada",
    emoji="Emoji do botão (padrão: ✅)"
)
async def chamada(
    interaction: discord.Interaction,
    titulo: str,
    data_hora: str,
    local: str,
    descricao: str = "",
    emoji: str = "✅"
):
    if not interaction.user.guild_permissions.mention_everyone:
        await interaction.response.send_message("❌ Você precisa da permissão `Mencionar @everyone`!", ephemeral=True)
        return
    
    if not interaction.guild.me.guild_permissions.mention_everyone:
        await interaction.response.send_message("❌ O bot precisa da permissão `Mencionar @everyone`!", ephemeral=True)
        return
    
    call_id = f"{interaction.channel.id}-{int(datetime.now().timestamp())}"
    
    embed = discord.Embed(
        title=f"📢 {titulo}",
        description=descricao if descricao else "Clique no botão para confirmar presença!",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="📅 Data/Hora", value=data_hora, inline=True)
    embed.add_field(name="📍 Local", value=local, inline=True)
    embed.add_field(name="👤 Organizador", value=interaction.user.mention, inline=True)
    embed.add_field(name="✅ **Confirmados: 0**", value="Ninguém confirmou ainda", inline=False)
    
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    
    embed.set_footer(text="Clique no botão abaixo para confirmar! A lista atualiza automaticamente.")
    embed.timestamp = datetime.now()
    
    view = CallView(call_id, emoji)
    
    await interaction.response.send_message(
        content="@everyone 📢 **NOVA CHAMADA!** 📢",
        embed=embed,
        view=view,
        allowed_mentions=discord.AllowedMentions(everyone=True)
    )
    
    message = await interaction.original_response()
    
    bot.call_data[call_id] = {
        'titulo': titulo,
        'data_hora': data_hora,
        'local': local,
        'descricao': descricao,
        'criador_id': str(interaction.user.id),
        'criador_nome': interaction.user.name,
        'channel_id': str(interaction.channel.id),
        'message_id': str(message.id),
        'emoji': emoji,
        'criado_em': datetime.now().isoformat()
    }
    
    bot.call_participants[call_id] = []
    bot.save_data()
    
    embed_confirm = discord.Embed(
        title="✅ Chamada Criada!",
        description=f"**{titulo}** criada com sucesso!",
        color=discord.Color.green()
    )
    
    embed_confirm.add_field(
        name="📊 Status",
        value=f"📝 ID: `{call_id}`\n🔗 [Clique aqui]({message.jump_url})\n👥 A lista aparece no embed!",
        inline=False
    )
    
    await interaction.followup.send(embed=embed_confirm, ephemeral=True)

@bot.tree.command(name="chamada_info", description="ℹ️ Ver informações de uma chamada")
async def chamada_info(interaction: discord.Interaction, message_id: str = None):
    if not message_id:
        calls = []
        for cid, data in bot.call_data.items():
            if data.get('channel_id') == str(interaction.channel.id):
                calls.append((cid, data))
        
        if not calls:
            await interaction.response.send_message("❌ Nenhuma chamada no canal!", ephemeral=True)
            return
        
        calls.sort(key=lambda x: x[1]['criado_em'], reverse=True)
        
        embed = discord.Embed(title="📋 Últimas Chamadas", color=discord.Color.blue())
        
        for cid, data in calls[:5]:
            participantes = len(bot.call_participants.get(cid, []))
            embed.add_field(
                name=f"📢 {data['titulo'][:30]}",
                value=f"📅 {data['data_hora']}\n✅ {participantes} confirmados\n📝 `{data['message_id']}`",
                inline=False
            )
        
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    
    call_id = None
    for cid, data in bot.call_data.items():
        if data['message_id'] == message_id:
            call_id = cid
            break
    
    if not call_id:
        await interaction.response.send_message("❌ Chamada não encontrada!", ephemeral=True)
        return
    
    data = bot.call_data[call_id]
    participantes = bot.call_participants.get(call_id, [])
    
    embed = discord.Embed(title=f"📊 {data['titulo']}", color=discord.Color.blue())
    embed.add_field(name="📅 Data/Hora", value=data['data_hora'], inline=True)
    embed.add_field(name="📍 Local", value=data['local'], inline=True)
    embed.add_field(name="👤 Criador", value=f"<@{data['criador_id']}>", inline=True)
    embed.add_field(name="✅ Confirmados", value=str(len(participantes)), inline=True)
    
    if participantes:
        lista = ""
        for pid in participantes[:15]:
            member = interaction.guild.get_member(int(pid))
            if member:
                lista += f"• {member.mention}\n"
        if lista:
            embed.add_field(name="📋 Lista", value=lista, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="chamada_lista", description="📋 Ver lista completa de participantes")
async def chamada_lista(interaction: discord.Interaction, message_id: str):
    call_id = None
    for cid, data in bot.call_data.items():
        if data['message_id'] == message_id:
            call_id = cid
            break
    
    if not call_id:
        await interaction.response.send_message("❌ Chamada não encontrada!", ephemeral=True)
        return
    
    data = bot.call_data[call_id]
    participantes = bot.call_participants.get(call_id, [])
    
    if not participantes:
        await interaction.response.send_message("📋 Ninguém confirmou ainda!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"📋 Lista de Presença",
        description=f"**{data['titulo']}**",
        color=discord.Color.green()
    )
    
    embed.add_field(name="📅 Data", value=data['data_hora'], inline=True)
    embed.add_field(name="📍 Local", value=data['local'], inline=True)
    embed.add_field(name="✅ Total", value=str(len(participantes)), inline=True)
    
    lista = ""
    for i, pid in enumerate(participantes, 1):
        member = interaction.guild.get_member(int(pid))
        if member:
            lista += f"{i}. {member.mention}\n"
    
    embed.add_field(name="📋 Participantes", value=lista, inline=False)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="chamada_cancelar", description="❌ Cancelar uma chamada")
async def chamada_cancelar(interaction: discord.Interaction, message_id: str):
    call_id = None
    for cid, data in bot.call_data.items():
        if data['message_id'] == message_id:
            call_id = cid
            break
    
    if not call_id:
        await interaction.response.send_message("❌ Chamada não encontrada!", ephemeral=True)
        return
    
    data = bot.call_data[call_id]
    
    if str(interaction.user.id) != data['criador_id']:
        await interaction.response.send_message("❌ Só o criador pode cancelar!", ephemeral=True)
        return
    
    try:
        channel = bot.get_channel(int(data['channel_id']))
        if channel:
            msg = await channel.fetch_message(int(message_id))
            if msg:
                embed_cancel = discord.Embed(
                    title="❌ CHAMADA CANCELADA",
                    description=f"**{data['titulo']}** cancelada por {interaction.user.mention}",
                    color=discord.Color.red()
                )
                await msg.edit(content=None, embed=embed_cancel, view=None)
    except:
        pass
    
    del bot.call_data[call_id]
    if call_id in bot.call_participants:
        del bot.call_participants[call_id]
    
    bot.save_data()
    await interaction.response.send_message("✅ Chamada cancelada!", ephemeral=True)

# ==================== SISTEMA DE SHIP COMPLETO ====================

@bot.tree.command(name="ship", description="💖 Calcula o amor entre duas pessoas")
async def ship(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    base = random.randint(40, 90)
    
    if pessoa1.guild == pessoa2.guild:
        base += 5
    
    cargos_comuns = set(pessoa1.roles) & set(pessoa2.roles)
    if len(cargos_comuns) > 1:
        base += len(cargos_comuns) * 2
    
    idade_p1 = (datetime.now() - pessoa1.created_at).days
    idade_p2 = (datetime.now() - pessoa2.created_at).days
    if abs(idade_p1 - idade_p2) < 30:
        base += 3
    
    if pessoa1.name[0].lower() == pessoa2.name[0].lower():
        base += 2
    
    porcentagem = max(0, min(100, base))
    
    if random.random() < 0.01:
        porcentagem = 100
    
    nome_casal = pessoa1.display_name[:len(pessoa1.display_name)//2] + pessoa2.display_name[len(pessoa2.display_name)//2:]
    barras = "█" * (porcentagem // 10) + "░" * (10 - (porcentagem // 10))
    
    if porcentagem < 20:
        cor = discord.Color.dark_gray()
        mensagem = "💔 Nem amigos serão..."
    elif porcentagem < 40:
        cor = discord.Color.red()
        mensagem = "❤️‍🩹 Só amizade"
    elif porcentagem < 60:
        cor = discord.Color.orange()
        mensagem = "💛 Tem potencial"
    elif porcentagem < 70:
        cor = discord.Color.gold()
        mensagem = "💚 Interessante"
    elif porcentagem < 80:
        cor = discord.Color.green()
        mensagem = "💙 Ótima combinação"
    elif porcentagem < 90:
        cor = discord.Color.teal()
        mensagem = "💜 Quase perfeitos"
    elif porcentagem < 100:
        cor = discord.Color.purple()
        mensagem = "💝 Perfeitos"
    else:
        cor = discord.Color.from_str("#FF69B4")
        mensagem = "✨ ALMAS GÊMEAS! ✨"
    
    embed = discord.Embed(
        title="💖 Teste de Amor",
        description=f"{pessoa1.mention} 💘 {pessoa2.mention}",
        color=cor
    )
    
    embed.add_field(name="📊 Compatibilidade", value=f"**{porcentagem}%**\n`{barras}`", inline=False)
    embed.add_field(name="💑 Nome do Casal", value=f"**{nome_casal}**", inline=True)
    embed.add_field(name="📝 Resultado", value=mensagem, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="shippar", description="💘 Cria um ship oficial")
async def shippar(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    if pessoa1 == pessoa2:
        await interaction.response.send_message("❌ Não pode shippar consigo mesmo!")
        return
    
    ship_id = f"{pessoa1.id}-{pessoa2.id}"
    
    if ship_id in bot.ship_data:
        await interaction.response.send_message("❌ Este ship já existe!")
        return
    
    bot.ship_data[ship_id] = {
        "pessoa1": str(pessoa1.id),
        "pessoa2": str(pessoa2.id),
        "likes": 0,
        "criado_por": str(interaction.user.id),
        "data": datetime.now().isoformat()
    }
    
    bot.save_data()
    
    embed = discord.Embed(
        title="💘 NOVO SHIP!",
        description=f"{pessoa1.mention} 💕 {pessoa2.mention}",
        color=discord.Color.from_str("#FF69B4")
    )
    
    embed.add_field(name="👍 Likes", value="0", inline=True)
    embed.add_field(name="👤 Criado por", value=interaction.user.mention, inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="likeship", description="👍 Dá like em um ship")
async def likeship(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    ship_id = f"{pessoa1.id}-{pessoa2.id}"
    
    if ship_id not in bot.ship_data:
        await interaction.response.send_message("❌ Ship não existe! Use /shippar primeiro.")
        return
    
    bot.ship_data[ship_id]["likes"] += 1
    bot.save_data()
    
    await interaction.response.send_message(f"👍 Like dado! Total: {bot.ship_data[ship_id]['likes']} likes")

@bot.tree.command(name="shipinfo", description="ℹ️ Informações do ship")
async def shipinfo(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    ship_id = f"{pessoa1.id}-{pessoa2.id}"
    
    if ship_id not in bot.ship_data:
        await interaction.response.send_message("❌ Ship não encontrado!")
        return
    
    data = bot.ship_data[ship_id]
    criador = interaction.guild.get_member(int(data["criado_por"]))
    
    embed = discord.Embed(
        title=f"ℹ️ {pessoa1.display_name} x {pessoa2.display_name}",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="👍 Likes", value=data["likes"], inline=True)
    embed.add_field(name="👤 Criador", value=criador.mention if criador else "Desconhecido", inline=True)
    embed.add_field(name="📅 Data", value=datetime.fromisoformat(data["data"]).strftime("%d/%m/%Y"), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="meusships", description="📋 Seus ships criados")
async def meusships(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    ships = []
    for ship_id, data in bot.ship_data.items():
        if str(data["criado_por"]) == user_id:
            ships.append(ship_id)
    
    if not ships:
        await interaction.response.send_message("❌ Você não criou nenhum ship!")
        return
    
    embed = discord.Embed(title=f"📋 Ships de {interaction.user.display_name}", color=discord.Color.blue())
    
    for ship_id in ships[:10]:
        data = bot.ship_data[ship_id]
        p1 = interaction.guild.get_member(int(data["pessoa1"]))
        p2 = interaction.guild.get_member(int(data["pessoa2"]))
        
        if p1 and p2:
            embed.add_field(
                name=f"{p1.display_name} x {p2.display_name}",
                value=f"👍 {data['likes']} likes",
                inline=False
            )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="topship", description="🏆 Top ships")
async def topship(interaction: discord.Interaction):
    ships = sorted(bot.ship_data.items(), key=lambda x: x[1]["likes"], reverse=True)[:10]
    
    if not ships:
        await interaction.response.send_message("❌ Nenhum ship encontrado!")
        return
    
    embed = discord.Embed(title="🏆 TOP 10 SHIPS", color=discord.Color.gold())
    
    for i, (ship_id, data) in enumerate(ships, 1):
        p1 = interaction.guild.get_member(int(data["pessoa1"]))
        p2 = interaction.guild.get_member(int(data["pessoa2"]))
        
        if p1 and p2:
            medalha = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}°"
            embed.add_field(
                name=f"{medalha} {p1.display_name} x {p2.display_name}",
                value=f"👍 {data['likes']} likes",
                inline=False
            )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="shiplist", description="📜 Lista todos os ships")
async def shiplist(interaction: discord.Interaction):
    ships = []
    
    for ship_id, data in bot.ship_data.items():
        p1 = interaction.guild.get_member(int(data["pessoa1"]))
        p2 = interaction.guild.get_member(int(data["pessoa2"]))
        
        if p1 and p2:
            ships.append((p1, p2, data["likes"]))
    
    if not ships:
        await interaction.response.send_message("❌ Nenhum ship encontrado!")
        return
    
    embed = discord.Embed(
        title="📜 Ships do Servidor",
        description=f"Total: {len(ships)} ships",
        color=discord.Color.blue()
    )
    
    for p1, p2, likes in ships[:15]:
        embed.add_field(
            name=f"{p1.display_name} 💘 {p2.display_name}",
            value=f"👍 {likes} likes",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="calcular_amor", description="🔮 Cálculo detalhado de compatibilidade")
async def calcular_amor(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    categorias = {
        "Amizade": random.randint(0, 100),
        "Paixão": random.randint(0, 100),
        "Confiança": random.randint(0, 100),
        "Comunicação": random.randint(0, 100),
        "Futuro": random.randint(0, 100)
    }
    
    media = sum(categorias.values()) // len(categorias)
    
    embed = discord.Embed(
        title="🔮 Análise Detalhada",
        description=f"{pessoa1.mention} ❤️ {pessoa2.mention}",
        color=discord.Color.purple()
    )
    
    for cat, valor in categorias.items():
        barras = "█" * (valor // 10) + "░" * (10 - (valor // 10))
        embed.add_field(name=cat, value=f"{valor}% `{barras}`", inline=False)
    
    embed.add_field(name="📊 Média", value=f"**{media}%**", inline=False)
    
    await interaction.response.send_message(embed=embed)

# ==================== SISTEMA DE CASAMENTO ====================

@bot.tree.command(name="pedir", description="💍 Pedir em casamento (2000 moedas)")
async def pedir(interaction: discord.Interaction, pessoa: discord.Member):
    user_id = str(interaction.user.id)
    target_id = str(pessoa.id)
    
    if pessoa == interaction.user:
        await interaction.response.send_message("❌ Não pode casar consigo mesmo!")
        return
    
    if pessoa.bot:
        await interaction.response.send_message("❌ Não pode casar com bots!")
        return
    
    for data in bot.marriage_data.values():
        if (data["pessoa1"] == user_id and data["pessoa2"] == target_id) or \
           (data["pessoa1"] == target_id and data["pessoa2"] == user_id):
            await interaction.response.send_message("❌ Vocês já são casados!")
            return
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 2000:
        await interaction.response.send_message("❌ Precisa de 2000 moedas!")
        return
    
    bot.user_balances[user_id] -= 2000
    bot.save_data()
    
    embed = discord.Embed(
        title="💍 PEDIDO DE CASAMENTO!",
        description=f"{interaction.user.mention} pediu {pessoa.mention} em casamento!",
        color=discord.Color.from_str("#FF69B4")
    )
    
    embed.add_field(
        name="💝 O que fazer?",
        value=f"{pessoa.mention}\n`/aceitar {interaction.user.mention}` para aceitar\n`/recusar {interaction.user.mention}` para recusar",
        inline=False
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="aceitar", description="💞 Aceitar pedido de casamento")
async def aceitar(interaction: discord.Interaction, pessoa: discord.Member):
    user_id = str(interaction.user.id)
    pessoa_id = str(pessoa.id)
    
    marriage_id = f"{pessoa_id}-{user_id}-{datetime.now().timestamp()}"
    
    bot.marriage_data[marriage_id] = {
        "pessoa1": pessoa_id,
        "pessoa2": user_id,
        "data_casamento": datetime.now().isoformat(),
        "aniversarios_comemorados": 0,
        "luademel": True,
        "presentes": []
    }
    
    if pessoa_id not in bot.user_balances:
        bot.user_balances[pessoa_id] = 0
    if user_id not in bot.user_balances:
        bot.user_balances[user_id] = 0
    
    bot.user_balances[pessoa_id] += 1000
    bot.user_balances[user_id] += 1000
    bot.save_data()
    
    embed = discord.Embed(
        title="💞 CASAMENTO REALIZADO!",
        description=f"🎉 {pessoa.mention} e {interaction.user.mention} estão casados!",
        color=discord.Color.gold()
    )
    
    embed.add_field(name="💰 Bônus", value="Ambos ganharam 1000 moedas!", inline=False)
    embed.add_field(name="🌙 Lua de Mel", value="Ativa por 7 dias!", inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="recusar", description="💔 Recusar pedido de casamento")
async def recusar(interaction: discord.Interaction, pessoa: discord.Member):
    embed = discord.Embed(
        title="💔 PEDIDO RECUSADO",
        description=f"{interaction.user.mention} recusou {pessoa.mention}...",
        color=discord.Color.dark_gray()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="divorciar", description="💔 Divorciar (5000 moedas)")
async def divorciar(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    casamento_atual = None
    casamento_id = None
    
    for m_id, data in bot.marriage_data.items():
        if data["pessoa1"] == user_id or data["pessoa2"] == user_id:
            casamento_atual = data
            casamento_id = m_id
            break
    
    if not casamento_atual:
        await interaction.response.send_message("❌ Você não está casado!")
        return
    
    if user_id in bot.divorce_cooldowns:
        if datetime.now() - bot.divorce_cooldowns[user_id] < timedelta(days=7):
            await interaction.response.send_message("❌ Aguarde 7 dias!")
            return
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 5000:
        await interaction.response.send_message("❌ Precisa de 5000 moedas!")
        return
    
    bot.user_balances[user_id] -= 5000
    bot.divorce_cooldowns[user_id] = datetime.now()
    
    del bot.marriage_data[casamento_id]
    bot.save_data()
    
    await interaction.response.send_message("💔 Divórcio realizado! 5000 moedas deduzidas.")

@bot.tree.command(name="casamento", description="💒 Ver informações do casamento")
async def casamento(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    casamento_atual = None
    for data in bot.marriage_data.values():
        if data["pessoa1"] == user_id or data["pessoa2"] == user_id:
            casamento_atual = data
            break
    
    if not casamento_atual:
        await interaction.response.send_message("❌ Você não está casado!")
        return
    
    conjuge_id = casamento_atual["pessoa2"] if casamento_atual["pessoa1"] == user_id else casamento_atual["pessoa1"]
    conjuge = interaction.guild.get_member(int(conjuge_id))
    
    if not conjuge:
        await interaction.response.send_message("❌ Cônjuge não encontrado!")
        return
    
    data_casamento = datetime.fromisoformat(casamento_atual["data_casamento"])
    tempo_casado = datetime.now() - data_casamento
    
    dias = tempo_casado.days
    horas = tempo_casado.seconds // 3600
    
    embed = discord.Embed(
        title="💒 Casamento",
        description=f"{interaction.user.mention} ❤️ {conjuge.mention}",
        color=discord.Color.from_str("#FF69B4")
    )
    
    embed.add_field(name="📅 Casados há", value=f"**{dias} dias** e **{horas} horas**", inline=True)
    embed.add_field(name="💝 Aniversários", value=f"**{casamento_atual['aniversarios_comemorados']}**", inline=True)
    
    if casamento_atual["presentes"]:
        presentes = "\n".join(casamento_atual["presentes"][-3:])
        embed.add_field(name="🎁 Últimos presentes", value=presentes, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="presentear", description="🎁 Dar presente ao cônjuge (100 moedas)")
async def presentear(interaction: discord.Interaction, presente: str):
    user_id = str(interaction.user.id)
    
    casamento_atual = None
    for data in bot.marriage_data.values():
        if data["pessoa1"] == user_id or data["pessoa2"] == user_id:
            casamento_atual = data
            break
    
    if not casamento_atual:
        await interaction.response.send_message("❌ Você não está casado!")
        return
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 100:
        await interaction.response.send_message("❌ Precisa de 100 moedas!")
        return
    
    bot.user_balances[user_id] -= 100
    
    if "presentes" not in casamento_atual:
        casamento_atual["presentes"] = []
    
    conjuge_id = casamento_atual["pessoa2"] if casamento_atual["pessoa1"] == user_id else casamento_atual["pessoa1"]
    casamento_atual["presentes"].append(f"{interaction.user.name} deu: {presente}")
    
    bot.save_data()
    
    await interaction.response.send_message(f"🎁 Presente dado para <@{conjuge_id}>!")

@bot.tree.command(name="aniversario", description="🎂 Comemorar aniversário de casamento")
async def aniversario(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    casamento_atual = None
    for data in bot.marriage_data.values():
        if data["pessoa1"] == user_id or data["pessoa2"] == user_id:
            casamento_atual = data
            break
    
    if not casamento_atual:
        await interaction.response.send_message("❌ Você não está casado!")
        return
    
    data_casamento = datetime.fromisoformat(casamento_atual["data_casamento"])
    hoje = datetime.now()
    
    if hoje.month == data_casamento.month and hoje.day == data_casamento.day:
        anos = hoje.year - data_casamento.year
        
        if anos > casamento_atual["aniversarios_comemorados"]:
            casamento_atual["aniversarios_comemorados"] = anos
            
            if user_id not in bot.user_balances:
                bot.user_balances[user_id] = 0
            bot.user_balances[user_id] += 500 * anos
            
            conjuge_id = casamento_atual["pessoa2"] if casamento_atual["pessoa1"] == user_id else casamento_atual["pessoa1"]
            if conjuge_id not in bot.user_balances:
                bot.user_balances[conjuge_id] = 0
            bot.user_balances[conjuge_id] += 500 * anos
            
            bot.save_data()
            
            embed = discord.Embed(
                title="🎂 FELIZ ANIVERSÁRIO!",
                description=f"**{anos}** anos juntos!",
                color=discord.Color.gold()
            )
            
            embed.add_field(name="💰 Bônus", value=f"Ambos ganharam {500 * anos} moedas!", inline=False)
            
            await interaction.response.send_message(embed=embed)
        else:
            await interaction.response.send_message("❌ Aniversário já comemorado!")
    else:
        await interaction.response.send_message("❌ Hoje não é aniversário!")

@bot.tree.command(name="luademel", description="🌙 Ativar modo lua de mel")
async def luademel(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    casamento_atual = None
    for data in bot.marriage_data.values():
        if data["pessoa1"] == user_id or data["pessoa2"] == user_id:
            casamento_atual = data
            break
    
    if not casamento_atual:
        await interaction.response.send_message("❌ Você não está casado!")
        return
    
    if not casamento_atual.get("luademel", False):
        await interaction.response.send_message("❌ Lua de mel já acabou!")
        return
    
    data_casamento = datetime.fromisoformat(casamento_atual["data_casamento"])
    if datetime.now() - data_casamento > timedelta(days=7):
        casamento_atual["luademel"] = False
        bot.save_data()
        await interaction.response.send_message("❌ Lua de mel acabou!")
        return
    
    conjuge_id = casamento_atual["pessoa2"] if casamento_atual["pessoa1"] == user_id else casamento_atual["pessoa1"]
    dias_restantes = 7 - (datetime.now() - data_casamento).days
    
    embed = discord.Embed(
        title="🌙 LUA DE MEL",
        description=f"{interaction.user.mention} ❤️ <@{conjuge_id}>",
        color=discord.Color.from_str("#FF69B4")
    )
    
    embed.add_field(name="⏳ Dias restantes", value=f"**{dias_restantes}** dias", inline=False)
    
    await interaction.response.send_message(embed=embed)

# ==================== SISTEMA DE SIGNOS E PRESENTES ====================

@bot.tree.command(name="signos", description="♈ Compatibilidade de signos")
async def signos(interaction: discord.Interaction, signo1: str, signo2: str):
    signos_validos = ["Áries", "Touro", "Gêmeos", "Câncer", "Leão", "Virgem", 
                      "Libra", "Escorpião", "Sagitário", "Capricórnio", "Aquário", "Peixes"]
    
    if signo1 not in signos_validos or signo2 not in signos_validos:
        await interaction.response.send_message(f"❌ Signos válidos: {', '.join(signos_validos)}")
        return
    
    compatibilidade = random.randint(40, 100)
    
    embed = discord.Embed(title="♈ Compatibilidade de Signos", color=discord.Color.blue())
    embed.add_field(name="Signo 1", value=signo1, inline=True)
    embed.add_field(name="Signo 2", value=signo2, inline=True)
    embed.add_field(name="Compatibilidade", value=f"**{compatibilidade}%**", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="loja_presentes", description="🎁 Loja de presentes")
async def loja_presentes(interaction: discord.Interaction):
    presentes = {
        "🌹 Rosa": 50,
        "🍫 Chocolate": 75,
        "🧸 Ursinho": 100,
        "💍 Anel": 500,
        "💐 Buquê": 150,
        "🎂 Bolo": 200,
        "✉️ Carta": 30,
        "🎫 Cinema": 120,
        "🍷 Jantar": 300,
        "💎 Colar": 800
    }
    
    embed = discord.Embed(title="🎁 Loja de Presentes", color=discord.Color.gold())
    
    for presente, preco in presentes.items():
        embed.add_field(name=presente, value=f"{preco} moedas", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="comprar_presente", description="🎁 Comprar e dar um presente")
async def comprar_presente(interaction: discord.Interaction, presente: str, usuario: discord.Member):
    presentes = {
        "🌹 Rosa": 50, "🍫 Chocolate": 75, "🧸 Ursinho": 100, "💍 Anel": 500,
        "💐 Buquê": 150, "🎂 Bolo": 200, "✉️ Carta": 30, "🎫 Cinema": 120,
        "🍷 Jantar": 300, "💎 Colar": 800
    }
    
    if presente not in presentes:
        await interaction.response.send_message("❌ Presente não encontrado! Use /loja_presentes")
        return
    
    preco = presentes[presente]
    user_id = str(interaction.user.id)
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < preco:
        await interaction.response.send_message("❌ Saldo insuficiente!")
        return
    
    bot.user_balances[user_id] -= preco
    
    target_id = str(usuario.id)
    if target_id not in bot.user_inventory:
        bot.user_inventory[target_id] = []
    
    bot.user_inventory[target_id].append({
        "presente": presente,
        "de": interaction.user.name,
        "data": datetime.now().isoformat()
    })
    
    bot.save_data()
    
    await interaction.response.send_message(f"🎁 {presente} dado para {usuario.mention}!")

@bot.tree.command(name="meuspresentes", description="📦 Ver presentes recebidos")
async def meuspresentes(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.user_inventory or not bot.user_inventory[user_id]:
        await interaction.response.send_message("❌ Você não tem presentes!")
        return
    
    embed = discord.Embed(title=f"📦 Presentes de {interaction.user.display_name}", color=discord.Color.gold())
    
    for presente in bot.user_inventory[user_id][-10:]:
        data = datetime.fromisoformat(presente["data"]).strftime("%d/%m/%Y")
        embed.add_field(
            name=presente["presente"],
            value=f"De: {presente['de']} | {data}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

# ==================== SISTEMA DE ECONOMIA ====================

@bot.tree.command(name="daily", description="💰 Recompensa diária")
async def daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    hoje = datetime.now().date()
    
    if user_id in bot.daily_cooldowns:
        ultimo = datetime.fromisoformat(bot.daily_cooldowns[user_id]).date()
        if hoje == ultimo:
            await interaction.response.send_message("❌ Daily já coletado hoje!")
            return
    
    valor = 500
    if user_id not in bot.user_balances:
        bot.user_balances[user_id] = 0
    
    bot.user_balances[user_id] += valor
    bot.daily_cooldowns[user_id] = datetime.now().isoformat()
    bot.save_data()
    
    await interaction.response.send_message(f"💰 Você ganhou {valor} moedas! Saldo: {bot.user_balances[user_id]}")

@bot.tree.command(name="saldo", description="💰 Ver saldo")
async def saldo(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    if membro is None:
        membro = interaction.user
    
    user_id = str(membro.id)
    saldo_atual = bot.user_balances.get(user_id, 0)
    
    await interaction.response.send_message(f"💰 Saldo de {membro.display_name}: **{saldo_atual} moedas**")

@bot.tree.command(name="transferir", description="💸 Transferir moedas")
async def transferir(interaction: discord.Interaction, membro: discord.Member, valor: int):
    if valor <= 0:
        await interaction.response.send_message("❌ Valor inválido!")
        return
    
    if membro == interaction.user:
        await interaction.response.send_message("❌ Não pode transferir para si mesmo!")
        return
    
    user_id = str(interaction.user.id)
    target_id = str(membro.id)
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < valor:
        await interaction.response.send_message("❌ Saldo insuficiente!")
        return
    
    bot.user_balances[user_id] -= valor
    
    if target_id not in bot.user_balances:
        bot.user_balances[target_id] = 0
    
    bot.user_balances[target_id] += valor
    bot.save_data()
    
    await interaction.response.send_message(f"💸 {valor} moedas transferidas para {membro.mention}!")

@bot.tree.command(name="slot", description="🎰 Caça-níqueis (50 moedas)")
async def slot(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 50:
        await interaction.response.send_message("❌ Precisa de 50 moedas!")
        return
    
    bot.user_balances[user_id] -= 50
    
    simbolos = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣"]
    resultado = [random.choice(simbolos) for _ in range(3)]
    
    premio = 0
    if resultado[0] == resultado[1] == resultado[2]:
        if resultado[0] == "7️⃣":
            premio = 1000
        elif resultado[0] == "💎":
            premio = 500
        else:
            premio = 200
    elif resultado[0] == resultado[1] or resultado[1] == resultado[2]:
        premio = 75
    
    if premio > 0:
        bot.user_balances[user_id] += premio
    
    bot.save_data()
    
    texto = f"` {resultado[0]} | {resultado[1]} | {resultado[2]} `\n"
    if premio > 0:
        texto += f"🏆 Ganhou {premio} moedas!"
    else:
        texto += "😢 Não foi dessa vez!"
    
    texto += f"\n💰 Saldo: {bot.user_balances[user_id]}"
    
    await interaction.response.send_message(f"🎰 **Caça-níqueis**\n{texto}")

@bot.tree.command(name="dado", description="🎲 Rolar um dado")
async def dado(interaction: discord.Interaction, lados: int = 6):
    if lados < 2:
        await interaction.response.send_message("❌ Dado precisa ter pelo menos 2 lados!")
        return
    
    resultado = random.randint(1, lados)
    await interaction.response.send_message(f"🎲 Resultado: **{resultado}** (d{lados})")

@bot.tree.command(name="cara_coroa", description="🪙 Cara ou coroa")
async def cara_coroa(interaction: discord.Interaction, escolha: str, aposta: int):
    user_id = str(interaction.user.id)
    
    if escolha.lower() not in ["cara", "coroa"]:
        await interaction.response.send_message("❌ Escolha 'cara' ou 'coroa'!")
        return
    
    if aposta <= 0:
        await interaction.response.send_message("❌ Aposta inválida!")
        return
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < aposta:
        await interaction.response.send_message("❌ Saldo insuficiente!")
        return
    
    bot.user_balances[user_id] -= aposta
    
    resultado = random.choice(["cara", "coroa"])
    ganhou = resultado == escolha.lower()
    
    if ganhou:
        premio = aposta * 2
        bot.user_balances[user_id] += premio
        msg = f"🎉 Deu **{resultado}**! Ganhou {premio} moedas!"
    else:
        msg = f"😢 Deu **{resultado}**! Perdeu {aposta} moedas!"
    
    bot.save_data()
    
    await interaction.response.send_message(f"🪙 {msg}\n💰 Saldo: {bot.user_balances[user_id]}")

@bot.tree.command(name="ppt", description="✂️ Pedra, papel ou tesoura")
async def ppt(interaction: discord.Interaction, escolha: str):
    escolhas = ["pedra", "papel", "tesoura"]
    
    if escolha.lower() not in escolhas:
        await interaction.response.send_message("❌ Escolha: pedra, papel ou tesoura!")
        return
    
    bot_choice = random.choice(escolhas)
    
    if escolha.lower() == bot_choice:
        resultado = "Empate!"
        cor = discord.Color.blue()
    elif (escolha.lower() == "pedra" and bot_choice == "tesoura") or \
         (escolha.lower() == "papel" and bot_choice == "pedra") or \
         (escolha.lower() == "tesoura" and bot_choice == "papel"):
        resultado = "Você ganhou!"
        cor = discord.Color.green()
    else:
        resultado = "Você perdeu!"
        cor = discord.Color.red()
    
    emojis = {"pedra": "🪨", "papel": "📄", "tesoura": "✂️"}
    
    embed = discord.Embed(
        title="✂️ PPT",
        description=f"Você: {emojis[escolha.lower()]}\nBot: {emojis[bot_choice]}",
        color=cor
    )
    
    embed.add_field(name="Resultado", value=resultado)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="adivinha", description="🔢 Jogo de adivinhação (30 moedas)")
async def adivinha(interaction: discord.Interaction, numero: int):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 30:
        await interaction.response.send_message("❌ Precisa de 30 moedas!")
        return
    
    if numero < 1 or numero > 10:
        await interaction.response.send_message("❌ Escolha um número entre 1 e 10!")
        return
    
    bot.user_balances[user_id] -= 30
    
    secreto = random.randint(1, 10)
    
    if numero == secreto:
        premio = 150
        bot.user_balances[user_id] += premio
        msg = f"🎉 ACERTOU! O número era {secreto}! Ganhou {premio} moedas!"
    else:
        msg = f"😢 Errou! O número era {secreto}. Perdeu 30 moedas!"
    
    bot.save_data()
    
    await interaction.response.send_message(f"🔢 {msg}\n💰 Saldo: {bot.user_balances[user_id]}")

# ==================== COMANDOS BÁSICOS ====================

@bot.tree.command(name="ping", description="🏓 Latência do bot")
async def ping(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 Pong! {round(bot.latency * 1000)}ms")

@bot.tree.command(name="userinfo", description="👤 Informações do usuário")
async def userinfo(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    if membro is None:
        membro = interaction.user
    
    embed = discord.Embed(title=f"Info: {membro.name}", color=membro.color)
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.add_field(name="ID", value=membro.id, inline=True)
    embed.add_field(name="Conta criada", value=membro.created_at.strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Entrou em", value=membro.joined_at.strftime("%d/%m/%Y"), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="📊 Informações do servidor")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"Info: {guild.name}", color=discord.Color.blue())
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    embed.add_field(name="ID", value=guild.id, inline=True)
    embed.add_field(name="Dono", value=guild.owner.mention, inline=True)
    embed.add_field(name="Membros", value=guild.member_count, inline=True)
    embed.add_field(name="Canais", value=len(guild.channels), inline=True)
    embed.add_field(name="Cargos", value=len(guild.roles), inline=True)
    embed.add_field(name="Criado em", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="avatar", description="🖼️ Avatar do usuário")
async def avatar(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    if membro is None:
        membro = interaction.user
    
    embed = discord.Embed(title=f"Avatar de {membro.display_name}")
    embed.set_image(url=membro.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="calcular", description="🧮 Calculadora")
async def calcular(interaction: discord.Interaction, num1: float, operador: str, num2: float):
    try:
        if operador == "+":
            resultado = num1 + num2
        elif operador == "-":
            resultado = num1 - num2
        elif operador == "*" or operador == "x":
            resultado = num1 * num2
        elif operador == "/":
            if num2 == 0:
                await interaction.response.send_message("❌ Divisão por zero!")
                return
            resultado = num1 / num2
        elif operador == "^":
            resultado = num1 ** num2
        else:
            await interaction.response.send_message("❌ Operador inválido!")
            return
        
        await interaction.response.send_message(f"🧮 Resultado: `{num1} {operador} {num2} = {resultado}`")
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}")

@bot.tree.command(name="ola_mundo", description="👋 Mensagem de boas vindas")
async def ola_mundo(interaction: discord.Interaction):
    await interaction.response.send_message(f"Olá {interaction.user.mention}! Bem-vindo ao bot Fort! 🎉")

# ==================== COMANDOS DE DIVERSÃO ====================

@bot.tree.command(name="8ball", description="🎱 Pergunte ao destino")
async def eight_ball(interaction: discord.Interaction, pergunta: str):
    respostas = [
        "Sim!", "Não!", "Talvez...", "Com certeza!", "Nem pensar!",
        "Os deuses dizem que sim!", "Melhor não dizer agora.", "Pode confiar!"
    ]
    
    embed = discord.Embed(
        title="🎱 8Ball",
        description=f"**Pergunta:** {pergunta}\n**Resposta:** {random.choice(respostas)}",
        color=discord.Color.purple()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="piada", description="😂 Piada aleatória")
async def piada(interaction: discord.Interaction):
    piadas = [
        "Por que o computador foi preso? Porque executou um comando!",
        "O que o zero disse para o oito? Belo cinto!",
        "Por que os elétrons nunca pagam contas? Porque estão sempre em débito!",
        "O que o pato disse para a pata? Vem quá!",
        "Qual o cúmulo da rapidez? Fechar o zíper com uma bala!"
    ]
    
    await interaction.response.send_message(f"😂 {random.choice(piadas)}")

@bot.tree.command(name="conselho", description="💡 Conselho aleatório")
async def conselho(interaction: discord.Interaction):
    conselhos = [
        "Beba água! 💧", "Durma bem! 😴", "Seja gentil! 🧘",
        "Aprenda algo novo! 📚", "Sorria! 😊", "Ajude alguém! 🤝"
    ]
    
    await interaction.response.send_message(f"💡 {random.choice(conselhos)}")

@bot.tree.command(name="fato", description="🔍 Fato curioso")
async def fato(interaction: discord.Interaction):
    fatos = [
        "Flamingos nascem cinzas!", "Coração da baleia azul é enorme!",
        "Ursos polares têm pele preta!", "Mel nunca estraga!",
        "Bananas são radioativas!", "Polvos têm três corações!"
    ]
    
    await interaction.response.send_message(f"🔍 {random.choice(fatos)}")

@bot.tree.command(name="cafune", description="🥰 Faça carinho")
async def cafune(interaction: discord.Interaction, membro: discord.Member):
    await interaction.response.send_message(f"{interaction.user.mention} fez carinho em {membro.mention}! 🥰")

@bot.tree.command(name="beijo", description="💋 Beije alguém")
async def beijo(interaction: discord.Interaction, membro: discord.Member):
    await interaction.response.send_message(f"{interaction.user.mention} beijou {membro.mention}! 💋")

@bot.tree.command(name="abraço", description="🤗 Abrace alguém")
async def abraco(interaction: discord.Interaction, membro: discord.Member):
    await interaction.response.send_message(f"{interaction.user.mention} abraçou {membro.mention}! 🤗")

@bot.tree.command(name="baitola", description="🏳️‍🌈 Mensagem especial")
async def baitola(interaction: discord.Interaction, membro: discord.Member):
    frases = [
        f"{membro.mention} é o maior baitola do servidor! 🏳️‍🌈",
        f"Parabéns {membro.mention}, você é o baitola master! 🏆"
    ]
    await interaction.response.send_message(random.choice(frases))

# ==================== COMANDO DE AJUDA COMPLETO ====================

@bot.tree.command(name="ajuda", description="📚 Todos os comandos")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Comandos do Bot Fort",
        description="**Sistema Completo - 50+ Comandos!**",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📢 **CHAMADAS**",
        value="`/chamada` - Criar chamada\n"
              "`/chamada_info` - Ver informações\n"
              "`/chamada_lista` - Lista completa\n"
              "`/chamada_cancelar` - Cancelar\n",
        inline=False
    )
    
    embed.add_field(
        name="💖 **SHIP**",
        value="`/ship` - Calcular amor\n"
              "`/shippar` - Criar ship\n"
              "`/likeship` - Dar like\n"
              "`/shipinfo` - Info do ship\n"
              "`/meusships` - Seus ships\n"
              "`/topship` - Ranking\n"
              "`/shiplist` - Listar ships\n"
              "`/calcular_amor` - Análise detalhada\n",
        inline=True
    )
    
    embed.add_field(
        name="💒 **CASAMENTO**",
        value="`/pedir` - Pedir\n"
              "`/aceitar` - Aceitar\n"
              "`/recusar` - Recusar\n"
              "`/divorciar` - Divorciar\n"
              "`/casamento` - Status\n"
              "`/presentear` - Presentear\n"
              "`/aniversario` - Aniversário\n"
              "`/luademel` - Lua de mel\n",
        inline=True
    )
    
    embed.add_field(
        name="💰 **ECONOMIA**",
        value="`/daily` - Daily\n"
              "`/saldo` - Ver saldo\n"
              "`/transferir` - Transferir\n"
              "`/slot` - Caça-níqueis\n"
              "`/dado` - Rolar dado\n"
              "`/cara_coroa` - Cara ou coroa\n"
              "`/ppt` - Pedra papel tesoura\n"
              "`/adivinha` - Adivinhação\n",
        inline=True
    )
    
    embed.add_field(
        name="💝 **PRESENTES**",
        value="`/loja_presentes` - Loja\n"
              "`/comprar_presente` - Comprar\n"
              "`/meuspresentes` - Inventário\n"
              "`/signos` - Compatibilidade\n",
        inline=True
    )
    
    embed.add_field(
        name="🤖 **BÁSICOS**",
        value="`/ping` - Latência\n"
              "`/userinfo` - Info usuário\n"
              "`/serverinfo` - Info servidor\n"
              "`/avatar` - Ver avatar\n"
              "`/calcular` - Calculadora\n"
              "`/ola_mundo` - Boas vindas\n",
        inline=True
    )
    
    embed.add_field(
        name="🎮 **DIVERSÃO**",
        value="`/8ball` - Perguntas\n"
              "`/piada` - Piadas\n"
              "`/conselho` - Conselhos\n"
              "`/fato` - Fatos\n"
              "`/cafune` - Carinho\n"
              "`/beijo` - Beijar\n"
              "`/abraço` - Abraçar\n"
              "`/baitola` - 🏳️‍🌈\n",
        inline=True
    )
    
    embed.set_footer(text="Total: 50+ comandos! Use / antes de cada comando")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

# ==================== INICIAR BOT ====================
if __name__ == "__main__":
    print("="*60)
    print("🚀 BOT FORT - VERSÃO COMPLETÍSSIMA COM SQLITE")
    print("="*60)
    print("\n📢 SISTEMAS CARREGADOS:")
    print("✅ Sistema de Chamadas (com lista de presença)")
    print("✅ Sistema de Ship (likes, ranking, histórico)")
    print("✅ Sistema de Casamento (com economia)")
    print("✅ Sistema de Presentes e Signos")
    print("✅ Sistema de Economia (daily, slots)")
    print("✅ Comandos de Diversão e Básicos")
    print("✅ Banco de Dados SQLite (dados permanentes)")
    print("\n📊 TOTAL: 50+ COMANDOS!")
    print("="*60)
    
    # PEGA O TOKEN DA VARIÁVEL DE AMBIENTE
    TOKEN = os.environ.get('DISCORD_TOKEN')
    if not TOKEN:
        print("❌ ERRO: Token não encontrado!")
        print("Defina a variável de ambiente DISCORD_TOKEN")
        sys.exit(1)
    
    try:
        bot.run(TOKEN)
    except discord.LoginFailure:
        print("❌ Token inválido!")
    except Exception as e:
        print(f"❌ Erro: {e}")