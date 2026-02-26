# SECURITY - Antigravity Phone Connect

This document explains the security model, HTTPS setup, and how to handle browser warnings.

---

## 🔒 HTTPS & SSL Certificates

Antigravity Phone Connect supports HTTPS for secure connections between your phone and desktop.

### Why HTTPS?

- **Encrypted Traffic**: All data between your phone and server is encrypted.
- **No Browser Warning Icon**: Removes the ⚠️ "Not Secure" warning in the address bar.
- **Professional Experience**: Feels more polished and trustworthy.

### Certificate Generation Methods

The `generate_ssl.js` script uses a **hybrid approach**:

| Method | When Used | Benefits |
|--------|-----------|----------|
| **OpenSSL** (preferred) | When OpenSSL is installed | Full IP address SAN support, cleaner browser warnings |
| **Node.js crypto** (fallback) | When OpenSSL not available | Zero dependencies, works everywhere |

**OpenSSL availability by platform:**
- **Windows**: Available if Git for Windows is installed
- **macOS**: LibreSSL built-in (compatible)
- **Linux**: Usually pre-installed

### Self-Signed vs CA-Signed Certificates

| Type | Pros | Cons |
|------|------|------|
| **Self-Signed** (what we use) | Free, works offline, no domain needed, instant setup | Browser shows warning on first visit |
| **CA-Signed** (Let's Encrypt, etc.) | No browser warnings | Requires domain name, internet access, periodic renewal |

For local network use, **self-signed certificates are the practical choice**.

---

## ⚠️ "Your Connection is Not Private" Warning

When you first visit the HTTPS URL on your phone, you'll see a warning like:

> **Your connection is not private**  
> Attackers might be trying to steal your information from 192.168.1.x  
> `NET::ERR_CERT_AUTHORITY_INVALID`

### Is This Safe?

**Yes, for your local network.** This warning appears because:
1. The certificate is "self-signed" (created by you, not a Certificate Authority)
2. Your browser doesn't recognize the issuer
3. This is **expected behavior** for local development servers

### How to Bypass (By Browser/Device)

#### Android Chrome
1. Tap **"Advanced"** at the bottom of the warning page
2. Tap **"Proceed to 192.168.1.x (unsafe)"**

#### iPhone Safari
1. Tap **"Show Details"**
2. Tap **"visit this website"**
3. Tap **"Visit Website"** in the confirmation popup

#### iPhone Chrome
1. Tap **"Advanced"**
2. Tap **"Proceed to 192.168.1.x (unsafe)"**

#### Desktop Chrome/Edge
1. Click **"Advanced"**
2. Click **"Proceed to localhost (unsafe)"**

#### Desktop Firefox
1. Click **"Advanced..."**
2. Click **"Accept the Risk and Continue"**

### After Accepting

**What you'll see in all browsers:**

All browsers will show **"Not Secure"** but **"Encrypted"** - this is expected!

| Browser | Icon | Message |
|---------|------|---------|
| Chrome (Android/Desktop) | 🔴 Red octagon with X | "Not secure" - but encrypted |
| Safari (iPhone) | ⚠️ Triangle warning | "Not Trusted" - but encrypted |
| Firefox | 🔴 Red octagon with X | "Not secure" - but encrypted |
| Edge | 🔴 Red octagon with X | "Not secure" - but encrypted |

**Why "Not Secure" but still encrypted?**
- ✅ **Your data IS encrypted** with TLS 1.3 / AES-256
- ❌ The certificate isn't from a trusted Certificate Authority
- This is **normal and expected** for self-signed certificates

**Key points:**
- ✅ The initial warning won't appear again (until you clear browser data)
- ✅ All traffic is encrypted with modern TLS 1.3
- ✅ Tap the icon → "Connection is encrypted" confirms security

---

## 🔑 Passcode Protection (NEW)

To secure your session when accessing it globally, Antigravity Phone Connect now includes a built-in authentication layer.

### How it Works
1. **Local Access (Wi-Fi)**: The server detects your local IP. Devices on same Wi-Fi are **automatically authenticated**.
2. **Global Access (Mobile Data)**: Requests from the internet (via ngrok) require a **Passcode**.
3. **Session Cookies**: Once logged in, your browser stores a secure, signed cookie valid for 30 days.

### Configuration
1. Copy `.env.example` to `.env`.
2. Set your custom password and API keys in the `.env` file:
```env
APP_PASSWORD=your_secure_password
XXX_API_KEY=your-ai-provider-key
```
*If no password is set, the server will generate a **temporary 6-digit passcode** each time it starts and display it in the terminal.*

---

## 🛡️ Security Model

### What's Protected

- **Transport Layer**: All HTTP traffic is encrypted with TLS 1.3 when using HTTPS.
- **Passcode Protection**: When accessed via the internet (ngrok) or non-local networks, a password/passcode is mandatory to prevent unauthorized access.
- **Local Exemption**: Intelligent IP detection automatically trusts your local Wi-Fi devices, allowing password-free access at home.
- **Secure Sessions**: Uses signed, `httpOnly` cookies that are inaccessible to cross-site scripting (XSS) attacks.
- **Input Sanitization**: User messages are escaped using `JSON.stringify` before CDP injection.
- **Graceful Shutdown**: Server cleans up connections properly on exit.

### What's NOT Protected

- **Self-Signed Certs**: Not trusted by browsers without manual accept (see "Bypassing Warnings" above).
- **Physical Access**: Anyone with physical access to your phone or desktop can control the session.

### Remote Access Strategy

| Method | Safety | Recommendation |
|----------|--------|----------------|
| **Local Wi-Fi** | 🟢 High | Default mode, no password required. |
| **_web Mode (ngrok)** | 🟡 Medium | Use `APP_PASSWORD` in `.env` (cloned from `.env.example`) for secure global access. |
| **Port Forwarding** | 🔴 Low | **NOT RECOMMENDED**. Use the built-in `_web` tunnel instead. |

### Recommendations

| Scenario | Recommendation |
|----------|----------------|
| Home network (trusted) | Use as-is, HTTPS recommended |
| Shared network (office) | Enable HTTPS, consider adding auth |
| Remote access | Use VPN or SSH tunnel, never expose directly to internet |

---

## 🔑 Certificate Management

### Generating Certificates

```bash
node generate_ssl.js
```

**What it does:**
1. Detects your local IP addresses (e.g., 192.168.1.3)
2. Tries OpenSSL first (if available) - includes IP in certificate SAN
3. Falls back to Node.js crypto if OpenSSL not found
4. Creates `certs/server.key` and `certs/server.cert`

**Example output:**
```
🔐 Generating self-signed SSL certificate...

📍 Detected IP addresses: 192.168.1.3, 127.0.0.1

🔧 Using OpenSSL for certificate generation...

✅ SSL certificates generated successfully!
   Method: OpenSSL
   Key:    ./certs/server.key
   Cert:   ./certs/server.cert
   SANs:   localhost, 192.168.1.3, 127.0.0.1
```

### Web UI Method

If you're already running the server on HTTP:
1. Look for the yellow **"⚠️ Not Secure"** banner
2. Click **"Enable HTTPS"** button
3. Restart the server when prompted

### Regenerating Certificates

If you need a new certificate (e.g., IP changed, expired, or compromised):

```bash
# Delete old certificates
rm -rf certs/     # Linux/macOS
rmdir /s certs    # Windows

# Generate new ones
node generate_ssl.js

# Restart server
node server.js
```

Note: After regenerating, you'll need to accept the browser warning again on all devices.

### Certificate Location

Certificates are stored in `./certs/` and are **gitignored** - they will NOT be committed to version control.

### Verifying Your Certificate

To check which certificate you're using and its details:

**Windows (with Git):**
```powershell
& "C:\Program Files\Git\usr\bin\openssl.exe" x509 -in certs/server.cert -text -noout | Select-String -Pattern "Subject:|Issuer:|Not Before|Not After|DNS:|IP Address:"
```

**macOS/Linux:**
```bash
openssl x509 -in certs/server.cert -text -noout | grep -E "Subject:|Issuer:|Not Before|Not After|DNS:|IP Address:"
```

**Example output:**
```
Issuer: C=US, O=AntigravityPhoneConnect, CN=localhost
Not Before: Jan 17 06:55:13 2026 GMT
Not After : Jan 17 06:55:13 2027 GMT
Subject: C=US, O=AntigravityPhoneConnect, CN=localhost
DNS:localhost, IP Address:192.168.1.3, IP Address:127.0.0.1
```

**Quick check (any platform):**
```bash
node -e "const fs=require('fs'); console.log(fs.existsSync('certs/server.cert') ? '✅ Certificate exists' : '❌ No certificate')"
```

---

## 🌐 Network Security

### Local Network Only

By default, the server binds to `0.0.0.0:3000`, meaning:
- ✅ Accessible from any device on your LAN
- ✅ Accessible via `localhost` on the host machine
- ❌ NOT accessible from the internet (unless you port-forward)

### Firewall Considerations

If you can't connect from your phone:
1. Check Windows Firewall / macOS Firewall settings
2. Ensure port 3000 is allowed for Node.js
3. Verify both devices are on the same Wi-Fi network

---

## 🔧 Installing OpenSSL (Optional)

For the best certificate experience (proper IP SAN support), install OpenSSL:

### Windows
- **Easiest**: Install [Git for Windows](https://git-scm.com/) - includes OpenSSL
- **Standalone**: Download from [slproweb.com](https://slproweb.com/products/Win32OpenSSL.html)

### macOS
```bash
# Already included as LibreSSL, or install via Homebrew:
brew install openssl
```

### Linux
```bash
# Usually pre-installed, or:
sudo apt install openssl    # Debian/Ubuntu
sudo yum install openssl    # RHEL/CentOS
```

---

## 🛡️ Security Audit Log

| Date | Type | Status | Summary |
|------|------|--------|---------|
| 2026-02-26 | **Full Sweep** | 🟢 **PASSED** | Hardcoded secrets moved to `.env`. XSS/CDP injection guards verified. |

### Audit Details

- **Secrets Detection**: No sensitive API keys found in codebase. Default passwords and salts externalized to `.env`.
- **Injection Prevention**: 
    - ✅ **XSS**: Scraped content is strictly escaped via `escapeHtml` before rendering.
    - ✅ **CDP**: All interactions (`injectMessage`, `clickElement`) use `JSON.stringify` for safe expression building.
- **Authentication**: Verified `signedCookie` middleware and `httpOnly` flags.
- **Access Control**: Validated `isLocalRequest` logic for LAN auto-trust vs Global passcode enforcement.
- **Dependencies**: All packages verified safe and up-to-date.

---

## 📚 Related Documentation

- [README.md](README.md) - Quick start and HTTPS setup instructions
- [CODE_DOCUMENTATION.md](CODE_DOCUMENTATION.md) - Technical details of SSL implementation
- [DESIGN_PHILOSOPHY.md](DESIGN_PHILOSOPHY.md) - Security design decisions
- [CONTRIBUTING.md](CONTRIBUTING.md) - Security checklist for contributors

---