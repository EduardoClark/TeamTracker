# stats/views.py
from django.shortcuts import render, get_object_or_404
from django.db import models
from django.db.models import Count, Sum
from django.db.models import Q, Max, Min
from .models import Team, Player, PescaraGame, Appearance, LeagueTable
from datetime import datetime
from django.utils.dateparse import parse_date
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone

TOTAL_ROUNDS = 25

def standings_view(request):
    # 1) Latest table (most recent by date / jornada)
    latest = (
        LeagueTable.objects
        .order_by("-date", "-jornada")
        .prefetch_related("entries__team")
        .first()
    )
    if not latest:
        return render(request, "stats/standings.html", {"table": None, "entries": []})

    # 2) Previous table (prefer same-date older jornada, else any earlier date)
    prev = (
        LeagueTable.objects
        .filter(Q(date__lt=latest.date) | Q(date=latest.date, jornada__lt=latest.jornada))
        .order_by("-date", "-jornada")
        .prefetch_related("entries__team")
        .first()
    )

    # Map team_id -> previous position
    prev_map = {}
    if prev:
        for pe in prev.entries.all():
            prev_map[pe.team_id] = pe.position

    # Current entries ordered by position
    entries = list(latest.entries.select_related("team").order_by("position"))

    # 3) Position deltas
    for e in entries:
        prev_pos = prev_map.get(e.team_id)
        if prev_pos is None:
            e.pos_delta = None
            e.pos_delta_abs = None
        else:
            # +N = improved N spots (moved UP); -N = dropped N spots
            e.pos_delta = prev_pos - e.position
            e.pos_delta_abs = abs(e.pos_delta)

    # 4) Last head-to-head vs Pescara up to the table date
    #    Build opponent_id -> last result ('W','D','L')
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
        # keep newest per opponent
        last_vs.setdefault(g["opponent_id"], g["result"])

    for e in entries:
        e.played_result = last_vs.get(e.team_id)  # 'W' | 'D' | 'L' | None

    return render(
        request,
        "stats/standings.html",
        {
            "table": latest,
            "entries": entries,
        },
    )    # Latest table (most recent by date/jornada)
    latest = (
        LeagueTable.objects
        .order_by("-date", "-jornada")
        .prefetch_related("entries__team")
        .first()
    )
    if not latest:
        return render(request, "stats/standings.html", {"table": None, "entries": []})

    # Previous table (prefer same date older jornada, else any earlier date)
    prev = (
        LeagueTable.objects
        .filter(Q(date__lt=latest.date) | Q(date=latest.date, jornada__lt=latest.jornada))
        .order_by("-date", "-jornada")
        .prefetch_related("entries__team")
        .first()
    )

    # team_id -> previous position map
    prev_map = {}
    if prev:
        for pe in prev.entries.all():
            prev_map[pe.team_id] = pe.position

    # Current entries ordered by position + annotate deltas
    entries = list(latest.entries.select_related("team").order_by("position"))
    for e in entries:
        prev_pos = prev_map.get(e.team_id)
        if prev_pos is None:
            e.pos_delta = None
            e.pos_delta_abs = None
        else:
            # +N means improved N spots (went UP); -N means dropped N spots
            e.pos_delta = prev_pos - e.position
            e.pos_delta_abs = abs(e.pos_delta)

    return render(
        request,
        "stats/standings.html",
        {
            "table": latest,
            "entries": entries,
        },
    )


def matches_view(request):
    qs = (
        PescaraGame.objects
        .select_related("opponent")
        .prefetch_related("appearances__player")
        .order_by("date")
    )

    # --- filtros que ya tienes ---
    result = request.GET.get("result")
    if result in {"W", "D", "L"}:
        qs = qs.filter(result=result)

    dfrom = request.GET.get("from")
    dto   = request.GET.get("to")
    if dfrom:
        df = parse_date(dfrom)
        if df:
            qs = qs.filter(date__gte=df)
    if dto:
        dt = parse_date(dto)
        if dt:
            qs = qs.filter(date__lte=dt)

    games = list(qs)

    # --- obtener posiciones actuales ---
    latest_table = LeagueTable.objects.order_by("-jornada").first()
    pos_by_team = {}
    if latest_table:
        for e in latest_table.entries.all():  # entries → tus TableEntry relacionados
            pos_by_team[e.team_id] = e.position

    # --- anotar posición a cada partido ---
    for g in games:
        g.opponent_position = pos_by_team.get(g.opponent_id)

    return render(request, "stats/matches.html", {
        "games": games,
        "result": result or "",
        "from": dfrom or "",
        "to": dto or "",
    })


from django.db.models import Q, Count, Sum
from .models import Player, Appearance

def players_view(request):
    # sort: games (default) | goals | gpm | number
    sort = request.GET.get("sort", "games")
    q = request.GET.get("q", "").strip()

    base = Player.objects.filter(active=True)

    if q:
        base = base.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )

    players = (
        base
        .annotate(
            gp=Count("appearances__game", distinct=True),  # games played
            goals_total=Sum("appearances__goals"),
        )
    )

    # Normalize + compute goals per match (gpm)
    rows = []
    for p in players:
        p.goals_total = p.goals_total or 0
        gpm = round(p.goals_total / p.gp, 2) if p.gp else 0
        rows.append({"player": p, "gpm": gpm})

    # Sorting (Python-side is fine for small datasets)
    if sort == "goals":
        # by total goals, tie-breaker gpm
        rows.sort(key=lambda r: (r["player"].goals_total, r["gpm"]), reverse=True)
    elif sort == "gpm":
        # by goals per match, tie-breaker total goals
        rows.sort(key=lambda r: (r["gpm"], r["player"].goals_total), reverse=True)
    elif sort == "number":
        rows.sort(key=lambda r: (r["player"].number or 9999, r["player"].last_name or ""))
    else:  # "games" (default)
        # by games played, tie-breaker total goals
        rows.sort(key=lambda r: (r["player"].gp, r["player"].goals_total), reverse=True)

    # Load appearances for the sandwich
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

    return render(request, "stats/players.html", {
        "rows": player_rows,
        "sort": sort,
        "q": q,
    })

def player_detail(request, pk):
    p = get_object_or_404(Player, pk=pk)
    apps = (Appearance.objects
            .filter(player=p)
            .select_related("game", "game__opponent")
            .order_by("game__date"))
    totals = apps.aggregate(gp=Count("game", distinct=True), goals=Sum("goals"))
    totals["goals"] = totals["goals"] or 0
    gpm = round(totals["goals"] / totals["gp"], 2) if totals["gp"] else 0
    return render(request, "stats/player_detail.html",
                  {"p": p, "apps": apps, "totals": totals, "gpm": gpm})

def match_detail(request, pk):
    game = get_object_or_404(
        PescaraGame.objects.select_related("opponent"),
        pk=pk
    )
    apps = (
        Appearance.objects
        .filter(game=game)
        .select_related("player")
        .order_by("player__number")
    )
    return render(request, "stats/match_detail.html", {"game": game, "apps": apps})


def home_view(request):
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

    # Latest league table and Pescara entry
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

                # PJ: try common field names; fallback to W+D+L if needed
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
        # cards need:
        "latest_jornada": latest_jornada,                 # use as J{{ latest_jornada }}/{{ total_rounds }}
        "total_rounds": TOTAL_ROUNDS,               # = 25 (fixed)
        "pescara_position": pescara_position,             # Y
        "team_count": team_count,                         # X
        "pescara_points": pescara_points,                 # XX
        "games_played": games_played,                     # PJ
        "max_potential_points": max_potential_points,     # YY = PJ * 3

        # existing bits you already used on home:
        "last_game": last_game,
        "next_game": next_game,
        "latest_table": table,
        "entry": entry,
        "pescara_team": pescara_team,
    })

def _lerp(a, b, t):
    return int(round(a + (b - a) * t))

def _hex(rgb):  # (r,g,b) -> "#rrggbb"
    return "#{:02x}{:02x}{:02x}".format(*rgb)

def _gradient_color(pos, max_pos):
    """
    Map position 1..max_pos to a color from green → gray.
    1   -> #22c55e (emerald-500)
    max -> #6b7280 (gray-500)
    """
    pos = max(1, min(pos, max_pos))
    t = (pos - 1) / max(1, max_pos - 1)   # 0..1

    g = (34, 197, 94)   # green  (#22c55e)
    w = (107, 114, 128) # gray   (#6b7280)
    rgb = (_lerp(g[0], w[0], t), _lerp(g[1], w[1], t), _lerp(g[2], w[2], t))
    return _hex(rgb)

def _lerp(a, b, t): return int(round(a + (b - a) * t))
def _hex(rgb): return "#{:02x}{:02x}{:02x}".format(*rgb)

def _gradient_color(pos, max_pos):
    # 1 -> green (#22c55e), max -> gray (#6b7280)
    pos = max(1, pos)
    t = (pos - 1) / max(1, max_pos - 1)
    g = (34, 197, 94)
    w = (107, 114, 128)
    rgb = (_lerp(g[0], w[0], t), _lerp(g[1], w[1], t), _lerp(g[2], w[2], t))
    return _hex(rgb)

def pescara_positions_view(request):
    pescara = Team.objects.filter(name__icontains="pescara").first()
    if not pescara:
        return render(request, "stats/pos_trend.html", {"rows": [], "max_pos": 0})

    # All league tables in order
    tables = (LeagueTable.objects
              .order_by("date", "jornada")
              .prefetch_related("entries__team"))

    # Build jornada -> game result map ('W','D','L')
    results_by_j = {
        g.jornada: g.result
        for g in PescaraGame.objects.only("jornada", "result")
    }

    rows = []
    max_pos_seen = 0
    for t in tables:
        # find Pescara entry at this jornada
        entry = next((x for x in t.entries.all() if pescara and x.team_id == pescara.id), None)
        if not entry:
            continue

        pos = entry.position
        pts = getattr(entry, "points", None) or 0

        max_pos_seen = max(max_pos_seen, pos)

        # Jornada result chip
        res = results_by_j.get(t.jornada)  # 'W' | 'D' | 'L' | None
        if res == "W":
            res_letter, res_cls = "G", "win"   # Ganó
        elif res == "L":
            res_letter, res_cls = "P", "loss"  # Perdió
        elif res == "D":
            res_letter, res_cls = "E", "draw"  # Empate
        else:
            res_letter, res_cls = "", ""       # no game / unknown

        rows.append({
            "jornada": t.jornada,
            "position": pos,
            "points": pts,              # cumulative points after that jornada
            "res_letter": res_letter,   # G/P/E or ""
            "res_class": res_cls,       # win/loss/draw or ""
        })

    # color for position chip
    max_pos = max_pos_seen or 1
    for r in rows:
        r["color"] = _gradient_color(r["position"], max_pos)

    return render(request, "stats/pos_trend.html", {
        "rows": rows,
        "max_pos": max_pos,
    })