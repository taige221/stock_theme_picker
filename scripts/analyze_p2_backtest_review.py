# -*- coding: utf-8 -*-
"""Generate P2 diagnostics for A-share box backtest artifacts."""

from __future__ import annotations

import argparse
import csv
import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import median
from typing import Any, Iterable


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SUMMARY = ROOT_DIR / "data/backtests/batch_20260528-182416/summary.json"
SIGNALS = ("breakout_long", "pullback_bounce")
MFE_THRESHOLDS = (3.0, 5.0, 8.0, 10.0)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate P2 backtest review report")
    parser.add_argument(
        "--summary",
        default=str(DEFAULT_SUMMARY),
        help="Batch summary.json path. Defaults to data/backtests/batch_20260528-182416/summary.json.",
    )
    parser.add_argument(
        "--output-dir",
        help="Output diagnostics directory. Defaults to data/backtests/diagnostics/p2_review_<timestamp>.",
    )
    parser.add_argument(
        "--short-loss-days",
        type=int,
        default=3,
        help="Holding days threshold for short-loss review. Default 3.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary_path = _resolve_path(args.summary)
    summary = _load_json(summary_path)
    output_dir = (
        _resolve_path(args.output_dir)
        if args.output_dir
        else ROOT_DIR / "data/backtests/diagnostics" / f"p2_review_{datetime.now():%Y%m%d-%H%M%S}"
    )
    output_dir.mkdir(parents=True, exist_ok=True)

    symbol_rows, trades, missing_paths = _load_batch(summary, summary_path)
    review = build_review(
        summary=summary,
        summary_path=summary_path,
        symbol_rows=symbol_rows,
        trades=trades,
        missing_paths=missing_paths,
        short_loss_days=max(0, args.short_loss_days),
    )

    _write_json(output_dir / "p2_review_summary.json", review)
    (output_dir / "p2_review_report.md").write_text(render_markdown(review), encoding="utf-8")
    _write_csv(output_dir / "trades_flat.csv", review["exports"]["trades_flat"])
    _write_csv(output_dir / "short_losses.csv", review["exports"]["short_losses"])
    _write_csv(output_dir / "giveback_trades.csv", review["exports"]["giveback_trades"])
    _write_csv(output_dir / "symbol_rank.csv", review["symbol_rank"]["rows"])

    print(f"saved_summary={output_dir / 'p2_review_summary.json'}")
    print(f"saved_report={output_dir / 'p2_review_report.md'}")
    print(f"saved_trades_csv={output_dir / 'trades_flat.csv'}")
    print(f"saved_short_losses_csv={output_dir / 'short_losses.csv'}")
    print(f"saved_giveback_trades_csv={output_dir / 'giveback_trades.csv'}")
    print(f"saved_symbol_rank_csv={output_dir / 'symbol_rank.csv'}")
    return 0


def build_review(
    *,
    summary: dict[str, Any],
    summary_path: Path,
    symbol_rows: list[dict[str, Any]],
    trades: list[dict[str, Any]],
    missing_paths: list[str],
    short_loss_days: int,
) -> dict[str, Any]:
    trades_flat = [_flatten_trade(t) for t in trades]
    short_losses = [t for t in trades_flat if t["holding_days"] <= short_loss_days and t["return_pct"] < 0]
    giveback_trades = [
        t for t in trades_flat if t["max_favorable_excursion_pct"] >= 3 and t["return_pct"] < 1.5
    ]

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "run_context": {
            "summary_path": str(summary_path),
            "strategy": summary.get("strategy"),
            "price_adjustment": summary.get("price_adjustment"),
            "trading_constraints": summary.get("trading_constraints"),
            "start_date": summary.get("start_date"),
            "end_date": summary.get("end_date"),
            "config": summary.get("config") or {},
            "missing_result_paths": missing_paths,
        },
        "aggregate": summary.get("aggregate") or {},
        "overall": _stats(trades_flat),
        "by_signal": _group_stats(trades_flat, ["signal_type"], keep=SIGNALS),
        "by_signal_exit": _group_stats(trades_flat, ["signal_type", "exit_reason"], keep_signal=SIGNALS),
        "by_signal_holding_bucket": _group_stats(
            trades_flat, ["signal_type", "holding_bucket"], keep_signal=SIGNALS
        ),
        "by_signal_year": _group_stats(trades_flat, ["signal_type", "entry_year"], keep_signal=SIGNALS),
        "score_buckets": _group_stats(trades_flat, ["signal_type", "score_bucket"], keep_signal=SIGNALS),
        "metadata_buckets": {
            "turnover_rate": _group_stats(
                _with_bucket(trades_flat, "turnover_rate", [(0, 3), (3, 6), (6, 10), (10, 15), (15, None)]),
                ["signal_type", "turnover_rate_bucket"],
                keep_signal=SIGNALS,
            ),
            "volume_ratio": _group_stats(
                _with_bucket(trades_flat, "volume_ratio", [(0, 1.5), (1.5, 2), (2, 3), (3, 5), (5, None)]),
                ["signal_type", "volume_ratio_bucket"],
                keep_signal=SIGNALS,
            ),
            "box_height_pct": _group_stats(
                _with_bucket(trades_flat, "box_height_pct", [(0, 10), (10, 20), (20, 30), (30, 50), (50, None)]),
                ["signal_type", "box_height_pct_bucket"],
                keep_signal=SIGNALS,
            ),
        },
        "short_loss_analysis": _short_loss_analysis(trades_flat, short_losses, short_loss_days),
        "giveback_analysis": _giveback_analysis(trades_flat),
        "winner_profile": _winner_profile(trades_flat),
        "symbol_rank": _symbol_rank(symbol_rows, trades_flat),
        "recommendations": _recommendations(trades_flat, short_losses),
        "exports": {
            "trades_flat": trades_flat,
            "short_losses": short_losses,
            "giveback_trades": giveback_trades,
        },
    }


def _resolve_path(raw_path: str | Path) -> Path:
    path = Path(raw_path)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path}")
    return payload


def _load_batch(
    summary: dict[str, Any], summary_path: Path
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
    symbol_rows: list[dict[str, Any]] = []
    trades: list[dict[str, Any]] = []
    missing_paths: list[str] = []
    for row in summary.get("results") or []:
        if not isinstance(row, dict):
            continue
        symbol_rows.append(row)
        if row.get("status") != "ok":
            continue
        result_path = str(row.get("result_path") or "").strip()
        if not result_path:
            continue
        path = Path(result_path)
        if not path.is_absolute():
            path = summary_path.parent / path
        if not path.is_file():
            missing_paths.append(result_path)
            continue
        detail = _load_json(path)
        for trade in detail.get("trades") or []:
            if isinstance(trade, dict):
                enriched = dict(trade)
                enriched["_detail_path"] = str(path)
                trades.append(enriched)
    return symbol_rows, trades, missing_paths


def _flatten_trade(trade: dict[str, Any]) -> dict[str, Any]:
    metadata = trade.get("entry_signal_metadata") or {}
    signal_type = str(metadata.get("signal_type") or trade.get("entry_signal_reason") or "")
    entry_date = str(trade.get("entry_date") or "")
    return {
        "stock_code": str(trade.get("stock_code") or ""),
        "entry_date": entry_date,
        "exit_date": str(trade.get("exit_date") or ""),
        "entry_year": entry_date[:4] if len(entry_date) >= 4 else "",
        "signal_type": signal_type,
        "exit_reason": str(trade.get("exit_reason") or ""),
        "entry_signal_score": _num(trade.get("entry_signal_score")),
        "score_bucket": _score_bucket(_num(trade.get("entry_signal_score"))),
        "return_pct": _num(trade.get("return_pct")),
        "net_pnl": _num(trade.get("net_pnl")),
        "total_cost": _num(trade.get("total_cost")),
        "holding_days": int(_num(trade.get("holding_days"))),
        "holding_bucket": _holding_bucket(int(_num(trade.get("holding_days")))),
        "max_favorable_excursion_pct": _num(trade.get("max_favorable_excursion_pct")),
        "max_adverse_excursion_pct": _num(trade.get("max_adverse_excursion_pct")),
        "turnover_rate": _num(metadata.get("turnover_rate")),
        "volume_ratio": _num(metadata.get("volume_ratio")),
        "box_height_pct": _num(metadata.get("box_height_pct")),
        "signal_number": _num(metadata.get("signal_number")),
        "quality_score": _num(metadata.get("quality_score")),
        "macd_state": str(metadata.get("macd_state") or ""),
        "macd_hist": _num(metadata.get("macd_hist")),
        "macd_hist_slope_3": _num(metadata.get("macd_hist_slope_3")),
        "macd_divergence_detected": bool(metadata.get("macd_divergence_detected")),
        "macd_divergence_price_confirms": bool(metadata.get("macd_divergence_price_confirms")),
        "breakout_macd_bearish_divergence": bool(metadata.get("breakout_macd_bearish_divergence")),
        "pullback_macd_bullish_divergence": bool(metadata.get("pullback_macd_bullish_divergence")),
        "resistance_touches": _num(metadata.get("resistance_touches")),
        "support_touches": _num(metadata.get("support_touches")),
        "detail_path": str(trade.get("_detail_path") or ""),
    }


def _stats(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {
            "count": 0,
            "win_rate_pct": 0.0,
            "avg_return_pct": 0.0,
            "median_return_pct": 0.0,
            "net_pnl": 0.0,
            "total_cost": 0.0,
            "avg_holding_days": 0.0,
            "avg_mfe_pct": 0.0,
            "avg_mae_pct": 0.0,
            "stop_count": 0,
            "take_profit_count": 0,
        }
    returns = [r["return_pct"] for r in rows]
    return {
        "count": len(rows),
        "win_rate_pct": _round(100 * sum(1 for r in rows if r["return_pct"] > 0) / len(rows)),
        "avg_return_pct": _round(sum(returns) / len(returns)),
        "median_return_pct": _round(median(returns)),
        "net_pnl": _round(sum(r["net_pnl"] for r in rows), 2),
        "total_cost": _round(sum(r["total_cost"] for r in rows), 2),
        "avg_holding_days": _round(sum(r["holding_days"] for r in rows) / len(rows)),
        "avg_mfe_pct": _round(sum(r["max_favorable_excursion_pct"] for r in rows) / len(rows)),
        "avg_mae_pct": _round(sum(r["max_adverse_excursion_pct"] for r in rows) / len(rows)),
        "stop_count": sum(1 for r in rows if r["exit_reason"] == "stop_loss_hit"),
        "take_profit_count": sum(1 for r in rows if r["exit_reason"] == "take_profit_hit"),
    }


def _group_stats(
    rows: list[dict[str, Any]],
    fields: list[str],
    *,
    keep: Iterable[str] | None = None,
    keep_signal: Iterable[str] | None = None,
) -> list[dict[str, Any]]:
    keep_set = set(keep or [])
    keep_signal_set = set(keep_signal or [])
    groups: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        if keep_set and row.get(fields[0]) not in keep_set:
            continue
        if keep_signal_set and row.get("signal_type") not in keep_signal_set:
            continue
        key = tuple(row.get(field) for field in fields)
        groups[key].append(row)
    result: list[dict[str, Any]] = []
    for key, group_rows in groups.items():
        item = {field: value for field, value in zip(fields, key)}
        item.update(_stats(group_rows))
        result.append(item)
    return sorted(result, key=lambda x: tuple(_sort_value(field, x.get(field)) for field in fields))


def _with_bucket(
    rows: list[dict[str, Any]], field: str, ranges: list[tuple[float, float | None]]
) -> list[dict[str, Any]]:
    bucket_field = f"{field}_bucket"
    result = []
    for row in rows:
        new_row = dict(row)
        new_row[bucket_field] = _range_bucket(row.get(field), ranges)
        result.append(new_row)
    return result


def _short_loss_analysis(
    rows: list[dict[str, Any]], short_losses: list[dict[str, Any]], short_loss_days: int
) -> dict[str, Any]:
    by_signal = _group_stats(short_losses, ["signal_type"], keep=SIGNALS)
    return {
        "definition": f"holding_days <= {short_loss_days} and return_pct < 0",
        "overall": _stats(short_losses),
        "by_signal": by_signal,
        "by_signal_exit": _group_stats(short_losses, ["signal_type", "exit_reason"], keep_signal=SIGNALS),
        "no_favorable_excursion_by_signal": _group_stats(
            [r for r in short_losses if r["max_favorable_excursion_pct"] <= 0.5],
            ["signal_type"],
            keep=SIGNALS,
        ),
        "gave_back_after_mfe_3_by_signal": _group_stats(
            [r for r in short_losses if r["max_favorable_excursion_pct"] >= 3],
            ["signal_type"],
            keep=SIGNALS,
        ),
        "metadata_buckets": {
            "turnover_rate": _group_stats(
                _with_bucket(short_losses, "turnover_rate", [(0, 3), (3, 6), (6, 10), (10, 15), (15, None)]),
                ["signal_type", "turnover_rate_bucket"],
                keep_signal=SIGNALS,
            ),
            "volume_ratio": _group_stats(
                _with_bucket(short_losses, "volume_ratio", [(0, 1.5), (1.5, 2), (2, 3), (3, 5), (5, None)]),
                ["signal_type", "volume_ratio_bucket"],
                keep_signal=SIGNALS,
            ),
            "box_height_pct": _group_stats(
                _with_bucket(short_losses, "box_height_pct", [(0, 10), (10, 20), (20, 30), (30, 50), (50, None)]),
                ["signal_type", "box_height_pct_bucket"],
                keep_signal=SIGNALS,
            ),
        },
    }


def _giveback_analysis(rows: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for threshold in MFE_THRESHOLDS:
        key = f"mfe_gte_{int(threshold)}"
        selected = [r for r in rows if r["max_favorable_excursion_pct"] >= threshold]
        weak_exit = [r for r in selected if r["return_pct"] < threshold / 2]
        result[key] = {
            "threshold_pct": threshold,
            "overall": _stats(selected),
            "negative_or_small_gain": _stats(weak_exit),
            "negative_count": sum(1 for r in selected if r["return_pct"] < 0),
            "small_gain_count": sum(1 for r in selected if 0 <= r["return_pct"] < threshold / 2),
            "by_signal": _group_stats(selected, ["signal_type"], keep=SIGNALS),
            "weak_exit_by_signal_exit": _group_stats(
                weak_exit,
                ["signal_type", "exit_reason"],
                keep_signal=SIGNALS,
            ),
        }
    return result


def _winner_profile(rows: list[dict[str, Any]]) -> dict[str, Any]:
    winners = [r for r in rows if r["return_pct"] > 0]
    big_winners = [r for r in rows if r["return_pct"] >= 8]
    return {
        "winners_by_signal": _group_stats(winners, ["signal_type"], keep=SIGNALS),
        "big_winners_by_signal": _group_stats(big_winners, ["signal_type"], keep=SIGNALS),
        "big_winners_exit": _group_stats(big_winners, ["signal_type", "exit_reason"], keep_signal=SIGNALS),
        "big_winners_turnover": _group_stats(
            _with_bucket(big_winners, "turnover_rate", [(0, 3), (3, 6), (6, 10), (10, 15), (15, None)]),
            ["signal_type", "turnover_rate_bucket"],
            keep_signal=SIGNALS,
        ),
        "big_winners_volume": _group_stats(
            _with_bucket(big_winners, "volume_ratio", [(0, 1.5), (1.5, 2), (2, 3), (3, 5), (5, None)]),
            ["signal_type", "volume_ratio_bucket"],
            keep_signal=SIGNALS,
        ),
        "big_winners_box_height": _group_stats(
            _with_bucket(big_winners, "box_height_pct", [(0, 10), (10, 20), (20, 30), (30, 50), (50, None)]),
            ["signal_type", "box_height_pct_bucket"],
            keep_signal=SIGNALS,
        ),
    }


def _symbol_rank(symbol_rows: list[dict[str, Any]], trades: list[dict[str, Any]]) -> dict[str, Any]:
    trade_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for trade in trades:
        trade_groups[trade["stock_code"]].append(trade)
    rows = []
    for row in symbol_rows:
        code = str(row.get("stock_code") or "")
        symbol_trades = trade_groups.get(code, [])
        rows.append(
            {
                "stock_code": code,
                "status": row.get("status"),
                "total_return_pct": _num(row.get("total_return_pct")),
                "trade_count": int(_num(row.get("trade_count"))),
                "win_rate_pct": _num(row.get("win_rate_pct")),
                "net_pnl": _round(sum(t["net_pnl"] for t in symbol_trades), 2),
                "avg_return_pct": _stats(symbol_trades)["avg_return_pct"] if symbol_trades else 0.0,
                "max_consecutive_losses": int(_num(row.get("max_consecutive_losses"))),
                "cost_return_drag_pct": _num(row.get("cost_return_drag_pct")),
            }
        )
    ranked = sorted(rows, key=lambda r: r["total_return_pct"], reverse=True)
    return {
        "rows": rows,
        "top_symbols": ranked[:15],
        "bottom_symbols": ranked[-15:][::-1],
        "high_trade_losers": sorted(
            [r for r in rows if r["trade_count"] >= 5 and r["total_return_pct"] < 0],
            key=lambda r: (r["total_return_pct"], -r["trade_count"]),
        )[:15],
    }


def _recommendations(rows: list[dict[str, Any]], short_losses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    recs: list[dict[str, Any]] = []
    by_signal = {r["signal_type"]: r for r in _group_stats(rows, ["signal_type"], keep=SIGNALS)}
    short_by_signal = {r["signal_type"]: r for r in _group_stats(short_losses, ["signal_type"], keep=SIGNALS)}
    giveback_5 = [r for r in rows if r["max_favorable_excursion_pct"] >= 5 and r["return_pct"] < 2.5]
    high_turnover = [r for r in rows if r["turnover_rate"] >= 15]
    breakout_stats = by_signal.get("breakout_long", {})
    breakout_short = short_by_signal.get("breakout_long", {})
    pullback_stats = by_signal.get("pullback_bounce", {})
    pullback_short = short_by_signal.get("pullback_bounce", {})
    pullback_no_float = [
        r
        for r in short_losses
        if r["signal_type"] == "pullback_bounce" and r["max_favorable_excursion_pct"] < 1
    ]
    breakout_giveback_5 = [
        r
        for r in rows
        if r["signal_type"] == "breakout_long"
        and r["max_favorable_excursion_pct"] >= 5
        and r["return_pct"] < 0
    ]
    pullback_giveback_3 = [
        r
        for r in rows
        if r["signal_type"] == "pullback_bounce"
        and r["max_favorable_excursion_pct"] >= 3
        and r["return_pct"] < 0
    ]
    recs.append(
        {
            "scope": "breakout_long",
            "finding": (
                f"breakout_long 总交易 {breakout_stats.get('count', 0)} 笔，"
                f"0-3d 短亏 {breakout_short.get('count', 0)} 笔，"
                f"短亏净损益 {breakout_short.get('net_pnl', 0)}；"
                f"MFE>=5 后仍亏损 {len(breakout_giveback_5)} 笔。"
            ),
            "next_experiment": (
                "优先测试突破追高过滤和利润保护：ma10_bias_pct>10 且 pct_chg>8 降权/拒绝，"
                "turnover_rate>15 拒绝，box_height_pct>50 拒绝；MFE>=5 启动保本，MFE>=8 启动 trailing。"
            ),
        }
    )
    recs.append(
        {
            "scope": "pullback_bounce",
            "finding": (
                f"pullback_bounce 总交易 {pullback_stats.get('count', 0)} 笔，"
                f"0-3d 短亏 {pullback_short.get('count', 0)} 笔，"
                f"短亏净损益 {pullback_short.get('net_pnl', 0)}；"
                f"短亏中 MFE<1 的无有效浮盈失败 {len(pullback_no_float)} 笔，"
                f"MFE>=3 后仍亏损 {len(pullback_giveback_3)} 笔。"
            ),
            "next_experiment": (
                "优先测试 pullback 专属确认：入场后 1-2 天 MFE<1 且收盘弱于关键位提前走；"
                "MFE>=3 后启用保本；turnover_rate 6-15 保留，0-3 降权，15+ 降权/过滤，volume_ratio>5 降权。"
            ),
        }
    )
    recs.append(
        {
            "scope": "profit_giveback",
            "finding": f"MFE>=5 后最终收益低于 2.5% 的交易 {len(giveback_5)} 笔。",
            "next_experiment": "单独测试保本止损与更低激活阈值 trailing，按 breakout/pullback 分开设参数。",
        }
    )
    recs.append(
        {
            "scope": "turnover_rate",
            "finding": f"换手率>=15% 的交易 {len(high_turnover)} 笔，胜率/收益见 metadata_buckets。",
            "next_experiment": "优先做高换手硬过滤或降权的 A/B，不与其它参数同时变动。",
        }
    )
    return recs


def render_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# P2 回测复盘报告",
        "",
        "## 运行信息",
        f"- summary: `{review['run_context']['summary_path']}`",
        f"- strategy: `{review['run_context'].get('strategy')}`",
        f"- range: `{review['run_context'].get('start_date')}` ~ `{review['run_context'].get('end_date')}`",
        f"- trades: `{review['overall']['count']}`",
        "",
        "## 总览",
        _stat_line(review["overall"]),
        "",
        "## By Signal",
        _table(review["by_signal"], ["signal_type", "count", "win_rate_pct", "avg_return_pct", "median_return_pct", "net_pnl", "avg_mfe_pct", "avg_mae_pct"]),
        "",
        "## Signal x Exit",
        _table(review["by_signal_exit"], ["signal_type", "exit_reason", "count", "win_rate_pct", "avg_return_pct", "net_pnl", "avg_holding_days"]),
        "",
        "## Holding Bucket",
        _table(review["by_signal_holding_bucket"], ["signal_type", "holding_bucket", "count", "win_rate_pct", "avg_return_pct", "net_pnl"]),
        "",
        "## Year",
        _table(review["by_signal_year"], ["signal_type", "entry_year", "count", "win_rate_pct", "avg_return_pct", "net_pnl"]),
        "",
        "## Score Bucket",
        _table(review["score_buckets"], ["signal_type", "score_bucket", "count", "win_rate_pct", "avg_return_pct", "net_pnl"]),
        "",
        "## Metadata Buckets",
        "### Turnover Rate",
        _table(review["metadata_buckets"]["turnover_rate"], ["signal_type", "turnover_rate_bucket", "count", "win_rate_pct", "avg_return_pct", "net_pnl"]),
        "",
        "### Volume Ratio",
        _table(review["metadata_buckets"]["volume_ratio"], ["signal_type", "volume_ratio_bucket", "count", "win_rate_pct", "avg_return_pct", "net_pnl"]),
        "",
        "### Box Height Pct",
        _table(review["metadata_buckets"]["box_height_pct"], ["signal_type", "box_height_pct_bucket", "count", "win_rate_pct", "avg_return_pct", "net_pnl"]),
        "",
        "## 0-3d 短亏",
        f"- definition: `{review['short_loss_analysis']['definition']}`",
        _stat_line(review["short_loss_analysis"]["overall"]),
        "",
        "### 短亏 By Signal",
        _table(review["short_loss_analysis"]["by_signal"], ["signal_type", "count", "win_rate_pct", "avg_return_pct", "net_pnl", "avg_mfe_pct", "avg_mae_pct"]),
        "",
        "### 短亏 Signal x Exit",
        _table(review["short_loss_analysis"]["by_signal_exit"], ["signal_type", "exit_reason", "count", "avg_return_pct", "net_pnl", "avg_mfe_pct", "avg_mae_pct"]),
        "",
        "### 短亏但无有效浮盈",
        _table(review["short_loss_analysis"]["no_favorable_excursion_by_signal"], ["signal_type", "count", "avg_return_pct", "net_pnl"]),
        "",
        "### 短亏且 MFE>=3 后回吐",
        _table(review["short_loss_analysis"]["gave_back_after_mfe_3_by_signal"], ["signal_type", "count", "avg_return_pct", "net_pnl"]),
        "",
        "## 利润回吐",
    ]
    for key, payload in review["giveback_analysis"].items():
        lines.extend(
            [
                f"### {key}",
                f"- negative_count: `{payload['negative_count']}`; small_gain_count: `{payload['small_gain_count']}`",
                _table(payload["by_signal"], ["signal_type", "count", "win_rate_pct", "avg_return_pct", "net_pnl", "avg_mfe_pct"]),
                "",
                "Weak Exit Signal x Exit",
                _table(payload["weak_exit_by_signal_exit"], ["signal_type", "exit_reason", "count", "avg_return_pct", "net_pnl"]),
                "",
            ]
        )
    lines.extend(
        [
            "## Winner Profile",
            "### Winners By Signal",
            _table(review["winner_profile"]["winners_by_signal"], ["signal_type", "count", "avg_return_pct", "net_pnl", "avg_holding_days"]),
            "",
            "### Big Winners By Signal",
            _table(review["winner_profile"]["big_winners_by_signal"], ["signal_type", "count", "avg_return_pct", "net_pnl", "avg_holding_days"]),
            "",
            "### Big Winners Exit",
            _table(review["winner_profile"]["big_winners_exit"], ["signal_type", "exit_reason", "count", "avg_return_pct", "net_pnl"]),
            "",
            "## Symbols",
            "### Top Symbols",
            _table(review["symbol_rank"]["top_symbols"], ["stock_code", "total_return_pct", "trade_count", "win_rate_pct", "net_pnl"]),
            "",
            "### Bottom Symbols",
            _table(review["symbol_rank"]["bottom_symbols"], ["stock_code", "total_return_pct", "trade_count", "win_rate_pct", "net_pnl"]),
            "",
            "### High Trade Losers",
            _table(review["symbol_rank"]["high_trade_losers"], ["stock_code", "total_return_pct", "trade_count", "win_rate_pct", "max_consecutive_losses"]),
            "",
            "## 下一轮实验建议",
        ]
    )
    for rec in review["recommendations"]:
        lines.append(f"- `{rec['scope']}`: {rec['finding']} {rec['next_experiment']}")
    lines.append("")
    return "\n".join(lines)


def _table(rows: list[dict[str, Any]], fields: list[str]) -> str:
    if not rows:
        return "_无数据_"
    header = "| " + " | ".join(fields) + " |"
    sep = "| " + " | ".join("---" for _ in fields) + " |"
    body = []
    for row in rows:
        body.append("| " + " | ".join(str(row.get(field, "")) for field in fields) + " |")
    return "\n".join([header, sep, *body])


def _stat_line(stats: dict[str, Any]) -> str:
    return (
        f"- count `{stats.get('count', 0)}`, win `{stats.get('win_rate_pct', 0)}%`, "
        f"avg `{stats.get('avg_return_pct', 0)}%`, median `{stats.get('median_return_pct', 0)}%`, "
        f"net_pnl `{stats.get('net_pnl', 0)}`, cost `{stats.get('total_cost', 0)}`"
    )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = sorted({key for row in rows for key in row.keys()})
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _holding_bucket(days: int) -> str:
    if days <= 3:
        return "0-3d"
    if days <= 6:
        return "4-6d"
    if days <= 10:
        return "7-10d"
    if days <= 14:
        return "11-14d"
    return "15d+"


def _score_bucket(score: float) -> str:
    if score < 70:
        return "<70"
    if score < 80:
        return "70-80"
    if score < 90:
        return "80-90"
    return "90+"


def _sort_value(field: str, value: Any) -> tuple[int, str]:
    orders = {
        "signal_type": {"breakout_long": 0, "pullback_bounce": 1},
        "holding_bucket": {"0-3d": 0, "4-6d": 1, "7-10d": 2, "11-14d": 3, "15d+": 4},
        "score_bucket": {"<70": 0, "70-80": 1, "80-90": 2, "90+": 3},
        "turnover_rate_bucket": {"0-3": 0, "3-6": 1, "6-10": 2, "10-15": 3, "15+": 4},
        "volume_ratio_bucket": {"0-1.5": 0, "1.5-2": 1, "2-3": 2, "3-5": 3, "5+": 4},
        "box_height_pct_bucket": {"0-10": 0, "10-20": 1, "20-30": 2, "30-50": 3, "50+": 4},
    }
    if field in orders:
        return (orders[field].get(str(value), 999), str(value))
    return (0, str(value))


def _range_bucket(value: Any, ranges: list[tuple[float, float | None]]) -> str:
    number = _num(value)
    for low, high in ranges:
        if high is None and number >= low:
            return f"{_fmt(low)}+"
        if high is not None and low <= number < high:
            return f"{_fmt(low)}-{_fmt(high)}"
    return "unknown"


def _fmt(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def _num(value: Any) -> float:
    if isinstance(value, bool) or value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _round(value: float, digits: int = 4) -> float:
    return round(float(value), digits)


if __name__ == "__main__":
    raise SystemExit(main())
