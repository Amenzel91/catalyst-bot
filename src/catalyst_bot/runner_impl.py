import os, sys, subprocess

def run_once():
    # Spawn normal loop, capture output, stop at first CYCLE_DONE
    cmd=[sys.executable, "-m", "catalyst_bot.runner", "--loop"]
    env=os.environ.copy()
    p=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, env=env)
    for line in p.stdout:
        print(line, end="")
        if "CYCLE_DONE" in line:
            p.terminate()
            try: p.wait(3)
            except Exception: p.kill()
            return 0
    return p.wait()