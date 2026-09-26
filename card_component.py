"""
Glassmorphism Card HTML Component for Streamlit
Accurately replicates the design of IndicatorCard.tsx:
- Dark Glassmorphism style with smooth backdrop blur and border
- Mini Daily Candle (Korean color scheme: Rise=Red, Fall=Blue)
- 60-day historical Sparkline (Yellow for odd, Slate for even)
- Precise favorable condition color logic
"""

import math

def render_daily_candle_svg(o, h, l, c):
    """Generate inline SVG for mini daily candle."""
    if o is None or h is None or l is None or c is None:
        return ""

    try:
        o, h, l, c = float(o), float(h), float(l), float(c)
    except (ValueError, TypeError):
        return ""

    val_range = h - l
    if val_range <= 0:
        val_range = 1.0

    height_px = 30.0
    scale = height_px / val_range

    is_rise = c >= o
    color = "#ef4444" if is_rise else "#3b82f6"  # Korean style: Rise=Red, Fall=Blue

    top_y = (h - max(o, c)) * scale
    body_h = max(abs(c - o) * scale, 2.0)
    bottom_y = (min(o, c) - l) * scale

    return (
        f'<svg width="18" height="32" viewBox="0 0 18 32" style="overflow: visible; display: inline-block; vertical-align: middle; margin-left: 6px;" title="O:{o:.2f} H:{h:.2f} L:{l:.2f} C:{c:.2f}">'
        f'<line x1="9" y1="0" x2="9" y2="{top_y:.1f}" stroke="{color}" stroke-width="1.6" />'
        f'<rect x="4" y="{top_y:.1f}" width="10" height="{body_h:.1f}" rx="1" fill="{color}" />'
        f'<line x1="9" y1="{top_y + body_h:.1f}" x2="9" y2="{top_y + body_h + bottom_y:.1f}" stroke="{color}" stroke-width="1.6" />'
        f'</svg>'
    )


def render_sparkline_svg(history, is_odd=True, is_int=False, is_percent=False):
    """Generate inline SVG sparkline with 50% opacity interactive hover tooltip (60-day trend)."""
    if not history or len(history) < 2:
        return '<div style="width:165px; height:44px; display:flex; align-items:center; justify-content:flex-end; font-size:11px; color:#71717a;">No data</div>'

    valid_items = [h for h in history if h.get("value") is not None]
    if len(valid_items) < 2:
        return '<div style="width:165px; height:44px; display:flex; align-items:center; justify-content:flex-end; font-size:11px; color:#71717a;">No data</div>'

    # Display the most recent 60 trading days for the 60-day trendline
    valid_items = valid_items[-60:]

    values = [float(h["value"]) for h in valid_items]
    min_val = min(values)
    max_val = max(values)
    val_range = max_val - min_val
    if val_range == 0:
        val_range = 1.0

    width = 165.0
    height = 44.0
    pad_y = 4.0
    avail_h = height - (pad_y * 2)

    step_x = width / (len(values) - 1)
    points = []
    hover_groups = []
    stroke_color = "#eab308" if is_odd else "#94a3b8"

    for i, item in enumerate(valid_items):
        v = values[i]
        x = i * step_x
        y = pad_y + avail_h - ((v - min_val) / val_range * avail_h)
        points.append(f"{x:.1f},{y:.1f}")

        # Format date & price for tooltip
        raw_date = str(item.get("date", "")).split("T")[0]
        if is_int:
            fmt_v = f"{int(round(v)):,}"
        elif is_percent:
            fmt_v = f"{v:.2f}%"
        else:
            fmt_v = f"{v:,.2f}"

        # Hit zone width: generous hit zones for endpoints so latest day is effortlessly hoverable
        if i == 0:
            x_start = 0.0
            x_w = max(step_x / 2.0, 10.0)
        elif i == len(values) - 1:
            x_start = x - (step_x / 2.0)
            x_w = max(step_x / 2.0 + 35.0, 40.0)
        else:
            x_start = x - (step_x / 2.0)
            x_w = step_x

        # Tooltip box coordinate: width 74, height 30
        tip_w = 74.0
        tip_h = 30.0
        if x > (width / 2.0):
            tx = max(0.0, x - tip_w - 4.0)
        else:
            tx = min(width - tip_w, x + 4.0)
        ty = -26.0

        # Hover group with hit rect, dashed line, dot, and 50% opacity tooltip
        group_svg = (
            f'<g class="sp-hover-group">'
            f'<rect class="sp-hover-hit" x="{x_start:.1f}" y="0" width="{x_w:.1f}" height="{height}" fill="transparent" />'
            f'<line class="sp-cross" x1="{x:.1f}" y1="0" x2="{x:.1f}" y2="{height}" stroke="rgba(255,255,255,0.25)" stroke-width="1" stroke-dasharray="2,2" />'
            f'<circle class="sp-dot" cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{stroke_color}" stroke="#ffffff" stroke-width="1.2" />'
            f'<g class="sp-tip">'
            f'<rect x="{tx:.1f}" y="{ty:.1f}" width="{tip_w}" height="{tip_h}" rx="4" fill="#0f172a" fill-opacity="0.8" stroke="#38bdf8" stroke-opacity="0.8" stroke-width="1" />'
            f'<text x="{tx + tip_w/2.0:.1f}" y="{ty + 11.0:.1f}" font-size="8.5" fill="#94a3b8" text-anchor="middle" font-family="-apple-system, sans-serif">{raw_date}</text>'
            f'<text x="{tx + tip_w/2.0:.1f}" y="{ty + 24.0:.1f}" font-size="10.5" font-weight="700" fill="#ffffff" text-anchor="middle" font-family="-apple-system, sans-serif">{fmt_v}</text>'
            f'</g>'
            f'</g>'
        )
        hover_groups.append(group_svg)

    path_data = "M " + " L ".join(points)
    all_hover_html = "".join(hover_groups)

    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" style="overflow: visible;">'
        f'<path d="{path_data}" fill="none" stroke="{stroke_color}" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" />'
        f'{all_hover_html}'
        f'</svg>'
    )


def render_indicator_card(data, display_index):
    """Render a single Glassmorphism card HTML string."""
    name = data.get("name", "")
    ticker = data.get("ticker", "")
    price = data.get("price")
    change_amt = data.get("change_amt")
    change_pct = data.get("change_percent")
    history = data.get("history", [])
    open_val = data.get("open")
    high_val = data.get("high")
    low_val = data.get("low")
    close_val = data.get("close")
    neg_favorable = data.get("negative_favorable", False)
    is_int = data.get("is_integer_only", False)
    is_percent = data.get("is_percent", False)

    display_name = f"{display_index:02d}. {name}" if display_index is not None else name
    is_odd = (display_index % 2 != 0) if display_index is not None else True

    # Value formatting with NaN protection
    if price is not None and not (isinstance(price, float) and (math.isnan(price) or math.isinf(price))):
        if is_int:
            formatted_price = f"{int(round(price)):,}"
        elif is_percent:
            formatted_price = f"{price:.2f}%"
        else:
            formatted_price = f"{price:,.2f}"
    else:
        formatted_price = "N/A"

    # Color determining for change with NaN protection
    has_valid_chg = change_amt is not None and not (isinstance(change_amt, float) and (math.isnan(change_amt) or math.isinf(change_amt)))
    has_valid_pct = change_pct is not None and not (isinstance(change_pct, float) and (math.isnan(change_pct) or math.isinf(change_pct)))

    is_positive = has_valid_chg and change_amt > 0
    is_negative = has_valid_chg and change_amt < 0

    if is_positive:
        sign = "+"
        arrow_svg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right:2px; vertical-align:text-bottom;"><line x1="7" y1="17" x2="17" y2="7"></line><polyline points="7 7 17 7 17 17"></polyline></svg>'
        if neg_favorable:
            val_color = "#ef4444"  # Unfavorable rise (e.g., higher inflation/yield/VIX)
        else:
            val_color = "#22c55e"  # Favorable rise
    elif is_negative:
        sign = "-"
        arrow_svg = '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" style="margin-right:2px; vertical-align:text-bottom;"><line x1="7" y1="7" x2="17" y2="17"></line><polyline points="17 7 17 17 7 17"></polyline></svg>'
        if neg_favorable:
            val_color = "#22c55e"  # Favorable fall (e.g., lower yield/VIX)
        else:
            val_color = "#ef4444"  # Unfavorable fall
    else:
        sign = ""
        arrow_svg = ""
        val_color = "#a1a1aa"

    if has_valid_chg:
        abs_amt = abs(change_amt)
        formatted_chg = f"{int(round(abs_amt)):,}" if is_int else f"{abs_amt:,.2f}"
    else:
        formatted_chg = "-"

    if has_valid_pct:
        formatted_pct = f"{abs(change_pct):.2f}%"
        percent_str = f" ({sign}{formatted_pct})"
    else:
        percent_str = ""

    change_text = f"{sign}{formatted_chg}{percent_str}" if formatted_chg != "-" else "-"

    candle_html = render_daily_candle_svg(open_val, high_val, low_val, close_val)
    sparkline_html = render_sparkline_svg(history, is_odd=is_odd, is_int=is_int, is_percent=is_percent)

    card_html = (
        f'<div class="glass-card">'
        f'<div class="card-header"><div class="card-title" title="{display_name}">{display_name}</div></div>'
        f'<div class="card-body">'
        f'<div class="price-container">'
        f'<div class="price-row"><span class="price-value">{formatted_price}</span>{candle_html}</div>'
        f'<div class="change-row" style="color: {val_color};">{arrow_svg}<span>{change_text}</span></div>'
        f'</div>'
        f'<div class="sparkline-container">{sparkline_html}</div>'
        f'</div>'
        f'</div>'
    )
    return card_html


def render_card_grid(items_with_index):
    """Render a responsive grid of glassmorphism cards."""
    cards_html = "".join([render_indicator_card(item, idx) for item, idx in items_with_index])
    return f'<div class="card-grid">{cards_html}</div>'

