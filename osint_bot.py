#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
YASIN_VIPXIT OSINT TELEGRAM BOT v7.0
Advanced OSINT Intelligence Platform
Author: @YASIN_VIPXIT
Version: 7.0.0
"""

import os
import sys
import time
import json
import sqlite3
import asyncio
import aiohttp
import requests
import re
import hashlib
import base64
import random
import string
import threading
import subprocess
import platform
import socket
import getpass
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import logging
from urllib.parse import quote_plus
import html

# Telegram Bot Libraries
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, CallbackQueryHandler, filters, ContextTypes
from telegram.constants import ParseMode

# OSINT Libraries
import phonenumbers
from phonenumbers import carrier, geocoder, timezone as phone_timezone
import dns.resolver
import whois
import requests
from bs4 import BeautifulSoup
import shodan
import ipaddress
import socket
import ssl
import OpenSSL
from urllib.parse import urlparse
import hashlib

# ============================================================================
# CONFIGURATION
# ============================================================================

VERSION = "7.0.0"
AUTHOR = "@YASIN_VIPXIT"
BOT_TOKEN = "8126390181:AAF8gttXWQiUR7AHebFo_RoPeUdTMp5VG8g"  # Replace with your bot token

# Database
DB_PATH = "osint_bot.db"

# ============================================================================
# DATABASE MANAGER
# ============================================================================

class DatabaseManager:
    """SQLite database for tracking and storing OSINT data"""
    
    def __init__(self):
        self.conn = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.init_db()
        
    def init_db(self):
        cursor = self.conn.cursor()
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY,
                username TEXT,
                first_name TEXT,
                last_name TEXT,
                registered_at TEXT
            )
        ''')
        
        # Searches table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS searches (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                query_type TEXT,
                query TEXT,
                result TEXT,
                timestamp TEXT
            )
        ''')
        
        # Tracked accounts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tracked_accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                platform TEXT,
                account_id TEXT,
                username TEXT,
                last_check TEXT,
                changes TEXT
            )
        ''')
        
        self.conn.commit()
        
    def add_user(self, user_id: int, username: str, first_name: str, last_name: str = ""):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT OR IGNORE INTO users (id, username, first_name, last_name, registered_at) VALUES (?, ?, ?, ?, ?)",
            (user_id, username, first_name, last_name, datetime.now().isoformat())
        )
        self.conn.commit()
        
    def save_search(self, user_id: int, query_type: str, query: str, result: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO searches (user_id, query_type, query, result, timestamp) VALUES (?, ?, ?, ?, ?)",
            (user_id, query_type, query, result[:10000], datetime.now().isoformat())
        )
        self.conn.commit()
        
    def add_tracked(self, user_id: int, platform: str, account_id: str, username: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "INSERT INTO tracked_accounts (user_id, platform, account_id, username, last_check, changes) VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, platform, account_id, username, datetime.now().isoformat(), "[]")
        )
        self.conn.commit()
        
    def get_tracked(self, user_id: int) -> List:
        cursor = self.conn.cursor()
        cursor.execute(
            "SELECT platform, account_id, username FROM tracked_accounts WHERE user_id = ?",
            (user_id,)
        )
        return cursor.fetchall()
        
    def update_tracked(self, account_id: str, changes: str):
        cursor = self.conn.cursor()
        cursor.execute(
            "UPDATE tracked_accounts SET last_check = ?, changes = ? WHERE account_id = ?",
            (datetime.now().isoformat(), changes, account_id)
        )
        self.conn.commit()

# ============================================================================
# OSINT ENGINES
# ============================================================================

class InstagramOSINT:
    """Instagram OSINT Engine"""
    
    @staticmethod
    async def get_user_info(username: str) -> Dict:
        """Get Instagram user information"""
        try:
            url = f"https://www.instagram.com/{username}/?__a=1&__d=dis"
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
                'Accept': 'application/json'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        user = data.get('graphql', {}).get('user', {})
                        
                        return {
                            'found': True,
                            'username': user.get('username'),
                            'full_name': user.get('full_name'),
                            'followers': user.get('edge_followed_by', {}).get('count', 0),
                            'following': user.get('edge_follow', {}).get('count', 0),
                            'posts': user.get('edge_owner_to_timeline_media', {}).get('count', 0),
                            'is_verified': user.get('is_verified', False),
                            'is_private': user.get('is_private', False),
                            'bio': user.get('biography', ''),
                            'profile_pic': user.get('profile_pic_url_hd', '')
                        }
                    else:
                        return {'found': False, 'error': 'User not found or private'}
                        
        except Exception as e:
            return {'found': False, 'error': str(e)}
    
    @staticmethod
    async def get_post_info(shortcode: str) -> Dict:
        """Get Instagram post information"""
        try:
            url = f"https://www.instagram.com/p/{shortcode}/?__a=1"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        post = data.get('graphql', {}).get('shortcode_media', {})
                        
                        return {
                            'found': True,
                            'shortcode': shortcode,
                            'likes': post.get('edge_media_preview_like', {}).get('count', 0),
                            'comments': post.get('edge_media_to_comment', {}).get('count', 0),
                            'caption': post.get('edge_media_to_caption', {}).get('edges', [{}])[0].get('node', {}).get('text', ''),
                            'timestamp': post.get('taken_at_timestamp'),
                            'is_video': post.get('is_video', False),
                            'owner': post.get('owner', {}).get('username')
                        }
                    else:
                        return {'found': False, 'error': 'Post not found'}
        except Exception as e:
            return {'found': False, 'error': str(e)}

class TwitterOSINT:
    """Twitter/X OSINT Engine"""
    
    @staticmethod
    async def get_user_info(username: str) -> Dict:
        """Get Twitter user information"""
        try:
            # Using Twitter API v2
            url = f"https://api.twitter.com/2/users/by/username/{username}"
            headers = {
                'Authorization': 'Bearer YOUR_BEARER_TOKEN',  # Needs API key
                'User-Agent': 'Mozilla/5.0'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        user = data.get('data', {})
                        
                        return {
                            'found': True,
                            'username': user.get('username'),
                            'name': user.get('name'),
                            'id': user.get('id'),
                            'description': user.get('description', ''),
                            'followers_count': user.get('public_metrics', {}).get('followers_count', 0),
                            'following_count': user.get('public_metrics', {}).get('following_count', 0),
                            'tweet_count': user.get('public_metrics', {}).get('tweet_count', 0),
                            'verified': user.get('verified', False)
                        }
                    else:
                        return {'found': False, 'error': 'User not found'}
        except Exception as e:
            return {'found': False, 'error': str(e)}

class TelegramOSINT:
    """Telegram OSINT Engine"""
    
    @staticmethod
    async def get_user_info(username: str) -> Dict:
        """Get Telegram user information (public data)"""
        try:
            url = f"https://t.me/{username.lstrip('@')}"
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as response:
                    if response.status == 200:
                        html_content = await response.text()
                        soup = BeautifulSoup(html_content, 'html.parser')
                        
                        # Extract user info
                        title_elem = soup.find('div', class_='tgme_page_title')
                        username_elem = soup.find('div', class_='tgme_page_extra')
                        bio_elem = soup.find('div', class_='tgme_page_description')
                        
                        return {
                            'found': True,
                            'username': username,
                            'full_name': title_elem.text.strip() if title_elem else 'N/A',
                            'username_display': username_elem.text.strip() if username_elem else f'@{username}',
                            'bio': bio_elem.text.strip() if bio_elem else 'No bio',
                            'url': url
                        }
                    else:
                        return {'found': False, 'error': 'User not found'}
        except Exception as e:
            return {'found': False, 'error': str(e)}

class PhoneOSINT:
    """Phone Number OSINT Engine"""
    
    @staticmethod
    async def get_info(phone_number: str) -> Dict:
        """Get phone number information"""
        try:
            parsed = phonenumbers.parse(phone_number, None)
            
            if phonenumbers.is_valid_number(parsed):
                return {
                    'found': True,
                    'number': phone_number,
                    'country': phonenumbers.region_code_for_number(parsed),
                    'country_name': geocoder.description_for_number(parsed, "en"),
                    'carrier': carrier.name_for_number(parsed, "en"),
                    'timezones': list(phone_timezone.time_zones_for_number(parsed)),
                    'is_possible': phonenumbers.is_possible_number(parsed),
                    'is_valid': True
                }
            else:
                return {'found': False, 'error': 'Invalid phone number'}
        except Exception as e:
            return {'found': False, 'error': str(e)}

class DomainOSINT:
    """Domain/IP OSINT Engine"""
    
    @staticmethod
    async def get_domain_info(domain: str) -> Dict:
        """Get domain information"""
        try:
            # WHOIS lookup
            w = whois.whois(domain)
            
            # DNS lookup
            dns_info = {}
            for record in ['A', 'MX', 'NS', 'TXT']:
                try:
                    answers = dns.resolver.resolve(domain, record)
                    dns_info[record] = [str(answer) for answer in answers]
                except:
                    dns_info[record] = []
            
            return {
                'found': True,
                'domain': domain,
                'registrar': w.registrar,
                'creation_date': str(w.creation_date) if w.creation_date else 'N/A',
                'expiration_date': str(w.expiration_date) if w.expiration_date else 'N/A',
                'name_servers': w.name_servers,
                'dns_records': dns_info
            }
        except Exception as e:
            return {'found': False, 'error': str(e)}
    
    @staticmethod
    async def get_ip_info(ip: str) -> Dict:
        """Get IP address information"""
        try:
            # Validate IP
            ipaddress.ip_address(ip)
            
            # IP Geolocation
            response = requests.get(f'http://ip-api.com/json/{ip}', timeout=10)
            data = response.json()
            
            return {
                'found': True,
                'ip': ip,
                'country': data.get('country', 'N/A'),
                'city': data.get('city', 'N/A'),
                'region': data.get('regionName', 'N/A'),
                'isp': data.get('isp', 'N/A'),
                'org': data.get('org', 'N/A'),
                'lat': data.get('lat', 0),
                'lon': data.get('lon', 0),
                'timezone': data.get('timezone', 'N/A')
            }
        except Exception as e:
            return {'found': False, 'error': str(e)}

class EmailOSINT:
    """Email OSINT Engine"""
    
    @staticmethod
    async def check_breaches(email: str) -> Dict:
        """Check if email appears in data breaches"""
        try:
            # Using Have I Been Pwned API
            sha1_hash = hashlib.sha1(email.lower().encode()).hexdigest().upper()
            response = requests.get(f'https://api.pwnedpasswords.com/range/{sha1_hash[:5]}', timeout=10)
            
            if response.status_code == 200:
                breaches = []
                for line in response.text.splitlines():
                    suffix, count = line.split(':')
                    if sha1_hash[5:] == suffix:
                        breaches.append({'breach': 'Password breach', 'count': int(count)})
                
                return {
                    'found': True,
                    'email': email,
                    'breaches': breaches,
                    'is_compromised': len(breaches) > 0
                }
            else:
                return {'found': True, 'email': email, 'breaches': [], 'is_compromised': False}
        except Exception as e:
            return {'found': False, 'error': str(e)}

# ============================================================================
# TRANSLATION ENGINE
# ============================================================================

class TranslationEngine:
    """Multi-language translation engine"""
    
    LANGUAGES = {
        'en': 'English',
        'ar': 'العربية',
        'fr': 'Français',
        'es': 'Español',
        'de': 'Deutsch',
        'ru': 'Русский',
        'zh': '中文',
        'ja': '日本語',
        'pt': 'Português',
        'tr': 'Türkçe'
    }
    
    @staticmethod
    async def translate(text: str, target_lang: str = 'en') -> str:
        """Translate text using LibreTranslate API"""
        try:
            url = "https://libretranslate.com/translate"
            payload = {
                'q': text,
                'source': 'auto',
                'target': target_lang,
                'format': 'text'
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, timeout=10) as response:
                    if response.status == 200:
                        data = await response.json()
                        return data.get('translatedText', text)
                    else:
                        return text
        except:
            return text

# ============================================================================
# TRACKING ENGINE
# ============================================================================

class TrackingEngine:
    """Account tracking engine"""
    
    def __init__(self, db: DatabaseManager):
        self.db = db
        self.running = True
        self.trackers = {
            'instagram': InstagramOSINT.get_user_info,
            'telegram': TelegramOSINT.get_user_info,
            'twitter': TwitterOSINT.get_user_info
        }
        
    async def check_account(self, platform: str, account_id: str):
        """Check a single account for changes"""
        tracker = self.trackers.get(platform)
        if not tracker:
            return None
            
        try:
            result = await tracker(account_id)
            return result
        except:
            return None
            
    async def run_tracker(self):
        """Main tracking loop"""
        while self.running:
            try:
                # Get all tracked accounts
                cursor = self.db.conn.cursor()
                cursor.execute("SELECT user_id, platform, account_id, username, last_check FROM tracked_accounts")
                accounts = cursor.fetchall()
                
                for user_id, platform, account_id, username, last_check in accounts:
                    # Check account
                    result = await self.check_account(platform, account_id)
                    
                    if result and result.get('found'):
                        # Check for changes (simplified)
                        current_data = json.dumps(result)
                        cursor.execute("SELECT changes FROM tracked_accounts WHERE account_id = ?", (account_id,))
                        old_data = cursor.fetchone()
                        
                        if old_data and old_data[0]:
                            if current_data != old_data[0]:
                                # Notify user
                                await self.notify_change(user_id, platform, username, result)
                                
                        # Update database
                        cursor.execute(
                            "UPDATE tracked_accounts SET last_check = ?, changes = ? WHERE account_id = ?",
                            (datetime.now().isoformat(), current_data, account_id)
                        )
                        self.db.conn.commit()
                        
                await asyncio.sleep(3600)  # Check every hour
                
            except Exception as e:
                print(f"Tracker error: {e}")
                await asyncio.sleep(60)
                
    async def notify_change(self, user_id: int, platform: str, username: str, new_data: Dict):
        """Notify user about account changes"""
        # This would send a message via Telegram bot
        pass

# ============================================================================
# REPORT GENERATORS
# ============================================================================

class ReportGenerator:
    """Generate reports in multiple formats"""
    
    @staticmethod
    def generate_html(data: Dict) -> str:
        """Generate HTML report"""
        html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OSINT Report - {data.get('query', 'Unknown')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            background: linear-gradient(135deg, #0a0a0a 0%, #1a1a2e 100%);
            font-family: 'Segoe UI', 'Consolas', monospace;
            color: #00ff00;
            padding: 20px;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; }}
        .header {{
            text-align: center;
            padding: 30px;
            background: rgba(0,0,0,0.5);
            border-radius: 15px;
            margin-bottom: 20px;
            border: 1px solid #00ff00;
        }}
        .section {{
            background: rgba(0,0,0,0.5);
            border-radius: 15px;
            padding: 20px;
            margin-bottom: 20px;
        }}
        .section-title {{
            font-size: 1.4em;
            margin-bottom: 15px;
            padding-bottom: 10px;
            border-bottom: 1px solid #00ff00;
        }}
        .info-row {{
            padding: 8px;
            border-bottom: 1px solid #333;
        }}
        .label {{ color: #33ccff; font-weight: bold; }}
        .footer {{
            text-align: center;
            padding: 20px;
            margin-top: 30px;
            border-top: 1px solid #333;
            color: #666;
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔍 OSINT Report</h1>
            <p>Query: {html.escape(str(data.get('query', 'Unknown')))}</p>
            <p>Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>Tool: YASIN_VIPXIT OSINT Bot v{VERSION}</p>
        </div>
"""
        
        for key, value in data.items():
            if key != 'query':
                html += f"""
        <div class="section">
            <div class="section-title">{key.upper()}</div>
            <div class="info-row"><span class="label">Value:</span> {html.escape(str(value)[:500])}</div>
        </div>
"""
        
        html += f"""
        <div class="footer">
            <p>Generated by @YASIN_VIPXIT OSINT Bot | Version {VERSION}</p>
        </div>
    </div>
</body>
</html>
"""
        return html
    
    @staticmethod
    def generate_txt(data: Dict) -> str:
        """Generate TXT report"""
        txt = f"""
{'='*60}
OSINT REPORT
{'='*60}
Query: {data.get('query', 'Unknown')}
Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
Tool: YASIN_VIPXIT OSINT Bot v{VERSION}
{'='*60}

"""
        for key, value in data.items():
            if key != 'query':
                txt += f"\n{key.upper()}:\n"
                txt += f"  {value}\n"
                
        txt += f"\n{'='*60}\n"
        return txt
    
    @staticmethod
    def generate_json(data: Dict) -> str:
        """Generate JSON report"""
        return json.dumps(data, indent=2, default=str)

# ============================================================================
# TELEGRAM BOT
# ============================================================================

class OSINTTelegramBot:
    """Main Telegram Bot"""
    
    def __init__(self, token: str):
        self.token = token
        self.application = Application.builder().token(token).build()
        self.db = DatabaseManager()
        self.translator = TranslationEngine()
        self.reporter = ReportGenerator()
        self.tracker = TrackingEngine(self.db)
        
        # Start tracker in background
        asyncio.create_task(self.tracker.run_tracker())
        
        # Setup handlers
        self.setup_handlers()
        
    def setup_handlers(self):
        """Setup bot command handlers"""
        
        # Command handlers
        self.application.add_handler(CommandHandler("start", self.cmd_start))
        self.application.add_handler(CommandHandler("help", self.cmd_help))
        self.application.add_handler(CommandHandler("instagram", self.cmd_instagram))
        self.application.add_handler(CommandHandler("twitter", self.cmd_twitter))
        self.application.add_handler(CommandHandler("telegram", self.cmd_telegram))
        self.application.add_handler(CommandHandler("phone", self.cmd_phone))
        self.application.add_handler(CommandHandler("domain", self.cmd_domain))
        self.application.add_handler(CommandHandler("ip", self.cmd_ip))
        self.application.add_handler(CommandHandler("email", self.cmd_email))
        self.application.add_handler(CommandHandler("translate", self.cmd_translate))
        self.application.add_handler(CommandHandler("track", self.cmd_track))
        self.application.add_handler(CommandHandler("tracked", self.cmd_tracked))
        self.application.add_handler(CommandHandler("untrack", self.cmd_untrack))
        self.application.add_handler(CommandHandler("export", self.cmd_export))
        self.application.add_handler(CommandHandler("stats", self.cmd_stats))
        
        # Message handler for non-commands
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /start command"""
        user = update.effective_user
        self.db.add_user(user.id, user.username, user.first_name, user.last_name or "")
        
        welcome_text = f"""
🔍 <b>YASIN_VIPXIT OSINT BOT v{VERSION}</b>

Welcome {user.first_name}! I'm an advanced OSINT intelligence bot.

<b>Available Commands:</b>
• /instagram &lt;username&gt; - Instagram profile info
• /twitter &lt;username&gt; - Twitter/X profile info  
• /telegram &lt;username&gt; - Telegram user info
• /phone &lt;number&gt; - Phone number intelligence
• /domain &lt;domain&gt; - Domain WHOIS lookup
• /ip &lt;address&gt; - IP geolocation
• /email &lt;address&gt; - Check email breaches
• /translate &lt;text&gt; - Translate text
• /track &lt;platform&gt; &lt;id&gt; - Track account
• /tracked - List tracked accounts
• /untrack &lt;id&gt; - Remove tracking
• /export &lt;format&gt; - Export last result
• /stats - Your usage statistics
• /help - Show this menu

<b>Export Formats:</b> txt, json, html

<i>Powered by @YASIN_VIPXIT | Advanced OSINT Intelligence</i>
"""
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.HTML)
        
    async def cmd_help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /help command"""
        await self.cmd_start(update, context)
        
    async def cmd_instagram(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /instagram command"""
        if not context.args:
            await update.message.reply_text("Usage: /instagram <username>")
            return
            
        username = context.args[0]
        await update.message.reply_text(f"🔍 Analyzing Instagram: @{username}...")
        
        result = await InstagramOSINT.get_user_info(username)
        self.db.save_search(update.effective_user.id, "instagram", username, json.dumps(result))
        
        if result.get('found'):
            text = f"""
📸 <b>Instagram Profile: @{result['username']}</b>
{'='*30}
👤 Full Name: {result.get('full_name', 'N/A')}
👥 Followers: {result.get('followers', 0):,}
📝 Following: {result.get('following', 0):,}
📷 Posts: {result.get('posts', 0):,}
✓ Verified: {'✅' if result.get('is_verified') else '❌'}
🔒 Private: {'✅' if result.get('is_private') else '❌'}

📝 Bio: {result.get('bio', 'No bio')[:200]}

🔗 Profile: https://instagram.com/{result['username']}
"""
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'User not found')}")
            
    async def cmd_twitter(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /twitter command"""
        if not context.args:
            await update.message.reply_text("Usage: /twitter <username>")
            return
            
        username = context.args[0]
        await update.message.reply_text(f"🔍 Analyzing Twitter/X: @{username}...")
        
        result = await TwitterOSINT.get_user_info(username)
        self.db.save_search(update.effective_user.id, "twitter", username, json.dumps(result))
        
        if result.get('found'):
            text = f"""
🐦 <b>Twitter/X Profile: @{result['username']}</b>
{'='*30}
👤 Name: {result.get('name', 'N/A')}
🆔 ID: {result.get('id', 'N/A')}
👥 Followers: {result.get('followers_count', 0):,}
📝 Following: {result.get('following_count', 0):,}
📊 Tweets: {result.get('tweet_count', 0):,}
✓ Verified: {'✅' if result.get('verified') else '❌'}

📝 Bio: {result.get('description', 'No bio')[:200]}

🔗 Profile: https://twitter.com/{result['username']}
"""
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'User not found')}")
            
    async def cmd_telegram(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /telegram command"""
        if not context.args:
            await update.message.reply_text("Usage: /telegram <username>")
            return
            
        username = context.args[0]
        await update.message.reply_text(f"🔍 Analyzing Telegram: @{username}...")
        
        result = await TelegramOSINT.get_user_info(username)
        self.db.save_search(update.effective_user.id, "telegram", username, json.dumps(result))
        
        if result.get('found'):
            text = f"""
✈️ <b>Telegram Profile: @{result['username']}</b>
{'='*30}
👤 Name: {result.get('full_name', 'N/A')}
📝 Username: {result.get('username_display', 'N/A')}

📝 Bio: {result.get('bio', 'No bio')[:200]}

🔗 Profile: https://t.me/{result['username']}
"""
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'User not found')}")
            
    async def cmd_phone(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /phone command"""
        if not context.args:
            await update.message.reply_text("Usage: /phone <number>")
            return
            
        number = ' '.join(context.args)
        await update.message.reply_text(f"🔍 Analyzing phone number: {number}...")
        
        result = await PhoneOSINT.get_info(number)
        self.db.save_search(update.effective_user.id, "phone", number, json.dumps(result))
        
        if result.get('found'):
            text = f"""
📞 <b>Phone Number Intelligence</b>
{'='*30}
📱 Number: {result['number']}
🌍 Country: {result.get('country_name', 'N/A')} ({result.get('country', 'N/A')})
📡 Carrier: {result.get('carrier', 'N/A')}
⏰ Timezone: {', '.join(result.get('timezones', []))}
✓ Valid: {'✅' if result.get('is_valid') else '❌'}

📍 Location: {result.get('country_name', 'N/A')}
"""
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Invalid phone number')}")
            
    async def cmd_domain(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /domain command"""
        if not context.args:
            await update.message.reply_text("Usage: /domain <domain>")
            return
            
        domain = context.args[0]
        await update.message.reply_text(f"🔍 Analyzing domain: {domain}...")
        
        result = await DomainOSINT.get_domain_info(domain)
        self.db.save_search(update.effective_user.id, "domain", domain, json.dumps(result))
        
        if result.get('found'):
            text = f"""
🌐 <b>Domain Information: {result['domain']}</b>
{'='*30}
📝 Registrar: {result.get('registrar', 'N/A')}
📅 Created: {result.get('creation_date', 'N/A')}
⏰ Expires: {result.get('expiration_date', 'N/A')}
🔄 Name Servers: {', '.join(result.get('name_servers', [])[:3])}

<b>DNS Records:</b>
"""
            for record, values in result.get('dns_records', {}).items():
                if values:
                    text += f"  {record}: {', '.join(values[:2])}\n"
                    
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Domain not found')}")
            
    async def cmd_ip(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /ip command"""
        if not context.args:
            await update.message.reply_text("Usage: /ip <address>")
            return
            
        ip = context.args[0]
        await update.message.reply_text(f"🔍 Analyzing IP: {ip}...")
        
        result = await DomainOSINT.get_ip_info(ip)
        self.db.save_search(update.effective_user.id, "ip", ip, json.dumps(result))
        
        if result.get('found'):
            text = f"""
🌍 <b>IP Address Intelligence</b>
{'='*30}
📡 IP: {result['ip']}
🌎 Country: {result.get('country', 'N/A')}
🏙️ City: {result.get('city', 'N/A')}
📍 Region: {result.get('region', 'N/A')}
📡 ISP: {result.get('isp', 'N/A')}
🏢 Organization: {result.get('org', 'N/A')}
⏰ Timezone: {result.get('timezone', 'N/A')}
🗺️ Coordinates: {result.get('lat', 0)}, {result.get('lon', 0)}
"""
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Invalid IP')}")
            
    async def cmd_email(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /email command"""
        if not context.args:
            await update.message.reply_text("Usage: /email <address>")
            return
            
        email = context.args[0]
        await update.message.reply_text(f"🔍 Checking email: {email}...")
        
        result = await EmailOSINT.check_breaches(email)
        self.db.save_search(update.effective_user.id, "email", email, json.dumps(result))
        
        if result.get('found'):
            text = f"""
📧 <b>Email Intelligence</b>
{'='*30}
📫 Email: {result['email']}
🔓 Compromised: {'⚠️ YES' if result.get('is_compromised') else '✅ NO'}

"""
            if result.get('breaches'):
                text += f"\n<b>Data Breaches Found:</b>\n"
                for breach in result['breaches']:
                    text += f"  • {breach.get('breach', 'Unknown')} ({breach.get('count', 0)} occurrences)\n"
            else:
                text += "\nNo breaches found in database.\n"
                
            await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        else:
            await update.message.reply_text(f"❌ {result.get('error', 'Invalid email')}")
            
    async def cmd_translate(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /translate command"""
        if not context.args:
            await update.message.reply_text("Usage: /translate <text>")
            return
            
        text = ' '.join(context.args)
        await update.message.reply_text(f"🌐 Translating: {text[:50]}...")
        
        translated = await self.translator.translate(text, 'en')
        
        await update.message.reply_text(f"""
🌐 <b>Translation Result</b>
{'='*30}
📝 Original: {text[:200]}
🔄 Translated: {translated[:200]}

<i>Auto-detected language → English</i>
""", parse_mode=ParseMode.HTML)
        
    async def cmd_track(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /track command"""
        if len(context.args) < 2:
            await update.message.reply_text("Usage: /track <platform> <username>\nPlatforms: instagram, twitter, telegram")
            return
            
        platform = context.args[0].lower()
        account_id = context.args[1]
        
        valid_platforms = ['instagram', 'twitter', 'telegram']
        if platform not in valid_platforms:
            await update.message.reply_text(f"Invalid platform. Choose: {', '.join(valid_platforms)}")
            return
            
        # Verify account exists
        if platform == 'instagram':
            result = await InstagramOSINT.get_user_info(account_id)
        elif platform == 'twitter':
            result = await TwitterOSINT.get_user_info(account_id)
        else:
            result = await TelegramOSINT.get_user_info(account_id)
            
        if not result.get('found'):
            await update.message.reply_text(f"❌ Account not found on {platform}")
            return
            
        # Add to tracking
        self.db.add_tracked(update.effective_user.id, platform, account_id, result.get('username', account_id))
        
        await update.message.reply_text(f"""
✅ <b>Account Added to Tracking</b>
{'='*30}
Platform: {platform}
Username: {result.get('username', account_id)}
Status: Active

<i>You will be notified of any changes!</i>
""", parse_mode=ParseMode.HTML)
        
    async def cmd_tracked(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /tracked command"""
        tracked = self.db.get_tracked(update.effective_user.id)
        
        if not tracked:
            await update.message.reply_text("📭 No accounts being tracked.")
            return
            
        text = f"📋 <b>Tracked Accounts ({len(tracked)})</b>\n{'='*30}\n"
        for platform, account_id, username in tracked:
            text += f"\n• {platform.upper()}: @{username} (ID: {account_id})"
            
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        
    async def cmd_untrack(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /untrack command"""
        if not context.args:
            await update.message.reply_text("Usage: /untrack <account_id>")
            return
            
        account_id = context.args[0]
        
        cursor = self.db.conn.cursor()
        cursor.execute(
            "DELETE FROM tracked_accounts WHERE account_id = ? AND user_id = ?",
            (account_id, update.effective_user.id)
        )
        self.db.conn.commit()
        
        if cursor.rowcount > 0:
            await update.message.reply_text(f"✅ Removed tracking for {account_id}")
        else:
            await update.message.reply_text(f"❌ Account not found in your tracking list")
            
    async def cmd_export(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /export command"""
        if not context.args:
            await update.message.reply_text("Usage: /export <format>\nFormats: txt, json, html")
            return
            
        format_type = context.args[0].lower()
        
        if format_type not in ['txt', 'json', 'html']:
            await update.message.reply_text("Invalid format. Choose: txt, json, html")
            return
            
        # Get last search result
        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT query_type, query, result FROM searches WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (update.effective_user.id,)
        )
        last = cursor.fetchone()
        
        if not last:
            await update.message.reply_text("No previous searches found. Run a search first!")
            return
            
        query_type, query, result = last
        data = json.loads(result) if result else {}
        data['query'] = f"{query_type}: {query}"
        
        # Generate report
        if format_type == 'txt':
            report = self.reporter.generate_txt(data)
            await update.message.reply_text(report[:4000])
        elif format_type == 'json':
            report = self.reporter.generate_json(data)
            await update.message.reply_text(report[:4000])
        elif format_type == 'html':
            report = self.reporter.generate_html(data)
            # Save to file and send
            filename = f"osint_report_{update.effective_user.id}_{int(time.time())}.html"
            with open(filename, 'w', encoding='utf-8') as f:
                f.write(report)
            await update.message.reply_document(document=open(filename, 'rb'))
            os.remove(filename)
            
    async def cmd_stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /stats command"""
        cursor = self.db.conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) FROM searches WHERE user_id = ?",
            (update.effective_user.id,)
        )
        total_searches = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT query_type, COUNT(*) FROM searches WHERE user_id = ? GROUP BY query_type",
            (update.effective_user.id,)
        )
        by_type = cursor.fetchall()
        
        cursor.execute(
            "SELECT COUNT(*) FROM tracked_accounts WHERE user_id = ?",
            (update.effective_user.id,)
        )
        tracked_count = cursor.fetchone()[0]
        
        text = f"""
📊 <b>Your OSINT Statistics</b>
{'='*30}
🔍 Total Searches: {total_searches}
📋 Tracked Accounts: {tracked_count}

<b>Searches by Type:</b>
"""
        for qtype, count in by_type:
            text += f"  • {qtype}: {count}\n"
            
        text += f"\n<i>Member since: {datetime.now().strftime('%Y-%m-%d')}</i>"
        
        await update.message.reply_text(text, parse_mode=ParseMode.HTML)
        
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle non-command messages"""
        text = update.message.text
        
        # Auto-detect and translate if needed
        if len(text) > 10 and not text.startswith('/'):
            translated = await self.translator.translate(text, 'en')
            if translated != text:
                await update.message.reply_text(f"🌐 Translation: {translated}")
                
    def run(self):
        """Run the bot"""
        print(f"""
{'='*50}
YASIN_VIPXIT OSINT BOT v{VERSION}
Author: {AUTHOR}
{'='*50}
Bot is running... Press Ctrl+C to stop
{'='*50}
""")
        self.application.run_polling()

# ============================================================================
# MAIN ENTRY POINT
# ============================================================================

def main():
    """Main function"""
    token = BOT_TOKEN
    
    if token == "YOUR_BOT_TOKEN_HERE":
        print("""
╔══════════════════════════════════════════════════════════════╗
║  ERROR: Please set your bot token!                          ║
║                                                            ║
║  1. Create a bot with @BotFather on Telegram               ║
║  2. Get your bot token                                     ║
║  3. Replace 'YOUR_BOT_TOKEN_HERE' with your token          ║
╚══════════════════════════════════════════════════════════════╝
        """)
        return
        
    bot = OSINTTelegramBot(token)
    bot.run()

if __name__ == "__main__":
    main()