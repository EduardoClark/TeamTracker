# stats/views.py
from django.shortcuts import render, get_object_or_404
from django.db import models
from django.db.models import Count, Sum
from .models import Team, Player, PescaraGame, Appearance, LeagueTable


def _latest_table():
    return LeagueTable.objects.order_by("-date", "-jornada").first()


def standings_view(request):
    table = _latest_table()
    entries = table.entries.select_related("team").all() if table else []
    return render(request, "stats/standings.html", {"table": table, "entries": entries})


def matches_view(request):
    games = PescaraGame.objects.select_related("opponent").order_by("date")
    return render(request, "stats/matches.html", {"games": games})


def players_view(request):
    players = (
        Player.objects.filter(active=True)
        .annotate(gp=Count("appearances__game", distinct=True),
                  goals_total=Sum("appearances__goals"))
        .order_by("number")
    )
    rows = []
    for p in players:
        p.goals_total = p.goals_total or 0
        gpm = round(p.goals_total / p.gp, 2) if p.gp else 0
        apps = (
            Appearance.objects
            .filter(player=p)
            .select_related("game", "game__opponent")
            .order_by("game__date")
        )
        rows.append({"player": p, "gpm": gpm, "apps": apps})
    return render(request, "stats/players.html", {"rows": rows})


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