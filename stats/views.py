# stats/views.py
from django.shortcuts import render, get_object_or_404
from django.db import models
from django.db.models import Count, Sum
from .models import Team, Player, PescaraGame, Appearance, LeagueTable
from datetime import datetime
from django.utils.dateparse import parse_date
from django.db.models import Q
from django.shortcuts import get_object_or_404



def _latest_table():
    return LeagueTable.objects.order_by("-date", "-jornada").first()


def standings_view(request):
    table = _latest_table()
    entries = table.entries.select_related("team").all() if table else []
    return render(request, "stats/standings.html", {"table": table, "entries": entries})


def matches_view(request):
    qs = (PescaraGame.objects
          .select_related("opponent")
          .prefetch_related("appearances__player")  # ← importante para el sándwich
          .order_by("date"))

    # (si ya tienes filtros/paginación, mantén tu lógica aquí)
    result = request.GET.get("result")
    if result in {"W", "D", "L"}:
        qs = qs.filter(result=result)

    dfrom = request.GET.get("from")
    dto   = request.GET.get("to")
    if dfrom:
        df = parse_date(dfrom)
        if df: qs = qs.filter(date__gte=df)
    if dto:
        dt = parse_date(dto)
        if dt: qs = qs.filter(date__lte=dt)

    games = qs  # o tu paginador si lo usas
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