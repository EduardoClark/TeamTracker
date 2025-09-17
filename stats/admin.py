from django.contrib import admin
from .models import Team, Player, PescaraGame, Appearance, LeagueTable, LeagueTableEntry

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)

@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display = ("number", "first_name", "last_name", "active")
    list_filter  = ("active",)
    search_fields= ("first_name", "last_name")

class AppearanceInline(admin.TabularInline):
    model = Appearance
    extra = 0

@admin.register(PescaraGame)
class PescaraGameAdmin(admin.ModelAdmin):
    list_display = ("jornada", "date", "opponent", "result", "goals_for", "goals_against")
    list_filter  = ("result", "opponent")
    date_hierarchy = "date"
    inlines = [AppearanceInline]

class LeagueTableEntryInline(admin.TabularInline):
    model = LeagueTableEntry
    extra = 0

@admin.register(LeagueTable)
class LeagueTableAdmin(admin.ModelAdmin):
    list_display = ("jornada", "date")
    inlines = [LeagueTableEntryInline]