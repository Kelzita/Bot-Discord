# -*- coding: utf-8 -*-
"""
Fort Bot — main.py corrigido (GIFs, enquete/modal, minigames Páscoa, RP extra).
Requer: discord.py 2.x, flask
"""
import sys
import discord
from discord import app_commands
from discord.ui import Button, View, Modal, TextInput
import random
import json
import asyncio
from datetime import datetime, timedelta, timezone
from typing import Optional
import sqlite3
import os
import time
import logging
import traceback

DISCORD_TOKEN = os.environ.get("DISCORD_TOKEN")
BR_TZ = timezone(timedelta(hours=-3))

from flask import Flask, jsonify
import threading

sys.stdout.reconfigure(encoding="utf-8")
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)


@app.route("/")
def home():
    return jsonify({"status": "online", "bot": "Fort Bot", "sistemas": 90})


@app.route("/health")
@app.route("/healthcheck")
def health():
    return "OK", 200


@app.route("/ping")
def ping():
    return "pong", 200


def run_webserver():
    port = int(os.environ.get("PORT", 8080))
    print(f"📡 Iniciando servidor web na porta {port}")
    app.run(host="0.0.0.0", port=port, debug=False, use_reloader=False, threaded=True)


def keep_alive():
    server = threading.Thread(target=run_webserver, daemon=True)
    server.start()
    print("✅ Servidor web configurado")


class EnqueteButton(Button):
    def __init__(self, enquete_id: str, opcao_index: int, opcao_texto: str):
        super().__init__(
            style=discord.ButtonStyle.primary,
            label=opcao_texto[:30],
            emoji=self.get_emoji(opcao_index),
            custom_id=f"enquete_{enquete_id}_{opcao_index}",
        )
        self.enquete_id = enquete_id
        self.opcao_index = opcao_index
        self.opcao_texto = opcao_texto

    def get_emoji(self, index):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        return emojis[index] if index < len(emojis) else "✅"

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

        await interaction.response.send_message(mensagem, ephemeral=True)
        await self.atualizar_embed(interaction, enquete)

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
        embed = discord.Embed(title="📊 **ENQUETE**", description=descricao, color=discord.Color.blue())
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
            custom_id=f"encerrar_enquete_{enquete_id}",
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
            color=discord.Color.dark_gray(),
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
        self.pergunta = TextInput(label="📝 Pergunta da Enquete", placeholder="Ex: Qual é a melhor cor?", required=True, max_length=200)
        self.opcoes = TextInput(label="🎯 Opções (separadas por |)", placeholder="Ex: Azul | Vermelho | Verde", required=True, max_length=500)
        self.duracao = TextInput(label="⏰ Duração em horas (0 = ilimitada)", placeholder="Ex: 24", required=False, default="0", max_length=3)
        self.add_item(self.pergunta)
        self.add_item(self.opcoes)
        self.add_item(self.duracao)

    def get_emoji(self, index):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        return emojis[index] if index < len(emojis) else "✅"

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
            descricao += f"{self.get_emoji(i)} **{opcao}**\n"
        descricao += "\n📊 **Total de votos:** 0\n👥 **Participantes:** 0"
        if expira_em:
            descricao += f"\n⏰ **Expira:** {expira_em.strftime('%d/%m/%Y %H:%M')} (Brasília)"
        else:
            descricao += "\n🌙 **Expira:** Nunca (enquete permanente)"
        embed = discord.Embed(title="📊 **ENQUETE**", description=descricao, color=discord.Color.blue())
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
            "expira_em": expira_em.isoformat() if expira_em else None,
        }
        bot.save_enquetes()
        if expira_em:
            task = asyncio.create_task(bot.encerrar_enquete_automatico(enquete_id, expira_em))
            bot.enquete_tasks[enquete_id] = task


class AdicionarOpcaoModal(Modal):
    def __init__(self, enquete_id: str):
        super().__init__(title="➕ Adicionar Nova Opção")
        self.enquete_id = enquete_id
        self.nova_opcao = TextInput(label="📝 Nova Opção", placeholder="Digite a nova opção", required=True, max_length=100)
        self.add_item(self.nova_opcao)

    def get_emoji(self, index):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        return emojis[index] if index < len(emojis) else "✅"

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
        await interaction.response.send_message(f"✅ Opção **{nova_opcao}** adicionada!", ephemeral=True)
        await self.recriar_view(interaction, enquete)

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
                    embed = discord.Embed(title="📊 **ENQUETE**", description=descricao, color=discord.Color.blue())
                    embed.set_footer(text=f"Criada por {enquete['criador_nome']} | ID: {self.enquete_id}")
                    embed.timestamp = datetime.now(BR_TZ)
                    await msg.edit(embed=embed, view=nova_view)
        except Exception as e:
            print(f"Erro ao recriar view: {e}")


class GerenciarEnqueteView(View):
    def __init__(self, enquete_id: str):
        super().__init__(timeout=None)
        self.enquete_id = enquete_id
        self.add_item(AdicionarOpcaoButton(enquete_id))
        self.add_item(ResultadosButton(enquete_id))
        self.add_item(EncerrarEnqueteButton(enquete_id))


class AdicionarOpcaoButton(Button):
    def __init__(self, enquete_id: str):
        super().__init__(style=discord.ButtonStyle.success, label="➕ Adicionar Opção", emoji="➕", custom_id=f"add_opcao_{enquete_id}")
        self.enquete_id = enquete_id

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(AdicionarOpcaoModal(self.enquete_id))


class ResultadosButton(Button):
    def __init__(self, enquete_id: str):
        super().__init__(style=discord.ButtonStyle.secondary, label="📊 Ver Resultados", emoji="📊", custom_id=f"resultados_{enquete_id}")
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
            color=discord.Color.green(),
        )
        embed.add_field(name="Total de Votos", value=str(total_votos), inline=True)
        embed.add_field(name="Participantes", value=str(len(enquete["votos_usuario"])), inline=True)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Fort(discord.Client):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(intents=intents)
        self.tree = app_commands.CommandTree(self)
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
        self.enquetes = {}
        self.enquete_tasks = {}
        self.pascoa_pontos = {}
        self.pascoa_ovos = {}
        self.pascoa_daily = {}
        self.pascoa_coelho = {}
        self.pascoa_memoria = {}
        self.pascoa_quiz_cd = {}
        self.pascoa_corrida = {}
        self.pascoa_cacaninja_cd = {}
        self.pascoa_roleta_cd = {}
        self.rp_fichas = {}
        self.rp_acoes_cd = {}
        self.active_tasks = {}
        self.init_database()
        self.load_data()

    def init_database(self):
        conn = sqlite3.connect("fort_bot.db")
        c = conn.cursor()
        c.execute("""CREATE TABLE IF NOT EXISTS economia (user_id TEXT PRIMARY KEY, saldo INTEGER)""")
        c.execute("""CREATE TABLE IF NOT EXISTS daily_cooldowns (user_id TEXT PRIMARY KEY, data TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS divorce_cooldowns (user_id TEXT PRIMARY KEY, data TEXT)""")
        c.execute("""CREATE TABLE IF NOT EXISTS dados_json (tipo TEXT PRIMARY KEY, dados TEXT)""")
        conn.commit()
        conn.close()
        print("✅ Banco de dados SQLite inicializado!")

    def load_data(self):
        conn = sqlite3.connect("fort_bot.db")
        c = conn.cursor()
        c.execute("SELECT user_id, saldo FROM economia")
        self.user_balances = {user_id: saldo for user_id, saldo in c.fetchall()}
        c.execute("SELECT user_id, data FROM daily_cooldowns")
        self.daily_cooldowns = {user_id: data for user_id, data in c.fetchall()}
        c.execute("SELECT user_id, data FROM divorce_cooldowns")
        self.divorce_cooldowns = {}
        for user_id, data in c.fetchall():
            self.divorce_cooldowns[user_id] = datetime.fromisoformat(data).replace(tzinfo=BR_TZ) if data else None
        c.execute("SELECT tipo, dados FROM dados_json")
        for tipo, dados_json in c.fetchall():
            dados = json.loads(dados_json)
            if tipo == "inventory":
                self.user_inventory = dados
            elif tipo == "ships":
                self.ship_data = dados
            elif tipo == "marriages":
                self.marriage_data = dados
            elif tipo == "anniversary":
                self.anniversary_data = dados
            elif tipo == "ship_history":
                self.ship_history = dados
            elif tipo == "calls":
                self.call_data = dados
            elif tipo == "call_participants":
                self.call_participants = dados
            elif tipo == "enquetes":
                self.enquetes = dados
            elif tipo == "pascoa_pontos":
                self.pascoa_pontos = dados
            elif tipo == "rp_fichas":
                self.rp_fichas = dados
        conn.close()
        self.import_from_json_if_empty()

    def import_from_json_if_empty(self):
        if not self.user_balances:
            try:
                arquivos = [
                    "economy.json",
                    "inventory.json",
                    "ships.json",
                    "marriages.json",
                    "anniversary.json",
                    "ship_history.json",
                    "calls.json",
                    "enquetes.json",
                ]
                for arquivo in arquivos:
                    if os.path.exists(arquivo):
                        with open(arquivo, "r", encoding="utf-8") as f:
                            data = json.load(f)
                            if arquivo == "economy.json":
                                self.user_balances = data
                            elif arquivo == "inventory.json":
                                self.user_inventory = data
                            elif arquivo == "ships.json":
                                self.ship_data = data
                            elif arquivo == "marriages.json":
                                self.marriage_data = data
                            elif arquivo == "anniversary.json":
                                self.anniversary_data = data
                            elif arquivo == "ship_history.json":
                                self.ship_history = data
                            elif arquivo == "calls.json":
                                self.call_data = data.get("calls", {})
                                self.call_participants = data.get("participants", {})
                            elif arquivo == "enquetes.json":
                                self.enquetes = data
                print("✅ Dados importados dos JSONs!")
                self.save_data()
            except Exception as e:
                print(f"⚠️ Erro ao importar JSONs: {e}")

    def save_data(self):
        conn = sqlite3.connect("fort_bot.db")
        c = conn.cursor()
        for user_id, saldo in self.user_balances.items():
            c.execute("INSERT OR REPLACE INTO economia VALUES (?, ?)", (user_id, saldo))
        for user_id, data in self.daily_cooldowns.items():
            c.execute("INSERT OR REPLACE INTO daily_cooldowns VALUES (?, ?)", (user_id, data))
        for user_id, data in self.divorce_cooldowns.items():
            data_str = data.isoformat() if data else None
            c.execute("INSERT OR REPLACE INTO divorce_cooldowns VALUES (?, ?)", (user_id, data_str))
        dados_para_salvar = [
            ("inventory", self.user_inventory),
            ("ships", self.ship_data),
            ("marriages", self.marriage_data),
            ("anniversary", self.anniversary_data),
            ("ship_history", self.ship_history),
            ("calls", self.call_data),
            ("call_participants", self.call_participants),
            ("enquetes", self.enquetes),
            ("pascoa_pontos", self.pascoa_pontos),
            ("rp_fichas", self.rp_fichas),
        ]
        for tipo, dados in dados_para_salvar:
            c.execute("INSERT OR REPLACE INTO dados_json VALUES (?, ?)", (tipo, json.dumps(dados, ensure_ascii=False)))
        conn.commit()
        conn.close()

    def save_enquetes(self):
        conn = sqlite3.connect("fort_bot.db")
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO dados_json VALUES (?, ?)", ("enquetes", json.dumps(self.enquetes, ensure_ascii=False)))
        conn.commit()
        conn.close()

    def save_pascoa(self):
        conn = sqlite3.connect("fort_bot.db")
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO dados_json VALUES (?, ?)", ("pascoa_pontos", json.dumps(self.pascoa_pontos, ensure_ascii=False)))
        conn.commit()
        conn.close()

    def save_rp(self):
        conn = sqlite3.connect("fort_bot.db")
        c = conn.cursor()
        c.execute("INSERT OR REPLACE INTO dados_json VALUES (?, ?)", ("rp_fichas", json.dumps(self.rp_fichas, ensure_ascii=False)))
        conn.commit()
        conn.close()

    def add_pascoa_pontos(self, user_id: str, pontos: int):
        uid = str(user_id)
        if uid not in self.pascoa_pontos:
            self.pascoa_pontos[uid] = 0
        self.pascoa_pontos[uid] += pontos
        self.save_pascoa()

    async def setup_hook(self):
        await self.tree.sync()
        print("✅ Comandos sincronizados!")
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
                color=discord.Color.dark_gray(),
            )
            embed_final.add_field(name="📊 Total de votos", value=str(total_votos), inline=True)
            embed_final.add_field(name="👥 Participantes", value=str(len(enquete["votos_usuario"])), inline=True)
            embed_final.set_footer(text="Encerrada automaticamente por tempo limite")
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
                expira_em = datetime.fromisoformat(call_data["expira_em"]).replace(tzinfo=BR_TZ)
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
        print(f"⏰ Horário atual: {datetime.now(BR_TZ).strftime('%d/%m/%Y %H:%M:%S')}")
        await self.change_presence(activity=discord.Game(name="🐣 Páscoa | Fort Bot"))


bot = Fort()


def calcular_tempo_expiracao(horas_limite: Optional[int] = None):
    agora = datetime.now(BR_TZ)
    if horas_limite is not None and horas_limite > 0:
        return agora + timedelta(hours=horas_limite)
    return datetime(agora.year, agora.month, agora.day, 23, 59, 59, tzinfo=BR_TZ)


CHAMADA_INTRO_PADRAO = (
    "Boa tarde, meus amores. Sejam bem-vindos ao canal de chamada da House! "
    "Esse espaço foi criado para confirmarmos quem permanece ativo e comprometido com a nossa House 🤍"
)


def montar_descricao_embed_chamada(
    data_atual: str,
    texto_intro: str,
    data_hora: str,
    emoji_botao: str,
    timing_text: str,
    num_presentes: int,
) -> str:
    """Texto completo do embed de chamada (layout original da House)."""
    return f"""﹒⬚﹒⇆﹒🍑 ᆞ

५ᅟ𐙚 ⎯ᅟ︶︶︶﹒୧﹐atividade ❞ {data_atual}
𓈒 ׂ 🪷੭ ᮫ : {texto_intro}

ㅤ𔘓 ㅤׄㅤ ㅤׅ ㅤׄ 말 🌿 𝅼ㅤׄㅤㅤ𔘓 丶丶
[𒃵] A cada ausência não justificada, será registrado um tracinho.

𑇡 📝 Ao acumular sete tracinhos, será banido automaticamente.
Caso tenha algum compromisso, justifique sua ausência em. Estarei registrando os presentes no horário correto, então não será considerada confirmação fora do período informado.

여기 ㅤ🔔✨ ; A chamada começará às {data_hora}.
Para confirmar sua presença, reaja com o emoji indicado abaixo e sinta-se à vontade para continuar suas atividades após isso.
✦𓂃 Utilize o emoji {emoji_botao} para responder à chamada.

ⓘ Lembrando: Marcar presença e desaparecer completamente da House até a próxima chamada também resultará em registro de ausência. Compromisso é essencial para mantermos a organização e o bom funcionamento daqui.

५ᅟ𐙚 ⎯ᅟᅟ❝ 🍑﹒ᥫ᭡﹐୨`﹒ꔫ﹐︶︶︶﹒୧﹐🍑 ❞
ㅤ𔘓 ㅤׄㅤ ㅤׅ ㅤׄ 魂 🌷 𝅼ㅤׄㅤㅤ𔘓 ◖

**{timing_text}**
**✅ PRESENTES: {num_presentes}**"""


CHAMADA_EMBED_TITLE = "🌿ᩚ📦 𝐇𝐎𝐔𝐒𝐄 ִ 𝐂̷̸𝐇𝐀𝐌𝐀𝐃𝐀 ꒥꒦ 📄"


class CallButton(Button):
    def __init__(self, call_id: str, emoji: str, expira_em: datetime):
        super().__init__(style=discord.ButtonStyle.success, label="Confirmar Presença", emoji=emoji, custom_id=f"call_{call_id}")
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
            await interaction.response.defer(ephemeral=True)
            bot.call_participants[call_id].append(user_id)
            bot.save_data()
            try:
                channel = bot.get_channel(int(call["channel_id"]))
                if channel:
                    message = await channel.fetch_message(int(call["message_id"]))
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
                        if call.get("horas_duracao"):
                            timing_text = f"⏰ Expira em {call['horas_duracao']} hora(s) (às {self.expira_em.strftime('%H:%M')} Brasília)"
                        else:
                            timing_text = "🌙 Expira HOJE às 23:59 (MEIA-NOITE Brasília)"
                        intro = (call.get("descricao") or "").strip() or CHAMADA_INTRO_PADRAO
                        descricao_completa = montar_descricao_embed_chamada(
                            data_atual,
                            intro,
                            call["data_hora"],
                            call["emoji"],
                            timing_text,
                            len(bot.call_participants[call_id]),
                        )
                        embed = discord.Embed(
                            title=CHAMADA_EMBED_TITLE,
                            description=descricao_completa,
                            color=discord.Color.from_str("#FF69B4"),
                        )
                        embed.add_field(
                            name="📋 LISTA DE PRESENTES",
                            value=participantes_text if participantes_text else "Ninguém confirmou ainda",
                            inline=False,
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
                    color=discord.Color.green(),
                )
                embed_privado.add_field(name="📅 Data/Hora", value=call["data_hora"], inline=True)
                embed_privado.add_field(name="📍 Local", value=call["local"], inline=True)
                embed_privado.add_field(name="👤 Organizador", value=f"<@{call['criador_id']}>", inline=True)
                embed_privado.add_field(name="📊 Total", value=f"{len(bot.call_participants[call_id])} confirmados", inline=True)
                embed_privado.set_footer(text="Obrigado por confirmar! 🎉")
                await interaction.user.send(embed=embed_privado)
            except Exception:
                pass
            await interaction.followup.send(
                f"✅ Presença confirmada! Total: {len(bot.call_participants[call_id])}",
                ephemeral=True,
            )
        except Exception as e:
            print(f"Erro: {e}")
            if interaction.response.is_done():
                await interaction.followup.send(f"❌ Erro: {e}", ephemeral=True)
            else:
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
        channel = bot.get_channel(int(call["channel_id"]))
        if channel:
            try:
                message = await channel.fetch_message(int(call["message_id"]))
                if message:
                    motivo = f"APÓS {call['horas_duracao']} HORA(S)" if call.get("horas_duracao") else "À MEIA-NOITE (23:59 Brasília)"
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
                        title="📦 𝐇𝐎𝐔𝐒𝐄 ִ 𝐂̷̸𝐇𝐀𝐌𝐀𝐃𝐀 [ENCERRADA]",
                        description=f"**CHAMADA ENCERRADA {motivo}**\n\nTotal de presentes: **{len(participantes)}**",
                        color=discord.Color.dark_gray(),
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
    data_hora="Data e hora",
    local="Local do evento",
    horas_duracao="Horas para expirar (opcional)",
    descricao="Descrição adicional (opcional)",
    emoji="Emoji do botão (padrão: ✅)",
)
async def chamada(
    interaction: discord.Interaction,
    titulo: str,
    data_hora: str,
    local: str,
    horas_duracao: Optional[int] = None,
    descricao: str = "",
    emoji: str = "✅",
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
        timing_text = "🌙 Expira HOJE às 23:59 (MEIA-NOITE Brasília)"
    intro = descricao.strip() if descricao else CHAMADA_INTRO_PADRAO
    descricao_completa = montar_descricao_embed_chamada(
        data_atual,
        intro,
        data_hora,
        emoji,
        timing_text,
        0,
    )
    embed = discord.Embed(
        title=CHAMADA_EMBED_TITLE,
        description=descricao_completa,
        color=discord.Color.from_str("#FF69B4"),
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
        allowed_mentions=discord.AllowedMentions(everyone=True),
    )
    message = await interaction.original_response()
    bot.call_data[call_id] = {
        "titulo": titulo,
        "data_hora": data_hora,
        "local": local,
        "descricao": descricao,
        "criador_id": str(interaction.user.id),
        "criador_nome": interaction.user.name,
        "channel_id": str(interaction.channel.id),
        "message_id": str(message.id),
        "emoji": emoji,
        "expira_em": expira_em.isoformat(),
        "criado_em": datetime.now(BR_TZ).isoformat(),
        "horas_duracao": horas_duracao,
    }
    bot.call_participants[call_id] = []
    bot.save_data()
    confirm_msg = (
        f"⏰ Expira em {horas_duracao} hora(s) (às {expira_em.strftime('%H:%M')} Brasília)"
        if horas_duracao
        else "🌙 Expira HOJE às 23:59 (MEIA-NOITE Brasília)"
    )
    embed_confirm = discord.Embed(title="✅ Chamada Criada!", description=f"**{titulo}**", color=discord.Color.green())
    embed_confirm.add_field(name="⏰ Timing", value=confirm_msg, inline=False)
    embed_confirm.add_field(name="📅 Data/Hora", value=data_hora, inline=True)
    embed_confirm.add_field(name="⏱️ Expira em", value=expira_em.strftime("%d/%m/%Y %H:%M") + " (Brasília)", inline=True)
    await interaction.followup.send(embed=embed_confirm, ephemeral=True)
    bot.active_tasks[call_id] = asyncio.create_task(encerrar_chamada_apos_tempo(call_id, expira_em))


@bot.tree.command(name="chamada_info", description="ℹ️ Ver informações de uma chamada")
async def chamada_info(interaction: discord.Interaction, message_id: str = None):
    if not message_id:
        calls = [(cid, data) for cid, data in bot.call_data.items() if data.get("channel_id") == str(interaction.channel.id)]
        if not calls:
            await interaction.response.send_message("❌ Nenhuma chamada no canal!", ephemeral=True)
            return
        calls.sort(key=lambda x: x[1]["criado_em"], reverse=True)
        embed = discord.Embed(title="📋 Últimas Chamadas", color=discord.Color.blue())
        for cid, data in calls[:5]:
            participantes = len(bot.call_participants.get(cid, []))
            expira_em = datetime.fromisoformat(data["expira_em"]).replace(tzinfo=BR_TZ)
            status = "🟢 Ativa" if expira_em > datetime.now(BR_TZ) else "🔴 Encerrada"
            embed.add_field(
                name=f"📢 {data['titulo'][:30]}",
                value=f"📅 {data['data_hora']}\n✅ {participantes} confirmados\n{status}\n📝 `{data['message_id']}`",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)
        return
    call_id = None
    for cid, data in bot.call_data.items():
        if data["message_id"] == message_id:
            call_id = cid
            break
    if not call_id:
        await interaction.response.send_message("❌ Chamada não encontrada!", ephemeral=True)
        return
    data = bot.call_data[call_id]
    participantes = bot.call_participants.get(call_id, [])
    expira_em = datetime.fromisoformat(data["expira_em"]).replace(tzinfo=BR_TZ)
    status = "🟢 Ativa" if expira_em > datetime.now(BR_TZ) else "🔴 Encerrada"
    embed = discord.Embed(title=f"📊 {data['titulo']}", color=discord.Color.blue())
    embed.add_field(name="📅 Data/Hora", value=data["data_hora"], inline=True)
    embed.add_field(name="📍 Local", value=data["local"], inline=True)
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
    call_id = next((cid for cid, data in bot.call_data.items() if data["message_id"] == message_id), None)
    if not call_id:
        await interaction.response.send_message("❌ Chamada não encontrada!", ephemeral=True)
        return
    data = bot.call_data[call_id]
    participantes = bot.call_participants.get(call_id, [])
    if not participantes:
        await interaction.response.send_message("📋 Ninguém confirmou ainda!", ephemeral=True)
        return
    embed = discord.Embed(title="📋 Lista de Presença", description=f"**{data['titulo']}**", color=discord.Color.green())
    embed.add_field(name="📅 Data", value=data["data_hora"], inline=True)
    embed.add_field(name="📍 Local", value=data["local"], inline=True)
    embed.add_field(name="✅ Total", value=str(len(participantes)), inline=True)
    lista = ""
    for i, pid in enumerate(participantes, 1):
        member = interaction.guild.get_member(int(pid))
        if member:
            lista += f"{i}. {member.mention}\n"
    if len(lista) > 1024:
        partes = [lista[i : i + 1024] for i in range(0, len(lista), 1024)]
        for j, parte in enumerate(partes):
            embed.add_field(name=f"📋 Participantes (parte {j+1})", value=parte, inline=False)
    else:
        embed.add_field(name="📋 Participantes", value=lista, inline=False)
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="chamada_cancelar", description="❌ Cancelar uma chamada")
async def chamada_cancelar(interaction: discord.Interaction, message_id: str):
    call_id = next((cid for cid, data in bot.call_data.items() if data["message_id"] == message_id), None)
    if not call_id:
        await interaction.response.send_message("❌ Chamada não encontrada!", ephemeral=True)
        return
    data = bot.call_data[call_id]
    if str(interaction.user.id) != data["criador_id"] and not interaction.user.guild_permissions.administrator:
        await interaction.response.send_message("❌ Só o criador ou admin pode cancelar!", ephemeral=True)
        return
    if call_id in bot.active_tasks:
        bot.active_tasks[call_id].cancel()
        del bot.active_tasks[call_id]
    try:
        channel = bot.get_channel(int(data["channel_id"]))
        if channel:
            msg = await channel.fetch_message(int(message_id))
            if msg:
                embed_cancel = discord.Embed(
                    title="❌ CHAMADA CANCELADA",
                    description=f"**{data['titulo']}** cancelada por {interaction.user.mention}",
                    color=discord.Color.red(),
                )
                await msg.edit(content=None, embed=embed_cancel, view=None)
    except Exception:
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
        if data.get("channel_id") == str(interaction.channel.id):
            expira_em = datetime.fromisoformat(data["expira_em"]).replace(tzinfo=BR_TZ)
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
            inline=False,
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="enquete", description="📊 Criar uma enquete dinâmica")
async def enquete_criar(interaction: discord.Interaction):
    await interaction.response.send_modal(CriarEnqueteModal())


@bot.tree.command(name="enquete_info", description="ℹ️ Ver informações de uma enquete")
async def enquete_info(interaction: discord.Interaction, message_id: str):
    enquete_id = next((eid for eid, data in bot.enquetes.items() if data.get("message_id") == message_id), None)
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
        if data.get("channel_id") == str(interaction.channel.id):
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
        status = "🟢 Permanente" if not expira else "⏰ Com prazo"
        embed.add_field(
            name=f"📊 {data['pergunta'][:40]}",
            value=f"✅ {total_votos} votos | {status}\n📝 `{data['message_id']}`",
            inline=False,
        )
    await interaction.response.send_message(embed=embed, ephemeral=True)


@bot.tree.command(name="enquete_gerenciar", description="⚙️ Gerenciar uma enquete")
async def enquete_gerenciar(interaction: discord.Interaction, message_id: str):
    enquete_id = next((eid for eid, data in bot.enquetes.items() if data.get("message_id") == message_id), None)
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
    await interaction.response.send_message(embed=embed, view=GerenciarEnqueteView(enquete_id), ephemeral=True)


GIFS_PASCOA = [
    "https://media.giphy.com/media/l4KibWpBGWchSqCRy/giphy.gif",
    "https://media.giphy.com/media/26n7b7PjSOZJwVCmY/giphy.gif",
    "https://media.giphy.com/media/3oz8xtBx06mcZWoNJm/giphy.gif",
    "https://media.giphy.com/media/xT0GqtcVoRfeMYRnzy/giphy.gif",
    "https://media.giphy.com/media/3o7TKDtZetOBBiPlkc/giphy.gif",
]
GIFS_COELHO = [
    "https://media.giphy.com/media/3o7TKDtZetOBBiPlkc/giphy.gif",
    "https://media.giphy.com/media/6X9UDSBznQG60/giphy.gif",
    "https://media.giphy.com/media/3o6Mbj2w67HnPQcQoM/giphy.gif",
]
GIFS_OVO = [
    "https://media.giphy.com/media/3oz8xtBx06mcZWoNJm/giphy.gif",
    "https://media.giphy.com/media/l4KibWpBGWchSqCRy/giphy.gif",
    "https://media.giphy.com/media/xT0GqtcVoRfeMYRnzy/giphy.gif",
]
GIFS_CHOCOLHATE = [
    "https://media.giphy.com/media/mGcWBFaedatJPxNVKV/giphy.gif",
    "https://media.giphy.com/media/3o7TKMeCOV3oXSABHq/giphy.gif",
]

QUIZ_PASCOA = [
    {"pergunta": "🐣 Qual animal é o símbolo da Páscoa?", "opcoes": ["🐇 Coelho", "🐤 Pinto", "🦆 Pato", "🐓 Galinha"], "correta": 0, "explicacao": "O coelho de Páscoa é o símbolo mais famoso!"},
    {"pergunta": "🥚 Quantas cores tem um ovo de Páscoa tradicional?", "opcoes": ["Apenas uma", "Duas ou mais", "Nenhuma", "Depende"], "correta": 1, "explicacao": "Ovos tradicionais são decorados com várias cores!"},
    {"pergunta": "🍫 De que é feito o ovo de Páscoa brasileiro?", "opcoes": ["Açúcar", "Chocolate", "Plástico", "Borracha"], "correta": 1, "explicacao": "No Brasil, ovos de Páscoa são feitos de chocolate!"},
    {"pergunta": "🌸 Em que estação a Páscoa cai no Brasil?", "opcoes": ["Verão", "Inverno", "Primavera", "Outono"], "correta": 3, "explicacao": "No Brasil, a Páscoa costuma ser no outono."},
    {"pergunta": "🐇 O que o coelho da Páscoa esconde?", "opcoes": ["Cenouras", "Ovos coloridos", "Só flores", "Pão"], "correta": 1, "explicacao": "A tradição são ovos coloridos!"},
    {"pergunta": "✝️ A Páscoa cristã celebra qual evento?", "opcoes": ["Nascimento", "Ressurreição", "Batismo", "Pentecostes"], "correta": 1, "explicacao": "Comemora a ressurreição de Jesus Cristo."},
    {"pergunta": "🐥 O ovo na Páscoa simboliza o quê?", "opcoes": ["Morte", "Nova vida", "Dinheiro", "Fome"], "correta": 1, "explicacao": "O ovo simboliza vida e renascimento."},
    {"pergunta": "🍬 Chocolate mais popular na Páscoa no Brasil?", "opcoes": ["Branco", "Amargo", "Ao leite", "Meio amargo"], "correta": 2, "explicacao": "O ao leite é um dos favoritos!"},
]

EASTER_DECORATIONS = ["🌸🐣🥚🐇🌸", "🐰🍫🌷🌼🐰", "🥚🌸🐥🌷🥚", "🌼🐇🍬🐣🌼", "🦋🌸🥚🌺🦋"]


def easter_header():
    return random.choice(EASTER_DECORATIONS)


class QuizPascoaView(View):
    def __init__(self, user_id: str, pergunta_data: dict, opcoes: list, correta_idx: int):
        super().__init__(timeout=30)
        self.user_id = user_id
        self.pergunta_data = pergunta_data
        self.correta_idx = correta_idx
        self.respondido = False
        cores = [discord.ButtonStyle.primary, discord.ButtonStyle.success, discord.ButtonStyle.danger, discord.ButtonStyle.secondary]
        for i, opcao in enumerate(opcoes):
            btn = Button(label=opcao[:80], style=cores[i % len(cores)], custom_id=f"quiz_pascoa_{i}")
            btn.callback = self._make_cb(i)
            self.add_item(btn)

    def _make_cb(self, idx: int):
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
                uid = str(interaction.user.id)
                if uid not in bot.user_balances:
                    bot.user_balances[uid] = 0
                bot.user_balances[uid] += moedas
                bot.save_data()
                embed = discord.Embed(
                    title="🎉 CORRETO!",
                    description=f"✅ **Parabéns!**\n\n💡 {self.pergunta_data['explicacao']}",
                    color=discord.Color.green(),
                )
                embed.set_image(url=random.choice(GIFS_PASCOA))
                embed.add_field(name="🥚 Pontos", value=f"+**{pontos}**", inline=True)
                embed.add_field(name="🍫 Moedas", value=f"+**{moedas}**", inline=True)
            else:
                embed = discord.Embed(
                    title="❌ ERROU!",
                    description=f"Certo: **{self.pergunta_data['opcoes'][self.correta_idx]}**\n\n💡 {self.pergunta_data['explicacao']}",
                    color=discord.Color.red(),
                )
            await interaction.response.edit_message(embed=embed, view=None)

        return callback


class PascoaMemoryButton(Button):
    def __init__(self, game_id: str, index: int):
        super().__init__(style=discord.ButtonStyle.secondary, label="🥚", row=min(index // 5, 4))
        self.game_id = game_id
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        game = bot.pascoa_memoria.get(self.game_id)
        if not game or game.get("done"):
            await interaction.response.send_message("❌ Jogo encerrado.", ephemeral=True)
            return
        if str(interaction.user.id) != game["user_id"]:
            await interaction.response.send_message("❌ Não é seu jogo!", ephemeral=True)
            return
        if self.index in game["matched"] or self.index == game.get("first_pick"):
            await interaction.response.send_message("❌ Escolha outra casa.", ephemeral=True)
            return
        labels = game["labels"]
        if game["first_pick"] is None:
            game["first_pick"] = self.index
            self.label = labels[self.index]
            self.disabled = True
            await interaction.response.edit_message(view=self.view)
            return
        i1, i2 = game["first_pick"], self.index
        game["first_pick"] = None
        b1 = next(b for b in self.view.children if isinstance(b, PascoaMemoryButton) and b.index == i1)
        b2 = self
        b1.label = labels[i1]
        b2.label = labels[i2]
        b1.disabled = True
        b2.disabled = True
        uid = game["user_id"]
        if labels[i1] == labels[i2]:
            game["matched"].update([i1, i2])
            game["pairs"] += 1
            bot.add_pascoa_pontos(uid, 12)
            if uid not in bot.user_balances:
                bot.user_balances[uid] = 0
            bot.user_balances[uid] += random.randint(20, 60)
            bot.save_data()
            total_pairs = len(labels) // 2
            if game["pairs"] >= total_pairs:
                game["done"] = True
                bot.add_pascoa_pontos(uid, 25)
                bot.save_data()
                for child in self.view.children:
                    if isinstance(child, PascoaMemoryButton):
                        child.disabled = True
                embed = discord.Embed(
                    title="🐣 Memória de Páscoa — vitória!",
                    description="Todos os pares encontrados! +25 pts bônus.",
                    color=discord.Color.gold(),
                )
                await interaction.response.edit_message(embed=embed, view=self.view)
                self.view.stop()
                return
            await interaction.response.edit_message(view=self.view)
            return
        await interaction.response.defer()
        await interaction.edit_original_response(view=self.view)
        await asyncio.sleep(1.2)
        b1.label = "🥚"
        b2.label = "🥚"
        b1.disabled = False
        b2.disabled = False
        await interaction.edit_original_response(view=self.view)


class PascoaMemoryView(View):
    def __init__(self, game_id: str, size: int):
        super().__init__(timeout=120)
        self.game_id = game_id
        for i in range(size):
            self.add_item(PascoaMemoryButton(game_id, i))


PASCOA_ANAGRAMAS = [
    ("PASCOA", ["PASCOA", "COSPAA", "ASCOPA", "SOCAPA"]),
    ("COELHO", ["COELHO", "LOCHEO", "OCHLEO", "HOLECO"]),
    ("CHOCOLATE", ["CHOCOLATE", "TELOCHOAC", "COLATECHO", "HOCELATOC"]),
    ("OVO", ["OVO", "VOO", "OVI", "VEO"]),
    ("CESTO", ["CESTO", "TESOC", "SOCET", "ECOST"]),
]


class AnagramPascoaView(View):
    def __init__(self, user_id: str, correta: str, botoes: list):
        super().__init__(timeout=45)
        self.user_id = user_id
        self.correta = correta
        self.respondido = False
        styles = [discord.ButtonStyle.primary, discord.ButtonStyle.success, discord.ButtonStyle.danger, discord.ButtonStyle.secondary]
        for i, texto in enumerate(botoes):
            self.add_item(self._mk_btn(i, texto[:75], styles[i % len(styles)]))

    def _mk_btn(self, idx: int, label: str, style):
        btn = Button(style=style, label=label, custom_id=f"anag_p_{idx}_{id(self)}")

        async def callback(interaction: discord.Interaction, lbl=label, correct=self.correta, owner=self.user_id):
            if str(interaction.user.id) != owner:
                await interaction.response.send_message("❌ Não é seu jogo!", ephemeral=True)
                return
            if self.respondido:
                await interaction.response.send_message("❌ Já respondeu.", ephemeral=True)
                return
            self.respondido = True
            self.stop()
            if lbl == correct:
                pts = random.randint(18, 28)
                moedas = random.randint(80, 180)
                bot.add_pascoa_pontos(owner, pts)
                if owner not in bot.user_balances:
                    bot.user_balances[owner] = 0
                bot.user_balances[owner] += moedas
                bot.save_data()
                emb = discord.Embed(
                    title="✅ Acertou!",
                    description=f"**{correct}**",
                    color=discord.Color.green(),
                )
                emb.add_field(name="Pontos", value=f"+{pts}", inline=True)
                emb.add_field(name="Moedas", value=f"+{moedas}", inline=True)
                emb.set_image(url=random.choice(GIFS_PASCOA))
            else:
                emb = discord.Embed(
                    title="❌ Ops!",
                    description=f"A palavra certa era **{correct}**.",
                    color=discord.Color.red(),
                )
            await interaction.response.edit_message(embed=emb, view=None)

        btn.callback = callback
        return btn


@bot.tree.command(name="pascoa_daily", description="🐣 Recompensa diária de Páscoa!")
async def pascoa_daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)
    hoje = agora.date()
    if user_id in bot.pascoa_daily:
        ultimo = datetime.fromisoformat(bot.pascoa_daily[user_id]).date()
        if hoje == ultimo:
            proximo = datetime(agora.year, agora.month, agora.day, 0, 0, 0, tzinfo=BR_TZ) + timedelta(days=1)
            restante = proximo - agora
            horas = int(restante.total_seconds() // 3600)
            minutos = int((restante.total_seconds() % 3600) // 60)
            await interaction.response.send_message(
                f"🐇 Você já coletou hoje!\n⏰ Próximo em **{horas}h {minutos}m**",
                ephemeral=True,
            )
            return
    pontos_base = random.randint(10, 30)
    moedas_base = random.randint(200, 600)
    bonus = ""
    extra_pontos = extra_moedas = 0
    roll = random.random()
    if roll < 0.05:
        extra_pontos, extra_moedas = 50, 1000
        bonus = "🎊 **JACKPOT!** +50 pts +1000 moedas!"
    elif roll < 0.20:
        extra_pontos, extra_moedas = 20, 300
        bonus = "✨ **Bônus!** +20 pts +300 moedas!"
    elif roll < 0.45:
        extra_pontos, extra_moedas = 10, 150
        bonus = "🌸 **Bônus!** +10 pts +150 moedas!"
    total_pontos = pontos_base + extra_pontos
    total_moedas = moedas_base + extra_moedas
    bot.add_pascoa_pontos(user_id, total_pontos)
    if user_id not in bot.user_balances:
        bot.user_balances[user_id] = 0
    bot.user_balances[user_id] += total_moedas
    bot.pascoa_daily[user_id] = agora.isoformat()
    bot.save_data()
    pontos_total = bot.pascoa_pontos.get(user_id, 0)
    deco = easter_header()
    embed = discord.Embed(
        title=f"{deco} PRESENTE DE PÁSCOA! {deco}",
        description=f"🐇 **{interaction.user.display_name}**, o Coelhinho trouxe presentes!",
        color=discord.Color.from_str("#FFD700"),
    )
    embed.set_image(url=random.choice(GIFS_PASCOA))
    embed.add_field(name="🥚 Pontos", value=f"+**{pontos_base}**", inline=True)
    embed.add_field(name="🍫 Moedas", value=f"+**{moedas_base}**", inline=True)
    if bonus:
        embed.add_field(name="🎁 BÔNUS", value=bonus, inline=False)
    embed.add_field(name="🏆 Total Páscoa", value=f"**{pontos_total}** pts", inline=False)
    embed.set_footer(text="🐣 Volte amanhã!")
    embed.timestamp = agora
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pascoa_quiz", description="🧠 Quiz de Páscoa (cooldown 30min)")
async def pascoa_quiz(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)
    if user_id in bot.pascoa_quiz_cd:
        ultimo = datetime.fromisoformat(bot.pascoa_quiz_cd[user_id])
        if ultimo.tzinfo is None:
            ultimo = ultimo.replace(tzinfo=BR_TZ)
        if agora - ultimo < timedelta(minutes=30):
            restante = timedelta(minutes=30) - (agora - ultimo)
            await interaction.response.send_message(f"🧠 Aguarde **{int(restante.total_seconds() // 60)} min**.", ephemeral=True)
            return
    pergunta_data = random.choice(QUIZ_PASCOA)
    view = QuizPascoaView(user_id, pergunta_data, pergunta_data["opcoes"], pergunta_data["correta"])
    deco = easter_header()
    embed = discord.Embed(
        title=f"{deco} QUIZ DE PÁSCOA {deco}",
        description=f"**{pergunta_data['pergunta']}**",
        color=discord.Color.from_str("#FF69B4"),
    )
    embed.set_footer(text="⏰ 30 segundos!")
    bot.pascoa_quiz_cd[user_id] = agora.isoformat()
    await interaction.response.send_message(embed=embed, view=view)


@bot.tree.command(name="pascoa_memoria", description="🧠 Jogo da memória — ganhe pontos!")
async def pascoa_memoria(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    pairs = 6
    emojis = ["🐣", "🐇", "🌷", "🍫", "🌸", "🎀"]
    board = emojis[:pairs] * 2
    random.shuffle(board)
    game_id = str(interaction.id)
    bot.pascoa_memoria[game_id] = {
        "user_id": user_id,
        "labels": board,
        "first_pick": None,
        "matched": set(),
        "pairs": 0,
        "done": False,
    }
    embed = discord.Embed(
        title="🧠 Memória de Páscoa",
        description="Clique em duas 🥚. Forme **6 pares**! ⏱️ 2 min.",
        color=discord.Color.from_str("#FF69B4"),
    )
    embed.set_image(url=random.choice(GIFS_OVO))
    await interaction.response.send_message(embed=embed, view=PascoaMemoryView(game_id, len(board)))


@bot.tree.command(name="pascoa_anagrama", description="🔤 Adivinhe a palavra (4 opções)")
async def pascoa_anagrama(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    palavra, opcoes = random.choice(PASCOA_ANAGRAMAS)
    random.shuffle(opcoes)
    scrambled = "".join(random.sample(list(palavra), len(palavra)))
    embed = discord.Embed(
        title="🔤 Anagrama",
        description=f"Letras: **{scrambled}**\nQual é a palavra?",
        color=discord.Color.from_str("#FFD700"),
    )
    embed.set_footer(text="45 segundos!")
    await interaction.response.send_message(embed=embed, view=AnagramPascoaView(user_id, palavra, opcoes))


class NinjaEggButton(Button):
    """Um dos ①–⑤ esconde o ovo dourado (índice golden)."""

    _labels = ["①", "②", "③", "④", "⑤"]

    def __init__(self, game_key: str, index: int, golden: int, rnd: int, hearts: int, pts: int, uid: str):
        super().__init__(style=discord.ButtonStyle.secondary, label=self._labels[index], row=0)
        self.game_key = game_key
        self.index = index
        self.golden = golden
        self.rnd = rnd
        self.hearts = hearts
        self.pts = pts
        self.uid = uid

    async def callback(self, interaction: discord.Interaction):
        if str(interaction.user.id) != self.uid:
            await interaction.response.send_message("❌ Não é seu jogo!", ephemeral=True)
            return
        if self.index == self.golden:
            new_pts = self.pts + 12 + self.rnd * 10
            if self.rnd >= 3:
                bonus = 55
                total = new_pts + bonus
                bot.add_pascoa_pontos(self.uid, total)
                if self.uid not in bot.user_balances:
                    bot.user_balances[self.uid] = 0
                moedas_bonus = random.randint(120, 280)
                bot.user_balances[self.uid] += moedas_bonus
                bot.save_data()
                bot.pascoa_cacaninja_cd[self.uid] = datetime.now(BR_TZ).isoformat()
                emb = discord.Embed(
                    title="🏆 LENDÁRIO! Você limpou as 3 rodadas!",
                    description=f"**+{total}** pts de Páscoa (com bônus final)\n**+{moedas_bonus}** moedas\n_O coelho te nomeou caçador oficial._ 🐇✨",
                    color=discord.Color.gold(),
                )
                emb.set_image(url=random.choice(GIFS_COELHO))
                await interaction.response.edit_message(embed=emb, view=None)
            else:
                nv = PascoaCacaNinjaView(self.game_key, self.uid, self.rnd + 1, self.hearts, new_pts)
                emb = discord.Embed(
                    title=f"✨ Rodada {self.rnd + 1}/3 — O coelho mudou os ovos de lugar!",
                    description=f"Você achou o **ovo dourado**!\n💰 Pontos acumulados nesta partida: **{new_pts}**\n❤️ Vidas: **{'❤️' * self.hearts}**\n\n_A próxima rodada está mais embaralhada…_",
                    color=discord.Color.from_str("#FF69B4"),
                )
                emb.set_footer(text="Só um ovo é o certo em cada rodada.")
                await interaction.response.edit_message(embed=emb, view=nv)
        else:
            nh = self.hearts - 1
            if nh <= 0:
                consolo = self.pts // 4 if self.pts > 0 else 0
                if consolo:
                    bot.add_pascoa_pontos(self.uid, consolo)
                bot.save_data()
                bot.pascoa_cacaninja_cd[self.uid] = datetime.now(BR_TZ).isoformat()
                lose_txt = f"Sem vidas! Fim de jogo.\n**+{consolo}** pts de consolação." if consolo else "Sem vidas! Fim de jogo.\nTreine o olhar e volte após o cooldown."
                emb = discord.Embed(
                    title="💀 O coelho riu e sumiu no mato…",
                    description=lose_txt,
                    color=discord.Color.dark_red(),
                )
                emb.set_image(url=random.choice(GIFS_COELHO))
                await interaction.response.edit_message(embed=emb, view=None)
            else:
                nv = PascoaCacaNinjaView(self.game_key, self.uid, self.rnd, nh, self.pts)
                emb = discord.Embed(
                    title=f"💨 Errou! Rodada {self.rnd}/3",
                    description=f"Isso era só casca pintada…\n❤️ Restam: **{'❤️' * nh}**\n💰 Pontos na mesa: **{self.pts}** (só ganha tudo se vencer!)\n\n_Tente outro ovo — o dourado mudou de lugar._",
                    color=discord.Color.orange(),
                )
                await interaction.response.edit_message(embed=emb, view=nv)


class PascoaCacaNinjaView(View):
    """Minijogo: 3 acertos seguidos (por rodada), 3 vidas."""

    def __init__(self, game_key: str, uid: str, rnd: int, hearts: int, pts: int):
        super().__init__(timeout=120)
        self.game_key = game_key
        golden = random.randint(0, 4)
        for i in range(5):
            self.add_item(NinjaEggButton(game_key, i, golden, rnd, hearts, pts, uid))


class RoletaCoelhoView(View):
    def __init__(self, uid: str):
        super().__init__(timeout=60)
        self.uid = uid
        btn = Button(label="🎰 GIRAR a Roleta do Coelho", style=discord.ButtonStyle.success, row=0)

        async def girar(interaction: discord.Interaction):
            if str(interaction.user.id) != uid:
                await interaction.response.send_message("❌ Não é sua roleta!", ephemeral=True)
                return
            outcomes = [
                ("💨 Só cheiro de cenoura… nada de ovo.", 0, 0),
                ("🥚 Ovo de galinha (mentira, é de chocolate).", 6, 45),
                ("🍫 Ovo médio — respeitável!", 14, 110),
                ("✨ OVO RELUZENTE! O coelho piscou pra você.", 28, 240),
                ("🌈 JACKPOT DO JARDIM! Chuva de ovos!", 55, 420),
            ]
            weights = [0.18, 0.34, 0.28, 0.14, 0.06]
            texto, pts, moedas = random.choices(outcomes, weights=weights, k=1)[0]
            if pts:
                bot.add_pascoa_pontos(uid, pts)
            if moedas:
                if uid not in bot.user_balances:
                    bot.user_balances[uid] = 0
                bot.user_balances[uid] += moedas
            bot.save_data()
            bot.pascoa_roleta_cd[uid] = datetime.now(BR_TZ).isoformat()
            cor = discord.Color.gold() if pts >= 28 else discord.Color.from_str("#FF69B4") if pts else discord.Color.dark_gray()
            emb = discord.Embed(
                title="🎰 Roleta parou em…",
                description=f"**{texto}**\n\n🥚 **+{pts}** pts Páscoa\n🍫 **+{moedas}** moedas",
                color=cor,
            )
            emb.set_image(url=random.choice(GIFS_PASCOA))
            emb.set_footer(text="Cooldown 25 min para girar de novo.")
            await interaction.response.edit_message(embed=emb, view=None)
            self.stop()

        btn.callback = girar
        self.add_item(btn)


@bot.tree.command(name="pascoa_cacaninja", description="🥷 3 rodadas, 5 ovos — ache o dourado (3 ❤️)")
async def pascoa_cacaninja(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)
    raw = bot.pascoa_cacaninja_cd.get(user_id)
    if raw:
        ult = datetime.fromisoformat(raw)
        if ult.tzinfo is None:
            ult = ult.replace(tzinfo=BR_TZ)
        if agora - ult < timedelta(minutes=25):
            m = int((timedelta(minutes=25) - (agora - ult)).total_seconds() // 60)
            await interaction.response.send_message(f"🥷 O coelho escondeu os ovos de novo. Volte em **{m} min**.", ephemeral=True)
            return
    game_key = str(interaction.id)
    emb = discord.Embed(
        title="🥷 Caça-Ninja do Coelho",
        description="**3 rodadas.** Em cada uma, **exatamente um** ovo (①–⑤) é o **dourado**.\n\n"
        "• Acertou → próxima rodada (mais pontos por acerto).\n"
        "• Errou → perde **1 ❤️** (você tem 3).\n"
        "• **Limpe as 3** → bônus enorme + moedas.\n\n"
        "_O coelho troca tudo a cada tentativa. Boa sorte._",
        color=discord.Color.from_str("#FFD700"),
    )
    emb.set_image(url=random.choice(GIFS_OVO))
    emb.set_footer(text="Cooldown 25 min após terminar a partida.")
    view = PascoaCacaNinjaView(game_key, user_id, 1, 3, 0)
    await interaction.response.send_message(embed=emb, view=view)


@bot.tree.command(name="pascoa_roleta", description="🎰 Roleta do coelho — prêmios variados (cooldown 25min)")
async def pascoa_roleta(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)
    raw = bot.pascoa_roleta_cd.get(user_id)
    if raw:
        ult = datetime.fromisoformat(raw)
        if ult.tzinfo is None:
            ult = ult.replace(tzinfo=BR_TZ)
        if agora - ult < timedelta(minutes=25):
            m = int((timedelta(minutes=25) - (agora - ult)).total_seconds() // 60)
            await interaction.response.send_message(f"🎰 A roleta esfriando… **{m} min**.", ephemeral=True)
            return
    emb = discord.Embed(
        title="🎰 Roleta do Coelho da Páscoa",
        description="Um giro, um destino. Pode sair **nada**, ovos comuns ou **jackpot raro**.\n\nClique em **GIRAR** quando estiver pronto(a).",
        color=discord.Color.from_str("#FF69B4"),
    )
    emb.set_thumbnail(url=random.choice(GIFS_PASCOA))
    await interaction.response.send_message(embed=emb, view=RoletaCoelhoView(user_id))


@bot.tree.command(name="pascoa_caca", description="🐇 Caçar o coelho (cooldown 1h)")
async def pascoa_caca(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)
    if user_id in bot.pascoa_coelho:
        ultimo = datetime.fromisoformat(bot.pascoa_coelho[user_id])
        if ultimo.tzinfo is None:
            ultimo = ultimo.replace(tzinfo=BR_TZ)
        if agora - ultimo < timedelta(hours=1):
            restante = timedelta(hours=1) - (agora - ultimo)
            await interaction.response.send_message(f"🐇 Volte em **{int(restante.total_seconds() // 60)} min**.", ephemeral=True)
            return
    roll = random.random()
    gif = random.choice(GIFS_COELHO)
    deco = easter_header()
    bot.pascoa_coelho[user_id] = agora.isoformat()
    if roll < 0.60:
        pontos, moedas = random.randint(8, 20), random.randint(100, 250)
        bot.add_pascoa_pontos(user_id, pontos)
        if user_id not in bot.user_balances:
            bot.user_balances[user_id] = 0
        bot.user_balances[user_id] += moedas
        bot.save_data()
        embed = discord.Embed(title=f"{deco} COELHO! {deco}", description="Você encontrou o coelho! 🐇", color=discord.Color.green())
        embed.set_image(url=gif)
        embed.add_field(name="🥚 Pontos", value=f"+{pontos}", inline=True)
        embed.add_field(name="🍫 Moedas", value=f"+{moedas}", inline=True)
    elif roll < 0.85:
        pontos = random.randint(2, 5)
        bot.add_pascoa_pontos(user_id, pontos)
        bot.save_data()
        embed = discord.Embed(title="💨 Quase!", description="Fugiu, mas você ganhou uns pontinhos.", color=discord.Color.orange())
        embed.set_image(url=gif)
        embed.add_field(name="🥚 Pontos", value=f"+{pontos}", inline=True)
    else:
        embed = discord.Embed(title="😅 Escapou!", description="Hoje não deu — tente de novo depois.", color=discord.Color.red())
        embed.set_image(url=gif)
    embed.timestamp = agora
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pascoa_ovo", description="🥚 Procurar ovo (20min por canal)")
async def pascoa_ovo(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)
    chave = f"{user_id}_{interaction.channel.id}"
    if chave in bot.pascoa_ovos:
        ultimo = datetime.fromisoformat(bot.pascoa_ovos[chave])
        if ultimo.tzinfo is None:
            ultimo = ultimo.replace(tzinfo=BR_TZ)
        if agora - ultimo < timedelta(minutes=20):
            r = timedelta(minutes=20) - (agora - ultimo)
            await interaction.response.send_message(f"🥚 Espere **{int(r.total_seconds() // 60)}m**.", ephemeral=True)
            return
    bot.pascoa_ovos[chave] = agora.isoformat()
    tipos = [
        ("🥚 Ovo Comum", 3, 30),
        ("🥚 Colorido", 6, 60),
        ("🥚 Chocolate", 10, 100),
        ("🥚 Dourado", 20, 250),
        ("🥚 Cristal", 35, 500),
        ("🥚 Vazio", 0, 0),
    ]
    pesos = [35, 30, 20, 10, 3, 2]
    nome, pontos, moedas = random.choices(tipos, weights=pesos, k=1)[0]
    deco = easter_header()
    if pontos > 0:
        bot.add_pascoa_pontos(user_id, pontos)
        if user_id not in bot.user_balances:
            bot.user_balances[user_id] = 0
        bot.user_balances[user_id] += moedas
        bot.save_data()
        embed = discord.Embed(title=f"{deco} OVO! {deco}", description=nome, color=discord.Color.from_str("#FFD700"))
        embed.set_image(url=random.choice(GIFS_OVO))
        embed.add_field(name="Pontos", value=f"+{pontos}", inline=True)
        embed.add_field(name="Moedas", value=f"+{moedas}", inline=True)
    else:
        embed = discord.Embed(title="😔 Vazio...", description="Só casca.", color=discord.Color.dark_gray())
        embed.set_image(url=random.choice(GIFS_OVO))
    embed.timestamp = agora
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pascoa_corrida", description="🐇 Corrida de coelhos (50 moedas)")
async def pascoa_corrida(interaction: discord.Interaction, coelho: int):
    user_id = str(interaction.user.id)
    if coelho < 1 or coelho > 5:
        await interaction.response.send_message("❌ Escolha 1 a 5!", ephemeral=True)
        return
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 50:
        await interaction.response.send_message("❌ Precisa de 50 moedas!", ephemeral=True)
        return
    bot.user_balances[user_id] -= 50
    coelhos = ["🐰 A", "🐇 B", "🐰 C", "🐇 D", "🐰 E"]
    posicoes = list(range(5))
    random.shuffle(posicoes)
    vencedor_idx = posicoes[0]
    ganhou = (coelho - 1) == vencedor_idx
    corrida_texto = ""
    for i in range(5):
        passos = random.randint(3, 18)
        pista = "▫️" * passos + "🐇" + "▫️" * (20 - passos)
        if i == vencedor_idx:
            pista = "🏆" + pista[1:]
        corrida_texto += f"{i+1}. {pista} {coelhos[i]}\n"
    deco = easter_header()
    if ganhou:
        mult = random.choice([2, 3, 4, 5])
        premio = 50 * mult
        bot.user_balances[user_id] += premio
        bot.add_pascoa_pontos(user_id, 15)
        bot.save_data()
        embed = discord.Embed(title=f"{deco} VENCEU! {deco}", description=f"```{corrida_texto}```", color=discord.Color.gold())
        embed.add_field(name="Prêmio", value=f"{premio} moedas (x{mult})", inline=True)
        embed.set_image(url=random.choice(GIFS_COELHO))
    else:
        embed = discord.Embed(title="😔 Não foi dessa vez", description=f"```{corrida_texto}```", color=discord.Color.red())
        embed.add_field(name="Vencedor", value=coelhos[vencedor_idx], inline=True)
        bot.save_data()
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pascoa_chocolate", description="🍫 Presentear (80 moedas)")
async def pascoa_chocolate(interaction: discord.Interaction, membro: discord.Member, mensagem: str = ""):
    user_id = str(interaction.user.id)
    if membro == interaction.user:
        await interaction.response.send_message("❌ Escolha outra pessoa.", ephemeral=True)
        return
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 80:
        await interaction.response.send_message("❌ 80 moedas necessárias.", ephemeral=True)
        return
    bot.user_balances[user_id] -= 80
    tid = str(membro.id)
    if tid not in bot.user_balances:
        bot.user_balances[tid] = 0
    bot.user_balances[tid] += 30
    bot.add_pascoa_pontos(user_id, 5)
    bot.save_data()
    chocs = ["🍫 Ao leite", "🍬 Bombom", "🥚 Ovo gigante", "🍭 Trufa"]
    c = random.choice(chocs)
    embed = discord.Embed(
        title="🍫 Chocolate de Páscoa!",
        description=f"**{interaction.user.display_name}** → **{membro.display_name}** — {c}",
        color=discord.Color.from_str("#8B4513"),
    )
    embed.set_image(url=random.choice(GIFS_CHOCOLHATE))
    if mensagem:
        embed.add_field(name="💌", value=mensagem[:500], inline=False)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pascoa_ranking", description="🏆 Ranking de Páscoa")
async def pascoa_ranking(interaction: discord.Interaction):
    if not bot.pascoa_pontos:
        await interaction.response.send_message("🐣 Ninguém tem pontos ainda!", ephemeral=True)
        return
    membros = []
    for uid, pontos in bot.pascoa_pontos.items():
        m = interaction.guild.get_member(int(uid))
        if m and not m.bot and pontos > 0:
            membros.append((m, pontos))
    membros.sort(key=lambda x: x[1], reverse=True)
    if not membros:
        await interaction.response.send_message("🐣 Ranking vazio neste servidor.", ephemeral=True)
        return
    texto = ""
    medals = ["🥇", "🥈", "🥉"]
    for i, (m, p) in enumerate(membros[:15], 1):
        texto += f"{medals[i-1] if i <= 3 else str(i)+'.'} {m.display_name} — **{p}** pts\n"
    embed = discord.Embed(title=f"{easter_header()} RANKING {easter_header()}", description=texto, color=discord.Color.gold())
    uid = str(interaction.user.id)
    pos = next((i + 1 for i, (m, _) in enumerate(membros) if str(m.id) == uid), None)
    if pos:
        embed.add_field(name="Você", value=f"{pos}º — {bot.pascoa_pontos.get(uid, 0)} pts", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pascoa_pontos", description="🥚 Ver pontos de Páscoa")
async def pascoa_pontos_cmd(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    membro = membro or interaction.user
    user_id = str(membro.id)
    pontos = bot.pascoa_pontos.get(user_id, 0)
    ranking = sorted(bot.pascoa_pontos.items(), key=lambda x: x[1], reverse=True)
    pos = next((i + 1 for i, (u, _) in enumerate(ranking) if u == user_id), None)
    embed = discord.Embed(title="🥚 Pontos de Páscoa", description=f"**{membro.display_name}** — **{pontos}** pts", color=discord.Color.from_str("#FF69B4"))
    embed.set_thumbnail(url=membro.display_avatar.url)
    if pos:
        embed.add_field(name="Ranking geral", value=f"{pos}º lugar", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pascoa_slot", description="🎰 Slot de Páscoa (40 moedas)")
async def pascoa_slot(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    if user_id not in bot.user_balances or bot.user_balances[user_id] < 40:
        await interaction.response.send_message("❌ 40 moedas!", ephemeral=True)
        return
    bot.user_balances[user_id] -= 40
    sims = ["🥚", "🐣", "🐇", "🌸", "🍫", "🌷", "✝️", "🎀"]
    w = [25, 20, 15, 15, 10, 8, 5, 2]
    r = random.choices(sims, weights=w, k=3)
    premio_moedas = premio_pts = 0
    msg = "😔 Sem prêmio."
    if r[0] == r[1] == r[2]:
        msg = "🎊 TRIPLO!"
        table = {"🎀": (2000, 100), "✝️": (800, 50), "🍫": (500, 30), "🐇": (400, 25), "🥚": (300, 20)}
        premio_moedas, premio_pts = table.get(r[0], (200, 15))
    elif r[0] == r[1] or r[1] == r[2] or r[0] == r[2]:
        premio_moedas, premio_pts = 80, 5
        msg = "🥳 Par!"
    if premio_moedas:
        bot.user_balances[user_id] += premio_moedas
        bot.add_pascoa_pontos(user_id, premio_pts)
    bot.save_data()
    embed = discord.Embed(
        title="🎰 Slot Páscoa",
        description=f"# `{r[0]} | {r[1]} | {r[2]}`\n{msg}",
        color=discord.Color.gold() if premio_moedas else discord.Color.dark_gray(),
    )
    if premio_moedas:
        embed.add_field(name="Moedas", value=f"+{premio_moedas}", inline=True)
        embed.add_field(name="Pts", value=f"+{premio_pts}", inline=True)
        embed.set_image(url=random.choice(GIFS_PASCOA))
    embed.add_field(name="Saldo", value=str(bot.user_balances.get(user_id, 0)), inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pascoa_info", description="🐣 Info do sistema de Páscoa")
async def pascoa_info(interaction: discord.Interaction):
    embed = discord.Embed(
        title=f"{easter_header()} Páscoa {easter_header()}",
        description="Minigames, pontos acumuláveis e ranking.",
        color=discord.Color.from_str("#FFD700"),
    )
    embed.add_field(
        name="Comandos",
        value="`/pascoa_daily` `/pascoa_quiz` `/pascoa_memoria` `/pascoa_anagrama`\n"
        "`/pascoa_cacaninja` `/pascoa_roleta` — **novos**\n"
        "`/pascoa_caca` `/pascoa_ovo` `/pascoa_corrida` `/pascoa_slot`\n"
        "`/pascoa_chocolate` `/pascoa_ranking` `/pascoa_pontos`",
        inline=False,
    )
    await interaction.response.send_message(embed=embed)


# Giphy = URL direto .gif (Discord embute bem). Tenor /m/... costuma falhar no embed.set_image.
GIFS_RP = {
    "abraco": [
        "https://media.giphy.com/media/1JmGiBtqTuehfYxuy9/giphy.gif",
        "https://media.giphy.com/media/3M4NpbLCTxBqU/giphy.gif",
        "https://media.giphy.com/media/l0MYC0LajPMPoXORq/giphy.gif",
        "https://media.giphy.com/media/26gspipWnu5Dz4rRS/giphy.gif",
        "https://media.giphy.com/media/Zqlv6aqpNNOd2/giphy.gif",
    ],
    "beijo": [
        "https://media.giphy.com/media/bmrxNoeuqdsKWEXCYH/giphy.gif",
        "https://media.giphy.com/media/12XvRnZ6MRcLq0/giphy.gif",
        "https://media.giphy.com/media/IWrQSJARGbC6bad78H/giphy.gif",
        "https://media.giphy.com/media/3o7TKU1IgV89jT9ZQ4/giphy.gif",
        "https://media.giphy.com/media/26AHG5KGFxSkUWw1i/giphy.gif",
    ],
    "choro": [
        "https://media.giphy.com/media/ISOckXUbnVfQ4/giphy.gif",
        "https://media.giphy.com/media/d2lcHJUH5D0KM/giphy.gif",
        "https://media.giphy.com/media/BEob5qwFkSJ7G/giphy.gif",
    ],
    "riso": [
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif",
        "https://media.giphy.com/media/l3q2K5jinAlChoCLS/giphy.gif",
        "https://media.giphy.com/media/3ohzdMvc1w2Vl0pZ6w/giphy.gif",
    ],
    "sono": [
        "https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif",
        "https://media.giphy.com/media/l0HlNQ03J5JxX6lva/giphy.gif",
        "https://media.giphy.com/media/3ohzdIuqJ1006bcgU8/giphy.gif",
    ],
    "briga": [
        "https://media.giphy.com/media/kiBkwEXfBTWPK/giphy.gif",
        "https://media.giphy.com/media/l3V0j3ytFyGHqiV7W/giphy.gif",
        "https://media.giphy.com/media/3o7aCTPPm4OHfRLSH6/giphy.gif",
    ],
    "dance": [
        "https://media.giphy.com/media/3o7TKSjRrfIPiNh9XS/giphy.gif",
        "https://media.giphy.com/media/l0HlBO7eyXzSZkJri/giphy.gif",
        "https://media.giphy.com/media/5xaOcLGvzHxDKjufnLW/giphy.gif",
    ],
    "pensando": [
        "https://media.giphy.com/media/3o7bu3XilJ5BOiSGic/giphy.gif",
        "https://media.giphy.com/media/26ufdipQqU2lhNA4g/giphy.gif",
    ],
    "susto": [
        "https://media.giphy.com/media/l3V0gGZJa5anBW5t6/giphy.gif",
        "https://media.giphy.com/media/3o7aCTPPm4OHfRLSH6/giphy.gif",
    ],
    "olhando": [
        "https://media.giphy.com/media/3o7btPCcdNniyf0ArS/giphy.gif",
        "https://media.giphy.com/media/26ufdipQqU2lhNA4g/giphy.gif",
    ],
    "envergonhado": [
        "https://media.giphy.com/media/ISOckXUbnVfQ4/giphy.gif",
        "https://media.giphy.com/media/l3V0gGZJa5anBW5t6/giphy.gif",
    ],
    "mimos": [
        "https://media.giphy.com/media/3M4NpbLCTxBqU/giphy.gif",
        "https://media.giphy.com/media/l0MYC0LajPMPoXORq/giphy.gif",
        "https://media.giphy.com/media/26gspipWnu5Dz4rRS/giphy.gif",
        "https://media.giphy.com/media/Zqlv6aqpNNOd2/giphy.gif",
    ],
    "raiva": [
        "https://media.giphy.com/media/kiBkwEXfBTWPK/giphy.gif",
        "https://media.giphy.com/media/l3V0j3ytFyGHqiV7W/giphy.gif",
    ],
    "curiosidade": [
        "https://media.giphy.com/media/3o7bu3XilJ5BOiSGic/giphy.gif",
        "https://media.giphy.com/media/26ufdipQqU2lhNA4g/giphy.gif",
    ],
    "tristeza": [
        "https://media.giphy.com/media/ISOckXUbnVfQ4/giphy.gif",
        "https://media.giphy.com/media/d2lcHJUH5D0KM/giphy.gif",
    ],
    "comemoracao": [
        "https://media.giphy.com/media/5GoVLqeAOo6PK/giphy.gif",
        "https://media.giphy.com/media/3ohzdIuqJ1006bcgU8/giphy.gif",
        "https://media.giphy.com/media/l0HlBO7eyXzSZkJri/giphy.gif",
    ],
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
    "comemoracao": discord.Color.gold(),
}

gifs_abraco = GIFS_RP["abraco"]
gifs_beijo = GIFS_RP["beijo"]
gifs_carinho = GIFS_RP["mimos"]
gifs_festa = GIFS_RP["comemoracao"]
gifs_tapa = GIFS_RP["briga"]
gifs_matar = GIFS_RP["briga"]


async def rp_acao(interaction: discord.Interaction, acao: str, titulo: str, membro: Optional[discord.Member], sozinho: str, com_alvo: str):
    gif = random.choice(GIFS_RP.get(acao, ["https://media.giphy.com/media/3ZnBrkqoaI2hq/giphy.gif"]))
    cor = RP_CORES.get(acao, discord.Color.blue())
    if membro and membro != interaction.user:
        desc = com_alvo.format(user=interaction.user.mention, alvo=membro.mention)
    else:
        desc = sozinho.format(user=interaction.user.mention)
    embed = discord.Embed(title=titulo, description=desc, color=cor)
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_abraco", description="🤗 Abraço em RP")
async def rp_abraco(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "abraco", "🤗 ABRAÇO!", membro, "**{user}** se abraça sozinho…", "**{user}** abraça **{alvo}**!")


@bot.tree.command(name="rp_beijo", description="💋 Beijo em RP")
async def rp_beijo(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "beijo", "💋 BEIJO!", membro, "**{user}** manda beijo pro vento!", "**{user}** beija **{alvo}**!")


@bot.tree.command(name="rp_chora", description="😭 Chorar em RP")
async def rp_chora(interaction: discord.Interaction, motivo: str = ""):
    gif = random.choice(GIFS_RP["choro"])
    d = f"**{interaction.user.mention}** chora"
    if motivo:
        d += f": *{motivo}*"
    d += " 😭"
    embed = discord.Embed(title="😭 …", description=d, color=discord.Color.blue())
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_ri", description="😂 Rir em RP")
async def rp_ri(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "riso", "😂 HAHA", membro, "**{user}** ri sozinho!", "**{user}** ri de **{alvo}**!")


@bot.tree.command(name="rp_dorme", description="😴 Dormir em RP")
async def rp_dorme(interaction: discord.Interaction):
    gif = random.choice(GIFS_RP["sono"])
    embed = discord.Embed(
        title="😴 Zzz",
        description=random.choice(
            [
                f"**{interaction.user.mention}** adormece…",
                f"**{interaction.user.mention}** boceja e apaga as luzes…",
            ]
        ),
        color=discord.Color.dark_blue(),
    )
    embed.set_image(url=gif)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_briga", description="💢 Brigar em RP")
async def rp_briga(interaction: discord.Interaction, membro: discord.Member, motivo: str = ""):
    gif = random.choice(GIFS_RP["briga"])
    d = f"**{interaction.user.mention}** e **{membro.mention}** brigam"
    if motivo:
        d += f" — *{motivo}*"
    d += "!"
    embed = discord.Embed(title="💢", description=d, color=discord.Color.orange())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_danca", description="💃 Dançar em RP")
async def rp_danca(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "dance", "💃", membro, "**{user}** dança solo!", "**{user}** puxa **{alvo}** pra dançar!")


@bot.tree.command(name="rp_envergonha", description="😳 Vergonha em RP")
async def rp_envergonha(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "envergonhado", "😳", membro, "**{user}** fica vermelho…", "**{user}** fica sem graça por **{alvo}**!")


@bot.tree.command(name="rp_mimos", description="🥰 Mimos em RP")
async def rp_mimos(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    await rp_acao(interaction, "mimos", "🥰 MIMOS", membro, "**{user}** derrete de fofura.", "**{user}** mimosa **{alvo}**!")


@bot.tree.command(name="rp_raiva", description="😡 Raiva em RP")
async def rp_raiva(interaction: discord.Interaction, membro: Optional[discord.Member] = None, motivo: str = ""):
    gif = random.choice(GIFS_RP["raiva"])
    if membro and membro != interaction.user:
        d = f"**{interaction.user.mention}** está pistola com **{membro.mention}**"
    else:
        d = f"**{interaction.user.mention}** está FURIOSO(A)"
    if motivo:
        d += f" — *{motivo}*"
    embed = discord.Embed(title="😡", description=d, color=discord.Color.dark_red())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_susto", description="😱 Susto em RP")
async def rp_susto(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    gif = random.choice(GIFS_RP["susto"])
    if membro and membro != interaction.user:
        d = f"**{membro.mention}** assustou **{interaction.user.mention}**!"
    else:
        d = f"**{interaction.user.mention}** levou um susto!"
    embed = discord.Embed(title="😱", description=d, color=discord.Color.dark_gray())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_comemora", description="🎉 Comemorar em RP")
async def rp_comemora(interaction: discord.Interaction, motivo: str = "", membro: Optional[discord.Member] = None):
    gif = random.choice(GIFS_RP["comemoracao"])
    if membro and membro != interaction.user:
        d = f"**{interaction.user.mention}** comemora com **{membro.mention}**"
    else:
        d = f"**{interaction.user.mention}** comemora"
    if motivo:
        d += f": *{motivo}*"
    embed = discord.Embed(title="🎉", description=d + "!", color=discord.Color.gold())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_tristeza", description="💔 Tristeza em RP")
async def rp_tristeza(interaction: discord.Interaction, motivo: str = ""):
    gif = random.choice(GIFS_RP["tristeza"])
    d = random.choice([f"**{interaction.user.mention}** está de coração pesado…", f"**{interaction.user.mention}** olha pro vazio…"])
    if motivo:
        d += f"\n*{motivo}*"
    embed = discord.Embed(title="💔", description=d, color=discord.Color.dark_blue())
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_curiosidade", description="🔍 Curiosidade em RP")
async def rp_curiosidade(interaction: discord.Interaction, membro: Optional[discord.Member] = None, sobre: str = ""):
    gif = random.choice(GIFS_RP["curiosidade"])
    if membro and membro != interaction.user:
        d = f"**{interaction.user.mention}** fuça **{membro.mention}** com olhos brilhantes"
    else:
        d = f"**{interaction.user.mention}** está curioso(a)"
    if sobre:
        d += f" sobre *{sobre}*"
    embed = discord.Embed(title="🔍", description=d + "…", color=discord.Color.from_str("#87CEEB"))
    embed.set_image(url=gif)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_acao", description="✨ Ação livre em itálico")
async def rp_acao_cmd(interaction: discord.Interaction, acao: str, membro: Optional[discord.Member] = None):
    if membro and membro != interaction.user:
        desc = f"*{interaction.user.display_name} {acao} {membro.display_name}*"
    else:
        desc = f"*{interaction.user.display_name} {acao}*"
    embed = discord.Embed(description=desc, color=discord.Color.from_str("#DDA0DD"))
    embed.set_author(name=interaction.user.display_name, icon_url=interaction.user.display_avatar.url)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_fala", description="💬 Fala em personagem")
async def rp_fala(interaction: discord.Interaction, texto: str, personagem: str = ""):
    nome = personagem or interaction.user.display_name
    embed = discord.Embed(description=f'\u201c{texto[:1800]}\u201d', color=discord.Color.from_str("#98FB98"))
    embed.set_author(name=f"💬 {nome}", icon_url=interaction.user.display_avatar.url)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="rp_carinho", description="🌸 Carinho fofo (estilo light novel)")
async def rp_carinho(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    gif = random.choice(GIFS_RP["mimos"])
    if membro and membro != interaction.user:
        desc = f"*— {interaction.user.display_name} faz um carinho gentil em {membro.display_name}; as bochechas esquentam.* 💗"
    else:
        desc = f"*— {interaction.user.display_name} se enrola num cobertor imaginário.* 🌸"
    emb = discord.Embed(title="🌸 momento fofo", description=desc, color=discord.Color.from_str("#FFB7C5"))
    emb.set_image(url=gif)
    emb.set_footer(text="RP leve")
    emb.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=emb)


@bot.tree.command(name="rp_narrar", description="📖 Narração curta (3ª pessoa)")
async def rp_narrar(interaction: discord.Interaction, texto: str):
    emb = discord.Embed(description=f"*{texto[:1800]}*", color=discord.Color.from_str("#E6E6FA"))
    emb.set_author(name=f"📖 {interaction.user.display_name}", icon_url=interaction.user.display_avatar.url)
    emb.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=emb)


@bot.tree.command(name="rp_ficha", description="📋 Ficha de RP")
async def rp_ficha(interaction: discord.Interaction, nome: str = None, idade: str = None, personalidade: str = None, historia: str = None):
    user_id = str(interaction.user.id)
    if not any([nome, idade, personalidade, historia]):
        if user_id not in bot.rp_fichas:
            await interaction.response.send_message("📋 Use `/rp_ficha` com campos para criar.", ephemeral=True)
            return
        f = bot.rp_fichas[user_id]
        embed = discord.Embed(title=f"📋 {f.get('nome', interaction.user.display_name)}", color=discord.Color.from_str("#DDA0DD"))
        embed.set_thumbnail(url=interaction.user.display_avatar.url)
        for k, label in [("nome", "Nome"), ("idade", "Idade"), ("personalidade", "Personalidade"), ("historia", "História")]:
            if f.get(k):
                embed.add_field(name=label, value=str(f[k])[:1024], inline=k in ("nome", "idade"))
        await interaction.response.send_message(embed=embed)
        return
    bot.rp_fichas.setdefault(user_id, {})
    if nome:
        bot.rp_fichas[user_id]["nome"] = nome
    if idade:
        bot.rp_fichas[user_id]["idade"] = idade
    if personalidade:
        bot.rp_fichas[user_id]["personalidade"] = personalidade
    if historia:
        bot.rp_fichas[user_id]["historia"] = historia
    bot.save_rp()
    await interaction.response.send_message("✅ Ficha salva!", ephemeral=True)


@bot.tree.command(name="rp_ver_ficha", description="👁️ Ver ficha de outro membro")
async def rp_ver_ficha(interaction: discord.Interaction, membro: discord.Member):
    user_id = str(membro.id)
    if user_id not in bot.rp_fichas or not bot.rp_fichas[user_id]:
        await interaction.response.send_message("❌ Sem ficha.", ephemeral=True)
        return
    f = bot.rp_fichas[user_id]
    embed = discord.Embed(title=f"📋 {f.get('nome', membro.display_name)}", color=discord.Color.from_str("#DDA0DD"))
    embed.set_thumbnail(url=membro.display_avatar.url)
    for k, label in [("nome", "Nome"), ("idade", "Idade"), ("personalidade", "Personalidade"), ("historia", "História")]:
        if f.get(k):
            embed.add_field(name=label, value=str(f[k])[:1024], inline=k in ("nome", "idade"))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="ship", description="💖 Compatibilidade")
async def ship(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    base = random.randint(40, 90)
    cargos = set(pessoa1.roles) & set(pessoa2.roles)
    if len(cargos) > 1:
        base += len(cargos) * 2
    if pessoa1.name[0].lower() == pessoa2.name[0].lower():
        base += 2
    pct = max(0, min(100, base))
    if random.random() < 0.01:
        pct = 100
    nome = pessoa1.display_name[: len(pessoa1.display_name) // 2] + pessoa2.display_name[len(pessoa2.display_name) // 2 :]
    barras = "█" * (pct // 10) + "░" * (10 - (pct // 10))
    cor = discord.Color.purple()
    msg = "💝"
    if pct < 20:
        cor, msg = discord.Color.dark_gray(), "💔"
    elif pct < 60:
        cor, msg = discord.Color.orange(), "💛"
    elif pct < 90:
        cor, msg = discord.Color.green(), "💙"
    embed = discord.Embed(title="💖 Ship", description=f"{pessoa1.mention} 💘 {pessoa2.mention}", color=cor)
    embed.add_field(name="Compatibilidade", value=f"**{pct}%**\n`{barras}`", inline=False)
    embed.add_field(name="Nome do casal", value=nome, inline=True)
    embed.add_field(name="Vibe", value=msg, inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="shippar", description="💘 Registrar ship")
async def shippar(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    if pessoa1 == pessoa2:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    sid = f"{pessoa1.id}-{pessoa2.id}"
    if sid in bot.ship_data:
        await interaction.response.send_message("❌ Já existe.", ephemeral=True)
        return
    bot.ship_data[sid] = {
        "pessoa1": str(pessoa1.id),
        "pessoa2": str(pessoa2.id),
        "likes": 0,
        "criado_por": str(interaction.user.id),
        "data": datetime.now(BR_TZ).isoformat(),
    }
    bot.save_data()
    embed = discord.Embed(title="💘 NOVO SHIP", description=f"{pessoa1.mention} 💕 {pessoa2.mention}", color=discord.Color.from_str("#FF69B4"))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="likeship", description="👍 Like no ship")
async def likeship(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    sid = f"{pessoa1.id}-{pessoa2.id}"
    if sid not in bot.ship_data:
        await interaction.response.send_message("❌ Ship não existe.", ephemeral=True)
        return
    bot.ship_data[sid]["likes"] += 1
    bot.save_data()
    await interaction.response.send_message(f"👍 Total: {bot.ship_data[sid]['likes']}")


@bot.tree.command(name="shipinfo", description="ℹ️ Info do ship")
async def shipinfo(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    sid = f"{pessoa1.id}-{pessoa2.id}"
    if sid not in bot.ship_data:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    d = bot.ship_data[sid]
    criador = interaction.guild.get_member(int(d["criado_por"]))
    embed = discord.Embed(title="ℹ️ Ship", color=discord.Color.blue())
    embed.add_field(name="Likes", value=d["likes"], inline=True)
    embed.add_field(name="Criador", value=criador.mention if criador else "?", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="meusships", description="📋 Ships que você criou")
async def meusships(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    ships = [s for s, d in bot.ship_data.items() if str(d["criado_por"]) == uid]
    if not ships:
        await interaction.response.send_message("❌ Nenhum.", ephemeral=True)
        return
    embed = discord.Embed(title="📋 Meus ships", color=discord.Color.blue())
    for sid in ships[:10]:
        d = bot.ship_data[sid]
        p1 = interaction.guild.get_member(int(d["pessoa1"]))
        p2 = interaction.guild.get_member(int(d["pessoa2"]))
        if p1 and p2:
            embed.add_field(name=f"{p1.display_name} x {p2.display_name}", value=f"👍 {d['likes']}", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="topship", description="🏆 Top ships")
async def topship(interaction: discord.Interaction):
    top = sorted(bot.ship_data.items(), key=lambda x: x[1]["likes"], reverse=True)[:10]
    if not top:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    embed = discord.Embed(title="🏆 TOP SHIPS", color=discord.Color.gold())
    for i, (sid, d) in enumerate(top, 1):
        p1 = interaction.guild.get_member(int(d["pessoa1"]))
        p2 = interaction.guild.get_member(int(d["pessoa2"]))
        if p1 and p2:
            embed.add_field(name=f"{i}. {p1.display_name} x {p2.display_name}", value=f"👍 {d['likes']}", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="shiplist", description="📜 Lista ships")
async def shiplist(interaction: discord.Interaction):
    rows = []
    for d in bot.ship_data.values():
        p1 = interaction.guild.get_member(int(d["pessoa1"]))
        p2 = interaction.guild.get_member(int(d["pessoa2"]))
        if p1 and p2:
            rows.append(f"{p1.display_name} 💘 {p2.display_name} — {d['likes']}")
    if not rows:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    await interaction.response.send_message(embed=discord.Embed(title="📜 Ships", description="\n".join(rows[:20]), color=discord.Color.blue()))


@bot.tree.command(name="calcular_amor", description="🔮 Análise aleatória")
async def calcular_amor(interaction: discord.Interaction, pessoa1: discord.Member, pessoa2: discord.Member):
    cats = {k: random.randint(0, 100) for k in ["Amizade", "Paixão", "Confiança", "Comunicação", "Futuro"]}
    media = sum(cats.values()) // len(cats)
    embed = discord.Embed(title="🔮", description=f"{pessoa1.mention} ❤️ {pessoa2.mention}", color=discord.Color.purple())
    for k, v in cats.items():
        embed.add_field(name=k, value=f"{v}%", inline=True)
    embed.add_field(name="Média", value=f"{media}%", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="pedir", description="💍 Pedido (2000 moedas)")
async def pedir(interaction: discord.Interaction, pessoa: discord.Member):
    uid, tid = str(interaction.user.id), str(pessoa.id)
    if pessoa == interaction.user or pessoa.bot:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    for d in bot.marriage_data.values():
        if uid in (d["pessoa1"], d["pessoa2"]):
            await interaction.response.send_message("❌ Você já está casado(a).", ephemeral=True)
            return
        if tid in (d["pessoa1"], d["pessoa2"]):
            await interaction.response.send_message("❌ Essa pessoa já está casada.", ephemeral=True)
            return
    if uid not in bot.user_balances or bot.user_balances[uid] < 2000:
        await interaction.response.send_message("❌ 2000 moedas.", ephemeral=True)
        return
    bot.user_balances[uid] -= 2000
    bot.save_data()
    embed = discord.Embed(
        title="💍 PEDIDO",
        description=f"{interaction.user.mention} pediu {pessoa.mention} em casamento!\n{pessoa.mention}: `/aceitar` ou `/recusar`",
        color=discord.Color.from_str("#FF69B4"),
    )
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="aceitar", description="💞 Aceitar casamento")
async def aceitar(interaction: discord.Interaction, pessoa: discord.Member):
    uid, pid = str(interaction.user.id), str(pessoa.id)
    mid = f"{pid}-{uid}-{int(datetime.now(BR_TZ).timestamp())}"
    bot.marriage_data[mid] = {
        "pessoa1": pid,
        "pessoa2": uid,
        "data_casamento": datetime.now(BR_TZ).isoformat(),
        "aniversarios_comemorados": 0,
        "luademel": True,
        "presentes": [],
    }
    for x in (pid, uid):
        bot.user_balances.setdefault(x, 0)
        bot.user_balances[x] += 1000
    bot.save_data()
    await interaction.response.send_message(embed=discord.Embed(title="💞 CASADOS!", description=f"{pessoa.mention} ❤️ {interaction.user.mention}", color=discord.Color.gold()))


@bot.tree.command(name="recusar", description="💔 Recusar")
async def recusar(interaction: discord.Interaction, pessoa: discord.Member):
    await interaction.response.send_message(embed=discord.Embed(title="💔", description=f"{interaction.user.mention} recusou.", color=discord.Color.dark_gray()))


@bot.tree.command(name="divorciar", description="💔 Divórcio (5000 moedas)")
async def divorciar(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    mid = next((m for m, d in bot.marriage_data.items() if d["pessoa1"] == uid or d["pessoa2"] == uid), None)
    if not mid:
        await interaction.response.send_message("❌ Não casado.", ephemeral=True)
        return
    if uid in bot.divorce_cooldowns and datetime.now(BR_TZ) - bot.divorce_cooldowns[uid] < timedelta(days=7):
        await interaction.response.send_message("❌ Cooldown 7d.", ephemeral=True)
        return
    if uid not in bot.user_balances or bot.user_balances[uid] < 5000:
        await interaction.response.send_message("❌ 5000 moedas.", ephemeral=True)
        return
    bot.user_balances[uid] -= 5000
    bot.divorce_cooldowns[uid] = datetime.now(BR_TZ)
    del bot.marriage_data[mid]
    bot.save_data()
    await interaction.response.send_message("💔 Divórcio realizado.")


@bot.tree.command(name="casamento", description="💒 Ver casamento")
async def casamento(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    d = next((x for x in bot.marriage_data.values() if x["pessoa1"] == uid or x["pessoa2"] == uid), None)
    if not d:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    cid = d["pessoa2"] if d["pessoa1"] == uid else d["pessoa1"]
    conj = interaction.guild.get_member(int(cid))
    if not conj:
        await interaction.response.send_message("❌ Cônjuge sumiu.", ephemeral=True)
        return
    dt = datetime.fromisoformat(d["data_casamento"]).replace(tzinfo=BR_TZ)
    delta = datetime.now(BR_TZ) - dt
    embed = discord.Embed(title="💒 Casamento", description=f"{interaction.user.mention} ❤️ {conj.mention}", color=discord.Color.from_str("#FF69B4"))
    embed.add_field(name="Há", value=f"{delta.days} dias", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="presentear", description="🎁 Presente ao cônjuge (100 moedas)")
async def presentear(interaction: discord.Interaction, presente: str):
    uid = str(interaction.user.id)
    d = next((x for x in bot.marriage_data.values() if x["pessoa1"] == uid or x["pessoa2"] == uid), None)
    if not d:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    if uid not in bot.user_balances or bot.user_balances[uid] < 100:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    bot.user_balances[uid] -= 100
    d.setdefault("presentes", []).append(f"{interaction.user.name}: {presente}")
    bot.save_data()
    cid = d["pessoa2"] if d["pessoa1"] == uid else d["pessoa1"]
    await interaction.response.send_message(f"🎁 Para <@{cid}>")


@bot.tree.command(name="aniversario", description="🎂 Aniversário de casamento")
async def aniversario(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    d = next((x for x in bot.marriage_data.values() if x["pessoa1"] == uid or x["pessoa2"] == uid), None)
    if not d:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    dt = datetime.fromisoformat(d["data_casamento"]).replace(tzinfo=BR_TZ)
    hoje = datetime.now(BR_TZ)
    if hoje.month != dt.month or hoje.day != dt.day:
        await interaction.response.send_message("❌ Hoje não é o dia.", ephemeral=True)
        return
    anos = hoje.year - dt.year
    if anos <= d["aniversarios_comemorados"]:
        await interaction.response.send_message("❌ Já comemorado.", ephemeral=True)
        return
    d["aniversarios_comemorados"] = anos
    cid = d["pessoa2"] if d["pessoa1"] == uid else d["pessoa1"]
    for x in (uid, cid):
        bot.user_balances.setdefault(x, 0)
        bot.user_balances[x] += 500 * anos
    bot.save_data()
    await interaction.response.send_message(embed=discord.Embed(title="🎂", description=f"{anos} anos! +{500*anos} moedas cada.", color=discord.Color.gold()))


@bot.tree.command(name="luademel", description="🌙 Lua de mel")
async def luademel(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    d = next((x for x in bot.marriage_data.values() if x["pessoa1"] == uid or x["pessoa2"] == uid), None)
    if not d:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    dt = datetime.fromisoformat(d["data_casamento"]).replace(tzinfo=BR_TZ)
    if datetime.now(BR_TZ) - dt > timedelta(days=7):
        d["luademel"] = False
        bot.save_data()
        await interaction.response.send_message("❌ Acabou.", ephemeral=True)
        return
    cid = d["pessoa2"] if d["pessoa1"] == uid else d["pessoa1"]
    dias = 7 - (datetime.now(BR_TZ) - dt).days
    await interaction.response.send_message(embed=discord.Embed(title="🌙", description=f"{interaction.user.mention} ❤️ <@{cid}>\n**{dias}** dias restantes.", color=discord.Color.from_str("#FF69B4")))


SIGNOS = ["Áries", "Touro", "Gêmeos", "Câncer", "Leão", "Virgem", "Libra", "Escorpião", "Sagitário", "Capricórnio", "Aquário", "Peixes"]


@bot.tree.command(name="signos", description="♈ Signos")
async def signos(interaction: discord.Interaction, signo1: str, signo2: str):
    if signo1 not in SIGNOS or signo2 not in SIGNOS:
        await interaction.response.send_message(f"❌ Use: {', '.join(SIGNOS[:4])}…", ephemeral=True)
        return
    c = random.randint(40, 100)
    await interaction.response.send_message(embed=discord.Embed(title="♈", description=f"{signo1} x {signo2}\n**{c}%**", color=discord.Color.blue()))


PRESENTES_LOJA = {"🌹 Rosa": 50, "🍫 Chocolate": 75, "🧸 Ursinho": 100, "💍 Anel": 500, "💐 Buquê": 150}


@bot.tree.command(name="loja_presentes", description="🎁 Loja")
async def loja_presentes(interaction: discord.Interaction):
    embed = discord.Embed(title="🎁 Loja", color=discord.Color.gold())
    for k, v in PRESENTES_LOJA.items():
        embed.add_field(name=k, value=f"{v} moedas", inline=True)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="comprar_presente", description="🎁 Comprar presente")
async def comprar_presente(interaction: discord.Interaction, presente: str, usuario: discord.Member):
    if presente not in PRESENTES_LOJA:
        await interaction.response.send_message("❌ Veja /loja_presentes", ephemeral=True)
        return
    preco = PRESENTES_LOJA[presente]
    uid = str(interaction.user.id)
    if uid not in bot.user_balances or bot.user_balances[uid] < preco:
        await interaction.response.send_message("❌ Saldo.", ephemeral=True)
        return
    bot.user_balances[uid] -= preco
    tid = str(usuario.id)
    bot.user_inventory.setdefault(tid, []).append({"presente": presente, "de": interaction.user.name, "data": datetime.now(BR_TZ).isoformat()})
    bot.save_data()
    await interaction.response.send_message(f"🎁 {presente} → {usuario.mention}")


@bot.tree.command(name="meuspresentes", description="📦 Presentes recebidos")
async def meuspresentes(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    if uid not in bot.user_inventory or not bot.user_inventory[uid]:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    embed = discord.Embed(title="📦 Presentes", color=discord.Color.gold())
    for p in bot.user_inventory[uid][-10:]:
        embed.add_field(name=p["presente"], value=f"De {p['de']}", inline=False)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="daily", description="💰 Daily com streak")
async def daily(interaction: discord.Interaction):
    user_id = str(interaction.user.id)
    agora = datetime.now(BR_TZ)
    hoje, ontem = agora.date(), agora.date() - timedelta(days=1)
    bot.user_balances.setdefault(user_id, 0)
    ultimo_raw = bot.daily_cooldowns.get(user_id)
    if ultimo_raw:
        try:
            ultimo = datetime.fromisoformat(ultimo_raw)
            if ultimo.tzinfo is None:
                ultimo = ultimo.replace(tzinfo=BR_TZ)
            if ultimo.date() == hoje:
                prox = datetime(agora.year, agora.month, agora.day, 0, 0, 0, tzinfo=BR_TZ) + timedelta(days=1)
                r = prox - agora
                await interaction.response.send_message(
                    embed=discord.Embed(
                        title="⏰ Daily já pego",
                        description=f"Próximo em **{int(r.total_seconds()//3600)}h {int((r.total_seconds()%3600)//60)}m**\nSaldo: **{bot.user_balances[user_id]}**",
                        color=discord.Color.orange(),
                    ),
                    ephemeral=True,
                )
                return
        except (ValueError, TypeError):
            pass
    streak_key = f"{user_id}_streak"
    streak = 1
    if user_id in bot.daily_cooldowns:
        try:
            u = datetime.fromisoformat(bot.daily_cooldowns[user_id])
            if u.tzinfo is None:
                u = u.replace(tzinfo=BR_TZ)
            if u.date() == ontem:
                try:
                    streak = int(bot.daily_cooldowns.get(streak_key, "0")) + 1
                except ValueError:
                    streak = 1
        except Exception:
            streak = 1
    base = random.randint(300, 600)
    bonus_streak = min(streak * 30, 500)
    extra = msg_b = 0
    roll = random.random()
    if roll < 0.03:
        extra, msg_b = 1000, "JACKPOT +1000"
    elif roll < 0.15:
        extra, msg_b = 300, "Sorte +300"
    elif roll < 0.35:
        extra, msg_b = 100, "Bônus +100"
    total = base + bonus_streak + extra
    bot.user_balances[user_id] += total
    bot.daily_cooldowns[user_id] = agora.isoformat()
    bot.daily_cooldowns[streak_key] = str(streak)
    bot.save_data()
    embed = discord.Embed(title="💰 DAILY", description=f"**+{total}** moedas\nStreak: **{streak}** dias (+{bonus_streak})", color=discord.Color.gold())
    if msg_b:
        embed.add_field(name="Extra", value=msg_b, inline=False)
    embed.add_field(name="Saldo", value=str(bot.user_balances[user_id]), inline=True)
    embed.timestamp = agora
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="saldo", description="💰 Saldo")
async def saldo(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    membro = membro or interaction.user
    uid = str(membro.id)
    sk = f"{uid}_streak"
    st = int(bot.daily_cooldowns[sk]) if sk in bot.daily_cooldowns else 0
    embed = discord.Embed(title=f"💰 {membro.display_name}", color=discord.Color.gold())
    embed.add_field(name="Moedas", value=str(bot.user_balances.get(uid, 0)), inline=True)
    if st:
        embed.add_field(name="Streak", value=str(st), inline=True)
    embed.set_thumbnail(url=membro.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="transferir", description="💸 Transferir")
async def transferir(interaction: discord.Interaction, membro: discord.Member, valor: int):
    if valor <= 0 or membro == interaction.user:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    uid, tid = str(interaction.user.id), str(membro.id)
    if uid not in bot.user_balances or bot.user_balances[uid] < valor:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    bot.user_balances[uid] -= valor
    bot.user_balances.setdefault(tid, 0)
    bot.user_balances[tid] += valor
    bot.save_data()
    await interaction.response.send_message(f"💸 {valor} → {membro.mention}")


@bot.tree.command(name="slot", description="🎰 Slot 50 moedas")
async def slot(interaction: discord.Interaction):
    uid = str(interaction.user.id)
    if uid not in bot.user_balances or bot.user_balances[uid] < 50:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    bot.user_balances[uid] -= 50
    sims = ["🍒", "🍋", "🍊", "🍇", "💎", "7️⃣"]
    r = [random.choice(sims) for _ in range(3)]
    premio = 0
    if r[0] == r[1] == r[2]:
        premio = 1000 if r[0] == "7️⃣" else 500 if r[0] == "💎" else 200
    elif r[0] == r[1] or r[1] == r[2] or r[0] == r[2]:
        premio = 75
    if premio:
        bot.user_balances[uid] += premio
    bot.save_data()
    await interaction.response.send_message(f"🎰 `{r[0]}|{r[1]}|{r[2]}` → **{premio}** moedas | saldo {bot.user_balances[uid]}")


@bot.tree.command(name="dado", description="🎲 Dado")
async def dado(interaction: discord.Interaction, lados: int = 6):
    if lados < 2:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    await interaction.response.send_message(f"🎲 **{random.randint(1, lados)}** (d{lados})")


@bot.tree.command(name="cara_coroa", description="🪙 Cara ou coroa")
async def cara_coroa(interaction: discord.Interaction, escolha: str, aposta: int):
    uid = str(interaction.user.id)
    if escolha.lower() not in ("cara", "coroa") or aposta <= 0:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    if uid not in bot.user_balances or bot.user_balances[uid] < aposta:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    bot.user_balances[uid] -= aposta
    res = random.choice(["cara", "coroa"])
    if res == escolha.lower():
        bot.user_balances[uid] += aposta * 2
        msg = f"Ganhou **{aposta*2}**"
    else:
        msg = "Perdeu"
    bot.save_data()
    await interaction.response.send_message(f"🪙 **{res}** — {msg} | saldo {bot.user_balances[uid]}")


@bot.tree.command(name="ppt", description="✂️ PPT")
async def ppt(interaction: discord.Interaction, escolha: str):
    opts = ["pedra", "papel", "tesoura"]
    if escolha.lower() not in opts:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    bc = random.choice(opts)
    e = escolha.lower()
    if e == bc:
        res, cor = "Empate", discord.Color.blue()
    elif (e == "pedra" and bc == "tesoura") or (e == "papel" and bc == "pedra") or (e == "tesoura" and bc == "papel"):
        res, cor = "Ganhou", discord.Color.green()
    else:
        res, cor = "Perdeu", discord.Color.red()
    em = {"pedra": "🪨", "papel": "📄", "tesoura": "✂️"}
    await interaction.response.send_message(embed=discord.Embed(title="PPT", description=f"Você {em[e]} vs {em[bc]}\n**{res}**", color=cor))


@bot.tree.command(name="adivinha", description="🔢 1-10 (30 moedas)")
async def adivinha(interaction: discord.Interaction, numero: int):
    uid = str(interaction.user.id)
    if uid not in bot.user_balances or bot.user_balances[uid] < 30 or not 1 <= numero <= 10:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    bot.user_balances[uid] -= 30
    sec = random.randint(1, 10)
    if numero == sec:
        bot.user_balances[uid] += 150
        msg = f"ACERTOU **{sec}**! +150"
    else:
        msg = f"Era **{sec}**"
    bot.save_data()
    await interaction.response.send_message(f"🔢 {msg} | saldo {bot.user_balances[uid]}")


@bot.tree.command(name="ping", description="🏓 Ping")
async def ping_cmd(interaction: discord.Interaction):
    await interaction.response.send_message(f"🏓 {round(bot.latency * 1000)}ms")


@bot.tree.command(name="userinfo", description="👤 User info")
async def userinfo(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    m = membro or interaction.user
    embed = discord.Embed(title=m.name, color=m.color or discord.Color.blue())
    embed.set_thumbnail(url=m.display_avatar.url)
    embed.add_field(name="ID", value=str(m.id))
    embed.add_field(name="Conta", value=m.created_at.strftime("%d/%m/%Y"))
    embed.add_field(name="Entrou", value=m.joined_at.strftime("%d/%m/%Y") if m.joined_at else "—")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="serverinfo", description="📊 Servidor")
async def serverinfo(interaction: discord.Interaction):
    g = interaction.guild
    embed = discord.Embed(title=g.name, color=discord.Color.blue())
    if g.icon:
        embed.set_thumbnail(url=g.icon.url)
    embed.add_field(name="Membros", value=str(g.member_count))
    embed.add_field(name="Dono", value=g.owner.mention if g.owner else "?")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="avatar", description="🖼️ Avatar")
async def avatar(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    m = membro or interaction.user
    embed = discord.Embed(title=m.display_name)
    embed.set_image(url=m.display_avatar.url)
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="calcular", description="🧮 Calc")
async def calcular(interaction: discord.Interaction, num1: float, operador: str, num2: float):
    try:
        if operador == "+":
            r = num1 + num2
        elif operador == "-":
            r = num1 - num2
        elif operador in ("*", "x"):
            r = num1 * num2
        elif operador == "/":
            if num2 == 0:
                await interaction.response.send_message("❌ /0", ephemeral=True)
                return
            r = num1 / num2
        elif operador == "^":
            r = num1**num2
        else:
            await interaction.response.send_message("❌", ephemeral=True)
            return
        await interaction.response.send_message(f"🧮 `{r}`")
    except Exception as e:
        await interaction.response.send_message(f"❌ {e}", ephemeral=True)


@bot.tree.command(name="ola_mundo", description="👋 Olá")
async def ola_mundo(interaction: discord.Interaction):
    await interaction.response.send_message(f"Olá {interaction.user.mention}!")


@bot.tree.command(name="8ball", description="🎱")
async def eight_ball(interaction: discord.Interaction, pergunta: str):
    r = random.choice(["Sim!", "Não!", "Talvez…", "Com certeza!", "Melhor não…", "Pergunte depois…"])
    await interaction.response.send_message(embed=discord.Embed(title="🎱", description=f"*{pergunta}*\n**{r}**", color=discord.Color.purple()))


@bot.tree.command(name="piada", description="😂")
async def piada(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(["Por que o dev foi preso? Porque deu **commit** no crime.", "Zero olhou pro oito: belo cinto!"]))


@bot.tree.command(name="conselho", description="💡")
async def conselho(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(["Beba água 💧", "Durma bem 😴", "Seja gentil 🫶"]))


@bot.tree.command(name="fato", description="🔍")
async def fato(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(["Mel não estraga.", "Polvos têm 3 corações.", "🐣 Tradições de Páscoa misturam raízes antigas."]))


@bot.tree.command(name="baitola", description="🏳️‍🌈 (brincadeira entre amigos)")
async def baitola(interaction: discord.Interaction, membro: discord.Member):
    await interaction.response.send_message(random.choice([f"{membro.mention} rainha 👑", f"{membro.mention} lendário 🏆"]))


@bot.tree.command(name="abraco_gif", description="🤗")
async def abraco_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    embed = discord.Embed(description=f"{interaction.user.mention} 🤗 {membro.mention}", color=discord.Color.from_str("#FF69B4"))
    embed.set_image(url=random.choice(gifs_abraco))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="beijo_gif", description="💋")
async def beijo_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    embed = discord.Embed(description=f"{interaction.user.mention} 💋 {membro.mention}", color=discord.Color.red())
    embed.set_image(url=random.choice(gifs_beijo))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="carinho_gif", description="🥰")
async def carinho_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    embed = discord.Embed(description=f"{interaction.user.mention} 🥰 {membro.mention}", color=discord.Color.purple())
    embed.set_image(url=random.choice(gifs_carinho))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="cafune_gif", description="😴")
async def cafune_gif(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    embed = discord.Embed(description=f"{interaction.user.mention} faz cafuné em {membro.mention}", color=discord.Color.teal())
    embed.set_image(url=random.choice(gifs_carinho))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="tapa", description="👋")
async def tapa(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    embed = discord.Embed(description=f"{interaction.user.mention} 👋 {membro.mention}", color=discord.Color.orange())
    embed.set_image(url=random.choice(gifs_tapa))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="festa", description="🎉")
async def festa(interaction: discord.Interaction, membro: Optional[discord.Member] = None):
    embed = discord.Embed(
        description=f"{interaction.user.mention} festa com {membro.mention}!" if membro else f"{interaction.user.mention} festa!",
        color=discord.Color.gold(),
    )
    embed.set_image(url=random.choice(gifs_festa))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="matar", description="💀 (brincadeira)")
async def matar(interaction: discord.Interaction, membro: discord.Member):
    if membro == interaction.user:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    embed = discord.Embed(description=f"{interaction.user.mention} 💀 {membro.mention} (brincadeira)", color=discord.Color.dark_red())
    embed.set_image(url=random.choice(gifs_matar))
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="chifre", description="🦌")
async def chifre(interaction: discord.Interaction, membro: discord.Member):
    embed = discord.Embed(description=f"{interaction.user.mention} 🦌 {membro.mention}", color=discord.Color.green())
    embed.set_image(url="https://media.giphy.com/media/3o7TKsQ8CAGJ6A9p20/giphy.gif")
    await interaction.response.send_message(embed=embed)


@bot.tree.command(name="moeda", description="🪙")
async def moeda(interaction: discord.Interaction):
    await interaction.response.send_message(random.choice(["CARA", "COROA"]))


@bot.tree.command(name="rps", description="🗿 RPS")
async def rps(interaction: discord.Interaction, escolha: str):
    opts = ["pedra", "papel", "tesoura"]
    if escolha.lower() not in opts:
        await interaction.response.send_message("❌", ephemeral=True)
        return
    bc = random.choice(opts)
    e = escolha.lower()
    if e == bc:
        res, cor = "Empate", discord.Color.blue()
    elif (e == "pedra" and bc == "tesoura") or (e == "papel" and bc == "pedra") or (e == "tesoura" and bc == "papel"):
        res, cor = "Ganhou", discord.Color.green()
    else:
        res, cor = "Perdeu", discord.Color.red()
    em = {"pedra": "🗿", "papel": "📄", "tesoura": "✂️"}
    await interaction.response.send_message(embed=discord.Embed(title="RPS", description=f"{em[e]} vs {em[bc]}\n{res}", color=cor))


@bot.tree.command(name="dado_rpg", description="🎲 Dados")
async def dado_rpg(interaction: discord.Interaction, quantidade: int = 1, faces: int = 20):
    if not 1 <= quantidade <= 10 or faces not in (4, 6, 8, 10, 12, 20, 100):
        await interaction.response.send_message("❌", ephemeral=True)
        return
    rolls = [random.randint(1, faces) for _ in range(quantidade)]
    await interaction.response.send_message(f"🎲 {quantidade}d{faces}: {rolls} = **{sum(rolls)}**")


@bot.tree.command(name="sortear", description="🎁 Sortear membro")
async def sortear(interaction: discord.Interaction, cargo: Optional[discord.Role] = None):
    if cargo:
        mems = [m for m in cargo.members if not m.bot]
        if not mems:
            await interaction.response.send_message("❌", ephemeral=True)
            return
        m = random.choice(mems)
    else:
        mems = [m for m in interaction.guild.members if not m.bot]
        if not mems:
            await interaction.response.send_message("❌", ephemeral=True)
            return
        m = random.choice(mems)
    await interaction.response.send_message(f"🎁 {m.mention}")


@bot.tree.command(name="ajuda", description="📚 Ajuda")
async def ajuda(interaction: discord.Interaction):
    embed = discord.Embed(title="📚 Fort Bot", description="Comandos principais (slash).", color=discord.Color.blue())
    embed.add_field(name="🐣 Páscoa", value="daily pascoa, quiz, memória, anagrama, caça, ovo, corrida, slot, chocolate, ranking, pontos", inline=False)
    embed.add_field(name="📢 Chamadas / 📊 Enquetes", value="/chamada* /enquete*", inline=False)
    embed.add_field(name="🎭 RP", value="/rp_* /rp_carinho /rp_narrar /rp_ficha", inline=False)
    embed.add_field(name="💖💒💰", value="/ship* /pedir /casamento /daily /saldo /slot …", inline=False)
    embed.set_thumbnail(url=interaction.client.user.display_avatar.url)
    embed.timestamp = datetime.now(BR_TZ)
    await interaction.response.send_message(embed=embed)


async def main():
    token = os.environ.get("DISCORD_TOKEN")
    if not token:
        print("❌ DISCORD_TOKEN não definido.")
        return
    try:
        async with bot:
            await bot.start(token)
    except Exception as e:
        print(f"❌ {e}")


def run_bot():
    print("🟢 Fort Bot")
    try:
        keep_alive()
        time.sleep(2)
        asyncio.run(main())
    except KeyboardInterrupt:
        print("👋")
    except Exception as e:
        print(f"❌ {e}")


if __name__ == "__main__":
    print("=" * 50)
    print("🚀 FORT BOT — main.py corrigido")
    print("=" * 50)
    run_bot()
