from django.urls import path
from . import views

urlpatterns = [
    path("", views.standings_view, name="standings"),
    path("partidos/", views.matches_view, name="matches"),
    path("partido/<int:pk>/", views.match_detail, name="match_detail"),  # ← NUEVO
    path("jugadores/", views.players_view, name="players"),
    path("jugador/<int:pk>/", views.player_detail, name="player_detail"),
]