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

# ===== CONFIGURAÇÃO DO TOKEN =====
DISCORD_TOKEN = os.environ.get('DISCORD_TOKEN')

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
        "sistemas": 80
    })

@app.route('/health')
@app.route('/healthcheck')
def health():
    return "OK", 200

@app.route('/ping')
def ping():
    return "pong", 200

def run_webserver():
    """Inicia o servidor web - usa a porta do ambiente"""
    port = int(os.environ.get('PORT', 8080))
    print(f"📡 Iniciando servidor web na porta {port}")
    app.run(host='0.0.0.0', port=port, debug=False, use_reloader=False, threaded=True)

def keep_alive():
    """Mantém o bot vivo"""
    server = threading.Thread(target=run_webserver, daemon=True)
    server.start()
    print(f"✅ Servidor web configurado")

class Fort(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        intents.moderation = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
        
        # ===== SISTEMAS EXISTENTES =====
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
        self.muted_users = {}
        self.locked_channels = set()
        self.slowmode_channels = {}
        self.mod_logs_channels = {}
        self.temp_bans = {}
        
        # Sistema de Utilidade
        self.reminders = []
        self.birthdays = {}
        self.saved_notes = {}
        self.poll_data = {}
        self.poll_votes = defaultdict(set)
        
        # Sistema Criativo
        self.user_phrases = {}
        self.daily_thought = None
        self.riddles = self.load_riddles()
        self.jokes = self.load_jokes()
        self.curiosities = self.load_curiosities()
        self.motivational_phrases = self.load_motivational()
        self.horoscope_data = self.load_horoscope()
        
        # Inicializa banco de dados e carrega dados
        self.init_database()
        self.load_data()
    
    # ===== FUNÇÕES SQLITE ATUALIZADAS =====
    def init_database(self):
        """Cria o banco de dados SQLite com novas tabelas"""
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
        # Sistema de Moderação
        c.execute('''CREATE TABLE IF NOT EXISTS warnings
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      moderator_id TEXT,
                      reason TEXT,
                      date TEXT,
                      guild_id TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS muted_users
                     (user_id TEXT PRIMARY KEY,
                      expiry TEXT,
                      guild_id TEXT,
                      reason TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS temp_bans
                     (user_id TEXT PRIMARY KEY,
                      expiry TEXT,
                      guild_id TEXT,
                      reason TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS mod_logs
                     (guild_id TEXT PRIMARY KEY,
                      channel_id TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS locked_channels
                     (channel_id TEXT PRIMARY KEY,
                      guild_id TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS slowmode_channels
                     (channel_id TEXT PRIMARY KEY,
                      slowmode INTEGER,
                      guild_id TEXT)''')
        
        # Sistema de Utilidade
        c.execute('''CREATE TABLE IF NOT EXISTS reminders
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      channel_id TEXT,
                      message TEXT,
                      reminder_time TEXT,
                      created_at TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS birthdays
                     (user_id TEXT PRIMARY KEY,
                      birth_date TEXT,
                      guild_id TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS notes
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      title TEXT,
                      content TEXT,
                      created_at TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS polls
                     (id TEXT PRIMARY KEY,
                      guild_id TEXT,
                      channel_id TEXT,
                      message_id TEXT,
                      question TEXT,
                      options TEXT,
                      creator_id TEXT,
                      created_at TEXT,
                      expires_at TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS poll_votes
                     (poll_id TEXT,
                      user_id TEXT,
                      option_index INTEGER,
                      PRIMARY KEY (poll_id, user_id))''')
        
        # Sistema Criativo
        c.execute('''CREATE TABLE IF NOT EXISTS user_phrases
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      user_id TEXT,
                      phrase TEXT,
                      created_at TEXT)''')
        
        c.execute('''CREATE TABLE IF NOT EXISTS daily_thought
                     (id INTEGER PRIMARY KEY AUTOINCREMENT,
                      thought TEXT,
                      date TEXT)''')
        
        conn.commit()
        conn.close()
        print("✅ Banco de dados SQLite atualizado!")
    
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
            if user_id not in self.warnings:
                self.warnings[user_id] = []
            self.warnings[user_id].append({
                'moderator': mod_id,
                'reason': reason,
                'date': date,
                'guild_id': guild_id,
                'id': len(self.warnings[user_id]) + 1
            })
        
        # Carregar muted users
        c.execute('SELECT user_id, expiry, guild_id, reason FROM muted_users')
        for user_id, expiry, guild_id, reason in c.fetchall():
            expiry_time = datetime.fromisoformat(expiry) if expiry else None
            if expiry_time and expiry_time > datetime.now():
                self.muted_users[user_id] = {
                    'expiry': expiry_time,
                    'guild_id': guild_id,
                    'reason': reason
                }
        
        # Carregar temp bans
        c.execute('SELECT user_id, expiry, guild_id, reason FROM temp_bans')
        for user_id, expiry, guild_id, reason in c.fetchall():
            expiry_time = datetime.fromisoformat(expiry) if expiry else None
            if expiry_time and expiry_time > datetime.now():
                self.temp_bans[user_id] = {
                    'expiry': expiry_time,
                    'guild_id': guild_id,
                    'reason': reason
                }
        
        # Carregar mod logs
        c.execute('SELECT guild_id, channel_id FROM mod_logs')
        self.mod_logs_channels = {guild_id: channel_id for guild_id, channel_id in c.fetchall()}
        
        # Carregar locked channels
        c.execute('SELECT channel_id FROM locked_channels')
        self.locked_channels = {channel_id for channel_id, in c.fetchall()}
        
        # Carregar slowmode channels
        c.execute('SELECT channel_id, slowmode FROM slowmode_channels')
        self.slowmode_channels = {channel_id: slowmode for channel_id, slowmode in c.fetchall()}
        
        # Carregar lembretes
        c.execute('SELECT id, user_id, channel_id, message, reminder_time FROM reminders')
        for rid, user_id, channel_id, message, reminder_time in c.fetchall():
            reminder_time_dt = datetime.fromisoformat(reminder_time)
            if reminder_time_dt > datetime.now():
                self.reminders.append({
                    'id': rid,
                    'user_id': user_id,
                    'channel_id': channel_id,
                    'message': message,
                    'time': reminder_time_dt
                })
        
        # Carregar aniversários
        c.execute('SELECT user_id, birth_date FROM birthdays')
        self.birthdays = {user_id: birth_date for user_id, birth_date in c.fetchall()}
        
        # Carregar notas
        c.execute('SELECT id, user_id, title, content FROM notes')
        for nid, user_id, title, content in c.fetchall():
            if user_id not in self.saved_notes:
                self.saved_notes[user_id] = []
            self.saved_notes[user_id].append({
                'id': nid,
                'title': title,
                'content': content
            })
        
        # Carregar enquetes
        c.execute('SELECT id, question, options, creator_id, expires_at FROM polls')
        for pid, question, options, creator_id, expires_at in c.fetchall():
            self.poll_data[pid] = {
                'question': question,
                'options': json.loads(options),
                'creator_id': creator_id,
                'expires_at': datetime.fromisoformat(expires_at) if expires_at else None
            }
        
        # Carregar votos
        c.execute('SELECT poll_id, user_id FROM poll_votes')
        for poll_id, user_id in c.fetchall():
            self.poll_votes[poll_id].add(user_id)
        
        # Carregar frases dos usuários
        c.execute('SELECT user_id, phrase FROM user_phrases')
        for user_id, phrase in c.fetchall():
            if user_id not in self.user_phrases:
                self.user_phrases[user_id] = []
            self.user_phrases[user_id].append(phrase)
        
        conn.close()
        self.import_from_json_if_empty()
        print("✅ Dados carregados do SQLite!")
    
    def import_from_json_if_empty(self):
        if not self.user_balances:
            try:
                arquivos = ['economy.json', 'inventory.json', 'ships.json', 'marriages.json', 
                           'anniversary.json', 'ship_history.json', 'calls.json']
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
                print("✅ Dados importados dos JSONs!")
                self.save_data()
            except Exception as e:
                print(f"⚠️ Erro ao importar JSONs: {e}")
    
    def save_data(self):
        """Salva dados no SQLite"""
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
        
        # ===== SALVAR NOVOS DADOS =====
        # Muted users
        c.execute('DELETE FROM muted_users')
        for user_id, data in self.muted_users.items():
            if data['expiry'] > datetime.now():
                c.execute('INSERT INTO muted_users VALUES (?, ?, ?, ?)',
                         (user_id, data['expiry'].isoformat(), data['guild_id'], data['reason']))
        
        # Temp bans
        c.execute('DELETE FROM temp_bans')
        for user_id, data in self.temp_bans.items():
            if data['expiry'] > datetime.now():
                c.execute('INSERT INTO temp_bans VALUES (?, ?, ?, ?)',
                         (user_id, data['expiry'].isoformat(), data['guild_id'], data['reason']))
        
        # Mod logs
        c.execute('DELETE FROM mod_logs')
        for guild_id, channel_id in self.mod_logs_channels.items():
            c.execute('INSERT INTO mod_logs VALUES (?, ?)', (guild_id, channel_id))
        
        # Locked channels
        c.execute('DELETE FROM locked_channels')
        for channel_id in self.locked_channels:
            c.execute('INSERT INTO locked_channels VALUES (?, ?)', (channel_id, '0'))
        
        # Slowmode channels
        c.execute('DELETE FROM slowmode_channels')
        for channel_id, slowmode in self.slowmode_channels.items():
            c.execute('INSERT INTO slowmode_channels VALUES (?, ?, ?)', 
                     (channel_id, slowmode, '0'))
        
        # Aniversários
        c.execute('DELETE FROM birthdays')
        for user_id, birth_date in self.birthdays.items():
            c.execute('INSERT INTO birthdays VALUES (?, ?, ?)', 
                     (user_id, birth_date, '0'))
        
        # Notas
        c.execute('DELETE FROM notes')
        for user_id, notes in self.saved_notes.items():
            for note in notes:
                c.execute('INSERT INTO notes (id, user_id, title, content, created_at) VALUES (?, ?, ?, ?, ?)',
                         (note['id'], user_id, note['title'], note['content'], datetime.now().isoformat()))
        
        # Enquetes
        c.execute('DELETE FROM polls')
        for poll_id, data in self.poll_data.items():
            c.execute('INSERT INTO polls VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                     (poll_id, '0', '0', '0', data['question'],
                      json.dumps(data['options']), data['creator_id'],
                      datetime.now().isoformat(),
                      data['expires_at'].isoformat() if data['expires_at'] else None))
        
        # Votos
        c.execute('DELETE FROM poll_votes')
        for poll_id, users in self.poll_votes.items():
            for user_id in users:
                c.execute('INSERT INTO poll_votes (poll_id, user_id, option_index) VALUES (?, ?, 0)',
                         (poll_id, user_id))
        
        # Frases dos usuários
        c.execute('DELETE FROM user_phrases')
        for user_id, phrases in self.user_phrases.items():
            for phrase in phrases:
                c.execute('INSERT INTO user_phrases (user_id, phrase, created_at) VALUES (?, ?, ?)',
                         (user_id, phrase, datetime.now().isoformat()))
        
        conn.commit()
        conn.close()
    
    # ===== CARREGAR DADOS CRIATIVOS =====
    def load_riddles(self):
        return [
            {"charada": "O que é, o que é? Tem cabeça e tem dente, não é bicho e nem é gente.", "resposta": "Alho"},
            {"charada": "O que é, o que é? Quanto mais se tira, maior fica.", "resposta": "Buraco"},
            {"charada": "O que é, o que é? Anda deitado e dorme em pé.", "resposta": "Pé"},
            {"charada": "O que é, o que é? Tem asas mas não voa, tem bico mas não bica.", "resposta": "Bule"},
            {"charada": "O que é, o que é? Dá muitas voltas e não sai do lugar.", "resposta": "Relógio"},
            {"charada": "O que é, o que é? Quanto maior, menos se vê.", "resposta": "Escuridão"},
            {"charada": "O que é, o que é? Tem coroa mas não é rei, tem raiz mas não é planta.", "resposta": "Dente"},
            {"charada": "O que é, o que é? Feito para andar e não anda.", "resposta": "Rua"},
            {"charada": "O que é, o que é? Tem 5 dedos mas não tem unha.", "resposta": "Luva"},
            {"charada": "O que é, o que é? Passa na frente do sol e não faz sombra.", "resposta": "Vento"},
        ]
    
    def load_jokes(self):
        return [
            "Por que o computador foi preso? Porque executou um comando!",
            "O que o zero disse para o oito? Belo cinto!",
            "Por que os elétrons nunca pagam contas? Porque estão sempre em débito!",
            "O que o pato disse para a pata? Vem quá!",
            "Qual o cúmulo da rapidez? Fechar o zíper com uma bala!",
            "Por que o livro de matemática está triste? Porque tem muitos problemas!",
            "O que o tomate foi fazer no banco? Tirar extrato!",
            "Por que o esqueleto não brigou com ninguém? Porque não tem estômago!",
            "Qual é o café mais perigoso do mundo? O ex-presso!",
            "O que o pagodeiro foi fazer na igreja? Cantar pá god!",
            "Por que a planta não responde no WhatsApp? Porque ela tem apenas um caule!",
            "Qual é o animal que tem mais valor? O porco, porque é puro-que!"
        ]
    
    def load_curiosities(self):
        return [
            "🦒 As girafas têm a mesma quantidade de vértebras no pescoço que os humanos: 7!",
            "🐙 Os polvos têm três corações e sangue azul!",
            "🐝 As abelhas podem reconhecer rostos humanos!",
            "🦋 As borboletas sentem gosto com os pés!",
            "🐫 Os camelos não armazenam água nas corcovas, e sim gordura!",
            "🐘 Os elefantes são os únicos mamíferos que não conseguem pular!",
            "🦦 As lontras dão as mãos quando dormem para não se perderem!",
            "🐧 Os pinguins propõem casamento com uma pedrinha!",
            "🦉 As corujas não conseguem mover os olhos, por isso viram a cabeça toda!",
            "🐬 Os golfinhos dão nomes uns aos outros!",
            "🌍 A Terra não é uma esfera perfeita, é achatada nos polos!",
            "🌊 90% da vida nos oceanos ainda é desconhecida!",
            "🍌 Bananas são ligeiramente radioativas!",
            "🍯 O mel nunca estraga! Já encontraram mel com 3000 anos!",
            "💧 A água pode ferver e congelar ao mesmo tempo (ponto triplo)!"
        ]
    
    def load_motivational(self):
        return [
            "🌱 Acredite em você e tudo será possível!",
            "💪 Cada novo dia é uma nova oportunidade!",
            "✨ Você é mais forte do que imagina!",
            "🌟 Seu único limite é você mesmo!",
            "🌈 A persistência é o caminho do êxito!",
            "🎯 Foque no que te faz feliz!",
            "🚀 Sonhe grande, comece pequeno!",
            "💖 O amor próprio é o começo de tudo!",
            "📚 Aprender algo novo todo dia te faz evoluir!",
            "🌞 A gratidão transforma o que temos em suficiente!",
            "🦋 As melhores coisas da vida são simples!",
            "⭐ Você é único e especial!"
        ]
    
    def load_horoscope(self):
        return {
            "Áries": {"inicio": "21/03", "fim": "19/04", "elemento": "Fogo", "planeta": "Marte"},
            "Touro": {"inicio": "20/04", "fim": "20/05", "elemento": "Terra", "planeta": "Vênus"},
            "Gêmeos": {"inicio": "21/05", "fim": "20/06", "elemento": "Ar", "planeta": "Mercúrio"},
            "Câncer": {"inicio": "21/06", "fim": "22/07", "elemento": "Água", "planeta": "Lua"},
            "Leão": {"inicio": "23/07", "fim": "22/08", "elemento": "Fogo", "planeta": "Sol"},
            "Virgem": {"inicio": "23/08", "fim": "22/09", "elemento": "Terra", "planeta": "Mercúrio"},
            "Libra": {"inicio": "23/09", "fim": "22/10", "elemento": "Ar", "planeta": "Vênus"},
            "Escorpião": {"inicio": "23/10", "fim": "21/11", "elemento": "Água", "planeta": "Plutão"},
            "Sagitário": {"inicio": "22/11", "fim": "21/12", "elemento": "Fogo", "planeta": "Júpiter"},
            "Capricórnio": {"inicio": "22/12", "fim": "19/01", "elemento": "Terra", "planeta": "Saturno"},
            "Aquário": {"inicio": "20/01", "fim": "18/02", "elemento": "Ar", "planeta": "Urano"},
            "Peixes": {"inicio": "19/02", "fim": "20/03", "elemento": "Água", "planeta": "Netuno"}
        }
    
    async def setup_hook(self):
        await self.tree.sync()
        print(f"✅ Comandos sincronizados!")

    async def on_ready(self):
        print(f"✅ Bot {self.user} ligado com sucesso!")
        print(f"📊 Servidores: {len(self.guilds)}")
        print(f"👥 Usuários: {len(self.users)}")
        print(f"🛡️ Sistema de Moderação: ATIVO")
        print(f"🔧 Sistema de Utilidade: ATIVO")
        print(f"🎨 Sistema Criativo: ATIVO")
        print(f"📢 Sistema de Chamadas: ATIVO (timing opcional)")
        print(f"💖 Sistema de Ship: ATIVO")
        print(f"💒 Sistema de Casamento: ATIVO")
        print(f"💰 Sistema de Economia: ATIVO")
        print(f"🎮 Sistema de Jogos: ATIVO")
        print(f"🎭 Comandos com GIF: ATIVO")
        print(f"💾 Banco de Dados: SQLite")
        await self.change_presence(activity=discord.Game(name="📢 Use /ajuda | 80+ comandos!"))
    
    async def on_message(self, message):
        if message.author.bot:
            return
        
        # Verificar canais trancados
        if str(message.channel.id) in self.locked_channels:
            if not message.author.guild_permissions.manage_channels:
                await message.delete()
                try:
                    await message.author.send(f"❌ O canal {message.channel.mention} está trancado! Apenas admins podem falar.")
                except:
                    pass
                return
        
        # Verificar lembretes periodicamente
        await self.check_reminders()
    
    async def check_reminders(self):
        """Verifica lembretes vencidos"""
        agora = datetime.now()
        lembretes_para_enviar = []
        
        for reminder in self.reminders[:]:
            if reminder['time'] <= agora:
                lembretes_para_enviar.append(reminder)
                self.reminders.remove(reminder)
                
                # Remover do banco
                conn = sqlite3.connect('fort_bot.db')
                c = conn.cursor()
                c.execute('DELETE FROM reminders WHERE id = ?', (reminder['id'],))
                conn.commit()
                conn.close()
        
        # Enviar lembretes
        for reminder in lembretes_para_enviar:
            try:
                channel = self.get_channel(int(reminder['channel_id']))
                if channel:
                    user = await self.fetch_user(int(reminder['user_id']))
                    if user:
                        embed = discord.Embed(
                            title="⏰ LEMBRETE!",
                            description=reminder['message'],
                            color=discord.Color.gold()
                        )
                        embed.set_footer(text=f"Lembrete para {user.name}")
                        await channel.send(content=user.mention, embed=embed)
            except:
                pass

bot = Fort()

# ==================== SISTEMA DE CHAMADAS COM TIMING INTELIGENTE ====================

def calcular_tempo_expiracao(horas_limite: Optional[int] = None):
    """
    Calcula o tempo de expiração da chamada:
    - Se horas_limite for fornecido: expira após X horas
    - Se não for fornecido: expira à meia-noite (23:59:59)
    """
    agora = datetime.now()
    
    if horas_limite is not None and horas_limite > 0:
        expira_em = agora + timedelta(hours=horas_limite)
        print(f"⏰ Chamada com duração de {horas_limite}h: expira às {expira_em.strftime('%d/%m/%Y %H:%M:%S')}")
        return expira_em
    else:
        meia_noite = datetime(agora.year, agora.month, agora.day, 23, 59, 59)
        if agora > meia_noite:
            meia_noite = datetime(agora.year, agora.month, agora.day, 23, 59, 59) + timedelta(days=1)
            print(f"🌙 Já passou da meia-noite, ajustando para amanhã: {meia_noite.strftime('%d/%m/%Y %H:%M:%S')}")
        else:
            print(f"🌙 Meia-noite de hoje: {meia_noite.strftime('%d/%m/%Y %H:%M:%S')}")
        
        print(f"⏳ Tempo restante até meia-noite: {meia_noite - agora}")
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
        print(f"⏰ Iniciando contador para chamada {call_id}")
        print(f"📅 Expira em: {expira_em.strftime('%d/%m/%Y %H:%M:%S')}")
        
        while True:
            agora = datetime.now()
            tempo_restante = (expira_em - agora).total_seconds()
            
            if tempo_restante <= 0:
                print(f"✅ Tempo esgotado para chamada {call_id}")
                break
            
            print(f"⏳ Chamada {call_id}: {tempo_restante:.0f}s restantes")
            
            espera = min(tempo_restante, 1800)
            await asyncio.sleep(espera)
        
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
                    print(f"✅ Mensagem da chamada {call_id} atualizada")
            except Exception as e:
                print(f"❌ Erro ao editar mensagem: {e}")
        
        if call_id in bot.call_data:
            del bot.call_data[call_id]
        if call_id in bot.call_participants:
            del bot.call_participants[call_id]
        bot.save_data()
        
        print(f"✅ Chamada {call_id} encerrada com sucesso!")
        
    except Exception as e:
        print(f"❌ Erro ao encerrar chamada: {e}")
        traceback.print_exc()

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
    
    if not interaction.guild.me.guild_permissions.mention_everyone:
        await interaction.response.send_message("❌ O bot precisa da permissão `Mencionar @everyone`!", ephemeral=True)
        return
    
    expira_em = calcular_tempo_expiracao(horas_duracao)
    
    agora = datetime.now()
    if expira_em <= agora:
        if horas_duracao:
            expira_em = agora + timedelta(hours=1)
            print(f"⚠️ Tempo já passou, ajustando para +1h: {expira_em}")
        else:
            expira_em = datetime(agora.year, agora.month, agora.day, 23, 59, 59) + timedelta(days=1)
            print(f"⚠️ Meia-noite já passou, ajustando para amanhã: {expira_em}")
    
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
    
    if horas_duracao:
        confirm_msg = f"⏰ Expira em {horas_duracao} hora(s) (às {expira_em.strftime('%H:%M')})"
    else:
        confirm_msg = f"🌙 Expira à meia-noite (hoje às 23:59)"
    
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
        value=expira_em.strftime("%d/%m/%Y %H:%M"),
        inline=True
    )
    
    await interaction.followup.send(embed=embed_confirm, ephemeral=True)
    
    asyncio.create_task(encerrar_chamada_apos_tempo(call_id, expira_em))
    
    print(f"✅ Chamada criada: {call_id}")
    print(f"📅 Expira em: {expira_em.strftime('%d/%m/%Y %H:%M:%S')}")

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

# ==================== COMANDOS DE DIVERSÃO (ANTIGOS) ====================

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

# ==================== SISTEMA DE MODERAÇÃO ====================

class WarnModal(Modal, title="Adicionar Aviso"):
    motivo = TextInput(label="Motivo do aviso", style=discord.TextStyle.paragraph, placeholder="Digite o motivo...", max_length=500)
    
    def __init__(self, member):
        super().__init__()
        self.member = member
    
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user_id = str(self.member.id)
        mod_id = str(interaction.user.id)
        
        if user_id not in bot.warnings:
            bot.warnings[user_id] = []
        
        warning = {
            'id': len(bot.warnings[user_id]) + 1,
            'moderator': mod_id,
            'reason': self.motivo.value,
            'date': datetime.now().strftime("%d/%m/%Y %H:%M"),
            'guild_id': str(interaction.guild_id)
        }
        
        bot.warnings[user_id].append(warning)
        
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        c.execute('INSERT INTO warnings (user_id, moderator_id, reason, date, guild_id) VALUES (?, ?, ?, ?, ?)',
                 (user_id, mod_id, self.motivo.value, datetime.now().isoformat(), str(interaction.guild_id)))
        conn.commit()
        conn.close()
        
        await log_mod_action(
            interaction.guild,
            f"⚠️ **AVISO**",
            f"**Usuário:** {self.member.mention}\n**Moderador:** {interaction.user.mention}\n**Motivo:** {self.motivo.value}\n**Total:** {len(bot.warnings[user_id])} avisos"
        )
        
        embed = discord.Embed(
            title="⚠️ Aviso Adicionado",
            description=f"{self.member.mention} recebeu um aviso!",
            color=discord.Color.orange()
        )
        embed.add_field(name="Motivo", value=self.motivo.value, inline=False)
        embed.add_field(name="Total de avisos", value=str(len(bot.warnings[user_id])), inline=True)
        
        await interaction.followup.send(embed=embed)

async def log_mod_action(guild, title, description):
    """Registra ação de moderação no canal de logs"""
    if str(guild.id) in bot.mod_logs_channels:
        channel_id = int(bot.mod_logs_channels[str(guild.id)])
        channel = guild.get_channel(channel_id)
        if channel:
            embed = discord.Embed(
                title=title,
                description=description,
                color=discord.Color.blue(),
                timestamp=datetime.now()
            )
            await channel.send(embed=embed)

@bot.tree.command(name="clear", description="🧹 Limpar mensagens do canal")
@app_commands.describe(quantidade="Número de mensagens para apagar (1-100)")
async def clear(interaction: discord.Interaction, quantidade: int):
    if not interaction.user.guild_permissions.manage_messages:
        await interaction.response.send_message("❌ Você precisa da permissão `Gerenciar Mensagens`!", ephemeral=True)
        return
    
    if quantidade < 1 or quantidade > 100:
        await interaction.response.send_message("❌ Quantidade deve ser entre 1 e 100!", ephemeral=True)
        return
    
    await interaction.response.defer(ephemeral=True)
    
    deleted = await interaction.channel.purge(limit=quantidade)
    
    embed = discord.Embed(
        title="🧹 Mensagens Apagadas",
        description=f"Foram apagadas **{len(deleted)}** mensagens!",
        color=discord.Color.green()
    )
    embed.set_footer(text=f"Por: {interaction.user.name}")
    
    await interaction.followup.send(embed=embed, ephemeral=True)
    
    await log_mod_action(
        interaction.guild,
        "🧹 **MENSAGENS APAGADAS**",
        f"**Canal:** {interaction.channel.mention}\n**Moderador:** {interaction.user.mention}\n**Quantidade:** {len(deleted)}"
    )

@bot.tree.command(name="kick", description="👢 Expulsar membro do servidor")
@app_commands.describe(membro="Membro para expulsar", motivo="Motivo da expulsão")
async def kick(interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não especificado"):
    if not interaction.user.guild_permissions.kick_members:
        await interaction.response.send_message("❌ Você precisa da permissão `Expulsar Membros`!", ephemeral=True)
        return
    
    if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Você não pode expulsar alguém com cargo maior ou igual ao seu!", ephemeral=True)
        return
    
    try:
        embed_dm = discord.Embed(
            title=f"👢 Você foi expulso de {interaction.guild.name}",
            description=f"**Motivo:** {motivo}",
            color=discord.Color.red()
        )
        await membro.send(embed=embed_dm)
    except:
        pass
    
    await membro.kick(reason=motivo)
    
    embed = discord.Embed(
        title="👢 Membro Expulso",
        description=f"{membro.mention} foi expulso do servidor!",
        color=discord.Color.orange()
    )
    embed.add_field(name="Motivo", value=motivo, inline=False)
    embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
    
    await interaction.response.send_message(embed=embed)
    
    await log_mod_action(
        interaction.guild,
        "👢 **MEMBRO EXPULSO**",
        f"**Usuário:** {membro.mention} (`{membro.id}`)\n**Moderador:** {interaction.user.mention}\n**Motivo:** {motivo}"
    )

@bot.tree.command(name="ban", description="🔨 Banir membro do servidor")
@app_commands.describe(membro="Membro para banir", motivo="Motivo do banimento")
async def ban(interaction: discord.Interaction, membro: discord.Member, motivo: str = "Não especificado"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Você precisa da permissão `Banir Membros`!", ephemeral=True)
        return
    
    if membro.top_role >= interaction.user.top_role and interaction.user != interaction.guild.owner:
        await interaction.response.send_message("❌ Você não pode banir alguém com cargo maior ou igual ao seu!", ephemeral=True)
        return
    
    try:
        embed_dm = discord.Embed(
            title=f"🔨 Você foi banido de {interaction.guild.name}",
            description=f"**Motivo:** {motivo}",
            color=discord.Color.red()
        )
        await membro.send(embed=embed_dm)
    except:
        pass
    
    await membro.ban(reason=motivo)
    
    embed = discord.Embed(
        title="🔨 Membro Banido",
        description=f"{membro.mention} foi banido do servidor!",
        color=discord.Color.red()
    )
    embed.add_field(name="Motivo", value=motivo, inline=False)
    embed.add_field(name="Moderador", value=interaction.user.mention, inline=True)
    
    await interaction.response.send_message(embed=embed)
    
    await log_mod_action(
        interaction.guild,
        "🔨 **MEMBRO BANIDO**",
        f"**Usuário:** {membro.mention} (`{membro.id}`)\n**Moderador:** {interaction.user.mention}\n**Motivo:** {motivo}"
    )

@bot.tree.command(name="tempban", description="⏰ Banir temporariamente")
@app_commands.describe(
    membro="Membro para banir",
    tempo="Tempo em horas (ex: 24 para 1 dia)",
    motivo="Motivo do banimento"
)
async def tempban(interaction: discord.Interaction, membro: discord.Member, tempo: int, motivo: str = "Não especificado"):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Você precisa da permissão `Banir Membros`!", ephemeral=True)
        return
    
    if tempo < 1 or tempo > 720:
        await interaction.response.send_message("❌ Tempo deve ser entre 1 e 720 horas (30 dias)!", ephemeral=True)
        return
    
    expiry = datetime.now() + timedelta(hours=tempo)
    
    try:
        embed_dm = discord.Embed(
            title=f"⏰ Você foi banido temporariamente de {interaction.guild.name}",
            description=f"**Motivo:** {motivo}\n**Expira em:** {expiry.strftime('%d/%m/%Y %H:%M')}",
            color=discord.Color.orange()
        )
        await membro.send(embed=embed_dm)
    except:
        pass
    
    await membro.ban(reason=f"{motivo} (Temp ban: {tempo}h)")
    
    bot.temp_bans[str(membro.id)] = {
        'expiry': expiry,
        'guild_id': str(interaction.guild.id),
        'reason': motivo
    }
    bot.save_data()
    
    embed = discord.Embed(
        title="⏰ Banimento Temporário",
        description=f"{membro.mention} foi banido por **{tempo} horas**!",
        color=discord.Color.orange()
    )
    embed.add_field(name="Motivo", value=motivo, inline=False)
    embed.add_field(name="Expira em", value=expiry.strftime("%d/%m/%Y %H:%M"), inline=True)
    
    await interaction.response.send_message(embed=embed)
    
    await log_mod_action(
        interaction.guild,
        "⏰ **BANIMENTO TEMPORÁRIO**",
        f"**Usuário:** {membro.mention}\n**Duração:** {tempo}h\n**Expira:** {expiry.strftime('%d/%m/%Y %H:%M')}\n**Motivo:** {motivo}"
    )

@bot.tree.command(name="unban", description="🔓 Desbanir usuário")
@app_commands.describe(user_id="ID do usuário para desbanir")
async def unban(interaction: discord.Interaction, user_id: str):
    if not interaction.user.guild_permissions.ban_members:
        await interaction.response.send_message("❌ Você precisa da permissão `Banir Membros`!", ephemeral=True)
        return
    
    try:
        user = await bot.fetch_user(int(user_id))
        await interaction.guild.unban(user)
        
        if user_id in bot.temp_bans:
            del bot.temp_bans[user_id]
            bot.save_data()
        
        embed = discord.Embed(
            title="🔓 Usuário Desbanido",
            description=f"{user.mention} foi desbanido!",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed)
        
        await log_mod_action(
            interaction.guild,
            "🔓 **USUÁRIO DESBANIDO**",
            f"**Usuário:** {user.mention} (`{user.id}`)\n**Moderador:** {interaction.user.mention}"
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao desbanir: {e}", ephemeral=True)

@bot.tree.command(name="timeout", description="🔇 Mutar um membro (timeout)")
@app_commands.describe(
    membro="Membro para mutar",
    minutos="Duração em minutos",
    motivo="Motivo do mute"
)
async def timeout(interaction: discord.Interaction, membro: discord.Member, minutos: int, motivo: str = "Não especificado"):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Você precisa da permissão `Moderar Membros`!", ephemeral=True)
        return
    
    if minutos < 1 or minutos > 40320:
        await interaction.response.send_message("❌ Tempo deve ser entre 1 e 40320 minutos (28 dias)!", ephemeral=True)
        return
    
    duracao = timedelta(minutes=minutos)
    
    try:
        await membro.timeout(duracao, reason=motivo)
        
        embed = discord.Embed(
            title="🔇 Membro Silenciado",
            description=f"{membro.mention} foi mutado por **{minutos} minutos**!",
            color=discord.Color.purple()
        )
        embed.add_field(name="Motivo", value=motivo, inline=False)
        embed.add_field(name="Expira em", value=(datetime.now() + duracao).strftime("%d/%m/%Y %H:%M"), inline=True)
        
        await interaction.response.send_message(embed=embed)
        
        await log_mod_action(
            interaction.guild,
            "🔇 **MEMBRO SILENCIADO**",
            f"**Usuário:** {membro.mention}\n**Duração:** {minutos} minutos\n**Expira:** {(datetime.now() + duracao).strftime('%d/%m/%Y %H:%M')}\n**Motivo:** {motivo}"
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao mutar: {e}", ephemeral=True)

@bot.tree.command(name="untimeout", description="🔊 Remover mute de um membro")
async def untimeout(interaction: discord.Interaction, membro: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Você precisa da permissão `Moderar Membros`!", ephemeral=True)
        return
    
    try:
        await membro.timeout(None)
        
        embed = discord.Embed(
            title="🔊 Membro Desmutado",
            description=f"{membro.mention} não está mais mutado!",
            color=discord.Color.green()
        )
        
        await interaction.response.send_message(embed=embed)
        
        await log_mod_action(
            interaction.guild,
            "🔊 **MEMBRO DESMUTADO**",
            f"**Usuário:** {membro.mention}\n**Moderador:** {interaction.user.mention}"
        )
    except Exception as e:
        await interaction.response.send_message(f"❌ Erro ao desmutar: {e}", ephemeral=True)

@bot.tree.command(name="warn", description="⚠️ Dar aviso a um membro")
async def warn(interaction: discord.Interaction, membro: discord.Member):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Você precisa da permissão `Moderar Membros`!", ephemeral=True)
        return
    
    modal = WarnModal(membro)
    await interaction.response.send_modal(modal)

@bot.tree.command(name="warnings", description="📋 Ver avisos de um membro")
async def warnings(interaction: discord.Interaction, membro: discord.Member):
    user_id = str(membro.id)
    
    if user_id not in bot.warnings or not bot.warnings[user_id]:
        await interaction.response.send_message(f"✅ {membro.mention} não tem avisos!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"📋 Avisos de {membro.display_name}",
        description=f"Total: **{len(bot.warnings[user_id])}** avisos",
        color=discord.Color.orange()
    )
    
    for warning in bot.warnings[user_id][-10:]:
        mod = interaction.guild.get_member(int(warning['moderator']))
        mod_name = mod.mention if mod else "Desconhecido"
        
        embed.add_field(
            name=f"Aviso #{warning['id']} - {warning['date']}",
            value=f"**Moderador:** {mod_name}\n**Motivo:** {warning['reason']}",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="remove_warn", description="🗑️ Remover um aviso")
@app_commands.describe(membro="Membro dono do aviso", warn_id="ID do aviso")
async def remove_warn(interaction: discord.Interaction, membro: discord.Member, warn_id: int):
    if not interaction.user.guild_permissions.moderate_members:
        await interaction.response.send_message("❌ Você precisa da permissão `Moderar Membros`!", ephemeral=True)
        return
    
    user_id = str(membro.id)
    
    if user_id not in bot.warnings or not bot.warnings[user_id]:
        await interaction.response.send_message("❌ Este membro não tem avisos!", ephemeral=True)
        return
    
    warning_to_remove = None
    for warning in bot.warnings[user_id]:
        if warning['id'] == warn_id:
            warning_to_remove = warning
            break
    
    if not warning_to_remove:
        await interaction.response.send_message(f"❌ Aviso #{warn_id} não encontrado!", ephemeral=True)
        return
    
    bot.warnings[user_id].remove(warning_to_remove)
    
    for i, warning in enumerate(bot.warnings[user_id], 1):
        warning['id'] = i
    
    conn = sqlite3.connect('fort_bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM warnings WHERE user_id = ? AND reason = ? AND date = ?',
             (user_id, warning_to_remove['reason'], warning_to_remove['date']))
    conn.commit()
    conn.close()
    
    embed = discord.Embed(
        title="🗑️ Aviso Removido",
        description=f"Aviso #{warn_id} de {membro.mention} foi removido!",
        color=discord.Color.green()
    )
    
    await interaction.response.send_message(embed=embed)
    
    await log_mod_action(
        interaction.guild,
        "🗑️ **AVISO REMOVIDO**",
        f"**Usuário:** {membro.mention}\n**Aviso ID:** #{warn_id}\n**Motivo original:** {warning_to_remove['reason']}\n**Moderador:** {interaction.user.mention}"
    )

@bot.tree.command(name="lock", description="🔒 Trancar canal")
async def lock(interaction: discord.Interaction, canal: Optional[discord.TextChannel] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ Você precisa da permissão `Gerenciar Canais`!", ephemeral=True)
        return
    
    if canal is None:
        canal = interaction.channel
    
    bot.locked_channels.add(str(canal.id))
    bot.save_data()
    
    embed = discord.Embed(
        title="🔒 Canal Trancado",
        description=f"{canal.mention} foi trancado! Apenas admins podem falar.",
        color=discord.Color.red()
    )
    
    await interaction.response.send_message(embed=embed)
    
    await log_mod_action(
        interaction.guild,
        "🔒 **CANAL TRANCADO**",
        f"**Canal:** {canal.mention}\n**Moderador:** {interaction.user.mention}"
    )

@bot.tree.command(name="unlock", description="🔓 Destrancar canal")
async def unlock(interaction: discord.Interaction, canal: Optional[discord.TextChannel] = None):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ Você precisa da permissão `Gerenciar Canais`!", ephemeral=True)
        return
    
    if canal is None:
        canal = interaction.channel
    
    if str(canal.id) in bot.locked_channels:
        bot.locked_channels.remove(str(canal.id))
        bot.save_data()
    
    embed = discord.Embed(
        title="🔓 Canal Destrancado",
        description=f"{canal.mention} foi destrancado! Todos podem falar novamente.",
        color=discord.Color.green()
    )
    
    await interaction.response.send_message(embed=embed)
    
    await log_mod_action(
        interaction.guild,
        "🔓 **CANAL DESTRANCADO**",
        f"**Canal:** {canal.mention}\n**Moderador:** {interaction.user.mention}"
    )

@bot.tree.command(name="slowmode", description="🐢 Ativar modo lento")
@app_commands.describe(segundos="Segundos entre mensagens (0 para desativar)")
async def slowmode(interaction: discord.Interaction, segundos: int):
    if not interaction.user.guild_permissions.manage_channels:
        await interaction.response.send_message("❌ Você precisa da permissão `Gerenciar Canais`!", ephemeral=True)
        return
    
    if segundos < 0 or segundos > 21600:
        await interaction.response.send_message("❌ Segundos deve ser entre 0 e 21600 (6 horas)!", ephemeral=True)
        return
    
    await interaction.channel.edit(slowmode_delay=segundos)
    
    if segundos > 0:
        bot.slowmode_channels[str(interaction.channel.id)] = segundos
        msg = f"Modo lento ativado: **{segundos} segundos** entre mensagens!"
        cor = discord.Color.orange()
    else:
        if str(interaction.channel.id) in bot.slowmode_channels:
            del bot.slowmode_channels[str(interaction.channel.id)]
        msg = "Modo lento desativado!"
        cor = discord.Color.green()
    
    bot.save_data()
    
    embed = discord.Embed(
        title="🐢 Modo Lento",
        description=msg,
        color=cor
    )
    
    await interaction.response.send_message(embed=embed)
    
    await log_mod_action(
        interaction.guild,
        "🐢 **MODO LENTO**",
        f"**Canal:** {interaction.channel.mention}\n**Segundos:** {segundos}\n**Moderador:** {interaction.user.mention}"
    )

@bot.tree.command(name="setmodlogs", description="📝 Configurar canal de logs de moderação")
async def setmodlogs(interaction: discord.Interaction, canal: discord.TextChannel):
    if not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Você precisa ser administrador!", ephemeral=True)
        return
    
    bot.mod_logs_channels[str(interaction.guild.id)] = str(canal.id)
    bot.save_data()
    
    embed = discord.Embed(
        title="📝 Canal de Logs Configurado",
        description=f"Logs de moderação serão enviados em {canal.mention}",
        color=discord.Color.green()
    )
    
    await interaction.response.send_message(embed=embed)

# ==================== SISTEMA DE UTILIDADE ====================

class ReminderModal(Modal, title="Criar Lembrete"):
    mensagem = TextInput(label="Mensagem do lembrete", style=discord.TextStyle.paragraph, placeholder="Digite o lembrete...", max_length=500)
    tempo = TextInput(label="Tempo (ex: 10min, 1h, 2d)", placeholder="10min, 1h, 2d, etc", max_length=10)
    
    async def on_submit(self, interaction: discord.Interaction):
        tempo_str = self.tempo.value.lower()
        try:
            if tempo_str.endswith('s'):
                segundos = int(tempo_str[:-1])
            elif tempo_str.endswith('min'):
                segundos = int(tempo_str[:-3]) * 60
            elif tempo_str.endswith('h'):
                segundos = int(tempo_str[:-1]) * 3600
            elif tempo_str.endswith('d'):
                segundos = int(tempo_str[:-1]) * 86400
            else:
                segundos = int(tempo_str) * 60
        except:
            await interaction.response.send_message("❌ Formato de tempo inválido! Use: 10min, 1h, 2d", ephemeral=True)
            return
        
        if segundos < 60 or segundos > 2592000:
            await interaction.response.send_message("❌ Tempo deve ser entre 1 minuto e 30 dias!", ephemeral=True)
            return
        
        reminder_time = datetime.now() + timedelta(seconds=segundos)
        
        conn = sqlite3.connect('fort_bot.db')
        c = conn.cursor()
        c.execute('INSERT INTO reminders (user_id, channel_id, message, reminder_time, created_at) VALUES (?, ?, ?, ?, ?)',
                 (str(interaction.user.id), str(interaction.channel.id), self.mensagem.value,
                  reminder_time.isoformat(), datetime.now().isoformat()))
        reminder_id = c.lastrowid
        conn.commit()
        conn.close()
        
        bot.reminders.append({
            'id': reminder_id,
            'user_id': str(interaction.user.id),
            'channel_id': str(interaction.channel.id),
            'message': self.mensagem.value,
            'time': reminder_time
        })
        
        embed = discord.Embed(
            title="⏰ Lembrete Criado!",
            description=f"**Mensagem:** {self.mensagem.value}",
            color=discord.Color.gold()
        )
        embed.add_field(name="⏱️ Tempo", value=f"{segundos} segundos", inline=True)
        embed.add_field(name="📅 Lembrete em", value=f"<t:{int(reminder_time.timestamp())}:R>", inline=True)
        
        await interaction.response.send_message(embed=embed)

@bot.tree.command(name="lembrete", description="⏰ Criar um lembrete")
async def lembrete(interaction: discord.Interaction):
    modal = ReminderModal()
    await interaction.response.send_modal(modal)

@bot.tree.command(name="meus_lembretes", description="📋 Ver seus lembretes ativos")
async def meus_lembretes(interaction: discord.Interaction):
    user_reminders = [r for r in bot.reminders if r['user_id'] == str(interaction.user.id)]
    
    if not user_reminders:
        await interaction.response.send_message("❌ Você não tem lembretes ativos!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"📋 Lembretes de {interaction.user.display_name}",
        color=discord.Color.blue()
    )
    
    for reminder in user_reminders[:10]:
        tempo_restante = reminder['time'] - datetime.now()
        horas = int(tempo_restante.total_seconds() // 3600)
        minutos = int((tempo_restante.total_seconds() % 3600) // 60)
        
        embed.add_field(
            name=f"ID: {reminder['id']}",
            value=f"**Mensagem:** {reminder['message'][:50]}...\n**Expira em:** {horas}h{minutos}m\n**Em:** <t:{int(reminder['time'].timestamp())}:R>",
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="cancelar_lembrete", description="❌ Cancelar um lembrete")
@app_commands.describe(lembrete_id="ID do lembrete")
async def cancelar_lembrete(interaction: discord.Interaction, lembrete_id: int):
    reminder_to_remove = None
    for reminder in bot.reminders:
        if reminder['id'] == lembrete_id and reminder['user_id'] == str(interaction.user.id):
            reminder_to_remove = reminder
            break
    
    if not reminder_to_remove:
        await interaction.response.send_message("❌ Lembrete não encontrado!", ephemeral=True)
        return
    
    bot.reminders.remove(reminder_to_remove)
    
    conn = sqlite3.connect('fort_bot.db')
    c = conn.cursor()
    c.execute('DELETE FROM reminders WHERE id = ?', (lembrete_id,))
    conn.commit()
    conn.close()
    
    await interaction.response.send_message(f"✅ Lembrete ID {lembrete_id} cancelado!")

@bot.tree.command(name="aniversario_membro", description="🎂 Registrar seu aniversário")
@app_commands.describe(data="Data no formato DD/MM (ex: 25/12)")
async def aniversario_membro(interaction: discord.Interaction, data: str):
    try:
        dia, mes = map(int, data.split('/'))
        if dia < 1 or dia > 31 or mes < 1 or mes > 12:
            raise ValueError
        data_formatada = f"{dia:02d}/{mes:02d}"
    except:
        await interaction.response.send_message("❌ Data inválida! Use o formato DD/MM (ex: 25/12)", ephemeral=True)
        return
    
    bot.birthdays[str(interaction.user.id)] = data_formatada
    bot.save_data()
    
    embed = discord.Embed(
        title="🎂 Aniversário Registrado!",
        description=f"Sua data de aniversário foi registrada como **{data_formatada}**",
        color=discord.Color.pink()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="aniversarios_hoje", description="🎉 Ver quem faz aniversário hoje")
async def aniversarios_hoje(interaction: discord.Interaction):
    hoje = datetime.now().strftime("%d/%m")
    aniversariantes = []
    
    for user_id, data in bot.birthdays.items():
        if data == hoje:
            membro = interaction.guild.get_member(int(user_id))
            if membro:
                aniversariantes.append(membro.mention)
    
    embed = discord.Embed(
        title="🎉 Aniversariantes de Hoje",
        color=discord.Color.gold()
    )
    
    if aniversariantes:
        embed.description = "\n".join(aniversariantes)
    else:
        embed.description = "Ninguém faz aniversário hoje! 😢"
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="nota", description="📝 Salvar uma nota")
@app_commands.describe(titulo="Título da nota", conteudo="Conteúdo da nota")
async def nota(interaction: discord.Interaction, titulo: str, conteudo: str):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.saved_notes:
        bot.saved_notes[user_id] = []
    
    note_id = len(bot.saved_notes[user_id]) + 1
    
    bot.saved_notes[user_id].append({
        'id': note_id,
        'title': titulo,
        'content': conteudo
    })
    
    bot.save_data()
    
    embed = discord.Embed(
        title="📝 Nota Salva!",
        description=f"Nota **#{note_id}** salva com sucesso!",
        color=discord.Color.green()
    )
    embed.add_field(name="Título", value=titulo, inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="minhas_notas", description="📋 Ver suas notas")
async def minhas_notas(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.saved_notes or not bot.saved_notes[user_id]:
        await interaction.response.send_message("❌ Você não tem notas salvas!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"📋 Notas de {interaction.user.display_name}",
        color=discord.Color.blue()
    )
    
    for note in bot.saved_notes[user_id][-10:]:
        embed.add_field(
            name=f"#{note['id']} - {note['title']}",
            value=f"{note['content'][:100]}..." if len(note['content']) > 100 else note['content'],
            inline=False
        )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="ver_nota", description="🔍 Ver uma nota específica")
@app_commands.describe(nota_id="ID da nota")
async def ver_nota(interaction: discord.Interaction, nota_id: int):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.saved_notes:
        await interaction.response.send_message("❌ Você não tem notas!", ephemeral=True)
        return
    
    note = None
    for n in bot.saved_notes[user_id]:
        if n['id'] == nota_id:
            note = n
            break
    
    if not note:
        await interaction.response.send_message(f"❌ Nota #{nota_id} não encontrada!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"📝 {note['title']}",
        description=note['content'],
        color=discord.Color.purple()
    )
    embed.set_footer(text=f"Nota #{note['id']}")
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="apagar_nota", description="🗑️ Apagar uma nota")
@app_commands.describe(nota_id="ID da nota")
async def apagar_nota(interaction: discord.Interaction, nota_id: int):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.saved_notes:
        await interaction.response.send_message("❌ Você não tem notas!", ephemeral=True)
        return
    
    note_to_remove = None
    for note in bot.saved_notes[user_id]:
        if note['id'] == nota_id:
            note_to_remove = note
            break
    
    if not note_to_remove:
        await interaction.response.send_message(f"❌ Nota #{nota_id} não encontrada!", ephemeral=True)
        return
    
    bot.saved_notes[user_id].remove(note_to_remove)
    
    for i, note in enumerate(bot.saved_notes[user_id], 1):
        note['id'] = i
    
    bot.save_data()
    
    await interaction.response.send_message(f"✅ Nota #{nota_id} apagada!")

@bot.tree.command(name="enquete", description="📊 Criar uma enquete avançada")
@app_commands.describe(
    pergunta="A pergunta da enquete",
    opcao1="Primeira opção",
    opcao2="Segunda opção",
    opcao3="Terceira opção (opcional)",
    opcao4="Quarta opção (opcional)",
    opcao5="Quinta opção (opcional)",
    horas="Duração em horas (opcional)"
)
async def enquete(
    interaction: discord.Interaction,
    pergunta: str,
    opcao1: str,
    opcao2: str,
    opcao3: str = None,
    opcao4: str = None,
    opcao5: str = None,
    horas: Optional[int] = None
):
    emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
    opcoes = [opcao1, opcao2]
    
    if opcao3:
        opcoes.append(opcao3)
    if opcao4:
        opcoes.append(opcao4)
    if opcao5:
        opcoes.append(opcao5)
    
    descricao = ""
    for i, opcao in enumerate(opcoes):
        descricao += f"{emojis[i]} **{opcao}**\n"
    
    if horas:
        expira_em = datetime.now() + timedelta(hours=horas)
        tempo_texto = f"⏰ Expira em {horas} hora(s) (<t:{int(expira_em.timestamp())}:R>)"
    else:
        expira_em = None
        tempo_texto = "⏰ Não expira"
    
    embed = discord.Embed(
        title=f"📊 {pergunta}",
        description=descricao,
        color=discord.Color.blue()
    )
    embed.add_field(name="⏱️ Duração", value=tempo_texto, inline=False)
    embed.set_footer(text=f"Enquete criada por {interaction.user.name} • Reaja para votar!")
    embed.timestamp = datetime.now()
    
    await interaction.response.send_message(embed=embed)
    message = await interaction.original_response()
    
    poll_id = f"{interaction.channel.id}-{message.id}"
    
    bot.poll_data[poll_id] = {
        'question': pergunta,
        'options': opcoes,
        'creator_id': str(interaction.user.id),
        'expires_at': expira_em
    }
    bot.save_data()
    
    for i in range(len(opcoes)):
        await message.add_reaction(emojis[i])
    
    if horas:
        asyncio.create_task(encerrar_enquete_apos_tempo(poll_id, expira_em, message))

async def encerrar_enquete_apos_tempo(poll_id: str, expira_em: datetime, message: discord.Message):
    """Encerra a enquete após o tempo limite"""
    try:
        agora = datetime.now()
        tempo_restante = (expira_em - agora).total_seconds()
        
        if tempo_restante > 0:
            await asyncio.sleep(tempo_restante)
        
        if poll_id in bot.poll_data:
            resultados = {}
            for reaction in message.reactions:
                if reaction.emoji in ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]:
                    idx = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"].index(reaction.emoji)
                    if idx < len(bot.poll_data[poll_id]['options']):
                        resultados[bot.poll_data[poll_id]['options'][idx]] = reaction.count - 1
            
            embed = discord.Embed(
                title=f"📊 RESULTADOS: {bot.poll_data[poll_id]['question']}",
                color=discord.Color.gold()
            )
            
            for opcao, votos in sorted(resultados.items(), key=lambda x: x[1], reverse=True):
                barra = "█" * min(votos, 10) + "░" * (10 - min(votos, 10))
                embed.add_field(
                    name=opcao,
                    value=f"{votos} votos `{barra}`",
                    inline=False
                )
            
            embed.set_footer(text="Enquete encerrada!")
            await message.edit(embed=embed)
            
            del bot.poll_data[poll_id]
            bot.save_data()
    except:
        pass

@bot.tree.command(name="clima", description="🌤️ Ver previsão do tempo")
@app_commands.describe(cidade="Nome da cidade")
async def clima(interaction: discord.Interaction, cidade: str):
    await interaction.response.defer()
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://wttr.in/{cidade}?format=%C+%t+%h+%w&m"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.text()
                    partes = data.strip().split()
                    
                    if len(partes) >= 4:
                        condicao = " ".join(partes[:-3])
                        temp = partes[-3]
                        umidade = partes[-2]
                        vento = partes[-1]
                        
                        emoji_map = {
                            'Clear': '☀️', 'Sunny': '☀️', 'Partly cloudy': '⛅',
                            'Cloudy': '☁️', 'Overcast': '☁️', 'Rain': '🌧️',
                            'Light rain': '🌦️', 'Heavy rain': '🌧️', 'Thunderstorm': '⛈️',
                            'Snow': '❄️', 'Fog': '🌫️', 'Mist': '🌫️'
                        }
                        
                        emoji = "🌡️"
                        for key, value in emoji_map.items():
                            if key.lower() in condicao.lower():
                                emoji = value
                                break
                        
                        embed = discord.Embed(
                            title=f"{emoji} Clima em {cidade.title()}",
                            color=discord.Color.blue()
                        )
                        embed.add_field(name="🌡️ Condição", value=condicao, inline=True)
                        embed.add_field(name="🌡️ Temperatura", value=temp, inline=True)
                        embed.add_field(name="💧 Umidade", value=umidade, inline=True)
                        embed.add_field(name="💨 Vento", value=vento, inline=True)
                        
                        await interaction.followup.send(embed=embed)
                    else:
                        await interaction.followup.send(f"❌ Cidade '{cidade}' não encontrada!")
                else:
                    await interaction.followup.send(f"❌ Erro ao buscar clima para '{cidade}'!")
    except Exception as e:
        await interaction.followup.send(f"❌ Erro: {e}")

@bot.tree.command(name="traduzir", description="🔤 Traduzir texto (usando API gratuita)")
@app_commands.describe(texto="Texto para traduzir", idioma="Idioma destino (ex: pt, en, es)")
async def traduzir(interaction: discord.Interaction, texto: str, idioma: str = "pt"):
    await interaction.response.defer()
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://api.mymemory.translated.net/get?q={texto}&langpair=en|{idioma}"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    traducao = data['responseData']['translatedText']
                    
                    embed = discord.Embed(
                        title="🔤 Tradução",
                        color=discord.Color.purple()
                    )
                    embed.add_field(name="📝 Original", value=texto[:1024], inline=False)
                    embed.add_field(name="📝 Tradução", value=traducao[:1024], inline=False)
                    
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("❌ Erro na tradução!")
    except Exception as e:
        await interaction.followup.send(f"❌ Erro: {e}")

@bot.tree.command(name="cep", description="📍 Buscar endereço por CEP")
@app_commands.describe(cep="CEP (apenas números)")
async def cep(interaction: discord.Interaction, cep: str):
    await interaction.response.defer()
    
    cep = cep.replace("-", "").strip()
    
    if not cep.isdigit() or len(cep) != 8:
        await interaction.followup.send("❌ CEP inválido! Digite 8 números.")
        return
    
    try:
        async with aiohttp.ClientSession() as session:
            url = f"https://viacep.com.br/ws/{cep}/json/"
            async with session.get(url) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    
                    if "erro" in data:
                        await interaction.followup.send("❌ CEP não encontrado!")
                        return
                    
                    embed = discord.Embed(
                        title=f"📍 Endereço para CEP {cep}",
                        color=discord.Color.green()
                    )
                    embed.add_field(name="Logradouro", value=data.get('logradouro', 'N/A'), inline=False)
                    embed.add_field(name="Bairro", value=data.get('bairro', 'N/A'), inline=True)
                    embed.add_field(name="Cidade", value=data.get('localidade', 'N/A'), inline=True)
                    embed.add_field(name="UF", value=data.get('uf', 'N/A'), inline=True)
                    embed.add_field(name="Complemento", value=data.get('complemento', 'N/A'), inline=False)
                    
                    await interaction.followup.send(embed=embed)
                else:
                    await interaction.followup.send("❌ Erro ao buscar CEP!")
    except Exception as e:
        await interaction.followup.send(f"❌ Erro: {e}")

# ==================== SISTEMA CRIATIVO ====================

@bot.tree.command(name="charada", description="🧩 Receber uma charada")
async def charada(interaction: discord.Interaction):
    charada = random.choice(bot.riddles)
    
    embed = discord.Embed(
        title="🧩 Charada",
        description=charada["charada"],
        color=discord.Color.purple()
    )
    embed.set_footer(text="Use /resposta para ver a resposta!")
    
    await interaction.response.send_message(embed=embed)
    
    bot.user_phrases.setdefault(str(interaction.user.id), [])
    bot.user_phrases[str(interaction.user.id)].append(f"CHARADA: {charada['charada']}")

@bot.tree.command(name="resposta", description="🔍 Ver resposta da última charada")
async def resposta(interaction: discord.Interaction):
    if str(interaction.user.id) in bot.user_phrases and bot.user_phrases[str(interaction.user.id)]:
        ultimas = [f for f in bot.user_phrases[str(interaction.user.id)] if f.startswith("CHARADA:")]
        if ultimas:
            ultima_charada = ultimas[-1].replace("CHARADA: ", "")
            for c in bot.riddles:
                if c["charada"] == ultima_charada:
                    await interaction.response.send_message(f"🔍 A resposta é: **{c['resposta']}**")
                    return
    
    await interaction.response.send_message("❌ Nenhuma charada recente encontrada! Use /charada primeiro.")

@bot.tree.command(name="piada_ruim", description="😂 Piada ruim (mas engraçada)")
async def piada_ruim(interaction: discord.Interaction):
    piada = random.choice(bot.jokes)
    
    embed = discord.Embed(
        title="😂 Piada Ruim",
        description=piada,
        color=discord.Color.gold()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="curiosidade", description="🔍 Fato curioso aleatório")
async def curiosidade(interaction: discord.Interaction):
    curiosidade = random.choice(bot.curiosities)
    
    embed = discord.Embed(
        title="🔍 Curiosidade",
        description=curiosidade,
        color=discord.Color.teal()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="frase_motivacional", description="💪 Frase motivacional do dia")
async def frase_motivacional(interaction: discord.Interaction):
    frase = random.choice(bot.motivational_phrases)
    
    embed = discord.Embed(
        title="💪 Frase Motivacional",
        description=f"*{frase}*",
        color=discord.Color.green()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="pensamento", description="💭 Pensamento do dia")
async def pensamento(interaction: discord.Interaction):
    pensamentos = [
        "💭 A vida é o que acontece enquanto você está ocupado fazendo outros planos.",
        "💭 O sucesso é ir de fracasso em fracasso sem perder entusiasmo.",
        "💭 A felicidade não é algo pronto, ela vem das suas próprias ações.",
        "💭 Seja a mudança que você quer ver no mundo.",
        "💭 O único modo de fazer um excelente trabalho é amar o que você faz.",
        "💭 Tudo o que você sempre quis está do outro lado do medo.",
        "💭 O pessimista vê dificuldade em cada oportunidade. O otimista vê oportunidade em cada dificuldade.",
        "💭 Não espere, nunca será a hora certa.",
        "💭 A jornada de mil milhas começa com um único passo.",
        "💭 Você é mais forte do que pensa e mais corajoso do que acredita."
    ]
    
    embed = discord.Embed(
        title="💭 Pensamento do Dia",
        description=random.choice(pensamentos),
        color=discord.Color.purple()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="horoscopo", description="⭐ Horóscopo do dia")
@app_commands.describe(signo="Seu signo")
async def horoscopo(interaction: discord.Interaction, signo: str):
    signos_validos = list(bot.horoscope_data.keys())
    
    if signo.capitalize() not in signos_validos:
        await interaction.response.send_message(f"❌ Signos válidos: {', '.join(signos_validos)}")
        return
    
    signo = signo.capitalize()
    info = bot.horoscope_data[signo]
    
    previsoes = [
        "🌟 Hoje é um ótimo dia para novos começos!",
        "💼 No trabalho, sua criatividade estará em alta.",
        "❤️ No amor, a comunicação será a chave.",
        "💰 Uma oportunidade financeira pode aparecer.",
        "🤝 Amizades verdadeiras serão fortalecidas.",
        "🌱 Cuide da sua saúde mental hoje.",
        "🎯 Seus objetivos estão mais próximos do que imagina.",
        "🌈 A sorte estará ao seu lado em decisões importantes.",
        "📚 Aprender algo novo trará benefícios.",
        "✨ Confie na sua intuição hoje."
    ]
    
    embed = discord.Embed(
        title=f"⭐ Horóscopo de {signo}",
        description=f"**Elemento:** {info['elemento']}\n**Planeta:** {info['planeta']}\n**Período:** {info['inicio']} - {info['fim']}",
        color=discord.Color.gold()
    )
    embed.add_field(name="📅 Previsão de Hoje", value=random.choice(previsoes), inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="rimar", description="🎭 Palavras que rimam")
@app_commands.describe(palavra="Palavra para buscar rimas")
async def rimar(interaction: discord.Interaction, palavra: str):
    rimas_comuns = {
        "amor": ["dor", "flor", "calor", "sabor", "valor", "cor"],
        "feliz": ["raiz", "matriz", "aprendiz", "país"],
        "casa": ["asa", "praça", "graça", "massa"],
        "vida": ["ferida", "saída", "partida", "querida"],
        "coração": ["emoção", "paixão", "ilusão", "canção"],
        "sol": ["farol", "girassol", "lençol", "anzol"],
        "mar": ["lugar", "sonhar", "voar", "cantar"],
        "céu": ["mel", "réu", "véu"],
        "lua": ["rua", "continua", "nua"],
        "estrela": ["dela", "bela", "procela"]
    }
    
    palavra_lower = palavra.lower()
    
    if palavra_lower in rimas_comuns:
        rimas = rimas_comuns[palavra_lower]
    else:
        ultimas_letras = palavra_lower[-2:] if len(palavra_lower) > 2 else palavra_lower
        rimas = [f"Palavra1", f"Palavra2", f"Palavra3"]
    
    embed = discord.Embed(
        title=f"🎭 Rimas para '{palavra}'",
        description=", ".join(rimas[:10]),
        color=discord.Color.pink()
    )
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="minhas_frases", description="📚 Ver suas frases salvas")
async def minhas_frases(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.user_phrases or not bot.user_phrases[user_id]:
        await interaction.response.send_message("❌ Você não tem frases salvas!", ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f"📚 Frases de {interaction.user.display_name}",
        color=discord.Color.teal()
    )
    
    frases = bot.user_phrases[user_id][-10:]
    for i, frase in enumerate(frases, 1):
        embed.add_field(name=f"#{i}", value=frase[:100], inline=False)
    
    await interaction.response.send_message(embed=embed)

@bot.tree.command(name="salvar_frase", description="💾 Salvar uma frase")
@app_commands.describe(frase="Frase para salvar")
async def salvar_frase(interaction: discord.Interaction, frase: str):
    user_id = str(interaction.user.id)
    
    if user_id not in bot.user_phrases:
        bot.user_phrases[user_id] = []
    
    bot.user_phrases[user_id].append(frase)
    bot.save_data()
    
    await interaction.response.send_message(f"✅ Frase salva! Total: {len(bot.user_phrases[user_id])} frases")

# ==================== ATUALIZAR COMANDO DE AJUDA ====================

@bot.tree.command(name="ajuda", description="📚 Todos os comandos")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(
        title="📚 Comandos do Bot Fort",
        description="**Sistema Completo - 85+ COMANDOS!**",
        color=discord.Color.blue()
    )
    
    embed.add_field(
        name="🛡️ **MODERAÇÃO**",
        value="`/clear` - Limpar mensagens\n"
              "`/kick` - Expulsar\n"
              "`/ban` - Banir\n"
              "`/tempban` - Ban temporário\n"
              "`/unban` - Desbanir\n"
              "`/timeout` - Mutar\n"
              "`/untimeout` - Desmutar\n"
              "`/warn` - Dar aviso\n"
              "`/warnings` - Ver avisos\n"
              "`/remove_warn` - Remover aviso\n"
              "`/lock` - Trancar canal\n"
              "`/unlock` - Destrancar\n"
              "`/slowmode` - Modo lento\n"
              "`/setmodlogs` - Canal de logs",
        inline=False
    )
    
    embed.add_field(
        name="🔧 **UTILIDADE**",
        value="`/lembrete` - Criar lembrete\n"
              "`/meus_lembretes` - Ver lembretes\n"
              "`/cancelar_lembrete` - Cancelar\n"
              "`/aniversario_membro` - Registrar\n"
              "`/aniversarios_hoje` - Hoje\n"
              "`/nota` - Salvar nota\n"
              "`/minhas_notas` - Ver notas\n"
              "`/ver_nota` - Ver nota\n"
              "`/apagar_nota` - Apagar nota\n"
              "`/enquete` - Criar enquete\n"
              "`/clima` - Previsão\n"
              "`/traduzir` - Tradutor\n"
              "`/cep` - Buscar CEP",
        inline=False
    )
    
    embed.add_field(
        name="🎨 **CRIATIVO**",
        value="`/charada` - Charada\n"
              "`/resposta` - Ver resposta\n"
              "`/piada_ruim` - Piada\n"
              "`/curiosidade` - Curiosidade\n"
              "`/frase_motivacional` - Motivação\n"
              "`/pensamento` - Pensamento\n"
              "`/horoscopo` - Horóscopo\n"
              "`/rimar` - Rimas\n"
              "`/salvar_frase` - Salvar frase\n"
              "`/minhas_frases` - Minhas frases",
        inline=False
    )
    
    embed.add_field(
        name="📢 **CHAMADAS**",
        value="`/chamada` - Criar chamada\n"
              "`/chamada_info` - Ver informações\n"
              "`/chamada_lista` - Lista completa\n"
              "`/chamada_cancelar` - Cancelar",
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
              "`/shiplist` - Listar ships\n"
              "`/calcular_amor` - Análise",
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
              "`/luademel` - Lua de mel",
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
              "`/adivinha` - Adivinhação",
        inline=True
    )
    
    embed.add_field(
        name="💝 **PRESENTES**",
        value="`/loja_presentes` - Loja\n"
              "`/comprar_presente` - Comprar\n"
              "`/meuspresentes` - Inventário\n"
              "`/signos` - Compatibilidade",
        inline=True
    )
    
    embed.add_field(
        name="🎭 **INTERAÇÕES**",
        value="`/abraco_gif` - Abraçar\n"
              "`/beijo_gif` - Beijar\n"
              "`/carinho_gif` - Carinho\n"
              "`/cafune_gif` - Cafuné\n"
              "`/tapa` - Dar tapa\n"
              "`/festa` - Fazer festa\n"
              "`/matar` - Matar\n"
              "`/chifre` - Dar chifre",
        inline=True
    )
    
    embed.add_field(
        name="🎮 **JOGOS**",
        value="`/moeda` - Cara ou coroa\n"
              "`/rps` - Jokenpo\n"
              "`/dado_rpg` - Dados RPG\n"
              "`/sortear` - Sortear\n"
              "`/8ball` - Perguntas\n"
              "`/piada` - Piada\n"
              "`/conselho` - Conselho\n"
              "`/fato` - Fato\n"
              "`/baitola` - 🏳️‍🌈",
        inline=True
    )
    
    embed.add_field(
        name="🤖 **BÁSICOS**",
        value="`/ping` - Latência\n"
              "`/userinfo` - Info usuário\n"
              "`/serverinfo` - Info servidor\n"
              "`/avatar` - Ver avatar\n"
              "`/calcular` - Calculadora\n"
              "`/ola_mundo` - Boas vindas",
        inline=True
    )
    
    embed.set_footer(text="Total: 85+ comandos! Use / antes de cada comando")
    embed.set_thumbnail(url=bot.user.display_avatar.url)
    
    await interaction.response.send_message(embed=embed)

# ==================== INICIAR BOT ====================
async def main():
    print("🔵 INICIANDO FUNÇÃO MAIN")
    
    token = os.environ.get('DISCORD_TOKEN')
    
    if not token:
        print("❌ ERRO CRÍTICO: Token não encontrado nas variáveis de ambiente!")
        print("📌 Certifique-se de que a variável DISCORD_TOKEN está configurada")
        return
    
    print(f"🔵 Token encontrado! Conectando...")
    
    try:
        async with bot:
            await bot.start(token)
    except Exception as e:
        print(f"❌ Erro: {e}")

def run_bot():
    print("🟢 INICIANDO BOT FORT - VERSÃO ULTIMATE")
    print("="*60)
    print("🚀 SISTEMAS CARREGADOS:")
    print("✅ Sistema de Moderação (14 comandos)")
    print("✅ Sistema de Utilidade (13 comandos)")
    print("✅ Sistema Criativo (10 comandos)")
    print("✅ Sistema de Chamadas (com decoração)")
    print("✅ Sistema de Ship e Casamento")
    print("✅ Sistema de Economia e Presentes")
    print("✅ Sistema de Jogos e Interações com GIF")
    print("✅ Comandos Básicos e Diversão")
    print("✅ Banco de Dados SQLite")
    print("="*60)
    print("📊 TOTAL: 85+ COMANDOS!")
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
