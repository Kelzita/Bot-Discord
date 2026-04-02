import sys
import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import random
import json
import aiohttp
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
import math
import sqlite3
import os
import time
import logging
import traceback

# ===== CONFIGURAÇÃO DO TOKEN E FUSO HORÁRIO =====
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')

# Fuso horário de Brasília (UTC-3)
BR_TZ = timezone(timedelta(hours=-3))

# ===== IMPORTS DO SERVIDOR WEB =====
from flask import Flask, jsonify
import threading

# Configurar encoding e logging
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO)

# ===== SERVIDOR WEB =====
app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({
        "status": "online",
        "bot": "Fort Bot",
        "sistemas": 90
    })

@app.route('/health')
@app.route('/healthcheck')
def health():
    return "OK", 200

@app.route('/ping')
def ping():
    return "pong", 200

def run_webserver():
    port = int(os.environ.get('PORT', 8080))
    print(f"📡 Iniciando servidor web na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)

def keep_alive():
    server = threading.Thread(target=run_webserver, daemon=True)
    server.start()
    print(f"✅ Servidor web configurado")

# ==================== SISTEMA DE ENQUETE DINÂMICO ====================

class EnqueteButton(Button):
    def __init__(self, enquete_id: str, opcao_index: int, opcao_texto: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=opcao_texto[:30],
            emoji=self.get_emoji(opcao_index),
            custom_id=f"enquete_{enquete_id}_{opcao_index}"
        )
        self.enquete_id = enquete_id
        self.opcao_index = opcao_index
        self.opcao_texto = opcao_texto
    
    def get_emoji(self, index):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        if index < len(emojis):
            return emojis[index]
        return "✅"
    
    async def callback(self, interaction: discord.Interaction):
        if self.enquete_id not in bot.enquetes:
            await interaction.response.send_message("❌ Esta enquete não existe mais!", ephemeral=True)
            return
        
        enquete = bot.enquetes[self.enquete_id]
        user_id = str(interaction.user.id)
        
        if user_id in enquete["votos_usuario"]:
            voto_antigo = enquete["votos_usuario"][user_id]
            enquete["votos"][voto_antigo] -= 1
            enquete["votos_usuario"][user_id] = self.opcao_index
            enquete["votos"][self.opcao_index] += 1
            mensagem = f"✅ Seu voto foi alterado para **{self.opcao_texto}**!"
        else:
            enquete["votos"][self.opcao_index] += 1
            enquete["votos_usuario"][user_id] = self.opcao_index
            mensagem = f"✅ Seu voto foi registrado em **{self.opcao_texto}**!"
        
        await self.atualizar_embed(interaction, enquete)
        await interaction.response.send_message(mensagem, ephemeral=True)
    
    async def atualizar_embed(self, interaction: discord.Interaction, enquete):
        total_votos = sum(enquete["votos"])
        descricao = f"**{enquete['pergunta']}**\n\n"
        
        for i, opcao in enumerate(enquete["opcoes"]):
            votos = enquete["votos"][i]
            porcentagem = (votos / total_votos * 100) if total_votos > 0 else 0
            barra = "█" * int(porcentagem // 5) + "░" * (20 - int(porcentagem // 5))
            descricao += f"**{self.get_emoji(i)} {opcao}**\n"
            descricao += f"`{barra}` **{votos} votos** ({porcentagem:.1f}%)\n\n"
        
        descricao += f"\n📊 **Total de votos:** {total_votos}"
        descricao += f"\n👥 **Participantes:** {len(enquete['votos_usuario'])}"
        
        embed = discord.Embed(
            title="📊 **ENQUETE**",
            description=descricao,
            color=discord.Color.blue()
        )
        
        embed.set_footer(text=f"Criada por {enquete['criador_nome']} | ID: {self.enquete_id}")
        embed.timestamp = datetime.now(BR_TZ)
        
        try:
            canal = bot.get_channel(int(enquete["channel_id"]))
            if canal:
                msg = await canal.fetch_message(int(enquete["message_id"]))
                if msg:
                    await msg.edit(embed=embed)
        except Exception as e:
            print(f"Erro ao atualizar embed: {e}")

class EnqueteView(View):
    def __init__(self, enquete_id: str, opcoes: list):
        super().__init__(timeout=None)
        self.enquete_id = enquete_id
        for i, opcao in enumerate(opcoes):
            self.add_item(EnqueteButton(enquete_id, i, opcao))
        self.add_item(EncerrarEnqueteButton(enquete_id))

class EncerrarEnqueteButton(Button):
    def __init__(self, enquete_id: str):
        super().__init__(
            style=discord.ButtonStyle.danger,
            label="🔒 Encerrar Enquete",
            custom_id=f"encerrar_enquete_{enquete_id}"
        )
        self.enquete_id = enquete_id
    
    async def callback(self, interaction: discord.Interaction):
        if self.enquete_id not in bot.enquetes:
            await interaction.response.send_message("❌ Enquete não encontrada!", ephemeral=True)
            return
        
        enquete = bot.enquetes[self.enquete_id]
        
        if str(interaction.user.id) != enquete["criador_id"] and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Apenas o criador ou administradores podem encerrar a enquete!", ephemeral=True)
            return
        
        total_votos = sum(enquete["votos"])
        resultados = []
        
        for i, opcao in enumerate(enquete["opcoes"]):
            votos = enquete["votos"][i]
            porcentagem = (votos / total_votos * 100) if total_votos > 0 else 0
            resultados.append(f"**{opcao}** - {votos} votos ({porcentagem:.1f}%)")
        
        embed_final = discord.Embed(
            title="📊 **ENQUETE ENCERRADA**",
            description=f"**{enquete['pergunta']}**\n\n" + "\n".join(resultados),
            color=discord.Color.dark_gray()
        )
        
        embed_final.add_field(name="📊 Total de votos", value=str(total_votos), inline=True)
        embed_final.add_field(name="👥 Participantes", value=str(len(enquete["votos_usuario"])), inline=True)
        embed_final.set_footer(text=f"Encerrada por {interaction.user.name}")
        embed_final.timestamp = datetime.now(BR_TZ)
        
        try:
            canal = bot.get_channel(int(enquete["channel_id"]))
            if canal:
                msg = await canal.fetch_message(int(enquete["message_id"]))
                if msg:
                    await msg.edit(embed=embed_final, view=None)
        except Exception as e:
            print(f"Erro ao encerrar: {e}")
        
        del bot.enquetes[self.enquete_id]
        bot.save_enquetes()
        
        await interaction.response.send_message("✅ Enquete encerrada com sucesso!", ephemeral=True)

class CriarEnqueteModal(Modal):
    def __init__(self):
        super().__init__(title="📊 Criar Nova Enquete")
        
        self.pergunta = TextInput(
            label="📝 Pergunta da Enquete",
            placeholder="Ex: Qual é a melhor cor?",
            required=True,
            max_length=200
        )
        
        self.opcoes = TextInput(
            label="🎯 Opções (separadas por |)",
            placeholder="Ex: Azul | Vermelho | Verde | Amarelo",
            required=True,
            max_length=500
        )
        
        self.duracao = TextInput(
            label="⏰ Duração em horas (0 = ilimitada)",
            placeholder="Ex: 24 (deixe 0 para enquete permanente)",
            required=False,
            default="0",
            max_length=3
        )
        
        self.add_item(self.pergunta)
        self.add_item(self.opcoes)
        self.add_item(self.duracao)
    
    async def on_submit(self, interaction: discord.Interaction):
        pergunta = self.pergunta.value
        opcoes_raw = self.opcoes.value
        duracao = int(self.duracao.value) if self.duracao.value.isdigit() else 0
        
        opcoes = [op.strip() for op in opcoes_raw.split("|") if op.strip()]
        
        if len(opcoes) < 2:
            await interaction.response.send_message("❌ Você precisa de pelo menos 2 opções!", ephemeral=True)
            return
        
        if len(opcoes) > 20:
            await interaction.response.send_message("❌ Máximo de 20 opções!", ephemeral=True)
            return
        
        enquete_id = f"{interaction.channel.id}-{int(datetime.now(BR_TZ).timestamp())}"
        
        expira_em = None
        if duracao > 0:
            expira_em = datetime.now(BR_TZ) + timedelta(hours=duracao)
        
        descricao = f"**{pergunta}**\n\n"
        for i, opcao in enumerate(opcoes):
            emoji = self.get_emoji(i)
            descricao += f"{emoji} **{opcao}**\n"
        
        descricao += f"\n📊 **Total de votos:** 0"
        descricao += f"\n👥 **Participantes:** 0"
        
        if expira_em:
            descricao += f"\n⏰ **Expira:** {expira_em.strftime('%d/%m/%Y %H:%M')} (Brasília)"
        else:
            descricao += f"\n🌙 **Expira:** Nunca (enquete permanente)"
        
        embed = discord.Embed(
            title="📊 **ENQUETE**",
            description=descricao,
            color=discord.Color.blue()
        )
        
        embed.set_footer(text=f"Criada por {interaction.user.name} | ID: {enquete_id}")
        embed.timestamp = datetime.now(BR_TZ)
        
        view = EnqueteView(enquete_id, opcoes)
        
        await interaction.response.send_message(embed=embed, view=view)
        message = await interaction.original_response()
        
        bot.enquetes[enquete_id] = {
            "pergunta": pergunta,
            "opcoes": opcoes,
            "votos": [0] * len(opcoes),
            "votos_usuario": {},
            "criador_id": str(interaction.user.id),
            "criador_nome": interaction.user.name,
            "channel_id": str(interaction.channel.id),
            "message_id": str(message.id),
            "criado_em": datetime.now(BR_TZ).isoformat(),
            "expira_em": expira_em.isoformat() if expira_em else None
        }
        
        bot.save_enquetes()
        
        if expira_em:
            task = asyncio.create_task(bot.encerrar_enquete_automatico(enquete_id, expira_em))
            bot.enquete_tasks[enquete_id] = task
    
    def get_emoji(self, index):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        if index < len(emojis):
            return emojis[index]
        return "✅"

class AdicionarOpcaoModal(Modal):
    def __init__(self, enquete_id: str):
        super().__init__(title="➕ Adicionar Nova Opção")
        self.enquete_id = enquete_id
        
        self.nova_opcao = TextInput(
            label="📝 Nova Opção",
            placeholder="Digite a nova opção",
            required=True,
            max_length=100
        )
        
        self.add_item(self.nova_opcao)
    
    async def on_submit(self, interaction: discord.Interaction):
        if self.enquete_id not in bot.enquetes:
            await interaction.response.send_message("❌ Enquete não encontrada!", ephemeral=True)
            return
        
        enquete = bot.enquetes[self.enquete_id]
        
        if str(interaction.user.id) != enquete["criador_id"] and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Apenas o criador pode adicionar opções!", ephemeral=True)
            return
        
        if len(enquete["opcoes"]) >= 20:
            await interaction.response.send_message("❌ Máximo de 20 opções atingido!", ephemeral=True)
            return
        
        nova_opcao = self.nova_opcao.value.strip()
        enquete["opcoes"].append(nova_opcao)
        enquete["votos"].append(0)
        
        bot.save_enquetes()
        
        await self.recriar_view(interaction, enquete)
        await interaction.response.send_message(f"✅ Opção **{nova_opcao}** adicionada!", ephemeral=True)
    
    async def recriar_view(self, interaction: discord.Interaction, enquete):
        try:
            canal = bot.get_channel(int(enquete["channel_id"]))
            if canal:
                msg = await canal.fetch_message(int(enquete["message_id"]))
                if msg:
                    nova_view = EnqueteView(self.enquete_id, enquete["opcoes"])
                    total_votos = sum(enquete["votos"])
                    descricao = f"**{enquete['pergunta']}**\n\n"
                    
                    for i, opcao in enumerate(enquete["opcoes"]):
                        votos = enquete["votos"][i]
                        porcentagem = (votos / total_votos * 100) if total_votos > 0 else 0
                        barra = "█" * int(porcentagem // 5) + "░" * (20 - int(porcentagem // 5))
                        emoji = self.get_emoji(i)
                        descricao += f"{emoji} **{opcao}**\n"
                        descricao += f"`{barra}` **{votos} votos** ({porcentagem:.1f}%)\n\n"
                    
                    descricao += f"\n📊 **Total de votos:** {total_votos}"
                    descricao += f"\n👥 **Participantes:** {len(enquete['votos_usuario'])}"
                    
                    if enquete.get("expira_em"):
                        expira = datetime.fromisoformat(enquete["expira_em"]).replace(tzinfo=BR_TZ)
                        if expira > datetime.now(BR_TZ):
                            descricao += f"\n⏰ **Expira:** {expira.strftime('%d/%m/%Y %H:%M')} (Brasília)"
                    
                    embed = discord.Embed(
                        title="📊 **ENQUETE**",
                        description=descricao,
                        color=discord.Color.blue()
                    )
                    
                    embed.set_footer(text=f"Criada por {enquete['criador_nome']} | ID: {self.enquete_id}")
                    embed.timestamp = datetime.now(BR_TZ)
                    
                    await msg.edit(embed=embed, view=nova_view)
        except Exception as e:
            print(f"Erro ao recriar view: {e}")
    
    def get_emoji(self, index):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        if index < len(emojis):
            return emojis[index]
        return "✅"

class GerenciarEnqueteView(View):
    def __init__(self, enquete_id: str):
        super().__init__(timeout=None)
        self.enquete_id = enquete_id
        self.add_item(AdicionarOpcaoButton(enquete_id))
        self.add_item(ResultadosButton(enquete_id))
        self.add_item(EncerrarEnqueteButton(enquete_id))

class AdicionarOpcaoButton(Button):
    def __init__(self, enquete_id: str):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="➕ Adicionar Opção",
            emoji="➕",
            custom_id=f"add_opcao_{enquete_id}"
        )
        self.enquete_id = enquete_id
    
    async def callback(self, interaction: discord.Interaction):
        modal = AdicionarOpcaoModal(self.enquete_id)
        await interaction.response.send_modal(modal)

class ResultadosButton(Button):
    def __init__(self, enquete_id: str):
        super().__init__(
            style=discord.ButtonStyle.secondary,
            label="📊 Ver Resultados",
            emoji="📊",
            custom_id=f"resultados_{enquete_id}"
        )
        self.enquete_id = enquete_id
    
    async def callback(self, interaction: discord.Interaction):
        if self.enquete_id not in bot.enquetes:
            await interaction.response.send_message("❌ Enquete não encontrada!", ephemeral=True)
            return
        
        enquete = bot.enquetes[self.enquete_id]
        total_votos = sum(enquete["votos"])
        
        resultados = []
        for i, opcao in enumerate(enquete["opcoes"]):
            votos = enquete["votos"][i]
            porcentagem = (votos / total_votos * 100) if total_votos > 0 else 0
            resultados.append(f"**{opcao}** - {votos} votos ({porcentagem:.1f}%)")
        
        embed = discord.Embed(
            title="📊 Resultados da Enquete",
            description=f"**{enquete['pergunta']}**\n\n" + "\n".join(resultados),
            color=discord.Color.green()
        )
        
        embed.add_field(name="Total de Votos", value=str(total_votos), inline=True)
        embed.add_field(name="Participantes", value=str(len(enquete["votos_usuario"])), inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== CLASSE PRINCIPAL DO BOT ====================

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
        
        # Sistema de enquetes
        self.enquetes = {}
        self.enquete_tasks = {}
        
        # Sistema de Páscoa
        self.pascoa_pontos = {}       # pontos acumulados de Páscoa por user
        self.pascoa_ovos = {}         # ovos escondidos por canal
        self.pascoa_daily = {}        # cooldown do daily de páscoa
        self.pascoa_coelho = {}       # cooldown do caça ao coelho
        self.pascoa_memoria = {}      # jogo de memória em andamento
        self.pascoa_quiz_cd = {}      # cooldown do quiz de páscoa
        self.pascoa_corrida = {}      # corridas de coelho em andamento

        # Sistema de RP
        self.rp_fichas = {}           # fichas de personagem
        self.rp_acoes_cd = {}         # cooldown de ações de RP
        
        # Tasks ativas
        self.active_tasks = {}
        
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
        c.execute('''CREATE TABLE IF NOT EXISTS dados_json
                     (tipo TEXT PRIMARY KEY, dados TEXT)''')
        
        conn.commit()
        conn.close()
        print("✅ Banco de dados SQLite inicializado!")
    
    def load_data(self):
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        c.execute('SELECT user_id, saldo FROM economia')
        self.user_balances = {user_id: saldo for user_id, saldo in c.fetchall()}
        
        c.execute('SELECT user_id, data FROM daily_cooldowns')
        self.daily_cooldowns = {user_id: data for user_id, data in c.fetchall()}
        
        c.execute('SELECT user_id, data FROM divorce_cooldowns')
        self.divorce_cooldowns = {}
        for user_id, data in c.fetchall():
            self.divorce_cooldowns[user_id] = datetime.fromisoformat(data).replace(tzinfo=BR_TZ) if data else None
        
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
            elif tipo == 'enquetes':
                self.enquetes = dados
            elif tipo == 'pascoa_pontos':
                self.pascoa_pontos = dados
            elif tipo == 'rp_fichas':
                self.rp_fichas = dados
        
        conn.close()
        self.import_from_json_if_empty()
    
    def import_from_json_if_empty(self):
        if not self.user_balances:
            try:
                arquivos = ['economy.json', 'inventory.json', 'ships.json', 'marriages.json', 
                           'anniversary.json', 'ship_history.json', 'calls.json', 'enquetes.json']
                for arquivo in arquivos:
                    if os.path.exists(arquivo):
                        with open(arquivo, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                            if arquivo == 'economy.json':
                                self.user_balances = data
                            elif arquivo == 'inventory.json':
                                self.user_inventory = data
                            elif arquivo == 'ships.json':
                                self.ship_data = data
                            elif arquivo == 'marriages.json':
                                self.marriage_data = data
                            elif arquivo == 'anniversary.json':
                                self.anniversary_data = data
                            elif arquivo == 'ship_history.json':
                                self.ship_history = data
                            elif arquivo == 'calls.json':
                                self.call_data = data.get('calls', {})
                                self.call_participants = data.get('participants', {})
                            elif arquivo == 'enquetes.json':
                                self.enquetes = data
                print("✅ Dados importados dos JSONs!")
                self.save_data()
            except Exception as e:
                print(f"⚠️ Erro ao importar JSONs: {e}")
    
    def save_data(self):
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        for user_id, saldo in self.user_balances.items():
            c.execute('INSERT OR REPLACE INTO economia VALUES (?, ?)', (user_id, saldo))
        
        for user_id, data in self.daily_cooldowns.items():
            c.execute('INSERT OR REPLACE INTO daily_cooldowns VALUES (?, ?)', (user_id, data))
        
        for user_id, data in self.divorce_cooldowns.items():
            data_str = data.isoformat() if data else None
            c.execute('INSERT OR REPLACE INTO divorce_cooldowns VALUES (?, ?)', (user_id, data_str))
        
        dados_para_salvar = [
            ('inventory', self.user_inventory),
            ('ships', self.ship_data),
            ('marriages', self.marriage_data),
            ('anniversary', self.anniversary_data),
            ('ship_history', self.ship_history),
            ('calls', self.call_data),
            ('call_participants', self.call_participants),
            ('enquetes', self.enquetes),
            ('pascoa_pontos', self.pascoa_pontos),
            ('rp_fichas', self.rp_fichas),
        ]
        
        for tipo, dados in dados_para_salvar:
            c.execute('INSERT OR REPLACE INTO dados_json VALUES (?, ?)', 
                     (tipo, json.dumps(dados, ensure_ascii=False)))
        
        conn.commit()
        conn.close()
    
    def save_enquetes(self):
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO dados_json VALUES (?, ?)', 
                 ('enquetes', json.dumps(self.enquetes, ensure_ascii=False)))
        conn.commit()
        conn.close()

    def save_pascoa(self):
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO dados_json VALUES (?, ?)',
                 ('pascoa_pontos', json.dumps(self.pascoa_pontos, ensure_ascii=False)))
        conn.commit()
        conn.close()

    def save_rp(self):
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO dados_json VALUES (?, ?)',
                 ('rp_fichas', json.dumps(self.rp_fichas, ensure_ascii=False)))
        conn.commit()
        conn.close()

    def add_pascoa_pontos(self, user_id: str, pontos: int):
        """Adiciona pontos de Páscoa ao usuário"""
        uid = str(user_id)
        if uid not in self.pascoa_pontos:
            self.pascoa_pontos[uid] = 0
        self.pascoa_pontos[uid] += pontos
        self.save_pascoa()

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Comandos sincronizados!")
        await self.restaurar_chamadas_ativas()
        await self.restaurar_enquetes_ativas()

    async def restaurar_enquetes_ativas(self):
        agora = datetime.now(BR_TZ)
        enquetes_remover = []
        
        for enquete_id, enquete_data in self.enquetes.items():
            try:
                expira_em = enquete_data.get("expira_em")
                if expira_em:
                    expira = datetime.fromisoformat(expira_em).replace(tzinfo=BR_TZ)
                    if expira <= agora:
                        enquetes_remover.append(enquete_id)
                    else:
                        task = asyncio.create_task(self.encerrar_enquete_automatico(enquete_id, expira))
                        self.enquete_tasks[enquete_id] = task
            except Exception as e:
                print(f"❌ Erro ao restaurar enquete {enquete_id}: {e}")
                enquetes_remover.append(enquete_id)
        
        for enquete_id in enquetes_remover:
            if enquete_id in self.enquetes:
                del self.enquetes[enquete_id]
        
        if enquetes_remover:
            self.save_enquetes()

    async def encerrar_enquete_automatico(self, enquete_id: str, expira_em: datetime):
        try:
            agora = datetime.now(BR_TZ)
            tempo_restante = (expira_em - agora).total_seconds()
            if tempo_restante > 0:
                await asyncio.sleep(tempo_restante)
            
            if enquete_id not in self.enquetes:
                return
            
            enquete = self.enquetes[enquete_id]
            total_votos = sum(enquete["votos"])
            resultados = []
            
            for i, opcao in enumerate(enquete["opcoes"]):
                votos = enquete["votos"][i]
                porcentagem = (votos / total_votos * 100) if total_votos > 0 else 0
                resultados.append(f"**{opcao}** - {votos} votos ({porcentagem:.1f}%)")
            
            embed_final = discord.Embed(
                title="📊 **ENQUETE ENCERRADA**",
                description=f"**{enquete['pergunta']}**\n\n" + "\n".join(resultados),
                color=discord.Color.dark_gray()
            )
            
            embed_final.add_field(name="📊 Total de votos", value=str(total_votos), inline=True)
            embed_final.add_field(name="👥 Participantes", value=str(len(enquete["votos_usuario"])), inline=True)
            embed_final.set_footer(text=f"Encerrada automaticamente por tempo limite")
            embed_final.timestamp = datetime.now(BR_TZ)
            
            try:
                canal = self.get_channel(int(enquete["channel_id"]))
                if canal:
                    msg = await canal.fetch_message(int(enquete["message_id"]))
                    if msg:
                        await msg.edit(embed=embed_final, view=None)
            except Exception as e:
                print(f"Erro ao encerrar enquete: {e}")
            
            del self.enquetes[enquete_id]
            if enquete_id in self.enquete_tasks:
                del self.enquete_tasks[enquete_id]
            
            self.save_enquetes()
            
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"❌ Erro ao encerrar enquete: {e}")

    async def restaurar_chamadas_ativas(self):
        agora = datetime.now(BR_TZ)
        calls_remover = []
        
        for call_id, call_data in self.call_data.items():
            try:
                expira_em = datetime.fromisoformat(call_data['expira_em']).replace(tzinfo=BR_TZ)
                if expira_em <= agora:
                    calls_remover.append(call_id)
                else:
                    task = asyncio.create_task(encerrar_chamada_apos_tempo(call_id, expira_em))
                    self.active_tasks[call_id] = task
            except Exception as e:
                print(f"❌ Erro ao restaurar chamada {call_id}: {e}")
                calls_remover.append(call_id)
        
        for call_id in calls_remover:
            if call_id in self.call_data:
                del self.call_data[call_id]
            if call_id in self.call_participants:
                del self.call_participants[call_id]
        
        if calls_remover:
            self.save_data()

    async def on_ready(self):
        print(f"✅ Bot {self.user} ligado com sucesso!")
        print(f"📊 Servidores: {len(self.guilds)}")
        print(f"👥 Usuários: {len(self.users)}")
        print(f"🐣 Sistema de Páscoa: ATIVO")
        print(f"🎭 Sistema de RP: ATIVO")
        print(f"💖 Sistema de Ship: ATIVO")
        print(f"💒 Sistema de Casamento: ATIVO")
        print(f"💰 Sistema de Economia: ATIVO")
        print(f"📊 Sistema de Enquetes: ATIVO")
        print(f"⏰ Horário atual: {datetime.now(BR_TZ).strftime('%d/%m/%Y %H:%M:%S')}")
        await self.change_presence(activity=discord.Game(name="🐣 Páscoa chegou! | 90+ comandos!"))

bot = Fort()

# ==================== SISTEMA DE CHAMADAS ====================

def calcular_tempo_expiracao(horas_limite: Optional[int] = None):
    agora = datetime.now(BR_TZ)
    
    if horas_limite is not None and horas_limite > 0:
        expira_em = agora + timedelta(hours=horas_limite)
        return expira_em
    else:
        meia_noite = datetime(agora.year, agora.month, agora.day, 23, 59, 59, tzinfo=BR_TZ)
        return meia_noite

class CallButton(Button):
    def __init__(self, call_id: str, emoji: str, expira_em: datetime):
        super().__init__(
            style=discord.ButtonStyle.success,
            label="Confirmar Presença",
            emoji=emoji,
            custom_id=f"call_{call_id}"
        )
        self.call_id = call_id
        self.expira_em = expira_em
    
    async def callback(self, interaction: discord.Interaction):
        agora = datetime.now(BR_TZ)
        
        if agora > self.expira_em:
            await interaction.response.send_message("⏰ **Esta chamada EXPIROU!**", ephemeral=True)
            return
            
        try:
            user_id = str(interaction.user.id)
            call_id = self.call_id
            
            if call_id not in bot.call_data:
                await interaction.response.send_message("❌ Chamada não existe!", ephemeral=True)
                return
            
            call = bot.call_data[call_id]
            
            if call_id not in bot.call_participants:
                bot.call_participants[call_id] = []
            
            if user_id in bot.call_participants[call_id]:
                await interaction.response.send_message("❌ Você já confirmou!", ephemeral=True)
                return
            
            bot.call_participants[call_id].append(user_id)
            bot.save_data()
            
            try:
                channel = bot.get_channel(int(call['channel_id']))
                if channel:
                    message = await channel.fetch_message(int(call['message_id']))
                    if message:
                        participantes_text = ""
                        if bot.call_participants[call_id]:
                            participantes_list = []
                            for pid in bot.call_participants[call_id]:
                                member = interaction.guild.get_member(int(pid))
                                if member:
                                    participantes_list.append(member.mention)
                            
                            if participantes_list:
                                participantes_text = "\n".join(participantes_list[:10])
                                if len(participantes_list) > 10:
                                    participantes_text += f"\n... e mais {len(participantes_list) - 10}"
                        else:
                            participantes_text = "Ninguém confirmou ainda"
                        
                        data_atual = datetime.now(BR_TZ).strftime("%d.%m")
                        
                        if call.get('horas_duracao'):
                            timing_text = f"⏰ Expira em {call['horas_duracao']} hora(s) (às {self.expira_em.strftime('%H:%M')} Brasília)"
                        else:
                            timing_text = f"🌙 Expira HOJE às 23:59 (MEIA-NOITE Brasília)"
                        
                        descricao_completa = f"""﹒⬚﹒⇆﹒🍑 ᆞ

५ᅟ𐙚 ⎯ᅟ︶︶︶﹒୧﹐atividade ❞ {data_atual}
𓈒 ׂ 🪷੭ ᮫ : Boa tarde, meus amores. Sejam bem-vindos ao canal de chamada da House! Esse espaço foi criado para confirmarmos quem permanece ativo e comprometido com a nossa House 🤍

ㅤ𔘓 ㅤׄㅤ ㅤׅ ㅤׄ 말 🌿 𝅼ㅤׄㅤㅤ𔘓 丶丶
[𒃵] A cada ausência não justificada, será registrado um tracinho.

𑇡 📝 Ao acumular sete tracinhos, será banido automaticamente.
Caso tenha algum compromisso, justifique sua ausência em. Estarei registrando os presentes no horário correto, então não será considerada confirmação fora do período informado.

여기 ㅤ🔔✨ ; A chamada começará às {call['data_hora']}.
Para confirmar sua presença, reaja com o emoji indicado abaixo e sinta-se à vontade para continuar suas atividades após isso.
✦𓂃 Utilize o emoji {call['emoji']} para responder à chamada.

ⓘ Lembrando: Marcar presença e desaparecer completamente da House até a próxima chamada também resultará em registro de ausência. Compromisso é essencial para mantermos a organização e o bom funcionamento daqui.

५ᅟ𐙚 ⎯ᅟᅟ❝ 🍑﹒ᥫ᭡﹐୨`﹒ꔫ﹐︶︶︶﹒୧﹐🍑 ❞
ㅤ𔘓 ㅤׄㅤ ㅤׅ ㅤׄ 魂 🌷 𝅼ㅤׄㅤㅤ𔘓 ◖

**{timing_text}**
**✅ PRESENTES: {len(bot.call_participants[call_id])}**"""
                        
                        embed = discord.Embed(
                            title=f"🌿ᩚ📦 𝐇𝐎𝐔𝐒𝐄 ִ 𝐂̷̸𝐇𝐀𝐌𝐀𝐃𝐀 ꒥꒦ 📄",
                            description=descricao_completa,
                            color=discord.Color.from_str("#FF69B4")
                        )
                        
                        embed.add_field(
                            name="📋 LISTA DE PRESENTES",
                            value=participantes_text if participantes_text else "Ninguém confirmou ainda",
                            inline=False
                        )
                        
                        if interaction.guild.icon:
                            embed.set_thumbnail(url=interaction.guild.icon.url)
                        
                        embed.set_footer(text="Clique no botão abaixo para confirmar sua presença!")
                        embed.timestamp = datetime.now(BR_TZ)
                        
                        await message.edit(embed=embed)
            except Exception as e:
                print(f"Erro ao atualizar embed: {e}")
            
            try:
                embed_privado = discord.Embed(
                    title="✅ PRESENÇA CONFIRMADA!",
                    description=f"**{call['titulo']}**",
                    color=discord.Color.green()
                )
                embed_privado.add_field(name="📅 Data/Hora", value=call['data_hora'], inline=True)
                embed_privado.add_field(name="📍 Local", value=call['local'], inline=True)
                embed_privado.add_field(name="👤 Organizador", value=f"<@{call['criador_id']}>", inline=True)
                embed_privado.add_field(name="📊 Total", value=f"{len(bot.call_participants[call_id])} confirmados", inline=True)
                embed_privado.set_footer(text="Obrigado por confirmar! 🎉")
                await interaction.user.send(embed=embed_privado)
            except:
                pass
            
            await interaction.response.send_message(
                f"✅ Presença confirmada! Total: {len(bot.call_participants[call_id])}",
                ephemeral=True
            )
            
        except Exception as e:
            print(f"Erro: {e}")
            await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

class CallView(View):
    def __init__(self, call_id: str, emoji: str, expira_em: datetime):
        super().__init__(timeout=None)
        self.add_item(CallButton(call_id, emoji, expira_em))

async def encerrar_chamada_apos_tempo(call_id: str, expira_em: datetime):
    try:
        agora = datetime.now(BR_TZ)
        tempo_restante = (expira_em - agora).total_seconds()
        
        if tempo_restante > 0:
            await asyncio.sleep(tempo_restante)
        
        if call_id not in bot.call_data:
            return
        
        call = bot.call_data[call_id]
        participantes = bot.call_participants.get(call_id, [])
        
        channel = bot.get_channel(int(call['channel_id']))
        if channel:
            try:
                message = await channel.fetch_message(int(call['message_id']))
                if message:
                    if call.get('horas_duracao'):
                        motivo = f"APÓS {call['horas_duracao']} HORA(S)"
                    else:
                        motivo = "À MEIA-NOITE (23:59 Brasília)"
                    
                    participantes_text = ""
                    if participantes:
                        participantes_list = []
                        for pid in participantes[:20]:
                            member = channel.guild.get_member(int(pid))
                            if member:
                                participantes_list.append(f"• {member.mention}")
                        if participantes_list:
                            participantes_text = "\n".join(participantes_list)
                            if len(participantes) > 20:
                                participantes_text += f"\n... e mais {len(participantes) - 20}"
                    else:
                        participantes_text = "Ninguém compareceu 😢"
                    
                    embed_final = discord.Embed(
                        title=f"📦 𝐇𝐎𝐔𝐒𝐄 ִ 𝐂̷̸𝐇𝐀𝐌𝐀𝐃𝐀 [ENCERRADA]",
                        description=f"**CHAMADA ENCERRADA {motivo}**\n\nTotal de presentes: **{len(participantes)}**",
                        color=discord.Color.dark_gray()
                    )
                    embed_final.add_field(name="✅ LISTA FINAL", value=participantes_text[:1024], inline=False)
                    encerrado_em = datetime.now(BR_TZ)
                    embed_final.set_footer(text=f"Encerrada em {encerrado_em.strftime('%d/%m/%Y %H:%M')} (Brasília)")
                    embed_final.timestamp = encerrado_em
                    
                    await message.edit(embed=embed_final, view=None)
                    await channel.send(f"⏰ **Chamada encerrada!** Total de {len(participantes)} presente(s)! 📊")
            except Exception as e:
                print(f"❌ Erro ao editar mensagem: {e}")
        
        if call_id in bot.call_data:
            del bot.call_data[call_id]
        if call_id in bot.call_participants:
            del bot.call_participants[call_id]
        if call_id in bot.active_tasks:
            del bot.active_tasks[call_id]
        
        bot.save_data()
        
    except asyncio.CancelledError:
        pass
    except Exception as e:
        print(f"❌ Erro ao encerrar chamada: {e}")
        traceback.print_exc()

@bot.tree.command(name="chamada", description="📢 Criar uma chamada (@everyone)")
@app_commands.describe(
    titulo="Título do evento",
    data_hora="Data e hora (ex: 15:40 ou 25/12 20h)",
    local="Local do evento",
    horas_duracao="Horas para expirar (opcional - se NÃO colocar, vence MEIA-NOITE 23:59 Brasília)",
    descricao="Descrição adicional (opcional)",
    emoji="Emoji do botão (padrão: ✅)"
)
async def chamada(
    interaction: discord.Interaction,
    titulo: str,
    data_hora: str,
    local: str,
    horas_duracao: Optional[int] = None,
    descricao: str = "",
    emoji: str = "✅"
):
    if not interaction.user.guild_permissions.mention_everyone:
        await interaction.response.send_message("❌ Você precisa da permissão `Mencionar @everyone`!", ephemeral=True)
        return
    
    if not interaction.guild.me.guild_permissions.mention_everyone:
        await interaction.response.send_message("❌ O bot precisa da permissão `Mencionar @everyone`!", ephemeral=True)
        return
    
    expira_em = calcular_tempo_expiracao(horas_duracao)
    call_id = f"{interaction.channel.id}-{int(datetime.now(BR_TZ).timestamp())}"
    data_atual = datetime.now(BR_TZ).strftime("%d.%m")
    
    if horas_duracao:
        timing_text = f"⏰ Expira em {horas_duracao} hora(s) (às {expira_em.strftime('%H:%M')} Brasília)"
    else:
        timing_text = f"🌙 Expira HOJE às 23:59 (MEIA-NOITE Brasília)"
    
    descricao_completa = f"""﹒⬚﹒⇆﹒🍑 ᆞ

५ᅟ𐙚 ⎯ᅟ︶︶︶﹒୧﹐atividade ❞ {data_atual}
𓈒 ׂ 🪷੭ ᮫ : {descricao if descricao else "Boa tarde, meus amores. Sejam bem-vindos ao canal de chamada da House! Esse espaço foi criado para confirmarmos quem permanece ativo e comprometido com a nossa House 🤍"}

ㅤ𔘓 ㅤׄㅤ ㅤׅ ㅤׄ 말 🌿 𝅼ㅤׄㅤㅤ𔘓 丶丶
[𒃵] A cada ausência não justificada, será registrado um tracinho.

𑇡 📝 Ao acumular sete tracinhos, será banido automaticamente.

여기 ㅤ🔔✨ ; A chamada começará às {data_hora}.
✦𓂃 Utilize o emoji {emoji} para responder à chamada.

**{timing_text}**
**✅ PRESENTES: 0**"""
    
    embed = discord.Embed(
        title=f"🌿ᩚ📦 𝐇𝐎𝐔𝐒𝐄 ִ 𝐂̷̸𝐇𝐀𝐌𝐀𝐃𝐀 ꒥꒦ 📄",
        description=descricao_completa,
        color=discord.Color.from_str("#FF69B4")
    )
    
    embed.add_field(name="📋 LISTA DE PRESENTES", value="Ninguém confirmou ainda", inline=False)
    
    if interaction.guild.icon:
        embed.set_thumbnail(url=interaction.guild.icon.url)
    
    embed.set_footer(text="Clique no botão abaixo para confirmar sua presença!")
    embed.timestamp = datetime.now(BR_TZ)
    
    view = CallView(call_id, emoji, expira_em)
    
    await interaction.response.send_message(
        content="@everyone",
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
        'criado_em': datetime.now(BR_TZ).isoformat(),
        'horas_duracao': horas_duracao
    }
    
    bot.call_participants[call_id] = []
    bot.save_data()
    
    if horas_duracao:
        confirm_msg = f"⏰ Expira em {horas_duracao} hora(s) (às {expira_em.strftime('%H:%M')} Brasília)"
    else:
        confirm_msg = f"🌙 Expira HOJE às 23:59 (MEIA-NOITE Brasília)"
    
    embed_confirm = discord.Embed(title="✅ Chamada Criada!", description=f"**{titulo}**", color=discord.Color.green())
    embed_confirm.add_field(name="⏰ Timing", value=confirm_msg, inline=False)
    embed_confirm.add_field(name="📅 Data/Hora", value=data_hora, inline=True)
    embed_confirm.add_field(name="⏱️ Expira em", value=expira_em.strftime("%d/%m/%Y %H:%M") + " (Brasília)", inline=True)
    
    await interaction.followup.send(embed=embed_confirm, ephemeral=True)
    
    task = asyncio.create_task(encerrar_chamada_apos_tempo(call_id, expira_em))
    bot.active_tasks[call_id] = task

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
            expira_em = datetime.fromisoformat(data['expira_em']).replace(tzinfo=BR_TZ)
            status = "🟢 Ativa" if expira_em > datetime.now(BR_TZ) else "🔴 Encerrada"
            embed.add_field(
                name=f"📢 {data['titulo'][:30]}",
                value=f"📅 {data['data_hora']}\n✅ {participantes} confirmados\n{status}\n📝 `{data['message_id']}`",
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
    expira_em = datetime.fromisoformat(data['expira_em']).replace(tzinfo=BR_TZ)
    status = "🟢 Ativa" if expira_em > datetime.now(BR_TZ) else "🔴 Encerrada"
    
    embed = discord.Embed(title=f"📊 {data['titulo']}", color=discord.Color.blue())
    embed.add_field(name="📅 Data/Hora", value=data['data_hora'], inline=True)
    embed.add_field(name="📍 Local", value=data['local'], inline=True)
    embed.add_field(name="👤 Criador", value=f"<@{data['criador_id']}>", inline=True)
    embed.add_field(name="✅ Confirmados", value=str(len(participantes)), inline=True)
    embed.add_field(name="📊 Status", value=status, inline=True)
    
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
    
    embed = discord.Embed(title="📋 Lista de Presença", description=f"**{data['titulo']}**", color=discord.Color.green())
    embed.add_field(name="📅 Data", value=data['data_hora'], inline=True)
    embed.add_field(name="📍 Local", value=data['local'], inline=True)
    embed.add_field(name="✅ Total", value=str(len(participantes)), inline=True)
    
    lista = ""
    for i, pid in enumerate(participantes, 1):
        member = interaction.guild.get_member(int(pid))
        if member:
            lista += f"{i}. {member.mention}\n"
    
    if len(lista) > 1024:
        partes = [lista[i:i+1024] for i in range(0, len(lista), 1024)]
        for j, parte in enumerate(partes):
            embed.add_field(name=f"📋 Participantes (parte {j+1})", value=parte, inline=False)
    else:
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
    
    if str(interaction.user.id) != data['criador_id'] and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Só o criador ou admin pode cancelar!", ephemeral=True)
        return
    
    if call_id in bot.active_tasks:
        bot.active_tasks[call_id].cancel()
        del bot.active_tasks[call_id]
    
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

@bot.tree.command(name="chamada_listar_ativas", description="📋 Listar todas as chamadas ativas")
async def chamada_listar_ativas(interaction: discord.Interaction):
    agora = datetime.now(BR_TZ)
    ativas = []
    
    for call_id, data in bot.call_data.items():
        if data.get('channel_id') == str(interaction.channel.id):
            expira_em = datetime.fromisoformat(data['expira_em']).replace(tzinfo=BR_TZ)
            if expira_em > agora:
                ativas.append((call_id, data, expira_em))
    
    if not ativas:
        await interaction.response.send_message("📋 Nenhuma chamada ativa neste canal!", ephemeral=True)
        return
    
    embed = discord.Embed(title="📋 Chamadas Ativas", description=f"Total: {len(ativas)}", color=discord.Color.green())
    
    for call_id, data, expira_em in ativas:
        participantes = len(bot.call_participants.get(call_id, []))
        tempo_restante = expira_em - agora
        horas = int(tempo_restante.total_seconds() // 3600)
        minutos = int((tempo_restante.total_seconds() % 3600) // 60)
        embed.add_field(
            name=f"📢 {data['titulo'][:30]}",
            value=f"✅ {participantes} confirmados | ⏰ {horas}h {minutos}m restantes\n📝 `{data['message_id']}`",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== COMANDOS DE ENQUETE ====================

@bot.tree.command(name="enquete", description="📊 Criar uma enquete dinâmica")
async def enquete_criar(interaction: discord.Interaction):
    modal = CriarEnqueteModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="enquete_info", description="ℹ️ Ver informações de uma enquete")
async def enquete_info(interaction: discord.Interaction, message_id: str):
    enquete_id = None
    for eid, data in bot.enquetes.items():
        if data.get('message_id') == message_id:
            enquete_id = eid
            break
    
    if not enquete_id:
        await interaction.response.send_message("❌ Enquete não encontrada!", ephemeral=True)
        return
    
    data = bot.enquetes[enquete_id]
    total_votos = sum(data["votos"])
    
    embed = discord.Embed(title="📊 Informações da Enquete", description=f"**{data['pergunta']}**", color=discord.Color.blue())
    embed.add_field(name="📝 Opções", value=str(len(data["opcoes"])), inline=True)
    embed.add_field(name="✅ Total de Votos", value=str(total_votos), inline=True)
    embed.add_field(name="👥 Participantes", value=str(len(data["votos_usuario"])), inline=True)
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="enquete_listar", description="📋 Listar todas as enquetes ativas")
async def enquete_listar(interaction: discord.Interaction):
    agora = datetime.now(BR_TZ)
    ativas = []
    
    for eid, data in bot.enquetes.items():
        if data.get('channel_id') == str(interaction.channel.id):
            expira = data.get("expira_em")
            if expira:
                expira_dt = datetime.fromisoformat(expira).replace(tzinfo=BR_TZ)
                if expira_dt > agora:
                    ativas.append((eid, data, expira_dt))
            else:
                ativas.append((eid, data, None))
    
    if not ativas:
        await interaction.response.send_message("📋 Nenhuma enquete ativa neste canal!", ephemeral=True)
        return
    
    embed = discord.Embed(title="📋 Enquetes Ativas", description=f"Total: {len(ativas)}", color=discord.Color.green())
    
    for eid, data, expira in ativas[:10]:
        total_votos = sum(data["votos"])
        status = "🟢 Permanente" if not expira else f"⏰ Expira em breve"
        embed.add_field(
            name=f"📊 {data['pergunta'][:40]}",
            value=f"✅ {total_votos} votos | {status}\n📝 `{data['message_id']}`",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="enquete_gerenciar", description="⚙️ Gerenciar uma enquete")
async def enquete_gerenciar(interaction: discord.Interaction, message_id: str):
    enquete_id = None
    for eid, data in bot.enquetes.items():
        if data.get('message_id') == message_id:
            enquete_id = eid
            break
    
    if not enquete_id:
        await interaction.response.send_message("❌ Enquete não encontrada!", ephemeral=True)
        return
    
    data = bot.enquetes[enquete_id]
    
    if str(interaction.user.id) != data["criador_id"] and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Sem permissão!", ephemeral=True)
        return
    
    embed = discord.Embed(title="⚙️ Painel de Gerenciamento", description=f"**{data['pergunta']}**", color=discord.Color.purple())
    embed.add_field(name="📝 Opções", value=str(len(data["opcoes"])), inline=True)
    embed.add_field(name="✅ Votos", value=str(sum(data["votos"])), inline=True)
    
    view = GerenciarEnqueteView(enquete_id)
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ==================== 🐣 SISTEMA DE PÁSCOA COMPLETO 🐣 ====================

# GIFs de Páscoa
# GIFS_PASCOA = [
   # "https://media.giphy.com/media/l4KibWpBGWchSqCRy/giphy.gif",
   # "https://media.giphy.com/media/26n7b7PjSOZJwVCmY/giphy.gif",
   # "https://media.giphy.com/media/3oz8xtBx06mcZWoNJm/giphy.gif",
   # "https://media.giphy.com/media/xT0GqtcVoRfeMYRnzy/giphy.gif",
   # "https://media.giphy.com/media/3o7TKDtZetOBBiPlkc/giphy.gif",
   # "https://media.giphy.com/media/26n7b7PjSOZJwVCmY/giphy.gif",
   # "https://media.giphy.com/media/l4KibWpBGWchSqCRy/giphy.gif",
   # "https://media.giphy.com/media/xT0GqtcVoRfeMYRnzy/giphy.gif"
#]

#GIFS_COELHO = [
   # "https://media.giphy.com/media/3o7TKDtZetOBBiPlkc/giphy.gif",
   # "https://media.giphy.com/media/6X9UDSBznQG60/giphy.gif",
   # "https://media.giphy.com/media/3o6Mbj2w67HnPQcQoM/giphy.gif",
   # "https://media.giphy.com/media/YKPmNJmilFiQU/giphy.gif",
   # "https://media.giphy.com/media/IwAZ4gsq8OZAs/giphy.gif",
   # "https://media.giphy.com/media/8vZY0QZZjJZqmfResk/giphy.gif"
#]

#GIFS_OVO = [
  #  "https://media.giphy.com/media/3oz8xtBx06mcZWoNJm/giphy.gif",
   # "https://media.giphy.com/media/26n7b7PjSOZJwVCmY/giphy.gif",
   # "https://media.giphy.com/media/l4KibWpBGWchSqCRy/giphy.gif",
   # "https://media.giphy.com/media/3o7TKDtZetOBBiPlkc/giphy.gif",
   # "https://media.giphy.com/media/xT0GqtcVoRfeMYRnzy/giphy.gif"
#]

#GIFS_CHOCOLHATE = [
   # "https://media.giphy.com/media/mGcWBFaedatJPxNVKV/giphy.gif",
   # "https://media.giphy.com/media/3o7TKMeCOV3oXSABHq/giphy.gif",
   # "https://media.giphy.com/media/TIKfNSCAOIhvlZ78LF/giphy.gif",
    #"https://media.giphy.com/media/3o7TKMeCOV3oXSABHq/giphy.gif"
#]

# Perguntas do Quiz de Páscoa
QUIZ_PASCOA = [
    {
        "pergunta": "🐣 Qual animal é o símbolo da Páscoa?",
        "opcoes": ["🐇 Coelho", "🐤 Pinto", "🦆 Pato", "🐓 Galinha"],
        "correta": 0,
        "explicacao": "O coelho de Páscoa é o símbolo mais famoso da festividade!"
    },
    {
        "pergunta": "🥚 Quantas cores tem um ovo de Páscoa tradicional?",
        "opcoes": ["Apenas uma", "Duas ou mais", "Nenhuma, é branco", "Depende do coelho"],
        "correta": 1,
        "explicacao": "Ovos de Páscoa tradicionais são decorados com várias cores!"
    },
    {
        "pergunta": "🍫 De que é feito o ovo de Páscoa brasileiro?",
        "opcoes": ["Açúcar", "Chocolate", "Plástico", "Borracha"],
        "correta": 1,
        "explicacao": "No Brasil, os ovos de Páscoa são feitos de chocolate!"
    },
    {
        "pergunta": "🌸 Em que estação do ano a Páscoa é celebrada no Brasil?",
        "opcoes": ["Verão", "Inverno", "Primavera", "Outono"],
        "correta": 3,
        "explicacao": "No Brasil, a Páscoa cai no outono (março/abril)!"
    },
    {
        "pergunta": "🐇 O que o coelho da Páscoa esconde?",
        "opcoes": ["Cenouras", "Ovos coloridos", "Chocolates", "Flores"],
        "correta": 1,
        "explicacao": "A tradição é o coelho esconder ovos coloridos para as crianças encontrarem!"
    },
    {
        "pergunta": "✝️ A Páscoa cristã celebra qual evento?",
        "opcoes": ["Nascimento de Jesus", "Ressurreição de Jesus", "Batizado de Jesus", "Milagre dos pães"],
        "correta": 1,
        "explicacao": "A Páscoa cristã comemora a ressurreição de Jesus Cristo!"
    },
    {
        "pergunta": "🌕 Como a data da Páscoa é calculada?",
        "opcoes": ["É sempre 25 de março", "Depende da lua cheia", "É sempre domingo fixo", "Muda todo ano aleatoriamente"],
        "correta": 1,
        "explicacao": "A Páscoa cai no primeiro domingo após a primeira lua cheia da primavera!"
    },
    {
        "pergunta": "🐥 O que representa o ovo na Páscoa?",
        "opcoes": ["Morte", "Nova vida e renascimento", "Riqueza", "Sorte"],
        "correta": 1,
        "explicacao": "O ovo simboliza nova vida, renascimento e esperança!"
    },
    {
        "pergunta": "🍬 Qual é o chocolate mais vendido no Brasil na Páscoa?",
        "opcoes": ["Branco", "Amargo", "Ao leite", "Meio amargo"],
        "correta": 2,
        "explicacao": "O chocolate ao leite é o favorito dos brasileiros na Páscoa!"
    },
    {
        "pergunta": "🌺 Qual flor é símbolo da Páscoa?",
        "opcoes": ["Rosa", "Tulipa", "Lírio", "Girassol"],
        "correta": 2,
        "explicacao": "O lírio branco é considerado a flor da Páscoa!"
    }
]

# Decorações de Páscoa para embeds
EASTER_DECORATIONS = [
    "🌸🐣🥚🐇🌸",
    "🐰🍫🌷🌼🐰",
    "🥚🌸🐥🌷🥚",
    "🌼🐇🍬🐣🌼",
    "🦋🌸🥚🌺🦋"
]

def easter_header():
    return random.choice(EASTER_DECORATIONS)

@bot.tree.command(name="pascoa_daily", description="🐣 Recompensa diária de Páscoa!")
async def pascoa_daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)
    hoje = agora.date()

    # Verifica cooldown
    if user_id in bot.pascoa_daily:
        ultimo = datetime.fromisoformat(bot.pascoa_daily[user_id]).date()
        if hoje == ultimo:
            # Calcula tempo restante
            proximo = datetime(agora.year, agora.month, agora.day, 0, 0, 0, tzinfo=BR_TZ) + timedelta(days=1)
            restante = proximo - agora
            horas = int(restante.total_seconds() // 3600)
            minutos = int((restante.total_seconds() % 3600) // 60)
            await interaction.response.send_message(
                f"🐇 Você já coletou seu presente de Páscoa hoje!\n⏰ Próximo daily em **{horas}h {minutos}m**",
                ephemeral=True
            )
            return

    # Recompensas variadas
    pontos_base = random.randint(10, 30)
    moedas_base = random.randint(200, 600)
    
    # Chance de bônus especial
    bonus = ""
    extra_pontos = 0
    extra_moedas = 0
    
    roll = random.random()
    if roll < 0.05:  # 5% chance jackpot
        extra_pontos = 50
        extra_moedas = 1000
        bonus = "🎊 **JACKPOT DE PÁSCOA!** Você encontrou um ovo de ouro! +50 pts +1000 moedas extras!"
    elif roll < 0.20:  # 15% chance bônus grande
        extra_pontos = 20
        extra_moedas = 300
        bonus = "✨ **Bônus Especial!** Ovo de chocolate gigante! +20 pts +300 moedas extras!"
    elif roll < 0.45:  # 25% chance bônus médio
        extra_pontos = 10
        extra_moedas = 150
        bonus = "🌸 **Bônus!** Cestinha de ovos coloridos! +10 pts +150 moedas extras!"

    total_pontos = pontos_base + extra_pontos
    total_moedas = moedas_base + extra_moedas

    bot.add_pascoa_pontos(user_id, total_pontos)
    if user_id not in bot.user_balances:
        bot.user_balances[user_id] = 0
    bot.user_balances[user_id] += total_moedas
    bot.pascoa_daily[user_id] = agora.isoformat()
    bot.save_data()

    pontos_total = bot.pascoa_pontos.get(user_id, 0)
    gif = random.choice(GIFS_PASCOA)

    deco = easter_header()
    embed = discord.Embed(
        title=f"{deco} PRESENTE DE PÁSCOA! {deco}",
        description=f"🐇 **{interaction.user.display_name}**, o Coelhinho trouxe presentes!",
        color=discord.Color.from_str("#FFD700")
    )
    embed.set_image(url=gif)
    embed.add_field(name="🥚 Pontos de Páscoa", value=f"+**{pontos_base}** pontos", inline=True)
    embed.add_field(name="🍫 Moedas", value=f"+**{moedas_base}** moedas", inline=True)
    if bonus:
        embed.add_field(name="🎁 BÔNUS SURPRESA!", value=bonus, inline=False)
    embed.add_field(name="🏆 Total de Pontos", value=f"**{pontos_total}** pontos de Páscoa", inline=False)
    embed.set_footer(text="🐣 Volte amanhã para mais presentes!")
    embed.timestamp = agora

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pascoa_quiz", description="🧠 Responda perguntas de Páscoa e ganhe pontos!")
async def pascoa_quiz(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)

    # Cooldown de 30 minutos
    if user_id in bot.pascoa_quiz_cd:
        ultimo = datetime.fromisoformat(bot.pascoa_quiz_cd[user_id])
        if agora - ultimo.replace(tzinfo=BR_TZ) < timedelta(minutes=30):
            restante = timedelta(minutes=30) - (agora - ultimo.replace(tzinfo=BR_TZ))
            minutos = int(restante.total_seconds() // 60)
            await interaction.response.send_message(
                f"🧠 Aguarde **{minutos} minutos** para jogar o quiz de Páscoa novamente!",
                ephemeral=True
            )
            return

    pergunta_data = random.choice(QUIZ_PASCOA)
    opcoes = pergunta_data["opcoes"]
    correta_idx = pergunta_data["correta"]

    # Cria view com botões
    view = QuizPascoaView(user_id, pergunta_data, opcoes, correta_idx)

    deco = easter_header()
    embed = discord.Embed(
        title=f"{deco} QUIZ DE PÁSCOA {deco}",
        description=f"**{pergunta_data['pergunta']}**\n\nEscolha a resposta correta!",
        color=discord.Color.from_str("#FF69B4")
    )
    embed.set_thumbnail(url="https://tenor.com/pt-BR/view/golden-eggs-willy-wonka-and-the-chocolate-factory-clean-the-eggs-get-the-eggs-ready-chocolate-golden-eggs-gif-21442701")
    embed.set_footer(text="⏰ Você tem 30 segundos!")

    bot.pascoa_quiz_cd[user_id] = agora.isoformat()

    await interaction.response.send_message(embed=embed, view=view)

class QuizPascoaView(View):
    def __init__(self, user_id: str, pergunta_data: dict, opcoes: list, correta_idx: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.pergunta_data = pergunta_data
        self.correta_idx = correta_idx
        self.respondido = False
        
        cores = [
            discord.ButtonStyle.primary,
            discord.ButtonStyle.success,
            discord.ButtonStyle.danger,
            discord.ButtonStyle.secondary
        ]
        
        for i, opcao in enumerate(opcoes):
            btn = Button(
                label=opcao[:50],
                style=cores[i % len(cores)],
                custom_id=f"quiz_{i}"
            )
            btn.callback = self.make_callback(i)
            self.add_item(btn)
    
    def make_callback(self, idx: int):
        async def callback(interaction: discord.Interaction):
            if str(interaction.user.id) != self.user_id:
                await interaction.response.send_message("❌ Este quiz não é seu!", ephemeral=True)
                return
            
            if self.respondido:
                await interaction.response.send_message("❌ Você já respondeu!", ephemeral=True)
                return
            
            self.respondido = True
            self.stop()
            
            acertou = idx == self.correta_idx
            
            if acertou:
                pontos = random.randint(15, 25)
                moedas = random.randint(100, 200)
                bot.add_pascoa_pontos(str(interaction.user.id), pontos)
                if str(interaction.user.id) not in bot.user_balances:
                    bot.user_balances[str(interaction.user.id)] = 0
                bot.user_balances[str(interaction.user.id)] += moedas
                bot.save_data()
                
                gif = random.choice(GIFS_PASCOA)
                embed = discord.Embed(
                    title="🎉 CORRETO! 🎉",
                    description=f"✅ **Parabéns!** Você acertou!\n\n💡 {self.pergunta_data['explicacao']}",
                    color=discord.Color.green()
                )
                embed.set_image(url=gif)
                embed.add_field(name="🥚 Pontos ganhos", value=f"+**{pontos}** pontos de Páscoa", inline=True)
                embed.add_field(name="🍫 Moedas ganhas", value=f"+**{moedas}** moedas", inline=True)
            else:
                embed = discord.Embed(
                    title="❌ ERROU!",
                    description=f"A resposta correta era: **{self.pergunta_data['opcoes'][self.correta_idx]}**\n\n💡 {self.pergunta_data['explicacao']}",
                    color=discord.Color.red()
                )
                embed.set_thumbnail(url="https://tenor.com/pt-BR/view/merry-easter-snoopy-easter-gif-9072974292192845609")
                embed.set_footer(text="Não desista! Tente novamente em 30 minutos.")
            
            await interaction.response.edit_message(embed=embed, view=None)
        
        return callback

@bot.tree.command(name="pascoa_caca", description="🐇 Caçar o coelho da Páscoa! (cooldown 1h)")
async def pascoa_caca(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)

    # Cooldown de 1 hora
    if user_id in bot.pascoa_coelho:
        ultimo = datetime.fromisoformat(bot.pascoa_coelho[user_id]).replace(tzinfo=BR_TZ)
        diff = agora - ultimo
        if diff < timedelta(hours=1):
            restante = timedelta(hours=1) - diff
            minutos = int(restante.total_seconds() // 60)
            await interaction.response.send_message(
                f"🐇 O coelho fugiu e está se escondendo! Volte em **{minutos} minutos** para tentar de novo!",
                ephemeral=True
            )
            return

    # Resultado da caça
    roll = random.random()
    gif = random.choice(GIFS_COELHO)

    deco = easter_header()
    
    if roll < 0.60:  # 60% sucesso
        pontos = random.randint(8, 20)
        moedas = random.randint(100, 250)
        bot.add_pascoa_pontos(user_id, pontos)
        if user_id not in bot.user_balances:
            bot.user_balances[user_id] = 0
        bot.user_balances[user_id] += moedas
        bot.pascoa_coelho[user_id] = agora.isoformat()
        bot.save_data()

        cenarios = [
            f"🐇 Você rasteou pelo jardim e pegou o coelho de surpresa! Ele deixou cair um ovo de chocolate!",
            f"🌷 O coelho estava dormindo atrás de uma tulipa. Você pegou ele com cuidado e ganhou uma cestinha de ovos!",
            f"🥕 Você usou uma cenoura como isca e o coelho não resistiu! Ele deixou ovos coloridos pelo caminho!",
            f"🌸 Correndo entre as flores, você finalmente alcançou o coelhinho! Ele te deu presentes em troca da liberdade!",
        ]
        
        embed = discord.Embed(
            title=f"{deco} COELHO CAPTURADO! {deco}",
            description=random.choice(cenarios),
            color=discord.Color.green()
        )
        embed.set_image(url=gif)
        embed.add_field(name="🥚 Pontos", value=f"+**{pontos}** pontos de Páscoa", inline=True)
        embed.add_field(name="🍫 Moedas", value=f"+**{moedas}** moedas", inline=True)
        embed.set_footer(text="🐇 O coelho foi solto para distribuir mais ovos!")
        
    elif roll < 0.85:  # 25% falha com mini-recompensa
        pontos = random.randint(2, 5)
        bot.add_pascoa_pontos(user_id, pontos)
        bot.pascoa_coelho[user_id] = agora.isoformat()
        bot.save_data()

        cenarios = [
            f"💨 O coelho era MUITO rápido! Ele fugiu, mas deixou um ovinho pequenininho para trás...",
            f"🌿 Você quase chegou! O coelho deu uma cambalhota e sumiu no meio do mato. Ao menos achou um ovo perdido.",
            f"🐇 Pff! O coelho te encarou, deu uma piscadela e desapareceu. Mas deixou uma lembrancinha!",
        ]
        
        embed = discord.Embed(
            title=f"💨 Quase!",
            description=random.choice(cenarios),
            color=discord.Color.orange()
        )
        embed.set_image(url=gif)
        embed.add_field(name="🥚 Pontos (consolação)", value=f"+**{pontos}** pontos", inline=True)
        embed.set_footer(text="Tente de novo em 1 hora!")
        
    else:  # 15% falha total
        bot.pascoa_coelho[user_id] = agora.isoformat()
        
        cenarios = [
            f"😅 Você tropeçou num ovo e caiu de bunda no gramado. O coelho riu e fugiu!",
            f"🌧️ Uma nuvem passou, você se distraiu e o coelho sumiu na neblina de chocolate.",
            f"🐇 O coelho olhou pra você, fez L com a patinha e foi embora. Zero pontos hoje!",
        ]
        
        embed = discord.Embed(
            title=f"😅 Coelho escapou!",
            description=random.choice(cenarios),
            color=discord.Color.red()
        )
        embed.set_image(url=gif)
        embed.set_footer(text="Não desista! Tente novamente em 1 hora.")

    embed.timestamp = agora
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pascoa_ovo", description="🥚 Encontrar um ovo escondido! (a cada 20min)")
async def pascoa_ovo(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)

    # Cooldown de 20 minutos por canal
    chave = f"{user_id}_{interaction.channel.id}"
    if chave in bot.pascoa_ovos:
        ultimo = datetime.fromisoformat(bot.pascoa_ovos[chave]).replace(tzinfo=BR_TZ)
        diff = agora - ultimo
        if diff < timedelta(minutes=20):
            restante = timedelta(minutes=20) - diff
            minutos = int(restante.total_seconds() // 60)
            segundos = int(restante.total_seconds() % 60)
            await interaction.response.send_message(
                f"🥚 Você já vasculhou este esconderijo! Espere **{minutos}m {segundos}s** para procurar de novo!",
                ephemeral=True
            )
            return

    bot.pascoa_ovos[chave] = agora.isoformat()
    gif = random.choice(GIFS_OVO)

    tipos_ovo = [
        ("🥚 Ovo Comum", 3, 30, "Um ovinho simples mas fofo!"),
        ("🥚 Ovo Colorido", 6, 60, "Pintadinho e cheio de alegria!"),
        ("🥚 Ovo de Chocolate", 10, 100, "Cheiroso e delicioso!"),
        ("🥚 Ovo Dourado", 20, 250, "Raro! O coelho guardava com carinho."),
        ("🥚 Ovo de Cristal", 35, 500, "RARISSIMO! Brilha como diamante!"),
        ("🥚 Ovo Vazio", 0, 0, "Esse estava vazio... que decepção 🥲"),
    ]

    pesos = [35, 30, 20, 10, 3, 2]
    escolha = random.choices(tipos_ovo, weights=pesos, k=1)[0]
    nome, pontos, moedas, descricao = escolha

    deco = easter_header()

    if pontos > 0:
        bot.add_pascoa_pontos(user_id, pontos)
        if user_id not in bot.user_balances:
            bot.user_balances[user_id] = 0
        bot.user_balances[user_id] += moedas
        bot.save_data()

        embed = discord.Embed(
            title=f"{deco} OVO ENCONTRADO! {deco}",
            description=f"**{nome}**\n{descricao}",
            color=discord.Color.from_str("#FFD700") if "Dourado" in nome else discord.Color.from_str("#FF69B4")
        )
        embed.set_image(url=gif)
        embed.add_field(name="🥚 Pontos", value=f"+**{pontos}**", inline=True)
        embed.add_field(name="🍫 Moedas", value=f"+**{moedas}**", inline=True)
    else:
        embed = discord.Embed(
            title=f"😔 Só tinha ar...",
            description=descricao,
            color=discord.Color.dark_gray()
        )
        embed.set_image(url=gif)

    embed.set_footer(text="🥚 Procure em outros canais! Cada canal tem ovos escondidos.")
    embed.timestamp = agora

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pascoa_corrida", description="🐇 Aposte numa corrida de coelhos! (50 moedas)")
async def pascoa_corrida(interaction: discord.Interaction, coelho: int):
    user_id = str(interaction.user.id)
    
    if coelho < 1 or coelho > 5:
        await interaction.response.send_message("❌ Escolha um coelho entre 1 e 5!", ephemeral=True)
        return
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 50:
        await interaction.response.send_message("❌ Precisa de 50 moedas para apostar!", ephemeral=True)
        return
    
    bot.user_balances[user_id] -= 50
    
    coelhos = ["🐰 Branquinho", "🐇 Pretinho", "🐰 Fofo", "🐇 Veloz", "🐰 Campeão"]
    
    # Simula corrida
    pistas = []
    posicoes = list(range(5))
    random.shuffle(posicoes)
    
    ordem_chegada = [coelhos[i] for i in posicoes]
    vencedor_idx = posicoes[0]  # Índice do vencedor (0-based)
    vencedor_num = vencedor_idx + 1
    
    ganhou = (coelho - 1) == vencedor_idx
    
    # Monta a corrida visual
    corrida_texto = ""
    for i, coelho_nome in enumerate(coelhos):
        passos = random.randint(3, 18)
        pista = "▫️" * passos + "🐇" + "▫️" * (20 - passos)
        if i == vencedor_idx:
            pista = "🏆" + pista[:-3]
        corrida_texto += f"{i+1}. {pista} {coelho_nome}\n"
    
    deco = easter_header()
    gif = random.choice(GIFS_COELHO)
    
    if ganhou:
        multiplicador = random.choice([2, 3, 4, 5])
        premio = 50 * multiplicador
        bot.user_balances[user_id] += premio
        bot.add_pascoa_pontos(user_id, 15)
        bot.save_data()
        
        embed = discord.Embed(
            title=f"{deco} SEU COELHO VENCEU! {deco}",
            description=f"```\n{corrida_texto}```",
            color=discord.Color.gold()
        )
        embed.add_field(name="🏆 Vencedor", value=f"**{coelhos[vencedor_idx]}** (Coelho {vencedor_num})", inline=True)
        embed.add_field(name="💰 Prêmio", value=f"**{premio} moedas** (x{multiplicador})", inline=True)
        embed.add_field(name="🥚 Pontos", value="+**15** pontos de Páscoa", inline=True)
        embed.set_image(url=gif)
    else:
        embed = discord.Embed(
            title=f"😔 Seu coelho não venceu...",
            description=f"```\n{corrida_texto}```",
            color=discord.Color.red()
        )
        embed.add_field(name="🏆 Vencedor", value=f"**{coelhos[vencedor_idx]}** (Coelho {vencedor_num})", inline=True)
        embed.add_field(name="💸 Perdeu", value="50 moedas", inline=True)
        embed.set_footer(text="Tente de novo!")
    
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pascoa_chocolate", description="🍫 Presentear alguém com chocolate de Páscoa! (80 moedas)")
async def pascoa_chocolate(interaction: discord.Interaction, membro: discord.Member, mensagem: str = ""):
    user_id = str(interaction.user.id)
    
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se dar chocolate!", ephemeral=True)
        return
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 80:
        await interaction.response.send_message("❌ Precisa de 80 moedas para comprar chocolate!", ephemeral=True)
        return
    
    bot.user_balances[user_id] -= 80
    target_id = str(membro.id)
    if target_id not in bot.user_balances:
        bot.user_balances[target_id] = 0
    bot.user_balances[target_id] += 30  # Recebe moedas também
    
    # Pontos para quem dá o presente
    bot.add_pascoa_pontos(user_id, 5)
    bot.save_data()

    gif = random.choice(GIFS_CHOCOLHATE)
    deco = easter_header()
    
    chocolates = ["🍫 Chocolate Ao Leite", "🍬 Bombom de Páscoa", "🥚 Ovo de Chocolate Gigante", 
                  "🍭 Trufa de Chocolate", "🍫 Barra de Chocolate Especial"]
    chocolate_escolhido = random.choice(chocolates)
    
    embed = discord.Embed(
        title=f"{deco} CHOCOLATE DE PÁSCOA! {deco}",
        description=f"**{interaction.user.display_name}** presenteou **{membro.display_name}** com um **{chocolate_escolhido}**! 🎁",
        color=discord.Color.from_str("#8B4513")
    )
    embed.set_image(url=gif)
    
    if mensagem:
        embed.add_field(name="💌 Mensagem", value=f"*\"{mensagem}\"*", inline=False)
    
    embed.add_field(name="🍫 Presente", value=chocolate_escolhido, inline=True)
    embed.add_field(name="💰 Bônus para quem recebeu", value="+30 moedas", inline=True)
    embed.set_footer(text=f"🐣 O espírito da Páscoa une os corações!")
    embed.timestamp = datetime.now(BR_TZ)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pascoa_ranking", description="🏆 Ranking de pontos de Páscoa do servidor!")
async def pascoa_ranking(interaction: discord.Interaction):
    if not bot.pascoa_pontos:
        await interaction.response.send_message("🐣 Ninguém tem pontos de Páscoa ainda! Use `/pascoa_daily` para começar!", ephemeral=True)
        return

    # Filtra apenas membros do servidor
    membros_pontos = []
    for uid, pontos in bot.pascoa_pontos.items():
        membro = interaction.guild.get_member(int(uid))
        if membro and not membro.bot and pontos > 0:
            membros_pontos.append((membro, pontos))
    
    membros_pontos.sort(key=lambda x: x[1], reverse=True)
    
    if not membros_pontos:
        await interaction.response.send_message("🐣 Nenhum membro do servidor tem pontos ainda!", ephemeral=True)
        return

    deco = easter_header()
    embed = discord.Embed(
        title=f"{deco} RANKING DE PÁSCOA {deco}",
        description="🐣 Os melhores caçadores de ovos do servidor!",
        color=discord.Color.from_str("#FFD700")
    )
    embed.set_thumbnail(url="https://tenor.com/pt-BR/view/he-is-risen-praise-him-gospel-church-easter-gif-16854388")

    medalhas = ["🥇", "🥈", "🥉"]
    ranking_texto = ""
    
    for i, (membro, pontos) in enumerate(membros_pontos[:15], 1):
        if i <= 3:
            medalha = medalhas[i-1]
        else:
            medalha = f"**{i}°**"
        
        ranking_texto += f"{medalha} {membro.display_name} — 🥚 **{pontos}** pontos\n"
    
    embed.description = f"🐣 Os melhores caçadores de ovos!\n\n{ranking_texto}"
    
    # Posição do usuário
    user_id = str(interaction.user.id)
    pos = next((i+1 for i, (m, _) in enumerate(membros_pontos) if str(m.id) == user_id), None)
    pts = bot.pascoa_pontos.get(user_id, 0)
    
    if pos:
        embed.add_field(
            name="📍 Sua posição",
            value=f"**{pos}°** lugar com **{pts}** pontos",
            inline=False
        )

    embed.set_footer(text="🐇 Jogue minigames de Páscoa para subir no ranking!")
    embed.timestamp = datetime.now(BR_TZ)

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pascoa_pontos", description="🥚 Ver seus pontos de Páscoa")
async def pascoa_pontos_cmd(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    if membro is None:
        membro = interaction.user
    
    user_id = str(membro.id)
    pontos = bot.pascoa_pontos.get(user_id, 0)
    
    # Calcula ranking
    membros_pontos = sorted(bot.pascoa_pontos.items(), key=lambda x: x[1], reverse=True)
    pos = next((i+1 for i, (uid, _) in enumerate(membros_pontos) if uid == user_id), None)
    
    # Título baseado nos pontos
    if pontos >= 500:
        titulo = "🌟 Grande Mestre dos Ovos"
    elif pontos >= 300:
        titulo = "🥇 Caçador Lendário"
    elif pontos >= 150:
        titulo = "🥈 Caçador Expert"
    elif pontos >= 50:
        titulo = "🥉 Caçador Iniciante"
    elif pontos > 0:
        titulo = "🐣 Aprendiz de Páscoa"
    else:
        titulo = "🥚 Ainda sem ovos..."

    deco = easter_header()
    embed = discord.Embed(
        title=f"{deco} PONTOS DE PÁSCOA {deco}",
        description=f"**{membro.display_name}** — {titulo}",
        color=discord.Color.from_str("#FF69B4")
    )
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.add_field(name="🥚 Pontos Totais", value=f"**{pontos}** pontos", inline=True)
    if pos:
        embed.add_field(name="📊 Ranking", value=f"**{pos}°** lugar", inline=True)
    embed.set_footer(text="🐇 Use /pascoa_daily, /pascoa_caca, /pascoa_ovo e /pascoa_quiz para ganhar pontos!")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pascoa_slot", description="🎰 Caça-níqueis de Páscoa! (40 moedas)")
async def pascoa_slot(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 40:
        await interaction.response.send_message("❌ Precisa de 40 moedas!", ephemeral=True)
        return
    
    bot.user_balances[user_id] -= 40
    
    simbolos_pascoa = ["🥚", "🐣", "🐇", "🌸", "🍫", "🌷", "✝️", "🎀"]
    pesos_slot = [25, 20, 15, 15, 10, 8, 5, 2]
    
    resultado = random.choices(simbolos_pascoa, weights=pesos_slot, k=3)
    
    premio_moedas = 0
    premio_pontos = 0
    mensagem_resultado = ""
    
    if resultado[0] == resultado[1] == resultado[2]:
        if resultado[0] == "🎀":
            premio_moedas = 2000
            premio_pontos = 100
            mensagem_resultado = "🎊 **MEGA JACKPOT DE PÁSCOA!** 🎊"
        elif resultado[0] == "✝️":
            premio_moedas = 800
            premio_pontos = 50
            mensagem_resultado = "✨ **JACKPOT SAGRADO!** ✨"
        elif resultado[0] == "🍫":
            premio_moedas = 500
            premio_pontos = 30
            mensagem_resultado = "🍫 **JACKPOT DE CHOCOLATE!**"
        elif resultado[0] == "🐇":
            premio_moedas = 400
            premio_pontos = 25
            mensagem_resultado = "🐇 **JACKPOT DO COELHINHO!**"
        elif resultado[0] == "🥚":
            premio_moedas = 300
            premio_pontos = 20
            mensagem_resultado = "🥚 **JACKPOT DO OVO!**"
        else:
            premio_moedas = 200
            premio_pontos = 15
            mensagem_resultado = "🌸 **TRIPLO ESPECIAL!**"
    elif resultado[0] == resultado[1] or resultado[1] == resultado[2] or resultado[0] == resultado[2]:
        premio_moedas = 80
        premio_pontos = 5
        mensagem_resultado = "🥳 Par encontrado!"
    else:
        mensagem_resultado = "😔 Sem sorte dessa vez..."
    
    if premio_moedas > 0:
        bot.user_balances[user_id] += premio_moedas
        bot.add_pascoa_pontos(user_id, premio_pontos)
    
    bot.save_data()
    
    deco = easter_header()
    embed = discord.Embed(
        title=f"{deco} CAÇA-NÍQUEIS DE PÁSCOA {deco}",
        description=f"# ` {resultado[0]} | {resultado[1]} | {resultado[2]} `\n\n**{mensagem_resultado}**",
        color=discord.Color.gold() if premio_moedas > 0 else discord.Color.dark_gray()
    )
    
    if premio_moedas > 0:
        embed.add_field(name="🍫 Moedas", value=f"+**{premio_moedas}**", inline=True)
        embed.add_field(name="🥚 Pontos", value=f"+**{premio_pontos}**", inline=True)
        gif = random.choice(GIFS_PASCOA)
        embed.set_image(url=gif)
    
    embed.add_field(name="💰 Saldo atual", value=f"**{bot.user_balances.get(user_id, 0)}** moedas", inline=False)
    embed.set_footer(text="🎰 Tente de novo para ganhar mais!")
    embed.timestamp = datetime.now(BR_TZ)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pascoa_info", description="🐣 Informações sobre o sistema de Páscoa")
async def pascoa_info(interaction: discord.Interaction):
    deco = easter_header()
    embed = discord.Embed(
        title=f"{deco} SISTEMA DE PÁSCOA {deco}",
        description="🐇 Bem-vindo ao mundo de Páscoa do Fort Bot!\n\nColecione pontos de Páscoa jogando minigames e suba no ranking!",
        color=discord.Color.from_str("#FFD700")
    )
    embed.set_thumbnail(url="https://tenor.com/pt-BR/view/easter-happy-easter-easter-bunny-hat-magic-trick-gif-8687929519437520988")
    embed.add_field(
        name="🎮 Minigames",
        value="`/pascoa_daily` — Daily de Páscoa (1x por dia)\n"
              "`/pascoa_quiz` — Quiz temático (30min cooldown)\n"
              "`/pascoa_caca` — Caçar o coelho (1h cooldown)\n"
              "`/pascoa_ovo` — Encontrar ovos escondidos (20min por canal)\n"
              "`/pascoa_corrida` — Corrida de coelhos (50 moedas)\n"
              "`/pascoa_slot` — Caça-níqueis temático (40 moedas)\n"
              "`/pascoa_chocolate` — Presentear alguém (80 moedas)",
        inline=False
    )
    embed.add_field(
        name="🏆 Ranking & Pontos",
        value="`/pascoa_ranking` — Ver ranking do servidor\n"
              "`/pascoa_pontos` — Ver seus pontos",
        inline=False
    )
    embed.add_field(
        name="🥚 Títulos",
        value="🐣 Aprendiz (1+ pts)\n"
              "🥉 Caçador Iniciante (50+ pts)\n"
              "🥈 Caçador Expert (150+ pts)\n"
              "🥇 Caçador Lendário (300+ pts)\n"
              "🌟 Grande Mestre (500+ pts)",
        inline=False
    )
    embed.set_footer(text="🌸 Feliz Páscoa! Que os ovos te encontrem!")
    await interaction.response.send_message(embed=embed)

# ==================== 🎭 SISTEMA DE RP 🎭 ====================

# GIFs de RP
GIFS_RP = {
    "abraco": [
        "https://media.giphy.com/media/v1.Y2lkPTc5MGI3NjExaHdua3U1dW95MzU2amtwcTMwenB1cm5tMGRjcnBoNW5xcXJ1cXByZyZlcD12MV9naWZzX3NlYXJjaCZjdD1n/1JmGiBtqTuehfYxuy9/giphy.gif",
        "https://media1.tenor.com/m/SYsRdiK-T7gAAAAd/hug-anime.gif",
        "https://media1.tenor.com/m/BFmsQg9J1ZMAAAAd/chikako-hugging-otohime-for-the-first-and-she-confused.gif",
        "https://media1.tenor.com/m/CBJKhz9QvnMAAAAd/cute-anime-cute.gif",
        "https://media1.tenor.com/m/_Ip7XSmd8M8AAAAd/clannad-after-story-anime.gif"

    ],
    "beijo": [
        "https://media1.tenor.com/m/kmxEaVuW8AoAAAAd/kiss-gentle-kiss.gif",
        "https://media1.tenor.com/m/gNhRibwJ0JMAAAAd/gay-anime.gif",
        "https://media1.tenor.com/m/IxSPEt5BOQIAAAAd/kiss-gay.gif",
        "https://media1.tenor.com/m/89DvSXKzlVwAAAAd/anime-kiss-kiss.gif"
        ],
    "choro": [
        "https://media1.tenor.com/m/j_jAo-neywoAAAAd/marin-crying-marin-kitagawa.gif",
        "https://media1.tenor.com/m/Bhq1WZGJfqIAAAAd/frieren-cry-frieren-beyond-journey%27s-end.gif",
        "https://media1.tenor.com/m/DifoWwjRvOcAAAAd/tohru-honda-tohru.gif"
    ],
    "riso": [
        "https://media1.tenor.com/m/K6WDm9L78mgAAAAd/rezero-rem.gif",
        "https://media1.tenor.com/m/BP9vMzwRSZwAAAAd/laughing-lol.gif",
        "https://media1.tenor.com/m/uxOWCWOIypAAAAAd/morfonication-anime-laugh.gif"
    ],
    "sono": [
        "https://media1.tenor.com/m/d9AcU5UmEdoAAAAd/anime-fran.gif",
        "https://media1.tenor.com/m/dUkiteCccQQAAAAd/yuru-camp-kagamihara-nadeshiko.gif"
    ],
    "briga": [
        "https://media1.tenor.com/m/b0ZXAm867pYAAAAd/jujutsu-kaisen-season-3.gif",
        "https://media1.tenor.com/m/teMaRqd27LgAAAAd/foot-waving-ghost.gif"
    ],
    "dance": [
        "https://media.tenor.com/uRlxzRNgp2MAAAAj/anime-girl.gif",
        "https://media1.tenor.com/m/9hSEFOrYc8cAAAAd/sakura-trick-dancing.gif"
    ],
    "pensando": [
        "https://media1.tenor.com/m/f3XybJki0H4AAAAd/anime-thinking.gif",
        "https://media1.tenor.com/m/gGO8Cx57zDYAAAAd/maomao-apothecary-diaries.gif"
    ],
    "susto": [
        "https://media1.tenor.com/m/nEh0yvlMrEgAAAAd/anime-scare.gif",
        "https://media1.tenor.com/m/RhyxCbENd6YAAAAd/umaru-chan-scared.gif"
    ],
    "olhando": [
        "https://media1.tenor.com/m/rVdLW8Oi97kAAAAd/what-aki-adagaki.gif",
        "https://media1.tenor.com/m/CWvsaRKWTsAAAAAd/smug.gif"
    ],
    "envergonhado": [
        "https://media1.tenor.com/m/GbgGJT3nsVUAAAAd/flustered-flushed.gif",
        "https://media1.tenor.com/m/4rcKprvD5hEAAAAd/anime-boy.gif"
    ],
    "mimos": [
        "https://media1.tenor.com/m/MVK93pHLpz4AAAAd/anime-hug-anime.gif",
        "https://media1.tenor.com/m/5MuGtFXKiGMAAAAd/anime.gif"
    ],
    "raiva": [
        "https://media1.tenor.com/m/hkoyf1VeaZ4AAAAd/anime-angry.gif",
        "https://media1.tenor.com/m/MvKZZ7JCkUMAAAAd/anime-angry.gif",
        "https://media1.tenor.com/m/3oYh5_W_Fd8AAAAd/brat-annoying.gif"
    ],
    "curiosidade": [
        "https://media1.tenor.com/m/qCuO6yW3qS0AAAAd/tonikawa-anime.gif",
        "https://media1.tenor.com/m/O_HYVj2aFyIAAAAd/nejire-curious.gif"
    ],
    "tristeza": [
        "https://media1.tenor.com/m/ukwvYi0Olk8AAAAd/sad-anime-guy-lonely-anime-guy.gif",
        "https://media1.tenor.com/m/8Ob5KEU7vKAAAAAd/anime-my-dress-up-darling.gif"
    ],
    "comemoracao": [
        "https://media1.tenor.com/m/_KYN7H6-42kAAAAd/celebrando-celebraci%C3%B3n.gif",
        "https://media1.tenor.com/m/YXXkNqv16AgAAAAd/oshi-no-ko-anime.gif"
    ]
}

RP_CORES = {
    "abraco": discord.Color.from_str("#FF69B4"),
    "beijo": discord.Color.red(),
    "choro": discord.Color.blue(),
    "riso": discord.Color.yellow(),
    "sono": discord.Color.dark_blue(),
    "briga": discord.Color.orange(),
    "dance": discord.Color.purple(),
    "pensando": discord.Color.teal(),
    "susto": discord.Color.dark_gray(),
    "olhando": discord.Color.green(),
    "envergonhado": discord.Color.from_str("#FF6347"),
    "mimos": discord.Color.from_str("#FFB6C1"),
    "raiva": discord.Color.dark_red(),
    "curiosidade": discord.Color.from_str("#87CEEB"),
    "tristeza": discord.Color.dark_blue(),
    "comemoracao": discord.Color.gold()
}

async def rp_acao(interaction: discord.Interaction, acao: str, titulo: str, 
                  membro: Optional[discord.Member], descricao_sozinho: str, descricao_com: str):
    gif = random.choice(GIFS_RP.get(acao, ["https://media.giphy.com/media/3ZnBrkqoaI2hq/giphy.gif"]))
    cor = RP_CORES.get(acao, discord.Color.blue())
    
    if membro and membro != interaction.user:
        descricao = descricao_com.format(
            user=interaction.user.mention,
            alvo=membro.mention
        )
    else:
        descricao = descricao_sozinho.format(user=interaction.user.mention)
    
    embed = discord.Embed(
        title=titulo,
        description=descricao,
        color=cor
    )
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_abraco", description="🤗 Dar um abraço em RP")
async def rp_abraco(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "abraco", "🤗 ABRAÇO!", membro,
        "**{user}** se abraça sozinho... que fofo! 🥹",
        "**{user}** abraça **{alvo}** com carinho! 💞")

@bot.tree.command(name="rp_beijo", description="💋 Dar um beijo em RP")
async def rp_beijo(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "beijo", "💋 BEIJO!", membro,
        "**{user}** manda um beijinho pro ar! 💕",
        "**{user}** dá um beijinho em **{alvo}**! 😘")

@bot.tree.command(name="rp_chora", description="😭 Chorar em RP")
async def rp_chora(interaction: discord.Interaction, motivo: str = ""):
    gif = random.choice(GIFS_RP["choro"])
    
    descricao = f"**{interaction.user.mention}** está chorando"
    if motivo:
        descricao += f" por: *{motivo}*"
    descricao += " 😭"
    
    embed = discord.Embed(title="😭 CHORANDO...", description=descricao, color=discord.Color.blue())
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_ri", description="😂 Rir em RP")
async def rp_ri(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "riso", "😂 HA HA HA!", membro,
        "**{user}** começa a rir sem parar! 🤣",
        "**{user}** ri muito de **{alvo}**! 😂")

@bot.tree.command(name="rp_dorme", description="😴 Dormir em RP")
async def rp_dorme(interaction: discord.Interaction):
    gif = random.choice(GIFS_RP["sono"])
    
    frases = [
        f"**{interaction.user.mention}** caiu no sono... zzZzZ 😴",
        f"**{interaction.user.mention}** fecha os olhos e adormece suavemente... 💤",
        f"**{interaction.user.mention}** boceja e lentamente vai ao mundo dos sonhos... 🌙",
    ]
    
    embed = discord.Embed(title="😴 DORMINDO...", description=random.choice(frases), color=discord.Color.dark_blue())
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_briga", description="💢 Brigar com alguém em RP")
async def rp_briga(interaction: discord.Interaction, membro: discord.Member, motivo: str = ""):
    gif = random.choice(GIFS_RP["briga"])
    
    descricao = f"**{interaction.user.mention}** e **{membro.mention}** estão brigando"
    if motivo:
        descricao += f" por: *{motivo}*"
    descricao += "! ⚔️"
    
    embed = discord.Embed(title="💢 BRIGA!", description=descricao, color=discord.Color.orange())
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_danca", description="💃 Dançar em RP")
async def rp_danca(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "dance", "💃 DANÇANDO!", membro,
        "**{user}** começa a dançar sozinho! 🎶",
        "**{user}** arrasta **{alvo}** para a pista de dança! 🎵")

@bot.tree.command(name="rp_envergonha", description="😳 Ficar envergonhado em RP")
async def rp_envergonha(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "envergonhado", "😳 QUE VERGONHA!", membro,
        "**{user}** fica vermelho de vergonha... 🍅",
        "**{user}** fica todo envergonhado por causa de **{alvo}**! 😳")

@bot.tree.command(name="rp_mimos", description="🥰 Dar mimos em RP")
async def rp_mimos(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "mimos", "🥰 MIMOS!", membro,
        "**{user}** está cheio de carinho pra dar! 💗",
        "**{user}** enche **{alvo}** de mimos e carinhos! 🥰")

@bot.tree.command(name="rp_raiva", description="😡 Ficar com raiva em RP")
async def rp_raiva(interaction: discord.Interaction, membro: Optional[discord.Member] = None, motivo: str = ""):
    gif = random.choice(GIFS_RP["raiva"])
    
    if membro and membro != interaction.user:
        descricao = f"**{interaction.user.mention}** está com muita raiva de **{membro.mention}**"
        if motivo:
            descricao += f" por: *{motivo}*"
        descricao += "! 😤"
    else:
        descricao = f"**{interaction.user.mention}** está FURIOSA(o)! 😡"
        if motivo:
            descricao += f"\nMotivo: *{motivo}*"
    
    embed = discord.Embed(title="😡 RAIVA!", description=descricao, color=discord.Color.dark_red())
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_susto", description="😱 Levar susto em RP")
async def rp_susto(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    gif = random.choice(GIFS_RP["susto"])
    
    if membro and membro != interaction.user:
        descricao = f"**{membro.mention}** assustou **{interaction.user.mention}**! 👻"
    else:
        descricao = f"**{interaction.user.mention}** levou um susto enorme! 😱"
    
    embed = discord.Embed(title="😱 SUSTO!", description=descricao, color=discord.Color.dark_gray())
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_comemora", description="🎉 Comemorar em RP")
async def rp_comemora(interaction: discord.Interaction, motivo: str = "", membro: Optional[discord.Member] = None):
    gif = random.choice(GIFS_RP["comemoracao"])
    
    if membro and membro != interaction.user:
        descricao = f"**{interaction.user.mention}** comemora com **{membro.mention}**"
    else:
        descricao = f"**{interaction.user.mention}** está celebrando"
    
    if motivo:
        descricao += f": *{motivo}*"
    descricao += "! 🎊"
    
    embed = discord.Embed(title="🎉 COMEMORANDO!", description=descricao, color=discord.Color.gold())
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_tristeza", description="💔 Demonstrar tristeza em RP")
async def rp_tristeza(interaction: discord.Interaction, motivo: str = ""):
    gif = random.choice(GIFS_RP["tristeza"])
    
    frases = [
        f"**{interaction.user.mention}** olha pro horizonte com os olhos marejados...",
        f"**{interaction.user.mention}** suspira fundo e deixa uma lágrima rolar...",
        f"**{interaction.user.mention}** está com o coração pesado...",
    ]
    
    descricao = random.choice(frases)
    if motivo:
        descricao += f"\n💭 *\"{motivo}\"*"
    
    embed = discord.Embed(title="💔 TRISTEZA...", description=descricao, color=discord.Color.dark_blue())
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_curiosidade", description="🔍 Ficar curioso em RP")
async def rp_curiosidade(interaction: discord.Interaction, membro: Optional[discord.Member] = None, sobre: str = ""):
    gif = random.choice(GIFS_RP["curiosidade"])
    
    if membro and membro != interaction.user:
        descricao = f"**{interaction.user.mention}** fica olhando pra **{membro.mention}** com curiosidade"
    else:
        descricao = f"**{interaction.user.mention}** fica olhando com curiosidade"
    
    if sobre:
        descricao += f" sobre *{sobre}*"
    descricao += "... 🤔"
    
    embed = discord.Embed(title="🔍 CURIOSO!", description=descricao, color=discord.Color.from_str("#87CEEB"))
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_acao", description="✨ Fazer uma ação personalizada em RP")
async def rp_acao_cmd(interaction: discord.Interaction, acao: str, membro: Optional[discord.Member] = None):
    """Permite ações personalizadas de RP em itálico, estilo livro"""
    if membro and membro != interaction.user:
        descricao = f"*{interaction.user.display_name} {acao} {membro.display_name}*"
    else:
        descricao = f"*{interaction.user.display_name} {acao}*"
    
    embed = discord.Embed(
        description=descricao,
        color=discord.Color.from_str("#DDA0DD")
    )
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    embed.timestamp = datetime.now(BR_TZ)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_fala", description="💬 Falar como seu personagem em RP")
async def rp_fala(interaction: discord.Interaction, texto: str, personagem: str = ""):
    nome = personagem if personagem else interaction.user.display_name
    
    embed = discord.Embed(
        description=f'**\u201c{texto}\u201d**',
        color=discord.Color.from_str("#98FB98")
    )
    embed.set_author(name=f"💬 {nome}", icon_url=interaction.user.display_avatar.url)
    embed.timestamp = datetime.now(BR_TZ)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_ficha", description="📋 Criar ou ver ficha de personagem de RP")
async def rp_ficha(interaction: discord.Interaction, 
                   nome: str = None, 
                   idade: str = None,
                   personalidade: str = None,
                   historia: str = None):
    user_id = str(interaction.user.id)
    
    # Se nenhum parâmetro foi passado, mostra a ficha atual
    if not any([nome, idade, personalidade, historia]):
        if user_id not in bot.rp_fichas:
            await interaction.response.send_message(
                "📋 Você ainda não tem uma ficha de RP!\nUse `/rp_ficha nome:... idade:... personalidade:... historia:...` para criar!",
                ephemeral=True
            )
            return
        
        ficha = bot.rp_fichas[user_id]
        embed = discord.Embed(
            title=f"📋 FICHA DE {ficha.get('nome', interaction.user.display_name).upper()}",
            color=discord.Color.from_str("#DDA0DD")
        )
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        
        if ficha.get('nome'):
            embed.add_field(name="🪪 Nome", value=ficha['nome'], inline=True)
        if ficha.get('idade'):
            embed.add_field(name="🎂 Idade", value=ficha['idade'], inline=True)
        if ficha.get('personalidade'):
            embed.add_field(name="💭 Personalidade", value=ficha['personalidade'], inline=False)
        if ficha.get('historia'):
            embed.add_field(name="📖 História", value=ficha['historia'][:500], inline=False)
        
        embed.set_footer(text=f"Ficha de {interaction.user.display_name}")
        await interaction.response.send_message(embed=embed)
        return
    
    # Criar/atualizar ficha
    if user_id not in bot.rp_fichas:
        bot.rp_fichas[user_id] = {}
    
    if nome:
        bot.rp_fichas[user_id]['nome'] = nome
    if idade:
        bot.rp_fichas[user_id]['idade'] = idade
    if personalidade:
        bot.rp_fichas[user_id]['personalidade'] = personalidade
    if historia:
        bot.rp_fichas[user_id]['historia'] = historia
    
    bot.save_rp()
    
    ficha = bot.rp_fichas[user_id]
    embed = discord.Embed(
        title=f"📋 FICHA ATUALIZADA!",
        description=f"Ficha de **{ficha.get('nome', interaction.user.display_name)}** salva com sucesso!",
        color=discord.Color.green()
    )
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    
    if ficha.get('nome'):
        embed.add_field(name="🪪 Nome", value=ficha['nome'], inline=True)
    if ficha.get('idade'):
        embed.add_field(name="🎂 Idade", value=ficha['idade'], inline=True)
    if ficha.get('personalidade'):
        embed.add_field(name="💭 Personalidade", value=ficha['personalidade'], inline=False)
    if ficha.get('historia'):
        embed.add_field(name="📖 História", value=ficha['historia'][:500], inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rp_ver_ficha", description="👁️ Ver ficha de RP de outro membro")
async def rp_ver_ficha(interaction: discord.Interaction, membro: discord.Member):
    user_id = str(membro.id)
    
    if user_id not in bot.rp_fichas or not bot.rp_fichas[user_id]:
        await interaction.response.send_message(f"❌ **{membro.display_name}** ainda não tem ficha de RP!", ephemeral=True)
        return
    
    ficha = bot.rp_fichas[user_id]
    embed = discord.Embed(
        title=f"📋 FICHA DE {ficha.get('nome', membro.display_name).upper()}",
        color=discord.Color.from_str("#DDA0DD")
    )
    embed.set_thumbnail(url=membro.display_avatar.url)
    
    if ficha.get('nome'):
        embed.add_field(name="🪪 Nome", value=ficha['nome'], inline=True)
    if ficha.get('idade'):
        embed.add_field(name="🎂 Idade", value=ficha['idade'], inline=True)
    if ficha.get('personalidade'):
        embed.add_field(name="💭 Personalidade", value=ficha['personalidade'], inline=False)
    if ficha.get('historia'):
        embed.add_field(name="📖 História", value=ficha['historia'][:500], inline=False)
    
    embed.set_footer(text=f"Ficha de {membro.display_name}")
    await interaction.response.send_message(embed=embed)

# ==================== SISTEMA DE SHIP ====================

@bot.tree.command(name="ship", description="💖 Calcula o amor entre duas pessoas")
async def ship(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    base = random.randint(40, 90)
    
    cargos_comuns = set(pessoa1.roles) & set(pessoa2.roles)
    if len(cargos_comuns) > 1:
        base += len(cargos_comuns) * 2
    
    if pessoa1.name[0].lower() == pessoa2.name[0].lower():
        base += 2
    
    porcentagem = max(0, min(100, base))
    if random.random() < 0.01:
        porcentagem = 100
    
    nome_casal = pessoa1.display_name[:len(pessoa1.display_name)//2] + pessoa2.display_name[len(pessoa2.display_name)//2:]
    barras = "█" * (porcentagem // 10) + "░" * (10 - (porcentagem // 10))
    
    if porcentagem < 20:
        cor = discord.Color.dark_gray(); mensagem = "💔 Nem amigos serão..."
    elif porcentagem < 40:
        cor = discord.Color.red(); mensagem = "❤️‍🩹 Só amizade"
    elif porcentagem < 60:
        cor = discord.Color.orange(); mensagem = "💛 Tem potencial"
    elif porcentagem < 70:
        cor = discord.Color.gold(); mensagem = "💚 Interessante"
    elif porcentagem < 80:
        cor = discord.Color.green(); mensagem = "💙 Ótima combinação"
    elif porcentagem < 90:
        cor = discord.Color.teal(); mensagem = "💜 Quase perfeitos"
    elif porcentagem < 100:
        cor = discord.Color.purple(); mensagem = "💝 Perfeitos"
    else:
        cor = discord.Color.from_str("#FF69B4"); mensagem = "✨ ALMAS GÊMEAS! ✨"
    
    embed = discord.Embed(title="💖 Teste de Amor", description=f"{pessoa1.mention} 💘 {pessoa2.mention}", color=cor)
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
        "pessoa1": str(pessoa1.id), "pessoa2": str(pessoa2.id),
        "likes": 0, "criado_por": str(interaction.user.id),
        "data": datetime.now(BR_TZ).isoformat()
    }
    bot.save_data()
    
    embed = discord.Embed(title="💘 NOVO SHIP!", description=f"{pessoa1.mention} 💕 {pessoa2.mention}", color=discord.Color.from_str("#FF69B4"))
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
    
    embed = discord.Embed(title=f"ℹ️ {pessoa1.display_name} x {pessoa2.display_name}", color=discord.Color.blue())
    embed.add_field(name="👍 Likes", value=data["likes"], inline=True)
    embed.add_field(name="👤 Criador", value=criador.mention if criador else "Desconhecido", inline=True)
    embed.add_field(name="📅 Data", value=datetime.fromisoformat(data["data"]).replace(tzinfo=BR_TZ).strftime("%d/%m/%Y"), inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="meusships", description="📋 Seus ships criados")
async def meusships(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    ships = [sid for sid, d in bot.ship_data.items() if str(d["criado_por"]) == user_id]
    
    if not ships:
        await interaction.response.send_message("❌ Você não criou nenhum ship!")
        return
    
    embed = discord.Embed(title=f"📋 Ships de {interaction.user.display_name}", color=discord.Color.blue())
    for ship_id in ships[:10]:
        data = bot.ship_data[ship_id]
        p1 = interaction.guild.get_member(int(data["pessoa1"]))
        p2 = interaction.guild.get_member(int(data["pessoa2"]))
        if p1 and p2:
            embed.add_field(name=f"{p1.display_name} x {p2.display_name}", value=f"👍 {data['likes']} likes", inline=False)
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
            embed.add_field(name=f"{medalha} {p1.display_name} x {p2.display_name}", value=f"👍 {data['likes']} likes", inline=False)
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
    
    embed = discord.Embed(title="📜 Ships do Servidor", description=f"Total: {len(ships)}", color=discord.Color.blue())
    for p1, p2, likes in ships[:15]:
        embed.add_field(name=f"{p1.display_name} 💘 {p2.display_name}", value=f"👍 {likes} likes", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="calcular_amor", description="🔮 Cálculo detalhado de compatibilidade")
async def calcular_amor(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    categorias = {
        "Amizade": random.randint(0, 100), "Paixão": random.randint(0, 100),
        "Confiança": random.randint(0, 100), "Comunicação": random.randint(0, 100),
        "Futuro": random.randint(0, 100)
    }
    media = sum(categorias.values()) // len(categorias)
    embed = discord.Embed(title="🔮 Análise Detalhada", description=f"{pessoa1.mention} ❤️ {pessoa2.mention}", color=discord.Color.purple())
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
    
    embed = discord.Embed(title="💍 PEDIDO DE CASAMENTO!", description=f"{interaction.user.mention} pediu {pessoa.mention} em casamento!", color=discord.Color.from_str("#FF69B4"))
    embed.add_field(name="💝 O que fazer?", value=f"{pessoa.mention}\n`/aceitar @{interaction.user.name}` para aceitar\n`/recusar @{interaction.user.name}` para recusar", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="aceitar", description="💞 Aceitar pedido de casamento")
async def aceitar(interaction: discord.Interaction, pessoa: discord.Member):
    user_id = str(interaction.user.id)
    pessoa_id = str(pessoa.id)
    
    marriage_id = f"{pessoa_id}-{user_id}-{datetime.now(BR_TZ).timestamp()}"
    bot.marriage_data[marriage_id] = {
        "pessoa1": pessoa_id, "pessoa2": user_id,
        "data_casamento": datetime.now(BR_TZ).isoformat(),
        "aniversarios_comemorados": 0, "luademel": True, "presentes": []
    }
    
    for uid in [pessoa_id, user_id]:
        if uid not in bot.user_balances:
            bot.user_balances[uid] = 0
        bot.user_balances[uid] += 1000
    
    bot.save_data()
    
    embed = discord.Embed(title="💞 CASAMENTO REALIZADO!", description=f"🎉 {pessoa.mention} e {interaction.user.mention} estão casados!", color=discord.Color.gold())
    embed.add_field(name="💰 Bônus", value="Ambos ganharam 1000 moedas!", inline=False)
    embed.add_field(name="🌙 Lua de Mel", value="Ativa por 7 dias!", inline=False)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="recusar", description="💔 Recusar pedido de casamento")
async def recusar(interaction: discord.Interaction, pessoa: discord.Member):
    embed = discord.Embed(title="💔 PEDIDO RECUSADO", description=f"{interaction.user.mention} recusou {pessoa.mention}...", color=discord.Color.dark_gray())
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
        if datetime.now(BR_TZ) - bot.divorce_cooldowns[user_id] < timedelta(days=7):
            await interaction.response.send_message("❌ Aguarde 7 dias!")
            return
    
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 5000:
        await interaction.response.send_message("❌ Precisa de 5000 moedas!")
        return
    
    bot.user_balances[user_id] -= 5000
    bot.divorce_cooldowns[user_id] = datetime.now(BR_TZ)
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
    
    data_casamento = datetime.fromisoformat(casamento_atual["data_casamento"]).replace(tzinfo=BR_TZ)
    tempo_casado = datetime.now(BR_TZ) - data_casamento
    dias = tempo_casado.days
    horas = tempo_casado.seconds // 3600
    
    embed = discord.Embed(title="💒 Casamento", description=f"{interaction.user.mention} ❤️ {conjuge.mention}", color=discord.Color.from_str("#FF69B4"))
    embed.add_field(name="📅 Casados há", value=f"**{dias} dias** e **{horas} horas**", inline=True)
    embed.add_field(name="💝 Aniversários", value=f"**{casamento_atual['aniversarios_comemorados']}**", inline=True)
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
    
    data_casamento = datetime.fromisoformat(casamento_atual["data_casamento"]).replace(tzinfo=BR_TZ)
    hoje = datetime.now(BR_TZ)
    
    if hoje.month == data_casamento.month and hoje.day == data_casamento.day:
        anos = hoje.year - data_casamento.year
        if anos > casamento_atual["aniversarios_comemorados"]:
            casamento_atual["aniversarios_comemorados"] = anos
            conjuge_id = casamento_atual["pessoa2"] if casamento_atual["pessoa1"] == user_id else casamento_atual["pessoa1"]
            for uid in [user_id, conjuge_id]:
                if uid not in bot.user_balances:
                    bot.user_balances[uid] = 0
                bot.user_balances[uid] += 500 * anos
            bot.save_data()
            
            embed = discord.Embed(title="🎂 FELIZ ANIVERSÁRIO!", description=f"**{anos}** anos juntos!", color=discord.Color.gold())
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
    
    data_casamento = datetime.fromisoformat(casamento_atual["data_casamento"]).replace(tzinfo=BR_TZ)
    if datetime.now(BR_TZ) - data_casamento > timedelta(days=7):
        casamento_atual["luademel"] = False
        bot.save_data()
        await interaction.response.send_message("❌ Lua de mel acabou!")
        return
    
    conjuge_id = casamento_atual["pessoa2"] if casamento_atual["pessoa1"] == user_id else casamento_atual["pessoa1"]
    dias_restantes = 7 - (datetime.now(BR_TZ) - data_casamento).days
    
    embed = discord.Embed(title="🌙 LUA DE MEL", description=f"{interaction.user.mention} ❤️ <@{conjuge_id}>", color=discord.Color.from_str("#FF69B4"))
    embed.add_field(name="⏳ Dias restantes", value=f"**{dias_restantes}** dias", inline=False)
    await interaction.response.send_message(embed=embed)

# ==================== PRESENTES E SIGNOS ====================

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
        "🌹 Rosa": 50, "🍫 Chocolate": 75, "🧸 Ursinho": 100, "💍 Anel": 500,
        "💐 Buquê": 150, "🎂 Bolo": 200, "✉️ Carta": 30, "🎫 Cinema": 120,
        "🍷 Jantar": 300, "💎 Colar": 800
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
        await interaction.response.send_message("❌ Use /loja_presentes para ver os itens disponíveis!")
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
        "presente": presente, "de": interaction.user.name,
        "data": datetime.now(BR_TZ).isoformat()
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
        data = datetime.fromisoformat(presente["data"]).replace(tzinfo=BR_TZ).strftime("%d/%m/%Y")
        embed.add_field(name=presente["presente"], value=f"De: {presente['de']} | {data}", inline=False)
    await interaction.response.send_message(embed=embed)

# ==================== SISTEMA DE ECONOMIA CORRIGIDO ====================

@bot.tree.command(name="daily", description="💰 Recompensa diária (com streak e bônus!)")
async def daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)
    hoje = agora.date()
    ontem = hoje - timedelta(days=1)

    if user_id not in bot.user_balances:
        bot.user_balances[user_id] = 0

    # Verifica cooldown
    if user_id in bot.daily_cooldowns:
        ultimo_isoformat = bot.daily_cooldowns[user_id]
        ultimo_data = datetime.fromisoformat(ultimo_isoformat)
        ultimo_date = ultimo_data.date()

        if ultimo_date == hoje:
            # Calcula tempo restante para a meia-noite
            proximo = datetime(agora.year, agora.month, agora.day, 0, 0, 0, tzinfo=BR_TZ) + timedelta(days=1)
            restante = proximo - agora
            horas = int(restante.total_seconds() // 3600)
            minutos = int((restante.total_seconds() % 3600) // 60)
            
            saldo_atual = bot.user_balances.get(user_id, 0)
            
            embed = discord.Embed(
                title="⏰ Daily já coletado!",
                description=f"Você já pegou sua recompensa hoje!\n\n⏰ Próximo daily em **{horas}h {minutos}m**",
                color=discord.Color.orange()
            )
            embed.add_field(name="💰 Seu saldo atual", value=f"**{saldo_atual} moedas**", inline=True)
            embed.set_footer(text="Volte amanhã para continuar o streak! 🔥")
            await interaction.response.send_message(embed=embed, ephemeral=True)
            return

    # Calcula streak
    streak_key = f"{user_id}_streak"
    streak_count = 0
    
    if user_id in bot.daily_cooldowns:
        ultimo_date = datetime.fromisoformat(bot.daily_cooldowns[user_id]).date()
        if ultimo_date == ontem:
            # Streak continua!
            streak_data = bot.daily_cooldowns.get(streak_key, "0")
            try:
                streak_count = int(streak_data) + 1
            except:
                streak_count = 1
        else:
            # Quebrou o streak
            streak_count = 1
    else:
        streak_count = 1

    # Recompensas base + streak
    valor_base = random.randint(300, 600)
    bonus_streak = min(streak_count * 30, 500)  # Máximo 500 de bônus de streak
    
    # Chance de bônus especial
    bonus_especial = 0
    msg_bonus = ""
    roll = random.random()
    if roll < 0.03:
        bonus_especial = 1000
        msg_bonus = "🎊 **JACKPOT DO DIA!** +1000 moedas extras!"
    elif roll < 0.15:
        bonus_especial = 300
        msg_bonus = "✨ **Dia de sorte!** +300 moedas extras!"
    elif roll < 0.35:
        bonus_especial = 100
        msg_bonus = "🌟 **Bônus surpresa!** +100 moedas extras!"

    total = valor_base + bonus_streak + bonus_especial
    bot.user_balances[user_id] += total
    bot.daily_cooldowns[user_id] = agora.isoformat()
    bot.daily_cooldowns[streak_key] = str(streak_count)
    bot.save_data()

    saldo_novo = bot.user_balances[user_id]

    # Emoji do streak
    if streak_count >= 30:
        emoji_streak = "🔥🔥🔥"
        titulo_streak = "STREAK LENDÁRIO!"
    elif streak_count >= 14:
        emoji_streak = "🔥🔥"
        titulo_streak = "Streak incrível!"
    elif streak_count >= 7:
        emoji_streak = "🔥"
        titulo_streak = "Streak de uma semana!"
    elif streak_count >= 3:
        emoji_streak = "⚡"
        titulo_streak = "Streak iniciando!"
    else:
        emoji_streak = "✨"
        titulo_streak = "Bem-vindo!"

    embed = discord.Embed(
        title=f"💰 DAILY COLETADO! {emoji_streak}",
        description=f"**{interaction.user.display_name}**, sua recompensa diária chegou!",
        color=discord.Color.gold()
    )
    embed.add_field(name="💵 Moedas base", value=f"+**{valor_base}**", inline=True)
    embed.add_field(name=f"🔥 Bônus de streak ({streak_count} dias)", value=f"+**{bonus_streak}**", inline=True)
    if bonus_especial:
        embed.add_field(name="🎁 Bônus especial", value=f"+**{bonus_especial}**", inline=True)
    embed.add_field(name="💰 Total ganho hoje", value=f"**+{total} moedas**", inline=False)
    embed.add_field(name="🏦 Saldo atual", value=f"**{saldo_novo} moedas**", inline=True)
    embed.add_field(name=f"{emoji_streak} {titulo_streak}", value=f"**{streak_count} dias** seguidos!", inline=True)
    if msg_bonus:
        embed.add_field(name="🎊 BÔNUS SURPRESA!", value=msg_bonus, inline=False)
    embed.set_thumbnail(url=interaction.user.display_avatar.url)
    embed.set_footer(text="🔥 Colete todo dia para aumentar o streak e ganhar mais!")
    embed.timestamp = agora

    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="saldo", description="💰 Ver saldo")
async def saldo(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    if membro is None:
        membro = interaction.user
    user_id = str(membro.id)
    saldo_atual = bot.user_balances.get(user_id, 0)
    
    # Streak info
    streak_key = f"{user_id}_streak"
    streak = int(bot.daily_cooldowns.get(streak_key, 0)) if streak_key in bot.daily_cooldowns else 0
    
    embed = discord.Embed(title=f"💰 Carteira de {membro.display_name}", color=discord.Color.gold())
    embed.set_thumbnail(url=membro.display_avatar.url)
    embed.add_field(name="💵 Saldo", value=f"**{saldo_atual} moedas**", inline=True)
    if streak > 0:
        embed.add_field(name="🔥 Streak do Daily", value=f"**{streak} dias**", inline=True)
    await interaction.response.send_message(embed=embed)

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
    
    await interaction.response.send_message(f"💸 **{valor} moedas** transferidas para {membro.mention}!")

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
        if resultado[0] == "7️⃣": premio = 1000
        elif resultado[0] == "💎": premio = 500
        else: premio = 200
    elif resultado[0] == resultado[1] or resultado[1] == resultado[2]:
        premio = 75
    
    if premio > 0:
        bot.user_balances[user_id] += premio
    bot.save_data()
    
    texto = f"` {resultado[0]} | {resultado[1]} | {resultado[2]} `\n"
    texto += f"🏆 Ganhou {premio} moedas!" if premio > 0 else "😢 Não foi dessa vez!"
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
    
    if escolha.lower() == bot_choice: resultado = "Empate!"; cor = discord.Color.blue()
    elif (escolha.lower() == "pedra" and bot_choice == "tesoura") or \
         (escolha.lower() == "papel" and bot_choice == "pedra") or \
         (escolha.lower() == "tesoura" and bot_choice == "papel"):
        resultado = "Você ganhou!"; cor = discord.Color.green()
    else:
        resultado = "Você perdeu!"; cor = discord.Color.red()
    
    emojis = {"pedra": "🪨", "papel": "📄", "tesoura": "✂️"}
    embed = discord.Embed(title="✂️ PPT", description=f"Você: {emojis[escolha.lower()]}\nBot: {emojis[bot_choice]}", color=cor)
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
    embed.add_field(name="Entrou em", value=membro.joined_at.strftime("%d/%m/%Y") if membro.joined_at else "N/A", inline=True)
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
        if operador == "+": resultado = num1 + num2
        elif operador == "-": resultado = num1 - num2
        elif operador in ["*", "x"]: resultado = num1 * num2
        elif operador == "/":
            if num2 == 0:
                await interaction.response.send_message("❌ Divisão por zero!")
                return
            resultado = num1 / num2
        elif operador == "^": resultado = num1 ** num2
        else:
            await interaction.response.send_message("❌ Operador inválido!")
            return
        await interaction.response.send_message(f"🧮 Resultado: `{num1} {operador} {num2} = {resultado}`")
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}")

@bot.tree.command(name="ola_mundo", description="👋 Mensagem de boas vindas")
async def ola_mundo(interaction: discord.Interaction):
    await interaction.response.send_message(f"Olá {interaction.user.mention}! Bem-vindo ao bot Fort! 🎉")

# ==================== DIVERSÃO ====================

@bot.tree.command(name="8ball", description="🎱 Pergunte ao destino")
async def eight_ball(interaction: discord.Interaction, pergunta: str):
    respostas = [
        "Sim!", "Não!", "Talvez...", "Com certeza!", "Nem pensar!",
        "Os deuses dizem que sim!", "Melhor não dizer agora.", "Pode confiar!",
        "As estrelas dizem que sim! ✨", "Hmm, não parece uma boa ideia...",
        "Com toda certeza!", "Definitivamente não!", "Pergunte de novo mais tarde..."
    ]
    embed = discord.Embed(title="🎱 8Ball", description=f"**Pergunta:** {pergunta}\n**Resposta:** {random.choice(respostas)}", color=discord.Color.purple())
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="piada", description="😂 Piada aleatória")
async def piada(interaction: discord.Interaction):
    piadas = [
        "Por que o computador foi preso? Porque executou um comando!",
        "O que o zero disse para o oito? Belo cinto!",
        "Por que os elétrons nunca pagam contas? Porque estão sempre em débito!",
        "O que o pato disse para a pata? Vem quá!",
        "Qual o cúmulo da rapidez? Fechar o zíper com uma bala!",
        "Por que o coelho de Páscoa 🐰 foi ao psicólogo? Porque tinha muita casca de ovo na cabeça!",
        "O que o ovo disse pro chocolate? Você me derrete! 🍫"
    ]
    await interaction.response.send_message(f"😂 {random.choice(piadas)}")

@bot.tree.command(name="conselho", description="💡 Conselho aleatório")
async def conselho(interaction: discord.Interaction):
    conselhos = [
        "Beba água! 💧", "Durma bem! 😴", "Seja gentil! 🧘",
        "Aprenda algo novo! 📚", "Sorria! 😊", "Ajude alguém! 🤝",
        "Não esqueça de comer chocolate de Páscoa! 🍫",
        "Se você está lendo isso, você é incrível! ✨"
    ]
    await interaction.response.send_message(f"💡 {random.choice(conselhos)}")

@bot.tree.command(name="fato", description="🔍 Fato curioso")
async def fato(interaction: discord.Interaction):
    fatos = [
        "Flamingos nascem cinzas!",
        "O coração da baleia azul é enorme!",
        "Ursos polares têm pele preta!",
        "Mel nunca estraga!",
        "Bananas são levemente radioativas!",
        "Polvos têm três corações!",
        "🐣 O coelho de Páscoa veio de tradições pagãs de fertilidade!",
        "🥚 O ovo de chocolate mais pesado do mundo tinha mais de 4 toneladas!",
        "🐇 Coelhos são crepusculares — mais ativos no amanhecer e entardecer!"
    ]
    await interaction.response.send_message(f"🔍 {random.choice(fatos)}")

@bot.tree.command(name="baitola", description="🏳️‍🌈 Mensagem especial")
async def baitola(interaction: discord.Interaction, membro: discord.Member):
    frases = [
        f"{membro.mention} é o maior baitola do servidor! 🏳️‍🌈",
        f"Parabéns {membro.mention}, você é o baitola master! 🏆"
    ]
    await interaction.response.send_message(random.choice(frases))

# ==================== COMANDOS COM GIFS ====================



@bot.tree.command(name="abraco_gif", description="🤗 Abraçar alguém com GIF")
async def abraco_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se abraçar! 🥲")
        return
    gif = random.choice(gifs_abraco)
    embed = discord.Embed(title="🤗 ABRAÇO!", description=f"{interaction.user.mention} abraçou {membro.mention}!", color=discord.Color.from_str("#FF69B4"))
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="beijo_gif", description="💋 Beijar alguém com GIF")
async def beijo_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se beijar! 🥲")
        return
    gif = random.choice(gifs_beijo)
    embed = discord.Embed(title="💋 BEIJO!", description=f"{interaction.user.mention} beijou {membro.mention}!", color=discord.Color.red())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="carinho_gif", description="🥰 Fazer carinho com GIF")
async def carinho_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode fazer carinho em si mesmo! 🥲")
        return
    gif = random.choice(gifs_carinho)
    embed = discord.Embed(title="🥰 CARINHO!", description=f"{interaction.user.mention} fez carinho em {membro.mention}!", color=discord.Color.purple())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="cafune_gif", description="😴 Fazer cafuné com GIF")
async def cafune_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode fazer cafuné em si mesmo! 🥲")
        return
    gif = random.choice(gifs_carinho)
    embed = discord.Embed(title="😴 CAFUNÉ!", description=f"{interaction.user.mention} fez cafuné em {membro.mention}!", color=discord.Color.teal())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="tapa", description="👋 Dar um tapa em alguém com GIF")
async def tapa(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se bater! 🥲")
        return
    gif = random.choice(gifs_tapa)
    embed = discord.Embed(title="👋 TAPA!", description=f"{interaction.user.mention} deu um tapa em {membro.mention}!", color=discord.Color.orange())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="festa", description="🎉 Fazer uma festa com GIF")
async def festa(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    gif = random.choice(gifs_festa)
    if membro:
        descricao = f"{interaction.user.mention} fez uma festa com {membro.mention}!"
    else:
        descricao = f"{interaction.user.mention} fez uma festa!"
    embed = discord.Embed(title="🎉 FESTA!", description=descricao, color=discord.Color.gold())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="matar", description="💀 Matar alguém (brincadeira) com GIF")
async def matar(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se matar! 😱")
        return
    gif = random.choice(gifs_matar)
    embed = discord.Embed(title="💀 MORTE!", description=f"{interaction.user.mention} matou {membro.mention}! (brincadeira 😅)", color=discord.Color.dark_red())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="chifre", description="🦌 Dar chifre em alguém")
async def chifre(interaction: discord.Interaction, membro: discord.Member):
    embed = discord.Embed(title="🦌 CHIFRE!", description=f"{interaction.user.mention} deu chifre em {membro.mention}!", color=discord.Color.green())
    embed.set_image(url="https://media.giphy.com/media/3o7TKsQ8CAGJ6A9p20/giphy.gif")
    await interaction.response.send_message(embed=embed)

# ==================== OUTRAS FUNÇÕES ====================

@bot.tree.command(name="moeda", description="🪙 Jogar uma moeda")
async def moeda(interaction: discord.Interaction):
    resultado = random.choice(["CARA", "COROA"])
    await interaction.response.send_message(f"🪙 A moeda caiu: **{resultado}**!")

@bot.tree.command(name="rps", description="🗿 Pedra, Papel ou Tesoura contra o bot")
async def rps(interaction: discord.Interaction, escolha: str):
    escolhas = ["pedra", "papel", "tesoura"]
    if escolha.lower() not in escolhas:
        await interaction.response.send_message("❌ Escolha: pedra, papel ou tesoura!")
        return
    
    bot_choice = random.choice(escolhas)
    if escolha.lower() == bot_choice: resultado = "Empate!"; cor = discord.Color.blue()
    elif (escolha.lower() == "pedra" and bot_choice == "tesoura") or \
         (escolha.lower() == "papel" and bot_choice == "pedra") or \
         (escolha.lower() == "tesoura" and bot_choice == "papel"):
        resultado = "Você ganhou!"; cor = discord.Color.green()
    else:
        resultado = "Você perdeu!"; cor = discord.Color.red()
    
    emojis = {"pedra": "🗿", "papel": "📄", "tesoura": "✂️"}
    embed = discord.Embed(title="🗿📄✂️ Jokenpo", description=f"Você: {emojis[escolha.lower()]}\nBot: {emojis[bot_choice]}", color=cor)
    embed.add_field(name="Resultado", value=resultado)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="dado_rpg", description="🎲 Rolar dados de RPG")
async def dado_rpg(interaction: discord.Interaction, quantidade: int = 1, faces: int = 20):
    if quantidade < 1 or quantidade > 10:
        await interaction.response.send_message("❌ Quantidade deve ser entre 1 e 10!")
        return
    if faces not in [4, 6, 8, 10, 12, 20, 100]:
        await interaction.response.send_message("❌ Faces válidas: 4, 6, 8, 10, 12, 20, 100")
        return
    
    resultados = [random.randint(1, faces) for _ in range(quantidade)]
    total = sum(resultados)
    embed = discord.Embed(title="🎲 Dados de RPG", description=f"**{quantidade}d{faces}**", color=discord.Color.purple())
    embed.add_field(name="Resultados", value=" + ".join(str(r) for r in resultados), inline=False)
    embed.add_field(name="Total", value=f"**{total}**", inline=True)
    if quantidade > 1:
        embed.add_field(name="Média", value=f"{total/quantidade:.1f}", inline=True)
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="sortear", description="🎁 Sortear um membro do servidor")
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

# ==================== COMANDO DE AJUDA COMPLETO ====================

@bot.tree.command(name="ajuda", description="📚 Todos os comandos")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Comandos do Bot Fort",
        description="**Sistema Completo - 90+ COMANDOS!** 🐣",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🐣 **PÁSCOA** (NOVIDADE!)",
        value="`/pascoa_daily` - Daily temático\n"
              "`/pascoa_quiz` - Quiz de Páscoa\n"
              "`/pascoa_caca` - Caçar o coelho\n"
              "`/pascoa_ovo` - Encontrar ovos\n"
              "`/pascoa_corrida` - Corrida de coelhos\n"
              "`/pascoa_slot` - Caça-níqueis temático\n"
              "`/pascoa_chocolate` - Presentear\n"
              "`/pascoa_ranking` - Ranking\n"
              "`/pascoa_pontos` - Ver pontos\n"
              "`/pascoa_info` - Info do sistema",
        inline=False
    )
    
    embed.add_field(
        name="🎭 **RP** (NOVIDADE!)",
        value="`/rp_abraco` - Abraçar\n"
              "`/rp_beijo` - Beijar\n"
              "`/rp_chora` - Chorar\n"
              "`/rp_ri` - Rir\n"
              "`/rp_dorme` - Dormir\n"
              "`/rp_briga` - Brigar\n"
              "`/rp_danca` - Dançar\n"
              "`/rp_envergonha` - Envergonhar\n"
              "`/rp_mimos` - Dar mimos\n"
              "`/rp_raiva` - Raiva\n"
              "`/rp_susto` - Susto\n"
              "`/rp_comemora` - Comemorar\n"
              "`/rp_tristeza` - Tristeza\n"
              "`/rp_curiosidade` - Curiosidade\n"
              "`/rp_acao` - Ação livre\n"
              "`/rp_fala` - Falar em personagem\n"
              "`/rp_ficha` - Criar ficha\n"
              "`/rp_ver_ficha` - Ver ficha",
        inline=False
    )
    
    embed.add_field(
        name="📢 **CHAMADAS**",
        value="`/chamada` - Criar chamada\n"
              "`/chamada_info` - Ver informações\n"
              "`/chamada_lista` - Lista completa\n"
              "`/chamada_cancelar` - Cancelar\n"
              "`/chamada_listar_ativas` - Listar ativas",
        inline=True
    )
    
    embed.add_field(
        name="📊 **ENQUETES**",
        value="`/enquete` - Criar enquete\n"
              "`/enquete_info` - Ver informações\n"
              "`/enquete_listar` - Listar\n"
              "`/enquete_gerenciar` - Gerenciar",
        inline=True
    )
    
    embed.add_field(
        name="💖 **SHIP**",
        value="`/ship` `/shippar` `/likeship`\n"
              "`/shipinfo` `/meusships`\n"
              "`/topship` `/shiplist`\n"
              "`/calcular_amor`",
        inline=True
    )
    
    embed.add_field(
        name="💒 **CASAMENTO**",
        value="`/pedir` `/aceitar` `/recusar`\n"
              "`/divorciar` `/casamento`\n"
              "`/presentear` `/aniversario`\n"
              "`/luademel`",
        inline=True
    )
    
    embed.add_field(
        name="💰 **ECONOMIA**",
        value="`/daily` - Daily (com streak! 🔥)\n"
              "`/saldo` `/transferir`\n"
              "`/slot` `/dado`\n"
              "`/cara_coroa` `/ppt`\n"
              "`/adivinha`",
        inline=True
    )
    
    embed.add_field(
        name="🎭 **GIFS**",
        value="`/abraco_gif` `/beijo_gif`\n"
              "`/carinho_gif` `/cafune_gif`\n"
              "`/tapa` `/festa`\n"
              "`/matar` `/chifre`",
        inline=True
    )
    
    embed.add_field(
        name="🎮 **JOGOS & DIVERSÃO**",
        value="`/moeda` `/rps` `/dado_rpg`\n"
              "`/sortear` `/8ball`\n"
              "`/piada` `/conselho` `/fato`\n"
              "`/calcular` `/userinfo`\n"
              "`/serverinfo` `/avatar` `/ping`",
        inline=True
    )
    
    embed.set_footer(text="🐣 Feliz Páscoa! | 90+ comandos no total!")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    embed.timestamp = datetime.now(BR_TZ)
    
    await interaction.response.send_message(embed=embed)

# ==================== INICIAR BOT ====================

async def main():
    print("🔵 INICIANDO FUNÇÃO MAIN")
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        print("❌ ERRO CRÍTICO: Token não encontrado!")
        return
    
    print(f"🔵 Token encontrado! Conectando...")
    print(f"⏰ Horário atual: {datetime.now(BR_TZ).strftime('%d/%m/%Y %H:%M:%S')}")
    
    try:
        async with bot:
            await bot.start(token)
    except Exception as e:
        print(f"❌ Erro: {e}")

def run_bot():
    print("🟢 INICIANDO BOT")
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
    print("🚀 FORT BOT - VERSÃO PÁSCOA + RP!")
    print("="*60)
    print("✅ Sistema de Páscoa com minigames e ranking!")
    print("✅ Sistema de RP completo com fichas de personagem!")
    print("✅ Daily corrigido com streak e cooldown certinho!")
    print("✅ Sistema de Ship, Casamento, Economia!")
    print("✅ Enquetes dinâmicas e Chamadas!")
    print("✅ 90+ COMANDOS NO TOTAL!")
    print("="*60)
    
    run_bot()
