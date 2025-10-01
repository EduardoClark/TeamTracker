from django.db import models
from django.utils import timezone

# 1) Equipos
class Team(models.Model):
    name = models.CharField(max_length=80, unique=True)
    logo = models.ImageField(upload_to="team_logos/", blank=True, null=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

# 2) Jugadores (solo Pescara)
class Player(models.Model):
    first_name = models.CharField(max_length=40)
    last_name  = models.CharField(max_length=40)
    number     = models.PositiveIntegerField()
    photo      = models.ImageField(upload_to="players/", blank=True, null=True)
    active     = models.BooleanField(default=True)

    class Meta:
        ordering = ["number"]
        unique_together = ("first_name", "last_name", "number")

    @property
    def short_name(self):
        return f"{self.first_name[0]}. {self.last_name}"

    def __str__(self):
        return f"{self.number} · {self.short_name}"

# 3) Partidos de Pescara
class PescaraGame(models.Model):
    RESULT_CHOICES = (("W","Win"),("D","Draw"),("L","Loss"))
    jornada       = models.PositiveIntegerField()
    date          = models.DateField(default=timezone.now)
    opponent      = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="games_vs_pescara")
    result        = models.CharField(max_length=1, choices=RESULT_CHOICES)
    goals_for     = models.PositiveIntegerField(default=0)       # Pescara
    goals_against = models.PositiveIntegerField(default=0)       # Rival
    players       = models.ManyToManyField("Player", through="Appearance", related_name="games")

    class Meta:
        ordering = ["date", "jornada"]
        unique_together = ("jornada", "opponent")
        indexes = [models.Index(fields=["jornada"]), models.Index(fields=["date"])]

    def __str__(self):
        return f"J{self.jornada} {self.date} vs {self.opponent}  {self.goals_for}-{self.goals_against}"

    @property
    def goal_difference(self):
        return self.goals_for - self.goals_against

class Appearance(models.Model):
    game   = models.ForeignKey(PescaraGame, on_delete=models.CASCADE, related_name="appearances")
    player = models.ForeignKey(Player, on_delete=models.CASCADE, related_name="appearances")
    goals  = models.PositiveIntegerField(default=0)  # 0–99

    class Meta:
        unique_together = ("game", "player")

    def __str__(self):
        return f"{self.player.short_name} en {self.game} – {self.goals} goles"

# 4) Tabla (snapshot semanal editable)
class LeagueTable(models.Model):
    jornada = models.PositiveIntegerField()
    date    = models.DateField(default=timezone.now)

    class Meta:
        ordering = ["-date", "-jornada"]
        unique_together = ("jornada", "date")

    def __str__(self):
        return f"Tabla J{self.jornada} – {self.date}"

class LeagueTableEntry(models.Model):
    table           = models.ForeignKey(LeagueTable, on_delete=models.CASCADE, related_name="entries")
    team            = models.ForeignKey(Team, on_delete=models.PROTECT)
    position        = models.PositiveIntegerField()
    played          = models.PositiveIntegerField(default=0)      # PJ
    wins            = models.PositiveIntegerField(default=0)      # JG
    draws           = models.PositiveIntegerField(default=0)      # JE
    losses          = models.PositiveIntegerField(default=0)      # JP
    points          = models.IntegerField(default=0)              # Pts
    goal_difference = models.IntegerField(default=0)              # DG

    class Meta:
        unique_together = ("table", "team")
        ordering = ["table", "position"]

    def __str__(self):
        return f"J{self.table.jornada} #{self.position} {self.team} ({self.points} pts, DG {self.goal_difference})"

# 5) Modelo para settings
from django.core.exceptions import ValidationError

class SiteSettings(models.Model):
    site_name   = models.CharField(max_length=120, default="Pescara")
    league_name = models.CharField(max_length=120, blank=True, default="")
    home_club   = models.ForeignKey(Team, on_delete=models.PROTECT, related_name="as_home_club")
    is_active   = models.BooleanField(default=True)
    max_rounds = models.PositiveSmallIntegerField(
        default=25,
        help_text="Total de jornadas.",
    )

    # Optional theme fields (keep for later; not required to function)
    color_primary = models.CharField(max_length=7, blank=True, default="")  # "#0ea5e9" style
    color_accent  = models.CharField(max_length=7, blank=True, default="")
    color_win     = models.CharField(max_length=7, blank=True, default="")
    color_draw    = models.CharField(max_length=7, blank=True, default="")
    color_loss    = models.CharField(max_length=7, blank=True, default="")

    def clean(self):
        # Ensure only ONE active row at a time
        if self.is_active:
            qs = SiteSettings.objects.exclude(pk=self.pk).filter(is_active=True)
            if qs.exists():
                raise ValidationError("Only one active SiteSettings is allowed.")

    def __str__(self):
        name = self.site_name or (self.home_club.name if self.home_club_id else "Site")
        return f"{name} ({'active' if self.is_active else 'inactive'})"