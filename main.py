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
        "sistemas": 70
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
        
        # Remove voto anterior se existir
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
        
        # Atualiza o embed
        await self.atualizar_embed(interaction, enquete)
        
        # Responde com confirmação
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
        
        # Verifica permissão
        if str(interaction.user.id) != enquete["criador_id"] and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Apenas o criador ou administradores podem encerrar a enquete!", ephemeral=True)
            return
        
        # Encerra a enquete
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
        
        # Remove da lista de enquetes ativas
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
        
        # Processa as opções
        opcoes = [op.strip() for op in opcoes_raw.split("|") if op.strip()]
        
        if len(opcoes) < 2:
            await interaction.response.send_message("❌ Você precisa de pelo menos 2 opções!", ephemeral=True)
            return
        
        if len(opcoes) > 20:
            await interaction.response.send_message("❌ Máximo de 20 opções!", ephemeral=True)
            return
        
        # Cria a enquete
        enquete_id = f"{interaction.channel.id}-{int(datetime.now(BR_TZ).timestamp())}"
        
        expira_em = None
        if duracao > 0:
            expira_em = datetime.now(BR_TZ) + timedelta(hours=duracao)
        
        # Cria o embed
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
        
        # Salva os dados da enquete
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
        
        # Agenda encerramento automático se tiver duração
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
        
        # Verifica permissão
        if str(interaction.user.id) != enquete["criador_id"] and not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ Apenas o criador pode adicionar opções!", ephemeral=True)
            return
        
        if len(enquete["opcoes"]) >= 20:
            await interaction.response.send_message("❌ Máximo de 20 opções atingido!", ephemeral=True)
            return
        
        nova_opcao = self.nova_opcao.value.strip()
        novo_index = len(enquete["opcoes"])
        
        enquete["opcoes"].append(nova_opcao)
        enquete["votos"].append(0)
        
        bot.save_enquetes()
        
        # Recria a view com o novo botão
        await self.recriar_view(interaction, enquete)
        
        await interaction.response.send_message(f"✅ Opção **{nova_opcao}** adicionada!", ephemeral=True)
    
    async def recriar_view(self, interaction: discord.Interaction, enquete):
        try:
            canal = bot.get_channel(int(enquete["channel_id"]))
            if canal:
                msg = await canal.fetch_message(int(enquete["message_id"]))
                if msg:
                    nova_view = EnqueteView(self.enquete_id, enquete["opcoes"])
                    
                    # Atualiza o embed
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
            ('enquetes', self.enquetes)
        ]
        
        for tipo, dados in dados_para_salvar:
            c.execute('INSERT OR REPLACE INTO dados_json VALUES (?, ?)', 
                     (tipo, json.dumps(dados, ensure_ascii=False)))
        
        conn.commit()
        conn.close()
    
    def save_enquetes(self):
        """Salva apenas as enquetes no banco de dados"""
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        c.execute('INSERT OR REPLACE INTO dados_json VALUES (?, ?)', 
                 ('enquetes', json.dumps(self.enquetes, ensure_ascii=False)))
        conn.commit()
        conn.close()

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Comandos sincronizados!")
        
        # Recriar tasks para chamadas ativas ao reiniciar
        await self.restaurar_chamadas_ativas()
        
        # Restaurar enquetes ativas
        await self.restaurar_enquetes_ativas()

    async def restaurar_enquetes_ativas(self):
        """Restaura as enquetes ativas quando o bot reinicia"""
        agora = datetime.now(BR_TZ)
        enquetes_remover = []
        
        for enquete_id, enquete_data in self.enquetes.items():
            try:
                expira_em = enquete_data.get("expira_em")
                if expira_em:
                    expira = datetime.fromisoformat(expira_em).replace(tzinfo=BR_TZ)
                    
                    if expira <= agora:
                        print(f"⏰ Enquete {enquete_id} já expirou, removendo...")
                        enquetes_remover.append(enquete_id)
                    else:
                        print(f"🔄 Recriando task para enquete {enquete_id} - Expira em {expira.strftime('%d/%m/%Y %H:%M:%S')}")
                        task = asyncio.create_task(self.encerrar_enquete_automatico(enquete_id, expira))
                        self.enquete_tasks[enquete_id] = task
            except Exception as e:
                print(f"❌ Erro ao restaurar enquete {enquete_id}: {e}")
                enquetes_remover.append(enquete_id)
        
        # Remover enquetes expiradas
        for enquete_id in enquetes_remover:
            if enquete_id in self.enquetes:
                del self.enquetes[enquete_id]
        
        if enquetes_remover:
            self.save_enquetes()
            print(f"✅ {len(enquetes_remover)} enquetes expiradas removidas")

    async def encerrar_enquete_automatico(self, enquete_id: str, expira_em: datetime):
        """Encerra a enquete automaticamente após o tempo limite"""
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
            print(f"✅ Enquete {enquete_id} encerrada automaticamente!")
            
        except asyncio.CancelledError:
            print(f"⏹️ Task da enquete {enquete_id} foi cancelada")
        except Exception as e:
            print(f"❌ Erro ao encerrar enquete: {e}")

    async def restaurar_chamadas_ativas(self):
        """Restaura as tasks de chamadas ativas quando o bot reinicia"""
        agora = datetime.now(BR_TZ)
        calls_remover = []
        
        for call_id, call_data in self.call_data.items():
            try:
                expira_em = datetime.fromisoformat(call_data['expira_em']).replace(tzinfo=BR_TZ)
                
                if expira_em <= agora:
                    # Chamada já expirou
                    print(f"⏰ Chamada {call_id} já expirou, removendo...")
                    calls_remover.append(call_id)
                else:
                    # Chamada ainda ativa, recriar task
                    print(f"🔄 Recriando task para chamada {call_id} - Expira em {expira_em.strftime('%d/%m/%Y %H:%M:%S')} (Brasília)")
                    task = asyncio.create_task(encerrar_chamada_apos_tempo(call_id, expira_em))
                    self.active_tasks[call_id] = task
            except Exception as e:
                print(f"❌ Erro ao restaurar chamada {call_id}: {e}")
                calls_remover.append(call_id)
        
        # Remover chamadas expiradas
        for call_id in calls_remover:
            if call_id in self.call_data:
                del self.call_data[call_id]
            if call_id in self.call_participants:
                del self.call_participants[call_id]
        
        if calls_remover:
            self.save_data()
            print(f"✅ {len(calls_remover)} chamadas expiradas removidas")

    async def on_ready(self):
        print(f"✅ Bot {self.user} ligado com sucesso!")
        print(f"📊 Servidores: {len(self.guilds)}")
        print(f"👥 Usuários: {len(self.users)}")
        print(f"📢 Chamadas ativas: {len(self.call_data)}")
        print(f"📊 Enquetes ativas: {len(self.enquetes)}")
        print(f"💖 Sistema de Ship: ATIVO")
        print(f"💒 Sistema de Casamento: ATIVO")
        print(f"💰 Sistema de Economia: ATIVO")
        print(f"🎮 Sistema de Jogos: ATIVO")
        print(f"🎭 Comandos com GIF: ATIVO")
        print(f"📊 Sistema de Enquetes Dinâmicas: ATIVO")
        print(f"💾 Banco de Dados: SQLite")
        print(f"⏰ Fuso Horário: Brasília (UTC-3)")
        print(f"⏰ Horário atual: {datetime.now(BR_TZ).strftime('%d/%m/%Y %H:%M:%S')}")
        await self.change_presence(activity=discord.Game(name="📢 Use /enquete | 70+ comandos!"))

bot = Fort()

# ==================== SISTEMA DE CHAMADAS CORRIGIDO COM FUSO BRASIL ====================

def calcular_tempo_expiracao(horas_limite: Optional[int] = None):
    """
    Calcula o tempo de expiração da chamada no HORÁRIO DE BRASÍLIA:
    - Se horas_limite for fornecido: expira após X horas
    - Se NÃO for fornecido: expira SEMPRE hoje às 23:59:59 (MEIA-NOITE)
    """
    agora = datetime.now(BR_TZ)
    
    print(f"🔍 DEBUG - horas_limite recebido: {horas_limite}")
    print(f"🔍 DEBUG - agora (Brasília): {agora.strftime('%d/%m/%Y %H:%M:%S')}")
    
    if horas_limite is not None and horas_limite > 0:
        # Expira após X horas
        expira_em = agora + timedelta(hours=horas_limite)
        print(f"⏰ Chamada com DURAÇÃO de {horas_limite}h: expira {expira_em.strftime('%d/%m/%Y %H:%M:%S')} (Brasília)")
        return expira_em
    else:
        # CRIA MEIA-NOITE DO DIA ATUAL (23:59:59) - SEMPRE HOJE, NUNCA AMANHÃ!
        meia_noite = datetime(agora.year, agora.month, agora.day, 23, 59, 59, tzinfo=BR_TZ)
        
        print(f"🌙 Chamada SEM DURAÇÃO: expira HOJE {meia_noite.strftime('%d/%m/%Y %H:%M:%S')} (Brasília)")
        print(f"⏳ Tempo restante até meia-noite de HOJE: {meia_noite - agora}")
        
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
            
            # ATUALIZA EMBED
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
                        
                        # Define o texto do timing
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
            
            # MENSAGEM PRIVADA
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
    """Encerra a chamada após o tempo limite"""
    try:
        print(f"⏰ Iniciando contador para chamada {call_id}")
        print(f"📅 Expira em: {expira_em.strftime('%d/%m/%Y %H:%M:%S')} (Brasília)")
        
        # Calcula tempo restante
        agora = datetime.now(BR_TZ)
        tempo_restante = (expira_em - agora).total_seconds()
        
        if tempo_restante > 0:
            print(f"⏳ Aguardando {tempo_restante:.0f} segundos até expiração...")
            await asyncio.sleep(tempo_restante)
        
        print(f"✅ Tempo esgotado para chamada {call_id}")
        
        # ENCERRA A CHAMADA
        if call_id not in bot.call_data:
            print(f"❌ Chamada {call_id} não encontrada para encerrar")
            return
        
        call = bot.call_data[call_id]
        participantes = bot.call_participants.get(call_id, [])
        
        print(f"📊 Encerrando chamada {call_id} com {len(participantes)} participantes")
        
        channel = bot.get_channel(int(call['channel_id']))
        if channel:
            try:
                message = await channel.fetch_message(int(call['message_id']))
                if message:
                    # Define o texto do motivo do encerramento
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
                    
                    embed_final.add_field(
                        name="✅ LISTA FINAL",
                        value=participantes_text[:1024],
                        inline=False
                    )
                    
                    encerrado_em = datetime.now(BR_TZ)
                    embed_final.set_footer(text=f"Encerrada em {encerrado_em.strftime('%d/%m/%Y %H:%M')} (Brasília)")
                    embed_final.timestamp = encerrado_em
                    
                    await message.edit(embed=embed_final, view=None)
                    await channel.send(f"⏰ **Chamada encerrada!** Total de {len(participantes)} presente(s)! 📊")
                    print(f"✅ Mensagem da chamada {call_id} atualizada")
            except Exception as e:
                print(f"❌ Erro ao editar mensagem: {e}")
        
        # Limpa os dados
        if call_id in bot.call_data:
            del bot.call_data[call_id]
        if call_id in bot.call_participants:
            del bot.call_participants[call_id]
        if call_id in bot.active_tasks:
            del bot.active_tasks[call_id]
        
        bot.save_data()
        
        print(f"✅ Chamada {call_id} encerrada com sucesso!")
        
    except asyncio.CancelledError:
        print(f"⏹️ Task da chamada {call_id} foi cancelada")
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
    
    # Calcula tempo de expiração
    expira_em = calcular_tempo_expiracao(horas_duracao)
    
    call_id = f"{interaction.channel.id}-{int(datetime.now(BR_TZ).timestamp())}"
    data_atual = datetime.now(BR_TZ).strftime("%d.%m")
    
    # Texto do timing para mostrar no embed
    if horas_duracao:
        timing_text = f"⏰ Expira em {horas_duracao} hora(s) (às {expira_em.strftime('%H:%M')} Brasília)"
    else:
        timing_text = f"🌙 Expira HOJE às 23:59 (MEIA-NOITE Brasília)"
    
    # Monta o embed
    descricao_completa = f"""﹒⬚﹒⇆﹒🍑 ᆞ

५ᅟ𐙚 ⎯ᅟ︶︶︶﹒୧﹐atividade ❞ {data_atual}
𓈒 ׂ 🪷੭ ᮫ : {descricao if descricao else "Boa tarde, meus amores. Sejam bem-vindos ao canal de chamada da House! Esse espaço foi criado para confirmarmos quem permanece ativo e comprometido com a nossa House 🤍"}

ㅤ𔘓 ㅤׄㅤ ㅤׅ ㅤׄ 말 🌿 𝅼ㅤׄㅤㅤ𔘓 丶丶
[𒃵] A cada ausência não justificada, será registrado um tracinho.

𑇡 📝 Ao acumular sete tracinhos, será banido automaticamente.
Caso tenha algum compromisso, justifique sua ausência em. Estarei registrando os presentes no horário correto, então não será considerada confirmação fora do período informado.

여기 ㅤ🔔✨ ; A chamada começará às {data_hora}.
Para confirmar sua presença, reaja com o emoji indicado abaixo e sinta-se à vontade para continuar suas atividades após isso.
✦𓂃 Utilize o emoji {emoji} para responder à chamada.

ⓘ Lembrando: Marcar presença e desaparecer completamente da House até a próxima chamada também resultará em registro de ausência. Compromisso é essencial para mantermos a organização e o bom funcionamento daqui.

५ᅟ𐙚 ⎯ᅟᅟ❝ 🍑﹒ᥫ᭡﹐୨`﹒ꔫ﹐︶︶︶﹒୧﹐🍑 ❞
ㅤ𔘓 ㅤׄㅤ ㅤׅ ㅤׄ 魂 🌷 𝅼ㅤׄㅤㅤ𔘓 ◖

**{timing_text}**
**✅ PRESENTES: 0**"""
    
    embed = discord.Embed(
        title=f"🌿ᩚ📦 𝐇𝐎𝐔𝐒𝐄 ִ 𝐂̷̸𝐇𝐀𝐌𝐀𝐃𝐀 ꒥꒦ 📄",
        description=descricao_completa,
        color=discord.Color.from_str("#FF69B4")
    )
    
    embed.add_field(
        name="📋 LISTA DE PRESENTES",
        value="Ninguém confirmou ainda",
        inline=False
    )
    
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
    
    # Mensagem de confirmação
    if horas_duracao:
        confirm_msg = f"⏰ Expira em {horas_duracao} hora(s) (às {expira_em.strftime('%H:%M')} Brasília)"
    else:
        confirm_msg = f"🌙 Expira HOJE às 23:59 (MEIA-NOITE Brasília)"
    
    embed_confirm = discord.Embed(
        title="✅ Chamada Criada!",
        description=f"**{titulo}** criada com sucesso!",
        color=discord.Color.green()
    )
    
    embed_confirm.add_field(
        name="⏰ Timing",
        value=confirm_msg,
        inline=False
    )
    
    embed_confirm.add_field(
        name="📅 Data/Hora da chamada",
        value=data_hora,
        inline=True
    )
    
    embed_confirm.add_field(
        name="⏱️ Expira em",
        value=expira_em.strftime("%d/%m/%Y %H:%M") + " (Brasília)",
        inline=True
    )
    
    await interaction.followup.send(embed=embed_confirm, ephemeral=True)
    
    # Agenda o encerramento
    task = asyncio.create_task(encerrar_chamada_apos_tempo(call_id, expira_em))
    bot.active_tasks[call_id] = task
    
    print(f"✅ Chamada criada: {call_id}")
    print(f"📅 Expira em: {expira_em.strftime('%d/%m/%Y %H:%M:%S')} (Brasília)")

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
            
            if expira_em > datetime.now(BR_TZ):
                if data.get('horas_duracao'):
                    status = f"🟢 Ativa (expira em {data['horas_duracao']}h)"
                else:
                    status = "🟢 Ativa (vence HOJE 23:59 Brasília)"
            else:
                status = "🔴 Encerrada"
            
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
    
    if expira_em > datetime.now(BR_TZ):
        if data.get('horas_duracao'):
            status = f"🟢 Ativa (expira em {data['horas_duracao']}h)"
        else:
            status = "🟢 Ativa (vence HOJE 23:59 Brasília)"
    else:
        status = "🔴 Encerrada"
    
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
    
    # Cancela a task se estiver ativa
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
    """Lista todas as chamadas ativas no servidor"""
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
    
    embed = discord.Embed(
        title="📋 Chamadas Ativas",
        description=f"Total: {len(ativas)} chamada(s)",
        color=discord.Color.green()
    )
    
    for call_id, data, expira_em in ativas:
        participantes = len(bot.call_participants.get(call_id, []))
        
        if data.get('horas_duracao'):
            tempo = f"Expira em {data['horas_duracao']}h"
        else:
            tempo = f"Expira HOJE 23:59 Brasília"
        
        tempo_restante = expira_em - agora
        horas = int(tempo_restante.total_seconds() // 3600)
        minutos = int((tempo_restante.total_seconds() % 3600) // 60)
        
        embed.add_field(
            name=f"📢 {data['titulo'][:30]}",
            value=f"📅 {data['data_hora']}\n✅ {participantes} confirmados\n⏰ {tempo} (restam {horas}h {minutos}m)\n📝 `{data['message_id']}`",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# ==================== COMANDOS DE ENQUETE ====================

@bot.tree.command(name="enquete", description="📊 Criar uma enquete dinâmica")
async def enquete_criar(interaction: discord.Interaction):
    """Abre um modal para criar uma enquete"""
    modal = CriarEnqueteModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="enquete_info", description="ℹ️ Ver informações de uma enquete")
async def enquete_info(interaction: discord.Interaction, message_id: str):
    """Ver informações detalhadas de uma enquete"""
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
    
    embed = discord.Embed(
        title="📊 Informações da Enquete",
        description=f"**{data['pergunta']}**",
        color=discord.Color.blue()
    )
    
    embed.add_field(name="📝 Opções", value=str(len(data["opcoes"])), inline=True)
    embed.add_field(name="✅ Total de Votos", value=str(total_votos), inline=True)
    embed.add_field(name="👥 Participantes", value=str(len(data["votos_usuario"])), inline=True)
    embed.add_field(name="👤 Criador", value=f"<@{data['criador_id']}>", inline=True)
    
    if data.get("expira_em"):
        expira = datetime.fromisoformat(data["expira_em"]).replace(tzinfo=BR_TZ)
        if expira > datetime.now(BR_TZ):
            embed.add_field(name="⏰ Expira em", value=expira.strftime("%d/%m/%Y %H:%M"), inline=True)
        else:
            embed.add_field(name="⏰ Status", value="🔴 Encerrada", inline=True)
    else:
        embed.add_field(name="⏰ Status", value="🟢 Permanente", inline=True)
    
    embed.set_footer(text=f"ID: {enquete_id}")
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="enquete_listar", description="📋 Listar todas as enquetes ativas")
async def enquete_listar(interaction: discord.Interaction):
    """Lista todas as enquetes ativas no canal"""
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
    
    embed = discord.Embed(
        title="📋 Enquetes Ativas",
        description=f"Total: {len(ativas)} enquete(s)",
        color=discord.Color.green()
    )
    
    for eid, data, expira in ativas[:10]:
        total_votos = sum(data["votos"])
        status = "🟢 Ativa"
        if expira:
            tempo_restante = expira - agora
            horas = int(tempo_restante.total_seconds() // 3600)
            minutos = int((tempo_restante.total_seconds() % 3600) // 60)
            status = f"⏰ Expira em {horas}h {minutos}m"
        
        embed.add_field(
            name=f"📊 {data['pergunta'][:40]}",
            value=f"📝 {len(data['opcoes'])} opções\n✅ {total_votos} votos\n{status}\n📝 `{data['message_id']}`",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

@bot.tree.command(name="enquete_gerenciar", description="⚙️ Gerenciar uma enquete")
async def enquete_gerenciar(interaction: discord.Interaction, message_id: str):
    """Abre o painel de gerenciamento da enquete"""
    enquete_id = None
    for eid, data in bot.enquetes.items():
        if data.get('message_id') == message_id:
            enquete_id = eid
            break
    
    if not enquete_id:
        await interaction.response.send_message("❌ Enquete não encontrada!", ephemeral=True)
        return
    
    data = bot.enquetes[enquete_id]
    
    # Verifica permissão
    if str(interaction.user.id) != data["criador_id"] and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Apenas o criador ou administradores podem gerenciar a enquete!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="⚙️ Painel de Gerenciamento",
        description=f"**{data['pergunta']}**",
        color=discord.Color.purple()
    )
    
    embed.add_field(name="📝 Opções", value=str(len(data["opcoes"])), inline=True)
    embed.add_field(name="✅ Votos", value=str(sum(data["votos"])), inline=True)
    embed.add_field(name="👥 Participantes", value=str(len(data["votos_usuario"])), inline=True)
    
    view = GerenciarEnqueteView(enquete_id)
    
    await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

# ==================== SISTEMA DE SHIP COMPLETO ====================

@bot.tree.command(name="ship", description="💖 Calcula o amor entre duas pessoas")
async def ship(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    base = random.randint(40, 90)
    
    if pessoa1.guild == pessoa2.guild:
        base += 5
    
    cargos_comuns = set(pessoa1.roles) & set(pessoa2.roles)
    if len(cargos_comuns) > 1:
        base += len(cargos_comuns) * 2
    
    idade_p1 = (datetime.now(BR_TZ) - pessoa1.created_at.replace(tzinfo=BR_TZ)).days
    idade_p2 = (datetime.now(BR_TZ) - pessoa2.created_at.replace(tzinfo=BR_TZ)).days
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
        "data": datetime.now(BR_TZ).isoformat()
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
    embed.add_field(name="📅 Data", value=datetime.fromisoformat(data["data"]).replace(tzinfo=BR_TZ).strftime("%d/%m/%Y"), inline=True)
    
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
    
    marriage_id = f"{pessoa_id}-{user_id}-{datetime.now(BR_TZ).timestamp()}"
    
    bot.marriage_data[marriage_id] = {
        "pessoa1": pessoa_id,
        "pessoa2": user_id,
        "data_casamento": datetime.now(BR_TZ).isoformat(),
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
    
    data_casamento = datetime.fromisoformat(casamento_atual["data_casamento"]).replace(tzinfo=BR_TZ)
    hoje = datetime.now(BR_TZ)
    
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
    
    data_casamento = datetime.fromisoformat(casamento_atual["data_casamento"]).replace(tzinfo=BR_TZ)
    if datetime.now(BR_TZ) - data_casamento > timedelta(days=7):
        casamento_atual["luademel"] = False
        bot.save_data()
        await interaction.response.send_message("❌ Lua de mel acabou!")
        return
    
    conjuge_id = casamento_atual["pessoa2"] if casamento_atual["pessoa1"] == user_id else casamento_atual["pessoa1"]
    dias_restantes = 7 - (datetime.now(BR_TZ) - data_casamento).days
    
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
    hoje = datetime.now(BR_TZ).date()
    
    if user_id in bot.daily_cooldowns:
        ultimo = datetime.fromisoformat(bot.daily_cooldowns[user_id]).date()
        if hoje == ultimo:
            await interaction.response.send_message("❌ Daily já coletado hoje!")
            return
    
    valor = 500
    if user_id not in bot.user_balances:
        bot.user_balances[user_id] = 0
    
    bot.user_balances[user_id] += valor
    bot.daily_cooldowns[user_id] = datetime.now(BR_TZ).isoformat()
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
    embed.add_field(name="Conta criada", value=membro.created_at.replace(tzinfo=BR_TZ).strftime("%d/%m/%Y"), inline=True)
    embed.add_field(name="Entrou em", value=membro.joined_at.replace(tzinfo=BR_TZ).strftime("%d/%m/%Y"), inline=True)
    
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
    embed.add_field(name="Criado em", value=guild.created_at.replace(tzinfo=BR_TZ).strftime("%d/%m/%Y"), inline=True)
    
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

@bot.tree.command(name="baitola", description="🏳️‍🌈 Mensagem especial")
async def baitola(interaction: discord.Interaction, membro: discord.Member):
    frases = [
        f"{membro.mention} é o maior baitola do servidor! 🏳️‍🌈",
        f"Parabéns {membro.mention}, você é o baitola master! 🏆"
    ]
    await interaction.response.send_message(random.choice(frases))

# ==================== COMANDOS COM GIFS ====================

gifs_abraco = [
    "https://media.giphy.com/media/3ZnBrkqoaI2hq/giphy.gif",
    "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif",
    "https://media.giphy.com/media/lrr9rHuoJOE0w/giphy.gif",
    "https://media.giphy.com/media/13d2jHlSlxklVe/giphy.gif",
    "https://media.giphy.com/media/wnsgren9NtITS/giphy.gif",
    "https://media.giphy.com/media/PHZ7v9tfQu0o0/giphy.gif",
    "https://media.giphy.com/media/3o7abB06u9bNzA8LC8/giphy.gif",
    "https://media.giphy.com/media/l2JegQYezBkR90gFm/giphy.gif"
]

gifs_beijo = [
    "https://media.giphy.com/media/bGm9FuBCGg4SY/giphy.gif",
    "https://media.giphy.com/media/G3va31oEEnIkM/giphy.gif",
    "https://media.giphy.com/media/12VXIxKaIEarL2/giphy.gif",
    "https://media.giphy.com/media/hnNyVPIXgLdle/giphy.gif",
    "https://media.giphy.com/media/flmwfIpFVrSKI/giphy.gif",
    "https://media.giphy.com/media/3oz8xIZrAhijabg8YM/giphy.gif",
    "https://media.giphy.com/media/3o7abKhOpu0N2tWqVO/giphy.gif",
    "https://media.giphy.com/media/26gs9kSN6d5PxSsQU/giphy.gif"
]

gifs_carinho = [
    "https://media.giphy.com/media/4HP0ddZnNVvKU/giphy.gif",
    "https://media.giphy.com/media/109ltuoSQT212w/giphy.gif",
    "https://media.giphy.com/media/xT0BKiwjg0O6yIR2o/giphy.gif",
    "https://media.giphy.com/media/3o7abpRrPjBne2h2Qw/giphy.gif",
    "https://media.giphy.com/media/l0MYt5jH6gkTWm8qo/giphy.gif",
    "https://media.giphy.com/media/xT0Gqn9yI8Edh6L7W0/giphy.gif",
    "https://media.giphy.com/media/3o6Zt481isNVuQI1l6/giphy.gif",
    "https://media.giphy.com/media/3o7TKsQ8CAGJ6A9p20/giphy.gif"
]

gifs_tapa = [
    "https://media.giphy.com/media/uG3lKkAuh53wc/giphy.gif",
    "https://media.giphy.com/media/j3iGKfXRKlLqw/giphy.gif",
    "https://media.giphy.com/media/3oxHQq4M0xGpWpU2g/giphy.gif",
    "https://media.giphy.com/media/3o7abBOGh2Lq3qFjm/giphy.gif",
    "https://media.giphy.com/media/3o7TKz2fL6f5T7d6cU/giphy.gif"
]

gifs_festa = [
    "https://media.giphy.com/media/l0MYEqEzwMWFCg8rm/giphy.gif",
    "https://media.giphy.com/media/3o7abAHdYwZdO3Q8qk/giphy.gif",
    "https://media.giphy.com/media/3o85xnoIXebk3xYx4I/giphy.gif",
    "https://media.giphy.com/media/l0MYt5jH6gkTWm8qo/giphy.gif",
    "https://media.giphy.com/media/3o7TKo5M8RxWpU8G1i/giphy.gif"
]

gifs_matar = [
    "https://media.giphy.com/media/3o6Mbj2w67HnPQcQoM/giphy.gif",
    "https://media.giphy.com/media/l0MYEqEzwMWFCg8rm/giphy.gif",
    "https://media.giphy.com/media/3o7TKsQ8CAGJ6A9p20/giphy.gif",
    "https://media.giphy.com/media/3o7abBOGh2Lq3qFjm/giphy.gif"
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

@bot.tree.command(name="matar", description="💀 Matar alguém (brincadeira) com GIF")
async def matar(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se matar! 😱")
        return
    
    gif = random.choice(gifs_matar)
    
    embed = discord.Embed(
        title="💀 MORTE!",
        description=f"{interaction.user.mention} matou {membro.mention}! (brincadeira 😅)",
        color=discord.Color.dark_red()
    )
    embed.set_image(url=gif)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="chifre", description="🦌 Dar chifre em alguém")
async def chifre(interaction: discord.Interaction, membro: discord.Member):
    embed = discord.Embed(
        title="🦌 CHIFRE!",
        description=f"{interaction.user.mention} deu chifre em {membro.mention}!",
        color=discord.Color.green()
    )
    embed.set_image(url="https://media.giphy.com/media/3o7TKsQ8CAGJ6A9p20/giphy.gif")
    
    await interaction.response.send_message(embed=embed)

# ==================== OUTRAS FUNÇÕES LEGAIS ====================

@bot.tree.command(name="moeda", description="🪙 Jogar uma moeda")
async def moeda(interaction: discord.Interaction):
    resultado = random.choice(["CARA", "COROA"])
    await interaction.response.send_message(f"🪙 A moeda caiu: **{resultado}**!")

@bot.tree.command(name="rps", description="🗿 Pedra, Papel ou Tesoura contra o bot")
@app_commands.describe(escolha="Sua escolha")
async def rps(interaction: discord.Interaction, escolha: str):
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
    
    emojis = {"pedra": "🗿", "papel": "📄", "tesoura": "✂️"}
    
    embed = discord.Embed(
        title="🗿📄✂️ Jokenpo",
        description=f"Você: {emojis[escolha.lower()]}\nBot: {emojis[bot_choice]}",
        color=cor
    )
    embed.add_field(name="Resultado", value=resultado)
    
    await interaction.response.send_message(embed=embed)

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
    
    if quantidade > 1:
        media = total / quantidade
        embed.add_field(name="Média", value=f"{media:.1f}", inline=True)
    
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

# ==================== COMANDO DE AJUDA ATUALIZADO ====================

@bot.tree.command(name="ajuda", description="📚 Todos os comandos")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Comandos do Bot Fort",
        description="**Sistema Completo - 70+ COMANDOS!**",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📢 **CHAMADAS**",
        value="`/chamada` - Criar chamada\n"
              "`/chamada_info` - Ver informações\n"
              "`/chamada_lista` - Lista completa\n"
              "`/chamada_cancelar` - Cancelar\n"
              "`/chamada_listar_ativas` - Listar ativas\n"
              "✨ **SEM horas: vence HOJE 23:59 (MEIA-NOITE Brasília)!**\n"
              "✨ **COM horas: vence após X horas**",
        inline=False
    )
    
    embed.add_field(
        name="📊 **ENQUETES**",
        value="`/enquete` - Criar enquete dinâmica\n"
              "`/enquete_info` - Ver informações\n"
              "`/enquete_listar` - Listar enquetes\n"
              "`/enquete_gerenciar` - Gerenciar enquete\n"
              "✨ **Botões interativos!**\n"
              "✨ **Votos em tempo real!**\n"
              "✨ **Até 20 opções!**",
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
        name="🎭 **INTERAÇÕES COM GIF**",
        value="`/abraco_gif` - Abraçar\n"
              "`/beijo_gif` - Beijar\n"
              "`/carinho_gif` - Carinho\n"
              "`/cafune_gif` - Cafuné\n"
              "`/tapa` - Dar tapa\n"
              "`/festa` - Fazer festa\n"
              "`/matar` - Matar (brincadeira)\n"
              "`/chifre` - Dar chifre\n",
        inline=True
    )
    
    embed.add_field(
        name="🎮 **JOGOS**",
        value="`/moeda` - Cara ou coroa\n"
              "`/rps` - Pedra papel tesoura\n"
              "`/dado_rpg` - Dados de RPG\n"
              "`/sortear` - Sortear membro\n",
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
              "`/baitola` - 🏳️‍🌈\n",
        inline=True
    )
    
    embed.set_footer(text="Total: 75+ comandos! Use / antes de cada comando")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

# ==================== INICIAR BOT ====================
async def main():
    print("🔵 INICIANDO FUNÇÃO MAIN")
    
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        print("❌ ERRO CRÍTICO: Token não encontrado!")
        return
    
    print(f"🔵 Token encontrado! Conectando...")
    print(f"⏰ Fuso horário configurado: Brasília (UTC-3)")
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
    print("🚀 INICIANDO BOT FORT - VERSÃO COMPLETA COM SISTEMA DE ENQUETES!")
    print("="*60)
    print("\n📢 SISTEMAS CARREGADOS:")
    print("✅ Sistema de Chamadas CORRIGIDO - Agora com FUSO BRASIL!")
    print("✅ Sistema de Enquetes DINÂMICO - Botões interativos!")
    print("✅ Expira HOJE 23:59 (Brasília) - NÃO confunde mais!")
    print("✅ Tasks persistentes - Mantém chamadas após reinicialização")
    print("✅ Enquetes com até 20 opções e votos em tempo real!")
    print("✅ Sistema de Ship (likes, ranking)")
    print("✅ Sistema de Casamento (com economia)")
    print("✅ Sistema de Presentes e Signos")
    print("✅ Sistema de Economia (daily, slots)")
    print("✅ Comandos com GIF (abraço, beijo, etc)")
    print("✅ 75+ COMANDOS NO TOTAL!")
    print("="*60)
    
    run_bot()
