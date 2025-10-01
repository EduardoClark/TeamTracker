from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils import timezone

from .models import (
    Team, Player, PescaraGame, Appearance,
    LeagueTable, LeagueTableEntry, SiteSettings
)



# -----------------------
# Team / Player / Games
# -----------------------

@admin.register(Team)
class TeamAdmin(admin.ModelAdmin):
    list_display  = ("name",)
    search_fields = ("name",)


@admin.register(Player)
class PlayerAdmin(admin.ModelAdmin):
    list_display  = ("number", "first_name", "last_name", "active")
    list_filter   = ("active",)
    search_fields = ("first_name", "last_name")


class AppearanceInline(admin.TabularInline):
    model = Appearance
    extra = 0


@admin.register(PescaraGame)
class PescaraGameAdmin(admin.ModelAdmin):
    list_display    = ("jornada", "date", "opponent", "result", "goals_for", "goals_against")
    list_filter     = ("result", "opponent")
    date_hierarchy  = "date"
    inlines         = [AppearanceInline]


# -----------------------
# League tables
# -----------------------

class LeagueTableEntryInline(admin.TabularInline):
    model = LeagueTableEntry
    extra = 0


@admin.register(LeagueTable)
class LeagueTableAdmin(admin.ModelAdmin):
    list_display       = ("jornada", "date")
    inlines            = [LeagueTableEntryInline]
    date_hierarchy     = "date"
    ordering           = ("-date", "-jornada")
    save_as            = True  # optional: "Save as new" on the change page

    # custom button on the changelist
    change_list_template = "admin/stats/leaguetable/change_list.html"

    # custom URL for cloning latest table
    def get_urls(self):
        urls = super().get_urls()
        my = [
            path(
                "create-from-latest/",
                self.admin_site.admin_view(self.create_from_latest),
                name="stats_leaguetable_create_from_latest",
            ),
        ]
        return my + urls

    def create_from_latest(self, request):
        """
        Create a new LeagueTable (jornada = latest + 1, date = today)
        and clone all its entries so you only edit the changes.
        """
        latest = LeagueTable.objects.order_by("-date", "-jornada").first()
        if not latest:
            messages.warning(request, "No existe una tabla previa para clonar.")
            return redirect("admin:stats_leaguetable_add")

        # Avoid duplicates if already created
        next_jornada = (latest.jornada or 0) + 1
        existing = LeagueTable.objects.filter(jornada=next_jornada).first()
        if existing:
            messages.info(
                request,
                f"Ya existe la tabla J{next_jornada}. Te llevamos a esa página."
            )
            return redirect(reverse("admin:stats_leaguetable_change", args=[existing.pk]))

        # Create new table
        new_table = LeagueTable.objects.create(
            jornada=next_jornada,
            date=timezone.now().date(),
        )

        # Clone entries — only fields that exist on your model
        to_create = []
        for e in latest.entries.all():
            to_create.append(
                LeagueTableEntry(
                    table=new_table,
                    team=e.team,
                    position=getattr(e, "position", 0),
                    played=getattr(e, "played", 0),
                    wins=getattr(e, "wins", 0),
                    draws=getattr(e, "draws", 0),
                    losses=getattr(e, "losses", 0),
                    points=getattr(e, "points", 0),
                )
            )
        LeagueTableEntry.objects.bulk_create(to_create)

        messages.success(
            request,
            f"Tabla J{new_table.jornada} creada a partir de J{latest.jornada}. "
            "¡Edita y guarda los cambios!"
        )
        return redirect(reverse("admin:stats_leaguetable_change", args=[new_table.pk]))
    
@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ("site_name", "league_name", "home_club", "is_active", "max_rounds")
    list_editable = ("is_active",)
    search_fields = ("site_name", "league_name", "home_club__name")
    actions = ["make_active"]

    def make_active(self, request, queryset):
        obj = queryset.first()
        if not obj:
            self.message_user(request, "No item selected.")
            return
        SiteSettings.objects.exclude(pk=obj.pk).update(is_active=False)
        obj.is_active = True
        obj.full_clean()
        obj.save()
        self.message_user(request, f"'{obj}' is now the only active SiteSettings.")
    make_active.short_description = "Set selected as the active SiteSettings (only one)"