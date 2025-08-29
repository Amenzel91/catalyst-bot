# tools/run_once.py
import os
import queue
import signal
import subprocess
import sys
import threading
import time

from dotenv import load_dotenv


def _reader_thread(pipe, outq):
    for line in iter(pipe.readline, ""):
        outq.put(line)
    pipe.close()


def main():
    # Load .env so the child inherits FINVIZ_AUTH_TOKEN, TICKERS_DB_PATH, etc.
    load_dotenv(dotenv_path=".env", override=False)

    env = os.environ.copy()
    env.setdefault("PYTHONUNBUFFERED", "1")

    cmd = [sys.executable, "-u", "-m", "catalyst_bot.runner", "--loop"]
    print(f"run_once: starting child: {cmd}", flush=True)

    # New process group so we can send CTRL_BREAK_EVENT on Windows
    flags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    p = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,  # line-buffered
        env=env,
        creationflags=flags,
    )

    q: "queue.Queue[str]" = queue.Queue()
    t = threading.Thread(target=_reader_thread, args=(p.stdout, q), daemon=True)
    t.start()

    last_output = time.time()

    try:
        while True:
            try:
                line = q.get(timeout=1.0)
                print(line, end="")
                last_output = time.time()

                if "CYCLE_DONE" in line:
                    print("run_once: got CYCLE_DONE; stopping child...", flush=True)
                    try:
                        if os.name == "nt":
                            p.send_signal(signal.CTRL_BREAK_EVENT)
                        else:
                            p.terminate()
                        p.wait(5)
                    except Exception:
                        p.kill()
                    break

            except queue.Empty:
                # No new output this second.
                if p.poll() is not None:
                    # Child exited; drain remaining lines if any
                    while not q.empty():
                        line = q.get_nowait()
                        print(line, end="")
                    break

                # Periodic heartbeat so you know it's alive
                if time.time() - last_output > 5:
                    print("run_once: still waiting for output...", flush=True)
                    last_output = time.time()

        rc = p.wait()
        print(f"run_once: done (rc={rc})", flush=True)
        sys.exit(0 if rc == 0 else rc)

    except KeyboardInterrupt:
        print("\nrun_once: CTRL+C received; stopping child...", flush=True)
        try:
            if os.name == "nt":
                p.send_signal(signal.CTRL_BREAK_EVENT)
            else:
                p.terminate()
            p.wait(5)
        except Exception:
            p.kill()
        print(f"run_once: done (reason=ctrl_c, child_rc={p.returncode})", flush=True)


if __name__ == "__main__":
    main()
