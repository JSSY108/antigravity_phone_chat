import sys
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
cloudflare_process = None

def cleanup_cloudflare():
    global cloudflare_process
    if cloudflare_process:
        try:
            cloudflare_process.terminate()
            cloudflare_process.wait(timeout=2)
        except:
            try:
                cloudflare_process.kill()
            except:
                pass
        cloudflare_process = None

# Register cleanup handler to ensure tunnel_proc.terminate() is called
atexit.register(cleanup_cloudflare)

def find_cloudflared():
    """Finds the cloudflared executable in PATH or project root."""
    # Check PATH
    path_bin = shutil.which("cloudflared")
    if path_bin:
        return path_bin
        
    # Check project root
    ext = ".exe" if sys.platform == "win32" else ""
    local_bin = os.path.join(os.getcwd(), f"cloudflared{ext}")
    if os.path.exists(local_bin):
        return local_bin
        
    return None

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
                # Handle .tgz for macOS
                with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
                    tmp_file.write(response.read())
                    tmp_path = tmp_file.name
                
                with tarfile.open(tmp_path, "r:gz") as tar:
                    tar.extract("cloudflared", path=os.getcwd())
                os.remove(tmp_path)
            else:
                with open(local_bin, "wb") as f:
                    f.write(response.read())
        
        # Set executable permissions on Unix
        if sys.platform != "win32":
            os.chmod(local_bin, 0o755)
            
        print(f"✅ Downloaded and prepared: {local_bin}")
        return True
    except Exception as e:
        print(f"❌ Automation failed: {e}")
        return False

def show_cloudflare_setup_guide():
    """Prints a high-visibility guide for downloading cloudflared and attempts auto-download."""
    print("\n" + "!"*60)
    print("🚀 UNLIMITED BANDWIDTH: CLOUDFLARE QUICK TUNNEL")
    print("!"*60)
    
    if download_cloudflared():
        print("✨ cloudflared was automatically installed!")
        print("!"*60 + "\n")
        return True

    print("To bypass ngrok's 1GB limit, please download 'cloudflared' manually:")
    
    if sys.platform == "win32":
       print("1. Download: https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe")
       print("2. Rename it to 'cloudflared.exe'")
    elif sys.platform == "darwin":
       print("1. Install via Homebrew: brew install cloudflared")
       print("2. Or download: https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-darwin-amd64.tgz")
    else:
       print("1. Download: https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64")
       print("2. Rename it to 'cloudflared'")

    print("\n3. Move the file into this folder:")
    print(f"   {os.getcwd()}")
    print("!"*60 + "\n")

def get_cloudflare_url(port, protocol="http"):
    """Starts cloudflared and extracts the generated trycloudflare URL."""
    global cloudflare_process
    
    cf_bin = find_cloudflared()
    if not cf_bin:
        return None
        
    print(f"PLEASE WAIT... Establishing Cloudflare Tunnel (using {os.path.basename(cf_bin)})...")
    
    # Use the same protocol as the local server
    origin_url = f"{protocol}://localhost:{port}"
    cmd = [cf_bin, "tunnel", "--url", origin_url]
    
    # If using HTTPS locally (often self-signed), disable certificate verification for the tunnel
    if protocol == "https":
        cmd.append("--no-tls-verify")
    
    try:
        # Capture stderr into stdout for combined log parsing
        cloudflare_process = subprocess.Popen(
            cmd, 
            stdout=subprocess.PIPE, 
            stderr=subprocess.STDOUT, 
            text=True,
            bufsize=1 # Line buffered
        )
    except Exception as e:
        print(f"❌ Failed to start cloudflared: {e}")
        return None
        
    url_event = threading.Event()
    found_url = [""]
    captured_logs = []
    
    def read_output():
        if not cloudflare_process or not cloudflare_process.stdout:
            return
            
        url_pattern = re.compile(r'(https://[a-zA-Z0-9-]+\.trycloudflare\.com)')
        for line in iter(cloudflare_process.stdout.readline, ''):
            if not line:
                break
            
            captured_logs.append(line.strip())
            # Keep log buffer reasonable
            if len(captured_logs) > 50: captured_logs.pop(0)

            # Look for the URL if we haven't found it yet
            if not found_url[0]:
                match = url_pattern.search(line)
                if match:
                    found_url[0] = match.group(1)
                    url_event.set()
                    
    reader_thread = threading.Thread(target=read_output, daemon=True)
    reader_thread.start()
    
    # Wait for the URL to be found, with a timeout
    if url_event.wait(timeout=15):
        return found_url[0] if found_url[0] else None
    else:
        print("❌ Cloudflare tunnel failed to establish URL.")
        print("\n--- CLOUDFLARE ERROR LOGS ---")
        for log in captured_logs:
            print(f"  [cf] {log}")
        print("-----------------------------\n")
        cleanup_cloudflare()
        return None

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def get_local_ip():
    """Robustly determines the local LAN IP address."""
    s = None
    try:
        # Connect to a public DNS server (doesn't actually send data)
        # This forces the OS to determine the correct outgoing interface
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('8.8.8.8', 80))
        IP = s.getsockname()[0]
    except Exception:
        IP = '127.0.0.1'
    finally:
        s.close()
    return IP

def generate_passcode():
    """Generates a 6-digit passcode."""
    return ''.join(random.choices(string.digits, k=6))

def print_qr(url):
    """Generates and prints a QR code to the terminal."""
    import qrcode
    qr = qrcode.QRCode(version=1, box_size=1, border=1)
    qr.add_data(url)
    qr.make(fit=True)
    # Using 'ANSI' implies standard block characters which work in most terminals
    # invert=True is often needed for dark terminals (white blocks on black bg)
    qr.print_ascii(invert=True)

# -----------------------------------------------------------------------------
# Main Execution
# -----------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="Antigravity Phone Connect Launcher")
    parser.add_argument('--mode', choices=['local', 'web'], default='web', help="Mode to run in: 'local' (WiFi) or 'web' (Internet)")
    args = parser.parse_args()

    # 1. Setup Environment
    check_dependencies()
    check_node_environment()
    
    # Suppress pyngrok noise (especially during shutdown)
    logging.getLogger("pyngrok").setLevel(logging.ERROR)
    
    from pyngrok import ngrok

    from dotenv import load_dotenv
    
    # Load .env if it exists
    load_dotenv()
    
    # Setup App Password
    passcode = os.environ.get('APP_PASSWORD')
    if not passcode:
        passcode = generate_passcode()
        os.environ['APP_PASSWORD'] = passcode # Set for child process
        print(f"⚠️  No APP_PASSWORD in .env. Using temporary: {passcode}")

    # 2. Start Node.js Server (Common to both modes)
    print(f"🚀 Starting Antigravity Server ({args.mode.upper()} mode)...")
    
    # Clean up old logs
    with open("server_log.txt", "w") as f:
        f.write(f"--- Server Started at {time.ctime()} ---\n")

    node_cmd = ["node", "server.js"]
    node_process = None
    
    try:
        # Redirect stdout/stderr to file
        log_file = open("server_log.txt", "a")
        if sys.platform == "win32":
            # On Windows, using shell=True can help with path resolution but makes killing harder.
            # We'll use shell=False and rely on PATH.
            node_process = subprocess.Popen(node_cmd, stdout=log_file, stderr=log_file, env=os.environ.copy())
        else:
            node_process = subprocess.Popen(node_cmd, stdout=log_file, stderr=log_file, env=os.environ.copy())
            
        time.sleep(2) # Give it a moment to crash if it's going to
        if node_process.poll() is not None:
            print("❌ Server failed to start immediately. Check server_log.txt.")
            sys.exit(1)
            
    except Exception as e:
        print(f"❌ Failed to launch node: {e}")
        sys.exit(1)

    # 3. Mode Specific Logic
    final_url = ""
    
    try:
        if args.mode == 'local':
            ip = get_local_ip()
            port = os.environ.get('PORT', '3000')
            
            # Detect HTTPS
            protocol = "http"
            if os.path.exists('certs/server.key') and os.path.exists('certs/server.cert'):
                protocol = "https"
            
            final_url = f"{protocol}://{ip}:{port}"
            
            print("\n" + "="*50)
            print(f"📡 LOCAL WIFI ACCESS")
            print("="*50)
            print(f"🔗 URL: {final_url}")
            print(f"🔑 Passcode: Not required for local WiFi (Auto-detected)")
            
            print("\n📱 Scan this QR Code to connect:")
            print_qr(final_url)

            print("-" * 50)
            print("📝 Steps to Connect:")
            print("1. Ensure your phone is on the SAME Wi-Fi network as this computer.")
            print("2. Open your phone's Camera app or a QR scanner.")
            print("3. Scan the code above OR manually type the URL into your browser.")
            print("4. You should be connected automatically!")
            
        elif args.mode == 'web':
            tunnel_type = os.environ.get('TUNNEL_TYPE', 'cloudflare').strip().lower()
            port = os.environ.get('PORT', '3000')
            cf_available = find_cloudflared() is not None
            
            # Detect HTTPS
            protocol = "http"
            if os.path.exists('certs/server.key') and os.path.exists('certs/server.cert'):
                protocol = "https"
                
            addr = f"{protocol}://localhost:{port}"
            public_url = None
            
            # 1. Attempt Cloudflare if requested or if binary is present
            if tunnel_type == 'cloudflare' or (not tunnel_type and cf_available):
                if not cf_available:
                    # Attempt auto-download via the guide function
                    if show_cloudflare_setup_guide():
                        cf_available = True
                
                if cf_available:
                    public_url = get_cloudflare_url(port, protocol)
                
                if not public_url:
                    print("⚠️  Falling back to ngrok...")
                    tunnel_type = 'ngrok'
                    
            # 2. Attempt Ngrok as fallback or primary
            if tunnel_type == 'ngrok':
                # Check Ngrok Token
                token = os.environ.get('NGROK_AUTHTOKEN')
                if token:
                    ngrok.set_auth_token(token)
                else:
                    print("⚠️  Warning: NGROK_AUTHTOKEN not found in .env. Tunnel might expire.")

                print("PLEASE WAIT... Establishing Ngrok Tunnel...")
                tunnel = ngrok.connect(addr, host_header="rewrite")
                public_url = tunnel.public_url

            if not public_url:
                print("❌ Failed to establish any tunnel.")
                sys.exit(1)
            
            # Magic URL with password
            final_url = f"{public_url}?key={passcode}"
            
            print("\n" + "="*50)
            print(f"   🌍 GLOBAL WEB ACCESS")
            print("="*50)
            print(f"🔗 Base URL: {public_url}")
            print(f"🔑 Passcode: {passcode}")
            
            print("\n📱 Scan this Magic QR Code (Auto-Logins):")
            print_qr(final_url)

            print("-" * 50)
            print("📝 Steps to Connect:")
            print("1. Switch your phone to Mobile Data or Turn off Wi-Fi.")
            print("2. Open your phone's Camera app or a QR scanner.")
            print("3. Scan the code above to auto-login.")
            print(f"4. Or visit {public_url}")
            print(f"5. Enter passcode: {passcode}")
            print("6. You should be connected automatically!")

        print("="*50)
        print("✅ Server is running in background. Logs -> server_log.txt")
        print("⌨️  Press Ctrl+C to stop.")
        
        # Keep alive loop
        last_log_pos = 0
        cdp_warning_shown = False

        # Run the debug check once the banner is up
        print("\n[DEBUG] Checking if port 9000 is available for Antigravity Remote Debugging...")
        try:
            listening = False
            if sys.platform == "win32":
                output = subprocess.check_output("netstat -ano | findstr :9000", shell=True).decode()
                if "LISTENING" in output: listening = True
            else:
                output = subprocess.check_output("lsof -i :9000", shell=True).decode()
                if "LISTEN" in output: listening = True
                
            if listening:
                print("✅ Found Antigravity debugging port (9000) actively listening.")
            else:
                print("❌ WARNING: Port 9000 is NOT listening. Antigravity may not be running in debug mode.")
        except:
            print("❌ WARNING: Port 9000 is NOT listening. Antigravity may not be running in debug mode.")
            pass
        print("[DEBUG] Antigravity must be started with: --remote-debugging-port=9000\n")
        
        
        while True:
            time.sleep(1)
            
            # Check process status
            if node_process.poll() is not None:
                print("\n❌ Server process died unexpectedly!")
                sys.exit(1)
                
            # Monitor logs for errors
            try:
                if os.path.exists("server_log.txt"):
                    with open("server_log.txt", "r", encoding='utf-8', errors='ignore') as f:
                        f.seek(last_log_pos)
                        new_lines = f.read().splitlines()
                        last_log_pos = f.tell()
                        
                        for line in new_lines:
                            if "CDP not found" in line and not cdp_warning_shown:
                                print("\n" + "!"*50)
                                print("❌ ERROR: Antigravity Editor Not Detected!")
                                print("!"*50)
                                print("   The server cannot see your editor.")
                                print("   1. Close Antigravity.")
                                print("   2. Re-open it with the debug flag:")
                                print("      antigravity . --remote-debugging-port=9000")
                                print("   3. Or use the 'Open with Antigravity (Debug)' context menu.")
                                print("!"*50 + "\n")
                                cdp_warning_shown = True
            except Exception:
                pass

    except KeyboardInterrupt:
        print("\n\n👋 Shutting down...")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        # Cleanup
        try:
            if node_process:
                node_process.terminate()
                try:
                    node_process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    node_process.kill()
            
            if args.mode == 'web':
                ngrok.kill()
        except:
            pass
        
        if 'log_file' in locals() and log_file:
            log_file.close()
        
        sys.exit(0)

if __name__ == "__main__":
    main()
