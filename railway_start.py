# railway_start.py
import subprocess
import sys
import os
import signal
import time

def main():
    print("🚀 Starting Nightflow on Railway...")
    
    # Start the bot
    bot_process = subprocess.Popen(
        [sys.executable, "bot/main.py"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    print(f"✅ Bot started (PID: {bot_process.pid})")
    
    # Start the web server
    web_process = subprocess.Popen(
        ["gunicorn", "api.app:app", "--bind", "0.0.0.0:8080", "--access-logfile", "-"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True
    )
    print(f"✅ Web server started (PID: {web_process.pid})")
    
    # Print output from both processes
    while True:
        # Check if processes are still running
        if bot_process.poll() is not None:
            print(f"❌ Bot process died with code {bot_process.returncode}")
            break
        if web_process.poll() is not None:
            print(f"❌ Web process died with code {web_process.returncode}")
            break
            
        # Read and print output
        bot_output = bot_process.stdout.readline()
        if bot_output:
            print(f"[BOT] {bot_output.strip()}")
            
        web_output = web_process.stdout.readline()
        if web_output:
            print(f"[WEB] {web_output.strip()}")
            
        time.sleep(0.1)
    
    # If we get here, something died
    bot_process.terminate()
    web_process.terminate()
    sys.exit(1)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n🛑 Shutting down...")
        sys.exit(0)