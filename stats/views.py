# stats/views.py
from datetime import datetime

from django.db import models
from django.db.models import Q, Count, Sum, Max
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_date

from .models import (
    Team,
    Player,
    PescaraGame,
    Appearance,
    LeagueTable,
)

# --------------------
# Constants / helpers
# --------------------

TOTAL_ROUNDS = 25  # used across home and trajectory chart


def _lerp(a, b, t):
    return int(round(a + (b - a) * t))


def _hex(rgb):
    return "#{:02x}{:02x}{:02x}".format(*rgb)


def _gradient_color(pos, max_pos):
    """
    Map position 1..max_pos to color from green → gray
    """
    if max_pos < 1:
        max_pos = 1
    pos = max(1, min(pos, max_pos))
    # 0 at best (1), 1 at worst (max_pos)
    t = (pos - 1) / max(1, (max_pos - 1))
    g = (34, 197, 94)    # emerald-500
    w = (107, 114, 128)  # gray-500
    rgb = (_lerp(g[0], w[0], t), _lerp(g[1], w[1], t), _lerp(g[2], w[2], t))
    return _hex(rgb)


# --------------------
# Standings
# --------------------

def standings_view(request):
    """
    Show latest LeagueTable, with deltas vs previous table and last result vs Pescara.
    """
    latest = (
        LeagueTable.objects
        .order_by("-date", "-jornada")
        .prefetch_related("entries__team")
        .first()
    )
    if not latest:
        return render(request, "stats/standings.html", {"table": None, "entries": []})

    prev = (
        LeagueTable.objects
        .filter(Q(date__lt=latest.date) | Q(date=latest.date, jornada__lt=latest.jornada))
        .order_by("-date", "-jornada")
        .prefetch_related("entries__team")
        .first()
    )

    prev_map = {}
    if prev:
        for pe in prev.entries.all():
            prev_map[pe.team_id] = pe.position

    entries = list(latest.entries.select_related("team").order_by("position"))

    for e in entries:
        prev_pos = prev_map.get(e.team_id)
        if prev_pos is None:
            e.pos_delta = None
            e.pos_delta_abs = None
        else:
            e.pos_delta = prev_pos - e.position
            e.pos_delta_abs = abs(e.pos_delta)

    # last head-to-head vs each opponent
    opp_ids = [e.team_id for e in entries]
    last_vs = {}
    games_qs = (
        PescaraGame.objects
        .filter(opponent_id__in=opp_ids)
        .filter(Q(date__lt=latest.date) | Q(date=latest.date))
        .order_by("opponent_id", "-date", "-jornada")
        .values("opponent_id", "result")
    )
    for g in games_qs:
        last_vs.setdefault(g["opponent_id"], g["result"])

    for e in entries:
        e.played_result = last_vs.get(e.team_id)

    return render(request, "stats/standings.html", {"table": latest, "entries": entries})


# --------------------
# Matches
# --------------------

def matches_view(request):
    qs = (
        PescaraGame.objects
        .select_related("opponent")
        .prefetch_related("appearances__player")
        .order_by("date")
    )

    result = request.GET.get("result")
    if result in {"W", "D", "L"}:
        qs = qs.filter(result=result)

    dfrom = request.GET.get("from")
    dto = request.GET.get("to")
    if dfrom:
        df = parse_date(dfrom)
        if df:
            qs = qs.filter(date__gte=df)
    if dto:
        dt = parse_date(dto)
        if dt:
            qs = qs.filter(date__lte=dt)

    games = list(qs)

    latest_table = LeagueTable.objects.order_by("-date", "-jornada").first()
    pos_by_team = {}
    if latest_table:
        for e in latest_table.entries.all():
            pos_by_team[e.team_id] = e.position

    for g in games:
        g.opponent_position = pos_by_team.get(g.opponent_id)

    return render(
        request,
        "stats/matches.html",
        {"games": games, "result": result or "", "from": dfrom or "", "to": dto or ""},
    )


# --------------------
# Players
# --------------------

def players_view(request):
    # sort: games | goals | gpm | number
    sort = request.GET.get("sort", "games")
    q = request.GET.get("q", "").strip()

    base = Player.objects.filter(active=True)
    if q:
        base = base.filter(Q(first_name__icontains=q) | Q(last_name__icontains=q))

    players = base.annotate(
        gp=Count("appearances__game", distinct=True),
        goals_total=Sum("appearances__goals"),
    )

    rows = []
    for p in players:
        p.goals_total = p.goals_total or 0
        gpm = round(p.goals_total / p.gp, 2) if p.gp else 0
        rows.append({"player": p, "gpm": gpm})

    if sort == "goals":
        rows.sort(key=lambda r: (r["player"].goals_total, r["gpm"]), reverse=True)
    elif sort == "gpm":
        rows.sort(key=lambda r: (r["gpm"], r["player"].goals_total), reverse=True)
    elif sort == "number":
        rows.sort(key=lambda r: (r["player"].number or 9999, r["player"].last_name or ""))
    else:  # games
        rows.sort(key=lambda r: (r["player"].gp, r["player"].goals_total), reverse=True)

    player_rows = []
    for r in rows:
        p = r["player"]
        apps = (
            Appearance.objects
            .filter(player=p)
            .select_related("game", "game__opponent")
            .order_by("game__date")
        )
        player_rows.append({"player": p, "gpm": r["gpm"], "apps": apps})

    return render(request, "stats/players.html", {"rows": player_rows, "sort": sort, "q": q})


def player_detail(request, pk):
    p = get_object_or_404(Player, pk=pk)
    apps = (
        Appearance.objects
        .filter(player=p)
        .select_related("game", "game__opponent")
        .order_by("game__date")
    )
    totals = apps.aggregate(gp=Count("game", distinct=True), goals=Sum("goals"))
    totals["goals"] = totals["goals"] or 0
    gpm = round(totals["goals"] / totals["gp"], 2) if totals["gp"] else 0
    return render(request, "stats/player_detail.html", {"p": p, "apps": apps, "totals": totals, "gpm": gpm})


def match_detail(request, pk):
    game = get_object_or_404(PescaraGame.objects.select_related("opponent"), pk=pk)
    apps = (
        Appearance.objects
        .filter(game=game)
        .select_related("player")
        .order_by("player__number")
    )
    return render(request, "stats/match_detail.html", {"game": game, "apps": apps})


# --------------------
# Home (hero)
# --------------------

def home_view(request):
    """
    Front page hero with last/next game and small summary cards.
    Keeps the existing hero design; also provides data for buttons,
    including a link to the positions trajectory page.
    """
    today = timezone.now().date()

    # Last and next game
    last_game = (
        PescaraGame.objects
        .select_related("opponent")
        .filter(date__lte=today)
        .order_by("-date", "-jornada")
        .first()
    )
    next_game = (
        PescaraGame.objects
        .select_related("opponent")
        .filter(date__gt=today)
        .order_by("date", "jornada")
        .first()
    )

    # Latest table and Pescara entry
    table = (
        LeagueTable.objects
        .order_by("-date", "-jornada")
        .prefetch_related("entries__team")
        .first()
    )

    pescara_team = Team.objects.filter(name__icontains="pescara").first()

    entry = None
    team_count = 0
    latest_jornada = None
    pescara_position = None
    pescara_points = None
    games_played = 0
    max_potential_points = 0

    if table:
        latest_jornada = table.jornada
        team_count = table.entries.count()

        # Find Pescara's row
        for e in table.entries.all():
            if pescara_team and e.team_id == pescara_team.id:
                entry = e
                pescara_position = getattr(e, "position", None)
                pescara_points = getattr(e, "points", None)

                games_played = (
                    getattr(e, "played", None) or
                    getattr(e, "games_played", None)
                )
                if games_played is None:
                    w = getattr(e, "wins", 0) or 0
                    d = getattr(e, "draws", 0) or 0
                    l = getattr(e, "losses", 0) or 0
                    games_played = w + d + l

                max_potential_points = (games_played or 0) * 3
                break

    return render(request, "stats/home.html", {
        "latest_jornada": latest_jornada,
        "total_rounds": TOTAL_ROUNDS,
        "pescara_position": pescara_position,
        "team_count": team_count,
        "pescara_points": pescara_points,
        "games_played": games_played,
        "max_potential_points": max_potential_points,
        "last_game": last_game,
        "next_game": next_game,
        "latest_table": table,
        "entry": entry,
        "pescara_team": pescara_team,
    })


# --------------------
# Positions trajectory (sparkline + table)
# --------------------

def pescara_positions_view(request):
    pescara = Team.objects.filter(name__icontains="pescara").first()
    if not pescara:
        return render(request, "stats/pos_trend.html", {"rows": [], "max_pos": 0})

    tables = (
        LeagueTable.objects
        .order_by("date", "jornada")
        .prefetch_related("entries__team")
    )

    results_by_j = {g.jornada: g.result for g in PescaraGame.objects.only("jornada", "result")}

    rows = []
    max_pos_seen = 0
    for t in tables:
        entry = next((x for x in t.entries.all() if x.team_id == pescara.id), None)
        if not entry:
            continue
        pos = entry.position
        pts = getattr(entry, "points", None) or 0
        max_pos_seen = max(max_pos_seen, pos)

        res = results_by_j.get(t.jornada)
        if res == "W":
            res_letter, res_cls = "G", "win"
        elif res == "L":
            res_letter, res_cls = "P", "loss"
        elif res == "D":
            res_letter, res_cls = "E", "draw"
        else:
            res_letter, res_cls = "", ""

        rows.append({
            "jornada": t.jornada,
            "position": pos,
            "points": pts,
            "res_letter": res_letter,
            "res_class": res_cls,
        })

    max_pos = max(max_pos_seen or 1, 1)
    for r in rows:
        r["color"] = _gradient_color(r["position"], max_pos)

    # Sparkline SVG layout
    svg_w, svg_h = 920, 260
    pad_l, pad_r, pad_t, pad_b = 36, 18, 12, 24
    inner_w = svg_w - pad_l - pad_r
    inner_h = svg_h - pad_t - pad_b

    # Fixed y range 1..25
    y_min, y_max = 1, 25

    def y_for(pos):
        pos = min(max(pos, y_min), y_max)
        t = (pos - y_min) / (y_max - y_min)  # 0..1
        return pad_t + t * inner_h

    # >>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>
    # X based on REAL JORNADA (J1..J{TOTAL_ROUNDS}), not on row index
    def x_for_j(j):
        j = max(1, min(j, TOTAL_ROUNDS))
        span = max(1, TOTAL_ROUNDS - 1)
        t = (j - 1) / span
        return pad_l + t * inner_w
    # <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

    points = []
    dots = []
    for r in rows:
        x = x_for_j(r["jornada"])      # ← jornada-based X
        y = y_for(r["position"])
        points.append(f"{int(round(x))},{int(round(y))}")
        dots.append({
            "cx": int(round(x)),
            "cy": int(round(y)),
            "label": f"J{r['jornada']}",
            "pos": r["position"],
        })
    spark_points = " ".join(points)

    # X-axis labels J1..TOTAL_ROUNDS
    x_axis_step = inner_w / max(1, (TOTAL_ROUNDS - 1))
    x_labels = [{"x": int(round(pad_l + i * x_axis_step)), "text": f"J{i+1}"} for i in range(TOTAL_ROUNDS)]

    # Y ticks every 5 (1,5,10,15,20,25)
    y_ticks = [1, 5, 10, 15, 20, 25]
    y_labels = [{"y": int(round(y_for(val))), "text": str(val)} for val in y_ticks]

    # Nice footer span like “J1–J4”
    jornada_span = f"J{rows[0]['jornada']}–J{rows[-1]['jornada']}" if rows else ""

    return render(request, "stats/pos_trend.html", {
        "rows": rows,
        "max_pos": y_max,
        "spark_w": svg_w,
        "spark_h": svg_h,
        "spark_points": spark_points,
        "spark_dots": dots,
        "y_labels": y_labels,
        "first_round": rows[0]["jornada"] if rows else None,
        "last_round": rows[-1]["jornada"] if rows else None,
        "x_labels": x_labels,
        "total_rounds": TOTAL_ROUNDS,
        "jornada_span": jornada_span,
    })