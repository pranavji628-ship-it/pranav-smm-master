import os
import time
import threading
import importlib

def run_web_server():
    from bot4_control import app, RENDER_PORT, self_ping_loop
    threading.Thread(target=self_ping_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=RENDER_PORT, use_reloader=False)

def run_isolated_bot(module_name, var_name):
    while True:
        try:
            mod = importlib.import_module(module_name)
            bot_obj = getattr(mod, var_name, None)
            if bot_obj:
                bot_obj.infinity_polling(timeout=10, long_polling_timeout=5, skip_pending=True)
            else:
                break
        except Exception:
            time.sleep(3)

if __name__ == "__main__":
    # Web API चालू करें
    threading.Thread(target=run_web_server, daemon=True).start()

    # सभी 5 बॉट्स को अलग-अलग थ्रेड्स में रन करें
    bots = [
        ("bot1_shop", "bot1"),
        ("bot2_cmd", "bot2"),
        ("bot3_guard", "bot3"),
        ("bot4_control", "bot4"),
        ("bot5_stats", "bot5")
    ]

    for mod, var in bots:
        threading.Thread(target=run_isolated_bot, args=(mod, var), daemon=True).start()
        time.sleep(1)

    while True:
        time.sleep(60)
