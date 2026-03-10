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
import requests
from collections import defaultdict
import re

# ===== CONFIGURAÇÃO DO TOKEN =====
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')

# ===== IMPORTS DO SERVIDOR WEB =====
from flask import Flask, jsonify
import threading

# ===== IMPORTS PARA MÚSICA =====
import yt_dlp as youtube_dl
import urllib.parse
import urllib.request

# Configurar encoding e logging
sys.stdout.reconfigure(encoding='utf-8')
logging.basicConfig(level=logging.INFO)

# ===== CONFIGURAÇÕES =====
YTDL_OPTIONS = {
    'format': 'bestaudio/best',
    'extractaudio': True,
    'audioformat': 'mp3',
    'outtmpl': '%(extractor)s-%(id)s-%(title)s.%(ext)s',
    'restrictfilenames': True,
    'noplaylist': True,
    'nocheckcertificate': True,
    'ignoreerrors': False,
    'logtostderr': False,
    'quiet': True,
    'no_warnings': True,
    'default_search': 'auto',
    'source_address': '0.0.0.0',
}

FFMPEG_OPTIONS = {
    'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
    'options': '-vn'
}

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

# ===== CLASSE DO BOT PRINCIPAL =====
class Fort(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.voice_states = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        
        # Sistemas existentes
        self.user_balances = {}
        self.user_inventory = {}
        self.daily_cooldowns = {}
        self.ship_data = {}
        self.marriage_data = {}
        self.divorce_cooldowns = {}
        self.anniversary_data = {}
        self.ship_history = {}
        self.call_data = {}
        self.call_participants = {}
        
        # ===== NOVOS SISTEMAS =====
        
        # Sistema de Moderação
        self.warnings = {}
        self.muted_roles = {}
        self.temp_mutes = {}
        self.locked_channels = set()
        self.slowmode_channels = {}
        
        # Sistema de Música
        self.voice_clients = {}
        self.music_queues = {}
        self.now_playing = {}
        self.music_loops = {}
        self.music_volumes = {}
        
        # Sistema de Utilidade
        self.reminders = []
        self.birthdays = {}
        self.user_timezones = {}
        self.saved_messages = {}
        self.poll_data = {}
        
        # Sistema Criativo
        self.daily_phrases = []
        self.user_jokes = {}
        self.fun_facts = []
        self.horoscope_cache = {}
        
        # Inicializa banco de dados
        self.init_database()
        self.load_data()
        self.load_resources()
    
    # ===== FUNÇÕES SQLITE =====
    def init_database(self):
        """Cria o banco de dados SQLite com todas as tabelas"""
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        # Tabelas existentes
        c.execute('''CREATE TABLE IF NOT EXISTS economia
                     (user_id TEXT PRIMARY KEY, saldo INTEGER)''')
        c.execute('''CREATE TABLE IF NOT EXISTS daily_cooldowns
                     (user_id TEXT PRIMARY KEY, data TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS divorce_cooldowns
                     (user_id TEXT PRIMARY KEY, data TEXT)''')
        c.execute('''CREATE TABLE IF NOT EXISTS dados_json
                     (tipo TEXT PRIMARY KEY, dados TEXT)''')
        
        # ===== NOVAS TABELAS =====
        
        # Tabela de avisos
        c.execute('''CREATE TABLE IF NOT EXISTS warnings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      moderator_id TEXT,
                      reason TEXT,
                      date TEXT,
                      guild_id TEXT)''')
        
        # Tabela de aniversários
        c.execute('''CREATE TABLE IF NOT EXISTS birthdays
                     (user_id TEXT PRIMARY KEY,
                      day INTEGER,
                      month INTEGER,
                      year INTEGER)''')
        
        # Tabela de lembretes
        c.execute('''CREATE TABLE IF NOT EXISTS reminders
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      channel_id TEXT,
                      message TEXT,
                      remind_time TEXT,
                      created_at TEXT)''')
        
        # Tabela de timezones
        c.execute('''CREATE TABLE IF NOT EXISTS timezones
                     (user_id TEXT PRIMARY KEY,
                      timezone TEXT)''')
        
        # Tabela de músicas favoritas
        c.execute('''CREATE TABLE IF NOT EXISTS favorite_songs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      song_title TEXT,
                      song_url TEXT,
                      added_date TEXT)''')
        
        # Tabela de frases salvas
        c.execute('''CREATE TABLE IF NOT EXISTS saved_phrases
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      phrase TEXT,
                      category TEXT,
                      date TEXT)''')
        
        # Tabela de logs de moderação
        c.execute('''CREATE TABLE IF NOT EXISTS moderation_logs
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      action TEXT,
                      moderator_id TEXT,
                      user_id TEXT,
                      reason TEXT,
                      date TEXT,
                      guild_id TEXT)''')
        
        conn.commit()
        conn.close()
        print("✅ Banco de dados SQLite atualizado com novas tabelas!")
    
    def load_resources(self):
        """Carrega recursos como frases, fatos, etc"""
        # Frases motivacionais
        self.daily_phrases = [
            "🌅 Acredite em você e tudo será possível!",
            "💪 Cada dia é uma nova chance para ser feliz!",
            "🌟 Você é mais forte do que imagina!",
            "🌈 A vida é feita de pequenas alegrias!",
            "⭐ Nunca é tarde para recomeçar!",
            "🌸 Seja a mudança que você quer ver no mundo!",
            "🦋 Acredite nos seus sonhos!",
            "🌺 A felicidade está nas pequenas coisas!",
            "🍀 Hoje será um ótimo dia!",
            "✨ Você é especial do jeito que é!"
        ]
        
        # Fatos curiosos
        self.fun_facts = [
            "🦒 As girafas dormem apenas 30 minutos por dia!",
            "🐘 Os elefantes são os únicos mamíferos que não podem pular!",
            "🐧 Os pinguins propõem casamento com uma pedra!",
            "🦋 As borboletas sentem gosto com os pés!",
            "🐙 Os polvos têm três corações!",
            "🦉 As corujas não podem mover os olhos!",
            "🐫 Os camelos não armazenam água nas corcovas!",
            "🦔 Ouriços são imunes a veneno de cobra!",
            "🦩 Flamingos nascem cinzas e ficam rosados!",
            "🐋 A baleia azul tem coração do tamanho de um carro!"
        ]
        
        # Charadas
        self.riddles = [
            {"pergunta": "O que é, o que é? Quanto mais se tira, maior fica?", "resposta": "O buraco"},
            {"pergunta": "O que é, o que é? Tem cabeça e tem dente, não é bicho e nem gente?", "resposta": "O alho"},
            {"pergunta": "O que é, o que é? Anda deitado e dorme em pé?", "resposta": "O pé"},
            {"pergunta": "O que é, o que é? Quanto maior, menos se vê?", "resposta": "A escuridão"},
            {"pergunta": "O que é, o que é? Tem asa mas não voa, tem bico mas não bica?", "resposta": "O bule"},
            {"pergunta": "O que é, o que é? Dá muitas voltas e não sai do lugar?", "resposta": "O relógio"},
            {"pergunta": "O que é, o que é? Feito para andar e não anda?", "resposta": "A rua"},
            {"pergunta": "O que é, o que é? Tem coroa mas não é rei?", "resposta": "O abacaxi"}
        ]
        
        # Piadas
        self.jokes = [
            "😂 Por que o computador foi preso? Porque executou um comando!",
            "😂 O que o zero disse para o oito? Belo cinto!",
            "😂 Por que os elétrons nunca pagam contas? Porque estão sempre em débito!",
            "😂 O que o pato disse para a pata? Vem quá!",
            "😂 Qual o cúmulo da rapidez? Fechar o zíper com uma bala!",
            "😂 O que é um pontinho amarelo no céu? Um yellowcóptero!",
            "😂 Por que o livro de matemática está triste? Porque tem muitos problemas!",
            "😂 O que o tomate foi fazer no banco? Tirar extrato!",
            "😂 Como o ovo se sente? Ovitado!",
            "😂 Qual é o café mais forte do mundo? O café com leão!"
        ]
        
        print("✅ Recursos carregados (frases, fatos, piadas, charadas)!")
    
    def load_data(self):
        """Carrega dados do SQLite"""
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        # Dados existentes
        c.execute('SELECT user_id, saldo FROM economia')
        self.user_balances = {user_id: saldo for user_id, saldo in c.fetchall()}
        
        c.execute('SELECT user_id, data FROM daily_cooldowns')
        self.daily_cooldowns = {user_id: data for user_id, data in c.fetchall()}
        
        c.execute('SELECT user_id, data FROM divorce_cooldowns')
        self.divorce_cooldowns = {}
        for user_id, data in c.fetchall():
            self.divorce_cooldowns[user_id] = datetime.fromisoformat(data) if data else None
        
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
        
        # ===== CARREGAR NOVOS DADOS =====
        
        # Carregar warnings
        c.execute('SELECT user_id, moderator_id, reason, date, guild_id FROM warnings')
        for user_id, mod_id, reason, date, guild_id in c.fetchall():
            if guild_id not in self.warnings:
                self.warnings[guild_id] = {}
            if user_id not in self.warnings[guild_id]:
                self.warnings[guild_id][user_id] = []
            
            self.warnings[guild_id][user_id].append({
                'moderator_id': mod_id,
                'reason': reason,
                'date': date
            })
        
        # Carregar aniversários
        c.execute('SELECT user_id, day, month, year FROM birthdays')
        for user_id, day, month, year in c.fetchall():
            self.birthdays[user_id] = {'day': day, 'month': month, 'year': year}
        
        # Carregar lembretes
        c.execute('SELECT id, user_id, channel_id, message, remind_time FROM reminders')
        for rid, user_id, channel_id, message, remind_time in c.fetchall():
            self.reminders.append({
                'id': rid,
                'user_id': user_id,
                'channel_id': channel_id,
                'message': message,
                'remind_time': datetime.fromisoformat(remind_time)
            })
        
        # Carregar timezones
        c.execute('SELECT user_id, timezone FROM timezones')
        self.user_timezones = {user_id: tz for user_id, tz in c.fetchall()}
        
        conn.close()
        print("✅ Dados carregados do SQLite!")
    
    def save_data(self):
        """Salva todos os dados no SQLite"""
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        
        # Dados existentes
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
            ('call_participants', self.call_participants)
        ]
        
        for tipo, dados in dados_para_salvar:
            c.execute('INSERT OR REPLACE INTO dados_json VALUES (?, ?)', 
                     (tipo, json.dumps(dados, ensure_ascii=False)))
        
        # Salvar warnings
        c.execute('DELETE FROM warnings')
        for guild_id, guild_warnings in self.warnings.items():
            for user_id, warns in guild_warnings.items():
                for warn in warns:
                    c.execute('''INSERT INTO warnings 
                               (user_id, moderator_id, reason, date, guild_id) 
                               VALUES (?, ?, ?, ?, ?)''',
                            (user_id, warn['moderator_id'], warn['reason'], 
                             warn['date'], guild_id))
        
        # Salvar aniversários
        c.execute('DELETE FROM birthdays')
        for user_id, data in self.birthdays.items():
            c.execute('INSERT INTO birthdays VALUES (?, ?, ?, ?)',
                     (user_id, data['day'], data['month'], data.get('year', 0)))
        
        # Salvar timezones
        c.execute('DELETE FROM timezones')
        for user_id, tz in self.user_timezones.items():
            c.execute('INSERT INTO timezones VALUES (?, ?)', (user_id, tz))
        
        # Limpar lembretes antigos
        c.execute('DELETE FROM reminders WHERE remind_time < ?', 
                 (datetime.now().isoformat(),))
        
        # Salvar lembretes ativos
        for reminder in self.reminders:
            if reminder['remind_time'] > datetime.now():
                c.execute('''INSERT OR REPLACE INTO reminders 
                           (id, user_id, channel_id, message, remind_time, created_at)
                           VALUES (?, ?, ?, ?, ?, ?)''',
                        (reminder['id'], reminder['user_id'], reminder['channel_id'],
                         reminder['message'], reminder['remind_time'].isoformat(),
                         datetime.now().isoformat()))
        
        conn.commit()
        conn.close()

    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Comandos sincronizados!")
        
        # Iniciar tarefas de background
        self.loop.create_task(self.check_reminders())
        self.loop.create_task(self.check_birthdays())
        self.loop.create_task(self.check_temp_mutes())

    async def on_ready(self):
        print(f"✅ Bot {self.user} ligado com sucesso!")
        print(f"📊 Servidores: {len(self.guilds)}")
        print(f"👥 Usuários: {len(self.users)}")
        print("\n📢 SISTEMAS CARREGADOS:")
        print("✅ Sistema de Chamadas")
        print("✅ Sistema de Ship e Casamento")
        print("✅ Sistema de Economia e Jogos")
        print("✅ Sistema de Moderação")
        print("✅ Sistema de Música")
        print("✅ Sistema de Utilidade")
        print("✅ Sistema Criativo")
        print("✅ Sistema de Aniversários e Lembretes")
        print(f"🎵 Comandos totais: 100+")
        await self.change_presence(activity=discord.Game(name="📢 Use /ajuda | 100+ comandos!"))
    
    # ===== TAREFAS DE BACKGROUND =====
    
    async def check_reminders(self):
        """Verifica lembretes a cada minuto"""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                agora = datetime.now()
                to_remove = []
                
                for reminder in self.reminders:
                    if reminder['remind_time'] <= agora:
                        channel = self.get_channel(int(reminder['channel_id']))
                        if channel:
                            user = self.get_user(int(reminder['user_id']))
                            if user:
                                embed = discord.Embed(
                                    title="⏰ LEMBRETE!",
                                    description=reminder['message'],
                                    color=discord.Color.gold()
                                )
                                embed.set_footer(text=f"Lembrete para {user.name}")
                                
                                await channel.send(content=user.mention, embed=embed)
                        
                        to_remove.append(reminder)
                
                for reminder in to_remove:
                    self.reminders.remove(reminder)
                
                if to_remove:
                    self.save_data()
                
            except Exception as e:
                print(f"Erro no check_reminders: {e}")
            
            await asyncio.sleep(60)  # Verifica a cada minuto
    
    async def check_birthdays(self):
        """Verifica aniversários uma vez por dia"""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                agora = datetime.now()
                
                # Verifica à meia-noite
                if agora.hour == 0 and agora.minute == 0:
                    for user_id, data in self.birthdays.items():
                        if data['month'] == agora.month and data['day'] == agora.day:
                            # Encontra servidores onde o usuário está
                            for guild in self.guilds:
                                member = guild.get_member(int(user_id))
                                if member:
                                    # Envia mensagem no sistema ou canal geral
                                    channel = discord.utils.get(guild.text_channels, name="geral")
                                    if channel:
                                        anos = agora.year - data.get('year', agora.year)
                                        embed = discord.Embed(
                                            title="🎂 FELIZ ANIVERSÁRIO!",
                                            description=f"Hoje é aniversário de {member.mention}!",
                                            color=discord.Color.gold()
                                        )
                                        if anos > 0:
                                            embed.add_field(name="🎉 Idade", value=f"{anos} anos")
                                        
                                        await channel.send(embed=embed)
            
            except Exception as e:
                print(f"Erro no check_birthdays: {e}")
            
            await asyncio.sleep(3600)  # Verifica a cada hora
    
    async def check_temp_mutes(self):
        """Verifica mutes temporários"""
        await self.wait_until_ready()
        while not self.is_closed():
            try:
                agora = datetime.now()
                to_remove = []
                
                for user_id, data in self.temp_mutes.items():
                    if data['until'] <= agora:
                        guild = self.get_guild(int(data['guild_id']))
                        if guild:
                            member = guild.get_member(int(user_id))
                            if member:
                                muted_role = discord.utils.get(guild.roles, name="Silenciado")
                                if muted_role and muted_role in member.roles:
                                    await member.remove_roles(muted_role, reason="Tempo de mute expirado")
                        
                        to_remove.append(user_id)
                
                for user_id in to_remove:
                    del self.temp_mutes[user_id]
                
            except Exception as e:
                print(f"Erro no check_temp_mutes: {e}")
            
            await asyncio.sleep(60)

bot = Fort()

# ===== SISTEMA DE CHAMADAS (existente, mantido) =====
# [Todo o código de chamadas permanece igual]

def calcular_tempo_expiracao(horas_limite: Optional[int] = None):
    agora = datetime.now()
    
    if horas_limite is not None and horas_limite > 0:
        expira_em = agora + timedelta(hours=horas_limite)
        return expira_em
    else:
        meia_noite = datetime(agora.year, agora.month, agora.day, 23, 59, 59)
        if agora > meia_noite:
            meia_noite = datetime(agora.year, agora.month, agora.day, 23, 59, 59) + timedelta(days=1)
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
        if datetime.now() > self.expira_em:
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
                        
                        data_atual = datetime.now().strftime("%d.%m")
                        
                        if call.get('horas_duracao'):
                            timing_text = f"⏰ Expira em {call['horas_duracao']} hora(s)"
                        else:
                            timing_text = f"🌙 Expira à meia-noite (hoje às 23:59)"
                        
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
                        embed.timestamp = datetime.now()
                        
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
        while True:
            agora = datetime.now()
            tempo_restante = (expira_em - agora).total_seconds()
            
            if tempo_restante <= 0:
                break
            
            espera = min(tempo_restante, 1800)
            await asyncio.sleep(espera)
        
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
                        motivo = "À MEIA-NOITE"
                    
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
                    
                    embed_final.set_footer(text=f"Encerrada em {datetime.now().strftime('%d/%m/%Y %H:%M')}")
                    embed_final.timestamp = datetime.now()
                    
                    await message.edit(embed=embed_final, view=None)
                    await channel.send(f"⏰ **Chamada encerrada!** Total de {len(participantes)} presente(s)! 📊")
            except Exception as e:
                print(f"❌ Erro ao editar mensagem: {e}")
        
        if call_id in bot.call_data:
            del bot.call_data[call_id]
        if call_id in bot.call_participants:
            del bot.call_participants[call_id]
        bot.save_data()
        
    except Exception as e:
        print(f"❌ Erro ao encerrar chamada: {e}")

@bot.tree.command(name="chamada", description="📢 Criar uma chamada (@everyone)")
@app_commands.describe(
    titulo="Título do evento",
    data_hora="Data e hora (ex: 15:40 ou 25/12 20h)",
    local="Local do evento",
    horas_duracao="Horas para expirar (opcional - se não colocar, vence meia-noite)",
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
    
    expira_em = calcular_tempo_expiracao(horas_duracao)
    
    agora = datetime.now()
    if expira_em <= agora:
        if horas_duracao:
            expira_em = agora + timedelta(hours=1)
        else:
            expira_em = datetime(agora.year, agora.month, agora.day, 23, 59, 59) + timedelta(days=1)
    
    call_id = f"{interaction.channel.id}-{int(datetime.now().timestamp())}"
    data_atual = datetime.now().strftime("%d.%m")
    
    if horas_duracao:
        timing_text = f"⏰ Expira em {horas_duracao} hora(s) (às {expira_em.strftime('%H:%M')})"
    else:
        timing_text = f"🌙 Expira à meia-noite (hoje às 23:59)"
    
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
    embed.timestamp = datetime.now()
    
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
        'criado_em': datetime.now().isoformat(),
        'horas_duracao': horas_duracao
    }
    
    bot.call_participants[call_id] = []
    bot.save_data()
    
    embed_confirm = discord.Embed(
        title="✅ Chamada Criada!",
        description=f"**{titulo}** criada com sucesso!",
        color=discord.Color.green()
    )
    
    embed_confirm.add_field(
        name="⏰ Timing",
        value=timing_text,
        inline=False
    )
    
    embed_confirm.add_field(
        name="📅 Data/Hora da chamada",
        value=data_hora,
        inline=True
    )
    
    embed_confirm.add_field(
        name="⏱️ Expira em",
        value=expira_em.strftime("%d/%m/%Y %H:%M"),
        inline=True
    )
    
    await interaction.followup.send(embed=embed_confirm, ephemeral=True)
    
    asyncio.create_task(encerrar_chamada_apos_tempo(call_id, expira_em))
    
    print(f"✅ Chamada criada: {call_id}")

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
            expira_em = datetime.fromisoformat(data['expira_em'])
            
            if expira_em > datetime.now():
                if data.get('horas_duracao'):
                    status = f"🟢 Ativa (expira em {data['horas_duracao']}h)"
                else:
                    status = "🟢 Ativa (vence meia-noite)"
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
    expira_em = datetime.fromisoformat(data['expira_em'])
    
    if expira_em > datetime.now():
        if data.get('horas_duracao'):
            status = f"🟢 Ativa (expira em {data['horas_duracao']}h)"
        else:
            status = "🟢 Ativa (vence meia-noite)"
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

# ===== SISTEMA DE SHIP E CASAMENTO (mantido do original) =====
# [Todo o código de ship e casamento permanece igual]

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

# ===== SISTEMA DE CASAMENTO (mantido do original) =====

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

# ===== SISTEMA DE SIGNOS E PRESENTES (mantido do original) =====

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

# ===== SISTEMA DE ECONOMIA (mantido do original) =====

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

# ===== SISTEMA DE MODERAÇÃO (NOVO) =====

@bot.tree.command(name="clear", description="🧹 Limpar mensagens do canal")
@app_commands.describe(quantidade="Número de mensagens para apagar (1-100)")
@app_commands.default_permissions(manage_messages=True)
async def clear(interaction: discord.Interaction, quantidade: int):
    if quantidade < 1 or quantidade > 100:
        await interaction.response.send_message("❌ Quantidade deve ser entre 1 e 100!")
        return
    
    await interaction.response.defer(ephemeral=True)
    
    try:
        deleted = await interaction.channel.purge(limit=quantidade)
        await interaction.followup.send(f"🧹 **{len(deleted)}** mensagens apagadas!", ephemeral=True)
        
        # Log da ação
        embed = discord.Embed(
            title="🧹 Mensagens Apagadas",
            description=f"**Canal:** {interaction.channel.mention}\n**Quantidade:** {len(deleted)}\n**Moderador:** {interaction.user.mention}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        # Tenta enviar para canal de logs
        log_channel = discord.utils.get(interaction.guild.text_channels, name="logs")
        if log_channel:
            await log_channel.send(embed=embed)
            
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao limpar mensagens: {e}", ephemeral=True)

@bot.tree.command(name="kick", description="👢 Expulsar membro do servidor")
@app_commands.describe(membro="Membro a ser expulso", motivo="Motivo da expulsão")
@app_commands.default_permissions(kick_members=True)
async def kick(interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não especificado"):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se expulsar!", ephemeral=True)
        return
    
    if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Você não pode expulsar alguém com cargo maior ou igual ao seu!", ephemeral=True)
        return
    
    try:
        # Tenta enviar DM
        embed_dm = discord.Embed(
            title="👢 Você foi expulso!",
            description=f"**Servidor:** {interaction.guild.name}\n**Motivo:** {motivo}",
            color=discord.Color.red()
        )
        await membro.send(embed=embed_dm)
    except:
        pass
    
    await membro.kick(reason=motivo)
    
    embed = discord.Embed(
        title="👢 Membro Expulso",
        description=f"**Membro:** {membro.mention} ({membro.id})\n**Motivo:** {motivo}\n**Moderador:** {interaction.user.mention}",
        color=discord.Color.red(),
        timestamp=datetime.now()
    )
    
    await interaction.response.send_message(embed=embed)
    
    # Log
    log_channel = discord.utils.get(interaction.guild.text_channels, name="logs")
    if log_channel:
        await log_channel.send(embed=embed)

@bot.tree.command(name="ban", description="🔨 Banir membro do servidor")
@app_commands.describe(membro="Membro a ser banido", motivo="Motivo do banimento", dias_mensagens="Dias de mensagens para apagar")
@app_commands.default_permissions(ban_members=True)
async def ban(interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não especificado", dias_mensagens: int = 0):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se banir!", ephemeral=True)
        return
    
    if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Você não pode banir alguém com cargo maior ou igual ao seu!", ephemeral=True)
        return
    
    try:
        embed_dm = discord.Embed(
            title="🔨 Você foi banido!",
            description=f"**Servidor:** {interaction.guild.name}\n**Motivo:** {motivo}",
            color=discord.Color.dark_red()
        )
        await membro.send(embed=embed_dm)
    except:
        pass
    
    await membro.ban(reason=motivo, delete_message_days=dias_mensagens)
    
    embed = discord.Embed(
        title="🔨 Membro Banido",
        description=f"**Membro:** {membro.mention} ({membro.id})\n**Motivo:** {motivo}\n**Moderador:** {interaction.user.mention}",
        color=discord.Color.dark_red(),
        timestamp=datetime.now()
    )
    
    await interaction.response.send_message(embed=embed)
    
    log_channel = discord.utils.get(interaction.guild.text_channels, name="logs")
    if log_channel:
        await log_channel.send(embed=embed)

@bot.tree.command(name="unban", description="🔓 Desbanir usuário")
@app_commands.describe(user_id="ID do usuário para desbanir")
@app_commands.default_permissions(ban_members=True)
async def unban(interaction: discord.Interaction, user_id: str):
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        
        embed = discord.Embed(
            title="🔓 Usuário Desbanido",
            description=f"**Usuário:** {user.mention} ({user.id})\n**Moderador:** {interaction.user.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
        
    except discord.NotFound:
        await interaction.response.send_message("❌ Usuário não encontrado ou não está banido!", ephemeral=True)
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

@bot.tree.command(name="timeout", description="⏰ Mutar temporariamente um membro")
@app_commands.describe(
    membro="Membro para mutar",
    duracao="Duração em minutos (máx 40320)",
    motivo="Motivo do mute"
)
@app_commands.default_permissions(moderate_members=True)
async def timeout(interaction: discord.Interaction, membro: discord.Member, duracao: int, motivo: str = "Não especificado"):
    if membro == interaction.user:
        await interaction.response.send_message("❌ Você não pode se mutar!", ephemeral=True)
        return
    
    if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Você não pode mutar alguém com cargo maior ou igual ao seu!", ephemeral=True)
        return
    
    if duracao > 40320:  # 28 dias em minutos
        await interaction.response.send_message("❌ Duração máxima é 40320 minutos (28 dias)!", ephemeral=True)
        return
    
    until = discord.utils.utcnow() + timedelta(minutes=duracao)
    
    try:
        await membro.timeout(until, reason=motivo)
        
        embed = discord.Embed(
            title="⏰ Membro Silenciado",
            description=f"**Membro:** {membro.mention}\n**Duração:** {duracao} minutos\n**Motivo:** {motivo}\n**Moderador:** {interaction.user.mention}",
            color=discord.Color.orange(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

@bot.tree.command(name="untimeout", description="🔊 Remover mute de um membro")
@app_commands.describe(membro="Membro para desmutar")
@app_commands.default_permissions(moderate_members=True)
async def untimeout(interaction: discord.Interaction, membro: discord.Member):
    try:
        await membro.timeout(None)
        
        embed = discord.Embed(
            title="🔊 Membro Desmutado",
            description=f"**Membro:** {membro.mention}\n**Moderador:** {interaction.user.mention}",
            color=discord.Color.green(),
            timestamp=datetime.now()
        )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="⚠️ Avisar um membro")
@app_commands.describe(membro="Membro para avisar", motivo="Motivo do aviso")
@app_commands.default_permissions(moderate_members=True)
async def warn(interaction: discord.Interaction, membro: discord.Member, motivo: str):
    guild_id = str(interaction.guild.id)
    user_id = str(membro.id)
    
    if guild_id not in bot.warnings:
        bot.warnings[guild_id] = {}
    
    if user_id not in bot.warnings[guild_id]:
        bot.warnings[guild_id][user_id] = []
    
    warn_data = {
        'moderator_id': str(interaction.user.id),
        'reason': motivo,
        'date': datetime.now().isoformat()
    }
    
    bot.warnings[guild_id][user_id].append(warn_data)
    bot.save_data()
    
    warn_count = len(bot.warnings[guild_id][user_id])
    
    embed = discord.Embed(
        title="⚠️ Aviso Registrado",
        description=f"**Membro:** {membro.mention}\n**Motivo:** {motivo}\n**Total de avisos:** {warn_count}\n**Moderador:** {interaction.user.mention}",
        color=discord.Color.yellow(),
        timestamp=datetime.now()
    )
    
    await interaction.response.send_message(embed=embed)
    
    try:
        embed_dm = discord.Embed(
            title="⚠️ Você recebeu um aviso!",
            description=f"**Servidor:** {interaction.guild.name}\n**Motivo:** {motivo}\n**Total de avisos:** {warn_count}",
            color=discord.Color.yellow()
        )
        await membro.send(embed=embed_dm)
    except:
        pass
    
    # Ações automáticas baseadas no número de avisos
    if warn_count >= 5:
        try:
            await membro.ban(reason="5 avisos acumulados")
            await interaction.channel.send(f"🔨 {membro.mention} foi banido automaticamente por acumular 5 avisos!")
        except:
            pass
    elif warn_count >= 3:
        try:
            until = discord.utils.utcnow() + timedelta(hours=24)
            await membro.timeout(until, reason="3 avisos acumulados")
            await interaction.channel.send(f"⏰ {membro.mention} foi mutado automaticamente por 24h por acumular 3 avisos!")
        except:
            pass

@bot.tree.command(name="warnings", description="📋 Ver avisos de um membro")
@app_commands.describe(membro="Membro para ver os avisos")
async def warnings(interaction: discord.Interaction, membro: discord.Member):
    guild_id = str(interaction.guild.id)
    user_id = str(membro.id)
    
    if guild_id not in bot.warnings or user_id not in bot.warnings[guild_id] or not bot.warnings[guild_id][user_id]:
        await interaction.response.send_message(f"✅ {membro.mention} não tem nenhum aviso!", ephemeral=True)
        return
    
    warns = bot.warnings[guild_id][user_id]
    
    embed = discord.Embed(
        title=f"📋 Avisos de {membro.display_name}",
        description=f"Total: **{len(warns)}** aviso(s)",
        color=discord.Color.orange()
    )
    
    for i, warn in enumerate(warns[-10:], 1):
        mod = interaction.guild.get_member(int(warn['moderator_id']))
        data = datetime.fromisoformat(warn['date']).strftime("%d/%m/%Y %H:%M")
        embed.add_field(
            name=f"Aviso #{i}",
            value=f"**Motivo:** {warn['reason']}\n**Moderador:** {mod.mention if mod else 'Desconhecido'}\n**Data:** {data}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove_warn", description="🗑️ Remover um aviso específico")
@app_commands.describe(membro="Membro", warn_number="Número do aviso (1, 2, 3...)")
@app_commands.default_permissions(moderate_members=True)
async def remove_warn(interaction: discord.Interaction, membro: discord.Member, warn_number: int):
    guild_id = str(interaction.guild.id)
    user_id = str(membro.id)
    
    if guild_id not in bot.warnings or user_id not in bot.warnings[guild_id]:
        await interaction.response.send_message("❌ Este membro não tem avisos!", ephemeral=True)
        return
    
    warns = bot.warnings[guild_id][user_id]
    
    if warn_number < 1 or warn_number > len(warns):
        await interaction.response.send_message(f"❌ Número inválido! Use entre 1 e {len(warns)}", ephemeral=True)
        return
    
    removed = warns.pop(warn_number - 1)
    bot.save_data()
    
    embed = discord.Embed(
        title="🗑️ Aviso Removido",
        description=f"**Membro:** {membro.mention}\n**Motivo removido:** {removed['reason']}\n**Avisos restantes:** {len(warns)}",
        color=discord.Color.green()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="lock", description="🔒 Trancar um canal")
@app_commands.describe(canal="Canal para trancar (padrão: atual)")
@app_commands.default_permissions(manage_channels=True)
async def lock(interaction: discord.Interaction, canal: Optional[discord.TextChannel] = None):
    if canal is None:
        canal = interaction.channel
    
    try:
        overwrite = canal.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = False
        await canal.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        
        embed = discord.Embed(
            title="🔒 Canal Trancado",
            description=f"{canal.mention} foi trancado por {interaction.user.mention}",
            color=discord.Color.red()
        )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

@bot.tree.command(name="unlock", description="🔓 Destrancar um canal")
@app_commands.describe(canal="Canal para destrancar (padrão: atual)")
@app_commands.default_permissions(manage_channels=True)
async def unlock(interaction: discord.Interaction, canal: Optional[discord.TextChannel] = None):
    if canal is None:
        canal = interaction.channel
    
    try:
        overwrite = canal.overwrites_for(interaction.guild.default_role)
        overwrite.send_messages = None
        await canal.set_permissions(interaction.guild.default_role, overwrite=overwrite)
        
        embed = discord.Embed(
            title="🔓 Canal Destrancado",
            description=f"{canal.mention} foi destrancado por {interaction.user.mention}",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

@bot.tree.command(name="slowmode", description="🐌 Ativar modo lento no canal")
@app_commands.describe(segundos="Segundos entre mensagens (0 para desativar)")
@app_commands.default_permissions(manage_channels=True)
async def slowmode(interaction: discord.Interaction, segundos: int):
    if segundos < 0 or segundos > 21600:
        await interaction.response.send_message("❌ Segundos deve ser entre 0 e 21600 (6 horas)!", ephemeral=True)
        return
    
    try:
        await interaction.channel.edit(slowmode_delay=segundos)
        
        if segundos > 0:
            embed = discord.Embed(
                title="🐌 Modo Lento Ativado",
                description=f"Usuários agora podem enviar mensagem a cada **{segundos} segundos**",
                color=discord.Color.blue()
            )
        else:
            embed = discord.Embed(
                title="🐌 Modo Lento Desativado",
                description="Canal voltou ao normal",
                color=discord.Color.green()
            )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

@bot.tree.command(name="nick", description="✏️ Mudar apelido de um membro")
@app_commands.describe(membro="Membro", novo_apelido="Novo apelido")
@app_commands.default_permissions(manage_nicknames=True)
async def nick(interaction: discord.Interaction, membro: discord.Member, novo_apelido: str):
    if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Você não pode mudar apelido de alguém com cargo maior ou igual ao seu!", ephemeral=True)
        return
    
    try:
        antigo = membro.display_name
        await membro.edit(nick=novo_apelido)
        
        embed = discord.Embed(
            title="✏️ Apelido Alterado",
            description=f"**Membro:** {membro.mention}\n**Antigo:** {antigo}\n**Novo:** {novo_apelido}",
            color=discord.Color.blue()
        )
        
        await interaction.response.send_message(embed=embed)
        
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}", ephemeral=True)

# ===== SISTEMA DE MÚSICA (NOVO) =====

class MusicPlayer:
    def __init__(self, bot, guild_id):
        self.bot = bot
        self.guild_id = guild_id
        self.queue = []
        self.now_playing = None
        self.loop = False
        self.volume = 0.5
        self.voice_client = None

async def get_youtube_info(query):
    """Busca informações do YouTube"""
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True,
        'extract_flat': True
    }
    
    with youtube_dl.YoutubeDL(ydl_opts) as ydl:
        try:
            if query.startswith('http'):
                info = ydl.extract_info(query, download=False)
                return {
                    'title': info.get('title', 'Desconhecido'),
                    'url': info['url'] if 'url' in info else info.get('webpage_url', query),
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', '')
                }
            else:
                info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
                return {
                    'title': info.get('title', 'Desconhecido'),
                    'url': info['webpage_url'],
                    'duration': info.get('duration', 0),
                    'thumbnail': info.get('thumbnail', '')
                }
        except Exception as e:
            print(f"Erro ao buscar música: {e}")
            return None

class MusicControls(View):
    def __init__(self, guild_id):
        super().__init__(timeout=300)
        self.guild_id = guild_id
    
    @discord.ui.button(label="⏸️", style=discord.ButtonStyle.secondary)
    async def pause_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Você não está em um canal de voz!", ephemeral=True)
            return
        
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸️ Música pausada!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhuma música tocando!", ephemeral=True)
    
    @discord.ui.button(label="▶️", style=discord.ButtonStyle.success)
    async def resume_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Você não está em um canal de voz!", ephemeral=True)
            return
        
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶️ Música continuada!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhuma música pausada!", ephemeral=True)
    
    @discord.ui.button(label="⏭️", style=discord.ButtonStyle.primary)
    async def skip_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Você não está em um canal de voz!", ephemeral=True)
            return
        
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("⏭️ Música pulada!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Nenhuma música tocando!", ephemeral=True)
    
    @discord.ui.button(label="⏹️", style=discord.ButtonStyle.danger)
    async def stop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.voice or not interaction.user.voice.channel:
            await interaction.response.send_message("❌ Você não está em um canal de voz!", ephemeral=True)
            return
        
        voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
        if voice_client:
            bot.music_queues[interaction.guild.id] = []
            if voice_client.is_playing():
                voice_client.stop()
            await voice_client.disconnect()
            await interaction.response.send_message("⏹️ Player parado e desconectado!", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Não estou em um canal de voz!", ephemeral=True)
    
    @discord.ui.button(label="🔁", style=discord.ButtonStyle.secondary)
    async def loop_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild.id not in bot.music_loops:
            bot.music_loops[interaction.guild.id] = False
        
        bot.music_loops[interaction.guild.id] = not bot.music_loops[interaction.guild.id]
        status = "ativado" if bot.music_loops[interaction.guild.id] else "desativado"
        
        await interaction.response.send_message(f"🔁 Loop {status}!", ephemeral=True)

async def play_next(guild_id, channel):
    """Toca a próxima música na fila"""
    if guild_id not in bot.music_queues or not bot.music_queues[guild_id]:
        return
    
    if bot.music_loops.get(guild_id, False) and bot.now_playing.get(guild_id):
        # Se loop está ativado, coloca a música atual de volta na fila
        bot.music_queues[guild_id].insert(0, bot.now_playing[guild_id])
    
    if not bot.music_queues[guild_id]:
        return
    
    next_song = bot.music_queues[guild_id].pop(0)
    bot.now_playing[guild_id] = next_song
    
    voice_client = discord.utils.get(bot.voice_clients, guild_id=guild_id)
    if not voice_client:
        return
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'quiet': True,
        'no_warnings': True
    }
    
    try:
        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(next_song['url'], download=False)
            url2 = info['formats'][0]['url'] if 'formats' in info else info['url']
        
        volume = bot.music_volumes.get(guild_id, 0.5)
        
        ffmpeg_options = {
            'before_options': '-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5',
            'options': f'-vn -filter:a "volume={volume}"'
        }
        
        source = await discord.FFmpegOpusAudio.from_probe(url2, **ffmpeg_options)
        
        def after_playing(error):
            if error:
                print(f"Erro ao tocar: {error}")
            asyncio.run_coroutine_threadsafe(play_next(guild_id, channel), bot.loop)
        
        voice_client.play(source, after=after_playing)
        
        embed = discord.Embed(
            title="🎵 Tocando Agora",
            description=f"**{next_song['title']}**",
            color=discord.Color.green()
        )
        
        if next_song.get('duration'):
            minutos = next_song['duration'] // 60
            segundos = next_song['duration'] % 60
            embed.add_field(name="⏱️ Duração", value=f"{minutos}:{segundos:02d}", inline=True)
        
        if next_song.get('thumbnail'):
            embed.set_thumbnail(url=next_song['thumbnail'])
        
        embed.add_field(name="📊 Fila", value=f"{len(bot.music_queues[guild_id])} músicas", inline=True)
        
        await channel.send(embed=embed, view=MusicControls(guild_id))
        
    except Exception as e:
        print(f"Erro ao tocar música: {e}")
        await channel.send(f"❌ Erro ao tocar música: {e}")
        await play_next(guild_id, channel)

@bot.tree.command(name="play", description="🎵 Tocar uma música do YouTube")
@app_commands.describe(pesquisa="Nome da música ou URL do YouTube")
async def play(interaction: discord.Interaction, pesquisa: str):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ Você precisa estar em um canal de voz!", ephemeral=True)
        return
    
    voice_channel = interaction.user.voice.channel
    guild_id = interaction.guild.id
    
    await interaction.response.defer()
    
    # Busca a música
    song_info = await get_youtube_info(pesquisa)
    if not song_info:
        await interaction.followup.send("❌ Não foi possível encontrar a música!")
        return
    
    # Conecta ao canal de voz se não estiver conectado
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if not voice_client:
        voice_client = await voice_channel.connect()
        bot.voice_clients[guild_id] = voice_client
    
    # Inicializa fila se necessário
    if guild_id not in bot.music_queues:
        bot.music_queues[guild_id] = []
    
    # Adiciona à fila
    bot.music_queues[guild_id].append(song_info)
    posicao = len(bot.music_queues[guild_id])
    
    embed = discord.Embed(
        title="🎵 Adicionado à Fila",
        description=f"**{song_info['title']}**",
        color=discord.Color.blue()
    )
    
    if song_info.get('duration'):
        minutos = song_info['duration'] // 60
        segundos = song_info['duration'] % 60
        embed.add_field(name="⏱️ Duração", value=f"{minutos}:{segundos:02d}", inline=True)
    
    embed.add_field(name="📊 Posição", value=f"#{posicao}", inline=True)
    
    if song_info.get('thumbnail'):
        embed.set_thumbnail(url=song_info['thumbnail'])
    
    await interaction.followup.send(embed=embed)
    
    # Se não está tocando nada, começa a tocar
    if not voice_client.is_playing():
        await play_next(guild_id, interaction.channel)

@bot.tree.command(name="queue", description="📋 Ver fila de músicas")
async def queue(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    
    if guild_id not in bot.music_queues or not bot.music_queues[guild_id]:
        await interaction.response.send_message("📋 A fila está vazia!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📋 Fila de Músicas",
        description=f"Total: **{len(bot.music_queues[guild_id])}** músicas",
        color=discord.Color.blue()
    )
    
    if guild_id in bot.now_playing and bot.now_playing[guild_id]:
        atual = bot.now_playing[guild_id]
        embed.add_field(
            name="🎵 Tocando Agora",
            value=f"**{atual['title']}**",
            inline=False
        )
    
    queue_list = ""
    for i, song in enumerate(bot.music_queues[guild_id][:10], 1):
        queue_list += f"{i}. {song['title'][:50]}...\n"
    
    if queue_list:
        embed.add_field(name="📊 Próximas", value=queue_list, inline=False)
    
    if len(bot.music_queues[guild_id]) > 10:
        embed.set_footer(text=f"E mais {len(bot.music_queues[guild_id]) - 10} músicas...")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="skip", description="⏭️ Pular música atual")
async def skip(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ Você precisa estar em um canal de voz!", ephemeral=True)
        return
    
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ Não há música tocando!", ephemeral=True)
        return
    
    voice_client.stop()
    await interaction.response.send_message("⏭️ Música pulada!")

@bot.tree.command(name="stop", description="⏹️ Parar música e limpar fila")
async def stop(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ Você precisa estar em um canal de voz!", ephemeral=True)
        return
    
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if not voice_client:
        await interaction.response.send_message("❌ Não estou em um canal de voz!", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    bot.music_queues[guild_id] = []
    
    if voice_client.is_playing():
        voice_client.stop()
    
    await voice_client.disconnect()
    await interaction.response.send_message("⏹️ Player parado e desconectado!")

@bot.tree.command(name="pause", description="⏸️ Pausar música")
async def pause(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ Você precisa estar em um canal de voz!", ephemeral=True)
        return
    
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if not voice_client or not voice_client.is_playing():
        await interaction.response.send_message("❌ Não há música tocando!", ephemeral=True)
        return
    
    voice_client.pause()
    await interaction.response.send_message("⏸️ Música pausada!")

@bot.tree.command(name="resume", description="▶️ Continuar música")
async def resume(interaction: discord.Interaction):
    if not interaction.user.voice:
        await interaction.response.send_message("❌ Você precisa estar em um canal de voz!", ephemeral=True)
        return
    
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if not voice_client or not voice_client.is_paused():
        await interaction.response.send_message("❌ Não há música pausada!", ephemeral=True)
        return
    
    voice_client.resume()
    await interaction.response.send_message("▶️ Música continuada!")

@bot.tree.command(name="volume", description="🔊 Ajustar volume")
@app_commands.describe(nivel="Nível de volume (0-100)")
async def volume(interaction: discord.Interaction, nivel: int):
    if nivel < 0 or nivel > 100:
        await interaction.response.send_message("❌ Volume deve ser entre 0 e 100!", ephemeral=True)
        return
    
    guild_id = interaction.guild.id
    bot.music_volumes[guild_id] = nivel / 100
    
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    
    if voice_client and voice_client.source:
        # Nota: Não é possível mudar volume dinamicamente no Discord.py facilmente
        pass
    
    await interaction.response.send_message(f"🔊 Volume ajustado para {nivel}%")

@bot.tree.command(name="loop", description="🔁 Ativar/desativar loop da música atual")
async def loop(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    
    if guild_id not in bot.music_loops:
        bot.music_loops[guild_id] = False
    
    bot.music_loops[guild_id] = not bot.music_loops[guild_id]
    status = "ativado" if bot.music_loops[guild_id] else "desativado"
    
    await interaction.response.send_message(f"🔁 Loop {status}!")

@bot.tree.command(name="nowplaying", description="🎵 Ver música atual")
async def nowplaying(interaction: discord.Interaction):
    guild_id = interaction.guild.id
    
    if guild_id not in bot.now_playing or not bot.now_playing[guild_id]:
        await interaction.response.send_message("❌ Não há música tocando no momento!", ephemeral=True)
        return
    
    song = bot.now_playing[guild_id]
    
    embed = discord.Embed(
        title="🎵 Tocando Agora",
        description=f"**{song['title']}**",
        color=discord.Color.green()
    )
    
    if song.get('duration'):
        minutos = song['duration'] // 60
        segundos = song['duration'] % 60
        embed.add_field(name="⏱️ Duração", value=f"{minutos}:{segundos:02d}", inline=True)
    
    if song.get('thumbnail'):
        embed.set_thumbnail(url=song['thumbnail'])
    
    voice_client = discord.utils.get(bot.voice_clients, guild=interaction.guild)
    if voice_client and voice_client.is_playing():
        embed.add_field(name="📊 Status", value="▶️ Tocando", inline=True)
    elif voice_client and voice_client.is_paused():
        embed.add_field(name="📊 Status", value="⏸️ Pausado", inline=True)
    
    await interaction.response.send_message(embed=embed)

# ===== SISTEMA DE UTILIDADE (NOVO) =====

@bot.tree.command(name="lembrete", description="⏰ Criar um lembrete")
@app_commands.describe(
    tempo="Tempo (ex: 10m, 1h, 2d, 30s)",
    mensagem="Mensagem do lembrete"
)
async def lembrete(interaction: discord.Interaction, tempo: str, mensagem: str):
    # Converte tempo para segundos
    try:
        if tempo.endswith('s'):
            segundos = int(tempo[:-1])
        elif tempo.endswith('m'):
            segundos = int(tempo[:-1]) * 60
        elif tempo.endswith('h'):
            segundos = int(tempo[:-1]) * 3600
        elif tempo.endswith('d'):
            segundos = int(tempo[:-1]) * 86400
        else:
            segundos = int(tempo)
    except:
        await interaction.response.send_message("❌ Formato inválido! Use: 30s, 10m, 1h, 2d", ephemeral=True)
        return
    
    if segundos < 10 or segundos > 2592000:  # 30 dias máximo
        await interaction.response.send_message("❌ Tempo deve ser entre 10 segundos e 30 dias!", ephemeral=True)
        return
    
    remind_time = datetime.now() + timedelta(seconds=segundos)
    
    reminder = {
        'id': len(bot.reminders) + 1,
        'user_id': str(interaction.user.id),
        'channel_id': str(interaction.channel.id),
        'message': mensagem,
        'remind_time': remind_time
    }
    
    bot.reminders.append(reminder)
    bot.save_data()
    
    tempo_formatado = ""
    if segundos >= 86400:
        tempo_formatado = f"{segundos//86400}d {segundos%86400//3600}h"
    elif segundos >= 3600:
        tempo_formatado = f"{segundos//3600}h {segundos%3600//60}m"
    elif segundos >= 60:
        tempo_formatado = f"{segundos//60}m {segundos%60}s"
    else:
        tempo_formatado = f"{segundos}s"
    
    embed = discord.Embed(
        title="⏰ Lembrete Criado!",
        description=f"**Mensagem:** {mensagem}\n**Tempo:** {tempo_formatado}\n**Quando:** {remind_time.strftime('%d/%m/%Y %H:%M:%S')}",
        color=discord.Color.blue()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="clima", description="☀️ Ver clima de uma cidade")
@app_commands.describe(cidade="Nome da cidade")
async def clima(interaction: discord.Interaction, cidade: str):
    # Usando wttr.in (não precisa de API key)
    await interaction.response.defer()
    
    try:
        async with aiohttp.ClientSession() as session:
            # Versão simplificada do clima
            url = f"https://wttr.in/{cidade}?format=%c+%t+%w+%h"
            async with session.get(url) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    
                    embed = discord.Embed(
                        title=f"☀️ Clima em {cidade.title()}",
                        description=f"```{text}```",
                        color=discord.Color.blue()
                    )
                    embed.set_footer(text="Fonte: wttr.in")
                    
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("❌ Cidade não encontrada!")
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao buscar clima: {e}")

@bot.tree.command(name="traduzir", description="🌐 Traduzir texto")
@app_commands.describe(
    texto="Texto para traduzir",
    idioma="Idioma destino (ex: pt, en, es, fr)"
)
async def traduzir(interaction: discord.Interaction, texto: str, idioma: str):
    await interaction.response.defer()
    
    idiomas = {
        'pt': 'português', 'en': 'inglês', 'es': 'espanhol', 'fr': 'francês',
        'de': 'alemão', 'it': 'italiano', 'ja': 'japonês', 'ko': 'coreano',
        'zh': 'chinês', 'ru': 'russo'
    }
    
    if idioma not in idiomas:
        await interaction.followup.send(f"❌ Idiomas disponíveis: {', '.join(idiomas.keys())}")
        return
    
    try:
        # Usando API gratuita (my memory)
        url = f"https://api.mymemory.translated.net/get?q={texto}&langpair=auto|{idioma}"
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                data = await resp.json()
                traducao = data['responseData']['translatedText']
                
                embed = discord.Embed(
                    title="🌐 Tradução",
                    color=discord.Color.blue()
                )
                embed.add_field(name="📝 Original", value=texto[:1024], inline=False)
                embed.add_field(name=f"📝 Tradução ({idiomas[idioma]})", value=traducao[:1024], inline=False)
                
                await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao traduzir: {e}")

@bot.tree.command(name="cep", description="📮 Buscar endereço por CEP")
@app_commands.describe(cep="CEP (apenas números)")
async def cep(interaction: discord.Interaction, cep: str):
    cep = cep.replace("-", "").strip()
    
    if not cep.isdigit() or len(cep) != 8:
        await interaction.response.send_message("❌ CEP inválido! Use 8 números.", ephemeral=True)
        return
    
    await interaction.response.defer()
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://viacep.com.br/ws/{cep}/json/"
            async with session.get(url) as resp:
                data = await resp.json()
                
                if "erro" in data:
                    await interaction.followup.send("❌ CEP não encontrado!")
                    return
                
                embed = discord.Embed(
                    title=f"📮 CEP {cep}",
                    color=discord.Color.blue()
                )
                
                embed.add_field(name="Logradouro", value=data.get('logradouro', 'N/A'), inline=False)
                embed.add_field(name="Bairro", value=data.get('bairro', 'N/A'), inline=True)
                embed.add_field(name="Cidade", value=data.get('localidade', 'N/A'), inline=True)
                embed.add_field(name="UF", value=data.get('uf', 'N/A'), inline=True)
                embed.add_field(name="DDD", value=data.get('ddd', 'N/A'), inline=True)
                
                await interaction.followup.send(embed=embed)
    except Exception as e:
        await interaction.followup.send(f"❌ Erro ao buscar CEP: {e}")

@bot.tree.command(name="aniversario_membro", description="🎂 Registrar seu aniversário")
@app_commands.describe(
    dia="Dia do nascimento (1-31)",
    mes="Mês do nascimento (1-12)",
    ano="Ano de nascimento (opcional)"
)
async def aniversario_membro(interaction: discord.Interaction, dia: int, mes: int, ano: Optional[int] = None):
    if dia < 1 or dia > 31 or mes < 1 or mes > 12:
        await interaction.response.send_message("❌ Dia ou mês inválido!", ephemeral=True)
        return
    
    if ano and (ano < 1900 or ano > datetime.now().year):
        await interaction.response.send_message("❌ Ano inválido!", ephemeral=True)
        return
    
    user_id = str(interaction.user.id)
    
    bot.birthdays[user_id] = {
        'day': dia,
        'month': mes,
        'year': ano
    }
    
    bot.save_data()
    
    data_str = f"{dia:02d}/{mes:02d}"
    if ano:
        data_str += f"/{ano}"
    
    embed = discord.Embed(
        title="🎂 Aniversário Registrado!",
        description=f"Sua data de aniversário foi registrada como **{data_str}**",
        color=discord.Color.gold()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="aniversarios_hoje", description="🎉 Ver quem faz aniversário hoje")
async def aniversarios_hoje(interaction: discord.Interaction):
    hoje = datetime.now()
    aniversariantes = []
    
    for user_id, data in bot.birthdays.items():
        if data['month'] == hoje.month and data['day'] == hoje.day:
            member = interaction.guild.get_member(int(user_id))
            if member:
                idade = hoje.year - data.get('year', hoje.year) if data.get('year') else None
                aniversariantes.append((member, idade))
    
    if not aniversariantes:
        await interaction.response.send_message("📅 Ninguém faz aniversário hoje!")
        return
    
    embed = discord.Embed(
        title="🎉 Aniversariantes do Dia",
        description=f"Hoje é dia {hoje.strftime('%d/%m')}",
        color=discord.Color.gold()
    )
    
    for member, idade in aniversariantes:
        texto = member.mention
        if idade:
            texto += f" (completa {idade} anos)"
        embed.add_field(name="🎂", value=texto, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="lembretes", description="📋 Ver seus lembretes ativos")
async def lembretes(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    user_reminders = [r for r in bot.reminders if r['user_id'] == user_id]
    
    if not user_reminders:
        await interaction.response.send_message("📋 Você não tem lembretes ativos!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title="📋 Seus Lembretes",
        color=discord.Color.blue()
    )
    
    for reminder in user_reminders[:10]:
        tempo_restante = reminder['remind_time'] - datetime.now()
        if tempo_restante.total_seconds() > 0:
            horas = tempo_restante.total_seconds() // 3600
            minutos = (tempo_restante.total_seconds() % 3600) // 60
            
            if horas > 0:
                tempo_str = f"{int(horas)}h {int(minutos)}m"
            else:
                tempo_str = f"{int(minutos)}m"
            
            embed.add_field(
                name=f"ID: {reminder['id']}",
                value=f"**{reminder['message']}**\n⏰ Em {tempo_str}",
                inline=False
            )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remover_lembrete", description="🗑️ Remover um lembrete")
@app_commands.describe(id_lembrete="ID do lembrete (use /lembretes)")
async def remover_lembrete(interaction: discord.Interaction, id_lembrete: int):
    user_id = str(interaction.user.id)
    
    for reminder in bot.reminders:
        if reminder['id'] == id_lembrete and reminder['user_id'] == user_id:
            bot.reminders.remove(reminder)
            bot.save_data()
            await interaction.response.send_message(f"✅ Lembrete {id_lembrete} removido!")
            return
    
    await interaction.response.send_message("❌ Lembrete não encontrado!", ephemeral=True)

# ===== SISTEMA CRIATIVO (NOVO) =====

@bot.tree.command(name="frase", description="💭 Frase motivacional do dia")
async def frase(interaction: discord.Interaction):
    frase = random.choice(bot.daily_phrases)
    
    embed = discord.Embed(
        title="💭 Frase do Dia",
        description=frase,
        color=discord.Color.gold()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pensamento", description="🤔 Pensamento aleatório")
async def pensamento(interaction: discord.Interaction):
    pensamentos = [
        "🤔 Será que os peixes têm sede?",
        "🤔 Se um elétron não pode ser observado, como sabemos que ele existe?",
        "🤔 Se o tempo é relativo, por que temos pressa?",
        "🤔 O que veio primeiro: o ovo ou a galinha?",
        "🤔 Se nada dura para sempre, será que essa frase dura?",
        "🤔 Por que chamamos de 'descansar' quando vamos dormir, se o cérebro continua trabalhando?",
        "🤔 Se você está lendo isso, quem está pensando agora?",
        "🤔 O amanhã é realmente amanhã se você pensar nele hoje?"
    ]
    
    embed = discord.Embed(
        title="🤔 Pensamento do Momento",
        description=random.choice(pensamentos),
        color=discord.Color.purple()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="horoscopo", description="🔮 Horóscopo do dia")
@app_commands.describe(signo="Seu signo")
async def horoscopo(interaction: discord.Interaction, signo: str):
    signos_validos = ["áries", "touro", "gêmeos", "câncer", "leão", "virgem", 
                      "libra", "escorpião", "sagitário", "capricórnio", "aquário", "peixes"]
    
    if signo.lower() not in signos_validos:
        await interaction.response.send_message(f"❌ Signos válidos: {', '.join(signos_validos)}")
        return
    
    previsoes = [
        "🌟 Hoje é um ótimo dia para novos começos!",
        "💖 O amor está no ar, fique atento aos sinais!",
        "💰 Boas notícias financeiras podem chegar!",
        "🤝 Parcerias serão favorecidas hoje!",
        "🧘 Tire um tempo para cuidar de você!",
        "🎯 Foco nos objetivos, você está no caminho certo!",
        "🌈 Aproveite as pequenas alegrias do dia!",
        "⭐ Alguém especial pode estar pensando em você!"
    ]
    
    cores = {
        'áries': 'Vermelho', 'touro': 'Verde', 'gêmeos': 'Amarelo',
        'câncer': 'Prata', 'leão': 'Laranja', 'virgem': 'Marrom',
        'libra': 'Rosa', 'escorpião': 'Preto', 'sagitário': 'Roxo',
        'capricórnio': 'Cinza', 'aquário': 'Azul', 'peixes': 'Turquesa'
    }
    
    numeros = [random.randint(1, 60) for _ in range(5)]
    
    embed = discord.Embed(
        title=f"🔮 Horóscopo de {signo.title()}",
        description=random.choice(previsoes),
        color=discord.Color.blue()
    )
    
    embed.add_field(name="🎨 Cor do dia", value=cores.get(signo.lower(), 'Arco-íris'), inline=True)
    embed.add_field(name="🔢 Números da sorte", value=', '.join(str(n) for n in numeros), inline=True)
    embed.set_footer(text="Use /signos para ver compatibilidade")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="charada", description="❓ Receba uma charada")
async def charada(interaction: discord.Interaction):
    charada = random.choice(bot.riddles)
    
    embed = discord.Embed(
        title="❓ Charada",
        description=charada['pergunta'],
        color=discord.Color.blue()
    )
    
    await interaction.response.send_message(embed=embed)
    
    # Espera 15 segundos e revela a resposta
    await asyncio.sleep(15)
    
    resposta_embed = discord.Embed(
        title="❓ Resposta",
        description=f"||{charada['resposta']}||",
        color=discord.Color.green()
    )
    
    await interaction.channel.send(embed=resposta_embed)

@bot.tree.command(name="piada", description="😂 Piada aleatória")
async def piada(interaction: discord.Interaction):
    await interaction.response.send_message(f"😂 {random.choice(bot.jokes)}")

@bot.tree.command(name="fato", description="🔍 Fato curioso")
async def fato(interaction: discord.Interaction):
    await interaction.response.send_message(f"🔍 {random.choice(bot.fun_facts)}")

@bot.tree.command(name="conselho", description="💡 Conselho aleatório")
async def conselho(interaction: discord.Interaction):
    conselhos = [
        "💡 Beba água! A hidratação é importante!",
        "💡 Durma pelo menos 8 horas por noite!",
        "💡 Pratique exercícios regularmente!",
        "💡 Leia um livro esse mês!",
        "💡 Ligue para alguém que você ama!",
        "💡 Aprenda algo novo todo dia!",
        "💡 Guarde dinheiro para o futuro!",
        "💡 Seja gentil com você mesmo!",
        "💡 Não se compare aos outros!",
        "💡 Celebre suas pequenas vitórias!"
    ]
    
    await interaction.response.send_message(random.choice(conselhos))

@bot.tree.command(name="8ball", description="🎱 Pergunte ao destino")
async def eight_ball(interaction: discord.Interaction, pergunta: str):
    respostas = [
        "Sim!", "Não!", "Talvez...", "Com certeza!", "Nem pensar!",
        "Os deuses dizem que sim!", "Melhor não dizer agora.", "Pode confiar!",
        "Minhas fontes dizem que sim!", "Perspectiva boa!", "Sinais apontam que sim!",
        "Muito duvidoso...", "Provavelmente!", "Não conte com isso!"
    ]
    
    embed = discord.Embed(
        title="🎱 8Ball",
        description=f"**Pergunta:** {pergunta}\n**Resposta:** {random.choice(respostas)}",
        color=discord.Color.purple()
    )
    
    await interaction.response.send_message(embed=embed)

# ===== COMANDOS BÁSICOS (Mantidos) =====

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
    
    if membro.premium_since:
        embed.add_field(name="💎 Booster desde", value=membro.premium_since.strftime("%d/%m/%Y"), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="serverinfo", description="📊 Informações do servidor")
async def serverinfo(interaction: discord.Interaction):
    guild = interaction.guild
    embed = discord.Embed(title=f"Info: {guild.name}", color=discord.Color.blue())
    
    if guild.icon:
        embed.set_thumbnail(url=guild.icon.url)
    
    total_membros = guild.member_count
    bots = len([m for m in guild.members if m.bot])
    humanos = total_membros - bots
    
    embed.add_field(name="ID", value=guild.id, inline=True)
    embed.add_field(name="Dono", value=guild.owner.mention, inline=True)
    embed.add_field(name="Membros", value=f"👤 Humanos: {humanos}\n🤖 Bots: {bots}\n📊 Total: {total_membros}", inline=True)
    embed.add_field(name="Canais", value=len(guild.channels), inline=True)
    embed.add_field(name="Cargos", value=len(guild.roles), inline=True)
    embed.add_field(name="Emojis", value=len(guild.emojis), inline=True)
    embed.add_field(name="Boost", value=f"Nível {guild.premium_tier}\n{guild.premium_subscription_count} boosts", inline=True)
    embed.add_field(name="Criado em", value=guild.created_at.strftime("%d/%m/%Y"), inline=True)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="avatar", description="🖼️ Avatar do usuário")
async def avatar(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    if membro is None:
        membro = interaction.user
    
    embed = discord.Embed(title=f"Avatar de {membro.display_name}")
    embed.set_image(url=membro.display_avatar.url)
    
    view = View()
    view.add_item(Button(label="📸 Download", url=membro.display_avatar.url))
    
    await interaction.response.send_message(embed=embed, view=view)

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
        elif operador == "%":
            resultado = num1 % num2
        else:
            await interaction.response.send_message("❌ Operador inválido! Use +, -, *, /, ^, %")
            return
        
        await interaction.response.send_message(f"🧮 Resultado: `{num1} {operador} {num2} = {resultado}`")
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro: {e}")

@bot.tree.command(name="ola_mundo", description="👋 Mensagem de boas vindas")
async def ola_mundo(interaction: discord.Interaction):
    await interaction.response.send_message(f"Olá {interaction.user.mention}! Bem-vindo ao bot Fort! 🎉")

# ===== COMANDOS DE DIVERSÃO COM GIF (Mantidos) =====

gifs_abraco = [
    "https://media.giphy.com/media/3ZnBrkqoaI2hq/giphy.gif",
    "https://media.giphy.com/media/od5H3PmEG5EVq/giphy.gif",
    "https://media.giphy.com/media/lrr9rHuoJOE0w/giphy.gif",
    "https://media.giphy.com/media/13d2jHlSlxklVe/giphy.gif"
]

gifs_beijo = [
    "https://media.giphy.com/media/bGm9FuBCGg4SY/giphy.gif",
    "https://media.giphy.com/media/G3va31oEEnIkM/giphy.gif",
    "https://media.giphy.com/media/12VXIxKaIEarL2/giphy.gif",
    "https://media.giphy.com/media/hnNyVPIXgLdle/giphy.gif"
]

gifs_carinho = [
    "https://media.giphy.com/media/4HP0ddZnNVvKU/giphy.gif",
    "https://media.giphy.com/media/109ltuoSQT212w/giphy.gif",
    "https://media.giphy.com/media/xT0BKiwjg0O6yIR2o/giphy.gif",
    "https://media.giphy.com/media/3o7abpRrPjBne2h2Qw/giphy.gif"
]

gifs_tapa = [
    "https://media.giphy.com/media/uG3lKkAuh53wc/giphy.gif",
    "https://media.giphy.com/media/j3iGKfXRKlLqw/giphy.gif",
    "https://media.giphy.com/media/3oxHQq4M0xGpWpU2g/giphy.gif",
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

# ===== COMANDOS DE JOGOS ADICIONAIS =====

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

# ===== COMANDO DE AJUDA ATUALIZADO =====

@bot.tree.command(name="ajuda", description="📚 Todos os comandos do bot")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Comandos do Bot Fort",
        description="**Sistema Completo - 120+ COMANDOS!**\nUse `/` antes de cada comando",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="📢 **CHAMADAS**",
        value="`/chamada` - Criar chamada\n"
              "`/chamada_info` - Ver informações\n"
              "`/chamada_lista` - Lista completa\n"
              "`/chamada_cancelar` - Cancelar\n"
              "✨ Timing inteligente: meia-noite ou horas definidas",
        inline=False
    )
    
    embed.add_field(
        name="💖 **SHIP & CASAMENTO**",
        value="`/ship` - Calcular amor\n"
              "`/shippar` - Criar ship\n"
              "`/likeship` - Dar like\n"
              "`/topship` - Ranking\n"
              "`/pedir` - Pedir em casamento\n"
              "`/casamento` - Status\n"
              "`/presentear` - Dar presente\n"
              "`/luademel` - Lua de mel",
        inline=True
    )
    
    embed.add_field(
        name="💰 **ECONOMIA**",
        value="`/daily` - Recompensa diária\n"
              "`/saldo` - Ver saldo\n"
              "`/transferir` - Transferir\n"
              "`/slot` - Caça-níqueis\n"
              "`/cara_coroa` - Apostar\n"
              "`/loja_presentes` - Loja\n"
              "`/comprar_presente` - Comprar\n"
              "`/meuspresentes` - Inventário",
        inline=True
    )
    
    embed.add_field(
        name="🛡️ **MODERAÇÃO**",
        value="`/clear` - Limpar mensagens\n"
              "`/kick` - Expulsar\n"
              "`/ban` - Banir\n"
              "`/unban` - Desbanir\n"
              "`/timeout` - Mutar\n"
              "`/warn` - Avisar\n"
              "`/warnings` - Ver avisos\n"
              "`/lock` - Trancar canal\n"
              "`/slowmode` - Modo lento",
        inline=True
    )
    
    embed.add_field(
        name="🎵 **MÚSICA**",
        value="`/play` - Tocar música\n"
              "`/queue` - Ver fila\n"
              "`/skip` - Pular\n"
              "`/stop` - Parar\n"
              "`/pause` - Pausar\n"
              "`/resume` - Continuar\n"
              "`/volume` - Ajustar\n"
              "`/loop` - Repetir",
        inline=True
    )
    
    embed.add_field(
        name="🎭 **INTERAÇÕES**",
        value="`/abraco_gif` - Abraçar\n"
              "`/beijo_gif` - Beijar\n"
              "`/carinho_gif` - Carinho\n"
              "`/tapa` - Dar tapa\n"
              "`/festa` - Fazer festa",
        inline=True
    )
    
    embed.add_field(
        name="🎮 **JOGOS**",
        value="`/dado` - Rolar dado\n"
              "`/dado_rpg` - Dados RPG\n"
              "`/ppt` - Pedra papel\n"
              "`/adivinha` - Adivinhação\n"
              "`/8ball` - Perguntas\n"
              "`/sortear` - Sortear\n"
              "`/enquete` - Criar enquete",
        inline=True
    )
    
    embed.add_field(
        name="🛠️ **UTILIDADE**",
        value="`/lembrete` - Criar lembrete\n"
              "`/clima` - Ver clima\n"
              "`/traduzir` - Tradutor\n"
              "`/cep` - Buscar CEP\n"
              "`/aniversario_membro` - Registrar\n"
              "`/lembretes` - Ver lembretes",
        inline=True
    )
    
    embed.add_field(
        name="💭 **CRIATIVOS**",
        value="`/frase` - Frase do dia\n"
              "`/pensamento` - Pensamento\n"
              "`/horoscopo` - Horóscopo\n"
              "`/charada` - Charada\n"
              "`/piada` - Piada\n"
              "`/fato` - Fato curioso\n"
              "`/conselho` - Conselho",
        inline=True
    )
    
    embed.add_field(
        name="ℹ️ **BÁSICOS**",
        value="`/ping` - Latência\n"
              "`/userinfo` - Info usuário\n"
              "`/serverinfo` - Info servidor\n"
              "`/avatar` - Ver avatar\n"
              "`/calcular` - Calculadora\n"
              "`/ajuda` - Este menu",
        inline=True
    )
    
    embed.set_footer(text="Total: 120+ comandos! Bot em constante evolução")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

# ==================== INICIAR BOT ====================

async def main():
    print("🔵 INICIANDO FUNÇÃO MAIN")
    
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        print("❌ ERRO CRÍTICO: Token não encontrado nas variáveis de ambiente!")
        return
    
    print(f"🔵 Token encontrado! Conectando...")
    
    try:
        async with bot:
            await bot.start(token)
    except Exception as e:
        print(f"❌ Erro: {e}")

def run_bot():
    print("🟢 INICIANDO BOT FORT ULTIMATE")
    print("="*60)
    print("🚀 SISTEMAS CARREGADOS:")
    print("✅ Sistema de Chamadas")
    print("✅ Sistema de Ship e Casamento")
    print("✅ Sistema de Economia e Jogos")
    print("✅ Sistema de Moderação (novo!)")
    print("✅ Sistema de Música (novo!)")
    print("✅ Sistema de Utilidade (novo!)")
    print("✅ Sistema Criativo (novo!)")
    print("✅ 120+ COMANDOS NO TOTAL!")
    print("="*60)
    
    try:
        keep_alive()
        time.sleep(2)
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋 Desligando")
    except Exception as e:
        print(f"❌ Erro fatal: {e}")

if __name__ == "__main__":
    run_bot()
