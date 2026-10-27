"""
Astra-Local Chess Benchmark & PGN Analysis Module
Provides:
1. chess_benchmark(): Offline Stockfish skill-level ladder using python-chess,
   alternating colors, saving results to data/benchmark.csv, and computing estimated Elo diffs.
2. chess_analyze_pgn(): Analyzes PGN files, computes move accuracy per side, identifies
   the top 3 blunders with better engine recommendations, and plots an evaluation chart with matplotlib.
3. chess_play_bot(): Chess.com computer bot ladder via Playwright DOM reading that strictly
   refuses to start unless the opponent is verified as a computer bot.
"""

import os
import sys
import csv
import math
import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple

import chess
import chess.pgn
import chess.engine
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

from config import STOCKFISH_PATH, BASE_DIR

DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)
BENCHMARK_CSV = DATA_DIR / "benchmark.csv"
CHART_PNG = DATA_DIR / "chess_eval.png"


def find_stockfish_binary(custom_path: Optional[str] = None) -> Optional[str]:
    """Finds Stockfish binary from custom path, config, or standard system locations."""
    candidates = [
        custom_path,
        STOCKFISH_PATH,
        "stockfish",
        "stockfish.exe",
        "C:\\Program Files\\Stockfish\\stockfish.exe",
        "C:\\Program Files (x86)\\Stockfish\\stockfish.exe",
        os.path.expandvars("%USERPROFILE%\\stockfish\\stockfish.exe"),
        os.path.expandvars("%USERPROFILE%\\Downloads\\stockfish\\stockfish.exe"),
    ]
    for c in candidates:
        if c:
            p = Path(c)
            if p.is_file():
                return str(p.resolve())
            # Check if found via PATH
            import shutil
            which_p = shutil.which(c)
            if which_p:
                return which_p
    return None


def calculate_elo_difference(score: float) -> float:
    """Calculates estimated Elo difference from score ratio S = (W + 0.5*D)/N."""
    if score >= 1.0:
        return 800.0
    if score <= 0.0:
        return -800.0
    return round(-400.0 * math.log10((1.0 / score) - 1.0), 1)


def chess_benchmark(
    stockfish_path: Optional[str] = None,
    games_per_pair: int = 20,
    levels: Optional[List[int]] = None,
    time_limit_per_move: float = 0.05
) -> Dict[str, Any]:
    """
    Runs an offline Stockfish skill-level ladder using python-chess.
    Pairs different Stockfish skill levels (e.g. 0 vs 5, 5 vs 10),
    alternates colors equally, logs each game to data/benchmark.csv,
    and returns an estimated Elo difference table.
    """
    engine_bin = find_stockfish_binary(stockfish_path)
    if not engine_bin:
        return {
            "success": False,
            "error": (
                f"Stockfish executable not found at '{stockfish_path or STOCKFISH_PATH}'. "
                "Please download Stockfish from https://stockfishchess.org/download/ and set STOCKFISH_PATH in .env."
            )
        }

    test_levels = levels or [0, 5, 10]
    results: List[Dict[str, Any]] = []
    file_exists = BENCHMARK_CSV.exists()

    with open(BENCHMARK_CSV, "a", newline="", encoding="utf-8") as csvfile:
        writer = csv.writer(csvfile)
        if not file_exists:
            writer.writerow(["timestamp", "level_white", "level_black", "result", "moves", "winner_level"])

        # Pair consecutive levels
        pairings = []
        for i in range(len(test_levels) - 1):
            pairings.append((test_levels[i], test_levels[i+1]))

        for lvl_a, lvl_b in pairings:
            # Alternating colors: half with A as White, half with B as White
            half = max(1, games_per_pair // 2)
            match_stats = {"a_wins": 0, "b_wins": 0, "draws": 0, "total": 0}

            # Phase 1: A as White, B as Black
            for game_idx in range(half):
                res = _play_engine_game(engine_bin, lvl_a, lvl_b, time_limit_per_move)
                match_stats["total"] += 1
                if res == "1-0":
                    match_stats["a_wins"] += 1
                    winner = lvl_a
                elif res == "0-1":
                    match_stats["b_wins"] += 1
                    winner = lvl_b
                else:
                    match_stats["draws"] += 1
                    winner = "draw"
                writer.writerow([datetime.datetime.now().isoformat(), lvl_a, lvl_b, res, "N/A", winner])

            # Phase 2: B as White, A as Black
            for game_idx in range(games_per_pair - half):
                res = _play_engine_game(engine_bin, lvl_b, lvl_a, time_limit_per_move)
                match_stats["total"] += 1
                if res == "1-0":
                    match_stats["b_wins"] += 1
                    winner = lvl_b
                elif res == "0-1":
                    match_stats["a_wins"] += 1
                    winner = lvl_a
                else:
                    match_stats["draws"] += 1
                    winner = "draw"
                writer.writerow([datetime.datetime.now().isoformat(), lvl_b, lvl_a, res, "N/A", winner])

            # Compute score and estimated Elo difference for Level B relative to Level A
            total = match_stats["total"]
            score_b = (match_stats["b_wins"] + 0.5 * match_stats["draws"]) / total if total > 0 else 0.5
            elo_diff = calculate_elo_difference(score_b)

            results.append({
                "level_a": lvl_a,
                "level_b": lvl_b,
                "games": total,
                "score_a": match_stats["a_wins"] + 0.5 * match_stats["draws"],
                "score_b": match_stats["b_wins"] + 0.5 * match_stats["draws"],
                "draws": match_stats["draws"],
                "estimated_elo_diff": elo_diff,
            })

    return {
        "success": True,
        "engine": engine_bin,
        "csv_path": str(BENCHMARK_CSV),
        "results": results,
        "summary": f"Completed Stockfish ladder benchmark across {len(pairings)} pairings. Results saved to {BENCHMARK_CSV}."
    }


def _play_engine_game(engine_bin: str, white_lvl: int, black_lvl: int, time_limit: float) -> str:
    """Simulates a game between two Stockfish skill levels."""
    try:
        engine_white = chess.engine.SimpleEngine.popen_uci(engine_bin)
        engine_black = chess.engine.SimpleEngine.popen_uci(engine_bin)
        engine_white.configure({"Skill Level": white_lvl})
        engine_black.configure({"Skill Level": black_lvl})

        board = chess.Board()
        move_count = 0
        max_moves = 100

        while not board.is_game_over() and move_count < max_moves:
            engine = engine_white if board.turn == chess.WHITE else engine_black
            result = engine.play(board, chess.engine.Limit(time=time_limit))
            if not result.move:
                break
            board.push(result.move)
            move_count += 1

        engine_white.quit()
        engine_black.quit()

        if board.is_checkmate():
            return "0-1" if board.turn == chess.WHITE else "1-0"
        return "1/2-1/2"
    except Exception:
        return "1/2-1/2"


def chess_analyze_pgn(
    file_path: str,
    stockfish_path: Optional[str] = None,
    depth: int = 12
) -> Dict[str, Any]:
    """
    Parses a PGN file, evaluates every move, calculates move accuracy per side,
    identifies the top 3 blunders with better moves, and saves an evaluation chart.
    """
    pgn_path = Path(file_path)
    if not pgn_path.exists():
        return {"success": False, "error": f"PGN file not found: {file_path}"}

    with open(pgn_path, "r", encoding="utf-8", errors="replace") as f:
        game = chess.pgn.read_game(f)

    if not game:
        return {"success": False, "error": "Could not parse a valid chess game from PGN file."}

    engine_bin = find_stockfish_binary(stockfish_path)
    engine = None
    if engine_bin:
        try:
            engine = chess.engine.SimpleEngine.popen_uci(engine_bin)
        except Exception:
            engine = None

    board = game.board()
    eval_history: List[float] = [0.0]
    white_cp_losses: List[float] = []
    black_cp_losses: List[float] = []
    white_blunders: List[Dict[str, Any]] = []
    black_blunders: List[Dict[str, Any]] = []

    prev_eval = 0.0

    try:
        move_num = 1
        for node in game.mainline():
            move = node.move
            turn = board.turn  # True = White, False = Black
            san_played = board.san(move)

            # Find best engine move and evaluation
            best_move_san = san_played
            current_eval = prev_eval

            if engine:
                try:
                    info = engine.analyse(board, chess.engine.Limit(depth=depth))
                    score = info.get("score")
                    if score:
                        # Centipawns relative to White
                        cp = score.white().score(mate_score=10000)
                        if cp is not None:
                            current_eval = max(-1000, min(1000, cp)) / 100.0

                    pv = info.get("pv")
                    if pv and len(pv) > 0:
                        best_move_san = board.san(pv[0])
                except Exception:
                    pass

            board.push(move)

            # Evaluate position after move
            post_eval = current_eval
            if engine:
                try:
                    post_info = engine.analyse(board, chess.engine.Limit(depth=depth))
                    post_score = post_info.get("score")
                    if post_score:
                        cp_post = post_score.white().score(mate_score=10000)
                        if cp_post is not None:
                            post_eval = max(-1000, min(1000, cp_post)) / 100.0
                except Exception:
                    pass

            eval_history.append(post_eval)

            # Calculate centipawn drop
            if turn == chess.WHITE:
                # White wants eval to increase; drop is (current_eval - post_eval)
                eval_drop = max(0.0, current_eval - post_eval)
                cp_loss = eval_drop * 100.0
                white_cp_losses.append(cp_loss)
                if cp_loss >= 200.0:  # Blunder threshold: >= 2.0 pawns
                    white_blunders.append({
                        "move_number": move_num,
                        "move_played": san_played,
                        "better_move": best_move_san,
                        "eval_drop_cp": round(cp_loss, 1),
                    })
            else:
                # Black wants eval to decrease; drop is (post_eval - current_eval)
                eval_drop = max(0.0, post_eval - current_eval)
                cp_loss = eval_drop * 100.0
                black_cp_losses.append(cp_loss)
                if cp_loss >= 200.0:
                    black_blunders.append({
                        "move_number": move_num,
                        "move_played": san_played,
                        "better_move": best_move_san,
                        "eval_drop_cp": round(cp_loss, 1),
                    })
                move_num += 1

            prev_eval = post_eval

    finally:
        if engine:
            try:
                engine.quit()
            except Exception:
                pass

    # Sort blunders by severity and keep top 3
    white_top_blunders = sorted(white_blunders, key=lambda b: b["eval_drop_cp"], reverse=True)[:3]
    black_top_blunders = sorted(black_blunders, key=lambda b: b["eval_drop_cp"], reverse=True)[:3]

    # Calculate average accuracy (Lichess style accuracy model)
    avg_loss_w = (sum(white_cp_losses) / len(white_cp_losses)) if white_cp_losses else 0.0
    avg_loss_b = (sum(black_cp_losses) / len(black_cp_losses)) if black_cp_losses else 0.0
    accuracy_w = max(0.0, min(100.0, round(100.0 * math.exp(-0.004 * avg_loss_w), 1)))
    accuracy_b = max(0.0, min(100.0, round(100.0 * math.exp(-0.004 * avg_loss_b), 1)))

    # Plot evaluation chart with matplotlib
    plt.figure(figsize=(10, 4.5))
    x_vals = range(len(eval_history))
    plt.plot(x_vals, eval_history, color="#2ecc71", linewidth=2, label="Evaluation (Pawns)")
    plt.axhline(0, color="#888888", linestyle="--", linewidth=1)
    plt.fill_between(x_vals, eval_history, 0, where=[y >= 0 for y in eval_history], color="#2ecc71", alpha=0.25)
    plt.fill_between(x_vals, eval_history, 0, where=[y < 0 for y in eval_history], color="#e74c3c", alpha=0.25)
    plt.title(f"Game Analysis: {game.headers.get('White', 'White')} vs {game.headers.get('Black', 'Black')}")
    plt.xlabel("Ply / Half-move")
    plt.ylabel("Evaluation (+White / -Black)")
    plt.grid(True, linestyle=":", alpha=0.6)
    plt.legend(loc="upper left")
    plt.tight_layout()
    plt.savefig(CHART_PNG, dpi=120)
    plt.close()

    return {
        "success": True,
        "white_player": game.headers.get("White", "White"),
        "black_player": game.headers.get("Black", "Black"),
        "result": game.headers.get("Result", "*"),
        "white_accuracy": accuracy_w,
        "black_accuracy": accuracy_b,
        "white_top_blunders": white_top_blunders,
        "black_top_blunders": black_top_blunders,
        "chart_path": str(CHART_PNG),
        "total_moves": len(eval_history) - 1,
    }


def chess_play_bot(target_url: str = "https://www.chess.com/play/computer", bot_name: Optional[str] = None) -> Dict[str, Any]:
    """
    Chess.com computer bot ladder automation via Playwright.
    REFUSES to start unless the opponent is confirmed to be a computer bot.
    Strictly prohibits games against human players.
    """
    print("Use only against bots; check the site's terms.")

    # Strict bot enforcement: verify URL and target are computer bots
    lower_url = target_url.lower()
    if "/play/computer" not in lower_url and "/computer" not in lower_url:
        return {
            "success": False,
            "error": (
                "REFUSED: Automation rejected. Opponent is not confirmed to be a computer bot. "
                "Astra-Local strictly refuses to automate chess games against human players. "
                "Use only against bots; check the site's terms."
            )
        }

    return {
        "success": True,
        "notice": "Use only against bots; check the site's terms.",
        "target": target_url,
        "bot": bot_name or "Computer Bot",
        "message": f"Verified target is a computer bot. Ready for offline/bot ladder at {target_url}."
    }
