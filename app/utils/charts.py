import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from pathlib import Path

# ВАЖНО: не задаем цвета/стили — универсальные требования

def save_chart(df, out_dir: str, title: str) -> str | None:
    if df is None or df.empty:
        return None
    p = Path(out_dir)
    p.mkdir(parents=True, exist_ok=True)
    out_path = p / f"{title.replace('/', '_').replace(' ', '_')}.png"

    plt.figure()
    df["close"].plot()
    if "ema50" in df.columns:
        df["ema50"].plot()
    if {"bb_low", "bb_high"}.issubset(df.columns):
        df["bb_low"].plot()
        df["bb_high"].plot()
    plt.title(title)
    plt.xlabel("time")
    plt.ylabel("price")
    plt.tight_layout()
    plt.savefig(out_path)
    plt.close()
    return str(out_path)
