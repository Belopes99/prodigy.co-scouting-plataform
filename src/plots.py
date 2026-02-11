import plotly.graph_objects as go
import pandas as pd
from typing import Optional

def create_pitch(
    pitch_length: float = 105.0,
    pitch_width: float = 68.0,
    line_color: str = "#c9cdd1",
    pitch_color: str = "#0e1117",
) -> go.Figure:
    """
    Creates the base football pitch using Plotly shapes.
    """
    fig = go.Figure()

    # Define Pitch Dimensions
    L = pitch_length
    W = pitch_width

    # Pitch Outline
    # Define Stripe Colors (Two-tone Green/Grey optimized for Dark Mode)
    # Pitch color input is usually very dark (#0e1117). We want a subtle variation.
    # If pitch_color is dark, we make the stripes slightly lighter.
    stripe_color = "#161b22" if pitch_color == "#0e1117" else "rgba(255,255,255,0.05)"
    
    shapes = []
    
    # Grass Stripes (every 5.5m approx, or just 10-12 divisions)
    # Standard pitch is 105m long. 105 / 18 stripes = ~5.8m per stripe
    n_stripes = 18
    stripe_width = L / n_stripes
    
    for i in range(0, n_stripes, 2):
        shapes.append(
            dict(
                type="rect",
                x0=i * stripe_width, 
                y0=0, 
                x1=(i + 1) * stripe_width, 
                y1=W,
                fillcolor=stripe_color,
                layer="below",
                line=dict(width=0),
            )
        )

    # Pitch Outline & Markings
    shapes.extend([
        # Outer Border
        dict(type="rect", x0=0, y0=0, x1=L, y1=W, line=dict(color=line_color, width=2)),
        # Halfway Line
        dict(type="line", x0=L/2, y0=0, x1=L/2, y1=W, line=dict(color=line_color, width=2)),
        # Center Circle
        dict(type="circle", x0=L/2-9.15, y0=W/2-9.15, x1=L/2+9.15, y1=W/2+9.15, line=dict(color=line_color, width=2)),
        # Penalty Area Left
        dict(type="rect", x0=0, y0=(W-40.32)/2, x1=16.5, y1=(W+40.32)/2, line=dict(color=line_color, width=2)),
        # Penalty Area Right
        dict(type="rect", x0=L-16.5, y0=(W-40.32)/2, x1=L, y1=(W+40.32)/2, line=dict(color=line_color, width=2)),
        # Goal Area Left
        dict(type="rect", x0=0, y0=(W-18.32)/2, x1=5.5, y1=(W+18.32)/2, line=dict(color=line_color, width=2)),
        # Goal Area Right
        dict(type="rect", x0=L-5.5, y0=(W-18.32)/2, x1=L, y1=(W+18.32)/2, line=dict(color=line_color, width=2)),
    ])

    fig.update_layout(
        shapes=shapes,
        xaxis=dict(range=[-5, L+5], showgrid=False, zeroline=False, visible=False, fixedrange=True),
        yaxis=dict(range=[-5, W+5], showgrid=False, zeroline=False, visible=False, fixedrange=True, scaleanchor="x", scaleratio=1),
        plot_bgcolor=pitch_color,
        paper_bgcolor=pitch_color,
        margin=dict(l=0, r=0, t=0, b=0),
        height=600,
        showlegend=True,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=-0.1,
            xanchor="center",
            x=0.5,
            font=dict(color=line_color)
        )
    )
    return fig

def plot_events_plotly(
    df: pd.DataFrame,
    pitch_length: float = 105.0,
    pitch_width: float = 68.0,
    color_outcome: bool = False,
    draw_arrows: bool = False,
    highlight_qualifier: Optional[str] = None,
    highlight_type: Optional[str] = None,
    theme_colors: Optional[dict] = None,
    color_strategy: str = "Resultado (Sucesso/Falha)",
    layer_colors: Optional[dict] = None
) -> go.Figure:
    """
    Plots events on top of the Plotly pitch.
    """
    if theme_colors is None:
        theme_colors = {}
        
    line_color = theme_colors.get("pitch_line_color", "#c9cdd1")
    pitch_bg = theme_colors.get("fig_bg", "#0e1117")
    
    fig = create_pitch(pitch_length, pitch_width, line_color, pitch_bg)
    
    # Defaults
    def_color = theme_colors.get("event_color", "#A0A0A0")
    ok_color = theme_colors.get("ok_color", "#7CFC98")
    bad_color = theme_colors.get("bad_color", "#FF6B6B")
    hl_color = theme_colors.get("highlight_color", "#FFD700")

    # Split Data Logic
    traces = []
    
    # Helper to map event types to shapes
    def get_event_symbol(event_type):
        etype = str(event_type).lower()
        if "pass" in etype: return "circle" if draw_arrows else "triangle-up"
        if "shot" in etype or "goal" in etype: return "circle"
        if "duel" in etype or "tackle" in etype or "interception" in etype or "foul" in etype: return "square"
        if "save" in etype: return "diamond-tall"
        return "hexagon" # specific generic

    # Helper to create trace
    def add_trace(sub_df, name, color, symbol=None, opacity=0.8, size=8):
        # Build Hover Text
        hover_texts = []
        
        # Lists for Arrow Lines (Pattern: x1, x2, None, x3, x4, None...)
        arr_x = []
        arr_y = []
        
        # Lists for Arrow Heads
        head_x = []
        head_y = []
        head_angles = []
        
        # Determine Symbols: If fixed symbol is None, calculate from Type
        if symbol is None:
            symbols = [get_event_symbol(getattr(r, "type", "")) for r in sub_df.itertuples()]
        else:
            symbols = symbol

        # Check if we have end coordinates for arrows
        has_end = ("end_x_plot" in sub_df.columns and "end_y_plot" in sub_df.columns)

        for r in sub_df.itertuples():
            min_str = f"{r.expanded_minute}'"
            p_name = getattr(r, "player", "Unknown")
            type_str = getattr(r, "type", "Event")
            
            txt = f"<b>{type_str}</b><br>{p_name}<br>Min: {min_str}<br>"
            if "outcome_type" in sub_df.columns:
                txt += f"Outcome: {r.outcome_type}<br>"
            if "kv_qualifiers" in sub_df.columns:
                q_list = getattr(r, "kv_qualifiers", [])
                if q_list:
                    txt += f"Tags: {', '.join(q_list)}"
            hover_texts.append(txt)

            # Collect Arrow Lines (efficient method)
            if draw_arrows and has_end:
                ex, ey = getattr(r, "end_x_plot", None), getattr(r, "end_y_plot", None)
                sx, sy = r.x_plot, r.y_plot
                
                if pd.notna(ex) and pd.notna(ey):
                    arr_x.extend([sx, ex, None])
                    arr_y.extend([sy, ey, None])
                    
                    # Calculate angle for arrowhead
                    dy = ey - sy
                    dx = ex - sx
                    import math
                    angle_math = math.degrees(math.atan2(dy, dx))
                    head_x.append(ex)
                    head_y.append(ey)
                    
                    # Plotly Marker Angle:
                    # 0 = Up (12 o'clock)
                    # Increases CLOCKWISE
                    # math.atan2:
                    # 0 = Right (3 o'clock)
                    # Increases COUNTER-CLOCKWISE
                    #
                    # Mapping:
                    # Math 0 (Right)   -> Plotly 90
                    # Math 90 (Up)     -> Plotly 0
                    # Math 180 (Left)  -> Plotly 270 (-90)
                    # Math -90 (Down)  -> Plotly 180
                    #
                    # Formula: 90 - MathAngle
                    head_angles.append(90 - angle_math)

        # 1. Main Scatter Traces (Markers - Start Point)
        traces.append(go.Scatter(
            x=sub_df["x_plot"],
            y=sub_df["y_plot"],
            mode="markers",
            name=name,
            marker=dict(size=size, color=color, symbol=symbols, opacity=opacity, line=dict(width=1, color="black")),
            text=hover_texts,
            hoverinfo="text"
        ))
        
        # 2. Optimized Arrow Trace (Lines)
        if arr_x:
            traces.append(go.Scatter(
                x=arr_x,
                y=arr_y,
                mode="lines",
                name=f"{name} (Trajetória)",
                line=dict(color=color, width=1.5),
                opacity=opacity, # Use function arg
                showlegend=False,
                hoverinfo="skip"
            ))
            
        # 3. Optimized Arrow Heads (Markers)
        if head_x:
             traces.append(go.Scatter(
                x=head_x,
                y=head_y,
                mode="markers",
                name=f"{name} (Pontas)",
                marker=dict(
                    symbol="triangle-up", # Using standard triangle
                    size=10,
                    color=color,
                    angle=head_angles,
                    standoff=0
                ),
                opacity=opacity, # Use function arg
                showlegend=False,
                hoverinfo="skip"
            ))

    # Logic tree for subsets
    if highlight_type and "type" in df.columns:
        mask = df["type"] == highlight_type
        df_h = df[mask]
        df_o = df[~mask]
        
        if not df_o.empty:
            add_trace(df_o, "Outros", def_color, opacity=0.1, size=6, symbol="circle")
        if not df_h.empty:
            # Highlight with Gold Color and slightly larger size, but keep symbol logic
            add_trace(df_h, highlight_type, hl_color, opacity=1.0, size=10, symbol=None)

    elif highlight_qualifier and "kv_qualifiers" in df.columns:
        mask = df["kv_qualifiers"].apply(lambda x: highlight_qualifier in x)
        df_h = df[mask]
        df_o = df[~mask]
        
        if not df_o.empty:
            add_trace(df_o, "Outros", def_color, opacity=0.1, size=6, symbol="circle") # Increased transparency (0.3 -> 0.1)
        if not df_h.empty:
            add_trace(df_h, highlight_qualifier, hl_color, opacity=1.0, size=12, symbol="star")
            
    elif color_strategy in ["Tipo de Evento", "Equipe", "Jogador"] and layer_colors:
        # Determine grouping column map
        # "Tipo de Evento" -> "type"
        # "Equipe" -> "team"
        # "Jogador" -> "player Name" ?? Wait, DF has "player" col usually.
        # Check DF cols first
        
        col_map = {
            "Tipo de Evento": "type",
            "Equipe": "team",
            "Jogador": "player" # Check if this matches your DF schema. usually 'player' or 'player_name'
        }
        
        group_col = col_map.get(color_strategy)
        
        if group_col and group_col in df.columns:
            unique_vals = df[group_col].dropna().unique()
            
            for val in unique_vals:
                # Key for layer_colors might be the string repr
                val_key = str(val)
                sub_df = df[df[group_col] == val]
                
                if sub_df.empty: continue
                
                # Config fetch
                # If the key provided in UI (e.g. "Hulk (123)") doesn't match raw val ("Hulk"), we rely on partial match or exact?
                # The UI constructed keys based on multiselect strings. 
                # For Type and Team, it's exact match. 
                # For Player, user multiselect has "Name (ID)". DF usually has "Name". 
                # UI key: "Hulk (123)". DF val: "Hulk". 
                # Let's try direct lookup first, if fail, try finding a key that starts with val?
                # Actually, in Pages, the 'clean_layer_colors' keys are exactly what is used in UI.
                # If we grouped by DF val 'Hulk', we need to find the config for 'Hulk (123)'.
                
                # Simplest fix: In this loop, just default. 
                # BETTER FIX: In pages/1_eventos.py, we iterate `teams_t` (exact) and `event_types` (exact).
                # For players, we used `selected_players` (Name (Id)).
                # So for Player strategy, we might have a key mismatch if we just use `val`.
                # But let's assume exact match for Type/Team for now. For Player, we try to match.
                
                t_conf = {}
                if color_strategy == "Jogador":
                    # Try to find key that contains val
                    found_k = None
                    for k in layer_colors.keys():
                        if str(val) in k: # "Hulk" in "Hulk (123)"
                            found_k = k
                            break
                    if found_k:
                        t_conf = layer_colors[found_k]
                else:
                    t_conf = layer_colors.get(val_key, {})
                
                base_c = t_conf.get("base", def_color)
                ok_c = t_conf.get("ok", ok_color)
                bad_c = t_conf.get("bad", bad_color)
                
                # We still want correct symbols per row (unless strategy forbids? No, keep shapes)
                # But here we are passing full sub_df. add_trace handles per-row symbols if symbol=None.
                
                if color_outcome and "outcome_type" in sub_df.columns:
                    succ = sub_df[sub_df["outcome_type"] == "Successful"]
                    fail = sub_df[sub_df["outcome_type"] != "Successful"]
                    
                    if not succ.empty:
                        add_trace(succ, f"{val} (OK)", ok_c, symbol=None) # Let add_trace resolve per-row symbol
                    if not fail.empty:
                        add_trace(fail, f"{val} (Fail)", bad_c, symbol=None)
                else:
                    add_trace(sub_df, str(val), base_c, symbol=None)
        else:
             # Fallback if col missing
             add_trace(df, "Eventos", def_color)

    elif color_outcome and "outcome_type" in df.columns:
        succ = df[df["outcome_type"] == "Successful"]
        fail = df[df["outcome_type"] != "Successful"]
        
        if not succ.empty:
            add_trace(succ, "Successful", ok_color) # Auto-symbol
        if not fail.empty:
            add_trace(fail, "Unsuccessful", bad_color) # Auto-symbol (was 'x')
            
    else:
        add_trace(df, "Eventos", def_color)

    for t in traces:
        fig.add_trace(t)
        
    return fig


def plot_radar_chart(
    player_name: str,
    categories: list,
    values: list,
    max_values: Optional[list] = None
) -> go.Figure:
    """
    Plots a radar chart for a single player.
    """
    fig = go.Figure()

    # If max_values provided, normalize to 0-1 (or 0-100) or just plot raw?
    # Simple approach: Plot raw, user sees axes.
    # Aesthetically, closed shape.

    fig.add_trace(go.Scatterpolar(
        r=values,
        theta=categories,
        fill='toself',
        name=player_name,
        line_color='#00ff00',
        fillcolor='rgba(0, 255, 0, 0.2)'
    ))

    fig.update_layout(
        polar=dict(
            radialaxis=dict(
                visible=True,
                showticklabels=True,
                gridcolor='#30363d',
                tickfont=dict(color='gray')
            ),
            bgcolor='rgba(0,0,0,0)'
        ),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False,
        margin=dict(l=40, r=40, t=40, b=40)
    )

    return fig
