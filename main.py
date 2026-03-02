import sys
import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import random
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta
from typing import Optional
import math
import sqlite3
import os
import time
import logging
import traceback

# ===== CONFIGURAÇÃO DO TOKEN =====
DISCORD_TOKEN = 'SEU_TOKEN_AQUI'

# ===== IMPORTS DO SERVIDOR WEB =====
from flask import Flask, jsonify
import threading

# Configurar encoding e logging
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO)

# Configurações
PREFIX = '!'
API_NINJAS_KEY = 'SUA_API_KEY'

# ===== SERVIDOR WEB =====
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "bot": "Fort Tithipong",
        "sistemas": "fort + 70+ comandos"
    })

@app.route('/health')
@app.route('/healthcheck')
def health():
    return "OK", 200

@app.route('/ping')
def ping():
    return "pong", 200

def run_webserver():
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)

def keep_alive():
    server = threading.Thread(target=run_webserver, daemon=True)
    server.start()
    print(f"✅ Servidor web rodando na porta {os.environ.get('PORT', 10000)}")

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
        
        # ===== SISTEMA DE fort =====
        self.fort_data = {}  # {user_id: {"quantidade": x, "ultima_vez": datetime}}
        self.fort_ranking = {}  # Ranking de usuários
        self.fort_loja = {
            "🌿 Baseado": {"preco": 50, "desc": "Um baseado pra relaxar"},
            "💨 Sedinha": {"preco": 30, "desc": "Seda de qualidade"},
            "🔥 Isqueiro": {"preco": 20, "desc": "Pra acender a braba"},
            "🌱 Bud": {"preco": 100, "desc": "Flor de qualidade"},
            "🍪 Cookies": {"preco": 150, "desc": "Cookies especiais"},
            "💧 Vaporizador": {"preco": 500, "desc": "Vape de última geração"},
            "🌿🍯 Haxixe": {"preco": 300, "desc": "Concentrado puro"},
            "🚬 Bong": {"preco": 400, "desc": "Bong de vidro"},
            "🌿💊 Comestível": {"preco": 200, "desc": "Brownie mágico"},
            "🌿🚬 Beck": {"preco": 80, "desc": "Fininho bolado"}
        }
        
        # Inicializa banco de dados e carrega dados
        self.init_database()
        self.load_data()
    
    # ===== FUNÇÕES SQLITE =====
    def init_database(self):
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        c.execute('''CREATE TABLE IF NOT EXISTS economia
                     (user_id TEXT PRIMARY KEY, saldo INTEGER)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS daily_cooldowns
                     (user_id TEXT PRIMARY KEY, data TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS divorce_cooldowns
                     (user_id TEXT PRIMARY KEY, data TEXT)''')
        
        # ===== TABELA DA fort =====
        c.execute('''CREATE TABLE IF NOT EXISTS fort
                     (user_id TEXT PRIMARY KEY, quantidade INTEGER, ultima_vez TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS fort_inventory
                     (user_id TEXT, item TEXT, quantidade INTEGER,
                      PRIMARY KEY (user_id, item))''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS fort_ranking
                     (user_id TEXT PRIMARY KEY, total INTEGER)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS dados_json
                     (tipo TEXT PRIMARY KEY, dados TEXT)''')
        
        conn.commit()
        conn.close()
        print("✅ Banco de dados SQLite inicializado!")
    
    def load_data(self):
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        # Carrega economia
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
        
        # ===== CARREGA DADOS DA fort =====
        c.execute('SELECT user_id, quantidade, ultima_vez FROM fort')
        for user_id, quantidade, ultima_vez in c.fetchall():
            self.fort_data[user_id] = {
                "quantidade": quantidade,
                "ultima_vez": datetime.fromisoformat(ultima_vez) if ultima_vez else None
            }
        
        c.execute('SELECT user_id, total FROM fort_ranking')
        for user_id, total in c.fetchall():
            self.fort_ranking[user_id] = total
        
        # Carrega outros dados
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
        self.import_from_json_if_empty()
    
    def import_from_json_if_empty(self):
        if not self.user_balances:
            try:
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
                self.save_data()
            except FileNotFoundError:
                print("ℹ️ Nenhum arquivo JSON antigo encontrado.")
            except Exception as e:
                print(f"⚠️ Erro ao importar JSONs: {e}")
    
    def save_data(self):
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        # Salva economia
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
        
        # ===== SALVA DADOS DA fort =====
        for user_id, data in self.fort_data.items():
            ultima_vez_str = data["ultima_vez"].isoformat() if data["ultima_vez"] else None
            c.execute('''INSERT OR REPLACE INTO fort (user_id, quantidade, ultima_vez)
                         VALUES (?, ?, ?)''', (user_id, data["quantidade"], ultima_vez_str))
        
        for user_id, total in self.fort_ranking.items():
            c.execute('''INSERT OR REPLACE INTO fort_ranking (user_id, total)
                         VALUES (?, ?)''', (user_id, total))
        
        # Salva outros dados
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
        print(f"⏰ Chamada com Tempo: ATIVO")
        print(f"💖 Sistema de Ship: ATIVO")
        print(f"💒 Sistema de Casamento: ATIVO")
        print(f"💰 Sistema de Economia: ATIVO")
        print(f"🌿 SISTEMA DE fort: ATIVO")
        print(f"🎮 Sistema de Jogos: ATIVO")
        print(f"🎭 Comandos com GIF: ATIVO")
        print(f"💾 Banco de Dados: SQLite")
        await self.change_presence(activity=discord.Game(name="🌿 Use /fort | 80+ comandos!"))

bot = Fort()

# ==================== SISTEMA DE fort ====================

class fortModal(Modal, title="🌿 fort - Registro"):
    quantidade = TextInput(
        label="Quantidade (gramas)",
        placeholder="Digite a quantidade...",
        required=True,
        min_length=1,
        max_length=3
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        try:
            qtd = int(self.quantidade.value)
            if qtd <= 0 or qtd > 100:
                await interaction.response.send_message("❌ Quantidade inválida! (1-100 gramas)", ephemeral=True)
                return
            
            user_id = str(interaction.user.id)
            agora = datetime.now()
            
            # Verifica cooldown
            if user_id in bot.fort_data:
                ultima = bot.fort_data[user_id].get("ultima_vez")
                if ultima and (agora - ultima) < timedelta(hours=1):
                    tempo_restante = timedelta(hours=1) - (agora - ultima)
                    minutos = int(tempo_restante.total_seconds() / 60)
                    await interaction.response.send_message(
                        f"⏰ Calma lá, maconheiro! Espere **{minutos} minutos** pra registrar de novo!",
                        ephemeral=True
                    )
                    return
            
            # Atualiza dados
            if user_id not in bot.fort_data:
                bot.fort_data[user_id] = {"quantidade": 0, "ultima_vez": None}
            
            bot.fort_data[user_id]["quantidade"] += qtd
            bot.fort_data[user_id]["ultima_vez"] = agora
            
            # Atualiza ranking
            if user_id not in bot.fort_ranking:
                bot.fort_ranking[user_id] = 0
            bot.fort_ranking[user_id] += qtd
            
            # Dá moedas (cada grama vale 10 moedas)
            ganho = qtd * 10
            if user_id not in bot.user_balances:
                bot.user_balances[user_id] = 0
            bot.user_balances[user_id] += ganho
            
            bot.save_data()
            
            embed = discord.Embed(
                title="🌿 REGISTRO DE fort",
                description=f"{interaction.user.mention} registrou **{qtd}g**!",
                color=discord.Color.green()
            )
            embed.add_field(name="📦 Total acumulado", value=f"{bot.fort_data[user_id]['quantidade']}g", inline=True)
            embed.add_field(name="💰 Ganho", value=f"{ganho} moedas", inline=True)
            embed.set_footer(text="Bons ventos e boa fumaça! 🌬️")
            
            await interaction.response.send_message(embed=embed)
            
        except ValueError:
            await interaction.response.send_message("❌ Digite um número válido!", ephemeral=True)

@bot.tree.command(name="fort", description="🌿 Registrar seu consumo de fort")
async def fort(interaction: discord.Interaction):
    modal = fortModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="fort_estoque", description="🌿 Ver seu estoque de fort")
async def fort_estoque(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.fort_data or bot.fort_data[user_id]["quantidade"] == 0:
        await interaction.response.send_message("❌ Você não tem nada registrado! Use `/fort` pra começar.")
        return
    
    data = bot.fort_data[user_id]
    ultima = data["ultima_vez"]
    
    embed = discord.Embed(
        title=f"🌿 Estoque de {interaction.user.display_name}",
        color=discord.Color.green()
    )
    embed.add_field(name="📦 Quantidade total", value=f"**{data['quantidade']}g**", inline=True)
    if ultima:
        embed.add_field(name="⏰ Último registro", value=f"<t:{int(ultima.timestamp())}:R>", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fort_ranking", description="🏆 Ranking dos maiores maconheiros")
async def fort_ranking(interaction: discord.Interaction):
    if not bot.fort_ranking:
        await interaction.response.send_message("❌ Ninguém registrou nada ainda!")
        return
    
    ranking = sorted(bot.fort_ranking.items(), key=lambda x: x[1], reverse=True)[:10]
    
    embed = discord.Embed(
        title="🏆 RANKING fort",
        description="Os maiores consumidores do servidor",
        color=discord.Color.green()
    )
    
    for i, (user_id, total) in enumerate(ranking, 1):
        user = interaction.guild.get_member(int(user_id))
        if user:
            medalha = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"{i}°"
            embed.add_field(
                name=f"{medalha} {user.display_name}",
                value=f"**{total}g** registrados",
                inline=False
            )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fort_loja", description="🛒 Loja de itens da fort")
async def fort_loja(interaction: discord.Interaction):
    embed = discord.Embed(
        title="🛒 LOJA DA fort",
        description="Compre com suas moedas! Use `/fort_comprar [item]`",
        color=discord.Color.green()
    )
    
    for item, dados in bot.fort_loja.items():
        embed.add_field(
            name=f"{item} - {dados['preco']} moedas",
            value=dados['desc'],
            inline=True
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fort_comprar", description="🛒 Comprar item da loja")
@app_commands.describe(item="Nome do item que quer comprar")
async def fort_comprar(interaction: discord.Interaction, item: str):
    user_id = str(interaction.user.id)
    
    # Procura o item (case insensitive)
    item_encontrado = None
    for nome, dados in bot.fort_loja.items():
        if item.lower() in nome.lower():
            item_encontrado = (nome, dados)
            break
    
    if not item_encontrado:
        await interaction.response.send_message("❌ Item não encontrado! Use `/fort_loja` pra ver os itens.")
        return
    
    nome_item, dados = item_encontrado
    preco = dados['preco']
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < preco:
        await interaction.response.send_message(f"❌ Você precisa de {preco} moedas!")
        return
    
    # Deduz moedas
    bot.user_balances[user_id] -= preco
    
    # Adiciona ao inventário (você pode expandir isso)
    embed = discord.Embed(
        title="✅ COMPRA REALIZADA!",
        description=f"{interaction.user.mention} comprou **{nome_item}** por **{preco} moedas**!",
        color=discord.Color.green()
    )
    embed.add_field(name="📝 Descrição", value=dados['desc'], inline=False)
    
    bot.save_data()
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fort_passar", description="🌿 Passar um baseado para alguém")
async def fort_passar(interaction: discord.Interaction, membro: discord.Member, quantidade: int = 1):
    user_id = str(interaction.user.id)
    target_id = str(membro.id)
    
    if user_id not in bot.fort_data or bot.fort_data[user_id]["quantidade"] < quantidade:
        await interaction.response.send_message("❌ Você não tem essa quantidade pra passar!")
        return
    
    # Transfere
    bot.fort_data[user_id]["quantidade"] -= quantidade
    
    if target_id not in bot.fort_data:
        bot.fort_data[target_id] = {"quantidade": 0, "ultima_vez": None}
    bot.fort_data[target_id]["quantidade"] += quantidade
    
    bot.save_data()
    
    embed = discord.Embed(
        title="🌿 BASEADO COMPARTILHADO!",
        description=f"{interaction.user.mention} passou **{quantidade}g** para {membro.mention}!",
        color=discord.Color.green()
    )
    embed.set_footer(text="Amizade é tudo! 🌬️")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="fort_reset", description="🔄 Resetar seu estoque (1000 moedas)")
async def fort_reset(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 1000:
        await interaction.response.send_message("❌ Precisa de 1000 moedas pra resetar!")
        return
    
    bot.user_balances[user_id] -= 1000
    if user_id in bot.fort_data:
        bot.fort_data[user_id]["quantidade"] = 0
    
    bot.save_data()
    
    await interaction.response.send_message("✅ Seu estoque foi resetado! Agora você tá limpo... por enquanto. 🌿")

# ==================== SISTEMA DE CHAMADAS ====================

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
            
            try:
                channel = bot.get_channel(int(call['channel_id']))
                if channel:
                    message = await channel.fetch_message(int(call['message_id']))
                    if message and message.embeds:
                        embed = message.embeds[0]
                        
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

@bot.tree.command(name="chamada", description="📢 Criar uma chamada com @everyone")
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
    
    embed.set_footer(text="Clique no botão abaixo para confirmar!")
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

# ==================== SISTEMA DE CHAMADA COM TEMPO ====================

class CallButtonComTempo(Button):
    def __init__(self, call_id: str, emoji: str, expira_em: datetime):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Confirmar Presença",
            emoji=emoji,
            custom_id=f"call_tempo_{call_id}"
        )
        self.call_id = call_id
        self.expira_em = expira_em
    
    async def callback(self, interaction: discord.Interaction):
        if datetime.now() > self.expira_em:
            await interaction.response.send_message("⏰ **Esta chamada EXPIROU!**", ephemeral=True)
            return
            
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
            
            try:
                channel = bot.get_channel(int(call['channel_id']))
                if channel:
                    message = await channel.fetch_message(int(call['message_id']))
                    if message and message.embeds:
                        embed = message.embeds[0]
                        
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
                        
                        novo_embed = discord.Embed(
                            title=embed.title,
                            description=embed.description,
                            color=discord.Color.blue()
                        )
                        
                        for field in embed.fields:
                            if not field.name.startswith("✅ Confirmados") and not field.name.startswith("⏰ Expira"):
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

class CallViewComTempo(View):
    def __init__(self, call_id: str, emoji: str, expira_em: datetime):
        super().__init__(timeout=None)
        self.add_item(CallButtonComTempo(call_id, emoji, expira_em))

@bot.tree.command(name="chamada_tempo", description="⏰ Criar chamada com tempo limite")
@app_commands.describe(
    titulo="Título do evento",
    data_hora="Data e hora",
    local="Local do evento",
    horas_limite="Horas para expirar",
    descricao="Descrição",
    emoji="Emoji do botão"
)
async def chamada_tempo(
    interaction: discord.Interaction,
    titulo: str,
    data_hora: str,
    local: str,
    horas_limite: int = 2,
    descricao: str = "",
    emoji: str = "✅"
):
    if not interaction.user.guild_permissions.mention_everyone:
        await interaction.response.send_message("❌ Você precisa da permissão `Mencionar @everyone`!", ephemeral=True)
        return
    
    call_id = f"{interaction.channel.id}-{int(datetime.now().timestamp())}"
    expira_em = datetime.now() + timedelta(hours=horas_limite)
    
    embed = discord.Embed(
        title=f"📢 {titulo}",
        description=descricao if descricao else "Clique no botão para confirmar!",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="📅 Data/Hora", value=data_hora, inline=True)
    embed.add_field(name="📍 Local", value=local, inline=True)
    embed.add_field(name="👤 Organizador", value=interaction.user.mention, inline=True)
    embed.add_field(name="⏰ Expira em", value=f"<t:{int(expira_em.timestamp())}:R>", inline=True)
    embed.add_field(name="✅ **Confirmados: 0**", value="Ninguém confirmou ainda", inline=False)
    
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    
    embed.set_footer(text="Após expirar, o botão não funcionará!")
    embed.timestamp = datetime.now()
    
    view = CallViewComTempo(call_id, emoji, expira_em)
    
    await interaction.response.send_message(
        content="@everyone 📢 **NOVA CHAMADA COM TEMPO LIMITE!** 📢",
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
        'expira_em': expira_em.isoformat(),
        'criado_em': datetime.now().isoformat()
    }
    
    bot.call_participants[call_id] = []
    bot.save_data()
    
    embed_confirm = discord.Embed(
        title="✅ Chamada Criada com Tempo!",
        description=f"**{titulo}** criada!",
        color=discord.Color.green()
    )
    
    embed_confirm.add_field(
        name="⏰ Expira",
        value=f"<t:{int(expira_em.timestamp())}:R>",
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
                    description=f"**{data['titulo']}** cancelada!",
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

# ==================== SISTEMA DE SHIP ====================

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

# ==================== COMANDOS COM GIFS ====================

gifs_abraco = [
    "https://i.imgur.com/qvwBvqP.gif",
    "https://i.imgur.com/QnUjqXH.gif", 
    "https://i.imgur.com/UAWqY6W.gif",
    "https://i.imgur.com/2U0X8zP.gif",
    "https://i.imgur.com/rKIDC7h.gif",
    "https://i.imgur.com/wOmOEwL.gif"
]

gifs_beijo = [
    "https://i.imgur.com/8K9L5xM.gif",
    "https://i.imgur.com/YI9H5pT.gif",
    "https://i.imgur.com/B7yX8Wz.gif",
    "https://i.imgur.com/f9UqRVL.gif"
]

gifs_carinho = [
    "https://i.imgur.com/K9F5V5z.gif",
    "https://i.imgur.com/NW7Y8vL.gif",
    "https://i.imgur.com/GZ8N9wW.gif",
    "https://i.imgur.com/6UqX9rV.gif"
]

gifs_tapa = [
    "https://i.imgur.com/m5J6F8v.gif",
    "https://i.imgur.com/LK7X8zN.gif",
    "https://i.imgur.com/X8R5vG9.gif"
]

gifs_festa = [
    "https://i.imgur.com/0A4K8Vn.gif",
    "https://i.imgur.com/X8R7WzL.gif",
    "https://i.imgur.com/M9Y5ZxK.gif"
]

@bot.tree.command(name="abraco_gif", description="🤗 Abraçar alguém com GIF")
async def abraco_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se abraçar! 🥲")
        return
    
    gif = random.choice(gifs_abraco)
    
    embed = discord.Embed(
        title="🤗 ABRAÇO!",
        description=f"{interaction.user.mention} abraçou {membro.mention}!",
        color=discord.Color.from_str("#FF69B4")
    )
    embed.set_image(url=gif)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="beijo_gif", description="💋 Beijar alguém com GIF")
async def beijo_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se beijar! 🥲")
        return
    
    gif = random.choice(gifs_beijo)
    
    embed = discord.Embed(
        title="💋 BEIJO!",
        description=f"{interaction.user.mention} beijou {membro.mention}!",
        color=discord.Color.red()
    )
    embed.set_image(url=gif)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="carinho_gif", description="🥰 Fazer carinho com GIF")
async def carinho_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode fazer carinho em si mesmo! 🥲")
        return
    
    gif = random.choice(gifs_carinho)
    
    embed = discord.Embed(
        title="🥰 CARINHO!",
        description=f"{interaction.user.mention} fez carinho em {membro.mention}!",
        color=discord.Color.purple()
    )
    embed.set_image(url=gif)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="cafune_gif", description="😴 Fazer cafuné com GIF")
async def cafune_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode fazer cafuné em si mesmo! 🥲")
        return
    
    gif = random.choice(gifs_carinho)
    
    embed = discord.Embed(
        title="😴 CAFUNÉ!",
        description=f"{interaction.user.mention} fez cafuné em {membro.mention}!",
        color=discord.Color.teal()
    )
    embed.set_image(url=gif)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tapa", description="👋 Dar um tapa em alguém com GIF")
async def tapa(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se bater! 🥲")
        return
    
    gif = random.choice(gifs_tapa)
    
    embed = discord.Embed(
        title="👋 TAPA!",
        description=f"{interaction.user.mention} deu um tapa em {membro.mention}!",
        color=discord.Color.orange()
    )
    embed.set_image(url=gif)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="festa", description="🎉 Fazer uma festa com GIF")
async def festa(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    gif = random.choice(gifs_festa)
    
    if membro:
        embed = discord.Embed(
            title="🎉 FESTA!",
            description=f"{interaction.user.mention} fez uma festa com {membro.mention}!",
            color=discord.Color.gold()
        )
    else:
        embed = discord.Embed(
            title="🎉 FESTA!",
            description=f"{interaction.user.mention} fez uma festa!",
            color=discord.Color.gold()
        )
    
    embed.set_image(url=gif)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="moeda", description="🪙 Jogar uma moeda")
async def moeda(interaction: discord.Interaction):
    resultado = random.choice(["CARA", "COROA"])
    await interaction.response.send_message(f"🪙 A moeda caiu: **{resultado}**!")

@bot.tree.command(name="dado_rpg", description="🎲 Rolar dados de RPG")
@app_commands.describe(
    quantidade="Quantidade de dados (ex: 2)",
    faces="Número de faces (ex: 20)"
)
async def dado_rpg(interaction: discord.Interaction, quantidade: int = 1, faces: int = 20):
    if quantidade < 1 or quantidade > 10:
        await interaction.response.send_message("❌ Quantidade deve ser entre 1 e 10!")
        return
    
    if faces not in [4, 6, 8, 10, 12, 20, 100]:
        await interaction.response.send_message("❌ Faces válidas: 4, 6, 8, 10, 12, 20, 100")
        return
    
    resultados = [random.randint(1, faces) for _ in range(quantidade)]
    total = sum(resultados)
    
    embed = discord.Embed(
        title="🎲 Dados de RPG",
        description=f"**{quantidade}d{faces}**",
        color=discord.Color.purple()
    )
    
    resultados_str = " + ".join(str(r) for r in resultados)
    embed.add_field(name="Resultados", value=resultados_str, inline=False)
    embed.add_field(name="Total", value=f"**{total}**", inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="sortear", description="🎁 Sortear um membro do servidor")
@app_commands.describe(cargo="Cargo específico para sortear (opcional)")
async def sortear(interaction: discord.Interaction, cargo: Optional[discord.Role] = None):
    if cargo:
        membros = [m for m in cargo.members if not m.bot]
        if not membros:
            await interaction.response.send_message(f"❌ Não há membros no cargo {cargo.mention}!")
            return
        sorteado = random.choice(membros)
        await interaction.response.send_message(f"🎁 O sorteado do cargo {cargo.mention} é: {sorteado.mention}! 🎉")
    else:
        membros = [m for m in interaction.guild.members if not m.bot]
        if not membros:
            await interaction.response.send_message("❌ Não há membros no servidor!")
            return
        sorteado = random.choice(membros)
        await interaction.response.send_message(f"🎁 O sorteado do servidor é: {sorteado.mention}! 🎉")

@bot.tree.command(name="enquete", description="📊 Criar uma enquete rápida")
@app_commands.describe(
    pergunta="A pergunta da enquete",
    opcao1="Primeira opção",
    opcao2="Segunda opção",
    opcao3="Terceira opção (opcional)",
    opcao4="Quarta opção (opcional)"
)
async def enquete(
    interaction: discord.Interaction,
    pergunta: str,
    opcao1: str,
    opcao2: str,
    opcao3: str = None,
    opcao4: str = None
):
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣"]
    opcoes = [opcao1, opcao2]
    
    if opcao3:
        opcoes.append(opcao3)
    if opcao4:
        opcoes.append(opcao4)
    
    descricao = ""
    for i, opcao in enumerate(opcoes):
        descricao += f"{emojis[i]} {opcao}\n"
    
    embed = discord.Embed(
        title=f"📊 {pergunta}",
        description=descricao,
        color=discord.Color.blue()
    )
    embed.set_footer(text=f"Enquete criada por {interaction.user.name}")
    embed.timestamp = datetime.now()
    
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    
    for i in range(len(opcoes)):
        await message.add_reaction(emojis[i])

# ==================== COMANDO DE AJUDA ATUALIZADO ====================

@bot.tree.command(name="ajuda", description="📚 Todos os comandos")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Comandos do Bot Fort",
        description="**Sistema Completo - 80+ COMANDOS!**",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🌿 **fort**",
        value="`/fort` - Registrar consumo\n"
              "`/fort_estoque` - Ver estoque\n"
              "`/fort_ranking` - Ranking\n"
              "`/fort_loja` - Loja de itens\n"
              "`/fort_comprar` - Comprar item\n"
              "`/fort_passar` - Passar pra alguém\n"
              "`/fort_reset` - Resetar estoque\n",
        inline=False
    )
    
    embed.add_field(
        name="📢 **CHAMADAS**",
        value="`/chamada` - Chamada normal\n"
              "`/chamada_tempo` - Chamada com tempo\n"
              "`/chamada_info` - Ver informações\n"
              "`/chamada_lista` - Lista completa\n"
              "`/chamada_cancelar` - Cancelar\n",
        inline=True
    )
    
    embed.add_field(
        name="💖 **SHIP**",
        value="`/ship` - Calcular amor\n"
              "`/shippar` - Criar ship\n"
              "`/likeship` - Dar like\n"
              "`/shipinfo` - Info do ship\n"
              "`/meusships` - Seus ships\n"
              "`/topship` - Ranking\n"
              "`/shiplist` - Listar ships\n",
        inline=True
    )
    
    embed.add_field(
        name="💒 **CASAMENTO**",
        value="`/pedir` - Pedir\n"
              "`/aceitar` - Aceitar\n"
              "`/recusar` - Recusar\n"
              "`/divorciar` - Divorciar\n",
        inline=True
    )
    
    embed.add_field(
        name="💰 **ECONOMIA**",
        value="`/daily` - Daily\n"
              "`/saldo` - Ver saldo\n"
              "`/transferir` - Transferir\n"
              "`/slot` - Caça-níqueis\n"
              "`/cara_coroa` - Cara ou coroa\n",
        inline=True
    )
    
    embed.add_field(
        name="🎭 **INTERAÇÕES**",
        value="`/abraco_gif` - Abraçar\n"
              "`/beijo_gif` - Beijar\n"
              "`/carinho_gif` - Carinho\n"
              "`/cafune_gif` - Cafuné\n"
              "`/tapa` - Dar tapa\n"
              "`/festa` - Fazer festa\n",
        inline=True
    )
    
    embed.add_field(
        name="🎮 **JOGOS**",
        value="`/moeda` - Cara ou coroa\n"
              "`/dado_rpg` - Dados de RPG\n"
              "`/sortear` - Sortear membro\n"
              "`/enquete` - Criar enquete\n",
        inline=True
    )
    
    embed.add_field(
        name="🤖 **BÁSICOS**",
        value="`/ping` - Latência\n"
              "`/userinfo` - Info usuário\n"
              "`/serverinfo` - Info servidor\n"
              "`/avatar` - Ver avatar\n"
              "`/calcular` - Calculadora\n",
        inline=True
    )
    
    embed.set_footer(text="Total: 80+ comandos! Use / antes de cada comando")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

# ==================== INICIAR BOT ====================

async def main():
    print("🔵 INICIANDO FUNÇÃO MAIN")
    
    token = DISCORD_TOKEN
    if token == 'SEU_TOKEN_AQUI':
        print("⚠️ Token não configurado no arquivo! Tentando variável de ambiente...")
        token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        print("❌ ERRO CRÍTICO: Token não encontrado!")
        return
    
    print(f"🔵 Token encontrado! Conectando...")
    
    try:
        async with bot:
            await bot.start(token)
    except Exception as e:
        print(f"❌ Erro: {e}")

def run_bot():
    print("🟢 INICIANDO BOT FORT TITHIPONG")
    try:
        keep_alive()
        time.sleep(2)
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Desligando")
    except Exception as e:
        print(f"❌ Erro fatal: {e}")

if __name__ == "__main__":
    print("="*60)
    print("🚀 BOT FORT TITHIPONG")
    print("="*60)
    print("\n📢 SISTEMAS CARREGADOS:")
    print("🌿 SISTEMA DE fort (ATIVO)")
    print("📢 Sistema de Chamadas (com tempo)")
    print("💖 Sistema de Ship (likes, ranking)")
    print("💒 Sistema de Casamento")
    print("💰 Sistema de Economia")
    print("🎭 Comandos com GIF")
    print("🎮 Jogos e Diversão")
    print("📊 80+ COMANDOS NO TOTAL!")
    print("="*60)
    
    run_bot()
