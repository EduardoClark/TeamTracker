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


def players_view(request):
    # Parámetros GET: sort = number|goals|gpm , q = texto de búsqueda
    sort = request.GET.get("sort", "number")
    q = request.GET.get("q", "").strip()

    base = Player.objects.filter(active=True)

    if q:
        base = base.filter(
            Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )

    players = (
        base
        .annotate(
            gp=Count("appearances__game", distinct=True),
            goals_total=Sum("appearances__goals"),
        )
    )

    # Normaliza totals para cálculo G/M y orden
    rows = []
    for p in players:
        p.goals_total = p.goals_total or 0
        gpm = round(p.goals_total / p.gp, 2) if p.gp else 0
        rows.append({"player": p, "gpm": gpm})

    # Ordenamiento en Python (dataset chico); si crece, movemos a anotaciones SQL
    if sort == "goals":
        rows.sort(key=lambda r: (r["player"].goals_total, r["gpm"]), reverse=True)
    elif sort == "gpm":
        rows.sort(key=lambda r: (r["gpm"], r["player"].goals_total), reverse=True)
    else:
        rows.sort(key=lambda r: r["player"].number)

    # Carga apariciones para el sándwich
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

    last_game = (
        PescaraGame.objects.select_related("opponent")
        .filter(date__lte=today).order_by("-date", "-jornada").first()
    )
    next_game = (
        PescaraGame.objects.select_related("opponent")
        .filter(date__gt=today).order_by("date", "jornada").first()
    )

    table = LeagueTable.objects.order_by("-date", "-jornada").first()

    # ⬇️ AQUÍ lo sencillo: toma la fila de Pescara en esa tabla
    entry = None
    if table:
        entry = table.entries.select_related("team")\
            .filter(team__name__icontains="pescara")\
            .first()

    total_rounds = LeagueTable.objects.aggregate(m=Max("jornada"))["m"] or 24

    pescara_team = Team.objects.filter(name__icontains="pescara").first()

    return render(request, "stats/home.html", {
        "last_game": last_game,
        "next_game": next_game,
        "latest_table": table,
        "entry": entry,
        "total_rounds": total_rounds,
        "pescara_team": pescara_team,   # ← add this
    })

    return render(request, "stats/home.html", {
        "last_game": last_game,
        "next_game": next_game,
        "latest_table": table,
        "entry": entry,
        "total_rounds": total_rounds,
    })