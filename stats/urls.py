from django.urls import path
from . import views

urlpatterns = [
    path("", views.home_view, name="home"),                 # ← NUEVA portada
    path("tabla/", views.standings_view, name="standings"), # ← antes era ""
    path("partidos/", views.matches_view, name="matches"),
    path("partido/<int:pk>/", views.match_detail, name="match_detail"),
    path("jugadores/", views.players_view, name="players"),
    path("jugador/<int:pk>/", views.player_detail, name="player_detail"),
    path("posiciones/", views.pescara_positions_view, name="pescara_positions"),
]