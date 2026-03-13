import sys
import typing

# Ensure UTF-8 output even on Windows terminals that default to cp1252
if sys.platform == "win32":
    try:
        import codecs
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except (AttributeError, ImportError):
        pass

import subprocess
import time
import random
import string
import os
import socket
import argparse
import logging
import threading
import atexit
import re
import shutil
import urllib.request
import zipfile
import tarfile
import tempfile

# -----------------------------------------------------------------------------
# Dependency Management
# -----------------------------------------------------------------------------
def check_dependencies():
    """Checks and installs required Python packages."""
    needed = ["pyngrok", "python-dotenv", "qrcode"]
    installed = []
    
    # Check what is missing
    for pkg in needed:
        try:
            if pkg == "pyngrok": from pyngrok import ngrok
            elif pkg == "python-dotenv": from dotenv import load_dotenv
            elif pkg == "qrcode": import qrcode
            installed.append(pkg)
        except ImportError:
            pass

    missing = [pkg for pkg in needed if pkg not in installed]
    
    if missing:
        print(f"📦 Installing missing dependencies: {', '.join(missing)}...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install"] + missing)
            print("✅ Dependencies installed.\n")
        except Exception as e:
            print(f"❌ Failed to install dependencies: {e}")
            sys.exit(1)

def check_node_environment():
    """Checks for Node.js and installs npm dependencies if needed."""
    # 1. Check if Node is installed
    try:
        subprocess.check_call(["node", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except (FileNotFoundError, subprocess.CalledProcessError):
        print("❌ Error: Node.js is not installed. Please install it from https://nodejs.org/")
        sys.exit(1)

    # 2. Check for node_modules
    if not os.path.exists("node_modules"):
        print("📦 'node_modules' missing. Installing Node.js dependencies...")
        try:
            # shell=True often needed on Windows for npm. On *nix, 'npm' usually works directly if in PATH.
            is_windows = sys.platform == "win32"
            subprocess.check_call(["npm", "install"], shell=is_windows)
            print("✅ Node dependencies installed.\n")
        except Exception as e:
            print(f"❌ Failed to run 'npm install': {e}")
            sys.exit(1)

# -----------------------------------------------------------------------------
# Cloudflare Tunnel
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# Cloudflare Helpers
# -----------------------------------------------------------------------------
def download_cloudflared():
    """Downloads the cloudflared binary for the current OS."""
    base_url = "https://github.com/cloudflare/cloudflared/releases/latest/download/"
    ext = ".exe" if sys.platform == "win32" else ""
    local_bin = os.path.join(os.getcwd(), f"cloudflared{ext}")
    
    mapping = {
        "win32": "cloudflared-windows-amd64.exe",
        "darwin": "cloudflared-darwin-amd64.tgz",
        "linux": "cloudflared-linux-amd64"
    }
    
    platform = "linux" if sys.platform.startswith("linux") else sys.platform
    if platform not in mapping:
        return False
        
    filename = mapping[platform]
    download_url = base_url + filename
    
    print(f"📦 Downloading cloudflared for {platform}...")
    try:
        with urllib.request.urlopen(download_url) as response:
            if platform == "darwin":
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    tmp_file.write(response.read())
                    tmp_path = tmp_file.name
                with tarfile.open(tmp_path, "r:gz") as tar:
                    tar.extract("cloudflared", path=os.getcwd())
                os.remove(tmp_path)
            else:
                with open(local_bin, "wb") as f:
                    f.write(response.read())
        if sys.platform != "win32":
            os.chmod(local_bin, 0o755)
        print(f"✅ Downloaded and prepared: {local_bin}")
        return True
    except Exception as e:
        print(f"❌ Automation failed: {e}")
        return False

# -----------------------------------------------------------------------------
# Utility Helpers
# -----------------------------------------------------------------------------
def get_local_ip():
    """Robustly determines the local LAN IP address."""
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        if s: s.close()
    return IP

def generate_passcode():
    """Generates a 6-digit passcode."""
    return ''.join(random.choices(string.digits, k=6))

def print_qr(url):
    """Generates and prints a QR code to the terminal."""
    try:
        import qrcode
        qr = qrcode.QRCode(version=1, box_size=1, border=1)
        qr.add_data(url)
        qr.make(fit=True)
        qr.print_ascii(invert=True)
    except ImportError:
        print(f"📱 URL: {url} (Install 'qrcode' for QR display)")

# -----------------------------------------------------------------------------
# Tunnel Management
# -----------------------------------------------------------------------------
class TunnelManager:
    """Manages tunneling solutions (Cloudflare, ngrok) with smart fallbacks."""
    
    def __init__(self, port, protocol="http"):
        self.port = port
        self.protocol = protocol
        self.process: typing.Optional[subprocess.Popen] = None
        self.public_url: typing.Optional[str] = None
        self.tunnel_type: str = ""
        self.stop_event = threading.Event()
        self.monitor_thread: typing.Optional[threading.Thread] = None
        self.addr = f"{protocol}://localhost:{port}"
        
        # Register cleanup
        atexit.register(self.cleanup)

    def find_cloudflared(self) -> typing.Optional[str]:
        """Finds cloudflared in project root or system PATH."""
        ext = ".exe" if sys.platform == "win32" else ""
        local_bin = os.path.join(os.getcwd(), f"cloudflared{ext}")
        if os.path.exists(local_bin): return local_bin
        return shutil.which("cloudflared")

    def start_cloudflare(self, tunnel_name=None) -> bool:
        """Starts a Cloudflare tunnel (Named or Quick)."""
        cf_bin = self.find_cloudflared()
        if not cf_bin:
            if download_cloudflared():
                cf_bin = self.find_cloudflared()
            if not cf_bin: return False

        print(f"📡 Establishing Cloudflare Tunnel ({'Named: ' + tunnel_name if tunnel_name else 'Quick Tunnel'})...")
        cmd = [cf_bin, "tunnel"]
        if tunnel_name: cmd += ["run", tunnel_name]
        else: cmd += ["--url", self.addr]
        if self.protocol == "https": cmd.append("--no-tls-verify")

        try:
            self.process = subprocess.Popen(
                cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1
            )
            self.tunnel_type = "cloudflare_named" if tunnel_name else "cloudflare_quick"
            self.stop_event.clear()
            self.monitor_thread = threading.Thread(target=self._monitor_logs, daemon=True)
            self.monitor_thread.start()
            return True
        except Exception as e:
            print(f"❌ Failed to start cloudflared: {e}")
            return False

    def start_ngrok(self, token) -> bool:
        """Starts an ngrok tunnel."""
        try:
            from pyngrok import ngrok
            if token: ngrok.set_auth_token(token)
            print("📡 Establishing ngrok Tunnel...")
            tunnel = ngrok.connect(self.addr, host_header="rewrite")
            self.public_url = str(tunnel.public_url)
            self.tunnel_type = "ngrok"
            return True
        except Exception as e:
            print(f"❌ Failed to start ngrok: {e}")
            return False

    def _monitor_logs(self):
        """Monitor stdout/stderr for URL in Quick Tunnel mode."""
        url_pattern = re.compile(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)')
        if not self.process or not self.process.stdout: return
        
        for line in iter(self.process.stdout.readline, ''):
            if self.stop_event.is_set(): break
            if not self.public_url:
                match = url_pattern.search(line)
                if match:
                    self.public_url = match.group(1)
                    print(f"✨ Cloudflare Quick Tunnel established: {self.public_url}")

    def cleanup(self):
        """Terminates all tunnel processes."""
        self.stop_event.set()
        if self.process:
            try:
                self.process.terminate()
                self.process.wait(timeout=2)
            except:
                try: self.process.kill()
                except: pass
            self.process = None
        if self.tunnel_type == "ngrok":
            try:
                from pyngrok import ngrok
                ngrok.kill()
            except: pass

def main():
    parser = argparse.ArgumentParser(description="Antigravity Phone Connect Launcher")
    parser.add_argument('--mode', choices=['local', 'web'], default='web', help="Mode to run in: 'local' (WiFi) or 'web' (Internet)")
    args = parser.parse_args()

    # 1. Setup Environment
    check_dependencies()
    check_node_environment()
    
    logging.getLogger("pyngrok").setLevel(logging.ERROR)
    from dotenv import load_dotenv
    load_dotenv()
    
    passcode = os.environ.get('APP_PASSWORD')
    if not passcode:
        passcode = generate_passcode()
        os.environ['APP_PASSWORD'] = passcode
        print(f"⚠️  No APP_PASSWORD in .env. Using temporary: {passcode}")

    # 2. Start Node.js Server
    print(f"🚀 Starting Antigravity Server ({args.mode.upper()} mode)...")
    with open("server_log.txt", "w") as f:
        f.write(f"--- Server Started at {time.ctime()} ---\n")

    node_cmd = ["node", "server.js"]
    node_process = None
    try:
        log_file = open("server_log.txt", "a")
        node_process = subprocess.Popen(node_cmd, stdout=log_file, stderr=log_file, env=os.environ.copy())
        time.sleep(2)
        if node_process.poll() is not None:
            print("❌ Server failed to start immediately. Check server_log.txt.")
            sys.exit(1)
    except Exception as e:
        print(f"❌ Failed to launch node: {e}")
        sys.exit(1)

    # 3. Connection Setup
    port = os.environ.get('PORT', '3000')
    protocol = "https" if os.path.exists('certs/server.key') and os.path.exists('certs/server.cert') else "http"
    
    if args.mode == 'local':
        ip = get_local_ip()
        final_url = f"{protocol}://{ip}:{port}"
        print("\n" + "="*50 + "\n📡 LOCAL WIFI ACCESS\n" + "="*50)
        print(f"🔗 URL: {final_url}\n📱 Scan QR to connect:")
        print_qr(final_url)
    else:
        # WEB MODE - Smart Connectivity
        manager = TunnelManager(port, protocol)
        
        tunnel_domain = os.environ.get('TUNNEL_DOMAIN', '').strip()
        tunnel_name = os.environ.get('TUNNEL_NAME', '').strip()
        ngrok_token = os.environ.get('NGROK_AUTHTOKEN', '').strip()
        
        success = False
        
        # Priority 1: Named Tunnel
        if tunnel_domain and tunnel_name:
            if manager.start_cloudflare(tunnel_name):
                manager.public_url = f"https://{tunnel_domain}"
                success = True
            else:
                print("⚠️  Named Tunnel failed. Falling back...")

        # Priority 2: ngrok
        if not success and ngrok_token:
            if manager.start_ngrok(ngrok_token):
                success = True
            else:
                print("⚠️  ngrok failed. Falling back...")
                
        # Priority 3: Quick Tunnel (Zero Config / Fallback)
        if not success:
            if not manager.start_cloudflare(): # Quick Tunnel
                print("❌ Failed to establish any tunnel solution.")
                sys.exit(1)
            
            # Wait for Quick Tunnel URL
            print("⏳ Waiting for Quick Tunnel URL...")
            start_time = time.time()
            while not manager.public_url and time.time() - start_time < 15:
                time.sleep(0.5)
            
            if not manager.public_url:
                print("❌ Quick Tunnel timed out.")
                sys.exit(1)

        # Final UI
        final_url = f"{manager.public_url}?key={passcode}"
        print("\n" + "="*50 + "\n🌍 GLOBAL WEB ACCESS\n" + "="*50)
        print(f"🔗 Base URL: {manager.public_url}\n🔑 Passcode: {passcode}")
        print("\n📱 Scan Magic QR (Auto-Login):")
        print_qr(final_url)

    # 4. Keep Alive / Monitor
    print("="*50 + "\n✅ Running. Press Ctrl+C to stop.")
    
    # Debug info
    print("\n[DEBUG] Port 9000 check...")
    try:
        if sys.platform == "win32":
            output = subprocess.check_output("netstat -ano | findstr :9000", shell=True).decode()
            if "LISTENING" in output: print("✅ Port 9000 active.")
        else:
            output = subprocess.check_output("lsof -i :9000", shell=True).decode()
            if "LISTEN" in output: print("✅ Port 9000 active.")
    except: pass
    
    try:
        last_log_pos = 0
        cdp_warning_shown = False
        while True:
            time.sleep(1)
            if node_process and node_process.poll() is not None:
                print("\n❌ Server process died!")
                break
            
            # Monitor logs for CDP warning
            if os.path.exists("server_log.txt"):
                with open("server_log.txt", "r", encoding='utf-8', errors='ignore') as f:
                    f.seek(last_log_pos)
                    lines = f.readlines()
                    last_log_pos = f.tell()
                    for line in lines:
                        if "CDP not found" in line and not cdp_warning_shown:
                            print("\n" + "!"*50 + "\n❌ ERROR: Antigravity Editor Not Detected!\n" + "!"*50)
                            cdp_warning_shown = True
    except KeyboardInterrupt:
        print("\n👋 Shutting down...")
    finally:
        if node_process:
            node_process.terminate()
        sys.exit(0)

if __name__ == "__main__":
    main()
