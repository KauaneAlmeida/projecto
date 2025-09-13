const { default: makeWASocket, DisconnectReason, useMultiFileAuthState } = require('@whiskeysockets/baileys');
const { Boom } = require('@hapi/boom');
const qrcode = require('qrcode-terminal');
const QRCode = require('qrcode');
const express = require('express');
const fs = require('fs');
const path = require('path');

// Configuração
const CONFIG = {
    phoneNumber: '+5511918368812',
    whatsappWebVersion: [2, 3000, 1026946712],
    sessionPath: './whatsapp_session',
    pendingMessageFile: 'pending_message.json',
    expressPort: process.env.PORT || 3000
};

// Express app setup
const app = express();
app.use(express.json());
let qrCodeBase64 = null;

class BaileysWhatsAppBot {
    constructor() {
        this.sock = null;
        this.isConnected = false;
        this.authState = null;
        this.saveCreds = null;
        this.setupExpressServer();
    }

    setupExpressServer() {
        // QR Code display route
        app.get('/qr', async (req, res) => {
            try {
                const htmlContent = `
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connect your WhatsApp</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <style>
        body { background: linear-gradient(135deg, #25D366 0%, #128C7E 100%); min-height: 100vh; }
        .qr-container { background: white; border-radius: 20px; padding: 3rem; margin: 2rem auto; max-width: 500px; text-align: center; box-shadow: 0 10px 30px rgba(0,0,0,0.2); }
        .qr-code-img { max-width: 280px; border: 3px solid #25D366; border-radius: 15px; padding: 15px; background: white; }
        .title { color: #128C7E; font-weight: 700; margin-bottom: 1rem; }
        .subtitle { color: #666; font-size: 1rem; margin-top: 1rem; }
        .footer { margin-top: 2rem; font-size: 0.9rem; color: #888; }
        .refresh-btn { background: #25D366; border: none; border-radius: 25px; padding: 10px 25px; color: white; font-weight: 600; transition: all 0.3s ease; }
        .refresh-btn:hover { background: #128C7E; transform: translateY(-2px); }
        .status-connected { color: #28a745; font-size: 1.2rem; font-weight: bold; }
        .status-waiting { color: #ffc107; font-size: 1.1rem; font-weight: bold; }
        .spinner-border { width: 1rem; height: 1rem; margin-right: 0.5rem; }
    </style>
</head>
<body>
    <div class="container d-flex justify-content-center align-items-center min-vh-100">
        <div class="qr-container">
            <h1 class="title">🔗 Connect WhatsApp</h1>
            ${this.isConnected 
                ? '<div class="mb-3 status-connected">✅ Conectado com sucesso!</div>'
                : '<div class="mb-3 status-waiting"><div class="spinner-border text-warning" role="status"></div>Waiting for connection...</div>'}
            ${qrCodeBase64 && !this.isConnected
                ? `<div class="mb-3">
                     <img src="${qrCodeBase64}" class="qr-code-img" alt="WhatsApp QR Code">
                     <p class="subtitle">📱 Scan this QR Code with WhatsApp</p>
                     <small class="text-muted">Open WhatsApp → Settings → Linked Devices → Link a Device</small>
                   </div>`
                : this.isConnected
                ? '<div class="mb-3"><p class="subtitle">WhatsApp está conectado e pronto!</p></div>'
                : '<div class="mb-3"><p class="subtitle">⏳ Gerando QR Code...</p></div>'}
            <button class="refresh-btn mt-3" onclick="window.location.reload()">🔄 Refresh</button>
            <div class="footer">
                <strong>WhatsApp Bot Service</strong><br>
                <small>${CONFIG.phoneNumber}</small><br>
                <small class="text-muted">Powered by Baileys</small>
            </div>
        </div>
    </div>
</body>
</html>`;
                res.send(htmlContent);
            } catch (error) {
                console.error('❌ Error serving QR page:', error);
                res.status(500).send("Error");
            }
        });

        // 👉 Servir frontend (chat demo)
        app.use('/chat-demo', express.static(path.join(__dirname, 'frontend')));

        // API endpoint for QR status
        app.get('/api/qr-status', (req, res) => {
            res.json({
                hasQR: !!qrCodeBase64,
                isConnected: this.isConnected,
                phoneNumber: CONFIG.phoneNumber,
                timestamp: new Date().toISOString(),
                status: this.isConnected ? 'connected' : qrCodeBase64 ? 'waiting_for_scan' : 'generating_qr'
            });
        });

        // Send message endpoint
        app.post('/send-message', async (req, res) => {
            try {
                const { to, message } = req.body;
                if (!to || !message) {
                    return res.status(400).json({ success: false, error: 'Missing required fields: to, message' });
                }
                if (!this.isConnected) {
                    return res.status(503).json({ success: false, error: 'WhatsApp not connected. Please scan QR code first.' });
                }
                const messageId = await this.sendMessage(to, message);
                res.json({ success: true, messageId, to, timestamp: new Date().toISOString() });
            } catch (error) {
                console.error('❌ Error in send-message endpoint:', error);
                res.status(500).json({ success: false, error: error.message || 'Failed to send message' });
            }
        });

        // Health check endpoint
        app.get('/health', (req, res) => {
            res.json({
                status: 'healthy',
                service: 'whatsapp_bot',
                connected: this.isConnected,
                uptime: process.uptime(),
                timestamp: new Date().toISOString()
            });
        });

        // Start Express server
        app.listen(CONFIG.expressPort, '0.0.0.0', () => {
            console.log(`🌐 Express server running on http://localhost:${CONFIG.expressPort}`);
            console.log(`📱 QR Code page: http://localhost:${CONFIG.expressPort}/qr`);
            console.log(`💬 Chat demo: http://localhost:${CONFIG.expressPort}/chat-demo/index.html`);
            console.log(`🔍 Health check: http://localhost:${CONFIG.expressPort}/health`);
        });
    }

    async initialize() {
        try {
            console.log('🚀 Initializing Baileys WhatsApp Bot...');
            console.log(`📞 Phone: ${CONFIG.phoneNumber}`);
            console.log(`🌐 Server: http://localhost:${CONFIG.expressPort}`);

            if (!fs.existsSync(CONFIG.sessionPath)) {
                fs.mkdirSync(CONFIG.sessionPath, { recursive: true });
                console.log(`📁 Created session directory: ${CONFIG.sessionPath}`);
            }

            const { state, saveCreds } = await useMultiFileAuthState(CONFIG.sessionPath);
            this.authState = state;
            this.saveCreds = saveCreds;

            await this.connectToWhatsApp();
            this.startMessageProcessor();
        } catch (error) {
            console.error('❌ Error initializing WhatsApp bot:', error);
            process.exit(1);
        }
    }

    async connectToWhatsApp() {
        try {
            console.log('🔌 Connecting to WhatsApp Web...');
            this.sock = makeWASocket({
                auth: this.authState,
                version: CONFIG.whatsappWebVersion,
                printQRInTerminal: false,
                browser: ['WhatsApp Bot', 'Chrome', '91.0'],
                defaultQueryTimeoutMs: 60000,
                keepAliveIntervalMs: 10000,
                markOnlineOnConnect: true
            });
            this.setupEventHandlers();
        } catch (error) {
            console.error('❌ Error connecting to WhatsApp:', error);
            throw error;
        }
    }

    setupEventHandlers() {
        this.sock.ev.on('connection.update', async (update) => {
            const { connection, lastDisconnect, qr } = update;

            if (qr) {
                console.log('📱 New QR Code generated!');
                console.log('🌐 Visit http://localhost:' + CONFIG.expressPort + '/qr to scan');
                qrcode.generate(qr, { small: true });

                try {
                    qrCodeBase64 = await QRCode.toDataURL(qr, {
                        width: 280,
                        margin: 2,
                        color: { dark: '#000000', light: '#FFFFFF' }
                    });
                    console.log('✅ QR Code ready for web display');
                } catch (err) {
                    console.error('❌ Error generating QR code for web:', err);
                }
            }

            if (connection === 'close') {
                this.isConnected = false;
                qrCodeBase64 = null;
                const shouldReconnect = (lastDisconnect?.error instanceof Boom)
                    ? lastDisconnect.error.output.statusCode !== DisconnectReason.loggedOut
                    : true;

                console.log('🔌 Connection closed:', lastDisconnect?.error?.message || 'Unknown reason');
                if (shouldReconnect) {
                    console.log('🔄 Reconnecting in 5 seconds...');
                    setTimeout(() => {
                        this.connectToWhatsApp().catch(console.error);
                    }, 5000);
                } else {
                    console.log('❌ Logged out. Please restart and scan QR code again.');
                    process.exit(0);
                }
            } else if (connection === 'open') {
                console.log('✅ WhatsApp connected successfully!');
                this.isConnected = true;
                qrCodeBase64 = null;
                const user = this.sock.user;
                if (user) console.log(`👤 Connected as: ${user.name || user.id}`);
            } else if (connection === 'connecting') {
                console.log('🔄 Connecting to WhatsApp...');
            }
        });

        this.sock.ev.on('creds.update', this.saveCreds);

        this.sock.ev.on('messages.upsert', async (m) => {
            try {
                const msg = m.messages[0];
                if (!msg.key.fromMe && m.type === 'notify') {
                    const messageText = msg.message?.conversation || msg.message?.extendedTextMessage?.text || null;
                    if (messageText) {
                        console.log('📨 New message from', msg.key.remoteJid, ':', messageText);
                        await this.forwardToWebhook(msg.key.remoteJid, messageText, msg.key.id);
                    }
                }
            } catch (error) {
                console.error('❌ Error processing incoming message:', error);
            }
        });
    }

    async forwardToWebhook(from, message, messageId) {
        try {
            const webhookUrl = process.env.FASTAPI_WEBHOOK_URL || 'http://law_firm_backend:8000/api/v1/whatsapp/webhook';
            const payload = { from, message, messageId, timestamp: new Date().toISOString(), platform: 'whatsapp' };

            console.log('🔄 Forwarding message to FastAPI webhook:', webhookUrl);
            console.log('📨 Message preview:', message.substring(0, 50) + (message.length > 50 ? '...' : ''));
            
            // Use node-fetch or built-in fetch (Node 18+)
            const fetch = globalThis.fetch || require('node-fetch');
            const response = await fetch(webhookUrl, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            
            if (response.ok) {
                console.log('✅ Message forwarded to FastAPI successfully');
                const responseData = await response.json();
                console.log('📋 FastAPI response type:', responseData.response_type || 'unknown');
            } else {
                console.error('❌ Failed to forward message to FastAPI:', response.status);
                const errorText = await response.text();
                console.error('Error details:', errorText);
            }
        } catch (error) {
            console.error('❌ Error forwarding message to webhook:', error);
        }
    }

    async sendMessage(to, message) {
        if (!this.isConnected || !this.sock) throw new Error('WhatsApp not connected');
        try {
            console.log('📤 Sending WhatsApp message:', message.substring(0, 100) + (message.length > 100 ? '...' : ''));
            const result = await this.sock.sendMessage(to, { text: message });
            console.log('✅ Message sent successfully:', result.key.id);
            return result.key.id;
        } catch (error) {
            console.error('❌ Error sending message:', error);
            throw error;
        }
    }

    startMessageProcessor() {
        console.log('🔄 Starting message processor...');
        setInterval(async () => {
            try {
                if (fs.existsSync(CONFIG.pendingMessageFile)) {
                    const data = JSON.parse(fs.readFileSync(CONFIG.pendingMessageFile, 'utf8'));
                    if (data.action === 'send_message' && data.to && data.message) {
                        console.log('📤 Processing pending message from file...');
                        await this.sendMessage(data.to, data.message);
                        fs.unlinkSync(CONFIG.pendingMessageFile);
                        console.log('✅ Processed and removed pending message file');
                    }
                }
            } catch (error) {
                if (error.code !== 'ENOENT') console.error('❌ Error processing pending message:', error);
            }
        }, 2000);
    }
}

// Initialize bot
const bot = new BaileysWhatsAppBot();
bot.initialize().catch((error) => {
    console.error('💥 Fatal error during initialization:', error);
    process.exit(1);
});

console.log('🤖 Baileys WhatsApp Bot starting...');
console.log(`🌐 Open http://localhost:${CONFIG.expressPort}/qr to scan the QR code`);

const gracefulShutdown = (signal) => {
    console.log(`📴 Received ${signal}, shutting down gracefully...`);
    if (bot.sock) {
        try { bot.sock.end(); } catch (error) { console.error('Error closing WhatsApp connection:', error); }
    }
    process.exit(0);
};

process.on('SIGTERM', () => gracefulShutdown('SIGTERM'));
process.on('SIGINT', () => gracefulShutdown('SIGINT'));

process.on('uncaughtException', (error) => {
    console.error('💥 Uncaught Exception:', error);
    process.exit(1);
});
process.on('unhandledRejection', (reason, promise) => {
    console.error('💥 Unhandled Rejection at:', promise, 'reason:', reason);
    process.exit(1);
});
