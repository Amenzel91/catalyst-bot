import os, sys, subprocess, signal, time
from dotenv import load_dotenv

load_dotenv()  # load .env here

CREATE_NEW_PROCESS_GROUP = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0x00000200)

def main(timeout=60):
    cmd=[sys.executable, "-m", "catalyst_bot.runner", "--loop"]
    p=subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
        encoding="utf-8", errors="replace",
        env=os.environ.copy(),
        creationflags=CREATE_NEW_PROCESS_GROUP
    )
    try:
        deadline = time.time() + timeout
        for line in p.stdout:
            print(line, end="")
            if "CYCLE_DONE" in line or time.time() > deadline:
                break
    except KeyboardInterrupt:
        print("\nrun_once: CTRL+C -> stopping child...", file=sys.stderr)
    finally:
        try:
            if sys.platform.startswith("win"):
                p.send_signal(signal.CTRL_BREAK_EVENT)
        except Exception:
            pass
        try: p.terminate()
        except Exception: pass
        try: p.wait(5)
        except Exception: p.kill()
    return 0

if __name__ == "__main__":
    raise SystemExit(main(int(os.environ.get("RUN_ONCE_TIMEOUT", "60"))))
